import config
import pandas as pd

def calculate_score(df):
    """Skor hesapla (0-10 arası, TAM SAYI)"""
    row = df.iloc[-1]
    
    if row[['rsi', 'atr', 'stoch_k', 'adx', 'cci']].isna().any():
        return 0, None
    
    # LONG SKORU
    long_score = 0
    if row['rsi'] < 25: long_score += 2
    elif row['rsi'] < 35: long_score += 1
    
    if row['close'] < row['mrc_lower']: long_score += 2
    elif row['mrc_position'] < 0.2: long_score += 1
    
    if row['stoch_k'] < 20 and row['stoch_k'] > row['stoch_d']: long_score += 2
    elif row['stoch_k'] < 30: long_score += 1
    
    if row['cci'] < -100: long_score += 1
    if row['macd'] > row['macd_signal'] and row['macd_hist'] > 0: long_score += 1
    if row['volume_ratio'] > 1.5: long_score += 1
    if row['adx'] > 25 and row['di_diff'] > 0: long_score += 1
    if row['bb_position'] < 0.1: long_score += 1
    if row['bull_div'] == 1: long_score += 1
    if row['ema_9'] > row['ema_21'] > row['ema_50']: long_score += 1
    
    # SHORT SKORU
    short_score = 0
    if row['rsi'] > 75: short_score += 2
    elif row['rsi'] > 65: short_score += 1
    
    if row['close'] > row['mrc_upper']: short_score += 2
    elif row['mrc_position'] > 0.8: short_score += 1
    
    if row['stoch_k'] > 80 and row['stoch_k'] < row['stoch_d']: short_score += 2
    elif row['stoch_k'] > 70: short_score += 1
    
    if row['cci'] > 100: short_score += 1
    if row['macd'] < row['macd_signal'] and row['macd_hist'] < 0: short_score += 1
    if row['volume_ratio'] > 1.5: short_score += 1
    if row['adx'] > 25 and row['di_diff'] < 0: short_score += 1
    if row['bb_position'] > 0.9: short_score += 1
    if row['bear_div'] == 1: short_score += 1
    if row['ema_9'] < row['ema_21'] < row['ema_50']: short_score += 1
    
    # KARAR (MIN_SKOR = 7)
    if long_score >= config.MIN_SKOR and long_score > short_score:
        return long_score, "LONG"
    elif short_score >= config.MIN_SKOR and short_score > long_score:
        return short_score, "SHORT"
    else:
        return max(long_score, short_score), None


def sinyal_kontrol(df_15m, df_1h, btc_4h, symbol=None):
    """(yön, skor) tuple döndürür"""
    df = df_1h
    
    if df is None or df.empty or len(df) < 200:
        if symbol:
            print(f"⏳ {symbol} yetersiz veri")
        return None, 0
    
    skor, yon = calculate_score(df)
    
    coin_adi = symbol if symbol else "bilinmeyen"
    if yon:
        print(f"✅ {coin_adi} skoru: {skor}/10 - {yon}")
        return yon, skor
    else:
        print(f"⏳ {coin_adi} skoru: {skor}/10 (yetersiz)")
        return None, skor