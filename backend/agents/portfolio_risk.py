"""پروزه اتوماسیون بورسی — ایجنت ریسک پرتفوی."""
from __future__ import annotations
from math import floor
from typing import Any
from uuid import uuid4

class PortfolioRiskAgent:
    name = "ایجنت ریسک پرتفوی"
    def inspect(self, report: dict[str, Any], observation: object | None) -> dict[str, Any]:
        agent = {"name": self.name, "id": "portfolio-risk-agent", "version": "0.1", "run_id": f"pra-{uuid4().hex}"}
        symbol = report["symbols"][0]
        if symbol.get("data_status") != "VALID" or observation is None:
            reason = "تا پیش از دادهٔ معتبر بازار و ورودی ریسک، کنترل ریسک اجرا نمی‌شود."
            report["portfolio_risk"] = {"status": "SKIPPED", "reason": reason, "findings": [{"code": "RISK_INPUT_NOT_CONNECTED", "severity": "warning", "message": reason}]}
            report["portfolio_risk_agent"] = agent | {"status": "SKIPPED"}
            return self._chain(report)
        try:
            required = ("symbol", "price_unit", "account_equity", "available_cash", "risk_percent", "entry_price", "stop_loss", "fee_per_unit", "slippage_per_unit", "liquidity_cap_quantity")
            if not isinstance(observation, dict) or any(key not in observation for key in required): raise ValueError("فیلدهای لازم ریسک کامل نیستند.")
            if observation["symbol"] != symbol["symbol"] or observation["price_unit"] != symbol["market_metadata"]["price_unit"]: raise ValueError("نماد یا واحد ریسک با دادهٔ بازار یکسان نیست.")
            values = {key: float(observation[key]) for key in required[2:]}
            if any(value < 0 for value in values.values()) or not 0 < values["risk_percent"] <= 100 or values["entry_price"] <= 0 or values["stop_loss"] <= 0 or values["entry_price"] == values["stop_loss"]: raise ValueError("مقادیر ریسک نامعتبرند.")
        except (TypeError, ValueError) as error:
            finding = {"code": "RISK_OBSERVATION_INVALID", "severity": "blocker", "message": str(error)}
            report["portfolio_risk"] = {"status": "RISK_BLOCKED", "reason": str(error), "findings": [finding]}
            symbol["quality"]["status"] = "QA_BLOCKED"; symbol["quality"]["findings"].append(finding); symbol["data_status"] = symbol["jack_decision"] = "DATA_BLOCKED"
            report["portfolio_risk_agent"] = agent | {"status": "RISK_BLOCKED"}
            return self._chain(report)
        budget = values["account_equity"] * values["risk_percent"] / 100
        per_unit = abs(values["entry_price"] - values["stop_loss"]) + values["fee_per_unit"] + values["slippage_per_unit"]
        quantity = min(floor(budget / per_unit), floor(values["available_cash"] / values["entry_price"]), floor(values["liquidity_cap_quantity"]))
        report["portfolio_risk"] = {"status": "OBSERVED", "reason": "سقف یک پلهٔ آزمایشی فقط محاسبه شد؛ هیچ سفارش یا توصیه‌ای صادر نشده است.", "metrics": {"risk_budget": budget, "unit_risk": per_unit, "max_single_step_quantity": max(0, quantity), "required_capital": max(0, quantity) * values["entry_price"]}, "findings": []}
        report["portfolio_risk_agent"] = agent | {"status": "OBSERVED"}
        return self._chain(report)
    @staticmethod
    def _chain(report: dict[str, Any]) -> dict[str, Any]:
        report["agents"] = list(report.get("agents", [])) + [report["portfolio_risk_agent"]]
        return report
