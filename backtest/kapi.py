# -*- coding: utf-8 -*-
"""V6.4 kapısını state dosyasından tek komutla değerlendirir.

Kapı `OPERASYON_NOTLARI.md` içinde **önceden** kayıtlıdır ve sonradan
değiştirilmez:

    | Ölçüt              | Eşik    |
    |--------------------|---------|
    | İşlem sayısı       | >= 60   |
    | Beklenti (notional)| >= +5 bps/işlem |
    | İşlem bazlı WR     | >= %57  |
    | Max drawdown       | <= %15  |

Ölçüt tanımları `/istatistik` ile birebir aynıdır: kayıtlar `poz_id` ile tek
işleme toplanır (TP1/TP2/TP3/BE aynı pozisyonun parçalarıdır), bps = toplam PnL /
toplam notional × 1e4.

Kullanım:
    python -m backtest.kapi --state scalp_bot_state.json

Bu modül canlı bot tarafından import edilmez; yalnızca okuma yapar.
"""
import argparse
import contextlib
import io
import json
import os
import sys

# config import edilirken sürüm satırı basıyor; CLI çıktısını temiz tut.
with contextlib.redirect_stdout(io.StringIO()):
    import config

ESIK = {"islem": 60, "bps": 5.0, "wr": 57.0, "dd": 15.0}


def oku(yol):
    with open(yol, encoding="utf-8") as f:
        return json.load(f)


def _grupla(state):
    """`istatistik` ile aynı gruplama: poz_id (yoksa symbol+giriş)."""
    kayitlar = [k for k in state.get("islem_gecmisi", []) if k.get("sebep") != "FONLAMA"]
    gruplar = {}
    for k in kayitlar:
        anahtar = k.get("poz_id") or (k.get("symbol"), k.get("entry"))
        gruplar.setdefault(anahtar, []).append(k)
    islemler = []
    for ks in gruplar.values():
        islemler.append(
            {
                "symbol": ks[0].get("symbol"),
                "direction": ks[0].get("direction"),
                "pnl": sum(k.get("pnl", 0.0) for k in ks),
                "notional": next((k.get("notional") for k in ks if k.get("notional")), 0.0),
                "zaman": max(k.get("zaman", "") for k in ks),
                "giris_zamani": next((k.get("giris_zamani") for k in ks if k.get("giris_zamani")), ""),
                "sebepler": [k.get("sebep") for k in ks],
            }
        )
    islemler.sort(key=lambda t: t["zaman"])
    return islemler


def _acik_pozisyon_degeri(p, kaldirac):
    """`paper_trade._acik_pozisyon_degeri` ile aynı formül."""
    oran = p.get("kalan_yuzde", 100) / 100
    marjin = p.get("notional", 0.0) * oran / kaldirac
    yon = 1.0 if p.get("direction") == "LONG" else -1.0
    giris = p.get("giris_fiyat") or p.get("entry") or 0.0
    son = p.get("son_fiyat") or giris
    brut = (son / giris - 1) * yon * p.get("notional", 0.0) * oran if giris else 0.0
    cikis_komisyonu = p.get("notional", 0.0) * oran * config.CIKIS_KOMISYON_ORANI
    return marjin + brut - cikis_komisyonu


def _ozkaynak(state, baslangic):
    efektif = state.get("bakiye", baslangic) + sum(
        _acik_pozisyon_degeri(p, config.KALDIRAC) for p in state.get("pozisyonlar", [])
    )
    return efektif


def _gerceklesen_dd(islemler, baslangic):
    """Kapanmış işlemlerden gerçekleşen özkaynak eğrisi ve drawdown'ı."""
    deger = baslangic
    tepe = baslangic
    dd = 0.0
    egri = []
    for t in islemler:
        deger += t["pnl"]
        tepe = max(tepe, deger)
        if tepe > 0:
            dd = max(dd, (tepe - deger) / tepe * 100)
        egri.append({"zaman": t["zaman"], "deger": deger})
    return dd, egri


def degerlendir(state, baslangic=None):
    baslangic = baslangic or config.BUTCE_SANAL
    islemler = _grupla(state)
    fonlama = sum(
        k.get("pnl", 0.0) for k in state.get("islem_gecmisi", []) if k.get("sebep") == "FONLAMA"
    )
    n = len(islemler)
    pnl = sum(t["pnl"] for t in islemler)
    notional = sum(t["notional"] for t in islemler)
    kazanan = sum(1 for t in islemler if t["pnl"] > 0)

    bps = (pnl / notional * 1e4) if notional else 0.0
    wr = (kazanan / n * 100) if n else 0.0
    ozkaynak = _ozkaynak(state, baslangic)
    tepe = max(state.get("peak_bakiye", baslangic), ozkaynak)
    dd_canli = ((tepe - ozkaynak) / tepe * 100) if tepe > 0 else 0.0
    dd_gerceklesen, egri = _gerceklesen_dd(islemler, baslangic)
    dd = max(dd_canli, dd_gerceklesen)

    satirlar = {
        "islem": n >= ESIK["islem"],
        "bps": bps >= ESIK["bps"],
        "wr": wr >= ESIK["wr"],
        "dd": dd <= ESIK["dd"],
    }
    return {
        "islem": n,
        "bps": bps,
        "wr": wr,
        "dd": dd,
        "dd_canli": dd_canli,
        "dd_gerceklesen": dd_gerceklesen,
        "pnl": pnl,
        "net": pnl,
        "fonlama": fonlama,
        "notional": notional,
        "kapanmis": n,
        "kazanan": kazanan,
        "kaybeden": n - kazanan,
        "ozkaynak": ozkaynak,
        "baslangic": baslangic,
        "acik": len(state.get("pozisyonlar", [])),
        "satirlar": satirlar,
        "hazir": n >= ESIK["islem"],
        "gecti": all(satirlar.values()),
        "islemler": islemler,
        "egri": egri,
    }


def _isaret(ok):
    return "✅" if ok else "❌"


def rapor(d):
    s = d["satirlar"]
    ilerleme = min(d["islem"] / ESIK["islem"], 1.0) * 100
    satir = [
        f"🚪 V6.4 KAPISI — {d['islem']}/{ESIK['islem']} işlem "
        f"(%{ilerleme:.0f})  {'HAZIR' if d['hazir'] else 'HAZIR DEĞİL'}",
        "",
        f"  {_isaret(s['islem'])} İşlem sayısı      {d['islem']:>7}      eşik >= {ESIK['islem']}",
        f"  {_isaret(s['bps'])} Beklenti (notional) {d['bps']:>+7.1f} bps  eşik >= +{ESIK['bps']:.0f}",
        f"  {_isaret(s['wr'])} İşlem bazlı WR     %{d['wr']:>6.1f}     eşik >= %{ESIK['wr']:.0f}",
        f"  {_isaret(s['dd'])} Max drawdown       %{d['dd']:>6.1f}     eşik <= %{ESIK['dd']:.0f}",
        "",
        f"  Özkaynak ${d['ozkaynak']:.2f}  (başlangıç ${d['baslangic']:.0f})  "
        f"net ${d['net']:+.2f}  fonlama ${d['fonlama']:+.2f}  açık pozisyon {d['acik']}",
        f"  DD canlı %{d['dd_canli']:.1f} · gerçekleşen %{d['dd_gerceklesen']:.1f}",
        "",
    ]

    if not d["hazir"]:
        kalan = ESIK["islem"] - d["islem"]
        satir.append(f"  ⏳ Karar yok. {kalan} işlem daha lazım.")
        satir.append("  Bu ara sayılar kanıt değildir; sadece ilerleme göstergesidir.")
    elif d["gecti"]:
        satir.append("  ✅ KAPI GEÇİLDİ — BARAJ_GENISLETME 2.0'da kalır, yeni tur açılmaz.")
    else:
        kalanlar = [ad for ad, ok in s.items() if not ok]
        satir.append(f"  ❌ KAPI KALDI ({', '.join(kalanlar)}) — "
                     "BARAJ_GENISLETME = 1.0 yapılır, V6.3 davranışına dönülür.")

    if d["islem"]:
        yonler = {}
        for t in d["islemler"]:
            yonler[t["direction"]] = yonler.get(t["direction"], 0) + 1
        satir.append("")
        satir.append(f"  Yön dağılımı: {yonler}")
        if len(yonler) == 1 and d["islem"] >= 3:
            satir.append("  ⚠ Tek yön: işlemler bağımsız bahis değil, tek rejim bahsidir.")
        en_iyi = max(d["islemler"], key=lambda t: t["pnl"])
        kalan_pnl = d["pnl"] - en_iyi["pnl"]
        satir.append(f"  En iyi işlem ({en_iyi['symbol']} ${en_iyi['pnl']:+.2f}) "
                     f"çıkarılınca net ${kalan_pnl:+.2f}")
    return "\n".join(satir)


def main(argv=None):
    parser = argparse.ArgumentParser(description="V6.4 kapı değerlendirmesi")
    parser.add_argument("--state", default="scalp_bot_state.json",
                        help="state JSON yolu (varsayılan: scalp_bot_state.json)")
    parser.add_argument("--baslangic", type=float, default=None,
                        help="başlangıç sermayesi (varsayılan: config.BUTCE_SANAL)")
    args = parser.parse_args(argv)

    if not os.path.exists(args.state):
        print(f"❌ State dosyası yok: {args.state}")
        return 2
    d = degerlendir(oku(args.state), args.baslangic)
    print(rapor(d))
    # Yeterli işlem yoksa "karar yok" — hata kodu dönmez.
    return 0 if (d["gecti"] or not d["hazir"]) else 1


if __name__ == "__main__":
    sys.exit(main())
