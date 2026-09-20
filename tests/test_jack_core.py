import unittest

from backend.jack_core import build_symbol_request, quality_supervisor


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


if __name__ == "__main__":
    unittest.main()
