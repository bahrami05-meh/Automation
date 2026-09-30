"""Collection timestamp policy shared by ingestion and final quality review."""
from datetime import datetime, timedelta, timezone

TEHRAN = timezone(timedelta(hours=3, minutes=30), "Asia/Tehran")
POLICY_VERSION = "collection-freshness-v1"
MAX_AGES = {
    "market": timedelta(days=7),
    "board": timedelta(minutes=30),
    "chart": timedelta(minutes=30),
    "portfolio": timedelta(minutes=15),
    "fundamental": timedelta(hours=24),
}
FUTURE_SKEW = timedelta(minutes=5)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def validate_collected_at(value: object, kind: str, *, now: datetime | None = None,
                          max_age: timedelta | None = None) -> datetime:
    if not isinstance(value, str):
        raise ValueError("COLLECTION_TIME_INVALID")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError("COLLECTION_TIME_INVALID") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("COLLECTION_TIME_OFFSET_REQUIRED")
    current = now if now is not None else utc_now()
    if current.tzinfo is None or current.utcoffset() is None:
        raise ValueError("REFERENCE_TIME_OFFSET_REQUIRED")
    age = current.astimezone(timezone.utc) - parsed.astimezone(timezone.utc)
    if age < -FUTURE_SKEW:
        raise ValueError("COLLECTION_TIME_FUTURE")
    if age > (max_age if max_age is not None else MAX_AGES[kind]):
        raise ValueError(f"COLLECTION_TIME_STALE:{kind}")
    return parsed.astimezone(TEHRAN)
