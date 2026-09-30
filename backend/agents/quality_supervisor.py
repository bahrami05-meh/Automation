"""پروزه اتوماسیون بورسی — ناظر کیفیت مستقل."""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4
from backend.jack_core import quality_supervisor
from backend.freshness import validate_collected_at, POLICY_VERSION

class QualitySupervisorAgent:
    name = "ایجنت ناظر کیفیت"
    def inspect(self, report: dict[str, Any]) -> dict[str, Any]:
        agent = {"name": self.name, "id": "quality-supervisor-agent", "version": "0.1", "run_id": f"qsa-{uuid4().hex}", "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
        symbol = report["symbols"][0]
        findings = []
        recalculated = quality_supervisor(symbol.get("indicators", []))
        findings.extend(recalculated.get("findings", []))
        if symbol.get("data_status") == "VALID" and symbol.get("quality", {}).get("status") != recalculated.get("status"):
            findings.append({"code": "QUALITY_STATUS_MISMATCH", "severity": "blocker", "message": "وضعیت کیفیت اولیه با بازاجرای مستقل یکسان نیست."})
        for key in ("technical_agent", "chart_control_agent", "market_board_agent", "fundamental_agent", "portfolio_risk_agent", "browser_portfolio_agent"):
            if report.get(key, {}).get("status") in {"BOARD_BLOCKED", "FUNDAMENTAL_BLOCKED", "RISK_BLOCKED", "CHART_CONFLICT", "CHART_BLOCKED", "PORTFOLIO_BLOCKED"}:
                findings.append({"code": "SPECIALIST_BLOCKED", "severity": "blocker", "message": f"خروجی {key} مسدود است."})
        timestamp_sources = [("market", symbol.get("market_metadata", {}))]
        for key, kind in (("market_board", "board"), ("chart_control", "chart"), ("fundamental", "fundamental")):
            specialist = report.get(key, {})
            if specialist.get("status") in {"OBSERVED", "MARKET_CLOSED"}:
                timestamp_sources.append((kind, specialist.get("observation", {})))
        if report.get("portfolio_capture", {}).get("status") == "PORTFOLIO_CAPTURED":
            timestamp_sources.append(("portfolio", report["portfolio_capture"]))
        if symbol.get("data_status") == "VALID":
            for kind, metadata in timestamp_sources:
                try:
                    if not isinstance(metadata, dict) or metadata.get("timezone") != "Asia/Tehran":
                        raise ValueError("COLLECTION_TIMEZONE_REQUIRED")
                    validate_collected_at(metadata.get("collected_at"), kind)
                except ValueError as error:
                    findings.append({"code": "FINAL_FRESHNESS_BLOCKED", "severity": "blocker", "message": str(error), "source_kind": kind})
        blockers = [item for item in findings if item.get("severity") == "blocker"]
        if symbol.get("data_status") != "VALID":
            findings.append({"code": "UPSTREAM_DATA_BLOCKED", "severity": "blocker", "message": "منبع یا دادهٔ معتبر بازار هنوز به بستهٔ تحلیل نرسیده است."})
        status = "QA_BLOCKED" if blockers or symbol.get("data_status") != "VALID" else "QA_PASSED"
        report["quality_supervisor"] = {"status": status, "rule_version": "JUP-009/JUP-010", "freshness_policy": POLICY_VERSION, "recalculated": recalculated, "findings": findings}
        report["quality_supervisor_agent"] = agent | {"status": status}
        report["agents"] = list(report.get("agents", [])) + [report["quality_supervisor_agent"]]
        if status == "QA_BLOCKED":
            symbol["quality"]["status"] = "QA_BLOCKED"
            symbol["quality"].setdefault("findings", []).extend(findings)
            symbol["data_status"] = symbol["jack_decision"] = "DATA_BLOCKED"
            symbol["reason"] = "ناظر کیفیت مستقل، ناسازگاری یا نقص قابل‌توجه در بستهٔ تحلیل پیدا کرد."
        return report
