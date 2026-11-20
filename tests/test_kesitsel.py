# -*- coding: utf-8 -*-
"""Kesitsel momentum aracının sözleşmesini doğrular.

Kritik noktalar:
- Sinyal i barı kapanışında, işlem i+1 barı açılışında (ileriye bakış yok)
- Sepet dolar-nötr ve brüt maruz kalma `brut` kadar
- Maliyet modeli: "tam" 2×(komisyon+kayma), "fark" yalnızca değişen pozisyon
- Faz taraması aynı veride farklı giriş zamanları üretir
"""
import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from backtest.kesitsel import _dengele, _agirliklar, calistir, ozet, panel

SEMBOLLER = ["A", "B", "C", "D", "E", "F", "G", "H"]


def sentetik_panel(bar=300, tohum=5, drift=None):
    """Semboller arasında sabit bir güç sırası olan deterministik panel."""
    rng = np.random.default_rng(tohum)
    zaman = pd.date_range("2026-01-01", periods=bar, freq="4h")
    A, K = {}, {}
    for n, ad in enumerate(SEMBOLLER):
        egim = 0.0 if drift is None else drift[n]
        getiri = rng.normal(egim, 0.004, bar)
        kapanis = 100 * np.exp(np.cumsum(getiri))
        acilis = np.r_[kapanis[0], kapanis[:-1]]
        A[ad] = pd.Series(acilis, index=zaman)
        K[ad] = pd.Series(kapanis, index=zaman)
    return pd.DataFrame(A), pd.DataFrame(K)


class AgirlikTesti(unittest.TestCase):
    def test_sira_agirligi_azalan(self):
        w = _agirliklar(list("ABC"), 1.0, pd.Series(dtype=float), range(3), "sira")
        self.assertAlmostEqual(sum(w.values()), 1.0)
        self.assertGreater(w["A"], w["B"])
        self.assertGreater(w["B"], w["C"])

    def test_esit_agirlik(self):
        w = _agirliklar(list("ABCD"), 1.0, pd.Series(dtype=float), range(4), "esit")
        for deger in w.values():
            self.assertAlmostEqual(deger, 0.25)

    def test_ters_vol_dusuk_vola_fazla_agirlik(self):
        vol = pd.Series({"A": 0.01, "B": 0.04})
        w = _agirliklar(["A", "B"], 1.0, vol, range(2), "ters_vol")
        self.assertGreater(w["A"], w["B"])
        self.assertAlmostEqual(sum(w.values()), 1.0)

    def test_ters_vol_sifir_vol_patlama_yapmaz(self):
        vol = pd.Series({"A": 0.0, "B": 0.04})
        w = _agirliklar(["A", "B"], 1.0, vol, range(2), "ters_vol")
        self.assertAlmostEqual(w["B"], 1.0)


class DolarNotrTesti(unittest.TestCase):
    def test_kitap_dolar_notr_ve_brut_maruz_kalma(self):
        A, K = sentetik_panel()
        VOL = K.pct_change().rolling(12, min_periods=5).std()
        for brut in (1.0, 2.0):
            t = _dengele(A, K, VOL, 60, 12, 24, 2, brut, 100.0,
                         0.0005, 0.0003, "esit", {}, "tam")
            self.assertIsNotNone(t)
            toplam = sum(t["kitap"].values())
            brut_maruz = sum(abs(v) for v in t["kitap"].values())
            self.assertAlmostEqual(toplam, 0.0, places=8)
            self.assertAlmostEqual(brut_maruz, 100.0 * brut, places=8)

    def test_uzun_ve_kisa_ayni_sayida(self):
        A, K = sentetik_panel()
        VOL = K.pct_change().rolling(12, min_periods=5).std()
        t = _dengele(A, K, VOL, 60, 12, 24, 3, 1.0, 100.0,
                     0.0005, 0.0003, "esit", {}, "tam")
        self.assertEqual(len(t["uzun"]), 3)
        self.assertEqual(len(t["kisa"]), 3)
        self.assertFalse(set(t["uzun"]) & set(t["kisa"]))


class IleriyeBakisTesti(unittest.TestCase):
    def test_giris_i_plus_1_acilisindan(self):
        """Getiri tam olarak A[i+1] -> A[i+1+tut] üzerinden hesaplanmalı."""
        A, K = sentetik_panel(tohum=9)
        i, tut, adet = 80, 24, 2
        VOL = K.pct_change().rolling(12, min_periods=5).std()
        t = _dengele(A, K, VOL, i, 12, tut, adet, 1.0, 100.0,
                     0.0, 0.0, "esit", {}, "tam")  # maliyet sıfır: saf fiyat etkisi

        j = i + 1
        cikis = j + tut
        beklenen = 0.0
        for sembol in t["uzun"]:
            beklenen += 50.0 / adet * (A[sembol].iat[cikis] / A[sembol].iat[j] - 1)
        for sembol in t["kisa"]:
            beklenen += 50.0 / adet * -(A[sembol].iat[cikis] / A[sembol].iat[j] - 1)

        self.assertAlmostEqual(t["brut_pnl"], beklenen, places=9)
        self.assertEqual(t["zaman"], K.index[i])
        self.assertEqual(t["zaman_cikis"], K.index[cikis])

    def test_sinyal_barinin_kapanisini_kullanir(self):
        """Sıralama K[i] / K[i-geri_bak] ile yapılmalı, gelecekteki barla değil."""
        A, K = sentetik_panel(tohum=13)
        i, geri_bak, adet = 100, 12, 2
        VOL = K.pct_change().rolling(12, min_periods=5).std()
        t = _dengele(A, K, VOL, i, geri_bak, 24, adet, 1.0, 100.0,
                     0.0005, 0.0003, "esit", {}, "tam")

        gecmis = (K.iloc[i] / K.iloc[i - geri_bak] - 1).sort_values(ascending=False)
        self.assertEqual(t["uzun"], list(gecmis.index[:adet]))
        self.assertEqual(t["kisa"], list(gecmis.index[-adet:]))

    def test_gecmis_yetmezse_islem_acmaz(self):
        A, K = sentetik_panel()
        VOL = K.pct_change().rolling(12, min_periods=5).std()
        # 8 sembol, adet=4 -> en az 10 geçmiş gerekir, 5 bar yeterli değil
        self.assertIsNone(
            _dengele(A, K, VOL, 5, 12, 24, 4, 1.0, 100.0, 0.0005, 0.0003, "esit", {}, "tam")
        )


class MaliyetTesti(unittest.TestCase):
    def test_tam_maliyet_formulu(self):
        A, K = sentetik_panel()
        VOL = K.pct_change().rolling(12, min_periods=5).std()
        t = _dengele(A, K, VOL, 60, 12, 24, 3, 1.0, 100.0,
                     0.0005, 0.0003, "esit", {}, "tam")
        beklenen = 100.0 * 2 * (0.0005 + 0.0003)
        self.assertAlmostEqual(t["maliyet"], beklenen, places=9)

    def test_fark_kitap_degismezse_sifir_maliyet(self):
        A, K = sentetik_panel()
        VOL = K.pct_change().rolling(12, min_periods=5).std()
        ilk = _dengele(A, K, VOL, 60, 12, 24, 2, 1.0, 100.0,
                       0.0005, 0.0003, "esit", {}, "tam")
        ayni = _dengele(A, K, VOL, 60, 12, 24, 2, 1.0, 100.0,
                        0.0005, 0.0003, "esit", ilk["kitap"], "fark")
        self.assertAlmostEqual(ayni["maliyet"], 0.0, places=9)

    def test_fark_tam_kadardan_fazla_olamaz(self):
        A, K = sentetik_panel()
        VOL = K.pct_change().rolling(12, min_periods=5).std()
        tam = _dengele(A, K, VOL, 60, 12, 24, 2, 1.0, 100.0,
                       0.0005, 0.0003, "esit", {}, "tam")
        fark = _dengele(A, K, VOL, 60, 12, 24, 2, 1.0, 100.0,
                        0.0005, 0.0003, "esit", {}, "fark")
        self.assertAlmostEqual(tam["maliyet"], fark["maliyet"], places=9)


class CalistirTesti(unittest.TestCase):
    def test_equity_cikis_zamaninda_kaydedilir(self):
        A, K = sentetik_panel(bar=300)
        s = calistir(A, K, geri_bak=12, tut=24, adet=2, brut=1.0)
        for islem, eq in zip(s["islemler"], s["equity"]):
            self.assertEqual(eq["zaman"], islem["zaman_cikis"])

    def test_bakiye_zinciri_tutarli(self):
        A, K = sentetik_panel(bar=300)
        s = calistir(A, K, geri_bak=12, tut=24, adet=2, brut=1.0)
        bakiye = s["baslangic"]
        for islem in s["islemler"]:
            bakiye += islem["net"]
            self.assertAlmostEqual(islem["bakiye"], bakiye, places=9)
        self.assertAlmostEqual(s["bakiye"], bakiye, places=9)

    def test_ayni_veri_ayni_sonuc(self):
        A, K = sentetik_panel()
        a = calistir(A, K, geri_bak=12, tut=24, adet=3)
        b = calistir(A, K, geri_bak=12, tut=24, adet=3)
        self.assertEqual(a["bakiye"], b["bakiye"])

    def test_farkli_faz_farkli_islem_uretir(self):
        A, K = sentetik_panel(bar=400)
        a = calistir(A, K, bas=K.index[40], bit=K.index[-1], geri_bak=12, tut=24, adet=2)
        b = calistir(A, K, bas=K.index[41], bit=K.index[-1], geri_bak=12, tut=24, adet=2)
        self.assertNotEqual(a["islemler"][0]["zaman"], b["islemler"][0]["zaman"])

    def test_ozet_alanlari(self):
        A, K = sentetik_panel()
        o = ozet(calistir(A, K, geri_bak=12, tut=24, adet=2))
        for alan in ("periyot", "getiri", "aylik", "max_dd", "wr", "ort", "maliyet", "son"):
            self.assertIn(alan, o)
        self.assertGreaterEqual(o["max_dd"], 0.0)
        self.assertLessEqual(o["wr"], 100.0)


class PanelTesti(unittest.TestCase):
    def test_dort_saatlik_panel_hizalanir(self):
        rng = np.random.default_rng(1)
        zaman = pd.date_range("2026-01-01", periods=400, freq="1h")
        veriler = {}
        for ad in ("BTCUSDT", "ETHUSDT"):
            fiyat = 100 * np.exp(np.cumsum(rng.normal(0, 0.004, 400)))
            veriler[ad] = pd.DataFrame(
                {
                    "time": zaman,
                    "open": fiyat,
                    "high": fiyat * 1.01,
                    "low": fiyat * 0.99,
                    "close": fiyat,
                    "volume": 1.0,
                }
            )
        A, K = panel(veriler, "4h")
        self.assertEqual(len(K), 100)
        self.assertEqual(list(K.columns), ["BTCUSDT", "ETHUSDT"])
        self.assertEqual(A.index.equals(K.index), True)
        self.assertFalse(K.isna().any().any())


if __name__ == "__main__":
    unittest.main()
