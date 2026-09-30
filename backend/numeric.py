"""Shared strict validation for numeric input and calculated output."""
from math import isfinite


def finite_number(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise ValueError("FINITE_NUMBER_REQUIRED")
    if isinstance(value, str) and not value.strip():
        raise ValueError("FINITE_NUMBER_REQUIRED")
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError) as error:
        raise ValueError("FINITE_NUMBER_REQUIRED") from error
    if not isfinite(number):
        raise ValueError("FINITE_NUMBER_REQUIRED")
    return number


def validate_finite_tree(value: object) -> None:
    """Reject nonfinite JSON numbers, including overflow such as 1e999."""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        finite_number(value)
    elif isinstance(value, dict):
        for item in value.values():
            validate_finite_tree(item)
    elif isinstance(value, list):
        for item in value:
            validate_finite_tree(item)
