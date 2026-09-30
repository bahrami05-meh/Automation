"""Strict JSON schemas for the read-only browser observation bridge."""
from __future__ import annotations

from datetime import datetime
from math import isfinite
from typing import Any

from backend.url_safety import safe_https_origin
from backend.numeric import finite_number

SENSITIVE = {"password", "pass", "otp", "token", "cookie", "session", "username", "user", "رمز", "کد", "نشست", "کوکی"}
MAX_DEPTH = 12
MAX_NODES = 20_000
MAX_LIST = 5_000
MAX_STRING = 4_096

TOP_KEYS = {"symbol", "market_snapshot", "chart_observation", "market_board_observation", "fundamental_observation", "risk_observation", "portfolio_observation", "bridge_nonce"}
MARKET_KEYS = {"symbol", "source", "collected_at", "timezone", "price_unit", "price_type", "timeframe", "ohlcv"}
OHLCV_KEYS = {"open", "high", "low", "close", "volume"}
CHART_KEYS = {"symbol", "source", "collected_at", "timezone", "timeframe", "indicators"}
INDICATOR_KEYS = {"name", "direction", "parameters"}
INDICATOR_PARAMETERS = {
    "SMA": {"period", "value"}, "RSI": {"period", "value"}, "MACD": {"fast", "slow", "signal", "value"},
    "ICHIMOKU": {"conversion", "base", "span_b", "displacement", "value"}, "ATR": {"period", "value"},
}
BOARD_KEYS = {"symbol", "source", "collected_at", "timezone", "price_unit", "market_status", "last_price", "volume", "average_volume_20", "individual_buy_volume", "individual_sell_volume", "legal_buy_volume", "legal_sell_volume", "buy_queue_value", "sell_queue_value", "individual_buy_count", "individual_sell_count", "legal_buy_count", "legal_sell_count", "trade_count", "turnover_value", "market_value", "best_bid_price", "best_ask_price"}
FUNDAMENTAL_KEYS = {"symbol", "source", "collected_at", "timezone", "fiscal_year_end", "financial_unit", "revenue", "net_profit", "operating_margin_percent", "price_to_earnings", "debt_to_equity", "events"}
EVENT_KEYS = {"event_type", "published_at"}
RISK_KEYS = {"symbol", "price_unit", "account_equity", "available_cash", "risk_percent", "entry_price", "stop_loss", "fee_per_unit", "slippage_per_unit", "liquidity_cap_quantity"}
PORTFOLIO_KEYS = {"source", "collected_at", "timezone", "price_unit", "holdings"}
HOLDING_KEYS = {"symbol", "quantity", "average_price", "last_price", "market_value"}


def _shape(value: object, *, depth: int = 0, budget: list[int] | None = None) -> None:
    if budget is None:
        budget = [0]
    budget[0] += 1
    if budget[0] > MAX_NODES or depth > MAX_DEPTH:
        raise ValueError("PAYLOAD_COMPLEXITY_LIMIT")
    if isinstance(value, dict):
        for key, child in value.items():
            if not isinstance(key, str) or len(key) > 128:
                raise ValueError("PAYLOAD_KEY_INVALID")
            lowered = key.casefold()
            if any(part in lowered for part in SENSITIVE):
                raise ValueError("SENSITIVE_FIELD_BLOCKED")
            _shape(child, depth=depth + 1, budget=budget)
    elif isinstance(value, list):
        if len(value) > MAX_LIST:
            raise ValueError("PAYLOAD_ARRAY_LIMIT")
        for child in value:
            _shape(child, depth=depth + 1, budget=budget)
    elif isinstance(value, str):
        if len(value) > MAX_STRING:
            raise ValueError("PAYLOAD_STRING_LIMIT")
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        finite_number(value)
    elif value is not None and not isinstance(value, (bool, int, float)):
        raise ValueError("JSON_VALUE_REQUIRED")


def _object(value: object, *, name: str, allowed: set[str], required: set[str]) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{name}_OBJECT_REQUIRED")
    unknown = sorted(set(value) - allowed)
    if unknown:
        raise ValueError(f"{name}_UNKNOWN_FIELDS")
    missing = sorted(required - set(value))
    if missing:
        raise ValueError(f"{name}_REQUIRED_FIELDS:{','.join(missing)}")
    return value


def _timestamp(value: object, name: str) -> None:
    if not isinstance(value, str):
        raise ValueError(f"{name}_TIMESTAMP_INVALID")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(f"{name}_TIMESTAMP_INVALID") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{name}_TIMESTAMP_OFFSET_REQUIRED")


def _source(value: object, name: str, hosts: set[str] | None) -> None:
    try:
        safe_https_origin(value, hosts)
    except ValueError as error:
        raise ValueError(f"{name}_{error}") from error


def validate_market_snapshot(snapshot: object, allowed_hosts: set[str] | None = None) -> dict[str, Any]:
    _shape(snapshot)
    data = _object(snapshot, name="MARKET", allowed=MARKET_KEYS, required=MARKET_KEYS)
    if not isinstance(data["symbol"], str) or not data["symbol"].strip():
        raise ValueError("MARKET_SYMBOL_INVALID")
    _source(data["source"], "MARKET", allowed_hosts)
    _timestamp(data["collected_at"], "MARKET")
    rows = data["ohlcv"]
    if not isinstance(rows, list) or len(rows) < 21 or len(rows) > MAX_LIST:
        raise ValueError("MARKET_OHLCV_LENGTH_INVALID")
    for index, row in enumerate(rows):
        _object(row, name=f"OHLCV_{index}", allowed=OHLCV_KEYS, required=OHLCV_KEYS)
        for key, value in row.items():
            if isinstance(value, bool) or not isinstance(value, (int, float, str)):
                raise ValueError(f"OHLCV_{key}_NUMBER_INVALID")
            if isinstance(value, str) and (not value.strip() or len(value) > 64):
                raise ValueError(f"OHLCV_{key}_NUMBER_INVALID")
    if data["timezone"] != "Asia/Tehran" or data["price_unit"] not in {"IRR", "IRT"} or data["price_type"] not in {"raw", "adjusted"} or data["timeframe"] != "daily":
        raise ValueError("MARKET_METADATA_INVALID")
    return data


def _validate_chart(value: object, market_symbol: str, market_timeframe: str, hosts: set[str] | None) -> None:
    data = _object(value, name="CHART", allowed=CHART_KEYS, required=CHART_KEYS)
    if data["symbol"] != market_symbol or data["timeframe"] != market_timeframe:
        raise ValueError("CHART_SYMBOL_OR_TIMEFRAME_MISMATCH")
    _source(data["source"], "CHART", hosts)
    _timestamp(data["collected_at"], "CHART")
    if data["timezone"] != "Asia/Tehran" or not isinstance(data["indicators"], list) or not 1 <= len(data["indicators"]) <= 32:
        raise ValueError("CHART_METADATA_OR_INDICATORS_INVALID")
    for index, item in enumerate(data["indicators"]):
        entry = _object(item, name=f"CHART_INDICATOR_{index}", allowed=INDICATOR_KEYS, required={"name", "direction"})
        name = entry["name"]
        if not isinstance(name, str) or name.upper() not in INDICATOR_PARAMETERS or entry["direction"] not in {"bullish", "bearish", "neutral"}:
            raise ValueError("CHART_INDICATOR_INVALID")
        params = entry.get("parameters", {})
        _object(params, name="CHART_PARAMETERS", allowed=INDICATOR_PARAMETERS[name.upper()], required=set())
        for key, param in params.items():
            if isinstance(param, bool) or not isinstance(param, (int, float)) or not isfinite(float(param)):
                raise ValueError(f"CHART_PARAMETER_{key}_INVALID")


def _validate_board(value: object, symbol: str, price_unit: str, hosts: set[str] | None) -> None:
    required = {"symbol", "source", "collected_at", "timezone", "price_unit", "market_status", "last_price", "volume", "average_volume_20", "individual_buy_volume", "individual_sell_volume", "legal_buy_volume", "legal_sell_volume", "buy_queue_value", "sell_queue_value"}
    data = _object(value, name="BOARD", allowed=BOARD_KEYS, required=required)
    if data["symbol"] != symbol or data["price_unit"] != price_unit:
        raise ValueError("BOARD_SYMBOL_OR_UNIT_MISMATCH")
    _source(data["source"], "BOARD", hosts)
    _timestamp(data["collected_at"], "BOARD")
    if data["timezone"] != "Asia/Tehran" or data["market_status"] not in {"open", "closed", "suspended"}:
        raise ValueError("BOARD_METADATA_INVALID")
    numeric_fields = BOARD_KEYS - {"symbol", "source", "collected_at", "timezone", "price_unit", "market_status"}
    for key in numeric_fields & set(data):
        finite_number(data[key])


def _validate_fundamental(value: object, symbol: str, hosts: set[str] | None) -> None:
    data = _object(value, name="FUNDAMENTAL", allowed=FUNDAMENTAL_KEYS, required=FUNDAMENTAL_KEYS)
    if data["symbol"] != symbol:
        raise ValueError("FUNDAMENTAL_SYMBOL_MISMATCH")
    _source(data["source"], "FUNDAMENTAL", hosts)
    _timestamp(data["collected_at"], "FUNDAMENTAL")
    if data["timezone"] != "Asia/Tehran" or data["financial_unit"] not in {"IRR", "IRT"} or not isinstance(data["fiscal_year_end"], str) or not data["fiscal_year_end"].strip():
        raise ValueError("FUNDAMENTAL_METADATA_INVALID")
    for key in ("revenue", "net_profit", "operating_margin_percent", "price_to_earnings", "debt_to_equity"):
        finite_number(data[key])
    events = data["events"]
    if not isinstance(events, list) or len(events) > 128:
        raise ValueError("FUNDAMENTAL_EVENTS_INVALID")
    for index, event in enumerate(events):
        item = _object(event, name=f"EVENT_{index}", allowed=EVENT_KEYS, required=EVENT_KEYS)
        if item["event_type"] not in {"financial_statement", "material_disclosure", "assembly", "capital_increase", "dividend", "suspension_notice"}:
            raise ValueError("FUNDAMENTAL_EVENT_TYPE_INVALID")
        _timestamp(item["published_at"], "EVENT")


def _validate_risk(value: object, symbol: str, unit: str) -> None:
    data = _object(value, name="RISK", allowed=RISK_KEYS, required=RISK_KEYS)
    if data["symbol"] != symbol or data["price_unit"] != unit:
        raise ValueError("RISK_SYMBOL_OR_UNIT_MISMATCH")
    for key in RISK_KEYS - {"symbol", "price_unit"}:
        finite_number(data[key])


def _validate_portfolio(value: object, hosts: set[str] | None) -> None:
    data = _object(value, name="PORTFOLIO", allowed=PORTFOLIO_KEYS, required=PORTFOLIO_KEYS)
    _source(data["source"], "PORTFOLIO", hosts)
    _timestamp(data["collected_at"], "PORTFOLIO")
    if data["timezone"] != "Asia/Tehran" or data["price_unit"] not in {"IRR", "IRT"}:
        raise ValueError("PORTFOLIO_METADATA_INVALID")
    holdings = data["holdings"]
    if not isinstance(holdings, list) or not 1 <= len(holdings) <= 512:
        raise ValueError("PORTFOLIO_HOLDINGS_INVALID")
    for index, holding in enumerate(holdings):
        item = _object(holding, name=f"HOLDING_{index}", allowed=HOLDING_KEYS, required=HOLDING_KEYS)
        for key in HOLDING_KEYS - {"symbol"}:
            finite_number(item[key])


def validate_browser_payload(payload: object, *, market_hosts: set[str] | None = None,
                             chart_hosts: set[str] | None = None, board_hosts: set[str] | None = None,
                             fundamental_hosts: set[str] | None = None, portfolio_hosts: set[str] | None = None) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("BROWSER_PAYLOAD_OBJECT_REQUIRED")
    _shape(payload)
    data = _object(payload, name="BROWSER_PAYLOAD", allowed=TOP_KEYS, required={"symbol", "market_snapshot", "bridge_nonce"})
    if not isinstance(data["symbol"], str) or not data["symbol"].strip():
        raise ValueError("BROWSER_SYMBOL_INVALID")
    nonce = data["bridge_nonce"]
    if not isinstance(nonce, str) or not 1 <= len(nonce) <= 128 or not nonce.strip():
        raise ValueError("BROWSER_NONCE_INVALID")
    market = validate_market_snapshot(data["market_snapshot"], market_hosts)
    if market["symbol"] != data["symbol"]:
        raise ValueError("BROWSER_MARKET_SYMBOL_MISMATCH")
    if "chart_observation" in data and data["chart_observation"] is not None:
        _validate_chart(data["chart_observation"], data["symbol"], market["timeframe"], chart_hosts)
    if "market_board_observation" in data and data["market_board_observation"] is not None:
        _validate_board(data["market_board_observation"], data["symbol"], market["price_unit"], board_hosts)
    if "fundamental_observation" in data and data["fundamental_observation"] is not None:
        _validate_fundamental(data["fundamental_observation"], data["symbol"], fundamental_hosts)
    if "risk_observation" in data and data["risk_observation"] is not None:
        _validate_risk(data["risk_observation"], data["symbol"], market["price_unit"])
    if "portfolio_observation" in data and data["portfolio_observation"] is not None:
        _validate_portfolio(data["portfolio_observation"], portfolio_hosts)
    return data


def validate_market_api_payload(payload: object, *, market_hosts: set[str] | None = None,
                                chart_hosts: set[str] | None = None, board_hosts: set[str] | None = None,
                                fundamental_hosts: set[str] | None = None, portfolio_hosts: set[str] | None = None) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("MARKET_API_PAYLOAD_OBJECT_REQUIRED")
    _shape(payload)
    allowed = MARKET_KEYS | {"chart_observation", "market_board_observation", "fundamental_observation", "risk_observation", "portfolio_observation"}
    data = _object(payload, name="MARKET_API_PAYLOAD", allowed=allowed, required=MARKET_KEYS)
    market_payload = {key: data[key] for key in MARKET_KEYS}
    market = validate_market_snapshot(market_payload, market_hosts)
    symbol = market["symbol"]
    for key, hosts in (("chart_observation", chart_hosts), ("market_board_observation", board_hosts),
                       ("fundamental_observation", fundamental_hosts), ("portfolio_observation", portfolio_hosts)):
        if key in data and data[key] is not None:
            if key == "chart_observation":
                _validate_chart(data[key], symbol, market["timeframe"], hosts)
            elif key == "market_board_observation":
                _validate_board(data[key], symbol, market["price_unit"], hosts)
            elif key == "fundamental_observation":
                _validate_fundamental(data[key], symbol, hosts)
            else:
                _validate_portfolio(data[key], hosts)
    if "risk_observation" in data and data["risk_observation"] is not None:
        _validate_risk(data["risk_observation"], symbol, market["price_unit"])
    return data


def validate_symbol_request_payload(payload: object) -> dict[str, str]:
    if not isinstance(payload, dict):
        raise ValueError("SYMBOL_REQUEST_OBJECT_REQUIRED")
    _shape(payload)
    data = _object(payload, name="SYMBOL_REQUEST", allowed={"symbol"}, required={"symbol"})
    if not isinstance(data["symbol"], str) or not data["symbol"].strip():
        raise ValueError("SYMBOL_REQUEST_SYMBOL_INVALID")
    return data
