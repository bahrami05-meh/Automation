"""پروزه اتوماسیون بورسی — سرور localhost جک."""

from __future__ import annotations

import argparse
import json
import mimetypes
import secrets
import threading
import time
from datetime import datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import sys
import tomllib
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.agents.market_capture import MarketCaptureAgent  # noqa: E402
from backend.agents.technical_analysis import TechnicalAnalysisAgent  # noqa: E402
from backend.agents.chart_control import ChartControlAgent  # noqa: E402
from backend.agents.browser_portfolio import BrowserPortfolioAgent  # noqa: E402
from backend.agents.market_board import MarketBoardAgent  # noqa: E402
from backend.agents.fundamental import FundamentalAgent  # noqa: E402
from backend.agents.portfolio_risk import PortfolioRiskAgent  # noqa: E402
from backend.agents.quality_supervisor import QualitySupervisorAgent  # noqa: E402
from backend.browser_bridge import validate_browser_payload, validate_market_api_payload, validate_symbol_request_payload  # noqa: E402
from backend.jack_core import build_demo_report  # noqa: E402
from backend.numeric import validate_finite_tree  # noqa: E402
from backend.portfolio_import import MAX_FILE_BYTES, parse_portfolio_file  # noqa: E402
from backend.portfolio_summary import summarize_portfolio  # noqa: E402

FRONTEND = ROOT / "frontend"
NONCE_TTL_SECONDS = 60
MAX_BROWSER_NONCES = 256


def load_allowed_hosts(section: str) -> set[str]:
    """فقط میزبان‌های مصوب هر منبع را از پیکربندی محلی می‌پذیرد."""
    config_path = ROOT / "config.local.toml"
    with (ROOT / "config.example.toml").open("rb") as stream:
        default_config = tomllib.load(stream)
    config = default_config
    if config_path.exists():
        with config_path.open("rb") as stream:
            local_config = tomllib.load(stream)
        config = {**default_config, **local_config}
        config["market"] = {**default_config.get("market", {}), **local_config.get("market", {})}
    hosts = config.get(section, {}).get("approved_hosts", [])
    if not isinstance(hosts, list) or not all(isinstance(host, str) and host for host in hosts):
        raise ValueError("فهرست میزبان‌های مصوب در تنظیمات محلی نامعتبر است.")
    return {host.lower() for host in hosts}


def load_allowed_source_hosts() -> set[str]:
    """سازگاری با نام تابع پیشینِ منابع دادهٔ بازار."""
    return load_allowed_hosts("market")


class JackHandler(BaseHTTPRequestHandler):
    server_version = "JackLocal/0.1"

    def _send_json(self, payload: dict, status: int = HTTPStatus.OK) -> None:
        try:
            body = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode("utf-8")
        except (ValueError, OverflowError):
            status = HTTPStatus.BAD_REQUEST
            body = b'{"error":"NONFINITE_OUTPUT_BLOCKED","data_status":"DATA_BLOCKED"}'
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        origin = getattr(self, "_cors_origin", None)
        if origin:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, relative: str) -> None:
        target = (FRONTEND / relative).resolve()
        if not target.is_file() or not target.is_relative_to(FRONTEND.resolve()):
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        content = target.read_bytes()
        mime, _ = mimetypes.guess_type(str(target))
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", f"{mime or 'application/octet-stream'}; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(content)

    def do_GET(self) -> None:  # noqa: N802
        self._cors_origin = None
        path = self.path.split("?", 1)[0]
        if path == "/api/health":
            self._send_json({"status": "ok", "mode": "local-only"})
        elif path == "/api/demo-report":
            self._send_json(build_demo_report())
        elif path == "/api/agent-status":
            self._send_json({"agents": [
                {"name": "ایجنت دریافت", "id": "market-capture-agent", "version": "0.1", "status": "available"},
                {"name": "ایجنت تکنیکال", "id": "technical-analysis-agent", "version": "0.1", "status": "available"},
                {"name": "ایجنت کنترل نمودار", "id": "chart-control-agent", "version": "0.1", "status": "available"},
                {"name": "ایجنت مرورگر و پرتفوی", "id": "browser-portfolio-agent", "version": "0.1", "status": "available"},
                {"name": "ایجنت تابلو", "id": "market-board-agent", "version": "0.1", "status": "available"},
                {"name": "ایجنت بنیادی", "id": "fundamental-agent", "version": "0.1", "status": "available"},
                {"name": "ایجنت ریسک پرتفوی", "id": "portfolio-risk-agent", "version": "0.1", "status": "available"},
                {"name": "ایجنت ناظر کیفیت", "id": "quality-supervisor-agent", "version": "0.1", "status": "available"},
            ]})
        elif path == "/api/browser-nonce":
            origin = self._validated_cors_origin()
            if self.headers.get("Origin") and origin is None:
                self.send_error(HTTPStatus.FORBIDDEN, "Origin is not approved")
                return
            nonce = self.server.issue_browser_nonce(origin)
            self._cors_origin = origin
            if nonce is None:
                self._send_json({"error": "BROWSER_NONCE_CAPACITY_REACHED"}, HTTPStatus.TOO_MANY_REQUESTS)
                return
            self._send_json({"nonce": nonce, "expires_in": NONCE_TTL_SECONDS})
        elif path in {"/", "/index.html"}:
            self._send_file("index.html")
        elif path in {"/app.js", "/styles.css"}:
            self._send_file(path.lstrip("/"))
        else:
            self.send_error(HTTPStatus.NOT_FOUND)

    def do_OPTIONS(self) -> None:  # noqa: N802
        """Allow the read-only browser bridge's JSON CORS preflight."""
        self._cors_origin = None
        endpoint = self.path.split("?", 1)[0]
        if endpoint != "/api/browser-observation":
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        origin = self._validated_cors_origin()
        if origin is None:
            self.send_error(HTTPStatus.FORBIDDEN, "Origin is not approved")
            return
        self.send_response(HTTPStatus.NO_CONTENT)
        self._cors_origin = origin
        self.send_header("Access-Control-Allow-Origin", origin)
        self.send_header("Vary", "Origin")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Max-Age", "300")
        self.end_headers()

    def do_POST(self) -> None:  # noqa: N802
        self._cors_origin = None
        endpoint = self.path.split("?", 1)[0]
        if endpoint not in {"/api/symbol-request", "/api/market-snapshot", "/api/browser-observation", "/api/portfolio-import"}:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        if endpoint == "/api/portfolio-import":
            origin = self.headers.get("Origin")
            if origin and not self._is_local_import_origin(origin):
                self._send_json({"error": "LOCAL_PORTFOLIO_IMPORT_ORIGIN_BLOCKED", "data_status": "DATA_BLOCKED"}, HTTPStatus.FORBIDDEN)
                return
        if endpoint == "/api/browser-observation":
            origin = self._validated_cors_origin()
            if self.headers.get("Origin") and origin is None:
                self.send_error(HTTPStatus.FORBIDDEN, "Origin is not approved")
                return
            self._cors_origin = origin
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if endpoint == "/api/portfolio-import":
                if not 1 <= length <= MAX_FILE_BYTES:
                    raise ValueError("PORTFOLIO_FILE_SIZE_INVALID")
                if self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower() != "application/octet-stream":
                    raise ValueError("PORTFOLIO_FILE_CONTENT_TYPE_INVALID")
                file_format = self.headers.get("X-Jack-Import-Format", "").strip().lower()
                price_unit = self.headers.get("X-Jack-Price-Unit", "").strip().upper()
                modified_value = self.headers.get("X-Jack-File-Modified", "").strip()
                if not modified_value:
                    raise ValueError("PORTFOLIO_FILE_TIMESTAMP_REQUIRED")
                try:
                    file_modified_at = datetime.fromisoformat(modified_value.replace("Z", "+00:00"))
                except ValueError as error:
                    raise ValueError("PORTFOLIO_FILE_TIMESTAMP_INVALID") from error
                if file_modified_at.tzinfo is None or file_modified_at.utcoffset() is None:
                    raise ValueError("PORTFOLIO_FILE_TIMESTAMP_INVALID")
                raw_file = self.rfile.read(length)
                if len(raw_file) != length:
                    raise ValueError("PORTFOLIO_FILE_SIZE_INVALID")
                observation = parse_portfolio_file(
                    raw_file, file_format, price_unit=price_unit,
                    allowed_hosts=getattr(self.server, "allowed_brokerage_hosts", set()),
                    collected_at=file_modified_at,
                )
                result = self.server.browser_portfolio_agent.capture({"agents": []}, observation)
                result["mode"] = "PORTFOLIO_FILE_IMPORT_PREVIEW"
                result["disclaimer"] = "این فقط اعتبارسنجی و نمایش فایل پرتفوی است؛ تحلیل بازار یا توصیهٔ معامله انجام نشده است. فایل روی دیسک ذخیره نمی‌شود."
                if result["portfolio_capture"]["status"] != "PORTFOLIO_CAPTURED":
                    result["error"] = result["browser_portfolio_agent"].get("error_code", "PORTFOLIO_OBSERVATION_INVALID")
                    self._send_json(result, HTTPStatus.UNPROCESSABLE_ENTITY)
                else:
                    result["portfolio_summary"] = summarize_portfolio(result["portfolio_capture"]["holdings"])
                    self._send_json(result)
                return
            if not 1 <= length <= 262_144:
                raise ValueError("اندازهٔ درخواست نامعتبر است.")
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            validate_finite_tree(payload)
            fundamental_hosts = getattr(self.server, "allowed_fundamental_hosts", {"codal.ir", "www.codal.ir"})
            brokerage_hosts = getattr(self.server, "allowed_brokerage_hosts", set())
            if endpoint == "/api/browser-observation":
                browser_payload = validate_browser_payload(
                    payload,
                    market_hosts=self.server.allowed_source_hosts,
                    chart_hosts=self.server.allowed_source_hosts,
                    board_hosts=self.server.allowed_source_hosts,
                    fundamental_hosts=fundamental_hosts,
                    portfolio_hosts=brokerage_hosts,
                )
                if not self.server.consume_browser_nonce(browser_payload["bridge_nonce"], self._cors_origin):
                    raise ValueError("BROWSER_NONCE_INVALID_OR_EXPIRED")
                browser_payload = {key: value for key, value in browser_payload.items() if key != "bridge_nonce"}
                symbol = browser_payload["symbol"]
                report = self.server.market_capture_agent.capture_snapshot(symbol, browser_payload["market_snapshot"])
                report = self.server.technical_analysis_agent.analyze(report)
                report = self.server.chart_control_agent.inspect(report, browser_payload.get("chart_observation"))
                report = self.server.market_board_agent.inspect(report, browser_payload.get("market_board_observation"))
                report = self.server.fundamental_agent.inspect(report, browser_payload.get("fundamental_observation"))
                report = self.server.portfolio_risk_agent.inspect(report, browser_payload.get("risk_observation"))
                report = self.server.browser_portfolio_agent.capture(report, browser_payload.get("portfolio_observation"))
                self._send_json(self.server.quality_supervisor_agent.inspect(report))
            elif endpoint == "/api/symbol-request":
                payload = validate_symbol_request_payload(payload)
                report = self.server.market_capture_agent.request_symbol(payload["symbol"])
                report = self.server.technical_analysis_agent.analyze(report)
                report = self.server.chart_control_agent.inspect(report, None)
                report = self.server.market_board_agent.inspect(report, None)
                report = self.server.fundamental_agent.inspect(report, None)
                report = self.server.portfolio_risk_agent.inspect(report, None)
                report = self.server.browser_portfolio_agent.capture(report, None)
                self._send_json(self.server.quality_supervisor_agent.inspect(report))
            else:
                if not isinstance(payload, dict) or not isinstance(payload.get("symbol"), str):
                    raise ValueError("نماد در بستهٔ دادهٔ بازار ارسال نشده است.")
                payload = validate_market_api_payload(
                    payload,
                    market_hosts=self.server.allowed_source_hosts,
                    chart_hosts=self.server.allowed_source_hosts,
                    board_hosts=self.server.allowed_source_hosts,
                    fundamental_hosts=fundamental_hosts,
                    portfolio_hosts=brokerage_hosts,
                )
                market_snapshot = {key: payload[key] for key in (
                    "symbol", "source", "collected_at", "timezone", "price_unit",
                    "price_type", "timeframe", "ohlcv",
                )}
                report = self.server.market_capture_agent.capture_snapshot(payload["symbol"], market_snapshot)
                report = self.server.technical_analysis_agent.analyze(report)
                report = self.server.chart_control_agent.inspect(report, payload.get("chart_observation"))
                report = self.server.market_board_agent.inspect(report, payload.get("market_board_observation"))
                report = self.server.fundamental_agent.inspect(report, payload.get("fundamental_observation"))
                report = self.server.portfolio_risk_agent.inspect(report, payload.get("risk_observation"))
                report = self.server.browser_portfolio_agent.capture(report, payload.get("portfolio_observation"))
                self._send_json(self.server.quality_supervisor_agent.inspect(report))
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError, ArithmeticError) as error:
            self._send_json({"error": "ARITHMETIC_INPUT_INVALID" if isinstance(error, ArithmeticError) else str(error), "data_status": "DATA_BLOCKED"}, HTTPStatus.BAD_REQUEST)

    def _validated_cors_origin(self) -> str | None:
        origin = self.headers.get("Origin")
        if not origin:
            return None
        if not origin.startswith("https://"):
            return None
        from urllib.parse import urlparse
        approved = getattr(self.server, "allowed_source_hosts", set())
        try:
            parsed = urlparse(origin)
            port = parsed.port
        except ValueError:
            return None
        if parsed.path or parsed.params or parsed.query or parsed.fragment or parsed.username or parsed.password or port is not None:
            return None
        return origin if parsed.hostname and parsed.hostname.lower() in approved else None

    def _is_local_import_origin(self, origin: str) -> bool:
        try:
            parsed = urlsplit(origin)
            port = parsed.port
        except ValueError:
            return False
        return (
            parsed.scheme == "http"
            and parsed.hostname in {"127.0.0.1", "localhost"}
            and port == self.server.server_port
            and not parsed.path and not parsed.query and not parsed.fragment
            and not parsed.username and not parsed.password
        )

    def log_message(self, format: str, *args: object) -> None:
        print(f"[jack-local] {self.address_string()} - {format % args}")


def configure_browser_nonces(server: ThreadingHTTPServer) -> None:
    server._browser_nonces = {}
    server._browser_nonce_lock = threading.Lock()
    server.issue_browser_nonce = lambda origin=None: _issue_browser_nonce(server, origin)
    server.consume_browser_nonce = lambda nonce, origin=None: _consume_browser_nonce(server, nonce, origin)


def _issue_browser_nonce(server: ThreadingHTTPServer, origin: str | None = None) -> str | None:
    with server._browser_nonce_lock:
        now = time.monotonic()
        server._browser_nonces = {key: entry for key, entry in server._browser_nonces.items() if entry[1] > now}
        if len(server._browser_nonces) >= MAX_BROWSER_NONCES:
            return None
        nonce = secrets.token_urlsafe(24)
        server._browser_nonces[nonce] = (origin, now + NONCE_TTL_SECONDS)
    return nonce


def _consume_browser_nonce(server: ThreadingHTTPServer, nonce: str, origin: str | None = None) -> bool:
    with server._browser_nonce_lock:
        entry = server._browser_nonces.get(nonce)
        if entry is None:
            return False
        issued_origin, expires = entry
        if time.monotonic() >= expires:
            server._browser_nonces.pop(nonce)
            return False
        if issued_origin != origin:
            return False
        server._browser_nonces.pop(nonce)
        return True


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Jack on localhost only.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    if args.host != "127.0.0.1":
        parser.error("Jack only allows 127.0.0.1 binding.")
    if not 1024 <= args.port <= 65535:
        parser.error("Port must be between 1024 and 65535.")
    server = ThreadingHTTPServer((args.host, args.port), JackHandler)
    configure_browser_nonces(server)
    server.allowed_source_hosts = load_allowed_source_hosts()
    server.allowed_fundamental_hosts = load_allowed_hosts("fundamental")
    server.allowed_brokerage_hosts = load_allowed_hosts("brokerage")
    server.market_capture_agent = MarketCaptureAgent(server.allowed_source_hosts)
    server.technical_analysis_agent = TechnicalAnalysisAgent()
    server.chart_control_agent = ChartControlAgent(server.allowed_source_hosts)
    server.market_board_agent = MarketBoardAgent(server.allowed_source_hosts)
    server.fundamental_agent = FundamentalAgent(server.allowed_fundamental_hosts)
    server.portfolio_risk_agent = PortfolioRiskAgent()
    server.quality_supervisor_agent = QualitySupervisorAgent()
    server.browser_portfolio_agent = BrowserPortfolioAgent(server.allowed_brokerage_hosts)
    print(f"Jack is running at http://{args.host}:{args.port}")
    print("Demo mode only: no brokerage access, no orders, no private data storage.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("Jack stopped.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
