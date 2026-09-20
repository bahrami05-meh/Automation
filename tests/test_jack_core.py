import unittest

from backend.jack_core import build_symbol_request, quality_supervisor
from backend.market_data import build_market_report


class QualitySupervisorTests(unittest.TestCase):
    def test_overlap_is_capped_without_blocking(self):
        result = quality_supervisor([
            {"name": "RSI", "family": "momentum", "timeframe": "daily", "direction": "bullish", "weight": 2},
            {"name": "MACD", "family": "momentum", "timeframe": "daily", "direction": "bullish", "weight": 2},
        ])
        self.assertEqual(result["status"], "QA_PASSED")
        self.assertEqual(result["score"], 2.0)
        self.assertIn("INDICATOR_OVERLAP", [item["code"] for item in result["findings"]])

    def test_conflict_blocks_handoff_to_jack(self):
        result = quality_supervisor([
            {"name": "RSI", "family": "momentum", "timeframe": "daily", "direction": "bullish", "weight": 2},
            {"name": "MACD", "family": "momentum", "timeframe": "daily", "direction": "bearish", "weight": 2},
        ])
        self.assertEqual(result["status"], "QA_BLOCKED")
        self.assertIn("INDICATOR_CONFLICT", [item["code"] for item in result["findings"]])

    def test_missing_indicator_input_blocks_quality(self):
        result = quality_supervisor([{"name": "RSI"}])
        self.assertEqual(result["status"], "QA_BLOCKED")
        self.assertIn("INDICATOR_INVALID", [item["code"] for item in result["findings"]])

    def test_symbol_request_is_blocked_until_market_data_exists(self):
        result = build_symbol_request("فولاد")
        self.assertEqual(result["symbols"][0]["symbol"], "فولاد")
        self.assertEqual(result["symbols"][0]["jack_decision"], "DATA_BLOCKED")

    def test_invalid_symbol_is_rejected(self):
        with self.assertRaises(ValueError):
            build_symbol_request("<script>")

    def test_market_snapshot_runs_local_quality_check(self):
        closes = list(range(100, 121))
        rows = [{"open": close - 1, "high": close + 1, "low": close - 2, "close": close, "volume": 1000} for close in closes]
        report = build_market_report({
            "symbol": "فملی", "source": "https://www.tsetmc.com/market", "collected_at": "2026-09-20T12:00:00+03:30",
            "timezone": "Asia/Tehran", "price_unit": "IRR", "price_type": "raw", "timeframe": "daily", "ohlcv": rows,
        }, {"www.tsetmc.com"})
        self.assertEqual(report["symbols"][0]["data_status"], "VALID")
        self.assertEqual(report["symbols"][0]["jack_decision"], "WATCHLIST")

    def test_unapproved_market_host_is_rejected(self):
        rows = [{"open": 1, "high": 2, "low": 1, "close": 2, "volume": 1}] * 21
        with self.assertRaises(ValueError):
            build_market_report({
                "symbol": "فملی", "source": "https://example.com/market", "collected_at": "2026-09-20T12:00:00+03:30",
                "timezone": "Asia/Tehran", "price_unit": "IRR", "price_type": "raw", "timeframe": "daily", "ohlcv": rows,
            }, {"www.tsetmc.com"})


if __name__ == "__main__":
    unittest.main()
