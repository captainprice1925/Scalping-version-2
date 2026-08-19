import ccxt
import pandas as pd

# ccxt >= 4.4'te 'gateio' sınıfı 'gate' olarak yeniden adlandırıldı; iki sürümü de destekle
_gate_cls = getattr(ccxt, 'gate', None) or getattr(ccxt, 'gateio')
gateio = _gate_cls({'options': {'defaultType': 'swap'}, 'enableRateLimit': True})

def get_exchange():
    return gateio

def veri_cek(symbol, interval, limit=500, sadece_kapali=False):
    """sadece_kapali=True: devam eden (henüz kapanmamış) son mum atılır -
    sinyal hesapları yarımlanmış mumdan etkilenmesin."""
    try:
        if ":" not in symbol:
            if not symbol.endswith("USDT"):
                return pd.DataFrame()
            coin = symbol[:-4]
            gate_symbol = f"{coin}/USDT:USDT"
        else:
            gate_symbol = symbol
        ohlcv = gateio.fetch_ohlcv(symbol=gate_symbol, timeframe=interval, limit=min(limit, 1000))
        if not ohlcv:
            return pd.DataFrame()
        if sadece_kapali:
            ohlcv = ohlcv[:-1]
            if not ohlcv:
                return pd.DataFrame()
        df = pd.DataFrame(ohlcv, columns=['time', 'open', 'high', 'low', 'close', 'volume'])
        df['time'] = pd.to_datetime(df['time'], unit='ms')
        return df
    except Exception as e:
        print(f"❌ {symbol} {interval} hata: {e}")
        return pd.DataFrame()
