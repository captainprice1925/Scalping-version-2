import config
import pandas as pd

def calculate_score(df):
    """SADELEŞTİ - 5 üzerinden 4 baraj (eski 10 üzerinden 7'ydi)"""
    if df is None or len(df) < 60:
        return 0, None
        
    row = df.iloc[-1]
    
    # Gerekli kolonlar yoksa bekle
    if pd.isna(row.get('rsi')) or pd.isna(row.get('mrc_position')) or pd.isna(row.get('ema_21')):
        return 0, None

    long_score = 0
    short_score = 0

    # 1- RSI (2 puan)
    if row['rsi'] < 40:
        long_score += 2
    if row['rsi'] > 60:
        short_score += 2

    # 2- MRC Position (2 puan)
    if row['mrc_position'] < 0.35:
        long_score += 2
    if row['mrc_position'] > 0.65:
        short_score += 2

    # 3- EMA 21 (1 puan)
    if row['close'] > row['ema_21']:
        long_score += 1
    else:
        short_score += 1

    # KARAR - 5 üzerinden 4
    if long_score >= config.MIN_SKOR and long_score > short_score:
        return long_score, "LONG"
    elif short_score >= config.MIN_SKOR and short_score > long_score:
        return short_score, "SHORT"
    else:
        return max(long_score, short_score), None

def sinyal_kontrol(df_15m, df_1h, btc_4h, symbol=None):
    """OR MANTIĞI - 1h VEYA 4h biri yetiyor (eski kod sadece 1h'ye bakıyordu)"""
    coin_adi = symbol if symbol else "bilinmeyen"
    
    # 15m, 1h, 4h skorlarını ayrı ayrı al
    skor_15m, yon_15m = (0, None)
    skor_1h, yon_1h = (0, None)
    skor_4h, yon_4h = (0, None)

    if df_15m is not None and len(df_15m) >= 60:
        skor_15m, yon_15m = calculate_score(df_15m)
    if df_1h is not None and len(df_1h) >= 60:
        skor_1h, yon_1h = calculate_score(df_1h)
    if btc_4h is not None and len(btc_4h) >= 60:
        skor_4h, yon_4h = calculate_score(btc_4h)

    # HAFTA SONU: 15m ana
    # HAFTA İÇİ: 1h OR 4h
    # OR mantığı: herhangi biri sinyal verirse al
    final_yon = None
    final_skor = 0

    # LONG kontrolü
    if yon_15m == "LONG" or yon_1h == "LONG" or yon_4h == "LONG":
        final_yon = "LONG"
        final_skor = max(skor_15m if yon_15m=="LONG" else 0, 
                         skor_1h if yon_1h=="LONG" else 0, 
                         skor_4h if yon_4h=="LONG" else 0)
        print(f"✅ {coin_adi} OR SİNYAL: {final_skor}/5 - {final_yon} (15m:{yon_15m} 1h:{yon_1h} 4h:{yon_4h})")
        return final_yon, final_skor

    # SHORT kontrolü
    if yon_15m == "SHORT" or yon_1h == "SHORT" or yon_4h == "SHORT":
        final_yon = "SHORT"
        final_skor = max(skor_15m if yon_15m=="SHORT" else 0, 
                         skor_1h if yon_1h=="SHORT" else 0, 
                         skor_4h if yon_4h=="SHORT" else 0)
        print(f"✅ {coin_adi} OR SİNYAL: {final_skor}/5 - {final_yon} (15m:{yon_15m} 1h:{yon_1h} 4h:{yon_4h})")
        return final_yon, final_skor

    # Sinyal yok
    max_skor = max(skor_15m, skor_1h, skor_4h)
    print(f"⏳ {coin_adi} skoru: {max_skor}/5 (yetersiz) - 15m:{skor_15m} 1h:{skor_1h} 4h:{skor_4h}")
    return None, max_skor
