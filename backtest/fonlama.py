# -*- coding: utf-8 -*-
"""Fonlama (funding) taşıması — yön tahmini gerektirmeyen tek kripto primi.

Pozisyon: **delta-nötr**. Spot'ta al, vadeli (perp) piyasada aynı notionalda
short. Fiyat nereye giderse gitsin iki bacak birbirini götürür; kazanç yalnızca
fonlama ödemesinden gelir. Pozitif fonlamada short tarafı ödeme **alır**.

Sermaye kullanımı: spot bacak tam notional ister, perp bacak `kaldirac` ile
teminat ister. Yani `sermaye = notional * (1 + 1/kaldirac)`; getiri sermayeye
göre raporlanır.

Maliyet: girişte ve çıkışta iki bacak da işlem görür →
`2 * (komisyon + kayma)` notional başına, tur başına.

Veri: Binance USDT-M vadeli fonlama geçmişi (`/fapi/v1/fundingRate`).
Canlı bot bu modülü import etmez; araştırma aracıdır.
"""
import os
import time

import numpy as np
import pandas as pd
import requests

BINANCE_FONLAMA = "https://fapi.binance.com/fapi/v1/fundingRate"
KLASOR = os.path.join(os.path.dirname(__file__), "fonlama")


def indir_fonlama(symbol, gun=1460, zorla=False):
    """Sembolün fonlama geçmişini indirir; `backtest/fonlama/` altında önbellekler."""
    os.makedirs(KLASOR, exist_ok=True)
    yol = os.path.join(KLASOR, f"{symbol}.csv.gz")
    simdi = int(time.time() * 1000)
    baslangic = simdi - gun * 86400 * 1000

    if os.path.exists(yol) and not zorla:
        df = pd.read_csv(yol, parse_dates=["time"])
        if not df.empty and df["time"].min().value // 10**6 <= baslangic + 86400 * 1000:
            return df

    hepsi = []
    since = baslangic
    while since < simdi:
        try:
            yanit = requests.get(
                BINANCE_FONLAMA,
                params={"symbol": symbol, "startTime": since, "limit": 1000},
                timeout=20,
            )
            yanit.raise_for_status()
            veri = yanit.json()
        except Exception as hata:
            print(f"⚠ {symbol} fonlama indirme hatası: {hata}")
            break
        if not veri:
            break
        hepsi.extend(veri)
        son = veri[-1]["fundingTime"]
        if son <= since:
            break
        since = son + 1
        if len(veri) < 1000:
            break

    if not hepsi:
        return pd.DataFrame(columns=["time", "oran"])

    df = pd.DataFrame(
        {
            "time": pd.to_datetime([x["fundingTime"] for x in hepsi], unit="ms"),
            "oran": pd.to_numeric([x["fundingRate"] for x in hepsi], errors="coerce"),
        }
    )
    df = df.dropna().drop_duplicates("time").sort_values("time").reset_index(drop=True)
    df.to_csv(yol, index=False, compression="gzip")
    return df


def tasima(
    df,
    esik=0.0,
    cikis_esigi=0.0,
    komisyon=0.0005,
    kayma=0.0003,
    kaldirac=5.0,
    baslangic=100.0,
    bas=None,
    bit=None,
):
    """Pozitif fonlama dönemlerinde delta-nötr taşıma simülasyonu.

    `esik`: bu oranın üstünde pozisyona gir. `cikis_esigi`: bu oranın altına
    düşünce çık (varsayılan 0 → fonlama negatife dönerse çık).
    """
    if df.empty:
        return {"bakiye": baslangic, "equity": [], "islemler": [], "gun": 0, "maruz_gun": 0}

    d = df.copy()
    if bas is not None:
        d = d[d["time"] >= pd.Timestamp(bas)]
    if bit is not None:
        d = d[d["time"] <= pd.Timestamp(bit)]
    d = d.reset_index(drop=True)
    if d.empty:
        return {"bakiye": baslangic, "equity": [], "islemler": [], "gun": 0, "maruz_gun": 0}

    birim_maliyet = komisyon + kayma
    bakiye = baslangic
    pozisyonda = False
    giris_zamani = None
    aralik_sayaci = 0
    giris_maliyeti = 0.0
    equity = []
    islemler = []
    toplam_maruz = 0

    def kapat(zaman, bakiye):
        nonlocal pozisyonda, aralik_sayaci, giris_maliyeti
        notional = bakiye / (1 + 1 / kaldirac)
        cikis_maliyeti = 2 * notional * birim_maliyet
        bakiye -= cikis_maliyeti
        islemler.append(
            {
                "giris": giris_zamani,
                "cikis": zaman,
                "aralik": aralik_sayaci,
                "mal": giris_maliyeti + cikis_maliyeti,
                "bakiye": bakiye,
            }
        )
        pozisyonda = False
        aralik_sayaci = 0
        giris_maliyeti = 0.0
        return bakiye

    for _, satir in d.iterrows():
        oran = float(satir["oran"])
        zaman = satir["time"]

        if not pozisyonda:
            if oran > esik:
                notional = bakiye / (1 + 1 / kaldirac)
                giris_maliyeti = 2 * notional * birim_maliyet
                bakiye -= giris_maliyeti
                pozisyonda = True
                giris_zamani = zaman
                aralik_sayaci = 0
            continue

        # Pozisyondayız: bu aralığın fonlaması short tarafına ödenir/alınır.
        notional = bakiye / (1 + 1 / kaldirac)
        bakiye += notional * oran
        aralik_sayaci += 1
        toplam_maruz += 1
        equity.append({"zaman": zaman, "efektif": bakiye})

        if oran <= cikis_esigi:
            bakiye = kapat(zaman, bakiye)

    if pozisyonda:
        bakiye = kapat(d["time"].iloc[-1], bakiye)

    gun = (d["time"].iloc[-1] - d["time"].iloc[0]).total_seconds() / 86400
    return {
        "bakiye": bakiye,
        "equity": equity,
        "islemler": islemler,
        "gun": gun,
        "maruz_oran": toplam_maruz / len(d) if len(d) else 0.0,
        "baslangic": baslangic,
    }


def ozet(sonuc):
    equity = sonuc["equity"]
    gun = sonuc.get("gun", 0)
    son = sonuc["bakiye"]
    bas = sonuc["baslangic"]
    getiri = (son / bas - 1) * 100
    if equity:
        deger = pd.Series([e["efektif"] for e in equity], index=[e["zaman"] for e in equity])
        dd = abs((deger / deger.cummax() - 1).min() * 100)
    else:
        dd = 0.0
    yil = gun / 365 if gun > 0 else 0
    yillik = ((son / bas) ** (1 / yil) - 1) * 100 if yil > 0 and son > 0 else 0.0
    return {
        "gun": round(gun, 1),
        "getiri": round(getiri, 2),
        "yillik": round(yillik, 2),
        "max_dd": round(dd, 2),
        "pozisyon": len(sonuc["islemler"]),
        "maruz_gun": round(sonuc.get("maruz_oran", 0.0) * 100, 1),
        "maliyet": round(sum(t["mal"] for t in sonuc["islemler"]), 2),
        "son": round(son, 2),
    }
