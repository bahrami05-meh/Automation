"""پروزه اتوماسیون بورسی — اعتبارسنجی و تحلیل دادهٔ بازارِ واردشده.

داده باید از منبع تأییدشده و همراه با زمان/واحد وارد شود. این ماژول هیچ
اتصال شبکه یا برداشت داده از کارگزاری انجام نمی‌دهد.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlparse

from backend.jack_core import build_symbol_request, quality_supervisor


REQUIRED_METADATA = ("symbol", "source", "collected_at", "timezone", "price_unit", "price_type", "timeframe", "ohlcv")


def _parse_time(value: object) -> None:
    if not isinstance(value, str):
        raise ValueError("زمان دریافت داده نامعتبر است.")
    datetime.fromisoformat(value.replace("Z", "+00:00"))


def _closes(snapshot: dict[str, Any]) -> list[float]:
    rows = snapshot["ohlcv"]
    if not isinstance(rows, list) or len(rows) < 21:
        raise ValueError("حداقل ۲۱ ردیف OHLCV برای تحلیل نمونه لازم است.")
    closes: list[float] = []
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise ValueError(f"ردیف {index + 1} OHLCV نامعتبر است.")
        try:
            open_price = float(row["open"])
            high = float(row["high"])
            low = float(row["low"])
            close = float(row["close"])
            volume = float(row["volume"])
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError(f"ردیف {index + 1} OHLCV ناقص است.") from error
        if min(open_price, high, low, close, volume) < 0 or high < max(open_price, close) or low > min(open_price, close):
            raise ValueError(f"ردیف {index + 1} OHLCV ناسازگار است.")
        closes.append(close)
    return closes


def validate_snapshot(snapshot: object, allowed_hosts: set[str] | None = None) -> dict[str, Any]:
    if not isinstance(snapshot, dict):
        raise ValueError("بستهٔ داده باید یک شیء JSON باشد.")
    missing = [key for key in REQUIRED_METADATA if key not in snapshot]
    if missing:
        raise ValueError("فیلدهای لازم وجود ندارند: " + ", ".join(missing))
    symbol_report = build_symbol_request(str(snapshot["symbol"]))
    symbol = symbol_report["symbols"][0]["symbol"]
    if not isinstance(snapshot["source"], str) or not snapshot["source"].startswith("https://"):
        raise ValueError("منبع باید یک نشانی HTTPS باشد.")
    source_host = urlparse(snapshot["source"]).hostname
    if not source_host:
        raise ValueError("میزبان منبع نامعتبر است.")
    if allowed_hosts is not None and source_host.lower() not in allowed_hosts:
        raise ValueError("میزبان منبع در فهرست منابع تأییدشدهٔ محلی نیست.")
    _parse_time(snapshot["collected_at"])
    if snapshot["timezone"] != "Asia/Tehran":
        raise ValueError("منطقهٔ زمانی باید Asia/Tehran باشد.")
    if snapshot["price_unit"] not in {"IRR", "IRT"}:
        raise ValueError("واحد قیمت باید IRR یا IRT باشد.")
    if snapshot["price_type"] not in {"raw", "adjusted"}:
        raise ValueError("نوع قیمت باید raw یا adjusted باشد.")
    if not isinstance(snapshot["timeframe"], str) or not snapshot["timeframe"]:
        raise ValueError("تایم‌فریم نامعتبر است.")
    return {**snapshot, "symbol": symbol, "closes": _closes(snapshot)}


def _rsi(closes: list[float], period: int = 14) -> float:
    changes = [closes[index] - closes[index - 1] for index in range(1, len(closes))]
    window = changes[-period:]
    gains = sum(max(change, 0) for change in window) / period
    losses = sum(max(-change, 0) for change in window) / period
    if losses == 0:
        return 100.0
    relative_strength = gains / losses
    return 100 - (100 / (1 + relative_strength))


def build_market_report(snapshot: object, allowed_hosts: set[str] | None = None) -> dict[str, Any]:
    """تحلیل آموزشیِ دادهٔ واردشده؛ خروجی هرگز توصیهٔ خرید یا فروش نیست."""
    data = validate_snapshot(snapshot, allowed_hosts)
    closes = data.pop("closes")
    last_close = closes[-1]
    sma20 = sum(closes[-20:]) / 20
    rsi14 = _rsi(closes)
    trend_direction = "bullish" if last_close > sma20 else "bearish" if last_close < sma20 else "neutral"
    momentum_direction = "bullish" if rsi14 > 55 else "bearish" if rsi14 < 45 else "neutral"
    indicators = [
        {"name": "SMA", "family": "trend", "timeframe": data["timeframe"], "direction": trend_direction,
         "weight": 1.0, "parameters": {"period": 20, "value": round(sma20, 4)}},
        {"name": "RSI", "family": "momentum", "timeframe": data["timeframe"], "direction": momentum_direction,
         "weight": 1.0, "parameters": {"period": 14, "value": round(rsi14, 2)}},
    ]
    qa = quality_supervisor(indicators)
    return {
        "project": "پروزه اتوماسیون بورسی",
        "mode": "LOCAL_MARKET_SNAPSHOT",
        "generated_at": datetime.now(timezone(timedelta(hours=3, minutes=30), "Asia/Tehran")).isoformat(timespec="seconds"),
        "portfolio_source": "دادهٔ بازار واردشده در حافظهٔ محلی؛ هیچ دادهٔ پرتفوی یا کارگزاری دریافت نشد.",
        "symbols": [{
            "symbol": data["symbol"],
            "data_status": "VALID" if qa["status"] == "QA_PASSED" else "DATA_BLOCKED",
            "market_metadata": {key: data[key] for key in ("source", "collected_at", "timezone", "price_unit", "price_type", "timeframe")},
            "last_close": last_close,
            "indicators": indicators,
            "quality": qa,
            "jack_decision": "WATCHLIST" if qa["status"] == "QA_PASSED" else "DATA_BLOCKED",
            "reason": "دادهٔ بازار اعتبارسنجی شد؛ تحلیل بنیادی، تابلو و ریسک پرتفوی هنوز به این مرحله متصل نیستند.",
        }],
        "disclaimer": "این خروجی صرفاً برای محیط آزمایشی است، اجرای زنده مجاز نیست و بررسی انسانی الزامی است.",
    }
