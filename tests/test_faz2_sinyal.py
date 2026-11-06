# -*- coding: utf-8 -*-
"""V6.2 giriş rejimi filtresi testleri (calculate_score_fatih sert eleme)."""
import sys
import unittest
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

import config
from faz2_sinyal import calculate_score_fatih


def _df_4h(kapanis, ema_200, n=210):
    return pd.DataFrame(
        {
            "close": [kapanis] * n,
            "ema_200": [ema_200] * n,
        }
    )


def _df_1h(kapanis, ema_21, rsi, volume_ratio, n=60):
    return pd.DataFrame(
        {
            "close": [kapanis] * n,
            "ema_21": [ema_21] * n,
            "rsi": [rsi] * n,
            "volume_ratio": [volume_ratio] * n,
        }
    )


class GirisRejimiFiltreTests(unittest.TestCase):
    def test_ema_cok_yakin_giris_eleme(self):
        # Downtrend, RSI ve hacim uygun ama fiyat EMA21'e çok yakın (0.2%)
        df_4h = _df_4h(kapanis=100.0, ema_200=110.0)     # short trend
        df_1h = _df_1h(kapanis=100.0, ema_21=100.2, rsi=42.0, volume_ratio=1.5)
        skor, yon = calculate_score_fatih(df_4h, df_1h)
        self.assertEqual(0, skor)
        self.assertIsNone(yon)

    def test_hacim_patlamasi_girisi_eleme(self):
        # ema_dist uygun (0.5%) ama hacim patlaması > 1.8
        df_4h = _df_4h(kapanis=100.0, ema_200=110.0)
        df_1h = _df_1h(kapanis=100.0, ema_21=100.5, rsi=42.0, volume_ratio=2.5)
        skor, yon = calculate_score_fatih(df_4h, df_1h)
        self.assertEqual(0, skor)
        self.assertIsNone(yon)

    def test_gecerli_short_gecis(self):
        # ema_dist 0.5% (0.45-0.8 bandı), hacim 1.5 (1.3-1.8 bandı), RSI 42
        df_4h = _df_4h(kapanis=100.0, ema_200=110.0)
        df_1h = _df_1h(kapanis=100.0, ema_21=100.5, rsi=42.0, volume_ratio=1.5)
        skor, yon = calculate_score_fatih(df_4h, df_1h)
        self.assertEqual(4, skor)
        self.assertEqual("SHORT", yon)

    def test_gecerli_long_gecis(self):
        # Uptrend (4h > ema_200), RSI 55, ayni bantlar
        df_4h = _df_4h(kapanis=110.0, ema_200=100.0)
        df_1h = _df_1h(kapanis=100.0, ema_21=100.5, rsi=55.0, volume_ratio=1.5)
        skor, yon = calculate_score_fatih(df_4h, df_1h)
        self.assertEqual(4, skor)
        self.assertEqual("LONG", yon)

    def test_hacim_alt_sinir_victa_calisir(self):
        # hacim 1.25 < 1.3: vol puanı gelmez, skor 3 -> giriş yok (MIN_SKOR 4)
        df_4h = _df_4h(kapanis=100.0, ema_200=110.0)
        df_1h = _df_1h(kapanis=100.0, ema_21=100.5, rsi=42.0, volume_ratio=1.25)
        skor, yon = calculate_score_fatih(df_4h, df_1h)
        self.assertEqual(3, skor)
        self.assertIsNone(yon)


if __name__ == "__main__":
    unittest.main()
