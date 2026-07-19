import numpy as np
import pandas as pd
import config

def calc_mrc(df, length=config.MRC_LENGTH, tv_mode=True):
    """Linear Regression Channel hesaplar (±1.5 std-dev)"""
    df = df.copy()
    close = df['close'].values
    
    n = len(close)
    mrc_mid = np.full(n, np.nan)
    mrc_u2 = np.full(n, np.nan)
    mrc_l2 = np.full(n, np.nan)
    mrc_slope_pct = np.full(n, np.nan)
    
    ddof = 1 if tv_mode else 0
    
    for i in range(length - 1, n):
        window = close[i - length + 1 : i + 1]
        x = np.arange(length)
        y = window
        
        x_mean = x.mean()
        y_mean = y.mean()
        
        cov_xy = np.sum((x - x_mean) * (y - y_mean)) / length
        var_x = np.sum((x - x_mean) ** 2) / length
        
        slope = cov_xy / var_x
        intercept = y_mean - slope * x_mean
        
        mid = intercept + slope * (length - 1)
        
        y_pred = intercept + slope * x
        residuals = y - y_pred
        std = np.std(residuals, ddof=ddof)
        
        mrc_mid[i] = mid
        mrc_u2[i] = mid + 1.5 * std
        mrc_l2[i] = mid - 1.5 * std
        mrc_slope_pct[i] = slope / close[i]
    
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