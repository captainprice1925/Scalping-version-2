import config

def calculate_score(df):
    """
    Skor hesapla (0-10 arası)
    Backtest'te kanıtlanmış sistem
    """
    row = df.iloc[-1]
    
    # NaN kontrolü
    if row[['rsi', 'atr', 'stoch_k', 'adx', 'cci']].isna().any():
        return 0, None
    
    # LONG SKORU
    long_score = 0
    
    # RSI (max 2 puan)
    if row['rsi'] < 25:
        long_score += 2
    elif row['rsi'] < 35:
        long_score += 1
    
    # MRC (max 2 puan)
    if row['close'] < row['mrc_lower']:
        long_score += 2
    elif row['mrc_position'] < 0.2:
        long_score += 1
    
    # Stochastic (max 2 puan)
    if row['stoch_k'] < 20 and row['stoch_k'] > row['stoch_d']:
        long_score += 2
    elif row['stoch_k'] < 30:
        long_score += 1
    
    # CCI (max 1 puan)
    if row['cci'] < -100:
        long_score += 1
    
    # MACD (max 1 puan)
    if row['macd'] > row['macd_signal'] and row['macd_hist'] > 0:
        long_score += 1
    
    # Volume (max 1 puan)
    if row['volume_ratio'] > 1.5:
        long_score += 1
    
    # ADX trend gücü (max 1 puan)
    if row['adx'] > 25 and row['di_diff'] > 0:
        long_score += 1
    
    # Bollinger (max 1 puan)
    if row['bb_position'] < 0.1:
        long_score += 1
    
    # Bullish divergence (max 1 puan)
    if row['bull_div'] == 1:
        long_score += 1
    
    # EMA trend (max 1 puan)
    if row['ema_9'] > row['ema_21'] > row['ema_50']:
        long_score += 1
    
    # SHORT SKORU
    short_score = 0
    
    # RSI (max 2 puan)
    if row['rsi'] > 75:
        short_score += 2
    elif row['rsi'] > 65:
        short_score += 1
    
    # MRC (max 2 puan)
    if row['close'] > row['mrc_upper']:
        short_score += 2
    elif row['mrc_position'] > 0.8:
        short_score += 1
    
    # Stochastic (max 2 puan)
    if row['stoch_k'] > 80 and row['stoch_k'] < row['stoch_d']:
        short_score += 2
    elif row['stoch_k'] > 70:
        short_score += 1
    
    # CCI (max 1 puan)
    if row['cci'] > 100:
        short_score += 1
    
    # MACD (max 1 puan)
    if row['macd'] < row['macd_signal'] and row['macd_hist'] < 0:
        short_score += 1
    
    # Volume (max 1 puan)
    if row['volume_ratio'] > 1.5:
        short_score += 1
    
    # ADX trend gücü (max 1 puan)
    if row['adx'] > 25 and row['di_diff'] < 0:
        short_score += 1
    
    # Bollinger (max 1 puan)
    if row['bb_position'] > 0.9:
        short_score += 1
    
    # Bearish divergence (max 1 puan)
    if row['bear_div'] == 1:
        short_score += 1
    
    # EMA trend (max 1 puan)
    if row['ema_9'] < row['ema_21'] < row['ema_50']:
        short_score += 1
    
    # KARAR
    if long_score >= config.MIN_SKOR and long_score > short_score:
        return long_score, "LONG"
    elif short_score >= config.MIN_SKOR and short_score > long_score:
        return short_score, "SHORT"
    else:
        return max(long_score, short_score), None
