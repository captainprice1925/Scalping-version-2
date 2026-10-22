import ccxt
import pandas as pd

import telegram_komut

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
        telegram_komut.hata_ekle(f"{symbol} {interval} veri", error)
        return pd.DataFrame()


def spread_orani(ob):
    """Order book'un ilk seviye spread'ini oran olarak döndürür.

    None: book eksik/geçersiz. Örnek: 0.0005 → %0.05 spread.
    """
    if not ob or not ob.get("bids") or not ob.get("asks"):
        return None
    bid = ob["bids"][0][0]
    ask = ob["asks"][0][0]
    if ask <= 0:
        return None
    return (ask - bid) / ask


def spread_kontrol(symbol):
    """Giriş anındaki spread'i ölçer.

    Liste hazırlığındaki spread kontrolü 6 saatte bir çalışıyordu; sinyal anında
    (volatilite tam da yükselirken) spread açılabilir. Giriş bu yüzden anlık
    olarak doğrulanır. Veri okunamazsa None döner ve giriş emniyet için atlanır.
    """
    try:
        ob = gateio.fetch_order_book(_gate_symbol(symbol), 5)
        return spread_orani(ob)
    except (ccxt.BaseError, ValueError) as error:
        print(f"⚠️ {symbol} spread verisi alınamadı: {error}")
        telegram_komut.hata_ekle(f"{symbol} spread", error)
        return None


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
        telegram_komut.hata_ekle(f"{symbol} fonlama", error)
        return []
