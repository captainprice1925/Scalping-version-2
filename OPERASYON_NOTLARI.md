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

## V6.3.2 — Drawdown toparlanma modu (19.11.2026)

Risk yönetimi düzeltmesi; sinyal/filtre mantığı değişmedi (`faz2_sinyal.py` aynı).
Eski kural %20 drawdown'da **kalıcı kilit** yaratıyordu: açık pozisyon kalmayınca
efektif bakiye toparlanamıyor, bakiye de işlem olmadan yükselmediği için bot
sonsuza kadar işlem açmıyordu (10 aylık backtest: Haziran'da kilit, sonraki 4 ay
hiç işlem yok — 3667/4124 bar).

Yeni kural histerezisli ve kademeli (`config.py`):

| Drawdown | Mod | Davranış |
|---|---|---|
| < %15 | normal | tam risk (%1 işlem / %2 toplam) |
| %15 – %20 | mevcut mod korunur | erken zıplamayı önler |
| %20 – %30 | kurtarma | işlem riski yarıya iner (`DD_KURTARMA_RISK_ORANI=0.5`) |
| ≥ %30 | durdu | yeni işlem yok, manuel müdahale |

`paper_trade.py`: `drawdown_durumu()` modu hesaplar, `risk_carpani` boyutlandırmaya
geçer, state'e `drawdown_modu` yazılır. `_max_drawdown_kontrol()` geriye dönük
uyum için yalnızca `durdu` modunda `True` döner. `backtest/motor.py` aynı kuralları
uygular (`_dd_durumu`, `boyutlandir(..., risk_carpani)`); `simule.py` içine
`eski_dd_cfg()` (eski kalıcı kilit) karşılaştırma için eklendi.

Canlı state 19.11.2026'da %7,5 drawdown'da olduğu için yeni mod **dormant**;
V6.3 doğrulamasını etkilemez. 6 yeni test (canlı + motor modları, yarım risk,
durdu modunda giriş engeli) eklendi; toplam 51 test.

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
Haziran'da eşik aşıldı; açık pozisyon kalmadığı için efektif bakiye toparlanamadı
ve son 4 ay hiç işlem açılmadı. Canlıda da aynı durum yaşanır: kilit, bakiye
yükselmeden açılmaz, bakiye de işlem olmadan yükselmez. Bu bulgu V6.3.2'deki
histerezisli kurtarma modunun gerekçesidir.

Bu araç V6.3 canlı doğrulamasını etkilemez; karar mantığında hiçbir değişiklik
yapılmadı.

### Baraj genişletme bulgusu (19.11.2026)

Sinyal analizinin işaret ettiği darboğaz maliyetti: tur başına ~16 bps, brüt kenar
~1.6 bps. Tur maliyeti baraj mesafesinden **bağımsız sabittir**; 1.2 ATR'lik TP1
çok yakın olduğu için maliyet hedefin büyük kısmını yiyor. Hipotez: TP/SL
mesafelerini ATR cinsinden aynı oranda genişletmek, maliyetin payını düşürür.

`backtest/simule.genis_cfg(oran)` TP/SL'i `oran` katına çıkarır ve `ZAMAN_EXIT_SAAT`
de aynı oranda ölçekler (aksi halde geniş barajlar zaman çıkışına takılır).

**Ana evren (15 sembol, 10 ay, taker):**

| Baraj | İşlem | EV | WR | İlk yarı | Son yarı | Max DD | Son bakiye |
|---|---|---|---|---|---|---|---|
| 1.0× (canlı) | 299 | −7.1 bps | %54.8 | −9.4 | −3.8 | %24.5 | $78.73 |
| 2.0× | 200 | **+10.7 bps** | %59.5 | +8.7 | +12.8 | %12.1 | $105.87 |
| 2.5× | 139 | +7.5 bps | %59.7 | +5.3 | +9.6 | %11.5 | $103.36 |
| 3.0× | 92 | +32.7 bps | %62.0 | +39.0 | +26.2 | %7.5 | $109.32 |
| 3.5× | 40 | +10.8 bps | %57.5 | +5.4 | +17.5 | %4.3 | $100.97 |

**Dış örneklem (hiç kullanılmamış 8 sembol, aynı dönem):** 1.0× +3.0, 2.0× +5.8,
2.5× +45.2, 3.0× +68.1 bps. Yön ana evrenle aynı: genişletme EV'yi artırıyor.
(2.0× dış örneklemde yarı-örneklemde tutarsız: +39.7 / −39.2.)

**Stres:** 2.0× çift kayma ile +4.7 bps (hâlâ pozitif), 2.5× çift kaymada −11.0
bps. Maker girişte 2.0× +16.6 bps.

**Sınırlar:** örneklem küçük (92-200 işlem), çeyrek bazında tutarsızlık var
(ana evren 3.0×: Q3 −57 bps), sonuç sembol evrenine duyarlı, 1h barı doldurma
iyimser değil ama kesin de değil. Fonlama modellenmiyor; canlı kayıtta SHORT
tarafı fonlamadan **kazandı** (+$0.113 / 41 işlem), yani gizli maliyet değil.

**Karar:** 2.0× en sağlam nokta (en çok işlem, iki yarıda pozitif, kayma stresine
dayanıklı). Ancak bu canlı bir kural değişikliğidir ve V6.3 doğrulaması sürerken
uygulanmadı. V6.3 kapısı kapandıktan sonra V6.4 olarak, tek değişiklik kuralıyla
uygulanabilir.

**Hazırlık:** `config.BARAJ_GENISLETME` anahtarı eklendi. Varsayılan `1.0` bugünkü
davranışı birebir korur (testli); `2.0` yapıldığında SL 3.0 / TP1 2.4 / TP2 3.78 /
TP3 5.4 ATR ve zaman çıkışı 48 saat olur. `paper_trade`, `backtest/simule` ve
`config.ZAMAN_EXIT_SAAT_ETKIN` aynı anahtarı okur, böylece canlı ve backtest
paritesi korunur. `/durum` ve başlangıç mesajı artık sürüm, baraj çarpanı ve
drawdown modunu gösterir (`🧩 V6.3.2 · baraj ×1 · DD modu: normal`).

### V6.4 — önceden kayıtlı doğrulama kapısı (onay: 20.11.2026)

V6.4 = tek değişiklik: `BARAJ_GENISLETME = 1.0 → 2.0`. yeni filtre/indikatör yok.
V6.3 kapısı kapandıktan sonra başlar; aynı anda iki değişiklik yapılmaz.

| Ölçüt | Eşik |
|---|---|
| İşlem sayısı | ≥ 60 |
| Beklenti (notional) | ≥ +5 bps/işlem |
| İşlem bazlı WR | ≥ %57 |
| Max drawdown | ≤ %15 |

**Neden dolar EV kapısı değişti:** baraj genişleyince aynı %1 risk daha küçük
notional alır (SL mesafesi 2 katı), dolayısıyla dolar EV yapısal olarak düşer.
V6.3'ün +$0.15/işlem hedefi V6.4'te ulaşılamaz (backtest +$0.029/işlem). Bps
birimi pozisyon büyüklüğünden bağımsızdır ve backtest karşılaştırmasıyla aynı
birimdir. `/istatistik` bu satırı artık basıyor:
`📐 Beklenti (notional): +X.X bps/işlem — n=N`.

**Geri alma kuralı:** 60 işlem sonunda dört ölçütten herhangi biri tutmazsa
`BARAJ_GENISLETME = 1.0` yapılır ve V6.3 davranışına dönülür (tek satır, state
uyumlu). Kapı geçilirse değer 2.0'da kalır ve yeni tur açılmaz.

#### Ara okuma — 9 işlem (26.11.2026), karar değişmedi

| Ölçüt | Değer | Kapı | Durum |
|---|---|---|---|
| İşlem | 9 | ≥ 60 | %15 |
| Beklenti (notional) | +5.6 bps | ≥ +5 | kıl payı |
| İşlem bazlı WR | %55.6 | ≥ %57 | altında |
| Max DD | ~%2.2 | ≤ %15 | rahat |

Bu sayılar **hiçbir şey kanıtlamaz**, üç sebepten:

1. **Dokuz işlem bağımsız değil.** Dokuzunun tamamı SHORT ve dokuzunda da
   `btc_yukari = false`. Yani tek bir rejimde, tek yönde alınmış bir bahis;
   örneklem büyüklüğü 9 değil ~1. BTC rejimi dönünce farklı bir popülasyon
   işlem görecek.
2. **Tek işlem çıkarınca işaret dönüyor.** En iyi işlem (BTC +$1.04) çıkarılınca
   toplam −$0.75 ve EV −14 bps. BTC sembolünü tamamen çıkarınca kalan 5 işlem
   −$1.80. t-stat 0.12, EV %95 aralığı −107 … +121 bps.
3. **Dolum iyimserliği payı küçük.** Çıkışların her biri 2 bps daha kötü
   dolarsa EV +3.5 bps'e, 5 bps daha kötü dolarsa +0.5 bps'e düşer — yani kapı
   kapanır. Ayrıca TP merdiveni tek mumda basamak basamak doluyor kabul ediliyor
   (bir BTC işleminde TP1 ve TP2 0.18 sn arayla doldu); mum içi sıralama
   bilinmediği için bu standart ama iyimser bir varsayım.

**Kâr/beklenti geometrisi:** risk %1 (~$1.00), ortalama kazanç ~$0.86 → başabaş
WR %53.8. Gerçekleşen %55.6, yani başabaşın 1.8 puan üstünde; WR standart
hatası ±16.6 puan. Ayırt etmek için 200-300 işlem gerekir. Mevcut hızda
(~1.5 işlem/gün) 60 işlem ≈ 40 gün.

**Karar:** konfige dokunulmadı. 60 işlem beklenir, kapı tek seferde değerlendirilir.

**Kapıyı elle tartışmamak için araç:** `backtest/kapi.py`. State dosyasını okur,
dört ölçütü `/istatistik` ile birebir aynı tanımla (poz_id gruplaması, notional
ağırlıklı bps) hesaplar ve hükmü basar:

```bash
python -m backtest.kapi --state scalp_bot_state.json
```

Çıktı üç durumdan biri olur: `HAZIR DEĞİL` (< 60 işlem, karar yok), `KAPI GEÇTİ`
(2.0'da kalır), `KAPI KALDI` (hangi ölçüt düştüyse yazar, geri alma kuralı
hatırlatılır). Tek yön uyarısı ve "en iyi işlem çıkarılınca net" satırı da basılır.

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

## Kesitsel momentum araştırması — kapandı (canlıya alınmıyor)

Amaç: tek coinin yönünü tahmin etmek yerine sepet içinde **göreli** gücü işlemek.
Her dengelemede son `geri_bak` barın getirisine göre en güçlü N coin LONG, en zayıf
N coin SHORT; dolar-nötr; sinyal kapanışta hesaplanır, giriş sonraki barın
açılışında (ileriye bakış yok); fonlama modellenmez.

Araç: `backtest/kesitsel.py` + `python -m backtest.calistir kesitsel`.
Veri: 23 sembol, 4h, 2022-11-25 → 2026-11-19 (8.761 bar, `backtest/veri_uzun/`).

**Neden kapandı — ölçümler:**

- Tek yıllık dilimde (2025-11→2026-11) en iyi hücre +%98 görünüyordu. 4 yıla
  çıkınca kayboldu: aynı hücrenin 4 yıllık faz medyanı +%20, DD %52.
- **Faz medyanı** esastır: canlıda giriş zamanını sen seçmiyorsun, ızgara `tut`
  adımıyla ilerlediği için en fazla `tut` kadar benzersiz faz var. 24 fazın
  14'ü pozitif, en kötü −%50, en iyi +%271. Bu yayılım kenarın zayıf olduğunun
  kanıtı: 4 saatlik kayma sonucu 7 katına çıkarabiliyor.
- Yıl yıl medyan: 2022-23 −%17.4 · 2023-24 +%21.4 · 2024-25 −%9.6 · 2025-26 +%49.2.
  Dört yılın ikisi negatif; bileşik medyan ≈ +%4.7/yıl.
- Parametre komşuluğu uçurum: g12/t24 +%46 iken g42/t24 −%47, g6/t12 −%61.
  Dar bir ada, etrafı çukur → uydurulmuş gürültü işareti.
- Kâr iki coine bağlı: WLD +%62, ZEC +%55; ikisi çıkarılınca geriye ≈0 kalıyor.
- IC testi (sıralamanın gelecek getiriyi bilme gücü): 28 kombinasyondan yalnızca
  1'i |t|>2; seçilen konfigin IC'si t=0.66.
- Kaldıraç medyanı **düşürüyor**: 1× +%20 → 2× −%10 → 3× −%60 (oynaklık sürüklenmesi).

**10× hedefi:** 5× brütte bile P(10×/10 ay) ≈ %7, P(yarısını kaybetme) ≈ %19
(faz dağılımı) veya %51 (işlem bootstrap'ı). Yani 10× ancak kumar olarak alınır.

Yan bulgu (düzeltildi): `backtest/veri.py` Binance kline alanlarını string olarak
kaydediyordu; 4 yıllık indirmede panel `object` dtype'a düşüp karşılaştırmaları
bozuyordu. `indir_binance` artık OHLCV'yi sayıya çeviriyor, `panel` de `float`'a
zorluyor.

## Fonlama taşıması — ölçüldü, gerçek ama küçük

Yön tahmini gerektirmeyen tek kripto primi: **delta-nötr taşıma**. Spot'ta al,
aynı notionalda vadeli short; fiyat nereye giderse gitsin iki bacak birbirini
götürür, kazanç yalnızca fonlamadan gelir (pozitif fonlamada short **alır**).
Sermaye = `notional * (1 + 1/kaldıraç)`; getiri sermayeye göre raporlanır.

Araç: `backtest/fonlama.py` + `python -m backtest.calistir fonlama`.
Veri: 23 sembol, Binance USDT-M fonlama geçmişi, 2022-11 → 2026-11.

**Sonuç (100$ sermaye, 4 yıl):**

| Kural | Toplam | Yıllık | Max DD | 100$ → |
|---|---|---|---|---|
| Eşik %0.01 (yalnız yüksek fonlama) | +%10.8 | +%2.7 | %0.2 | 110.75$ |
| Al-tut, 5× | +%16.3 | +%3.9 | %1.8 | 116.28$ |
| Al-tut, 10× | +%17.9 | +%4.2 | %1.9 | 117.88$ |
| Al-tut, 20× | +%18.8 | +%4.4 | %2.0 | 118.81$ |

- 23 sembolün **tamamı** pozitif (medyan +%11.6); hiçbir yıl negatif değil.
- Ham fonlama medyanı yıllık **+%6.7** (4/23 sembolde negatif: BNB, TRX, ATOM, APT).
- Eşiksiz taşıma **maliyetle ölüyor**: 300-560 tur → −%57. Devir hızı kritik.
- Kaldıraç 5×'ten sonra neredeyse hiçbir şey eklemiyor; 20× likidasyon riskini
  bedava almış olursun. Önerilen: 3-5×.
- **$100'de yapısal sınır:** 23 sembol eşit ağırlık ≈ sembol başına 4.3$, minimum
  emir tutarının altında. Gerçekçi olarak 2-3 sembol (BTC/ETH/SOL) → yılda ~3$.

**Yorum:** Bu gerçek bir risk primi (perakende long tarafı fonlama ödüyor) ama
getirisi yılda %3-4. 100$ → 1000$ için buradan çıkacak para yılda ~3$; yani
10× hedefi bu yolla da ulaşılamaz. Yine de "parayı koru" hedefi için en sağlam
araç bu: DD %2, her yıl pozitif.

**Canlıya almanın bedeli:** mevcut bot yalnızca Gate vadeli işlem yapıyor;
taşıma **spot bacak** ister (hesap yapısı, teminat yönetimi, iki bacağın
eşzamanlı açılması, perp bacağında likidasyon koruması). Ayrı bir modül gerekir,
mevcut V6 sinyal motoruyla ilgisi yok.

## Karar — yeni sistem eklenmiyor (2026-11-20)

Üç yol ölçüldü, üçü de 10 ayda 10× hedefini karşılamıyor:

| Yol | Ölçüm | Sonuç |
|---|---|---|
| Mevcut V6 (1h sinyal) | 10 aylık motor, EV ≈ 0 | Kenar yok |
| Kesitsel momentum (4h, 23 sembol, 4 yıl) | faz medyanı +%20/4 yıl, DD %52 | Kenar yok |
| Fonlama taşıması (delta-nötr, 4 yıl) | yılda +%4, DD %2 | Kenar **var** ama küçük |

**Gerekçe:** 10 ayda 10× = ayda +%26. En sağlam bulunan yol yılda +%4. Aradaki
fark daha iyi bir indikatörle kapanmaz; 100$ sermayede yılda %20 getiren kusursuz
bir sistem bile yılda 20$ eder. Darboğaz strateji değil, sermaye.

**Bundan sonra yapılmayacaklar:** yeni indikatör/sinyal ailesi denemeleri, yeni
kaldıraç/kumar modları, fiyat deseni tabanlı yeni sistemler. İki araştırma aracı
(`backtest/kesitsel.py`, `backtest/fonlama.py`) belgelenmiş halde duruyor; veri
önbelleği `backtest/veri_uzun/` ve `backtest/fonlama/` altında (git dışı), yani
istenirse tek komutla tekrar koşulur.

**Dış varlık listesi de ölçüldü (26.11.2026):** "BTC/ETH/SOL/XRP/DOGE + Mag7"
sepeti, 5,5 yıl günlük veri, aylık dengeleme, tek yön 10 bps maliyet:

| Kural | Yıllık | Max DD | 100$ → |
|---|---|---|---|
| Al-tut (tek alım) | +%15.6 | %70 | 221$ |
| Al-tut (aylık denge) | +%23.0 | %62 | 311$ |
| Zaman momentum 12 ay | +%13.8 | %42 | 203$ |
| Kesitsel üst-3 (12 ay) | +%27.2 | %56 | 372$ |
| Kesitsel üst-3 (**6 ay**) | +%7.0 | %61 | 145$ |
| Kesitsel 3 uzun / 3 kısa | −%15.9 | %72 | 39$ |
| SPY (referans) | +%11.7 | %24 | 183$ |

Tek iyi satır (12 ay kesitsel) parametre adası: aynı fikrin 6 ay versiyonu
+%7/yıl. NVDA çıkarılınca +%27.2 → +%18.4. Kısa bacak yılda −%16. Kripto
tarafında 5,5 yılda ETH −%7.5/yıl, DOGE −%27.8/yıl, XRP +%1.6/yıl; yalnız BTC
(+%11.4) ve SOL (+%11.8) taşıdı. Sonuç: bu 12 varlıkta **tutmak, işlem yapmayı
yendi**; kenar yok.

**Açık kalan tek iş:** V6.3/V6.4 paper doğrulaması. 60 işleme ulaşınca kapı
`python -m backtest.kapi --state <dosya>` ile bir kez değerlendirilir
(≥60 işlem, ≥+5 bps, WR ≥ %57, DD ≤ %15); tutmazsa `BARAJ_GENISLETME = 1.0`'a
dönülür ve bot paper'da kalır.

## References

[1]: https://www.gate.com/help/futures/futures_logic/22079 "Futures Trading Fee Calculation | Gate"
[2]: https://www.gate.com/help/futures/futures-logic/27569/funding-rate-and-funding-fee "Contract Funding Rate and Funding Fee Explanation | Gate"
