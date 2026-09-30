"""Time policy, specialist rejection and final handoff regression coverage."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import unittest
from unittest.mock import patch

from backend.freshness import MAX_AGES, validate_collected_at
from backend.market_data import build_market_report
from backend.agents.technical_analysis import TechnicalAnalysisAgent
from backend.agents.chart_control import ChartControlAgent
from backend.agents.market_board import MarketBoardAgent
from backend.agents.fundamental import FundamentalAgent
from backend.agents.browser_portfolio import BrowserPortfolioAgent
from backend.agents.quality_supervisor import QualitySupervisorAgent
import test_critical_regressions as regressions

snapshot = regressions.snapshot
fundamental = regressions.fundamental

NOW = datetime.fromisoformat("2026-09-28T12:00:00+03:30")


def portfolio():
    return {"source": "https://broker.example/portfolio", "collected_at": NOW.isoformat(),
            "timezone": "Asia/Tehran", "price_unit": "IRR", "holdings": [
                {"symbol": "TEST", "quantity": 100, "average_price": 100,
                 "last_price": 120, "market_value": 12000}]}


def board():
    return {"symbol": "TEST", "source": "https://www.tsetmc.com/board", "collected_at": NOW.isoformat(),
            "timezone": "Asia/Tehran", "price_unit": "IRR", "market_status": "open",
            "last_price": 120, "volume": 1000, "average_volume_20": 1000,
            "individual_buy_volume": 300, "individual_sell_volume": 300,
            "legal_buy_volume": 700, "legal_sell_volume": 700,
            "buy_queue_value": 0, "sell_queue_value": 0}


class ObservationFreshnessTests(unittest.TestCase):
    def setUp(self):
        self.clock = patch("backend.freshness.utc_now", return_value=NOW)
        self.mock_clock = self.clock.start()
        self.addCleanup(self.clock.stop)

    def report(self):
        return TechnicalAnalysisAgent().analyze(build_market_report(snapshot()))

    def test_policy_boundaries_and_offset_normalization(self):
        for kind, age in MAX_AGES.items():
            with self.subTest(kind=kind):
                validate_collected_at((NOW - age).isoformat(), kind)
                with self.assertRaisesRegex(ValueError, "COLLECTION_TIME_STALE"):
                    validate_collected_at((NOW - age - timedelta(microseconds=1)).isoformat(), kind)
                validate_collected_at((NOW + timedelta(minutes=5)).isoformat(), kind)
                with self.assertRaisesRegex(ValueError, "COLLECTION_TIME_FUTURE"):
                    validate_collected_at((NOW + timedelta(minutes=5, microseconds=1)).isoformat(), kind)
        normalized = validate_collected_at(NOW.astimezone(timezone.utc).isoformat(), "portfolio")
        self.assertEqual(normalized.isoformat(), NOW.isoformat())
        for value in (None, "invalid", "2026-09-28T12:00:00"):
            with self.assertRaises(ValueError):
                validate_collected_at(value, "board")

    def test_all_specialists_reject_stale_future_naive_and_missing_times(self):
        chart = {"symbol": "TEST", "source": "https://www.tsetmc.com/chart", "collected_at": NOW.isoformat(),
                 "timezone": "Asia/Tehran", "timeframe": "daily",
                 "indicators": [{"name": "SMA", "direction": "bullish", "parameters": {"period": 20}}]}
        cases = [(FundamentalAgent({"www.codal.ir"}), "inspect", fundamental(), "fundamental", "FUNDAMENTAL_BLOCKED"),
                 (MarketBoardAgent({"www.tsetmc.com"}), "inspect", board(), "market_board", "BOARD_BLOCKED"),
                 (ChartControlAgent({"www.tsetmc.com"}), "inspect", chart, "chart_control", "CHART_BLOCKED"),
                 (BrowserPortfolioAgent({"broker.example"}), "capture", portfolio(), "portfolio_capture", "PORTFOLIO_BLOCKED")]
        for agent, method, observation, key, status in cases:
            for value in ((NOW - timedelta(days=10)).isoformat(), (NOW + timedelta(hours=1)).isoformat(), "2026-09-28T12:00:00", None):
                with self.subTest(key=key, value=value):
                    data = deepcopy(observation)
                    data["collected_at"] = value
                    report = getattr(agent, method)(self.report(), data)
                    self.assertEqual(report[key]["status"], status)
                    self.assertEqual(report["symbols"][0]["jack_decision"], "DATA_BLOCKED")
                    self.assertEqual(QualitySupervisorAgent().inspect(report)["quality_supervisor"]["status"], "QA_BLOCKED")

    def test_current_specialists_preserve_valid_results(self):
        report = self.report()
        report = MarketBoardAgent({"www.tsetmc.com"}).inspect(report, board())
        report = FundamentalAgent({"www.codal.ir"}).inspect(report, fundamental())
        report = BrowserPortfolioAgent({"broker.example"}).capture(report, portfolio())
        report = QualitySupervisorAgent().inspect(report)
        self.assertEqual(report["quality_supervisor"]["status"], "QA_PASSED")
        self.assertEqual(report["portfolio_capture"]["status"], "PORTFOLIO_CAPTURED")

    def test_expiration_after_capture_blocks_final_handoff(self):
        report = BrowserPortfolioAgent({"broker.example"}).capture(self.report(), portfolio())
        self.mock_clock.return_value = NOW + timedelta(minutes=16)
        report = QualitySupervisorAgent().inspect(report)
        self.assertEqual(report["quality_supervisor"]["status"], "QA_BLOCKED")
        self.assertTrue(any(f.get("source_kind") == "portfolio" for f in report["quality_supervisor"]["findings"]))

    def test_final_review_rejects_stale_or_missing_market_metadata(self):
        for value in ((NOW - timedelta(days=8)).isoformat(), None):
            report = self.report()
            report["symbols"][0]["market_metadata"]["collected_at"] = value
            self.assertEqual(QualitySupervisorAgent().inspect(report)["quality_supervisor"]["status"], "QA_BLOCKED")

    def test_direct_report_cannot_disable_freshness(self):
        data = snapshot()
        data["collected_at"] = (NOW - timedelta(days=8)).isoformat()
        with self.assertRaisesRegex(ValueError, "COLLECTION_TIME_STALE"):
            build_market_report(data)
        with self.assertRaisesRegex(ValueError, "FRESHNESS_CHECK_REQUIRED"):
            build_market_report(snapshot(), enforce_freshness=False)


class PortfolioHttpFreshnessTests(unittest.TestCase):
    setUp = regressions.HttpRegressionTests.setUp
    post = regressions.HttpRegressionTests.post
    tearDownClass = classmethod(regressions.HttpRegressionTests.tearDownClass.__func__)

    @classmethod
    def setUpClass(cls):
        regressions.HttpRegressionTests.setUpClass.__func__(cls)
        cls.server.allowed_brokerage_hosts = {"broker.example"}
        cls.server.browser_portfolio_agent = BrowserPortfolioAgent({"broker.example"})

    def test_stale_portfolio_is_rejected_before_final_quality(self):
        data = snapshot()
        data["portfolio_observation"] = portfolio() | {"collected_at": (NOW - timedelta(minutes=16)).isoformat()}
        status, result = self.post(data)
        self.assertEqual(status, 200)
        self.assertEqual(result["portfolio_capture"]["status"], "PORTFOLIO_BLOCKED")
        self.assertEqual(result["quality_supervisor"]["status"], "QA_BLOCKED")
        self.assertEqual(result["agents"][-1]["id"], "quality-supervisor-agent")

    def test_current_portfolio_passes_final_quality(self):
        data = snapshot() | {"portfolio_observation": portfolio()}
        status, result = self.post(data)
        self.assertEqual(status, 200)
        self.assertEqual(result["portfolio_capture"]["status"], "PORTFOLIO_CAPTURED")
        self.assertEqual(result["quality_supervisor"]["status"], "QA_PASSED")
        self.assertEqual(result["agents"][-1]["id"], "quality-supervisor-agent")
