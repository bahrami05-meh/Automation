"""Single-use, Origin-bound bridge nonce and HTTP access regressions."""
from concurrent.futures import ThreadPoolExecutor
import http.client
import json
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from backend.server import configure_browser_nonces, MAX_BROWSER_NONCES
import test_critical_regressions as regressions


class NonceStoreTests(unittest.TestCase):
    def setUp(self):
        self.server = SimpleNamespace()
        configure_browser_nonces(self.server)
        clock = patch("backend.server.time.monotonic", return_value=100.0)
        self.clock = clock.start()
        self.addCleanup(clock.stop)

    def test_expiration_at_exact_deadline_and_before_deadline(self):
        nonce = self.server.issue_browser_nonce("https://www.tsetmc.com")
        self.clock.return_value = 159.999
        self.assertTrue(self.server.consume_browser_nonce(nonce, "https://www.tsetmc.com"))
        nonce = self.server.issue_browser_nonce()
        self.clock.return_value = 219.999
        self.assertFalse(self.server.consume_browser_nonce(nonce))

    def test_origin_mismatch_does_not_consume_valid_nonce(self):
        nonce = self.server.issue_browser_nonce("https://www.tsetmc.com")
        self.assertFalse(self.server.consume_browser_nonce(nonce, "https://tsetmc.com"))
        self.assertFalse(self.server.consume_browser_nonce(nonce))
        self.assertTrue(self.server.consume_browser_nonce(nonce, "https://www.tsetmc.com"))
        self.assertFalse(self.server.consume_browser_nonce(nonce, "https://www.tsetmc.com"))

    def test_concurrent_replay_accepts_only_one_request(self):
        nonce = self.server.issue_browser_nonce()
        with ThreadPoolExecutor(max_workers=8) as executor:
            accepted = list(executor.map(lambda _: self.server.consume_browser_nonce(nonce), range(16)))
        self.assertEqual(sum(accepted), 1)

    def test_capacity_is_bounded_and_expired_entries_are_reclaimed(self):
        for _ in range(MAX_BROWSER_NONCES):
            self.assertIsNotNone(self.server.issue_browser_nonce())
        self.assertIsNone(self.server.issue_browser_nonce())
        self.assertEqual(len(self.server._browser_nonces), MAX_BROWSER_NONCES)
        self.clock.return_value = 160.0
        self.assertIsNotNone(self.server.issue_browser_nonce())
        self.assertEqual(len(self.server._browser_nonces), 1)


class NonceHttpTests(unittest.TestCase):
    setUp = regressions.HttpRegressionTests.setUp
    setUpClass = classmethod(regressions.HttpRegressionTests.setUpClass.__func__)
    tearDownClass = classmethod(regressions.HttpRegressionTests.tearDownClass.__func__)

    def request(self, method, path, body=None, origin=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
        headers = {"Content-Type": "application/json"}
        if origin is not None:
            headers["Origin"] = origin
        connection.request(method, path, json.dumps(body) if body is not None else None, headers)
        response = connection.getresponse()
        raw = response.read()
        result = json.loads(raw) if response.getheader("Content-Type", "").startswith("application/json") else None
        status, cors = response.status, response.getheader("Access-Control-Allow-Origin")
        connection.close()
        return status, result, cors

    def test_approved_origin_gets_nonce_and_can_use_it_once(self):
        origin = "https://www.tsetmc.com"
        status, grant, cors = self.request("GET", "/api/browser-nonce", origin=origin)
        self.assertEqual((status, cors), (200, origin))
        payload = {"symbol": "TEST", "market_snapshot": regressions.snapshot(), "bridge_nonce": grant["nonce"]}
        status, result, cors = self.request("POST", "/api/browser-observation", payload, origin)
        self.assertEqual((status, cors), (200, origin))
        self.assertEqual(result["symbols"][0]["data_status"], "VALID")
        self.assertNotIn(grant["nonce"], json.dumps(result))
        status, result, cors = self.request("POST", "/api/browser-observation", payload, origin)
        self.assertEqual(status, 400)
        self.assertEqual(result["error"], "BROWSER_NONCE_INVALID_OR_EXPIRED")

    def test_unknown_or_malformed_origin_cannot_issue_or_submit(self):
        for origin in ("https://evil.example", "null", "https://www.tsetmc.com:bad", "https://www.tsetmc.com:0"):
            with self.subTest(origin=origin):
                for method, path in (("GET", "/api/browser-nonce"), ("POST", "/api/browser-observation")):
                    status, result, cors = self.request(method, path, {}, origin)
                    self.assertEqual(status, 403)
                    self.assertIsNone(cors)

    def test_nonce_required_and_missing_fake_or_expired_nonce_block(self):
        payload = {"symbol": "TEST", "market_snapshot": regressions.snapshot()}
        for body in (payload, payload | {"bridge_nonce": "invalid"}, payload | {"bridge_nonce": {"bad": 1}}):
            status, result, _ = self.request("POST", "/api/browser-observation", body)
            self.assertEqual(status, 400)
            self.assertEqual(result["data_status"], "DATA_BLOCKED")
        with patch("backend.server.time.monotonic", return_value=100.0):
            _, grant, _ = self.request("GET", "/api/browser-nonce")
        with patch("backend.server.time.monotonic", return_value=160.0):
            status, result, _ = self.request("POST", "/api/browser-observation", payload | {"bridge_nonce": grant["nonce"]})
        self.assertEqual(status, 400)
        self.assertEqual(result["error"], "BROWSER_NONCE_INVALID_OR_EXPIRED")

    def test_nonce_stays_bound_to_issuing_origin(self):
        self.server.allowed_source_hosts.add("tsetmc.com")
        try:
            _, grant, _ = self.request("GET", "/api/browser-nonce", origin="https://www.tsetmc.com")
            body = {"symbol": "TEST", "market_snapshot": regressions.snapshot(), "bridge_nonce": grant["nonce"]}
            self.assertEqual(self.request("POST", "/api/browser-observation", body, "https://tsetmc.com")[0], 400)
            self.assertEqual(self.request("POST", "/api/browser-observation", body)[0], 400)
            self.assertEqual(self.request("POST", "/api/browser-observation", body, "https://www.tsetmc.com")[0], 200)
        finally:
            self.server.allowed_source_hosts.discard("tsetmc.com")
