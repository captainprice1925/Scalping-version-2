import ccxt
import pandas as pd

# ccxt >= 4.4'te 'gateio' sınıfı 'gate' olarak yeniden adlandırıldı.
_gate_cls = getattr(ccxt, "gate", None) or getattr(ccxt, "gateio")
gateio = _gate_cls(
    {
        "options": {"defaultType": "swap"},
        "enableRateLimit": True,
        "timeout": 10000,
    }
)


def get_exchange():
    return gateio


def _gate_symbol(symbol):
    if ":" in symbol:
        return symbol
    if not symbol.endswith("USDT"):
        raise ValueError(f"Geçersiz USDT sembolü: {symbol}")
    return f"{symbol[:-4]}/USDT:USDT"


def veri_cek(symbol, interval, limit=500, sadece_kapali=False):
    """OHLCV verisini çeker; sadece_kapali son oluşmakta olan mumu çıkarır."""
    try:
        ohlcv = gateio.fetch_ohlcv(
            symbol=_gate_symbol(symbol), timeframe=interval, limit=min(limit, 1000)
        )
        if not ohlcv:
            return pd.DataFrame()
        if sadece_kapali:
            ohlcv = ohlcv[:-1]
            if not ohlcv:
                return pd.DataFrame()
        df = pd.DataFrame(
            ohlcv, columns=["time", "open", "high", "low", "close", "volume"]
        )
        df["time"] = pd.to_datetime(df["time"], unit="ms")
        return df
    except (ccxt.BaseError, ValueError) as error:
        print(f"❌ {symbol} {interval} veri hatası: {error}")
        return pd.DataFrame()


def fonlama_gecmisi_cek(symbol, limit=100):
    """Gate USDT perpetual fonlama geçmişini zaman damgası ve oran ile döndürür.

    İstek başarısız olursa işlem motoru fonlama tahakkuk ettirmeden çalışmaya devam eder;
    çağrı hatası görünür biçimde loglanır. Bu fonksiyon emir veya hesap değişikliği yapmaz.
    """
    try:
        history = gateio.fetch_funding_rate_history(
            _gate_symbol(symbol), limit=min(limit, 100)
        )
        return [
            {
                "timestamp": item.get("timestamp"),
                "rate": item.get("fundingRate"),
            }
            for item in history
            if item.get("timestamp") is not None and item.get("fundingRate") is not None
        ]
    except (ccxt.BaseError, ValueError) as error:
        print(f"⚠️ {symbol} fonlama verisi alınamadı: {error}")
        return []
