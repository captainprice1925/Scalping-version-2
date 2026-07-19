import numpy as np
import pandas as pd
from scipy.signal import argrelextrema
import config

def find_divergence(df, lookback=10, max_bar_oncesi=30):
    """
    RSI divergence tespiti (2/3 onay - CMF elendi)
    max_bar_oncesi: Son dip/tepe en fazla bu kadar bar önce oluşmuş olmalı
    Returns: "LONG", "SHORT", veya None
    """
    if len(df) < lookback * 2:
        return None
    
    close = df['close'].values
    rsi = df['rsi'].values
    
    mask = ~np.isnan(rsi)
    close = close[mask]
    rsi = rsi[mask]
    
    if len(close) < lookback * 2:
        return None
    
    dipler = argrelextrema(close, np.less, order=lookback//2)[0]
    tepeler = argrelextrema(close, np.greater, order=lookback//2)[0]
    
    son_bar_index = len(close) - 1
    
    # BULLISH DIVERGENCE (LONG)
    if len(dipler) >= 2:
        onceki, son = dipler[-2], dipler[-1]
        
        # Tazelik kontrolü: son dip en fazla max_bar_oncesi önce olmalı
        bar_farki = son_bar_index - son
        if bar_farki <= max_bar_oncesi:
            if close[son] < close[onceki] and rsi[son] > rsi[onceki]:
                if df['close'].iloc[-1] < df['mrc_l2'].iloc[-1]:
                    return "LONG"
        else:
            print(f"   ⏰ LONG divergence çok eski ({bar_farki} bar önce)")
    
    # BEARISH DIVERGENCE (SHORT)
    if len(tepeler) >= 2:
        onceki, son = tepeler[-2], tepeler[-1]
        
        # Tazelik kontrolü: son tepe en fazla max_bar_oncesi önce olmalı
        bar_farki = son_bar_index - son
        if bar_farki <= max_bar_oncesi:
            if close[son] > close[onceki] and rsi[son] < rsi[onceki]:
                if df['close'].iloc[-1] > df['mrc_u2'].iloc[-1]:
                    return "SHORT"
        else:
            print(f"   ⏰ SHORT divergence çok eski ({bar_farki} bar önce)")
    
    return None

def btc_dominance_filter(btc_4h_df):
    """BTC 4H trend filtresi (veto)"""
    if btc_4h_df.empty or 'mrc_slope_pct' not in btc_4h_df.columns:
        return "NEUTRAL"
    
    slope = btc_4h_df['mrc_slope_pct'].iloc[-1]
    
    if pd.isna(slope):
        return "NEUTRAL"
    
    if slope > config.VETO_ESIK:
        return "LONG_ONLY"
    elif slope < -config.VETO_ESIK:
        return "SHORT_ONLY"
    else:
        return "NEUTRAL"

def sinyal_kontrol(df_15m, df_1h, btc_4h_df):
    """Tam sinyal kontrolü (2/3 onay + MTF)"""
    btc_filter = btc_dominance_filter(btc_4h_df)
    coin_1h_slope = df_1h['mrc_slope_pct'].iloc[-1]
    sinyal = find_divergence(df_15m)
    
    if sinyal is None:
        return None
    
    if sinyal == "LONG":
        if btc_filter == "SHORT_ONLY":
            return None
        if coin_1h_slope < -config.SLOPE_ESIK:
            return None
        return "LONG"
    
    elif sinyal == "SHORT":
        if btc_filter == "LONG_ONLY":
            return None
        if coin_1h_slope > config.SLOPE_ESIK:
            return None
        return "SHORT"
    
    return None