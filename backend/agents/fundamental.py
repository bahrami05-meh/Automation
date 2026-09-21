"""پروزه اتوماسیون بورسی — ایجنت بنیادیِ فقط‌خواندنی."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlparse
from uuid import uuid4


AGENT_NAME = "ایجنت بنیادی"
AGENT_ID = "fundamental-agent"
AGENT_VERSION = "0.1"
TEHRAN = timezone(timedelta(hours=3, minutes=30), "Asia/Tehran")
EVENT_TYPES = {
    "financial_statement", "material_disclosure", "assembly",
    "capital_increase", "dividend", "suspension_notice",
}


def _run_metadata() -> dict[str, str]:
    return {
        "name": AGENT_NAME, "id": AGENT_ID, "version": AGENT_VERSION,
        "run_id": f"fda-{uuid4().hex}",
        "started_at": datetime.now(TEHRAN).isoformat(timespec="seconds"),
    }


class FundamentalAgent:
    """اعتبارسنجی خلاصهٔ صورت مالی و رویداد رسمی، بدون رأی معاملاتی."""

    def __init__(self, allowed_hosts: set[str]) -> None:
        self.allowed_hosts = {host.lower() for host in allowed_hosts}

    def inspect(self, report: dict[str, Any], observation: object | None) -> dict[str, Any]:
        agent = _run_metadata()
        symbol = report["symbols"][0]
        if symbol.get("data_status") != "VALID":
            report["fundamental"] = self._skipped("تا پیش از دادهٔ معتبر بازار، بررسی بنیادی اجرا نمی‌شود.")
            report["fundamental_agent"] = agent | {"status": "SKIPPED"}
            return self._with_agent_chain(report)
        if observation is None:
            report["fundamental"] = self._skipped("مشاهدهٔ بنیادی به درخواست داده افزوده نشده است؛ اتصال خودکار منبع رسمی هنوز ساخته نشده است.")
            report["fundamental"]["findings"] = [{
                "code": "FUNDAMENTAL_SOURCE_NOT_CONNECTED", "severity": "warning",
                "message": "ایجنت بنیادی فقط مشاهدهٔ رسمیِ ثبت‌شده را کنترل می‌کند و هنوز دادهٔ زنده دریافت نمی‌کند.",
            }]
            report["fundamental_agent"] = agent | {"status": "SKIPPED"}
            return self._with_agent_chain(report)
        try:
            fundamental = self._validate(symbol, observation)
        except ValueError as error:
            finding = {"code": "FUNDAMENTAL_OBSERVATION_INVALID", "severity": "blocker", "message": str(error)}
            report["fundamental"] = {"status": "FUNDAMENTAL_BLOCKED", "reason": str(error), "findings": [finding]}
            self._block_quality(symbol, finding, "دادهٔ بنیادی نامعتبر است و تحلیل ادامه نمی‌یابد.")
            report["fundamental_agent"] = agent | {"status": "FUNDAMENTAL_BLOCKED"}
            return self._with_agent_chain(report)

        net_margin = round(fundamental["net_profit"] / fundamental["revenue"] * 100, 2)
        earnings_state = "PROFITABLE" if fundamental["net_profit"] > 0 else "LOSS_MAKING"
        leverage_state = "HIGH_LEVERAGE" if fundamental["debt_to_equity"] > 2 else "MODERATE_OR_LOW_LEVERAGE"
        report["fundamental"] = {
            "status": "OBSERVED",
            "reason": "دادهٔ بنیادی رسمی اعتبارسنجی شد؛ خروجی فقط مشاهده و محاسبه است، نه توصیهٔ معامله.",
            "observation": fundamental,
            "metrics": {
                "net_margin_percent": net_margin,
                "earnings_state": earnings_state,
                "leverage_state": leverage_state,
                "operating_margin_percent": fundamental["operating_margin_percent"],
                "price_to_earnings": fundamental["price_to_earnings"],
            },
            "findings": [],
        }
        report["fundamental_agent"] = agent | {"status": "OBSERVED"}
        return self._with_agent_chain(report)

    @staticmethod
    def _skipped(reason: str) -> dict[str, Any]:
        return {"status": "SKIPPED", "reason": reason, "findings": []}

    def _validate(self, symbol: dict[str, Any], observation: object) -> dict[str, Any]:
        if not isinstance(observation, dict):
            raise ValueError("مشاهدهٔ بنیادی باید یک شیء JSON باشد.")
        required = (
            "symbol", "source", "collected_at", "timezone", "fiscal_year_end", "financial_unit",
            "revenue", "net_profit", "operating_margin_percent", "price_to_earnings", "debt_to_equity", "events",
        )
        missing = [key for key in required if key not in observation]
        if missing:
            raise ValueError("فیلدهای لازم مشاهدهٔ بنیادی وجود ندارند: " + ", ".join(missing))
        if observation["symbol"] != symbol["symbol"]:
            raise ValueError("نماد مشاهدهٔ بنیادی با نماد دادهٔ بازار یکسان نیست.")
        source = observation["source"]
        if not isinstance(source, str) or not source.startswith("https://"):
            raise ValueError("منبع بنیادی باید نشانی HTTPS باشد.")
        host = urlparse(source).hostname
        if not host or host.lower() not in self.allowed_hosts:
            raise ValueError("میزبان بنیادی در فهرست منابع رسمیِ تأییدشدهٔ محلی نیست.")
        collected_at = observation["collected_at"]
        if not isinstance(collected_at, str):
            raise ValueError("زمان مشاهدهٔ بنیادی نامعتبر است.")
        try:
            datetime.fromisoformat(collected_at.replace("Z", "+00:00"))
        except ValueError as error:
            raise ValueError("زمان مشاهدهٔ بنیادی نامعتبر است.") from error
        if observation["timezone"] != "Asia/Tehran":
            raise ValueError("منطقهٔ زمانی مشاهدهٔ بنیادی باید Asia/Tehran باشد.")
        if observation["financial_unit"] not in {"IRR", "IRT"}:
            raise ValueError("واحد مالی باید IRR یا IRT باشد.")
        if not isinstance(observation["fiscal_year_end"], str) or not observation["fiscal_year_end"].strip():
            raise ValueError("پایان سال مالی نامعتبر است.")
        checked: dict[str, Any] = {
            key: observation[key] for key in ("symbol", "source", "collected_at", "timezone", "fiscal_year_end", "financial_unit")
        }
        for key in ("revenue", "net_profit", "operating_margin_percent", "price_to_earnings", "debt_to_equity"):
            try:
                value = float(observation[key])
            except (TypeError, ValueError) as error:
                raise ValueError(f"مقدار {key} در مشاهدهٔ بنیادی نامعتبر است.") from error
            if key in {"revenue", "price_to_earnings", "debt_to_equity"} and value < 0:
                raise ValueError(f"مقدار {key} در مشاهدهٔ بنیادی نامعتبر است.")
            checked[key] = value
        events = observation["events"]
        if not isinstance(events, list):
            raise ValueError("فهرست رویدادهای بنیادی نامعتبر است.")
        checked_events = []
        for event in events:
            if not isinstance(event, dict) or event.get("event_type") not in EVENT_TYPES or not isinstance(event.get("published_at"), str):
                raise ValueError("یکی از رویدادهای بنیادی نامعتبر است.")
            checked_events.append({"event_type": event["event_type"], "published_at": event["published_at"]})
        checked["events"] = checked_events
        return checked

    @staticmethod
    def _block_quality(symbol: dict[str, Any], finding: dict[str, Any], reason: str) -> None:
        quality = symbol.setdefault("quality", {"status": "QA_BLOCKED", "findings": []})
        quality["status"] = "QA_BLOCKED"
        quality.setdefault("findings", []).append(finding)
        symbol["data_status"] = "DATA_BLOCKED"
        symbol["jack_decision"] = "DATA_BLOCKED"
        symbol["reason"] = reason

    @staticmethod
    def _with_agent_chain(report: dict[str, Any]) -> dict[str, Any]:
        report["agents"] = list(report.get("agents", [])) + [report["fundamental_agent"]]
        return report
