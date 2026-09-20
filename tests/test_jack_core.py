import unittest

from backend.jack_core import build_symbol_request, quality_supervisor
from backend.agents.market_capture import MarketCaptureAgent
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

    def test_capture_agent_creates_traceable_valid_run(self):
        rows = [{"open": 100, "high": 101, "low": 99, "close": 100, "volume": 1000}] * 21
        report = MarketCaptureAgent({"www.tsetmc.com"}).capture_snapshot("فملی", {
            "symbol": "فملی", "source": "https://www.tsetmc.com/market", "collected_at": "2026-09-20T12:00:00+03:30",
            "timezone": "Asia/Tehran", "price_unit": "IRR", "price_type": "raw", "timeframe": "daily", "ohlcv": rows,
        })
        self.assertEqual(report["agent"]["name"], "ایجنت دریافت")
        self.assertEqual(report["agent"]["status"], "CAPTURED")
        self.assertTrue(report["agent"]["run_id"].startswith("mca-"))

    def test_capture_agent_blocks_symbol_mismatch(self):
        report = MarketCaptureAgent({"www.tsetmc.com"}).capture_snapshot("فملی", {"symbol": "اهرم"})
        self.assertEqual(report["agent"]["error_code"], "SYMBOL_MISMATCH")

    def test_flat_prices_produce_neutral_rsi(self):
        rows = [{"open": 100, "high": 100, "low": 100, "close": 100, "volume": 1000}] * 21
        report = build_market_report({
            "symbol": "فملی", "source": "https://www.tsetmc.com/market", "collected_at": "2026-09-20T12:00:00+03:30",
            "timezone": "Asia/Tehran", "price_unit": "IRR", "price_type": "raw", "timeframe": "daily", "ohlcv": rows,
        }, {"www.tsetmc.com"})
        rsi = next(item for item in report["symbols"][0]["indicators"] if item["name"] == "RSI")
        self.assertEqual(rsi["parameters"]["value"], 50.0)


if __name__ == "__main__":
    unittest.main()
