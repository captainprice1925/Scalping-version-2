import pandas as pd
import numpy as np
import ccxt

def get_exchange():
    return ccxt.gateio({'options': {'defaultType': 'swap'}})

def calc_rsi(df, period=14):
    delta = df['close'].diff()
    gain = delta.where(delta>0,0).ewm(alpha=1/period).mean()
    loss = (-delta.where(delta<0,0)).ewm(alpha=1/period).mean()
    rs = gain / loss.replace(0, np.nan)
    df['rsi'] = 100 - (100 / (1 + rs))
    return df

def calc_atr(df, period=14):
    high_low = df['high'] - df['low']
    high_close = (df['high'] - df['close'].shift()).abs()
    low_close = (df['low'] - df['close'].shift()).abs()
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    df['atr'] = tr.ewm(span=period).mean()
    df['atr_pct'] = df['atr'] / df['close'] * 100
    return df

def calc_ema(df):
    df['ema_21'] = df['close'].ewm(span=21).mean()
    df['ema_200'] = df['close'].ewm(span=200).mean()
    return df

def calc_volume(df):
    df['volume_ma20'] = df['volume'].rolling(20).mean()
    df['volume_ratio'] = df['volume'] / df['volume_ma20']
    return df

def full_analysis(df):
    if df is None or len(df) < 210:
        return df
    df = calc_rsi(df)
    df = calc_atr(df)
    df = calc_ema(df)
    df = calc_volume(df)
    return df

def get_dinamik_coins(exchange):
    try:
        tickers = exchange.fetch_tickers()
        adaylar = []
        for sym, t in tickers.items():
            if ":USDT" not in sym: continue
            if "USDT" not in sym: continue
            qv = t.get('quoteVolume')
            if not qv or qv < 5000000: continue
            bid = t.get('bid'); ask = t.get('ask')
            if bid and ask:
                spread = (ask-bid)/ask
                if spread > 0.0008: continue
            # USDT formatini senin sisteme çevir: BTC/USDT:USDT -> BTCUSDT
            clean = sym.split('/')[0] + "USDT"
            adaylar.append((clean, qv))
        adaylar.sort(key=lambda x: x[1], reverse=True)
        return [x[0] for x in adaylar[:15]]
    except Exception as e:
        print(f"⚠️ Dinamik hata: {e}")
        return []