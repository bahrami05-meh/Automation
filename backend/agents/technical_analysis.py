"""پروزه اتوماسیون بورسی — ایجنت تحلیل تکنیکال.

این ایجنت فقط بر مبنای خروجی اعتبارسنجی‌شدهٔ ایجنت دریافت کار می‌کند و هیچ
پیشنهاد خرید، فروش یا اقدام مالی صادر نمی‌کند.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4


AGENT_NAME = "ایجنت تکنیکال"
AGENT_ID = "technical-analysis-agent"
AGENT_VERSION = "0.1"
TEHRAN = timezone(timedelta(hours=3, minutes=30), "Asia/Tehran")


def _run_metadata() -> dict[str, str]:
    return {
        "name": AGENT_NAME,
        "id": AGENT_ID,
        "version": AGENT_VERSION,
        "run_id": f"taa-{uuid4().hex}",
        "started_at": datetime.now(TEHRAN).isoformat(timespec="seconds"),
    }


class TechnicalAnalysisAgent:
    """جمع‌بندی شفاف روند و مومنتوم، بدون تبدیل آن به دستور معامله."""

    def analyze(self, report: dict[str, Any]) -> dict[str, Any]:
        agent = _run_metadata()
        symbol = report["symbols"][0]
        is_valid = symbol.get("data_status") == "VALID"
        qa_passed = symbol.get("quality", {}).get("status") == "QA_PASSED"

        if not is_valid or not qa_passed:
            report["technical"] = {
                "status": "SKIPPED",
                "reason": "دادهٔ معتبر و تأییدشدهٔ ناظر کیفیت برای تحلیل تکنیکال موجود نیست.",
                "overall_signal": "NOT_AVAILABLE",
                "evidence": [],
            }
            report["technical_agent"] = agent | {"status": "SKIPPED"}
            return self._with_agent_chain(report)

        indicators = symbol.get("indicators", [])
        evidence = [
            {
                "name": item["name"],
                "family": item["family"],
                "timeframe": item["timeframe"],
                "direction": item["direction"],
                "parameters": item.get("parameters", {}),
            }
            for item in indicators
            if item.get("family") in {"trend", "momentum"}
        ]
        directions = {item["direction"] for item in evidence}
        if directions == {"bullish"}:
            overall_signal = "ALIGNED_BULLISH"
            summary = "روند و مومنتومِ محاسبه‌شده هم‌جهت صعودی هستند؛ این صرفاً مشاهدهٔ فنی است، نه پیشنهاد خرید."
        elif directions == {"bearish"}:
            overall_signal = "ALIGNED_BEARISH"
            summary = "روند و مومنتومِ محاسبه‌شده هم‌جهت نزولی هستند؛ این صرفاً مشاهدهٔ فنی است، نه پیشنهاد فروش."
        elif "bullish" in directions and "bearish" in directions:
            overall_signal = "MIXED"
            summary = "شواهد فنی هم‌جهت نیستند؛ نتیجهٔ تکنیکال مختلط است و برای تصمیم کافی نیست."
        else:
            overall_signal = "NEUTRAL_OR_INCOMPLETE"
            summary = "شواهد فنی خنثی یا ناکامل است و برای تصمیم کافی نیست."

        report["technical"] = {
            "status": "ANALYZED",
            "overall_signal": overall_signal,
            "summary": summary,
            "evidence": evidence,
        }
        report["technical_agent"] = agent | {"status": "ANALYZED"}
        return self._with_agent_chain(report)

    @staticmethod
    def _with_agent_chain(report: dict[str, Any]) -> dict[str, Any]:
        chain = []
        if report.get("agent"):
            chain.append(report["agent"])
        chain.append(report["technical_agent"])
        report["agents"] = chain
        return report
