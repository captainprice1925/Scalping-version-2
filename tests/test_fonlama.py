# -*- coding: utf-8 -*-
"""Fonlama taşıması aracının sözleşmesini doğrular.

Kritik noktalar:
- Pozitif fonlama short tarafına ödenir: pozisyondayken bakiye artar
- Negatif fonlama ve eşik altı oranlarda pozisyona girilmez
- Sermaye = notional * (1 + 1/kaldıraç); notional sermayeden küçüktür
- Giriş ve çıkışta iki bacak da işlem görür: 2 * notional * (komisyon + kayma)
"""
import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from backtest.fonlama import ozet, tasima


def seri(oranlar, baslangic="2026-01-01", saat=8):
    zaman = pd.date_range(baslangic, periods=len(oranlar), freq=f"{saat}h")
    return pd.DataFrame({"time": zaman, "oran": oranlar})


class TasimaTesti(unittest.TestCase):
    def test_pozitif_fonlama_bakiye_buyutur(self):
        s = tasima(seri([0.0001] * 50), komisyon=0.0, kayma=0.0)
        self.assertGreater(s["bakiye"], 100.0)
        self.assertEqual(len(s["islemler"]), 1)

    def test_sifir_ve_negatif_fonlamada_islem_acmaz(self):
        s = tasima(seri([0.0] * 20 + [-0.0001] * 20))
        self.assertEqual(s["islemler"], [])
        self.assertAlmostEqual(s["bakiye"], 100.0)

    def test_esik_altinda_islem_acmaz(self):
        s = tasima(seri([0.00005] * 30), esik=0.0001)
        self.assertEqual(s["islemler"], [])

    def test_esik_uzerinde_islem_acar(self):
        s = tasima(seri([0.0002] * 30), esik=0.0001)
        self.assertEqual(len(s["islemler"]), 1)

    def test_fonlama_dusunce_cikar_ve_yeniden_girer(self):
        oranlar = [0.0002] * 5 + [0.0] * 5 + [0.0002] * 5
        s = tasima(seri(oranlar), esik=0.0, cikis_esigi=0.0)
        self.assertEqual(len(s["islemler"]), 2)

    def test_kapali_formul_ile_ayni(self):
        """Sıfır maliyette bakiye, notional = bakiye/1.2 zinciriyle büyümeli."""
        s = tasima(seri([0.01] * 10), esik=0.0, komisyon=0.0, kayma=0.0, kaldirac=5.0)
        beklenen = 100.0 * (1 + 0.01 / 1.2) ** 9  # ilk bar giriş, kalan 9 bar kazanç
        self.assertAlmostEqual(s["bakiye"], beklenen, places=9)

    def test_tur_maliyeti_giris_ve_cikis(self):
        """Bir tur = girişte 2 bacak + çıkışta 2 bacak."""
        s = tasima(seri([0.0001] * 10), komisyon=0.0005, kayma=0.0003, kaldirac=5.0)
        notional = 100.0 / 1.2
        tek_bacak_turu = 2 * notional * (0.0005 + 0.0003)
        self.assertAlmostEqual(s["islemler"][0]["mal"], 2 * tek_bacak_turu, delta=tek_bacak_turu * 0.01)

    def test_notional_sermayeden_kucuk(self):
        """Kaldıraçlı perp bacağı olsa bile spot bacak tam notional ister."""
        for kaldirac in (1.0, 3.0, 10.0):
            s = tasima(seri([0.0001] * 10), komisyon=0.0, kayma=0.0, kaldirac=kaldirac)
            self.assertGreater(s["bakiye"], 100.0)
            # getiri, saf fonlama oranının altında kalmalı (sermaye > notional)
            self.assertLess(s["bakiye"] - 100.0, 100.0 * 0.0001 * 10)

    def test_kaldirac_yukseldikce_getiri_artar(self):
        dusuk = tasima(seri([0.0001] * 40), komisyon=0.0, kayma=0.0, kaldirac=1.0)["bakiye"]
        yuksek = tasima(seri([0.0001] * 40), komisyon=0.0, kayma=0.0, kaldirac=10.0)["bakiye"]
        self.assertGreater(yuksek, dusuk)

    def test_bos_seri_patlama_yapmaz(self):
        s = tasima(pd.DataFrame(columns=["time", "oran"]))
        self.assertAlmostEqual(s["bakiye"], 100.0)
        self.assertEqual(s["islemler"], [])

    def test_ozet_alanlari(self):
        o = ozet(tasima(seri([0.0001] * 30)))
        for alan in ("gun", "getiri", "yillik", "max_dd", "pozisyon", "maruz_gun", "son"):
            self.assertIn(alan, o)
        self.assertGreaterEqual(o["max_dd"], 0.0)
        self.assertLessEqual(o["maruz_gun"], 100.0)


if __name__ == "__main__":
    unittest.main()
