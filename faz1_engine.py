import pandas as pd
import numpy as np

def calc_rsi(df, period=14):
    """RSI hesapla"""
    df = df.copy()
    delta = df['close'].diff()
    gain = delta.where(delta > 0, 0).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    df['rsi'] = 100 - (100 / (1 + rs))
    df['rsi_slope'] = df['rsi'].diff(5)
    return df

def calc_atr(df, period=14):
    """ATR hesapla"""
    df = df.copy()
    high_low = df['high'] - df['low']
    high_close = (df['high'] - df['close'].shift()).abs()
    low_close = (df['low'] - df['close'].shift()).abs()
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    df['atr'] = tr.rolling(period).mean()
    df['atr_pct'] = df['atr'] / df['close'] * 100
    return df

def calc_mrc(df, length=100):
    """MRC (Mean Reversion Channel) hesapla"""
    df = df.copy()
    df['mrc_mid'] = df['close'].ewm(span=length).mean()
    df['mrc_band'] = df['atr'] * 2.0
    df['mrc_upper'] = df['mrc_mid'] + df['mrc_band']
    df['mrc_lower'] = df['mrc_mid'] - df['mrc_band']
    df['mrc_position'] = (df['close'] - df['mrc_lower']) / (df['mrc_upper'] - df['mrc_lower'])
    return df

def calc_ema(df):
    """EMA'lar hesapla"""
    df = df.copy()
    for span in [9, 21, 50]:
        df[f'ema_{span}'] = df['close'].ewm(span=span).mean()
    df['ema_trend'] = (df['ema_9'] > df['ema_21']) & (df['ema_21'] > df['ema_50'])
    return df

def calc_bollinger(df, period=20):
    """Bollinger Bands hesapla"""
    df = df.copy()
    df['bb_mid'] = df['close'].rolling(period).mean()
    df['bb_std'] = df['close'].rolling(period).std()
    df['bb_upper'] = df['bb_mid'] + 2 * df['bb_std']
    df['bb_lower'] = df['bb_mid'] - 2 * df['bb_std']
    df['bb_position'] = (df['close'] - df['bb_lower']) / (df['bb_upper'] - df['bb_lower'])
    return df

def calc_macd(df):
    """MACD hesapla"""
    df = df.copy()
    df['ema_12'] = df['close'].ewm(span=12).mean()
    df['ema_26'] = df['close'].ewm(span=26).mean()
    df['macd'] = df['ema_12'] - df['ema_26']
    df['macd_signal'] = df['macd'].ewm(span=9).mean()
    df['macd_hist'] = df['macd'] - df['macd_signal']
    return df

def calc_stochastic(df, period=14):
    """Stochastic hesapla"""
    df = df.copy()
    low_14 = df['low'].rolling(period).min()
    high_14 = df['high'].rolling(period).max()
    df['stoch_k'] = 100 * (df['close'] - low_14) / (high_14 - low_14)
    df['stoch_d'] = df['stoch_k'].rolling(3).mean()
    return df

def calc_cci(df, period=20):
    """CCI hesapla"""
    df = df.copy()
    tp = (df['high'] + df['low'] + df['close']) / 3
    df['cci'] = (tp - tp.rolling(period).mean()) / (0.015 * tp.rolling(period).std())
    return df

def calc_adx(df, period=14):
    """ADX + DI hesapla"""
    df = df.copy()
    plus_dm = df['high'].diff()
    minus_dm = -df['low'].diff()
    plus_dm = plus_dm.where((plus_dm > minus_dm) & (plus_dm > 0), 0)
    minus_dm = minus_dm.where((minus_dm > plus_dm) & (minus_dm > 0), 0)
    
    df['plus_di'] = 100 * (plus_dm.rolling(period).mean() / df['atr'])
    df['minus_di'] = 100 * (minus_dm.rolling(period).mean() / df['atr'])
    df['di_diff'] = df['plus_di'] - df['minus_di']
    
    dx = 100 * ((df['plus_di'] - df['minus_di']).abs() / (df['plus_di'] + df['minus_di']))
    df['adx'] = dx.rolling(period).mean()
    return df

def calc_volume(df):
    """Volume indikatörleri hesapla"""
    df = df.copy()
    df['volume_ma20'] = df['volume'].rolling(20).mean()
    df['volume_ratio'] = df['volume'] / df['volume_ma20']
    return df

def calc_divergence(df):
    """Bullish/Bearish divergence hesapla"""
    df = df.copy()
    df['price_higher'] = (df['close'] > df['close'].shift(10)).astype(int)
    df['rsi_higher'] = (df['rsi'] > df['rsi'].shift(10)).astype(int)
    df['bull_div'] = ((df['price_higher'] == 0) & (df['rsi_higher'] == 1)).astype(int)
    df['bear_div'] = ((df['price_higher'] == 1) & (df['rsi_higher'] == 0)).astype(int)
    return df

def full_analysis(df):
    """Tüm indikatörleri hesapla (50+)"""
    df = calc_rsi(df)
    df = calc_atr(df)
    df = calc_mrc(df)
    df = calc_ema(df)
    df = calc_bollinger(df)
    df = calc_macd(df)
    df = calc_stochastic(df)
    df = calc_cci(df)
    df = calc_adx(df)
    df = calc_volume(df)
    df = calc_divergence(df)
    return df
