"""پروزه اتوماسیون بورسی — ایجنت کنترل نمودار و اندیکاتور.

این ایجنت فقط شواهد ثبت‌شده از نمودار را بررسی می‌کند؛ مرورگر، کارگزاری و
هیچ اقدام مالی را کنترل نمی‌کند.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlparse
from uuid import uuid4

from backend.jack_core import VALID_DIRECTIONS


AGENT_NAME = "ایجنت کنترل نمودار"
AGENT_ID = "chart-control-agent"
AGENT_VERSION = "0.1"
TEHRAN = timezone(timedelta(hours=3, minutes=30), "Asia/Tehran")
SUPPORTED_INDICATORS = {"SMA", "RSI", "MACD", "ICHIMOKU", "ATR"}


def _run_metadata() -> dict[str, str]:
    return {
        "name": AGENT_NAME,
        "id": AGENT_ID,
        "version": AGENT_VERSION,
        "run_id": f"cca-{uuid4().hex}",
        "started_at": datetime.now(TEHRAN).isoformat(timespec="seconds"),
    }


class ChartControlAgent:
    """کنترل قابلیت ردیابی شواهد نمودار بدون انجام تعامل با وب‌سایت."""

    def __init__(self, allowed_hosts: set[str]) -> None:
        self.allowed_hosts = {host.lower() for host in allowed_hosts}

    def inspect(self, report: dict[str, Any], observation: object | None) -> dict[str, Any]:
        agent = _run_metadata()
        symbol = report["symbols"][0]
        if symbol.get("data_status") != "VALID" or report.get("technical", {}).get("status") != "ANALYZED":
            report["chart_control"] = {
                "status": "SKIPPED",
                "reason": "تا پیش از دادهٔ معتبر و اجرای ایجنت تکنیکال، کنترل نمودار انجام نمی‌شود.",
                "findings": [],
            }
            report["chart_control_agent"] = agent | {"status": "SKIPPED"}
            return self._with_agent_chain(report)
        if observation is None:
            report["chart_control"] = {
                "status": "SKIPPED",
                "reason": "مشاهدهٔ نمودار به درخواست داده افزوده نشده است؛ اتصال مرورگر در این نسخه ساخته نشده است.",
                "findings": [{
                    "code": "CHART_SOURCE_NOT_CONNECTED",
                    "severity": "warning",
                    "message": "ایجنت فقط دادهٔ نمودارِ ثبت‌شده را کنترل می‌کند و هنوز از مرورگر دریافت خودکار ندارد.",
                }],
            }
            report["chart_control_agent"] = agent | {"status": "SKIPPED"}
            return self._with_agent_chain(report)

        try:
            checked = self._validate_observation(symbol, observation)
        except ValueError as error:
            report["chart_control"] = {
                "status": "CHART_BLOCKED",
                "reason": str(error),
                "findings": [{"code": "CHART_OBSERVATION_INVALID", "severity": "blocker", "message": str(error)}],
            }
            self._block_quality(symbol, report["chart_control"]["findings"][0])
            report["chart_control_agent"] = agent | {"status": "CHART_BLOCKED"}
            return self._with_agent_chain(report)

        calculated = {item["name"].upper(): item["direction"] for item in symbol.get("indicators", [])}
        conflicts = [
            item for item in checked["indicators"]
            if item["name"] in calculated and item["direction"] != calculated[item["name"]]
        ]
        if conflicts:
            report["chart_control"] = {
                "status": "CHART_CONFLICT",
                "reason": "حداقل یک جهت ثبت‌شده در نمودار با محاسبهٔ مستقل OHLCV سازگار نیست.",
                "observation": checked,
                "findings": [{
                    "code": "CHART_DIRECTION_MISMATCH",
                    "severity": "blocker",
                    "message": "اختلاف جهت اندیکاتور بین نمودار و محاسبهٔ مستقل ثبت شد.",
                    "details": {"indicators": conflicts},
                }],
            }
            symbol["data_status"] = "DATA_BLOCKED"
            symbol["jack_decision"] = "DATA_BLOCKED"
            symbol["reason"] = "اختلاف نمودار و محاسبهٔ مستقل باید پیش از هر جمع‌بندی رفع شود."
            self._block_quality(symbol, report["chart_control"]["findings"][0])
            report["chart_control_agent"] = agent | {"status": "CHART_CONFLICT"}
            return self._with_agent_chain(report)

        report["chart_control"] = {
            "status": "OBSERVED",
            "reason": "مشاهدهٔ نمودار با شواهد فنیِ دارای نام مشترک ناسازگاری جهت نداشت.",
            "observation": checked,
            "findings": [],
        }
        report["chart_control_agent"] = agent | {"status": "OBSERVED"}
        return self._with_agent_chain(report)

    def _validate_observation(self, symbol: dict[str, Any], observation: object) -> dict[str, Any]:
        if not isinstance(observation, dict):
            raise ValueError("مشاهدهٔ نمودار باید یک شیء JSON باشد.")
        required = ("symbol", "source", "collected_at", "timezone", "timeframe", "indicators")
        missing = [key for key in required if key not in observation]
        if missing:
            raise ValueError("فیلدهای لازم مشاهدهٔ نمودار وجود ندارند: " + ", ".join(missing))
        if observation["symbol"] != symbol["symbol"]:
            raise ValueError("نماد مشاهدهٔ نمودار با نماد دادهٔ بازار یکسان نیست.")
        if not isinstance(observation["source"], str) or not observation["source"].startswith("https://"):
            raise ValueError("منبع نمودار باید نشانی HTTPS باشد.")
        host = urlparse(observation["source"]).hostname
        if not host or host.lower() not in self.allowed_hosts:
            raise ValueError("میزبان نمودار در فهرست منابع تأییدشدهٔ محلی نیست.")
        if not isinstance(observation["collected_at"], str):
            raise ValueError("زمان مشاهدهٔ نمودار نامعتبر است.")
        try:
            datetime.fromisoformat(observation["collected_at"].replace("Z", "+00:00"))
        except ValueError as error:
            raise ValueError("زمان مشاهدهٔ نمودار نامعتبر است.") from error
        if observation["timezone"] != "Asia/Tehran":
            raise ValueError("منطقهٔ زمانی مشاهدهٔ نمودار باید Asia/Tehran باشد.")
        if observation["timeframe"] != symbol["market_metadata"]["timeframe"]:
            raise ValueError("تایم‌فریم نمودار با تایم‌فریم دادهٔ بازار یکسان نیست.")
        indicators = observation["indicators"]
        if not isinstance(indicators, list) or not indicators:
            raise ValueError("حداقل یک اندیکاتور نمودار لازم است.")
        checked = []
        for item in indicators:
            if not isinstance(item, dict):
                raise ValueError("یکی از اندیکاتورهای نمودار نامعتبر است.")
            name = item.get("name")
            direction = item.get("direction")
            if not isinstance(name, str) or name.upper() not in SUPPORTED_INDICATORS:
                raise ValueError("نام اندیکاتور نمودار در فهرست مجاز نیست.")
            if direction not in VALID_DIRECTIONS:
                raise ValueError("جهت اندیکاتور نمودار نامعتبر است.")
            if not isinstance(item.get("parameters", {}), dict):
                raise ValueError("پارامترهای اندیکاتور نمودار نامعتبر است.")
            checked.append({"name": name.upper(), "direction": direction, "parameters": item.get("parameters", {})})
        return {
            "symbol": observation["symbol"], "source": observation["source"],
            "collected_at": observation["collected_at"], "timezone": observation["timezone"],
            "timeframe": observation["timeframe"], "indicators": checked,
        }

    @staticmethod
    def _block_quality(symbol: dict[str, Any], finding: dict[str, Any]) -> None:
        quality = symbol.setdefault("quality", {"status": "QA_BLOCKED", "findings": []})
        quality["status"] = "QA_BLOCKED"
        quality.setdefault("findings", []).append(finding)

    @staticmethod
    def _with_agent_chain(report: dict[str, Any]) -> dict[str, Any]:
        chain = list(report.get("agents", []))
        chain.append(report["chart_control_agent"])
        report["agents"] = chain
        return report
