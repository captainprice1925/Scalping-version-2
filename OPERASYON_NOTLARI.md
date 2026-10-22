# Scalping V6 Operasyon Notları

## Kapsam

Bu sürüm **paper-trade** içindir. Gate'ten piyasa ve fonlama verisi çekebilir, ancak borsaya emir göndermez, API anahtarı kullanmaz ve gerçek hesap bakiyesiyle eşleşme iddiasında bulunmaz. Gerçek işlem entegrasyonu, bu simülasyon sonuçları doğrulandıktan sonra ayrı bir çalışma olmalıdır.

## Pozisyon boyutlandırması

Varsayılan sanal sermaye **100 USDT**, kaldıraç **10×** ve işlem başına hedef risk **efektif sermayenin %1'i**dir. Pozisyonun brüt büyüklüğü sabit değildir. Giriş ile stop arasındaki fiyat hareketi, giriş/çıkış komisyonu ve giriş/çıkış slippage varsayımları birlikte hesaplanır. Marjin, bu hesapla bulunan pozisyon büyüklüğünün on kat kaldıraç karşılığıdır.

> `notional = risk bütçesi / (stop fiyat riski + giriş komisyonu + çıkış komisyonu)`
>
> `marjin = notional / kaldıraç`

İşlem başına marjin 2,5–10 USDT (10× kaldıraçta yaklaşık 25–100 USDT notional) ile sınırlandırılır. Açık pozisyonların toplam tahmini stop riski efektif sermayenin %2'sini, toplam marjini ise efektif sermayenin %30'unu geçemez. Aynı anda en fazla iki pozisyon açılır. Bu sınırlar `config.py` içindedir.

Örnek olarak, giriş 100, ATR 1 ve 1,5 ATR stopta ham stop mesafesi %1,5'tir. V6 varsayımlarında giriş ve çıkışta %0,05 taker komisyonu ile her yönde %0,03 slippage ayrıca dikkate alınır. 100 USDT efektif sermayede %1 risk bütçesiyle motor, sınırlar uygunsa yaklaşık 60 USDT brüt pozisyon ve 6 USDT marjin üretir. Kesin değer, anlık ATR, açık pozisyon riski ve marjin sınırlarına göre değişir.

## Maliyet modeli

| Maliyet bileşeni | Varsayılan | Uygulama |
|---|---:|---|
| Giriş komisyonu | %0,05 | Pozisyon açılırken nakitten düşer. |
| Çıkış komisyonu | %0,05 | Her kısmi veya tam çıkışta düşer. |
| Giriş slippage | %0,03 | Long girişini yükseltir, short girişini düşürür. |
| Çıkış slippage | %0,03 | Long çıkışını düşürür, short çıkışını yükseltir. |
| Funding | Gate geçmişindeki gerçekleşmiş oran | Pozitif oranda long öder/short alır; negatif oranda tersi uygulanır. |

Komisyon oranları Gate hesabının VIP seviyesi ve emir türüne göre değişir. Varsayılanlar yalnızca muhafazakâr bir **taker** simülasyonudur. Gerçek hesabın güncel maker/taker oranları doğrulanınca `GIRIS_KOMISYON_ORANI` ve `CIKIS_KOMISYON_ORANI` değiştirilmelidir. Gate işlem ücretini kaldıraçtan bağımsız olarak pozisyon değeri üzerinden, fonlamayı ise pozisyon değeri çarpı funding rate olarak tanımlar.[1] [2]

## Tasfiye koruması

Motor, 10× izole kaldıraç için bakım marjinini hariç tutan yaklaşık bir tasfiye fiyatı hesaplar ve stopun bu seviyeden en az %0,5 uzakta olmasını ister. 10×'te tahmini likidasyon girişe yaklaşık %10 mesafededir; stoplar bu sınırın belirgin biçimde içinde kalır. Bu kontrol güvenlik filtresidir; **Gate'in gerçek tasfiye fiyatı değildir**. Gerçek emir uygulamasında borsanın API üzerinden döndürdüğü liquidation price, bakım marjini, risk limiti ve çapraz/izole marjin modu kullanılmalıdır.

## Pozisyon yönetimi düzeltmeleri

Geniş bir mum TP3'e ulaşırsa V6 önce TP1'de %40, ardından TP2'de %30 ve kalan %30'u TP3'te işler. Aynı mumda hem stop hem hedef görülürse stop önceliği korunur. Ayrıca açılış zamanından önce oluşmuş 1 dakikalık mumlar yeni pozisyona uygulanmaz. Oluşmakta olan (henüz kapanmamış) son mum ise kapanana kadar her tarama turunda yeniden değerlendirilir; böylece mum içinde oluşan SL/TP dokunuşları kaçırılmaz.

## V6.1 — PnL düzeltme paketi (18.10.2026)

Log analizi: 282 "işlem" gerçekte 282 **çıkış olayı**; TP1'de kapatılan %40'lık parçalar ayrı kazanç sayıldığı için win rate (%72) şişiyordu. Gerçek beklenti negatifti: TP1 kazancı 0.4×1.2 ATR iken tam stop 1.5 ATR — kazanç/kayıp kırılganlığı ~3.3x, yani break-even için %77+ işlem bazlı WR gerekiyor.

Alınan önlemler (hepsi `config.py`'den yönetilir):

| Değişiklik | Eski | Yeni | Gerekçe |
|---|---|---|---|
| `MIN_SKOR` | 3 | **4** | Hacim onayı (≥1.3x) zorunlu; logda Vol 0.7x ile girilen 3/4 sinyaller negatif EV kaynağıydı |
| `MAX_AYNI_YON` | 2 | **1** | Taramada tüm sinyaller tek yöndeydi (SHORT); korele çift stop riski |
| `COOLDOWN_DAKIKA` | 90 | **240** | STOP sonrası 1h sinyal hâlâ geçerliyken tekrar girip aynı chop'ta ikinci stop |
| BTC rejim filtresi | yok | **aktif** | BTC dışı coinler BTC 4h trendinin tersine gitmez |
| BE seviyesi | sinyal fiyatı | **gerçek doluş fiyatı** | TP1 sonrası BE artık gerçekten başa baş |
| İstatistik | olay bazlı | **işlem bazlı** (`/istatistik`) | Kısmi TP parçaları tek işleme toplanır; break-even WR ve beklenti gösterilir |
| Girişte spread | yok (6 saatte bir) | **anlık kontrol** | Sinyal anında spread açılabilir; `SPREAD_MAX` üstü giriş yok, okunamazsa giriş atlanır |
| Marjin tavanı | sabit $10 | **max($10, bakiye×%10)** | Bakiye büyüyünce kazanç artık kilitlenmiyor |
| Fallback listesi | TUTUSDT içeriyor | **temizlendi** | Fallback aktifse mikro-cap'e girilmez |

> `/istatistik` komutu: işlem bazlı WR, ortalama kazanç/kayıp oranı, break-even WR, çıkış nedenleri dökümü ve en çok kaybettiren semboller. Yeni kayıtlar `poz_id` ile gruplanır; eski kayıtlarda symbol+entry fallback'i kullanılır.

## Dağıtım

`Procfile`, `wsgi:app` ile tek Gunicorn worker ve tek thread kullanır. Birden fazla worker, aynı botun birden fazla kez başlamasına yol açacağı için desteklenmez. `wsgi.py` başlatıldığında bot thread'i tek sefer başlatılır.

## Telegram komutları

Bot ayaktayken Telegram sohbetinden şu komutlar sorulabilir. Yanıtlar yalnızca `TELEGRAM_CHAT_ID` ile eşleşen sohbete gönderilir; diğer sohbetlerden gelen mesajlar yok sayılır.

| Komut | Yanıt |
|---|---|
| `/durum` | Açık pozisyonlar + bakiye/efektif/günlük PnL/drawdown/cooldown özeti |
| `/pozisyonlar` | Yalnızca açık pozisyonların özeti |
| `/istatistik` | İşlem bazlı WR, ort. kazanç/kayıp, break-even WR, çıkış nedenleri dökümü |
| `/state` | `scalp_bot_state.json` dosyasını belge olarak gönderir (ücretsiz Render planında shell erişimi olmadan yedek/analiz için) |
| `/hata` | Son hata kayıtları + sistem durumu (başlangıç, son tarama) |
| `/yardim` | Komut listesi |

Komut dinleyicisi Telegram `getUpdates` ile çalışır; bot hesabında webhook kurulu olmamalıdır ve aynı bot token'ı ile tek örnek çalıştırılmalıdır (çoklu örnek `getUpdates` çakışması yaratır). Özellik salt-okunurdur: emir göndermez, hesap durumunu değiştirmez.

## Kontrol listesi

Gerçek para aşamasına geçmeden önce Gate hesabındaki ücret tablosunu girin, en az 30 gün paper sonuçlarını izleyin, her sembolün kontrat çarpanını ve minimum emir büyüklüğünü doğrulayın, fonlama tahakkuklarını hesap ekstresiyle karşılaştırın ve ayrı bir gerçek-emir adaptörüne kill-switch ile günlük kayıp sınırı ekleyin; borsadaki kaldıraç ve risk limiti ayarlarını 10× ile eşleştirin.

## References

[1]: https://www.gate.com/help/futures/futures_logic/22079 "Futures Trading Fee Calculation | Gate"
[2]: https://www.gate.com/help/futures/futures-logic/27569/funding-rate-and-funding-fee "Contract Funding Rate and Funding Fee Explanation | Gate"
