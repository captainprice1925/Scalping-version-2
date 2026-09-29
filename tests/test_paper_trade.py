import json
import os
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

import config
import telegram_komut
from paper_trade import PaperTrade


class PaperTradeRiskTests(unittest.TestCase):
    def setUp(self):
        self._original_cwd = os.getcwd()
        self._temp_dir = tempfile.TemporaryDirectory(prefix="scalping-v6-test-")
        os.chdir(self._temp_dir.name)
        self.frame = pd.DataFrame(
            [
                {
                    "time": pd.Timestamp("2026-09-23T00:00:00"),
                    "open": 100.0,
                    "high": 100.0,
                    "low": 100.0,
                    "close": 100.0,
                    "volume": 1.0,
                }
            ]
        )

    def tearDown(self):
        os.chdir(self._original_cwd)
        self._temp_dir.cleanup()

    def open_long(self, symbol="TESTUSDT", atr=1.0):
        trade = PaperTrade()
        self.assertTrue(trade.islem_ac(symbol, "LONG", 100.0, atr, 3, self.frame))
        return trade

    def test_standard_one_percent_risk_sizes_position_from_stop_and_costs(self):
        trade = self.open_long()
        position = trade.pozisyonlar[0]

        self.assertGreater(position["miktar"], config.MIN_ISLEM_MARJINI)
        self.assertLess(position["miktar"], config.MAX_ISLEM_MARJINI)
        self.assertAlmostEqual(
            trade.tahmini_stop_riski(position, acilis_komisyonu_dahil=True),
            config.BUTCE_SANAL * config.RISK_YUZDE_ISLEM,
            places=6,
        )
        self.assertAlmostEqual(
            trade.bakiye,
            config.BUTCE_SANAL - position["miktar"] - position["giris_komisyonu"],
            places=8,
        )

    def test_total_open_stop_risk_is_capped_at_two_percent(self):
        trade = self.open_long("ONEUSDT")
        self.assertTrue(trade.islem_ac("TWOUSDT", "LONG", 100.0, 1.0, 3, self.frame))

        self.assertLessEqual(
            trade._toplam_acik_risk(),
            trade._efektif_bakiye_hesapla() * config.MAX_TOPLAM_RISK_YUZDE + 1e-8,
        )
        self.assertFalse(trade.islem_ac("THREEUSDT", "LONG", 100.0, 1.0, 3, self.frame))

    def test_tp3_cross_processes_tp1_tp2_and_tp3_in_order(self):
        trade = self.open_long()
        trade.pozisyon_guncelle("TESTUSDT", 100.0, 103.0, 100.0, 102.7)

        self.assertEqual([], trade.pozisyonlar)
        self.assertEqual(["TP1", "TP2", "TP3"], [x["sebep"] for x in trade.islem_gecmisi])
        self.assertEqual([40, 30, 30], [x["yuzde"] for x in trade.islem_gecmisi])

    def test_pre_entry_bar_does_not_change_position(self):
        trade = self.open_long()
        before_open = datetime.now() - timedelta(minutes=10)
        old_bar = pd.DataFrame(
            [
                {
                    "time": pd.Timestamp(before_open),
                    "open": 100.0,
                    "high": 103.0,
                    "low": 100.0,
                    "close": 102.7,
                    "volume": 1.0,
                }
            ]
        )

        trade.pozisyon_bars_guncelle("TESTUSDT", old_bar)

        self.assertEqual(1, len(trade.pozisyonlar))
        self.assertEqual([], trade.islem_gecmisi)

    def test_forming_bar_is_reprocessed_until_closed(self):
        trade = self.open_long()
        base = datetime.now() + timedelta(seconds=5)

        forming = pd.DataFrame(
            [
                {
                    "time": pd.Timestamp(base),
                    "open": 100.2,
                    "high": 100.5,
                    "low": 100.1,
                    "close": 100.4,
                    "volume": 1.0,
                }
            ]
        )
        # İlk tur: mum henüz oluşuyor; hiçbir seviyeye dokunulmadı.
        trade.pozisyon_bars_guncelle("TESTUSDT", forming)
        self.assertEqual(1, len(trade.pozisyonlar))
        self.assertEqual([], trade.islem_gecmisi)

        # Aynı mum kapanmış halde geri gelir: dip SL'in altına inmiş.
        closed = pd.DataFrame(
            [
                {
                    "time": pd.Timestamp(base),
                    "open": 100.2,
                    "high": 100.5,
                    "low": 98.0,
                    "close": 98.3,
                    "volume": 1.0,
                },
                {
                    "time": pd.Timestamp(base + timedelta(minutes=1)),
                    "open": 98.3,
                    "high": 99.8,
                    "low": 99.1,
                    "close": 99.6,
                    "volume": 1.0,
                },
            ]
        )
        trade.pozisyon_bars_guncelle("TESTUSDT", closed)

        self.assertEqual([], trade.pozisyonlar)
        self.assertEqual("STOP", trade.islem_gecmisi[-1]["sebep"])
        self.assertAlmostEqual(
            trade.islem_gecmisi[-1]["exit"],
            98.5 * (1 - config.CIKIS_SLIPPAGE_ORANI),
            places=8,
        )

        # Aynı mumun yeniden gönderilmesi çift işlem üretmez.
        trade.pozisyon_bars_guncelle("TESTUSDT", closed)
        self.assertEqual(1, len(trade.islem_gecmisi))

    def test_funding_is_applied_once_and_positive_rate_costs_long(self):
        trade = self.open_long()
        position = trade.pozisyonlar[0]
        opened_at = int(datetime.fromisoformat(position["acilis_zamani"]).timestamp() * 1000)
        opening_cash = trade.bakiye
        event = {"timestamp": opened_at + 60_000, "rate": 0.001}

        trade.fonlama_uygula("TESTUSDT", [event])
        first_cash = trade.bakiye
        trade.fonlama_uygula("TESTUSDT", [event])

        expected_funding = (
            -position["notional"]
            * position["son_fiyat"]
            / position["giris_fiyat"]
            * event["rate"]
        )
        self.assertAlmostEqual(first_cash - opening_cash, expected_funding, places=8)
        self.assertAlmostEqual(trade.bakiye, first_cash, places=8)
        self.assertEqual(1, len([x for x in trade.islem_gecmisi if x["sebep"] == "FONLAMA"]))

    def test_telegram_summary_includes_open_position(self):
        trade = self.open_long()
        metin = telegram_komut.ozet_mesaji(trade)

        self.assertIn("TESTUSDT", metin)
        self.assertIn("SL 98.5", metin)
        self.assertIn("Nakit", metin)

    def test_telegram_unknown_command(self):
        self.assertIsNone(telegram_komut.komut_isle("merhaba", None))
        cevap = telegram_komut.komut_isle("/bilinmeyen", None)
        self.assertIn("/yardim", cevap)

    def test_telegram_error_log_records(self):
        telegram_komut._hata_gecmisi.clear()
        telegram_komut.hata_ekle("test-kaynak", "bir hata")
        metin = telegram_komut.hata_mesaji()
        self.assertIn("test-kaynak", metin)

    def test_liquidation_safety_filter(self):
        trade = PaperTrade()
        with patch.object(config, "KALDIRAC", 50):
            guvenli, likidasyon = trade._stop_likidasyon_guvenli_mi(
                {"sl": 98.4}, 100.0, "LONG"
            )
            self.assertFalse(guvenli)
            self.assertAlmostEqual(likidasyon, 98.0, places=8)
            guvenli2, _ = trade._stop_likidasyon_guvenli_mi(
                {"sl": 98.6}, 100.0, "LONG"
            )
            self.assertTrue(guvenli2)

    def test_old_state_migration_fills_v6_fields(self):
        old_state = {
            "bakiye": 95.0,
            "pozisyonlar": [
                {
                    "symbol": "OLDUSDT",
                    "direction": "LONG",
                    "entry": 1.0,
                    "atr": 0.01,
                    "sl": 0.985,
                    "tp1": 1.012,
                    "tp2": 1.0189,
                    "tp3": 1.027,
                    "rr": 1.8,
                    "skor": 3,
                    "miktar": 10,
                    "acilis_zamani": "2026-09-29T20:00:00",
                    "tp1_tetiklendi": False,
                    "tp2_tetiklendi": False,
                    "kalan_yuzde": 100,
                    "son_islenen_bar": None,
                }
            ],
            "islem_gecmisi": [],
            "cooldown": {},
            "gun_baslangic_bakiye": 100,
            "gun_tarihi": "2026-09-29",
            "gunluk_limit_asildi": False,
            "gunluk_gerceklesen_pnl": 0,
            "peak_bakiye": 100,
            "drawdown_limit_asildi": False,
        }
        with open("scalp_bot_state.json", "w", encoding="utf-8") as file:
            json.dump(old_state, file)

        trade = PaperTrade()
        pozisyon = trade.pozisyonlar[0]
        self.assertEqual(pozisyon["notional"], 10 * config.KALDIRAC)
        self.assertEqual(pozisyon["giris_fiyat"], 1.0)
        self.assertEqual(pozisyon["giris_komisyonu"], 0.0)
        self.assertEqual(pozisyon["son_fiyat"], 1.0)
        self.assertIsNone(pozisyon["tahmini_likidasyon"])
        self.assertIsNone(pozisyon["son_fonlama_zamani"])

    def test_partial_tp_then_breakeven_stop(self):
        trade = self.open_long()
        trade.pozisyon_guncelle("TESTUSDT", 100.2, 101.3, 100.1, 101.2)
        self.assertEqual(60, trade.pozisyonlar[0]["kalan_yuzde"])
        self.assertEqual(100.0, trade.pozisyonlar[0]["sl"])

        trade.pozisyon_guncelle("TESTUSDT", 101.0, 101.0, 99.9, 99.95)
        self.assertEqual([], trade.pozisyonlar)
        self.assertEqual(["TP1", "BE"], [x["sebep"] for x in trade.islem_gecmisi])

    def test_drawdown_limit_blocks_and_resets(self):
        trade = PaperTrade()
        trade.peak_bakiye = 100.0
        trade.bakiye = 79.0
        self.assertTrue(trade._max_drawdown_kontrol())
        self.assertTrue(trade.drawdown_limit_asildi)

        trade.bakiye = 90.0
        self.assertFalse(trade._max_drawdown_kontrol())
        self.assertFalse(trade.drawdown_limit_asildi)

    def test_wsgi_starts_the_single_bot_thread_entrypoint(self):
        sys.modules.pop("wsgi", None)
        with patch("app.start_bot") as start_bot:
            __import__("wsgi")
        start_bot.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
