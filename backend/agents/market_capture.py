"""پروزه اتوماسیون بورسی — ایجنت دریافت و اعتبارسنجی دادهٔ بازار.

این ایجنت فقط دادهٔ بازار را دریافت و اعتبارسنجی می‌کند. نه به کارگزاری وارد
می‌شود، نه نشست مرورگر را ذخیره می‌کند و نه اقدام مالی انجام می‌دهد.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from backend.jack_core import build_symbol_request
from backend.market_data import build_market_report


AGENT_NAME = "ایجنت دریافت"
AGENT_ID = "market-capture-agent"
AGENT_VERSION = "0.1"
TEHRAN = timezone(timedelta(hours=3, minutes=30), "Asia/Tehran")


def _run_metadata() -> dict[str, str]:
    return {
        "name": AGENT_NAME,
        "id": AGENT_ID,
        "version": AGENT_VERSION,
        "run_id": f"mca-{uuid4().hex}",
        "started_at": datetime.now(TEHRAN).isoformat(timespec="seconds"),
    }


class MarketCaptureAgent:
    """مرز اجراییِ دریافت داده بین منبع مصوب و هستهٔ تحلیل."""

    def __init__(self, allowed_hosts: set[str]) -> None:
        self.allowed_hosts = {host.lower() for host in allowed_hosts}

    def request_symbol(self, symbol: str) -> dict[str, Any]:
        """ثبت نماد بدون منبع داده؛ عمداً تحلیل را مسدود می‌کند."""
        report = build_symbol_request(symbol)
        report["agent"] = _run_metadata()
        report["agent"]["status"] = "DATA_BLOCKED"
        report["agent"]["next_requirement"] = "دادهٔ OHLCV از منبع تأییدشده"
        return report

    def capture_snapshot(self, requested_symbol: str, snapshot: object) -> dict[str, Any]:
        """بستهٔ دادهٔ خام را بدون تغییر پنهان به هستهٔ تحلیل می‌فرستد."""
        agent = _run_metadata()
        requested = build_symbol_request(requested_symbol)["symbols"][0]["symbol"]
        if not isinstance(snapshot, dict) or snapshot.get("symbol") != requested:
            report = build_symbol_request(requested)
            report["agent"] = agent | {
                "status": "DATA_BLOCKED",
                "error_code": "SYMBOL_MISMATCH",
                "next_requirement": "نماد دادهٔ بازار باید دقیقاً با نماد انتخاب‌شده برابر باشد.",
            }
            report["symbols"][0]["quality"]["findings"] = [{
                "code": "SYMBOL_MISMATCH",
                "severity": "blocker",
                "message": "نماد انتخاب‌شده با نماد موجود در دادهٔ بازار یکسان نیست.",
            }]
            return report
        try:
            report = build_market_report(snapshot, self.allowed_hosts)
        except ValueError as error:
            report = build_symbol_request(requested)
            report["symbols"][0]["quality"]["findings"] = [{
                "code": "CAPTURE_VALIDATION_FAILED",
                "severity": "blocker",
                "message": str(error),
            }]
            report["symbols"][0]["reason"] = "ایجنت دریافت داده، بستهٔ نامعتبر را به تحلیل ارسال نکرد."
            report["agent"] = agent | {
                "status": "DATA_BLOCKED",
                "error_code": "CAPTURE_VALIDATION_FAILED",
                "next_requirement": "بستهٔ دادهٔ بازارِ کامل و معتبر",
            }
            return report
        report["agent"] = agent | {"status": "CAPTURED", "source": snapshot["source"]}
        return report
