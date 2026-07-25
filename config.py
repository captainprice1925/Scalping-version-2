# ═══════════════════════════════════════════════════
# SCALP BOT AYARLARI (PROFESYONEL SEVİYE)
# ═══════════════════════════════════════════════════

# Coin listesi (Top 20 likit coin)
COINS = [
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT",
    "DOGEUSDT", "ADAUSDT", "AVAXUSDT", "DOTUSDT", "LINKUSDT",
    "POLUSDT", "LTCUSDT", "BCHUSDT", "ATOMUSDT", "UNIUSDT",
    "NEARUSDT", "APTUSDT", "FILUSDT", "ARBUSDT", "OPUSDT"
]

# Timeframe'ler
TIMEFRAME_MAIN = "1h"       # Ana sinyal (1H - daha güvenilir)
TIMEFRAME_MTF = "4h"        # Onay
TIMEFRAME_VETO = "1d"       # Veto (BTC Daily)

# Risk Yönetimi (PROFESYONEL)
BUTCE_SANAL = 100           # $100 başlangıç
POZISYON_ORANI = 0.01       # 🆕 Bakiyenin %1'i (güvenli)
KALDIRAC = 10               # 10x
MAX_POZISYON = 5            # Max 5 açık pozisyon (risk azaltma)
MAX_AYNI_YON = 3            # Aynı yönde max 3 pozisyon

# Risk Limitleri (KRİTİK)
GUNLUK_KAYIP_LIMITI = 0.03  # 🆕 Günlük %3 kayıpta dur
MAX_DRAWDOWN = 0.20         # 🆕 %20 drawdown'da dur
DRAWDOWN_REDUCE = 0.15      # 🆕 %15 drawdown'da pozisyon yarıya düş

# Minimum işlem tutarı
MIN_ISLEM_TUTAR = 2         # Minimum $2

# İndikatör parametreleri
MRC_LENGTH = 100
ATR_PERIOD = 14
RSI_PERIOD = 14

# Skor Sistemi
MIN_SKOR = 7                # Minimum skor (0-10 arası)

# SL/TP (ATR bazlı)
ATR_CARPI_SL = 1.5          # SL = ATR * 1.5
TP1_CARPI = 2.0             # TP1 = ATR * 2.0
TP2_CARPI = 4.0             # TP2 = ATR * 4.0
TP3_CARPI = 6.0             # TP3 = ATR * 6.0

# Trailing Stop (40/30/30)
TP1_KAPANMA = 40            # %40 kapat
TP2_KAPANMA = 30            # %30 kapat
TP3_KAPANMA = 30            # %30 kapat

# Komisyon
KOMISYON = 0.0008           # %0.08 (açılış + kapanış)

# Slippage simülasyonu
SLIPPAGE = 0.0005           # %0.05 fiyat kayması

# Tarama aralığı (saniye)
TARAMA_ARALIGI = 60         # 1 dakikada bir tara

# Cooldown
COOLDOWN_DAKIKA = 60        # 1 saat cooldown

print("✅ Config yüklendi (Profesyonel Risk Yönetimi Aktif)")
