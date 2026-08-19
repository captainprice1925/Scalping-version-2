# FATIH V5 - Kademeli kâr + 1m pozisyon takibi + geniş RSI
COINS_CORE = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
COINS_MAX = 12
HACIM_MIN_USD = 5000000
SPREAD_MAX = 0.0008

TIMEFRAME_TREND = "4h"
TIMEFRAME_GIRIS = "1h"
POZISYON_TF = "1m"          # pozisyon SL/TP takibi bu zaman diliminden yapılır

ISLEM_BASINA = 10
BUTCE_SANAL = 100
KALDIRAC = 5
MAX_POZISYON = 2
MAX_AYNI_YON = 2

GUNLUK_KAYIP_LIMITI = 0.03
MAX_DRAWDOWN = 0.20

EMA_TREND = 200
EMA_GIRIS = 21
RSI_PERIOD = 14
RSI_LONG_MIN = 40
RSI_LONG_MAX = 65
RSI_SHORT_MIN = 35
RSI_SHORT_MAX = 60
VOLUME_MA = 20
VOLUME_MULT = 1.3
MIN_SKOR = 3

# SL 1.5 ATR (tek barlık gürültüye dayanır), TP 2.7 ATR => RR 1.8
SL_ATR = 1.5
TP_ATR = 2.7
BE_ATR = 1.2                # TP1 = kademeli satış 1 + SL'i girişe çekme
TP1_YUZDE = 40              # TP1'de satılan oran
TP2_YUZDE = 30              # TP2'de satılan oran (kalan TP3'te satılır)
ZAMAN_EXIT_SAAT = 24        # bu sürede SL/TP tetiklenmezse pozisyon piyasadan kapatılır

KOMISYON = 0.0008
SLIPPAGE = 0.0005
TARAMA_ARALIGI = 300        # 5 dakika
COOLDOWN_DAKIKA = 90
COOLDOWN_BE_DAKIKA = 45     # başabaş çıkış sonrası kısa cooldown

print("✅ Config V5 - kademeli TP 40/30/30 + SL 1.5 ATR + 5dk takip")
