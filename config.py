# ═══════════════════════════════════════════════════
# SCALP BOT AYARLARI
# ═══════════════════════════════════════════════════

# Coin listesi (Top 20 likit coin)
COINS = [
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT",
    "DOGEUSDT", "ADAUSDT", "AVAXUSDT", "DOTUSDT", "LINKUSDT",
    "POLUSDT", "LTCUSDT", "BCHUSDT", "ATOMUSDT", "UNIUSDT",
    "NEARUSDT", "APTUSDT", "FILUSDT", "ARBUSDT", "OPUSDT"
]

# Timeframe'ler
TIMEFRAME_MAIN = "15m"      # Ana sinyal
TIMEFRAME_MTF = "1h"        # Onay
TIMEFRAME_VETO = "4h"       # Veto (BTC 4H)

# İndikatör parametreleri
MRC_LENGTH = 100
ATR_PERIOD = 14
RSI_PERIOD = 14

# Risk yönetimi
BUTCE_SANAL = 100           # $100 toplam sanal bakiye
ISLEM_BASINA = 10           # $10/işlem (max)
KALDIRAC = 10               # 10x
MAX_POZISYON = 10           # Max 10 açık işlem (toplam)
MAX_AYNI_YON = 5            # Aynı yönde (LONG veya SHORT) max pozisyon

# Adaptive Position Sizing - Bakiye azaldıkça işlem küçülür
POZISYON_ORANI = 0.10       # Bakiyenin max %10'u tek işlemde
MIN_ISLEM_TUTAR = 2         # Minimum $2 (daha küçük işlem anlamsız)

# Günlük kayıp limiti
GUNLUK_KAYIP_LIMITI = 0.05  # %5 - günlük bu oranda kayıpta yeni işlem açılmaz

# Max Drawdown - Peak bakiyeden %15 düşerse her şey durur
MAX_DRAWDOWN = 0.15         # %15 - tüm zamanların en yüksek bakiyesinden düşüş

# SL/TP (ATR bazlı + %3 cap)
ATR_CARPI = 2.0             # 🆕 1.5 → 2.0 (daha geniş SL)
MAX_SL_YUZDE = 0.03         # 🆕 %2 → %3 max (daha geniş SL)
TP1_CARPI = 1.5             # 1.5R
TP2_CARPI = 3.0             # 3.0R
TP3_CARPI = 4.5             # 4.5R

# Filtre eşikleri
SLOPE_ESIK = 0.001          # ±0.1% trend
VETO_ESIK = 0.005           # ±0.5% veto (4H) - gevşetildi

# Trailing Stop (40/30/30)
TP1_KAPANMA = 40            # %40 kapat
TP2_KAPANMA = 30            # %30 kapat
TP3_KAPANMA = 30            # %30 kapat

# Onay sayısı
ONAY_SAYISI = 2             # 2/3 (CMF elendi)

# RR minimum
MIN_RR = 3.0                # TP3 RR >= 3.0

# Komisyon
KOMISYON = 0.0008           # %0.08 (açılış + kapanış)

# Slippage simülasyonu (gerçekçi test için)
SLIPPAGE = 0.0005           # %0.05 fiyat kayması (her işlemde aleyhimize)

# Tarama aralığı (saniye)
TARAMA_ARALIGI = 60         # 1 dakikada bir tara

print("✅ Config yüklendi")