"""پروزه اتوماسیون بورسی — ناظر کیفیت مستقل."""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4
from backend.jack_core import quality_supervisor

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
        for key in ("technical_agent", "market_board_agent", "fundamental_agent", "portfolio_risk_agent"):
            if report.get(key, {}).get("status") in {"BOARD_BLOCKED", "FUNDAMENTAL_BLOCKED", "RISK_BLOCKED", "CHART_CONFLICT"}:
                findings.append({"code": "SPECIALIST_BLOCKED", "severity": "blocker", "message": f"خروجی {key} مسدود است."})
        blockers = [item for item in findings if item.get("severity") == "blocker"]
        status = "QA_BLOCKED" if blockers else "QA_PASSED"
        report["quality_supervisor"] = {"status": status, "rule_version": "JUP-009/JUP-010", "recalculated": recalculated, "findings": findings}
        report["quality_supervisor_agent"] = agent | {"status": status}
        report["agents"] = list(report.get("agents", [])) + [report["quality_supervisor_agent"]]
        if status == "QA_BLOCKED":
            symbol["quality"]["status"] = "QA_BLOCKED"
            symbol["quality"].setdefault("findings", []).extend(findings)
            symbol["data_status"] = symbol["jack_decision"] = "DATA_BLOCKED"
            symbol["reason"] = "ناظر کیفیت مستقل، ناسازگاری یا نقص قابل‌توجه در بستهٔ تحلیل پیدا کرد."
        return report
