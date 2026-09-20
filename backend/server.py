"""پروزه اتوماسیون بورسی — سرور localhost جک."""

from __future__ import annotations

import argparse
import json
import mimetypes
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import sys
import tomllib

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.agents.market_capture import MarketCaptureAgent  # noqa: E402
from backend.jack_core import build_demo_report  # noqa: E402

FRONTEND = ROOT / "frontend"


def load_allowed_source_hosts() -> set[str]:
    """فقط میزبان‌های مصوب پیکربندی محلی را برای دادهٔ بازار می‌پذیرد."""
    config_path = ROOT / "config.local.toml"
    with (ROOT / "config.example.toml").open("rb") as stream:
        default_config = tomllib.load(stream)
    config = default_config
    if config_path.exists():
        with config_path.open("rb") as stream:
            local_config = tomllib.load(stream)
        config = {**default_config, **local_config}
        config["market"] = {**default_config.get("market", {}), **local_config.get("market", {})}
    hosts = config.get("market", {}).get("approved_source_hosts", [])
    if not isinstance(hosts, list) or not all(isinstance(host, str) and host for host in hosts):
        raise ValueError("فهرست منابع بازار در تنظیمات محلی نامعتبر است.")
    return {host.lower() for host in hosts}


class JackHandler(BaseHTTPRequestHandler):
    server_version = "JackLocal/0.1"

    def _send_json(self, payload: dict, status: int = HTTPStatus.OK) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
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
        path = self.path.split("?", 1)[0]
        if path == "/api/health":
            self._send_json({"status": "ok", "mode": "local-only"})
        elif path == "/api/demo-report":
            self._send_json(build_demo_report())
        elif path == "/api/agent-status":
            self._send_json({"agents": [{"name": "market-capture-agent", "version": "0.1", "status": "available"}]})
        elif path in {"/", "/index.html"}:
            self._send_file("index.html")
        elif path in {"/app.js", "/styles.css"}:
            self._send_file(path.lstrip("/"))
        else:
            self.send_error(HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:  # noqa: N802
        endpoint = self.path.split("?", 1)[0]
        if endpoint not in {"/api/symbol-request", "/api/market-snapshot"}:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 1 <= length <= 262_144:
                raise ValueError("اندازهٔ درخواست نامعتبر است.")
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            if endpoint == "/api/symbol-request":
                if not isinstance(payload, dict) or not isinstance(payload.get("symbol"), str):
                    raise ValueError("نام نماد ارسال نشده است.")
                self._send_json(self.server.market_capture_agent.request_symbol(payload["symbol"]))
            else:
                if not isinstance(payload, dict) or not isinstance(payload.get("symbol"), str):
                    raise ValueError("نماد در بستهٔ دادهٔ بازار ارسال نشده است.")
                self._send_json(self.server.market_capture_agent.capture_snapshot(payload["symbol"], payload))
        except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
            self._send_json({"error": str(error)}, HTTPStatus.BAD_REQUEST)

    def log_message(self, format: str, *args: object) -> None:
        print(f"[jack-local] {self.address_string()} - {format % args}")


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
    server.allowed_source_hosts = load_allowed_source_hosts()
    server.market_capture_agent = MarketCaptureAgent(server.allowed_source_hosts)
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
