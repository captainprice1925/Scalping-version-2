# -*- coding: utf-8 -*-
"""Kesitsel (cross-sectional) momentum backtesti — uzun/kısa sepet.

Fikir: tek bir coinin yönünü tahmin etmek yerine, sepetin içinde **göreli**
güç sıralaması kullanılır. Her dengelemede son `geri_bak` barın getirisine göre
en güçlü `adet` coin LONG, en zayıf `adet` coin SHORT alınır. Sepet dolar-nötr
olduğu için piyasa yönüne bağımlılık düşer.

Ağırlıklandırma (`agirlik`):
  "esit"     — her bacak aynı notional (varsayılan)
  "ters_vol" — her bacak 1/volatilite ile ölçeklenir, yani bacaklar eşit risk
               taşır. Tek bir çok oynak coinin sonucu domine etmesini engeller.
  "sira"     — sıralamadaki güce göre doğrusal ağırlık (en güçlü en ağır)

Maliyet varsayımı: her dengelemede tüm bacaklar kapanıp yeniden açılır, yani
tur başına 2 × (komisyon + kayma). Aynı coin sepette kalsa bile maliyet
ödenir — bu **kasıtlı olarak kötümser**; gerçek dolum daha az maliyetli olabilir.

Giriş/çıkış: sinyal barı kapanışında hesaplanır, işlem **sonraki barın açılışında**
yapılır (ileriye bakış yok). Fonlama modellenmez.

Canlı bot bu modülü import etmez; araştırma aracıdır.
"""
import numpy as np
import pandas as pd

from backtest.veri import dort_saatlik

TF_BAR_SAAT = {"1h": 1, "4h": 4, "1d": 24}


def panel(veriler, tf="4h"):
    """Sembollerin açılış/kapanış fiyatlarını ortak zaman indeksinde birleştirir."""
    acilis, kapanis = {}, {}
    for sembol, df in veriler.items():
        d = dort_saatlik(df) if tf == "4h" else df
        d = d.set_index("time").sort_index()
        acilis[sembol] = d["open"]
        kapanis[sembol] = d["close"]
    K = pd.DataFrame(kapanis).sort_index().astype(float)
    A = pd.DataFrame(acilis).reindex(K.index).astype(float)
    return A, K


def _agirliklar(semboller, yon, vol, sira, agirlik):
    """Bacak notional ağırlıkları (toplamı 1.0 olacak şekilde normalize)."""
    n = len(semboller)
    if n == 0:
        return {}
    if agirlik == "ters_vol":
        w = np.array([1.0 / vol[s] if np.isfinite(vol[s]) and vol[s] > 0 else 0.0 for s in semboller])
        if w.sum() <= 0:
            w = np.ones(n)
    elif agirlik == "sira":
        w = np.array([max(n - k, 0.5) for k in sira], dtype=float)
    else:
        w = np.ones(n)
    return dict(zip(semboller, w / w.sum()))


def _dengele(A, K, VOL, i, geri_bak, tut, adet, brut, bakiye, komisyon, kayma, agirlik, onceki_kitap, maliyet_modu):
    """i barındaki sinyalle i+1 açılışından girer, i+1+tut açılışından çıkar."""
    j = i + 1
    cikis = j + tut
    if cikis >= len(K):
        return None

    gecmis = (K.iloc[i] / K.iloc[i - geri_bak] - 1).dropna()
    if len(gecmis) < 2 * adet + 2:
        return None

    sirali = gecmis.sort_values(ascending=False)
    uzun = list(sirali.index[:adet])
    kisa = list(sirali.index[-adet:])

    wu = _agirliklar(uzun, 1.0, VOL.iloc[i], range(adet), agirlik)
    wk = _agirliklar(kisa, -1.0, VOL.iloc[i], range(adet), agirlik)

    taraf_notional = bakiye * brut / 2.0  # long ve short tarafı ayrı ayrı
    birim_maliyet = komisyon + kayma
    brut_pnl = 0.0
    kitap = {}
    for sembol, w in wu.items():
        kitap[sembol] = taraf_notional * w
    for sembol, w in wk.items():
        kitap[sembol] = -taraf_notional * w

    # Maliyet: "tam" = her dengelemede tüm kitap kapanıp yeniden açılır (kötümser)
    #         "fark" = yalnızca pozisyon değişimi kadar (gerçekçi)
    if maliyet_modu == "fark" and onceki_kitap:
        maliyet = 0.0
        for sembol in set(kitap) | set(onceki_kitap):
            maliyet += abs(kitap.get(sembol, 0.0) - onceki_kitap.get(sembol, 0.0)) * birim_maliyet
    else:
        maliyet = sum(abs(v) for v in kitap.values()) * 2 * birim_maliyet

    for sembol, notional in kitap.items():
        giris_f = A[sembol].iat[j]
        cikis_f = A[sembol].iat[cikis]
        if not np.isfinite(giris_f) or not np.isfinite(cikis_f) or giris_f <= 0:
            continue
        brut_pnl += notional * (cikis_f / giris_f - 1)

    return {
        "zaman": K.index[i],
        "zaman_cikis": K.index[cikis],
        "uzun": uzun,
        "kisa": kisa,
        "brut_pnl": brut_pnl,
        "maliyet": maliyet,
        "net": brut_pnl - maliyet,
        "bakiye": bakiye + brut_pnl - maliyet,
        "kitap": kitap,
    }


def calistir(
    A,
    K,
    geri_bak=42,
    tut=42,
    adet=3,
    brut=1.0,
    komisyon=0.0005,
    kayma=0.0003,
    baslangic=100.0,
    bas=None,
    bit=None,
    agirlik="esit",
    maliyet_modu="tam",
):
    """Sepet momentumunu kronolojik oynatır; bakiye ve işlem listesi döner.

    `bas` verilirse dengeleme ızgarası o bardan başlar; ızgara `tut` adımıyla
    ilerlediği için yalnızca `bas` mod `tut` kadar farklı sonuç üretir.
    Canlıda bu fazı seçemezsin — bu yüzden tek bir faz yerine fazların
    medyanını raporlamak gerekir (`python -m backtest.calistir kesitsel --faz 24`).
    """
    zamanlar = K.index
    VOL = K.pct_change().rolling(max(geri_bak, 5), min_periods=5).std()

    if bas is not None:
        ilk = int(np.searchsorted(zamanlar, pd.Timestamp(bas)))
    else:
        ilk = geri_bak
    if bit is not None:
        son = int(np.searchsorted(zamanlar, pd.Timestamp(bit), side="right"))
    else:
        son = len(zamanlar)

    bakiye = baslangic
    equity = []
    islemler = []
    onceki_kitap = {}
    i = max(ilk, geri_bak)
    while i < son:
        sonuc = _dengele(
            A, K, VOL, i, geri_bak, tut, adet, brut, bakiye, komisyon, kayma,
            agirlik, onceki_kitap, maliyet_modu,
        )
        if sonuc is None:
            i += 1
            continue
        bakiye = sonuc["bakiye"]
        onceki_kitap = sonuc["kitap"]
        islemler.append(sonuc)
        equity.append({"zaman": sonuc["zaman_cikis"], "efektif": bakiye})
        i += tut

    return {
        "bakiye": bakiye,
        "equity": equity,
        "islemler": islemler,
        "baslangic": baslangic,
    }


def ozet(sonuc, bar_saat=4):
    equity = sonuc["equity"]
    islemler = sonuc["islemler"]
    if not equity:
        return {"periyot": 0, "gun": 0, "pnl": 0.0, "getiri": 0.0, "aylik": 0.0,
                "max_dd": 0.0, "wr": 0.0, "ort": 0.0, "maliyet": 0.0, "son": sonuc["baslangic"]}

    deger = pd.Series([e["efektif"] for e in equity], index=[e["zaman"] for e in equity])
    tepe = deger.cummax()
    dd = (deger / tepe - 1).min() * 100
    gun = (deger.index[-1] - deger.index[0]).total_seconds() / 86400
    son = deger.iloc[-1]
    bas = sonuc["baslangic"]
    getiri = (son / bas - 1) * 100

    ay = gun / 30.44 if gun > 0 else 0
    aylik = ((son / bas) ** (1 / ay) - 1) * 100 if ay > 0 and son > 0 else 0.0

    netler = [t["net"] for t in islemler]
    return {
        "periyot": len(islemler),
        "gun": round(gun, 1),
        "pnl": round(son - bas, 2),
        "getiri": round(getiri, 1),
        "aylik": round(aylik, 2),
        "max_dd": round(abs(dd), 1),
        "wr": round(sum(1 for n in netler if n > 0) / len(netler) * 100, 1) if netler else 0.0,
        "ort": round(float(np.mean(netler)), 3) if netler else 0.0,
        "maliyet": round(sum(t["maliyet"] for t in islemler), 2),
        "son": round(float(son), 2),
    }
