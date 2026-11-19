# -*- coding: utf-8 -*-
"""Backtest komut satırı arayüzü.

Kullanım:
    python -m backtest.calistir indir          # 15 sembol, ~345 gün 1h veri
    python -m backtest.calistir analiz         # sinyal + gösterge analizi
    python -m backtest.calistir motor [cfg]    # portföy simülasyonu (v63|v62|filtresiz)
    python -m backtest.calistir hepsi          # üçü birden

Canlı botu etkilemez; ayrı bir araçtır. Sonuçlar `backtest/sonuclar/` altına
CSV olarak yazılır (git'e girmez).
"""
import argparse
import os

import pandas as pd

from backtest.analiz import (
    ayirt_etme_gucu,
    karsilastir,
    kova_analizi,
    metrikler,
    sinyal_taramasi,
)
from backtest.motor import Motor, ozet
from backtest.simule import filtersiz_cfg, v62_cfg, varsayilan_cfg
from backtest.veri import indir

SEMBOLLER = [
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT",
    "AVAXUSDT", "LINKUSDT", "ADAUSDT", "WLDUSDT", "ZECUSDT",
    "BNBUSDT", "HYPEUSDT", "UNIUSDT", "LTCUSDT", "NEARUSDT",
]

GUN = 345          # 345 gün indir; ~40 gün ısınma, ~300 gün simülasyon
ISINMA_GUN = 40
SONUC_KLASOR = os.path.join(os.path.dirname(__file__), "sonuclar")

CFG_SECENEK = {
    "v63": varsayilan_cfg,
    "v62": v62_cfg,
    "filtresiz": filtersiz_cfg,
}


def verileri_yukle(semboller=None, gun=GUN, zorla=False):
    semboller = semboller or SEMBOLLER
    veriler = {}
    for sembol in semboller:
        print(f"📥 {sembol}...", end=" ", flush=True)
        df = indir(sembol, "1h", gun=gun, zorla=zorla)
        if df.empty:
            print("❌ veri yok")
            continue
        veriler[sembol] = df
        print(f"{len(df)} bar ({df['time'].iloc[0]} → {df['time'].iloc[-1]})")
    return veriler


def pencere(veriler, gun=ISINMA_GUN):
    """Isınma sonrası simülasyon penceresi."""
    bas = min(df["time"].iloc[0] for df in veriler.values()) + pd.Timedelta(days=gun)
    bit = max(df["time"].iloc[-1] for df in veriler.values())
    return bas, bit


def _yaz(df, ad):
    os.makedirs(SONUC_KLASOR, exist_ok=True)
    yol = os.path.join(SONUC_KLASOR, ad)
    df.to_csv(yol, index=False)
    return yol


def komut_indir(args):
    verileri_yukle(zorla=args.zorla)


def komut_analiz(args, veriler=None):
    veriler = veriler or verileri_yukle()
    bas, bit = pencere(veriler)
    print(f"\n🗓️ Analiz penceresi: {bas} → {bit}")

    print("\n🔬 Giriş kümeleri karşılaştırması (aynı veri, sinyal seviyesi)...")
    kars = karsilastir(veriler, bas, bit)
    for _, r in kars.iterrows():
        print(
            f"  {r['etiket']:<26} n={int(r['n']):>5}  "
            f"EV={r['ev_bps']:>7.1f} bps  WR=%{r['wr']:>5.1f}  "
            f"TP1=%{r['tp1']:>5.1f}  STOP=%{r['stop']:>5.1f}  "
            f"t={r['t']:>5.2f}  süre={r['sure']:>4.1f}h"
        ) if r["n"] else print(f"  {r['etiket']:<26} sinyal yok")
    _yaz(kars, "karsilastirma.csv")

    print("\n📊 Gösterge kovaları (filtresiz 4/4 sinyaller)...")
    sinyaller = sinyal_taramasi(veriler, filtersiz_cfg(), bas, bit)
    kovalar = kova_analizi(sinyaller)
    if not kovalar.empty:
        print(
            kovalar.to_string(
                index=False,
                formatters={
                    "wr": "{:.0f}".format,
                    "ev_bps": "{:+.1f}".format,
                    "ev_ilk": "{:+.1f}".format,
                    "ev_son": "{:+.1f}".format,
                    "tp1": "{:.0f}".format,
                },
            )
        )
        _yaz(kovalar, "kovalar.csv")
        guc = ayirt_etme_gucu(kovalar)
        _yaz(guc, "ayirt_etme_gucu.csv")
        print("\n🏆 Ayrıt etme gücü (en iyi - en kötü kova, n>=10):")
        print(guc.to_string(index=False))
    else:
        print("  kova oluşmadı")

    print("\n📅 Yarı-örneklem özeti (filtresiz 4/4):")
    if not sinyaller.empty:
        orta = sinyaller["zaman"].median()
        ilk = sinyaller[sinyaller["zaman"] < orta]
        son = sinyaller[sinyaller["zaman"] >= orta]
        for etiket, df in [("ilk yarı", ilk), ("son yarı", son)]:
            m = metrikler(df, etiket)
            print(
                f"  {etiket:<10} n={m['n']:>5}  EV={m['ev_bps']:>+7.1f} bps  "
                f"WR=%{m['wr']:>5.1f}  TP1=%{m['tp1']:>5.1f}  STOP=%{m['stop']:>5.1f}"
            )
    return kars, sinyaller


def komut_motor(args, veriler=None):
    veriler = veriler or verileri_yukle()
    bas, bit = pencere(veriler)
    cfg = CFG_SECENEK[args.cfg]()
    print(f"\n🧮 Motor: {args.cfg}  ({bas} → {bit})")
    motor = Motor(veriler, cfg)
    sonuc = motor.calistir(bas, bit, ilerleme=True)
    _yaz(pd.DataFrame(motor.kayitlar), f"islemler_{args.cfg}.csv")
    _yaz(pd.DataFrame(motor.equity), f"equity_{args.cfg}.csv")

    print(f"\n{'=' * 58}")
    print(f"📊 MOTOR SONUCU — {args.cfg.upper()}")
    print("=" * 58)
    print(f"  İşlem sayısı      : {sonuc['islem']}")
    print(f"  Net PnL           : ${sonuc['pnl']:+.2f}")
    print(f"  Kazanma oranı     : %{sonuc['wr']:.1f}")
    print(f"  İşlem başı EV     : ${sonuc['ev']:+.3f}")
    print(f"  Ort. kazanç/kayıp : ${sonuc['ort_kazanc']:+.2f} / ${sonuc['ort_kayip']:+.2f}")
    print(f"  Komisyon          : ${sonuc['komisyon']:.2f}")
    print(f"  Max drawdown      : %{sonuc['max_dd']:.1f}")
    print(f"  Son efektif bakiye: ${sonuc['son_bakiye']:.2f}")
    print(f"  Çıkış sebepleri   : {sonuc['sebepler']}")
    return motor, sonuc


def komut_hepsi(args):
    veriler = verileri_yukle()
    komut_analiz(args, veriler)
    for cfg in ["filtresiz", "v62", "v63"]:
        args.cfg = cfg
        komut_motor(args, veriler)


def main(argv=None):
    parser = argparse.ArgumentParser(description="FATIH V6 backtest araçları")
    parser.add_argument(
        "komut", choices=["indir", "analiz", "motor", "hepsi"], nargs="?", default="hepsi"
    )
    parser.add_argument("cfg", nargs="?", default="v63", choices=list(CFG_SECENEK))
    parser.add_argument("--zorla", action="store_true", help="önbelleği yok say")
    args = parser.parse_args(argv)

    if args.komut == "indir":
        komut_indir(args)
    elif args.komut == "analiz":
        komut_analiz(args)
    elif args.komut == "motor":
        komut_motor(args)
    else:
        komut_hepsi(args)


if __name__ == "__main__":
    main()
