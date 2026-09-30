"""Regression coverage for the three high priority audit findings."""
import http.client
import json
import threading
import unittest
from datetime import datetime
from unittest.mock import patch
from http.server import ThreadingHTTPServer

from backend.agents.market_capture import MarketCaptureAgent
from backend.agents.technical_analysis import TechnicalAnalysisAgent
from backend.agents.chart_control import ChartControlAgent
from backend.agents.market_board import MarketBoardAgent
from backend.agents.fundamental import FundamentalAgent
from backend.agents.portfolio_risk import PortfolioRiskAgent
from backend.agents.quality_supervisor import QualitySupervisorAgent
from backend.agents.browser_portfolio import BrowserPortfolioAgent
from backend.jack_core import quality_supervisor
from backend.market_data import build_market_report
from backend.numeric import finite_number
from backend.server import JackHandler, configure_browser_nonces


def snapshot():
    return {"symbol": "TEST", "source": "https://www.tsetmc.com/market",
            "collected_at": "2026-09-28T12:00:00+03:30", "timezone": "Asia/Tehran",
            "price_unit": "IRR", "price_type": "raw", "timeframe": "daily",
            "ohlcv": [{"open": x, "high": x + 2, "low": x - 1,
                       "close": x + 1, "volume": 1000} for x in range(100, 121)]}


def fundamental():
    return {"symbol": "TEST", "source": "https://www.codal.ir/report",
            "collected_at": "2026-09-28T12:00:00+03:30", "timezone": "Asia/Tehran",
            "fiscal_year_end": "1405/12/29", "financial_unit": "IRR",
            "revenue": 1000, "net_profit": 200, "operating_margin_percent": 25,
            "price_to_earnings": 6.2, "debt_to_equity": 0.8, "events": []}


class CriticalRegressionTests(unittest.TestCase):
    def setUp(self):
        clock = patch("backend.freshness.utc_now", return_value=datetime.fromisoformat("2026-09-28T12:00:00+03:30"))
        clock.start()
        self.addCleanup(clock.stop)

    def test_market_capture_rejects_stale_snapshot(self):
        data = snapshot()
        data["collected_at"] = "2000-01-01T00:00:00+00:00"
        result = MarketCaptureAgent({"www.tsetmc.com"}).capture_snapshot("TEST", data)
        self.assertEqual(result["agent"]["status"], "DATA_BLOCKED")
        self.assertTrue(any("COLLECTION_TIME_STALE" in item.get("message", "") for item in result["symbols"][0]["quality"]["findings"]))

    def test_all_ohlcv_fields_reject_invalid_numbers(self):
        for field in ("open", "high", "low", "close", "volume"):
            for value in (float("nan"), float("inf"), -float("inf"), "1e999", True, "", None):
                with self.subTest(field=field, value=value):
                    data = snapshot()
                    data["ohlcv"][0][field] = value
                    result = MarketCaptureAgent({"www.tsetmc.com"}).capture_snapshot("TEST", data)
                    self.assertEqual(result["symbols"][0]["jack_decision"], "DATA_BLOCKED")
                    json.dumps(result, allow_nan=False)

    def test_finite_number_rejects_integer_overflow(self):
        with self.assertRaises(ValueError):
            finite_number(10 ** 1000)

    def test_zero_price_is_blocked_but_zero_volume_is_valid(self):
        data = snapshot()
        data["ohlcv"][0] = {"open": 0, "high": 0, "low": 0, "close": 0, "volume": 1000}
        with self.assertRaises(ValueError):
            build_market_report(data)
        data = snapshot()
        data["ohlcv"][0]["volume"] = 0
        self.assertEqual(build_market_report(data)["symbols"][0]["data_status"], "VALID")

    def test_bad_weights_and_parameters_block_qa(self):
        for value in (float("nan"), float("inf"), "1e999", True, "invalid", -1):
            with self.subTest(value=value):
                result = quality_supervisor([{"name": "SMA", "family": "trend",
                    "timeframe": "daily", "direction": "bullish", "weight": value}])
                self.assertEqual(result["status"], "QA_BLOCKED")
                json.dumps(result, allow_nan=False)
        result = quality_supervisor([{"name": "SMA", "family": "trend", "timeframe": "daily",
            "direction": "bullish", "weight": 1, "parameters": {"value": float("nan")}}])
        self.assertEqual(result["status"], "QA_BLOCKED")

    def test_fundamental_zero_and_nonfinite_block(self):
        for field in ("revenue", "net_profit", "operating_margin_percent", "price_to_earnings", "debt_to_equity"):
            for value in (float("nan"), float("inf"), "1e999", True):
                data = fundamental()
                data[field] = value
                report = FundamentalAgent({"www.codal.ir"}).inspect(build_market_report(snapshot()), data)
                self.assertEqual(report["fundamental"]["status"], "FUNDAMENTAL_BLOCKED")
        data = fundamental()
        data["revenue"] = 0
        report = FundamentalAgent({"www.codal.ir"}).inspect(build_market_report(snapshot()), data)
        self.assertEqual(report["symbols"][0]["jack_decision"], "DATA_BLOCKED")
        self.assertIn("FUNDAMENTAL_REVENUE_MUST_BE_POSITIVE", report["fundamental"]["reason"])


class HttpRegressionTests(unittest.TestCase):
    def setUp(self):
        clock = patch("backend.freshness.utc_now", return_value=datetime.fromisoformat("2026-09-28T12:00:00+03:30"))
        clock.start()
        self.addCleanup(clock.stop)

    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), JackHandler)
        cls.server.allowed_source_hosts = {"www.tsetmc.com"}
        configure_browser_nonces(cls.server)
        for key, agent in {
            "market_capture_agent": MarketCaptureAgent({"www.tsetmc.com"}),
            "technical_analysis_agent": TechnicalAnalysisAgent(),
            "chart_control_agent": ChartControlAgent({"www.tsetmc.com"}),
            "market_board_agent": MarketBoardAgent({"www.tsetmc.com"}),
            "fundamental_agent": FundamentalAgent({"www.codal.ir"}),
            "portfolio_risk_agent": PortfolioRiskAgent(),
            "quality_supervisor_agent": QualitySupervisorAgent(),
            "browser_portfolio_agent": BrowserPortfolioAgent(set()),
        }.items():
            setattr(cls.server, key, agent)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def post(self, data, endpoint="/api/market-snapshot"):
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
        if endpoint == "/api/browser-observation":
            connection.request("GET", "/api/browser-nonce")
            nonce_response = connection.getresponse()
            nonce = json.loads(nonce_response.read())["nonce"]
            data = dict(data) | {"bridge_nonce": nonce}
        connection.request("POST", endpoint, json.dumps(data), {"Content-Type": "application/json"})
        response = connection.getresponse()
        status, raw = response.status, response.read().decode()
        connection.close()
        def reject(value):
            raise AssertionError("Nonstandard JSON number: " + value)
        return status, json.loads(raw, parse_constant=reject)

    def test_nonfinite_http_input_is_structured_block(self):
        for value in (float("nan"), float("inf"), -float("inf")):
            data = snapshot()
            data["ohlcv"][0]["close"] = value
            status, result = self.post(data)
            self.assertEqual(status, 400)
            self.assertEqual(result["data_status"], "DATA_BLOCKED")

    def test_browser_origin_allowlist_is_enforced(self):
        data = {"symbol": "TEST", "market_snapshot": snapshot()}
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
        connection.request("OPTIONS", "/api/browser-observation", headers={"Origin": "https://evil.example"})
        response = connection.getresponse()
        response.read()
        self.assertEqual(response.status, 403)
        connection.close()

        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
        connection.request("OPTIONS", "/api/browser-observation", headers={"Origin": "https://www.tsetmc.com"})
        response = connection.getresponse()
        response.read()
        self.assertEqual(response.status, 204)
        self.assertEqual(response.getheader("Access-Control-Allow-Origin"), "https://www.tsetmc.com")
        connection.close()

    def test_browser_schema_rejects_unknown_field(self):
        status, result = self.post({"symbol": "TEST", "market_snapshot": snapshot(), "raw_html": "not allowed"}, "/api/browser-observation")
        self.assertEqual(status, 400)
        self.assertEqual(result["error"], "BROWSER_PAYLOAD_UNKNOWN_FIELDS")

    def test_browser_nonce_is_single_use_and_required(self):
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
        connection.request("GET", "/api/browser-nonce")
        response = connection.getresponse()
        nonce = json.loads(response.read())["nonce"]
        self.assertEqual(response.status, 200)
        connection.request("POST", "/api/browser-observation", json.dumps({"symbol": "TEST", "market_snapshot": snapshot(), "bridge_nonce": nonce}), {"Content-Type": "application/json"})
        response = connection.getresponse()
        first = json.loads(response.read())
        self.assertEqual(response.status, 200)
        self.assertEqual(first["symbols"][0]["data_status"], "VALID")
        connection.request("POST", "/api/browser-observation", json.dumps({"symbol": "TEST", "market_snapshot": snapshot(), "bridge_nonce": nonce}), {"Content-Type": "application/json"})
        response = connection.getresponse()
        second = json.loads(response.read())
        self.assertEqual(response.status, 400)
        self.assertEqual(second["data_status"], "DATA_BLOCKED")
        connection.close()

    def test_zero_revenue_http_returns_blocked_report(self):
        data = snapshot()
        data["fundamental_observation"] = fundamental() | {"revenue": 0}
        status, result = self.post(data)
        self.assertEqual(status, 200)
        self.assertEqual(result["fundamental"]["status"], "FUNDAMENTAL_BLOCKED")
        self.assertEqual(result["symbols"][0]["jack_decision"], "DATA_BLOCKED")

    def test_browser_string_infinity_is_blocked(self):
        data = snapshot()
        data["ohlcv"][0]["volume"] = "1e999"
        status, result = self.post({"symbol": "TEST", "market_snapshot": data}, "/api/browser-observation")
        self.assertEqual(status, 200)
        self.assertEqual(result["symbols"][0]["jack_decision"], "DATA_BLOCKED")

    def test_valid_request_still_succeeds(self):
        status, result = self.post(snapshot())
        self.assertEqual(status, 200)
        self.assertEqual(result["symbols"][0]["data_status"], "VALID")

    def test_nonfinite_calculated_output_is_blocked(self):
        from unittest.mock import patch
        with patch("backend.server.build_demo_report", return_value={"score": float("nan")}):
            connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
            connection.request("GET", "/api/demo-report")
            response = connection.getresponse()
            result = json.loads(response.read())
            connection.close()
            self.assertEqual(response.status, 400)
            self.assertEqual(result["error"], "NONFINITE_OUTPUT_BLOCKED")


if __name__ == "__main__":
    unittest.main()
