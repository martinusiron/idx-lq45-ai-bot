import tempfile
import unittest
from datetime import datetime

import pandas as pd

from market_session import IDXMarketSession
from risk import RiskEngine
from storage import TradingStorage


class MarketSessionTest(unittest.TestCase):
    def test_lunch_break_detected(self):
        session = IDXMarketSession("Asia/Jakarta")
        dt = session.tz.localize(datetime(2026, 5, 6, 12, 30))
        self.assertEqual(session.get_status(dt), "lunch_break")
        self.assertFalse(session.is_regular_session(dt))


class RiskEngineTest(unittest.TestCase):
    def setUp(self):
        self.engine = RiskEngine(
            account_size=100_000_000,
            risk_per_trade_pct=0.005,
            daily_max_loss_r=1.5,
            max_open_positions=3,
            lot_size=100,
            buy_fee_pct=0.0015,
            sell_fee_pct=0.0025,
            slippage_pct=0.0005,
            partial_exit_ratio=0.5,
            risk_off_mode="reduce",
            risk_off_size_multiplier=0.5,
        )

    def test_plan_position_uses_lot_rounding(self):
        plan, reason = self.engine.plan_position(
            entry=1000,
            stop=970,
            open_positions=0,
            realized_r=0,
            risk_off=False,
        )
        self.assertIsNotNone(plan, reason)
        self.assertEqual(plan.qty % 100, 0)
        self.assertGreater(plan.risk_amount, 0)

    def test_evaluate_trade_unfilled(self):
        idx = pd.date_range("2026-05-08 09:30", periods=3, freq="15min", tz="Asia/Jakarta")
        candles = pd.DataFrame(
            {
                "open": [1010, 1015, 1012],
                "high": [1015, 1016, 1014],
                "low": [1005, 1008, 1007],
                "close": [1012, 1011, 1013],
            },
            index=idx,
        )
        result = self.engine.evaluate_trade(
            candles=candles,
            signal_timestamp="2026-05-08T09:30:00+07:00",
            entry=1000,
            stop=980,
            tp1=1030,
            tp2=1050,
            qty=1000,
            finalize=True,
        )
        self.assertEqual(result["status"], "UNFILLED")
        self.assertEqual(result["pnl_amount"], 0.0)


class StorageTest(unittest.TestCase):
    def test_watchlist_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            storage = TradingStorage(f"{tmp}/journal.db")
            storage.add_watch_symbol("123", "BBCA")
            storage.add_watch_symbol("123", "TLKM")
            self.assertEqual(storage.get_watchlist("123"), ["BBCA", "TLKM"])
            self.assertTrue(storage.remove_watch_symbol("123", "BBCA"))
            self.assertEqual(storage.get_watchlist("123"), ["TLKM"])


if __name__ == "__main__":
    unittest.main()
