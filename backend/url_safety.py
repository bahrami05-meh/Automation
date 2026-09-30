"""Validate HTTPS source URLs while retaining only a safe origin for reports."""
from urllib.parse import urlsplit


def safe_https_origin(value: object, allowed_hosts: set[str] | None = None) -> str:
    if not isinstance(value, str) or not value or len(value) > 4096:
        raise ValueError("SOURCE_URL_INVALID")
    if any(ord(char) < 32 or ord(char) == 127 for char in value) or "\\" in value:
        raise ValueError("SOURCE_URL_INVALID")
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError as error:
        raise ValueError("SOURCE_URL_INVALID") from error
    host = parsed.hostname
    if parsed.scheme.lower() != "https" or not host or parsed.username is not None or parsed.password is not None:
        raise ValueError("SOURCE_URL_INVALID")
    if port not in (None, 443):
        raise ValueError("SOURCE_URL_INVALID")
    authority = parsed.netloc.rsplit("@", 1)[-1]
    if "%" in authority:
        raise ValueError("SOURCE_URL_INVALID")
    try:
        ascii_host = host.encode("idna").decode("ascii").lower()
    except UnicodeError as error:
        raise ValueError("SOURCE_URL_INVALID") from error
    if allowed_hosts is not None:
        try:
            approved_hosts = {item.encode("idna").decode("ascii").lower() for item in allowed_hosts}
        except (AttributeError, UnicodeError) as error:
            raise ValueError("APPROVED_HOST_CONFIGURATION_INVALID") from error
        if ascii_host not in approved_hosts:
            raise ValueError("SOURCE_HOST_NOT_APPROVED")
    return f"https://{ascii_host}"
