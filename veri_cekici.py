import ccxt
import pandas as pd

gateio = ccxt.gateio({'options': {'defaultType': 'swap'}})

def get_exchange():
    return gateio

def veri_cek(symbol, interval, limit=500):
    try:
        if ":" not in symbol:
            coin = symbol.replace("USDT", "")
            gate_symbol = f"{coin}/USDT:USDT"
        else:
            gate_symbol = symbol
        ohlcv = gateio.fetch_ohlcv(symbol=gate_symbol, timeframe=interval, limit=min(limit, 1000))
        if not ohlcv:
            return pd.DataFrame()
        df = pd.DataFrame(ohlcv, columns=['time', 'open', 'high', 'low', 'close', 'volume'])
        df['time'] = pd.to_datetime(df['time'], unit='ms')
        return df
    except Exception as e:
        print(f"❌ {symbol} {interval} hata: {e}")
        return pd.DataFrame()