import numpy as np
import pandas as pd
import config

def calc_mrc(df, length=config.MRC_LENGTH, tv_mode=True):
    """
    Mean Reversion Channel (Gerçek MRC)
    - Orta çizgi: EMA(length) 
    - Üst/alt bant: EMA ± ATR * 2.0 (volatilite uyumlu)
    - Slope: EMA'nın son 5 bar'daki değişim oranı
    """
    df = df.copy()
    close = df['close'].values
    high = df['high'].values
    low = df['low'].values
    
    n = len(close)
    mrc_mid = np.full(n, np.nan)
    mrc_u2 = np.full(n, np.nan)
    mrc_l2 = np.full(n, np.nan)
    mrc_slope_pct = np.full(n, np.nan)
    
    # 1. EMA hesapla (orta çizgi - ortalama)
    ema = pd.Series(close).ewm(span=length, adjust=False).mean().values
    
    # 2. ATR hesapla (bant genişliği için - volatilite)
    tr1 = pd.Series(high) - pd.Series(low)
    tr2 = (pd.Series(high) - pd.Series(close).shift(1)).abs()
    tr3 = (pd.Series(low) - pd.Series(close).shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1/config.ATR_PERIOD, adjust=False).mean().values
    
    # 3. MRC bantlarını hesapla
    for i in range(length, n):
        mrc_mid[i] = ema[i]
        mrc_u2[i] = ema[i] + (atr[i] * 2.0)  # Üst bant: EMA + 2*ATR
        mrc_l2[i] = ema[i] - (atr[i] * 2.0)  # Alt bant: EMA - 2*ATR
        
        # Slope: Son 5 bar'daki EMA değişim oranı (%)
        if i >= 5:
            slope_change = (ema[i] - ema[i-5]) / ema[i-5]
            mrc_slope_pct[i] = slope_change
        else:
            mrc_slope_pct[i] = 0.0
    
    df['mrc_mid'] = mrc_mid
    df['mrc_u2'] = mrc_u2
    df['mrc_l2'] = mrc_l2
    df['mrc_slope_pct'] = mrc_slope_pct
    
    return df

def calc_atr(df, period=config.ATR_PERIOD):
    """Average True Range - Wilder's Smoothed MA"""
    df = df.copy()
    
    high = df['high']
    low = df['low']
    close = df['close']
    
    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    
    atr = tr.ewm(alpha=1/period, adjust=False).mean()
    df['atr'] = atr
    
    return df

def calc_rsi(df, period=config.RSI_PERIOD):
    """RSI hesaplar (Wilder's Smoothing - TradingView standardı)"""
    df = df.copy()
    delta = df['close'].diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    avg_gain = gain.ewm(alpha=1/period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/period, adjust=False).mean()
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    df['rsi'] = rsi
    return df

def full_analysis(df):
    """Tüm indikatörleri uygular"""
    df = calc_mrc(df)
    df = calc_atr(df)
    df = calc_rsi(df)
    return df