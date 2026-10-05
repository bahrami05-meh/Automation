import unittest

from backend.portfolio_summary import summarize_portfolio


class PortfolioSummaryTests(unittest.TestCase):
    def test_reports_value_weights_and_estimated_unrealized_results(self):
        summary = summarize_portfolio([
            {"symbol": "AAA", "quantity": 10, "average_price": 100, "last_price": 125, "market_value": 1300},
            {"symbol": "BBB", "quantity": 5, "average_price": 200, "last_price": 180, "market_value": 900},
        ])
        self.assertEqual(summary["reported_total_market_value"], 2200.0)
        self.assertEqual(summary["estimated_total_cost_basis"], 2000.0)
        self.assertEqual(summary["estimated_unrealized_pnl"], 150.0)
        self.assertEqual(summary["estimated_return_percent"], 7.5)
        self.assertEqual(summary["top_five_concentration_percent"], 100.0)
        self.assertEqual(summary["positions"], [
            {"symbol": "AAA", "market_value_weight_percent": 59.09, "estimated_cost_basis": 1000.0,
             "estimated_unrealized_pnl": 250.0, "estimated_return_percent": 25.0},
            {"symbol": "BBB", "market_value_weight_percent": 40.91, "estimated_cost_basis": 1000.0,
             "estimated_unrealized_pnl": -100.0, "estimated_return_percent": -10.0},
        ])

    def test_zero_market_value_and_zero_cost_have_no_divide_by_zero_metrics(self):
        summary = summarize_portfolio([
            {"symbol": "AAA", "quantity": 0, "average_price": 0, "last_price": 0, "market_value": 0},
        ])
        self.assertIsNone(summary["top_five_concentration_percent"])
        self.assertIsNone(summary["estimated_return_percent"])
        self.assertIsNone(summary["positions"][0]["market_value_weight_percent"])
        self.assertIsNone(summary["positions"][0]["estimated_return_percent"])

    def test_top_five_concentration_uses_five_largest_reported_values(self):
        holdings = [
            {"symbol": f"S{i}", "quantity": 1, "average_price": 1, "last_price": 1, "market_value": value}
            for i, value in enumerate((600, 500, 400, 300, 200, 100))
        ]
        summary = summarize_portfolio(holdings)
        self.assertEqual(summary["top_five_concentration_percent"], 95.24)

    def test_rejects_duplicate_symbols_and_nonfinite_or_negative_values(self):
        holding = {"symbol": "AAA", "quantity": 1, "average_price": 1, "last_price": 1, "market_value": 1}
        with self.assertRaisesRegex(ValueError, "PORTFOLIO_SUMMARY_SYMBOL_INVALID"):
            summarize_portfolio([holding, holding.copy()])
        bad = holding | {"last_price": float("inf")}
        with self.assertRaisesRegex(ValueError, "PORTFOLIO_SUMMARY_INVALID_LAST_PRICE"):
            summarize_portfolio([bad])
        negative = holding | {"quantity": -1}
        with self.assertRaisesRegex(ValueError, "PORTFOLIO_SUMMARY_NEGATIVE_VALUE"):
            summarize_portfolio([negative])


if __name__ == "__main__":
    unittest.main()
