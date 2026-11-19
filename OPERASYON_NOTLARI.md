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
| Gösterge kaydı | yok | **giriş anı anlık görüntü** | RSI/EMA mesafe/hacim/ATR/MACD/4h trend/BTC rejimi her girişte kaydedilir; `/istatistik`'te kazanan vs kaybeden ortalamaları gösterilir. Kararda kullanılmaz, sadece veridir |

> `/istatistik` komutu: işlem bazlı WR, ortalama kazanç/kayıp oranı, break-even WR, çıkış nedenleri dökümü ve en çok kaybettiren semboller. Yeni kayıtlar `poz_id` ile gruplanır; eski kayıtlarda symbol+entry fallback'i kullanılır.

## V6.2 — Giriş rejimi filtresi (06.11.2026)

41 işlemlik `scalp_bot_state.json` analizi: TP1 isabeti %56.1, teorik rastgele yürüyüş isabeti %55.6 — yani yön tahmini rastgele ile aynıydı; komisyonlar (−$0.086/işlem) beklentiyi negatife çekiyordu (−$0.092/işlem). Gösterge karşılaştırması iki güvenilir ayırıcı buldu (her ikisi de ilk 20 / son 21 işlem yarı-örneklem testinde tutarlı):

| Koşul | Geçen grup | Reddedilen grup |
|---|---|---|
| `ema_dist ≥ 0.45` | n=14, WR %79, EV **+$0.242** | n=27, WR %44, EV −$0.265 |
| `vol_ratio ≤ 1.8` | n=25, EV +$0.031 | n=16, EV **−$0.283** |
| **İkisi birlikte** | **n=8, WR %88, EV +$0.446** | n=33, toplam −$7.32 |

`faz2_sinyal.calculate_score_fatih` içinde skorlamadan önce sert eleme olarak uygulanır (`MIN_EMA_DIST`, `MAX_VOL_RATIO`). Etki: giriş bandı `0.45 ≤ ema_dist < 0.8` ve `1.3 ≤ vol_ratio ≤ 1.8` ile sınırlanır. Beklenen işlem sıklığı günde ~0.6'ya düşer (az ama kârlı). Doğrulama: sonraki ~40 işlemde filtre alt grubunun EV'si >0 kalmalı; aksi halde iki config değeriyle geri alınır.

Bilinen sınırlar: 40/41 işlem SHORT olduğundan long tarafı hâlâ sınanmadı; n=8 küçük örneklem, hipotez güçlü ama kesinleşmedi.

## V6.3 — Volatilite bandı (19.11.2026)

V6.2 doğrulama kapısı ilk kontrolde (n=24) geçemedi: EV −$0.020 (hedef ≥ +$0.15), WR %58.3 (hedef ≥ %65), drawdown %7.5 (kapı %10). Yarı-örneklem bozuluyor: ilk 12 EV +$0.103 → son 12 EV −$0.144. V6.2 zararı azalttı (önceki −$0.092) ama hedefe taşımadı.

24 işlemlik veride tek yarı-örneklem tutarlı ayırıcı ATR oldu:

| Giriş anı 1h ATR% | n | WR | EV/işlem | İlk 12 EV | Son 12 EV |
|---|---|---|---|---|---|
| ≤ 1.3 | 15 | %73 | **+$0.225** | +$0.24 | +$0.20 |
| > 1.3 | 9 | %33 | **−$0.429** | −$0.18 | −$0.63 |

Bant (0.7–1.3] simülasyonu: n=12, WR %75, EV +$0.286 (ilk yarı +$0.40 / son yarı +$0.20). Alt sınır 0.7'nin kanıtı 41 işlemlik turdan (ATR ≤ 0.7 grubu EV −$0.179, n=29). Eşik jilet değil: 1.2 ve 1.3 eşikleri aynı sonucu veriyor. Mekanizma: giriş anında ATR yüksekse hareet zaten olmuş, geç kalınmış giriş → STOP; ATR çok düşükse TP'ye ulaşacak hareket yok.

`faz2_sinyal.calculate_score_fatih` içinde V6.2 kontrollerinden sonra sert eleme (`MIN_ATR_PCT`, `MAX_ATR_PCT`). Beklenen işlem sıklığı ~%50 düşer (~0.9/gün). Doğrulama: sonraki ~40 işlemde bant-içi grubun EV'si >0 kalmalı; aksi halde iki config değeriyle geri alınır.

Reddedilen adaylar (bu turda sağlanmadı): ema200 yorgunluğu (≤ −20) yarı-örneklemde tutmadı; RSI ≤ 45 hipotezi tersine döndü (>50 iyi çıktı) — RSI eşiği gürültü, uygulanmadı. İzlemede: aynı sembole anında tekrar giriş (2/2 kayıp, örneklem çok küçük).

Bilinen sınırlar: 24/24 işlem SHORT; long tarafı hâlâ sınanmadı; ATR üst sınırı n=9'luk kayıp grubundan geldi (yarı-örneklem desteğiyle).

## V6.3.1 — Giriş zamanı kaydı (19.11.2026)

Davranış değişikliği yoktur (filtre/karar mantığı aynı): `pozisyon_kapat` çıkış kayıtlarına `giris_zamani` alanı eklenir ve `/istatistik` kazanan / kaybeden / STOP işlemlerinin ortalama tutma süresini saat cinsinden gösterir. Amaç: saf STOP'ların ne kadar sürdüğünü ölçmek ve "ilerlemeyen işlemden erken çık" (zaman-stop) hipotezini kanıta dayalı test edebilmek. Bu sürümden önce açılmış işlemlerde alan yoktur; ortalamaya girmez. Doğrulama verisini bulandırmaz, sadece kayıt ekler.

## Backtest aracı ve 10 aylık bulgular (19.11.2026)

Canlı botu etkilemeyen ayrı bir araç `backtest/` altına eklendi (hiçbir canlı
modül bu paketi import etmez):

- `python -m backtest.calistir indir` — Binance USDT-M 1h, 15 sembol, 345 gün
- `python -m backtest.calistir analiz` — sinyal seviyesinde filtre/gösterge analizi
- `python -m backtest.calistir motor v63|v62|filtresiz` — portföy simülasyonu
- Veri (`backtest/veri/`) ve sonuçlar (`backtest/sonuclar/`) git'e girmez.

Motor `paper_trade.py` kurallarının 1h aynasıdır: giriş kayması + taker komisyon,
%1/%2 risk boyutlandırması, SL 1.5 / TP 1.2-1.89-2.7 ATR, TP1 %40 + BE, TP2 %30,
aynı barda SL önce (kötümser), STOP 240 dk / BE 45 dk cooldown, günlük %3 kayıp,
%20 max drawdown. Fonlama ve spread modellenmez.

**10 ay (2026-01-18 → 11-19, 15 sembol):**

| Konfig | İşlem | EV/işlem | WR | Max DD |
|---|---|---|---|---|
| Filtresiz | 144 | −$0.118 | %50.7 | %20.5 |
| V6.2 | 157 | −$0.097 | %54.1 | %20.8 |
| V6.3 | 228 | −$0.081 | %55.3 | %20.2 |

İşlem sayıları yol bağımlıdır (erken DD kilidi daha az işlem üretir); asıl ölçü
EV/işlemdir. Hiçbir konfig pozitif değil; V6.3 en az kaybettiren, ama kapı hedefi
(+$0.15) hâlâ uzak.

**Sinyal seviyesi (6.132 filtresiz 4/4 sinyal):** TP1 isabeti %55.7, rastgele
beklenti %55.6 → skor sistemi yön kenarı üretmiyor. Tur maliyeti 16 bps
(%0,05 giriş + %0,05 çıkış + %0,03×2 kayma); brüt kenar yalnızca ~+1.6 bps
(V6.3'te ~+7 bps). **Darboğaz indikatör değil, maliyet.**

**Gösterge ayrımı (tutarlı olanlar):** ATR > 1.6 en toksik bölge (−54 bps, her
iki yarıda negatif; V6.3 üst sınırı doğru yönde). ATR 0.7–1.3 tek başına pozitif
değil (−14 bps). En tutarlı ayrım MACD: SHORT'ta MACD histogramı > 0 (ters
momentum) −6.6 bps, < −0.2 ise −30 bps. ATR<1.3 + SHORT MACD>0 birlikte −7.7 bps
(ilk yarı −9.1 / son yarı −5.9) — hâlâ maliyetin altında. Hiçbir gösterge tek
başına pozitif EV üretmiyor.

**Operasyonel bulgu:** %20 max drawdown kuralı kalıcı kilit yaratıyor. Simülasyonda
Temmuz'da eşik aşıldı; açık pozisyon kalmadığı için efektif bakiye toparlanamadı
ve son 4 ay hiç işlem açılmadı. Canlıda da aynı durum yaşanır: kilit, bakiye
yükselmeden açılmaz, bakiye de işlem olmadan yükselmez. Bu kuralın bir toparlanma
mekanizmasına (ör. %15'te yarım boyutla devam) ihtiyacı var.

Bu araç V6.3 canlı doğrulamasını etkilemez; karar mantığında hiçbir değişiklik
yapılmadı.

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
