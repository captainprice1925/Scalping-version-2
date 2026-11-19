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
