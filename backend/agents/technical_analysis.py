"""پروزه اتوماسیون بورسی — ایجنت تحلیل تکنیکال."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

AGENT_NAME = "ایجنت تکنیکال"
AGENT_ID = "technical-analysis-agent"
AGENT_VERSION = "0.2"
TEHRAN = timezone(timedelta(hours=3, minutes=30), "Asia/Tehran")


def _run_metadata() -> dict[str, str]:
    return {"name": AGENT_NAME, "id": AGENT_ID, "version": AGENT_VERSION,
            "run_id": f"taa-{uuid4().hex}", "started_at": datetime.now(TEHRAN).isoformat(timespec="seconds")}


class TechnicalAnalysisAgent:
    """گزارش روند، مومنتوم، سطوح و سیگنال مشروط؛ بدون سفارش مالی."""

    def analyze(self, report: dict[str, Any]) -> dict[str, Any]:
        agent, symbol = _run_metadata(), report["symbols"][0]
        if symbol.get("data_status") != "VALID" or symbol.get("quality", {}).get("status") != "QA_PASSED":
            report["technical"] = {"status": "SKIPPED", "reason": "دادهٔ معتبر و تأییدشدهٔ ناظر کیفیت برای تحلیل تکنیکال موجود نیست.",
                "overall_signal": "NOT_AVAILABLE", "evidence": [], "levels": [],
                "clear_signal": {"status": "NOT_AVAILABLE", "direction": "NONE", "trigger": None, "invalidation": None}}
            report["technical_agent"] = agent | {"status": "SKIPPED"}
            return self._with_agent_chain(report)

        indicators = symbol.get("indicators", [])
        evidence = [{"name": item["name"], "family": item["family"], "timeframe": item["timeframe"], "direction": item["direction"], "parameters": item.get("parameters", {})}
                    for item in indicators if item.get("family") in {"trend", "momentum"}]
        directions = {item["direction"] for item in evidence}
        if directions == {"bullish"}:
            overall, summary, direction = "ALIGNED_BULLISH", "روند و مومنتوم هم‌جهت صعودی‌اند؛ این فقط مشاهدهٔ فنی است، نه پیشنهاد خرید.", "BULLISH_CONFIRMATION"
        elif directions == {"bearish"}:
            overall, summary, direction = "ALIGNED_BEARISH", "روند و مومنتوم هم‌جهت نزولی‌اند؛ این فقط مشاهدهٔ فنی است، نه پیشنهاد فروش.", "BEARISH_CONFIRMATION"
        elif "bullish" in directions and "bearish" in directions:
            overall, summary, direction = "MIXED", "شواهد فنی هم‌جهت نیستند؛ سیگنال شفاف ایجاد نمی‌شود.", "NO_CLEAR_SIGNAL"
        else:
            overall, summary, direction = "NEUTRAL_OR_INCOMPLETE", "شواهد فنی خنثی یا ناکامل است؛ سیگنال شفاف ایجاد نمی‌شود.", "NO_CLEAR_SIGNAL"

        closes = [float(value) for value in symbol.get("market_metadata", {}).get("recent_closes", [])]
        last_close = float(symbol.get("last_close", 0))
        window = closes[-20:] or [last_close]
        support, resistance = min(window), max(window)
        sma = next((float(item["parameters"]["value"]) for item in indicators if item.get("name") == "SMA"), None)
        rsi = next((float(item["parameters"]["value"]) for item in indicators if item.get("name") == "RSI"), None)
        report["technical"] = {"status": "ANALYZED", "overall_signal": overall, "summary": summary, "evidence": evidence,
            "levels": [{"name": "SUPPORT", "value": round(support, 4), "basis": "minimum close of recent window"},
                       {"name": "RESISTANCE", "value": round(resistance, 4), "basis": "maximum close of recent window"},
                       *([{"name": "SMA20", "value": round(sma, 4), "basis": "calculated indicator"}] if sma is not None else [])],
            "clear_signal": {"status": "OBSERVED", "direction": direction,
                             "trigger": f"عبور و تثبیت بالای مقاومت {resistance}",
                             "invalidation": f"شکست و تثبیت زیر حمایت {support}",
                             "conditions": {"overall_signal": overall, "sma20": sma, "rsi14": rsi},
                             "note": "سیگنال فنی مشروط و آموزشی است؛ سفارش یا تضمین نتیجه نیست."}}
        report["technical_agent"] = agent | {"status": "ANALYZED"}
        return self._with_agent_chain(report)

    @staticmethod
    def _with_agent_chain(report: dict[str, Any]) -> dict[str, Any]:
        report["agents"] = list(report.get("agents", [])) + [report["technical_agent"]]
        return report
