import pandas as pd
import numpy as np

def calc_rsi(df, period=14):
    df = df.copy()
    delta = df['close'].diff()
    gain = delta.where(delta > 0, 0).ewm(alpha=1/period).mean()
    loss = (-delta.where(delta < 0, 0)).ewm(alpha=1/period).mean()
    rs = gain / loss.replace(0, np.nan)
    df['rsi'] = 100 - (100 / (1 + rs))
    return df

def calc_atr(df, period=14):
    df = df.copy()
    high_low = df['high'] - df['low']
    high_close = (df['high'] - df['close'].shift()).abs()
    low_close = (df['low'] - df['close'].shift()).abs()
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    df['atr'] = tr.ewm(span=period).mean()
    return df

def calc_mrc(df, length=100):
    df = df.copy()
    df['mrc_mid'] = df['close'].ewm(span=length).mean()
    df['mrc_band'] = df['atr'] * 2.0
    df['mrc_upper'] = df['mrc_mid'] + df['mrc_band']
    df['mrc_lower'] = df['mrc_mid'] - df['mrc_band']
    df['mrc_upper'] = df['mrc_upper'].fillna(df['close'])
    df['mrc_lower'] = df['mrc_lower'].fillna(df['close'])
    df['mrc_position'] = (df['close'] - df['mrc_lower']) / (df['mrc_upper'] - df['mrc_lower']).replace(0, np.nan)
    df['mrc_position'] = df['mrc_position'].fillna(0.5)
    return df

def calc_ema(df):
    df = df.copy()
    df['ema_21'] = df['close'].ewm(span=21).mean()
    df['ema_50'] = df['close'].ewm(span=50).mean()
    return df

def full_analysis(df):
    """SADELEŞTİRİLDİ - Sadece 3 indikatör"""
    if df is None or len(df) < 120:
        return df
    df = calc_rsi(df)
    df = calc_atr(df)
    df = calc_mrc(df, length=100)
    df = calc_ema(df)
    return df
