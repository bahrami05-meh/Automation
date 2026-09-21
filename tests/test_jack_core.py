import unittest

from backend.jack_core import build_symbol_request, quality_supervisor
from backend.agents.market_capture import MarketCaptureAgent
from backend.agents.technical_analysis import TechnicalAnalysisAgent
from backend.agents.chart_control import ChartControlAgent
from backend.agents.browser_portfolio import BrowserPortfolioAgent
from backend.agents.market_board import MarketBoardAgent
from backend.agents.fundamental import FundamentalAgent
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

    def test_technical_agent_analyzes_valid_capture_without_trade_decision(self):
        rows = [{"open": close - 1, "high": close + 1, "low": close - 2, "close": close, "volume": 1000} for close in range(100, 121)]
        report = build_market_report({
            "symbol": "فملی", "source": "https://www.tsetmc.com/market", "collected_at": "2026-09-20T12:00:00+03:30",
            "timezone": "Asia/Tehran", "price_unit": "IRR", "price_type": "raw", "timeframe": "daily", "ohlcv": rows,
        }, {"www.tsetmc.com"})
        result = TechnicalAnalysisAgent().analyze(report)
        self.assertEqual(result["technical_agent"]["name"], "ایجنت تکنیکال")
        self.assertEqual(result["technical"]["status"], "ANALYZED")
        self.assertEqual(result["technical"]["overall_signal"], "ALIGNED_BULLISH")
        self.assertEqual(result["symbols"][0]["jack_decision"], "WATCHLIST")

    def test_technical_agent_skips_blocked_data(self):
        result = TechnicalAnalysisAgent().analyze(build_symbol_request("اهرم"))
        self.assertEqual(result["technical_agent"]["status"], "SKIPPED")
        self.assertEqual(result["technical"]["overall_signal"], "NOT_AVAILABLE")

    def test_chart_agent_conflict_blocks_jack_decision(self):
        rows = [{"open": close - 1, "high": close + 1, "low": close - 2, "close": close, "volume": 1000} for close in range(100, 121)]
        report = build_market_report({
            "symbol": "فملی", "source": "https://www.tsetmc.com/market", "collected_at": "2026-09-20T12:00:00+03:30",
            "timezone": "Asia/Tehran", "price_unit": "IRR", "price_type": "raw", "timeframe": "daily", "ohlcv": rows,
        }, {"www.tsetmc.com"})
        report = TechnicalAnalysisAgent().analyze(report)
        result = ChartControlAgent({"www.tsetmc.com"}).inspect(report, {
            "symbol": "فملی", "source": "https://www.tsetmc.com/chart", "collected_at": "2026-09-20T12:00:00+03:30",
            "timezone": "Asia/Tehran", "timeframe": "daily",
            "indicators": [{"name": "SMA", "direction": "bearish", "parameters": {"period": 20}}],
        })
        self.assertEqual(result["chart_control_agent"]["status"], "CHART_CONFLICT")
        self.assertEqual(result["symbols"][0]["quality"]["status"], "QA_BLOCKED")
        self.assertEqual(result["symbols"][0]["jack_decision"], "DATA_BLOCKED")

    def test_chart_agent_skips_without_observation(self):
        report = TechnicalAnalysisAgent().analyze(build_symbol_request("اهرم"))
        result = ChartControlAgent({"www.tsetmc.com"}).inspect(report, None)
        self.assertEqual(result["chart_control_agent"]["name"], "ایجنت کنترل نمودار")
        self.assertEqual(result["chart_control"]["status"], "SKIPPED")

    def test_browser_portfolio_agent_captures_visible_rows_without_sensitive_fields(self):
        report = build_symbol_request("فملی")
        result = BrowserPortfolioAgent({"broker.example"}).capture(report, {
            "source": "https://broker.example/portfolio", "collected_at": "2026-09-20T12:00:00+03:30",
            "timezone": "Asia/Tehran", "price_unit": "IRR",
            "holdings": [{"symbol": "فملی", "quantity": 100, "average_price": 1200, "last_price": 1300, "market_value": 130000}],
        })
        self.assertEqual(result["browser_portfolio_agent"]["status"], "PORTFOLIO_CAPTURED")
        self.assertEqual(result["portfolio_capture"]["holdings_count"], 1)

    def test_browser_portfolio_agent_blocks_sensitive_fields(self):
        result = BrowserPortfolioAgent({"broker.example"}).capture(build_symbol_request("فملی"), {
            "source": "https://broker.example/portfolio", "collected_at": "2026-09-20T12:00:00+03:30",
            "timezone": "Asia/Tehran", "price_unit": "IRR", "token": "not-allowed",
            "holdings": [{"symbol": "فملی", "quantity": 100, "average_price": 1200, "last_price": 1300, "market_value": 130000}],
        })
        self.assertEqual(result["browser_portfolio_agent"]["status"], "PORTFOLIO_BLOCKED")

    def test_market_board_agent_observes_valid_open_market_data(self):
        rows = [{"open": close - 1, "high": close + 1, "low": close - 2, "close": close, "volume": 1000} for close in range(100, 121)]
        report = build_market_report({
            "symbol": "فملی", "source": "https://www.tsetmc.com/market", "collected_at": "2026-09-21T11:40:00+03:30",
            "timezone": "Asia/Tehran", "price_unit": "IRR", "price_type": "raw", "timeframe": "daily", "ohlcv": rows,
        }, {"www.tsetmc.com"})
        result = MarketBoardAgent({"www.tsetmc.com"}).inspect(report, {
            "symbol": "فملی", "source": "https://www.tsetmc.com/board", "collected_at": "2026-09-21T11:40:00+03:30",
            "timezone": "Asia/Tehran", "price_unit": "IRR", "market_status": "open", "last_price": 120,
            "volume": 1500, "average_volume_20": 1000, "individual_buy_volume": 800, "individual_sell_volume": 500,
            "legal_buy_volume": 200, "legal_sell_volume": 400, "buy_queue_value": 300000, "sell_queue_value": 100000,
        })
        self.assertEqual(result["market_board_agent"]["status"], "OBSERVED")
        self.assertEqual(result["market_board"]["metrics"]["volume_state"], "ABOVE_AVERAGE")
        self.assertEqual(result["market_board"]["metrics"]["queue_state"], "BUY_QUEUE_DOMINANT")

    def test_market_board_agent_blocks_suspended_symbol(self):
        rows = [{"open": close - 1, "high": close + 1, "low": close - 2, "close": close, "volume": 1000} for close in range(100, 121)]
        report = build_market_report({
            "symbol": "فملی", "source": "https://www.tsetmc.com/market", "collected_at": "2026-09-21T11:40:00+03:30",
            "timezone": "Asia/Tehran", "price_unit": "IRR", "price_type": "raw", "timeframe": "daily", "ohlcv": rows,
        }, {"www.tsetmc.com"})
        result = MarketBoardAgent({"www.tsetmc.com"}).inspect(report, {
            "symbol": "فملی", "source": "https://www.tsetmc.com/board", "collected_at": "2026-09-21T11:40:00+03:30",
            "timezone": "Asia/Tehran", "price_unit": "IRR", "market_status": "suspended", "last_price": 120,
            "volume": 0, "average_volume_20": 1000, "individual_buy_volume": 0, "individual_sell_volume": 0,
            "legal_buy_volume": 0, "legal_sell_volume": 0, "buy_queue_value": 0, "sell_queue_value": 0,
        })
        self.assertEqual(result["market_board_agent"]["status"], "MARKET_SUSPENDED")
        self.assertEqual(result["symbols"][0]["quality"]["status"], "QA_BLOCKED")
        self.assertEqual(result["symbols"][0]["jack_decision"], "DATA_BLOCKED")

    def test_fundamental_agent_observes_official_data_without_trade_decision(self):
        rows = [{"open": close - 1, "high": close + 1, "low": close - 2, "close": close, "volume": 1000} for close in range(100, 121)]
        report = build_market_report({
            "symbol": "فملی", "source": "https://www.tsetmc.com/market", "collected_at": "2026-09-21T11:40:00+03:30",
            "timezone": "Asia/Tehran", "price_unit": "IRR", "price_type": "raw", "timeframe": "daily", "ohlcv": rows,
        }, {"www.tsetmc.com"})
        result = FundamentalAgent({"www.codal.ir"}).inspect(report, {
            "symbol": "فملی", "source": "https://www.codal.ir/report", "collected_at": "2026-09-21T11:40:00+03:30",
            "timezone": "Asia/Tehran", "fiscal_year_end": "1405/12/29", "financial_unit": "IRR",
            "revenue": 1000, "net_profit": 200, "operating_margin_percent": 25, "price_to_earnings": 6.2,
            "debt_to_equity": 0.8, "events": [{"event_type": "financial_statement", "published_at": "2026-09-20T10:00:00+03:30"}],
        })
        self.assertEqual(result["fundamental_agent"]["status"], "OBSERVED")
        self.assertEqual(result["fundamental"]["metrics"]["net_margin_percent"], 20.0)
        self.assertEqual(result["symbols"][0]["jack_decision"], "WATCHLIST")

    def test_fundamental_agent_blocks_unapproved_source(self):
        rows = [{"open": close - 1, "high": close + 1, "low": close - 2, "close": close, "volume": 1000} for close in range(100, 121)]
        report = build_market_report({
            "symbol": "فملی", "source": "https://www.tsetmc.com/market", "collected_at": "2026-09-21T11:40:00+03:30",
            "timezone": "Asia/Tehran", "price_unit": "IRR", "price_type": "raw", "timeframe": "daily", "ohlcv": rows,
        }, {"www.tsetmc.com"})
        result = FundamentalAgent({"www.codal.ir"}).inspect(report, {
            "symbol": "فملی", "source": "https://example.com/report", "collected_at": "2026-09-21T11:40:00+03:30",
            "timezone": "Asia/Tehran", "fiscal_year_end": "1405/12/29", "financial_unit": "IRR",
            "revenue": 1000, "net_profit": 200, "operating_margin_percent": 25, "price_to_earnings": 6.2,
            "debt_to_equity": 0.8, "events": [],
        })
        self.assertEqual(result["fundamental_agent"]["status"], "FUNDAMENTAL_BLOCKED")
        self.assertEqual(result["symbols"][0]["quality"]["status"], "QA_BLOCKED")


if __name__ == "__main__":
    unittest.main()
