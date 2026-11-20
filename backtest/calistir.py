# -*- coding: utf-8 -*-
"""Backtest komut satırı arayüzü.

Kullanım:
    python -m backtest.calistir indir          # 15 sembol, ~345 gün 1h veri
    python -m backtest.calistir analiz         # sinyal + gösterge analizi
    python -m backtest.calistir motor [cfg]    # portföy simülasyonu
    python -m backtest.calistir hepsi          # üçü birden

`cfg` seçenekleri: v63 (canlı), v62, filtresiz, atr_only, maker, maker_atr,
eski_dd (V6.3.2 öncesi kalıcı kilit), genis20/genis25/genis30 (baraj genişletme).

Canlı botu etkilemez; ayrı bir araçtır. Sonuçlar `backtest/sonuclar/` altına
CSV olarak yazılır (git'e girmez).
"""
import argparse
import os

import numpy as np
import pandas as pd

from backtest.analiz import (
    ayirt_etme_gucu,
    karsilastir,
    kova_analizi,
    metrikler,
    sinyal_taramasi,
)
from backtest.motor import Motor, ozet
from backtest.simule import (
    atr_only_cfg,
    eski_dd_cfg,
    filtersiz_cfg,
    genis_cfg,
    maker_cfg,
    v62_cfg,
    varsayilan_cfg,
)
from backtest.veri import indir

SEMBOLLER = [
    "BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT",
    "AVAXUSDT", "LINKUSDT", "ADAUSDT", "WLDUSDT", "ZECUSDT",
    "BNBUSDT", "HYPEUSDT", "UNIUSDT", "LTCUSDT", "NEARUSDT",
]

GUN = 345          # 345 gün indir; ~40 gün ısınma, ~300 gün simülasyon
ISINMA_GUN = 40

# Kesitsel momentum daha geniş bir kesit ister (sıralama anlamlı olsun diye).
KESITSEL_EK = [
    "TRXUSDT", "DOTUSDT", "ATOMUSDT", "APTUSDT",
    "ARBUSDT", "OPUSDT", "FILUSDT", "SUIUSDT",
]
SONUC_KLASOR = os.path.join(os.path.dirname(__file__), "sonuclar")

CFG_SECENEK = {
    "v63": varsayilan_cfg,
    "v62": v62_cfg,
    "filtresiz": filtersiz_cfg,
    "atr_only": atr_only_cfg,
    "maker": maker_cfg,
    "maker_atr": lambda: maker_cfg(atr_only_cfg()),
    "eski_dd": eski_dd_cfg,
    "genis20": lambda: genis_cfg(2.0),
    "genis25": lambda: genis_cfg(2.5),
    "genis30": lambda: genis_cfg(3.0),
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


def komut_kesitsel(args, veriler=None):
    """Kesitsel momentum: uzun/kısa sepet backtesti (araştırma)."""
    from backtest.kesitsel import calistir as kesitsel_calistir
    from backtest.kesitsel import ozet, panel

    if args.veri_uzun:
        import backtest.veri as veri_modulu

        veri_modulu.KLASOR = os.path.join(os.path.dirname(__file__), "veri_uzun")

    semboller = args.sembol.split(",") if args.sembol else (SEMBOLLER + KESITSEL_EK)
    veriler = veriler or verileri_yukle(semboller)
    A, K = panel(veriler, args.tf)
    bas = args.bas or str(K.index[0].date())
    bit = args.bit or str(K.index[-1].date())

    cfg = dict(
        geri_bak=args.geri,
        tut=args.tut,
        adet=args.adet,
        brut=args.brut,
        agirlik=args.agirlik,
        maliyet_modu=args.maliyet,
    )
    print(f"\n🧮 Kesitsel momentum — {len(veriler)} sembol, {args.tf}")
    print(f"   geri_bak={args.geri} tut={args.tut} adet={args.adet} brüt={args.brut}x "
          f"ağırlık={args.agirlik} maliyet={args.maliyet}")
    print(f"   {bas} → {bit}\n")

    if args.faz > 1:
        # Canlıda giriş fazını seçemezsin: her fazı ayrı koş, medyanı göster.
        # Dikkat: faz yalnızca `tut` modunda anlamlıdır (i += tut), yani
        # benzersiz faz sayısı en fazla `tut` kadardır.
        z = K.index
        b0 = int(np.searchsorted(z, pd.Timestamp(bas)))
        benzersiz = min(args.faz, args.tut)
        getiriler, ddler, pozlar = [], [], []
        for sh in range(benzersiz):
            i = b0 + sh
            if i >= len(z):
                break
            o = ozet(kesitsel_calistir(A, K, bas=z[i], bit=bit, **cfg))
            if o["periyot"] >= 3:
                getiriler.append(o["getiri"])
                ddler.append(o["max_dd"])
                pozlar.append(o["periyot"])
        if not getiriler:
            print("  yeterli veri yok")
            return
        g = np.array(getiriler)
        print(f"  {len(g)} benzersiz faz (mod {args.tut})  medyan {np.median(g):+.1f}%  "
              f"ort {g.mean():+.1f}%")
        print(f"  min {g.min():+.1f}%  max {g.max():+.1f}%  medyan DD %{np.median(ddler):.1f}  "
              f"pozitif faz {int((g > 0).sum())}/{len(g)}  işlem≈{int(np.median(pozlar))}")
        if len(g) > 1 and g.max() - g.min() > 40:
            print("  ⚠ fazlar arası fark çok geniş: sonuç giriş zamanına aşırı duyarlı,"
                  " yani kenar zayıf.")
        return

    sonuc = kesitsel_calistir(A, K, bas=bas, bit=bit, **cfg)
    o = ozet(sonuc)
    print(f"  İşlem (dengeleme) : {o['periyot']}")
    print(f"  Net getiri        : {o['getiri']:+.1f}%  (${o['son']:.2f})")
    print(f"  Aylık bileşik     : %{o['aylik']:.2f}")
    print(f"  Kazanma oranı     : %{o['wr']:.1f}")
    print(f"  Max drawdown      : %{o['max_dd']:.1f}")
    print(f"  Maliyet           : ${o['maliyet']:.2f}")
    return sonuc


def komut_fonlama(args, veriler=None):
    """Fonlama taşıması (delta-nötr) — yön tahmini gerektirmeyen prim."""
    from backtest.fonlama import indir_fonlama, ozet, tasima

    semboller = args.sembol.split(",") if args.sembol else (SEMBOLLER + KESITSEL_EK)
    sonuclar = {}
    print(f"\n💰 Fonlama taşıması — {len(semboller)} sembol")
    print(f"   giriş eşiği {args.esik:.4f}%  çıkış {args.cikis:.4f}%  "
          f"kaldıraç {args.kaldirac:.0f}x  komisyon {args.komisyon * 1e4:.0f} + "
          f"kayma {args.kayma * 1e4:.0f} bps\n")
    for sembol in semboller:
        df = indir_fonlama(sembol, gun=args.gun)
        if df.empty:
            continue
        sonuclar[sembol] = tasima(
            df,
            esik=args.esik / 100,
            cikis_esigi=args.cikis / 100,
            komisyon=args.komisyon,
            kayma=args.kayma,
            kaldirac=args.kaldirac,
            bas=args.bas or None,
            bit=args.bit or None,
        )
    if not sonuclar:
        print("  veri yok")
        return

    satirlar = []
    for sembol, r in sonuclar.items():
        o = ozet(r)
        satirlar.append(
            {"sembol": sembol, "getiri%": o["getiri"], "yıllık%": o["yillik"],
             "DD%": o["max_dd"], "tur": o["pozisyon"], "maruz%": o["maruz_gun"]}
        )
    tablo = pd.DataFrame(satirlar).sort_values("getiri%", ascending=False)
    print(tablo.to_string(index=False))
    print(f"\n  medyan getiri %{tablo['getiri%'].median():.1f}  "
          f"ort %{tablo['getiri%'].mean():.1f}  "
          f"negatif {int((tablo['getiri%'] < 0).sum())}/{len(tablo)}")
    return tablo


def komut_hepsi(args):
    veriler = verileri_yukle()
    komut_analiz(args, veriler)
    for cfg in ["filtresiz", "v62", "v63"]:
        args.cfg = cfg
        komut_motor(args, veriler)


def main(argv=None):
    parser = argparse.ArgumentParser(description="FATIH V6 backtest araçları")
    parser.add_argument(
        "komut", choices=["indir", "analiz", "motor", "kesitsel", "fonlama", "hepsi"],
        nargs="?", default="hepsi",
    )
    parser.add_argument("cfg", nargs="?", default="v63", choices=list(CFG_SECENEK))
    parser.add_argument("--zorla", action="store_true", help="önbelleği yok say")
    # kesitsel komutu
    parser.add_argument("--tf", default="4h", choices=["1h", "4h", "1d"])
    parser.add_argument("--geri", type=int, default=12, help="geri bakış barı")
    parser.add_argument("--tut", type=int, default=24, help="tutma barı")
    parser.add_argument("--adet", type=int, default=3, help="her tarafta kaç coin")
    parser.add_argument("--brut", type=float, default=1.0, help="brüt maruz kalma (kaldıraç)")
    parser.add_argument("--agirlik", default="sira", choices=["esit", "ters_vol", "sira"])
    parser.add_argument("--maliyet", default="fark", choices=["tam", "fark"],
                        help="tam: her dengelemede tüm kitap kapanır (kötümser)")
    parser.add_argument("--faz", type=int, default=1,
                        help="faz sayısı; >1 ise faz medyanı raporlanır (canlıya daha yakın)")
    parser.add_argument("--sembol", default="", help="virgülle ayrılmış sembol listesi")
    parser.add_argument("--bas", default="", help="YYYY-MM-DD")
    parser.add_argument("--bit", default="", help="YYYY-MM-DD")
    parser.add_argument("--veri-uzun", action="store_true",
                        help="backtest/veri_uzun önbelleğini kullan (4 yıllık veri)")
    # fonlama komutu
    parser.add_argument("--esik", type=float, default=0.01, help="giris fonlama esigi (yuzde)")
    parser.add_argument("--cikis", type=float, default=-0.0001, help="cikis fonlama esigi (yuzde)")
    parser.add_argument("--kaldirac", type=float, default=5.0, help="perp bacağı kaldıracı")
    parser.add_argument("--komisyon", type=float, default=0.0005, help="işlem komisyonu (oran)")
    parser.add_argument("--kayma", type=float, default=0.0003, help="kayma (oran)")
    parser.add_argument("--gun", type=int, default=1460, help="geriye kaç gün veri")
    args = parser.parse_args(argv)

    if args.komut == "indir":
        komut_indir(args)
    elif args.komut == "analiz":
        komut_analiz(args)
    elif args.komut == "motor":
        komut_motor(args)
    elif args.komut == "kesitsel":
        komut_kesitsel(args)
    elif args.komut == "fonlama":
        komut_fonlama(args)
    else:
        komut_hepsi(args)


if __name__ == "__main__":
    main()
