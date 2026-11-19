# -*- coding: utf-8 -*-
"""Sinyal seviyesinde geçmiş veri analizi.

Portföy kurallarını (boyutlandırma, cooldown, günlük limit) uygulamaz; her
4/4 sinyali tek başına TP1/SL yarışına sokar. Amaç:

1. Filtresiz / V6.2 / V6.3 giriş kümelerinin beklentisini aynı veride kıyaslamak
2. Hangi göstergenin ileri getiriyi ayırt ettiğini kovalara bölerek ölçmek
3. Her bulgunun ilk yarı / son yarı örneklemde tutarlı olup olmadığını görmek

Çıktı birimleri: `pnl_pct` notional başına net getiridir (0.001 = %0,1).
"""
import pandas as pd

from backtest.motor import hazirla, rejim_haritasi, sinyal_uret
from backtest.simule import islem_simule, v62_cfg, varsayilan_cfg, filtersiz_cfg

KOVALAR = {
    "ema_dist": [0, 0.3, 0.45, 0.6, 0.8, 1.2, 2.0, float("inf")],
    "vol_ratio": [0, 0.8, 1.0, 1.3, 1.6, 1.8, 2.2, 3.0, float("inf")],
    "atr_pct": [0, 0.5, 0.7, 0.9, 1.1, 1.3, 1.6, 2.2, float("inf")],
    "rsi_1h": [0, 30, 35, 40, 45, 50, 55, 60, 70, 100],
    "rsi_4h": [0, 30, 40, 45, 50, 55, 60, 70, 100],
    "ema200_dist": [
        float("-inf"), -20, -10, -5, 0, 5, 10, 20, float("inf")
    ],
    "macd_pct": [
        float("-inf"), -0.5, -0.2, -0.05, 0.05, 0.2, 0.5, float("inf")
    ],
}


def _kayit(sembol, i, s, cfg, btc_harita):
    t = s["1h"]["time"].iat[i]
    sinyal = sinyal_uret(s, i, cfg, btc_harita.get(t))
    if sinyal is None:
        return None
    yon, skor, gosterge = sinyal
    r = s["1h"].iloc[i]
    sim = islem_simule(s["1h"], i, yon, float(r["atr"]), cfg)
    kayit = {
        "symbol": sembol,
        "zaman": t,
        "yon": yon,
        "skor": skor,
        "atr_pct": gosterge["atr_pct"],
        "ema_dist": gosterge["ema_dist"],
        "vol_ratio": gosterge["vol_ratio"],
        "rsi_1h": gosterge["rsi_1h"],
        "rsi_4h": gosterge["rsi_4h"],
        "ema200_dist": gosterge["ema200_dist"],
        "macd_pct": gosterge["macd_hist"] / float(r["close"]) * 100,
        "btc_yukari": gosterge["btc_yukari"],
        "pnl_pct": sim["pnl_pct"],
        "sebep": sim["sebep"],
        "ilk_sebep": sim["ilk_sebep"],
        "tp1_gordu": sim["tp1_gordu"],
        "sure_saat": sim["sure_saat"],
    }
    return kayit


def sinyal_taramasi(veriler, cfg=None, baslangic=None, bitis=None, ilerleme=False):
    """Tüm sembollerin 1h barlarında 4/4 sinyalleri tarar ve yarıştırır."""
    cfg = cfg or varsayilan_cfg()
    btc_harita = (
        rejim_haritasi(veriler["BTCUSDT"]) if "BTCUSDT" in veriler else {}
    )
    kayitlar = []
    for sembol, df in veriler.items():
        s = hazirla(df)
        for i, t in enumerate(s["1h"]["time"]):
            if baslangic is not None and t < baslangic:
                continue
            if bitis is not None and t > bitis:
                continue
            k = _kayit(sembol, i, s, cfg, btc_harita)
            if k is not None:
                kayitlar.append(k)
        if ilerleme:
            print(f"  📊 {sembol}: {len(kayitlar)} sinyal")
    df = pd.DataFrame(kayitlar)
    if not df.empty:
        df = df.sort_values("zaman").reset_index(drop=True)
    return df


def metrikler(df, etiket=""):
    if df is None or df.empty:
        return {
            "etiket": etiket,
            "n": 0,
            "ev_bps": 0.0,
            "wr": 0.0,
            "tp1": 0.0,
            "stop": 0.0,
            "t": 0.0,
            "sure": 0.0,
        }
    pnl = df["pnl_pct"]
    std = pnl.std()
    t_stat = pnl.mean() / (std / len(df) ** 0.5) if std and std > 0 else 0.0
    return {
        "etiket": etiket,
        "n": len(df),
        "ev_bps": pnl.mean() * 10000,
        "wr": (pnl > 0).mean() * 100,
        "tp1": df["tp1_gordu"].mean() * 100,
        "stop": (df["ilk_sebep"] == "STOP").mean() * 100,
        "t": t_stat,
        "sure": df["sure_saat"].mean(),
    }


def karsilastir(veriler, baslangic=None, bitis=None):
    """Aynı veride filtresiz / V6.2 / V6.3 giriş kümelerini kıyaslar."""
    satirlar = []
    for etiket, cfg in [
        ("Filtresiz (V6.1 öncesi)", filtersiz_cfg()),
        ("V6.2 (ema/vol)", v62_cfg()),
        ("V6.3 (+ATR bandı)", varsayilan_cfg()),
    ]:
        df = sinyal_taramasi(veriler, cfg, baslangic, bitis)
        satirlar.append(metrikler(df, etiket))
    return pd.DataFrame(satirlar)


def _kova_ozeti(df, kolon):
    kenar = KOVALAR[kolon]
    df = df[df[kolon].notna()].copy()
    if df.empty:
        return pd.DataFrame()
    df["kova"] = pd.cut(df[kolon], kenar, right=False)
    # İlk/son yarı: zamana göre medyan
    orta = df["zaman"].median()
    df["yarim"] = ["ilk" if t < orta else "son" for t in df["zaman"]]

    satirlar = []
    for kova, grup in df.groupby("kova", observed=True):
        ilk = grup[grup["yarim"] == "ilk"]["pnl_pct"]
        son = grup[grup["yarim"] == "son"]["pnl_pct"]
        if len(grup) < 5:
            continue
        satirlar.append(
            {
                "gosterge": kolon,
                "kova": str(kova),
                "n": len(grup),
                "wr": (grup["pnl_pct"] > 0).mean() * 100,
                "ev_bps": grup["pnl_pct"].mean() * 10000,
                "ev_ilk": ilk.mean() * 10000 if len(ilk) else float("nan"),
                "ev_son": son.mean() * 10000 if len(son) else float("nan"),
                "tp1": grup["tp1_gordu"].mean() * 100,
                "tutarli": bool(
                    len(ilk) >= 3
                    and len(son) >= 3
                    and ilk.mean() * son.mean() > 0
                ),
            }
        )
    return pd.DataFrame(satirlar)


def kova_analizi(sinyaller):
    """Göstergelerin ileri getiriyi ayırt edip etmediğini kovalara böler."""
    parcalar = [_kova_ozeti(sinyaller, kolon) for kolon in KOVALAR]
    parcalar = [p for p in parcalar if not p.empty]
    if not parcalar:
        return pd.DataFrame()
    return pd.concat(parcalar, ignore_index=True)


def ayirt_etme_gucu(kovalar, min_n=10):
    """Her göstergede en iyi - en kötü kova EV farkı (n >= min_n)."""
    satirlar = []
    for gosterge, grup in kovalar.groupby("gosterge"):
        grup = grup[grup["n"] >= min_n]
        if len(grup) < 2:
            continue
        en_iyi = grup.loc[grup["ev_bps"].idxmax()]
        en_kotu = grup.loc[grup["ev_bps"].idxmin()]
        satirlar.append(
            {
                "gosterge": gosterge,
                "en_iyi_kova": en_iyi["kova"],
                "en_iyi_ev": round(en_iyi["ev_bps"], 1),
                "en_kotu_kova": en_kotu["kova"],
                "en_kotu_ev": round(en_kotu["ev_bps"], 1),
                "fark_bps": round(en_iyi["ev_bps"] - en_kotu["ev_bps"], 1),
                "tutarli_mi": bool(en_iyi["tutarli"] and en_kotu["tutarli"]),
            }
        )
    if not satirlar:
        return pd.DataFrame()
    return pd.DataFrame(satirlar).sort_values("fark_bps", ascending=False)


