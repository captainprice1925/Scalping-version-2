# -*- coding: utf-8 -*-
"""Geçmiş OHLCV indirme ve önbellek.

Backtest verisi Binance USDT-M futures'tan (hızlı, sayfalama güvenilir) indirilir.
Canlı bot Gate perpetual'ında çalışır; fiyat serileri pratikte aynıdır. Gate
kaynağı da desteklenir (yavaş) ama varsayılan binance'dir.

Veri `backtest/veri/` altında gzip CSV olarak önbelleğe alınır.
Bu modül canlı bot tarafından import edilmez.
"""
import os
import time

import pandas as pd
import requests

KLASOR = os.path.join(os.path.dirname(__file__), "veri")
BINANCE_KLINES = "https://fapi.binance.com/fapi/v1/klines"


def indir_binance(symbol, timeframe="1h", gun=300):
    simdi = int(time.time() * 1000)
    since = simdi - gun * 86400 * 1000
    hepsi = []
    while since < simdi:
        try:
            yanit = requests.get(
                BINANCE_KLINES,
                params={
                    "symbol": symbol,
                    "interval": timeframe,
                    "startTime": since,
                    "limit": 1500,
                },
                timeout=20,
            )
            yanit.raise_for_status()
            veri = yanit.json()
        except Exception as hata:
            print(f"⚠️ {symbol} {timeframe} indirme hatası: {hata}")
            break
        if not veri:
            break
        hepsi.extend(veri)
        son = veri[-1][0]
        if son <= since:
            break
        since = son + 1
        if len(veri) < 1500:
            break

    if not hepsi:
        return pd.DataFrame()
    df = pd.DataFrame(
        [satir[:6] for satir in hepsi],
        columns=["time", "open", "high", "low", "close", "volume"],
    )
    df["time"] = pd.to_datetime(df["time"], unit="ms")
    return df.drop_duplicates("time").sort_values("time").reset_index(drop=True)


def indir(symbol, timeframe="1h", gun=300, zorla=False, kaynak="binance"):
    """Sembolün son `gun` gününü indirir; önbellek varsa onu döndürür."""
    os.makedirs(KLASOR, exist_ok=True)
    yol = os.path.join(KLASOR, f"{symbol}_{timeframe}.csv.gz")
    if os.path.exists(yol) and not zorla:
        df = pd.read_csv(yol, parse_dates=["time"])
        # Önbellek istenen pencereyi kapsıyorsa tekrar indirme.
        if not df.empty:
            kapsam = (pd.Timestamp.now() - df["time"].min()).total_seconds() / 86400
            if kapsam >= gun - 2:
                return df

    if kaynak == "gate":
        df = _indir_gate(symbol, timeframe, gun)
    else:
        df = indir_binance(symbol, timeframe, gun)

    if df.empty:
        return df
    df = df[df["time"] <= pd.Timestamp.now()].reset_index(drop=True)
    df.to_csv(yol, index=False, compression="gzip")
    return df


def _indir_gate(symbol, timeframe, gun):
    import ccxt

    sinif = getattr(ccxt, "gate", None) or getattr(ccxt, "gateio")
    ex = sinif(
        {"options": {"defaultType": "swap"}, "enableRateLimit": True, "timeout": 20000}
    )
    simdi = int(time.time() * 1000)
    since = simdi - gun * 86400 * 1000
    hepsi = []
    while since < simdi:
        try:
            ohlcv = ex.fetch_ohlcv(
                f"{symbol[:-4]}/USDT:USDT", timeframe, since=since, limit=1000
            )
        except Exception as hata:
            print(f"⚠️ {symbol} {timeframe} gate hatası: {hata}")
            break
        if not ohlcv:
            break
        hepsi.extend(ohlcv)
        son = ohlcv[-1][0]
        if son <= since:
            break
        since = son + 1
    if not hepsi:
        return pd.DataFrame()
    df = pd.DataFrame(hepsi, columns=["time", "open", "high", "low", "close", "volume"])
    df["time"] = pd.to_datetime(df["time"], unit="ms")
    return df.drop_duplicates("time").sort_values("time").reset_index(drop=True)


def dort_saatlik(df_1h):
    """1h verisinden UTC hizalı 4h mumlar üretir."""
    if df_1h.empty:
        return df_1h.copy()
    df = (
        df_1h.set_index("time")
        .resample("4h", origin="epoch")
        .agg(
            {
                "open": "first",
                "high": "max",
                "low": "min",
                "close": "last",
                "volume": "sum",
            }
        )
        .dropna()
        .reset_index()
    )
    return df
