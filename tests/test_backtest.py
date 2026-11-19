# -*- coding: utf-8 -*-
"""Backtest aracının canlı kurallarla paritesini ve simülasyon mantığını doğrular."""
import os
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

import config
from faz2_sinyal import calculate_score_fatih
from paper_trade import PaperTrade
from backtest.analiz import kova_analizi, metrikler, sinyal_taramasi
from backtest.motor import Motor, boyutlandir, ozet
from backtest.simule import (
    filtersiz_cfg,
    filtreli_skor,
    genis_cfg,
    islem_simule,
    v62_cfg,
    varsayilan_cfg,
)


def sentetik_veri(sembol_sayisi=3, bar=900, tohum=11):
    rng = np.random.default_rng(tohum)
    zaman = pd.date_range("2026-01-01", periods=bar, freq="1h")
    veriler = {}
    for n in range(sembol_sayisi):
        ad = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"][n]
        fiyat = 100 * np.exp(np.cumsum(rng.normal(0, 0.006, bar)))
        veriler[ad] = pd.DataFrame(
            {
                "time": zaman,
                "open": np.r_[fiyat[0], fiyat[:-1]],
                "high": np.maximum(fiyat * (1 + abs(rng.normal(0, 0.004, bar))), fiyat),
                "low": np.minimum(fiyat * (1 - abs(rng.normal(0, 0.004, bar))), fiyat),
                "close": fiyat,
                "volume": rng.lognormal(10, 1, bar),
            }
        )
    return veriler


class SinyalPariteTestleri(unittest.TestCase):
    def _cerceveler(self, trend_long, ema_dist, vol, rsi, atr_pct):
        df4 = pd.DataFrame(
            {
                "close": [100.0] * 210,
                "ema_200": [100.0] * 210,
            }
        )
        df4.iloc[-1, df4.columns.get_loc("close")] = 110.0 if trend_long else 90.0
        df1 = pd.DataFrame(
            {
                "close": [100.0] * 50,
                "ema_21": [100.0] * 50,
                "volume_ratio": [vol] * 50,
                "rsi": [rsi] * 50,
                "atr_pct": [atr_pct] * 50,
            }
        )
        # ema_dist = |100 - ema21| / 100 * 100 = |100 - ema21|
        df1.iloc[-1, df1.columns.get_loc("ema_21")] = 100.0 - ema_dist
        return df4, df1

    def test_filtreli_skor_canli_fonksiyonla_ayni(self):
        rng = np.random.default_rng(3)
        cfg = varsayilan_cfg()
        for _ in range(400):
            trend_long = bool(rng.integers(0, 2))
            ema_dist = float(rng.uniform(0, 1.5))
            vol = float(rng.uniform(0.5, 2.5))
            rsi = float(rng.uniform(20, 80))
            atr = float(rng.uniform(0.3, 2.5))
            df4, df1 = self._cerceveler(trend_long, ema_dist, vol, rsi, atr)
            canli = calculate_score_fatih(df4, df1)
            motor = filtreli_skor(trend_long, ema_dist, vol, rsi, atr, cfg)
            self.assertEqual(canli, motor, (trend_long, ema_dist, vol, rsi, atr))

    def test_v63_atr_bandi_eliyor(self):
        cfg = varsayilan_cfg()
        # Bant dışı ATR: skor üretilmemeli
        self.assertEqual((0, None), filtreli_skor(False, 0.6, 1.4, 45, 0.5, cfg))
        self.assertEqual((0, None), filtreli_skor(False, 0.6, 1.4, 45, 1.9, cfg))
        # Bant içi ve diğer koşullar sağlanınca SHORT
        skor, yon = filtreli_skor(False, 0.6, 1.4, 45, 1.0, cfg)
        self.assertEqual("SHORT", yon)
        self.assertEqual(4, skor)

    def test_v62_atr_bandini_kapatir(self):
        cfg = v62_cfg()
        skor, yon = filtreli_skor(False, 0.6, 1.4, 45, 1.9, cfg)
        self.assertEqual("SHORT", yon)
        self.assertEqual(4, skor)


class BoyutlandirmaPariteTestleri(unittest.TestCase):
    def setUp(self):
        self._original_cwd = os.getcwd()
        self._temp_dir = tempfile.TemporaryDirectory(prefix="bt-parite-")
        os.chdir(self._temp_dir.name)

    def tearDown(self):
        os.chdir(self._original_cwd)
        self._temp_dir.cleanup()

    def _karsilastir(self, pt, direction, entry, atr):
        levels = pt.akilli_sl_tp_hesapla(None, direction, atr, referans_fiyat=entry)
        canli = pt._pozisyon_boyutlandir(direction, entry, levels)
        motor = boyutlandir(
            direction,
            entry,
            levels["sl"],
            pt._efektif_bakiye_hesapla(),
            pt._toplam_acik_risk(),
            sum(pt._kalan_marjin(p) for p in pt.pozisyonlar),
            config.__dict__,
        )
        if canli is None:
            self.assertIsNone(motor)
            return
        self.assertIsNotNone(motor)
        for anahtar in ("marjin", "notional", "giris_fiyati", "giris_komisyonu"):
            self.assertAlmostEqual(canli[anahtar], motor[anahtar], places=9, msg=anahtar)

    def test_bos_hesapla_ayni(self):
        self._karsilastir(PaperTrade(), "SHORT", 100.0, 1.0)
        self._karsilastir(PaperTrade(), "LONG", 100.0, 1.0)
        self._karsilastir(PaperTrade(), "SHORT", 100.0, 0.4)

    def test_acik_pozisyon_varken_ayni(self):
        pt = PaperTrade()
        self.assertTrue(pt.islem_ac("TESTUSDT", "LONG", 100.0, 1.0, 4))
        self._karsilastir(pt, "SHORT", 50.0, 0.6)


class BarajGenisletmeTestleri(unittest.TestCase):
    def test_barajlar_ve_zaman_olcekli(self):
        temel = varsayilan_cfg()
        iki = genis_cfg(2.0)
        for anahtar in ("SL_ATR", "BE_ATR", "TP_ATR"):
            self.assertAlmostEqual(iki[anahtar], temel[anahtar] * 2, places=9)
        self.assertEqual(temel["ZAMAN_EXIT_SAAT"] * 2, iki["ZAMAN_EXIT_SAAT"])
        # Taban cfg değişmemeli (kopya üzerinde çalışır)
        self.assertAlmostEqual(temel["SL_ATR"], config.SL_ATR, places=9)

    def test_seviyeler_genisliyor(self):
        from backtest.simule import seviyeler

        temel = varsayilan_cfg()
        iki = genis_cfg(2.0)
        a = seviyeler(100.0, "SHORT", 1.0, temel)
        b = seviyeler(100.0, "SHORT", 1.0, iki)
        self.assertAlmostEqual(b["sl"] - 100.0, (a["sl"] - 100.0) * 2, places=9)
        self.assertAlmostEqual(100.0 - b["tp1"], (100.0 - a["tp1"]) * 2, places=9)
        # tp2/tp3 de aynı oranda
        self.assertAlmostEqual(100.0 - b["tp2"], (100.0 - a["tp2"]) * 2, places=9)
        self.assertAlmostEqual(100.0 - b["tp3"], (100.0 - a["tp3"]) * 2, places=9)

    def test_genis_baraj_ayni_barda_daha_az_cakisma(self):
        """Baraj genişledikçe SL ve TP1'in aynı 1h barında çakışma olasılığı düşer."""
        from backtest.simule import seviyeler

        df = pd.DataFrame(
            [
                [None, 100, 100.5, 99.5, 100, 1],
                [None, 100, 102.0, 98.0, 100, 1],
            ],
            columns=["time", "open", "high", "low", "close", "volume"],
        ).assign(time=lambda d: pd.date_range("2026-01-01", periods=len(d), freq="1h"))
        dar = islem_simule(df, 0, "SHORT", 1.0, varsayilan_cfg())
        gen = islem_simule(df, 0, "SHORT", 1.0, genis_cfg(2.0))
        # Dar baraj: SL 101.5 ve TP1 98.8 aynı barda; motor kötümser olarak SL seçer.
        self.assertEqual("STOP", dar["ilk_sebep"])
        # Geniş baraj: SL 103.0 ve TP1 97.6; 98-102 aralığında hiçbiri dokunulmaz.
        self.assertEqual(["VERI_SONU"], gen["sebepler"])
        self.assertFalse(gen["tp1_gordu"])


class BariyerTestleri(unittest.TestCase):
    def _df(self, satirlar):
        return pd.DataFrame(
            satirlar,
            columns=["time", "open", "high", "low", "close", "volume"],
        ).assign(time=lambda d: pd.date_range("2026-01-01", periods=len(d), freq="1h"))

    def test_ayni_barda_sl_once(self):
        df = self._df(
            [
                [None, 100, 100.5, 99.5, 100, 1],
                [None, 100, 102.0, 99.0, 101, 1],
                [None, 101, 101, 96, 97, 1],
            ]
        )
        sim = islem_simule(df, 0, "SHORT", 1.0, varsayilan_cfg())
        self.assertEqual("STOP", sim["ilk_sebep"])
        self.assertFalse(sim["tp1_gordu"])
        self.assertLess(sim["pnl_pct"], 0)

    def test_tp1_sonrasi_be(self):
        df = self._df(
            [
                [None, 100, 100.5, 99.5, 100, 1],
                [None, 100, 100.5, 98.7, 99.5, 1],
                [None, 99.5, 100.2, 99.0, 99.9, 1],
            ]
        )
        sim = islem_simule(df, 0, "SHORT", 1.0, varsayilan_cfg())
        self.assertEqual(["TP1", "BE"], sim["sebepler"])
        self.assertTrue(sim["tp1_gordu"])

    def test_tp3_tam_kapanis(self):
        df = self._df(
            [
                [None, 100, 100.5, 99.5, 100, 1],
                [None, 100, 100.2, 96.5, 97, 1],
            ]
        )
        sim = islem_simule(df, 0, "SHORT", 1.0, varsayilan_cfg())
        self.assertEqual("TP3", sim["sebep"])
        self.assertEqual(["TP1", "TP2", "TP3"], sim["sebepler"])
        self.assertGreater(sim["pnl_pct"], 0)


class MotorTestleri(unittest.TestCase):
    def test_uclu_sembol_uclu_cfg(self):
        veriler = sentetik_veri(3, 900)
        for cfg in (filtersiz_cfg(), v62_cfg(), varsayilan_cfg()):
            motor = Motor(veriler, cfg)
            sonuc = motor.calistir()
            self.assertIn("islem", sonuc)
            self.assertGreaterEqual(sonuc["max_dd"], 0)
            self.assertAlmostEqual(
                sonuc["son_bakiye"], motor.equity[-1]["efektif"], places=6
            )
            for k in motor.kayitlar:
                self.assertIn(k["sebep"], {"TP1", "TP2", "TP3", "STOP", "BE", "ZAMAN"})
                self.assertTrue(np.isfinite(k["pnl"]))
            # Equity eğrisi her 1h barı için bir satır
            self.assertEqual(
                len(motor.equity),
                len({t for df in veriler.values() for t in df["time"]}),
            )

    def test_ozet_bos(self):
        bos = ozet([], [])
        self.assertEqual(0, bos["islem"])
        self.assertEqual(0.0, bos["pnl"])


class DrawdownTestleri(unittest.TestCase):
    def setUp(self):
        self._original_cwd = os.getcwd()
        self._temp_dir = tempfile.TemporaryDirectory(prefix="bt-dd-")
        os.chdir(self._temp_dir.name)

    def tearDown(self):
        os.chdir(self._original_cwd)
        self._temp_dir.cleanup()

    def _pt(self, bakiye, peak):
        pt = PaperTrade()
        pt.pozisyonlar = []
        pt.bakiye = bakiye
        pt.peak_bakiye = peak
        return pt

    def test_canli_drawdown_modlari(self):
        pt = self._pt(100.0, 100.0)
        self.assertEqual("normal", pt.drawdown_durumu())
        pt.bakiye = 83.0  # %17: normal modda histerezis
        self.assertEqual("normal", pt.drawdown_durumu())
        pt.bakiye = 79.0  # %21: kurtarma
        self.assertEqual("kurtarma", pt.drawdown_durumu())
        pt.bakiye = 83.0  # %17: kurtarmada kalır
        self.assertEqual("kurtarma", pt.drawdown_durumu())
        pt.bakiye = 86.0  # %14: normale döner
        self.assertEqual("normal", pt.drawdown_durumu())
        pt.bakiye = 69.0  # %31: durdu
        self.assertEqual("durdu", pt.drawdown_durumu())

    def test_kurtarma_modunda_yarim_risk(self):
        pt = self._pt(790.0, 1000.0)
        self.assertEqual("kurtarma", pt.drawdown_durumu())
        levels = pt.akilli_sl_tp_hesapla(None, "SHORT", 1.0, referans_fiyat=100.0)
        tam = pt._pozisyon_boyutlandir("SHORT", 100.0, levels)
        yarim = pt._pozisyon_boyutlandir(
            "SHORT", 100.0, levels, risk_carpani=0.5
        )
        self.assertAlmostEqual(
            yarim["notional"], tam["notional"] / 2, delta=tam["notional"] * 0.02
        )

    def test_durdu_modunda_giris_yok(self):
        pt = self._pt(69.0, 100.0)
        self.assertFalse(pt.islem_ac("TESTUSDT", "SHORT", 100.0, 1.0, 4))
        self.assertEqual([], pt.pozisyonlar)

    def test_kurtarma_modunda_giris_yarim_riskli(self):
        pt = self._pt(790.0, 1000.0)
        self.assertTrue(pt.islem_ac("TESTUSDT", "SHORT", 100.0, 1.0, 4))
        risk = pt.pozisyonlar[0]["tahmini_stop_riski"]
        self.assertGreater(risk, 790.0 * 0.0035)
        self.assertLess(risk, 790.0 * 0.0055)

    def test_motor_drawdown_modlari(self):
        m = Motor(sentetik_veri(1, 900), varsayilan_cfg())
        m.pozisyonlar = []
        m.bakiye = 100.0
        m.peak = 100.0
        self.assertEqual("normal", m._dd_durumu())
        m.bakiye = 79.0
        self.assertEqual("kurtarma", m._dd_durumu())
        m.bakiye = 83.0
        self.assertEqual("kurtarma", m._dd_durumu())
        m.bakiye = 86.0
        self.assertEqual("normal", m._dd_durumu())
        m.bakiye = 69.0
        self.assertEqual("durdu", m._dd_durumu())

    def test_motor_yarim_risk_boyutlandirma(self):
        cfg = varsayilan_cfg()
        tam = boyutlandir("SHORT", 100.0, 101.5, 1000.0, 0.0, 0.0, cfg)
        yarim = boyutlandir(
            "SHORT", 100.0, 101.5, 1000.0, 0.0, 0.0, cfg, risk_carpani=0.5
        )
        self.assertAlmostEqual(
            yarim["notional"], tam["notional"] / 2, delta=tam["notional"] * 0.02
        )


class AnalizTestleri(unittest.TestCase):
    def test_sinyal_taramasi_ve_kovalar(self):
        veriler = sentetik_veri(3, 900)
        df = sinyal_taramasi(veriler, filtersiz_cfg())
        self.assertFalse(df.empty)
        for kolon in ("pnl_pct", "sebep", "atr_pct", "ema_dist", "tp1_gordu"):
            self.assertIn(kolon, df.columns)
        m = metrikler(df, "test")
        self.assertEqual(len(df), m["n"])
        kovalar = kova_analizi(df)
        self.assertFalse(kovalar.empty)
        self.assertIn("tutarli", kovalar.columns)

    def test_analiz_sinyali_motorla_ayni_esik(self):
        veriler = sentetik_veri(3, 1600, tohum=7)
        df = sinyal_taramasi(veriler, varsayilan_cfg())
        self.assertFalse(df.empty)
        self.assertTrue(((df["atr_pct"] >= config.MIN_ATR_PCT) & (df["atr_pct"] <= config.MAX_ATR_PCT)).all())
        self.assertTrue((df["ema_dist"] >= config.MIN_EMA_DIST).all())
        self.assertTrue((df["vol_ratio"] <= config.MAX_VOL_RATIO).all())


if __name__ == "__main__":
    unittest.main()
