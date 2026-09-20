"""پروزه اتوماسیون بورسی — ایجنت مرورگر و پرتفویِ فقط‌خواندنی.

ورود و احراز هویت بیرون از این کد است. این ایجنت نشست، رمز یا کوکی را دریافت
یا ذخیره نمی‌کند و فقط یک مشاهدهٔ قابل‌نمایشِ ساختاریافته را در حافظهٔ همان
درخواست اعتبارسنجی می‌کند.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlparse
from uuid import uuid4

from backend.jack_core import build_symbol_request


AGENT_NAME = "ایجنت مرورگر و پرتفوی"
AGENT_ID = "browser-portfolio-agent"
AGENT_VERSION = "0.1"
TEHRAN = timezone(timedelta(hours=3, minutes=30), "Asia/Tehran")
SENSITIVE_FIELD_PARTS = {"password", "pass", "otp", "token", "cookie", "session", "username", "user", "رمز", "کد", "نشست"}


def _run_metadata() -> dict[str, str]:
    return {
        "name": AGENT_NAME,
        "id": AGENT_ID,
        "version": AGENT_VERSION,
        "run_id": f"bpa-{uuid4().hex}",
        "started_at": datetime.now(TEHRAN).isoformat(timespec="seconds"),
    }


class BrowserPortfolioAgent:
    """مرز امن دادهٔ قابل‌مشاهدهٔ پرتفوی، تا زمان اتصال پل مرورگر."""

    def __init__(self, approved_hosts: set[str]) -> None:
        self.approved_hosts = {host.lower() for host in approved_hosts}

    def capture(self, report: dict[str, Any], observation: object | None) -> dict[str, Any]:
        agent = _run_metadata()
        if observation is None:
            report["portfolio_capture"] = {
                "status": "WAITING_FOR_BROWSER_SOURCE",
                "reason": "پل مرورگر و مشاهدهٔ فقط‌خواندنی پرتفوی هنوز به این اجرا متصل نشده است.",
                "holdings_count": 0,
            }
            report["browser_portfolio_agent"] = agent | {"status": "WAITING_FOR_BROWSER_SOURCE"}
            return self._with_agent_chain(report)
        try:
            captured = self._validate_observation(observation)
        except ValueError as error:
            report["portfolio_capture"] = {
                "status": "PORTFOLIO_BLOCKED",
                "reason": str(error),
                "holdings_count": 0,
            }
            report["browser_portfolio_agent"] = agent | {"status": "PORTFOLIO_BLOCKED", "error_code": "PORTFOLIO_OBSERVATION_INVALID"}
            return self._with_agent_chain(report)

        report["portfolio_capture"] = {
            "status": "PORTFOLIO_CAPTURED",
            "reason": "مشاهدهٔ فقط‌خواندنی پرتفوی اعتبارسنجی شد؛ فقط در حافظهٔ همین درخواست است.",
            "source": captured["source"],
            "collected_at": captured["collected_at"],
            "timezone": captured["timezone"],
            "price_unit": captured["price_unit"],
            "holdings_count": len(captured["holdings"]),
            "holdings": captured["holdings"],
        }
        report["browser_portfolio_agent"] = agent | {"status": "PORTFOLIO_CAPTURED"}
        return self._with_agent_chain(report)

    def _validate_observation(self, observation: object) -> dict[str, Any]:
        if not isinstance(observation, dict):
            raise ValueError("مشاهدهٔ پرتفوی باید یک شیء JSON باشد.")
        if self._contains_sensitive_field(observation):
            raise ValueError("مشاهدهٔ پرتفوی نباید شامل اطلاعات ورود، نشست، کوکی یا کد تأیید باشد.")
        required = ("source", "collected_at", "timezone", "price_unit", "holdings")
        missing = [key for key in required if key not in observation]
        if missing:
            raise ValueError("فیلدهای لازم مشاهدهٔ پرتفوی وجود ندارند: " + ", ".join(missing))
        if not isinstance(observation["source"], str) or not observation["source"].startswith("https://"):
            raise ValueError("منبع پرتفوی باید نشانی HTTPS باشد.")
        host = urlparse(observation["source"]).hostname
        if not host or host.lower() not in self.approved_hosts:
            raise ValueError("میزبان پرتفوی در فهرست `brokerage.approved_hosts` تنظیمات محلی تأیید نشده است.")
        if not isinstance(observation["collected_at"], str):
            raise ValueError("زمان مشاهدهٔ پرتفوی نامعتبر است.")
        try:
            datetime.fromisoformat(observation["collected_at"].replace("Z", "+00:00"))
        except ValueError as error:
            raise ValueError("زمان مشاهدهٔ پرتفوی نامعتبر است.") from error
        if observation["timezone"] != "Asia/Tehran":
            raise ValueError("منطقهٔ زمانی مشاهدهٔ پرتفوی باید Asia/Tehran باشد.")
        if observation["price_unit"] not in {"IRR", "IRT"}:
            raise ValueError("واحد قیمت پرتفوی باید IRR یا IRT باشد.")
        holdings = observation["holdings"]
        if not isinstance(holdings, list) or not holdings:
            raise ValueError("حداقل یک ردیف داراییِ قابل‌مشاهده لازم است.")
        checked = []
        for index, item in enumerate(holdings):
            if not isinstance(item, dict):
                raise ValueError(f"ردیف {index + 1} پرتفوی نامعتبر است.")
            try:
                symbol = build_symbol_request(str(item["symbol"]))["symbols"][0]["symbol"]
                quantity = float(item["quantity"])
                average_price = float(item["average_price"])
                last_price = float(item["last_price"])
                market_value = float(item["market_value"])
            except (KeyError, TypeError, ValueError) as error:
                raise ValueError(f"ردیف {index + 1} پرتفوی ناقص یا نامعتبر است.") from error
            if min(quantity, average_price, last_price, market_value) < 0:
                raise ValueError(f"ردیف {index + 1} پرتفوی دارای مقدار منفی است.")
            checked.append({
                "symbol": symbol, "quantity": quantity, "average_price": average_price,
                "last_price": last_price, "market_value": market_value,
            })
        return {
            "source": observation["source"], "collected_at": observation["collected_at"],
            "timezone": observation["timezone"], "price_unit": observation["price_unit"], "holdings": checked,
        }

    @staticmethod
    def _contains_sensitive_field(value: object) -> bool:
        if isinstance(value, dict):
            for key, nested in value.items():
                key_lower = str(key).lower()
                if any(part in key_lower for part in SENSITIVE_FIELD_PARTS) or BrowserPortfolioAgent._contains_sensitive_field(nested):
                    return True
        elif isinstance(value, list):
            return any(BrowserPortfolioAgent._contains_sensitive_field(item) for item in value)
        return False

    @staticmethod
    def _with_agent_chain(report: dict[str, Any]) -> dict[str, Any]:
        chain = list(report.get("agents", []))
        chain.append(report["browser_portfolio_agent"])
        report["agents"] = chain
        return report
