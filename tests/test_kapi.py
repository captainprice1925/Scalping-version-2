# -*- coding: utf-8 -*-
"""V6.4 kapı değerlendiricisinin `/istatistik` ile aynı tanımı kullandığını doğrular.

Kritik noktalar:
- TP1/TP2/TP3/BE kayıtları aynı `poz_id` altında **tek işlem** sayılır
- FONLAMA kayıtları işlem sayılmaz (ama PnL'i işlemin içinde gelir)
- bps = toplam PnL / toplam notional × 1e4
- 60 işlemden az örneklemde hüküm verilmez
"""
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from backtest.kapi import ESIK, degerlendir, rapor


def kayit(poz_id, pnl, notional=100.0, sebep="TP1", yon="SHORT", zaman="2026-01-01T00:00"):
    return {
        "poz_id": poz_id,
        "symbol": "BTCUSDT",
        "direction": yon,
        "pnl": pnl,
        "notional": notional,
        "sebep": sebep,
        "zaman": zaman,
        "giris_zamani": "2026-01-01T00:00",
    }


def state(kayitlar, bakiye=100.0, peak=100.0, pozisyonlar=None):
    return {
        "islem_gecmisi": kayitlar,
        "bakiye": bakiye,
        "peak_bakiye": peak,
        "pozisyonlar": pozisyonlar or [],
    }


class GruplamaTesti(unittest.TestCase):
    def test_tp_parcalari_tek_islem(self):
        s = state([
            kayit("a", 0.4, sebep="TP1"),
            kayit("a", 0.3, sebep="TP2"),
            kayit("a", 0.2, sebep="TP3"),
            kayit("b", -1.0, sebep="STOP"),
        ])
        d = degerlendir(s)
        self.assertEqual(d["islem"], 2)
        self.assertEqual(d["kazanan"], 1)
        self.assertAlmostEqual(d["islemler"][0]["pnl"], 0.9)

    def test_fonlama_islem_sayilmaz(self):
        s = state([
            kayit("a", 0.5),
            kayit("a", -0.0001, sebep="FONLAMA"),
        ])
        d = degerlendir(s)
        self.assertEqual(d["islem"], 1)
        # /istatistik ile aynı: fonlama işlem PnL'ine katılmaz, ayrı raporlanır.
        self.assertAlmostEqual(d["net"], 0.5)
        self.assertAlmostEqual(d["fonlama"], -0.0001)

    def test_bos_state(self):
        d = degerlendir(state([]))
        self.assertEqual(d["islem"], 0)
        self.assertFalse(d["hazir"])
        self.assertEqual(d["bps"], 0.0)


class OlcuTesti(unittest.TestCase):
    def test_bps_notional_agirlikli(self):
        s = state([
            kayit("a", 1.0, notional=100.0),
            kayit("b", -0.5, notional=300.0),
        ])
        d = degerlendir(s)
        self.assertAlmostEqual(d["bps"], 0.5 / 400.0 * 1e4, places=6)

    def test_wr_kazanan_orani(self):
        s = state([kayit(str(i), 1.0 if i < 3 else -1.0) for i in range(4)])
        d = degerlendir(s)
        self.assertAlmostEqual(d["wr"], 75.0)

    def test_kapali_pozisyon_dd_hesaplanir(self):
        s = state([
            kayit("a", 5.0, zaman="2026-01-01T00:00"),
            kayit("b", -10.0, zaman="2026-01-02T00:00"),
        ], bakiye=95.0, peak=105.0)
        d = degerlendir(s)
        self.assertGreater(d["dd"], 0.0)
        self.assertAlmostEqual(d["dd_gerceklesen"], 10.0 / 105.0 * 100, places=4)


class KapiTesti(unittest.TestCase):
    def test_60_den_az_orneklemde_hukum_yok(self):
        s = state([kayit(str(i), 1.0) for i in range(59)])
        d = degerlendir(s)
        self.assertFalse(d["hazir"])
        self.assertIn("Karar yok", rapor(d))

    def test_60_kazanan_islem_kapiyi_gecer(self):
        s = state([kayit(str(i), 1.0, notional=100.0) for i in range(60)])
        d = degerlendir(s)
        self.assertTrue(d["hazir"])
        self.assertTrue(d["gecti"])
        self.assertAlmostEqual(d["bps"], 100.0)

    def test_dusuk_wr_kapiyi_kaybettirir(self):
        # 60 işlem, 33 kazanan -> %55 WR, eşik %57
        s = state([kayit(str(i), 1.0 if i < 33 else -1.0, notional=100.0) for i in range(60)])
        d = degerlendir(s)
        self.assertTrue(d["hazir"])
        self.assertFalse(d["gecti"])
        self.assertFalse(d["satirlar"]["wr"])

    def test_yuksek_dd_kapiyi_kaybettirir(self):
        # 30 kazanç (özkaynak 100 -> 130), sonra 30 kayıp (130 -> 105): DD %19
        kayitlar = [kayit(f"k{i}", 1.0, notional=100.0, zaman=f"2026-01-{i+1:02d}T00:00")
                    for i in range(30)]
        kayitlar += [kayit(f"z{i}", -0.8333, notional=100.0, zaman=f"2026-03-{i+1:02d}T00:00")
                     for i in range(30)]
        s = state(kayitlar, bakiye=105.0, peak=130.0)
        d = degerlendir(s, baslangic=100.0)
        self.assertTrue(d["hazir"])
        self.assertGreater(d["dd"], ESIK["dd"])
        self.assertFalse(d["satirlar"]["dd"])

    def test_esik_sabit(self):
        self.assertEqual(ESIK["islem"], 60)
        self.assertEqual(ESIK["bps"], 5.0)
        self.assertEqual(ESIK["wr"], 57.0)
        self.assertEqual(ESIK["dd"], 15.0)


if __name__ == "__main__":
    unittest.main()
