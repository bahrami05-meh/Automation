"""پروزه اتوماسیون بورسی — سرور localhost جک."""

from __future__ import annotations

import argparse
import json
import mimetypes
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from backend.jack_core import build_demo_report, build_symbol_request  # noqa: E402

FRONTEND = ROOT / "frontend"


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
        elif path in {"/", "/index.html"}:
            self._send_file("index.html")
        elif path in {"/app.js", "/styles.css"}:
            self._send_file(path.lstrip("/"))
        else:
            self.send_error(HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:  # noqa: N802
        if self.path.split("?", 1)[0] != "/api/symbol-request":
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 1 <= length <= 1024:
                raise ValueError("اندازهٔ درخواست نامعتبر است.")
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            if not isinstance(payload, dict) or not isinstance(payload.get("symbol"), str):
                raise ValueError("نام نماد ارسال نشده است.")
            self._send_json(build_symbol_request(payload["symbol"]))
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
