"""پروزه اتوماسیون بورسی — پل امن مشاهدهٔ مرورگر."""
from __future__ import annotations
from typing import Any

SENSITIVE = {"password", "pass", "otp", "token", "cookie", "session", "username", "user", "رمز", "کد", "نشست", "کوکی"}

def validate_browser_payload(payload: object) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError("دادهٔ پل مرورگر باید یک شیء JSON باشد.")
    if _contains_sensitive(payload):
        raise ValueError("پل مرورگر دادهٔ ورود، نشست، کوکی، رمز یا OTP را نمی‌پذیرد.")
    required = ("symbol", "market_snapshot")
    missing = [key for key in required if key not in payload]
    if missing:
        raise ValueError("فیلدهای لازم پل مرورگر وجود ندارند: " + ", ".join(missing))
    snapshot = payload["market_snapshot"]
    if not isinstance(snapshot, dict) or snapshot.get("symbol") != payload["symbol"]:
        raise ValueError("نماد مشاهدهٔ مرورگر با نماد بستهٔ بازار یکسان نیست.")
    return payload

def _contains_sensitive(value: object) -> bool:
    if isinstance(value, dict):
        for key, item in value.items():
            lowered = str(key).lower()
            if any(part in lowered for part in SENSITIVE):
                return True
            if _contains_sensitive(item):
                return True
    elif isinstance(value, list):
        return any(_contains_sensitive(item) for item in value)
    return False
