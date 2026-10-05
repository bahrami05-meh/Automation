"""Descriptive, in-memory portfolio totals derived from a validated snapshot."""
from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, localcontext
from typing import Any


_CENT = Decimal("0.01")


def _decimal(value: object, field: str) -> Decimal:
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as error:
        raise ValueError(f"PORTFOLIO_SUMMARY_INVALID_{field.upper()}") from error
    if not number.is_finite():
        raise ValueError(f"PORTFOLIO_SUMMARY_INVALID_{field.upper()}")
    return number


def _rounded(value: Decimal) -> float:
    with localcontext() as context:
        context.prec = 160
        return float(value.quantize(_CENT, rounding=ROUND_HALF_UP))


def summarize_portfolio(holdings: object) -> dict[str, Any]:
    """Calculate snapshot value, allocation, and clearly labeled P/L estimates.

    Allocation uses the broker-reported market value. Estimated cost and P/L use
    quantity, average purchase price, and last price from the same snapshot.
    """
    if not isinstance(holdings, list) or not holdings:
        raise ValueError("PORTFOLIO_SUMMARY_HOLDINGS_REQUIRED")

    checked: list[dict[str, Any]] = []
    symbols: set[str] = set()
    total_market_value = Decimal(0)
    total_cost = Decimal(0)
    total_unrealized = Decimal(0)

    with localcontext() as context:
        context.prec = 160
        for holding in holdings:
            if not isinstance(holding, dict):
                raise ValueError("PORTFOLIO_SUMMARY_HOLDING_INVALID")
            symbol = holding.get("symbol")
            if not isinstance(symbol, str) or not symbol or symbol in symbols:
                raise ValueError("PORTFOLIO_SUMMARY_SYMBOL_INVALID")
            quantity = _decimal(holding.get("quantity"), "quantity")
            average_price = _decimal(holding.get("average_price"), "average_price")
            last_price = _decimal(holding.get("last_price"), "last_price")
            market_value = _decimal(holding.get("market_value"), "market_value")
            if min(quantity, average_price, last_price, market_value) < 0:
                raise ValueError("PORTFOLIO_SUMMARY_NEGATIVE_VALUE")

            cost_basis = quantity * average_price
            unrealized_pnl = quantity * (last_price - average_price)
            checked.append({
                "symbol": symbol,
                "market_value": market_value,
                "cost_basis": cost_basis,
                "unrealized_pnl": unrealized_pnl,
            })
            symbols.add(symbol)
            total_market_value += market_value
            total_cost += cost_basis
            total_unrealized += unrealized_pnl

        positions = []
        for item in checked:
            weight = (item["market_value"] / total_market_value * 100) if total_market_value else None
            position_return = (item["unrealized_pnl"] / item["cost_basis"] * 100) if item["cost_basis"] else None
            positions.append({
                "symbol": item["symbol"],
                "market_value_weight_percent": _rounded(weight) if weight is not None else None,
                "estimated_cost_basis": _rounded(item["cost_basis"]),
                "estimated_unrealized_pnl": _rounded(item["unrealized_pnl"]),
                "estimated_return_percent": _rounded(position_return) if position_return is not None else None,
            })

        if total_market_value:
            largest_five = sorted((item["market_value"] for item in checked), reverse=True)[:5]
            top_five = sum(largest_five, Decimal(0)) / total_market_value * 100
        else:
            top_five = None
        total_return = total_unrealized / total_cost * 100 if total_cost else None

    return {
        "holdings_count": len(checked),
        "reported_total_market_value": _rounded(total_market_value),
        "estimated_total_cost_basis": _rounded(total_cost),
        "estimated_unrealized_pnl": _rounded(total_unrealized),
        "estimated_return_percent": _rounded(total_return) if total_return is not None else None,
        "top_five_concentration_percent": _rounded(top_five) if top_five is not None else None,
        "positions": positions,
        "method": "Broker reported market value drives allocation; P/L is estimated as quantity × (last price − average purchase price).",
        "limitations": [
            "برآورد سودوزیان فقط بر پایهٔ میانگین خرید و آخرین قیمت فایل است؛ فروش‌های قبلی، سود نقدی، افزایش سرمایه و سایر رویدادها را محاسبه نمی‌کند.",
            "وزن دارایی از ارزش فعلی گزارش‌شده در فایل کارگزاری محاسبه می‌شود.",
            "این گزارش توصیفی است و پیشنهاد خریدوفروش یا اقدام مالی صادر نمی‌کند.",
        ],
    }
