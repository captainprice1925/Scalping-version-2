# FATIH V6 - risk tabanlı boyutlandırma + kademeli kâr + 1m pozisyon takibi
COINS_CORE = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
COINS_MAX = 12
HACIM_MIN_USD = 5000000
SPREAD_MAX = 0.0008

TIMEFRAME_TREND = "4h"
TIMEFRAME_GIRIS = "1h"
POZISYON_TF = "1m"

# Paper hesap ve risk sınırları. Gerçek emir gönderen bir borsa adaptörü yoktur.
BUTCE_SANAL = 100
KALDIRAC = 10                         # İzole 10×; tahmini likidasyon girişe ~%10 mesafede
RISK_YUZDE_ISLEM = 0.01              # Kullanıcı tercihi: işlem başına sermayenin %1'i
MAX_TOPLAM_RISK_YUZDE = 0.02         # Aynı anda açık tüm işlemlerde en fazla %2 tahmini risk
# Marjin sınırları 10× kaldıraçta notional aralığını (~25–100 USDT) koruyacak şekilde ölçeklendi.
MIN_ISLEM_MARJINI = 2.5
# V6.1: Tavan bakiyeyle ölçeklenir — sabit $10, bakiye $500 olsa bile kazancı
# $10 marjine kilitliyordu. Sabit değer taban (küçük bakiyede eski davranış).
MAX_ISLEM_MARJINI = 10
MAX_ISLEM_MARJINI_ORAN = 0.10          # efektif bakiyenin %10'u
MAX_TOPLAM_MARJIN_YUZDE = 0.30        # Açık marjin toplamı sermayenin %30'unu geçmez
MAX_POZISYON = 2
# V6.1: Aynı yönde ikinci pozisyon yasak — logda tüm sinyaller aynı anda SHORT
# geliyordu; iki korele pozisyon tek harekette çift stop yiyor.
MAX_AYNI_YON = 1
LIKIDASYON_TAMPON_YUZDE = 0.005       # Tahmini likidasyon ile stop arasında en az %0,5 tampon

GUNLUK_KAYIP_LIMITI = 0.03
# V6.3.2 - Drawdown toparlanma modu. Eski kural %20'de kalıcı kilit yaratıyordu:
# açık pozisyon kalmayınca efektif bakiye toparlanamıyor, bot sonsuza kadar
# işlem açmıyordu (10 aylık backtest: Temmuz'dan sonra 4 ay hiç işlem yok).
# Yeni kural kademeli ve histerezisli:
#   DD < %15            -> normal (tam risk)
#   %15 - %20 arası     -> mevcut mod korunur (erken zıplamayı önler)
#   %20 - %30 arası     -> kurtarma: işlem riski yarıya iner
#   >= %30              -> durdu: yeni işlem yok, manuel müdahale gerekir
MAX_DRAWDOWN = 0.20          # kurtarma moduna giriş eşiği
DD_TOPARLANMA_ESIGI = 0.15   # tam boyuta dönüş eşiği
DD_SERT_DURDURMA = 0.30      # tam durdurma eşiği
DD_KURTARMA_RISK_ORANI = 0.5 # kurtarma modunda risk çarpanı

EMA_TREND = 200
EMA_GIRIS = 21
RSI_PERIOD = 14
RSI_LONG_MIN = 40
RSI_LONG_MAX = 65
RSI_SHORT_MIN = 35
RSI_SHORT_MAX = 60
VOLUME_MA = 20
VOLUME_MULT = 1.3
# V6.1: Hacim onayı zorunlu (MIN_SKOR 4). Log analizi: 3/4 skorlu, Vol < 1.3x
# olan "ucuz" sinyaller negatif EV'nin ana kaynağıydı.
MIN_SKOR = 4

# V6.2 - GİRİŞ REJİMİ FİLTRESİ (41 işlemlik state analizi; iki yarı-örneklemde
# de tutarlı sonuç):
#   ema_dist < 0.45   -> WR %40, EV -$0.34 ile en kötü bölge (EMA21'e çok yakın
#                        giriş, mean-reversion'a kurban gidiyor)
#   volume_ratio > 1.8 -> EV -$0.28 (hacim patlaması = climax, devam değil ters sinyal)
#   Birlikte: n=8, WR %88, EV +$0.446 (net, komisyon dahil)
MIN_EMA_DIST = 0.45    # minimum mutlak EMA21 mesafesi (%)
MAX_VOL_RATIO = 1.8    # hacim patlaması üst sınırı

# V6.3 - VOLATİLİTE BANDI (24 işlemlik V6.2 doğrulama verisi; her iki yarı-örneklemde
# de tutarlı, yön 41 işlemlik turda da aynıydı):
#   ATR > 1.3  -> n=9, WR %33, EV -$0.429 (giriş anında hareket zaten olmuş,
#                 geç kalınmış giriş → STOP)
#   ATR <= 1.3 -> n=15, WR %73, EV +$0.225 (kapı geçer: hedef +$0.15)
#   ATR <= 0.7 -> 41 işlemlik turda EV -$0.179 (hareket yok → TP'ye ulaşılamıyor)
#   Bant içindeki simülasyon: EV +$0.286, WR %75 (ilk yarı EV+0.40 / son yarı EV+0.20)
MIN_ATR_PCT = 0.7      # minimum 1h ATR% (durgun piyasa girişi yasak)
MAX_ATR_PCT = 1.3      # maksimum 1h ATR% (çalkantılı piyasa girişi yasak)

# V6.1: BTC 4h rejimi, BTC dışı coinlerin yönünü filtreler. Tüm piyasa aynı
# anda tek yöne sinyal verdiğinde korele kayıp riski düşer.
BTC_REGIME_FILTRE = True

# SL 1.5 ATR, TP 2.7 ATR, TP1 1.2 ATR
SL_ATR = 1.5
TP_ATR = 2.7
BE_ATR = 1.2
TP1_YUZDE = 40
TP2_YUZDE = 30
ZAMAN_EXIT_SAAT = 24

# Maliyet varsayımları. Gate hesabındaki güncel VIP maker/taker oranlarıyla değiştirilmeli.
# Varsayılan, piyasa emri (taker) için her iki yönde %0,05 komisyon ve %0,03 kayma tahminidir.
GIRIS_KOMISYON_ORANI = 0.0005
CIKIS_KOMISYON_ORANI = 0.0005
GIRIS_SLIPPAGE_ORANI = 0.0003
CIKIS_SLIPPAGE_ORANI = 0.0003
FONLAMA_AKTIF = True

TARAMA_ARALIGI = 300
# V6.1: STOP sonrası 90dk çok kısaydı — 1h sinyal hâlâ geçerliyken tekrar
# girip aynı chop'ta ikinci stop yeme döngüsü vardı.
COOLDOWN_DAKIKA = 240
COOLDOWN_BE_DAKIKA = 45

print("✅ Config V6.3 - %1 risk + hacim onaylı sinyal (4/4) + BTC rejim + giriş rejimi filtresi (ema/vol/atr bandı)")
