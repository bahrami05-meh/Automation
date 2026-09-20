"""پروزه اتوماسیون بورسی — تحلیل نمونه و دروازهٔ کیفیت جک.

این ماژول هیچ اتصال کارگزاری، سفارش‌گذاری یا دادهٔ واقعی پرتفوی ندارد.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
import re
from typing import Any


VALID_DIRECTIONS = {"bullish", "bearish", "neutral"}
SYMBOL_PATTERN = re.compile(r"^[A-Za-zآ-ی٠-٩۰-۹][A-Za-zآ-ی٠-٩۰-۹0-9 _-]{0,19}$")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def quality_supervisor(indicators: list[dict[str, Any]]) -> dict[str, Any]:
    """کنترل هم‌پوشانی و تعارض اندیکاتورها، بدون اصلاح خاموش داده."""
    findings: list[dict[str, Any]] = []
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)

    for item in indicators:
        required = ("name", "family", "timeframe", "direction", "weight")
        missing = [key for key in required if key not in item]
        if missing or item.get("direction") not in VALID_DIRECTIONS:
            findings.append({
                "code": "INDICATOR_INVALID",
                "severity": "blocker",
                "message": "مشخصات یکی از اندیکاتورها ناقص یا نامعتبر است.",
                "details": {"indicator": item.get("name", "نامشخص"), "missing": missing},
            })
            continue
        grouped[(item["family"], item["timeframe"])].append(item)

    accepted_score = 0.0
    for (family, timeframe), group in grouped.items():
        directions = {item["direction"] for item in group if item["direction"] != "neutral"}
        family_weight = max(float(item["weight"]) for item in group)
        # خانوادهٔ هم‌پوشان فقط یک بار با سقف بیشترین وزن اثر می‌گذارد.
        if len(group) > 1:
            findings.append({
                "code": "INDICATOR_OVERLAP",
                "severity": "warning",
                "message": "اندیکاتورهای هم‌خانواده فقط یک بار در امتیاز لحاظ شدند.",
                "details": {"family": family, "timeframe": timeframe,
                            "indicators": [item["name"] for item in group], "weight_cap": family_weight},
            })
        if len(directions) > 1:
            findings.append({
                "code": "INDICATOR_CONFLICT",
                "severity": "blocker",
                "message": "تعارض مؤثر بین اندیکاتورهای هم‌خانواده تشخیص داده شد.",
                "details": {
                    "family": family,
                    "timeframe": timeframe,
                    "signals": [{"name": item["name"], "direction": item["direction"],
                                 "parameters": item.get("parameters", {})} for item in group],
                },
            })
            continue
        direction = next(iter(directions), "neutral")
        accepted_score += family_weight * {"bullish": 1, "bearish": -1, "neutral": 0}[direction]

    blockers = [item for item in findings if item["severity"] == "blocker"]
    return {
        "status": "QA_BLOCKED" if blockers else "QA_PASSED",
        "score": round(accepted_score, 2),
        "findings": findings,
        "rule_version": "JUP-010",
        "checked_at": _utc_now(),
    }


def build_demo_report() -> dict[str, Any]:
    """گزارش آزمایشیِ بدون دادهٔ بازار یا پرتفوی واقعی."""
    indicators = [
        {"name": "RSI", "family": "momentum", "timeframe": "daily", "direction": "bullish",
         "weight": 2.0, "parameters": {"period": 14}},
        {"name": "MACD", "family": "momentum", "timeframe": "daily", "direction": "bullish",
         "weight": 2.0, "parameters": {"fast": 12, "slow": 26, "signal": 9}},
        {"name": "SMA", "family": "trend", "timeframe": "daily", "direction": "neutral",
         "weight": 1.0, "parameters": {"period": 50}},
    ]
    qa = quality_supervisor(indicators)
    return {
        "project": "پروزه اتوماسیون بورسی",
        "mode": "DEMO_ONLY",
        "generated_at": _utc_now(),
        "portfolio_source": "نمونهٔ داخلی؛ هیچ دادهٔ شخصی یا کارگزاری خوانده نشده است.",
        "symbols": [{
            "symbol": "DEMO",
            "data_status": "DEMO_ONLY",
            "indicators": indicators,
            "quality": qa,
            "jack_decision": "WATCHLIST" if qa["status"] == "QA_PASSED" else "DATA_BLOCKED",
            "reason": "نمونهٔ فنی برای بررسی زنجیرهٔ تحلیل؛ فاقد دادهٔ واقعی بازار و پرتفوی.",
        }],
        "disclaimer": "این خروجی صرفاً برای محیط آزمایشی است، اجرای زنده مجاز نیست و بررسی انسانی الزامی است.",
    }


def build_symbol_request(symbol: str) -> dict[str, Any]:
    """اعتبارسنجی نام نماد؛ دریافت واقعی داده عمداً در این مرحله اجرا نمی‌شود."""
    normalized = " ".join(symbol.strip().split())
    if not SYMBOL_PATTERN.fullmatch(normalized):
        raise ValueError("نام نماد باید ۱ تا ۲۰ نویسهٔ فارسی یا لاتین داشته باشد.")
    return {
        "project": "پروزه اتوماسیون بورسی",
        "mode": "SYMBOL_REQUEST_ONLY",
        "generated_at": _utc_now(),
        "symbols": [{
            "symbol": normalized,
            "data_status": "DATA_BLOCKED",
            "quality": {"status": "QA_BLOCKED", "findings": [{
                "code": "MARKET_SOURCE_NOT_CONNECTED",
                "severity": "blocker",
                "message": "نماد ثبت شد، اما دریافت دادهٔ بازار و خواندن مرورگر هنوز به برنامه متصل نشده است.",
            }]},
            "jack_decision": "DATA_BLOCKED",
            "reason": "برای جلوگیری از حدس‌زدن، تا دریافت دادهٔ معتبر هیچ تحلیل یا امتیازدهی انجام نمی‌شود.",
        }],
        "disclaimer": "این خروجی صرفاً برای محیط آزمایشی است، اجرای زنده مجاز نیست و بررسی انسانی الزامی است.",
    }
