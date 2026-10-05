"""Local, read-only CSV/XLSX import for visible brokerage portfolio exports."""
from __future__ import annotations

import csv
from datetime import datetime, timedelta, timezone
from io import BytesIO, StringIO
import re
import unicodedata
import xml.etree.ElementTree as ET
from zipfile import BadZipFile, ZipFile

from backend.numeric import finite_number
from backend.url_safety import safe_https_origin
from backend.jack_core import build_symbol_request

MAX_FILE_BYTES = 5 * 1024 * 1024
MAX_UNPACKED_BYTES = 20 * 1024 * 1024
MAX_XML_PART_BYTES = 8 * 1024 * 1024
MAX_ZIP_ENTRIES = 256
MAX_ROWS = 512
MAX_COLUMNS = 64
MAX_HEADER_SCAN = 20
SOURCE_URL = "https://d.easytrader.ir"
TEHRAN = timezone(timedelta(hours=3, minutes=30), "Asia/Tehran")

ALIASES = {
    "symbol": {"symbol", "ticker", "نماد", "نمادبورسی", "نامنماد", "نام نماد"},
    "quantity": {"quantity", "qty", "shares", "تعداد", "تعدادسهام", "حجم", "تعداد دارایی"},
    "average_price": {"averageprice", "avgprice", "costbasis", "میانگینخرید", "میانگینقیمتخرید", "قیمتتمامشده", "بهایتمامشده",
                      "قیمت میانگین خرید در آخرین دوره با لحاظ کارمزد"},
    "last_price": {"lastprice", "closingprice", "آخرینقیمت", "قیمتآخرین", "قیمتپایانی"},
    "market_value": {"marketvalue", "currentvalue", "totalvalue", "ارزشروز", "ارزشروزپرتفوی", "ارزشکل", "ارزشبازار", "ارزش فعلی"},
}
REQUIRED_COLUMNS = tuple(ALIASES)
_DIGIT_MAP = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
_NS = {"main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
       "rel": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
       "pkg": "http://schemas.openxmlformats.org/package/2006/relationships"}


def _normalize(value: object) -> str:
    text = unicodedata.normalize("NFKC", str(value or "")).casefold()
    text = text.replace("ك", "ک").replace("ي", "ی").replace("‌", "")
    return "".join(char for char in text if char.isalnum())


_ALIAS_TO_FIELD = {_normalize(alias): field for field, aliases in ALIASES.items() for alias in aliases}


def _cell_number(value: object, field: str, row_number: int) -> float:
    if isinstance(value, str):
        normalized = unicodedata.normalize("NFKC", value).translate(_DIGIT_MAP)
        normalized = normalized.replace("٫", ".").replace("٬", "").replace(",", "")
        normalized = normalized.replace("\u00a0", "").replace(" ", "").strip()
        if not normalized or len(normalized) > 64 or not re.fullmatch(r"\+?(?:\d+(?:\.\d*)?|\.\d+)", normalized):
            raise ValueError(f"PORTFOLIO_FILE_NUMBER_INVALID_ROW_{row_number}_{field.upper()}")
        value = normalized
    try:
        number = finite_number(value)
    except ValueError as error:
        raise ValueError(f"PORTFOLIO_FILE_NUMBER_INVALID_ROW_{row_number}_{field.upper()}") from error
    if number < 0:
        raise ValueError(f"PORTFOLIO_FILE_NEGATIVE_VALUE_ROW_{row_number}_{field.upper()}")
    return number


def _header_columns(rows: list[list[object]]) -> tuple[int, dict[str, int]]:
    for row_index, row in enumerate(rows[:MAX_HEADER_SCAN]):
        if len(row) > MAX_COLUMNS:
            raise ValueError("PORTFOLIO_FILE_TOO_MANY_COLUMNS")
        columns: dict[str, int] = {}
        ambiguous: set[str] = set()
        matched_headers: dict[str, list[tuple[str, int]]] = {}
        for index, cell in enumerate(row):
            normalized = _normalize(cell)
            field = _ALIAS_TO_FIELD.get(normalized)
            if field:
                matched_headers.setdefault(field, []).append((normalized, index))
                if field in columns:
                    ambiguous.add(field)
                columns[field] = index
        if all(field in columns for field in REQUIRED_COLUMNS):
            # EasyTrader exports both the live last-traded price and closing price.
            # Prefer the explicit live-price column when both recognized aliases exist.
            if "last_price" in ambiguous:
                preferred_last_price = _normalize("آخرین قیمت")
                preferred = [index for header, index in matched_headers["last_price"]
                             if header == preferred_last_price]
                if len(preferred) == 1:
                    columns["last_price"] = preferred[0]
                    ambiguous.remove("last_price")
            if ambiguous:
                raise ValueError("PORTFOLIO_FILE_AMBIGUOUS_COLUMNS")
            return row_index, columns
    raise ValueError("PORTFOLIO_FILE_REQUIRED_COLUMNS_MISSING")


def _build_observation(rows: list[list[object]], *, price_unit: str,
                       allowed_hosts: set[str] | None, collected_at: datetime | None) -> dict:
    if price_unit not in {"IRR", "IRT"}:
        raise ValueError("PORTFOLIO_FILE_PRICE_UNIT_REQUIRED")
    source = safe_https_origin(SOURCE_URL, allowed_hosts)
    header_index, columns = _header_columns(rows)
    holdings = []
    seen_symbols: set[str] = set()
    for row_number, row in enumerate(rows[header_index + 1:], start=header_index + 2):
        if len(row) > MAX_COLUMNS:
            raise ValueError("PORTFOLIO_FILE_TOO_MANY_COLUMNS")
        if not any(str(value or "").strip() for value in row):
            continue
        try:
            raw_symbol = str(row[columns["symbol"]]).strip()
            symbol = build_symbol_request(raw_symbol)["symbols"][0]["symbol"]
            if symbol in seen_symbols:
                raise ValueError("PORTFOLIO_FILE_DUPLICATE_SYMBOL")
            holding = {
                "symbol": symbol,
                "quantity": _cell_number(row[columns["quantity"]], "quantity", row_number),
                "average_price": _cell_number(row[columns["average_price"]], "average_price", row_number),
                "last_price": _cell_number(row[columns["last_price"]], "last_price", row_number),
                "market_value": _cell_number(row[columns["market_value"]], "market_value", row_number),
            }
        except IndexError as error:
            raise ValueError(f"PORTFOLIO_FILE_INCOMPLETE_ROW_{row_number}") from error
        except (TypeError, ValueError) as error:
            if str(error) == "PORTFOLIO_FILE_DUPLICATE_SYMBOL":
                raise
            if str(error).startswith("PORTFOLIO_FILE_"):
                raise
            raise ValueError(f"PORTFOLIO_FILE_INVALID_SYMBOL_ROW_{row_number}") from error
        seen_symbols.add(symbol)
        holdings.append(holding)
        if len(holdings) > MAX_ROWS:
            raise ValueError("PORTFOLIO_FILE_TOO_MANY_ROWS")
    if not holdings:
        raise ValueError("PORTFOLIO_FILE_NO_HOLDINGS")
    timestamp = collected_at or datetime.now(TEHRAN)
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise ValueError("PORTFOLIO_FILE_TIMESTAMP_INVALID")
    return {
        "source": source,
        "collected_at": timestamp.astimezone(TEHRAN).isoformat(timespec="seconds"),
        "timezone": "Asia/Tehran",
        "price_unit": price_unit,
        "holdings": holdings,
    }


def _decode_csv(content: bytes) -> str:
    if content.startswith((b"\xff\xfe", b"\xfe\xff")):
        return content.decode("utf-16")
    try:
        return content.decode("utf-8-sig")
    except UnicodeDecodeError:
        try:
            return content.decode("cp1256")
        except UnicodeDecodeError as error:
            raise ValueError("PORTFOLIO_FILE_ENCODING_INVALID") from error


def _parse_csv(content: bytes) -> list[list[object]]:
    text = _decode_csv(content)
    if "\x00" in text:
        raise ValueError("PORTFOLIO_FILE_ENCODING_INVALID")
    sample = text[:8192]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    try:
        rows = []
        for row in csv.reader(StringIO(text), dialect):
            if len(row) > MAX_COLUMNS:
                raise ValueError("PORTFOLIO_FILE_TOO_MANY_COLUMNS")
            if any(len(cell) > 512 for cell in row):
                raise ValueError("PORTFOLIO_FILE_CELL_TOO_LONG")
            rows.append(row)
            if len(rows) > MAX_ROWS + MAX_HEADER_SCAN + 1:
                raise ValueError("PORTFOLIO_FILE_TOO_MANY_ROWS")
        return rows
    except csv.Error as error:
        raise ValueError("PORTFOLIO_FILE_CSV_INVALID") from error


def _safe_xml(archive: ZipFile, name: str) -> ET.Element:
    try:
        if archive.getinfo(name).file_size > MAX_XML_PART_BYTES:
            raise ValueError("PORTFOLIO_FILE_XLSX_SIZE_LIMIT")
        data = archive.read(name)
    except (KeyError, BadZipFile, RuntimeError) as error:
        raise ValueError("PORTFOLIO_FILE_XLSX_INVALID") from error
    if b"<!DOCTYPE" in data.upper() or b"<!ENTITY" in data.upper():
        raise ValueError("PORTFOLIO_FILE_XLSX_INVALID")
    try:
        return ET.fromstring(data)
    except ET.ParseError as error:
        raise ValueError("PORTFOLIO_FILE_XLSX_INVALID") from error


def _xlsx_rows(content: bytes) -> list[list[object]]:
    try:
        archive = ZipFile(BytesIO(content))
    except (BadZipFile, OSError) as error:
        raise ValueError("PORTFOLIO_FILE_XLSX_INVALID") from error
    with archive:
        infos = archive.infolist()
        if len(infos) > MAX_ZIP_ENTRIES or sum(info.file_size for info in infos) > MAX_UNPACKED_BYTES:
            raise ValueError("PORTFOLIO_FILE_XLSX_SIZE_LIMIT")
        names = [info.filename for info in infos]
        if len(names) != len(set(names)):
            raise ValueError("PORTFOLIO_FILE_XLSX_INVALID")
        for info in infos:
            if info.flag_bits & 0x1 or info.file_size > MAX_UNPACKED_BYTES or (info.compress_size == 0 and info.file_size > 0):
                raise ValueError("PORTFOLIO_FILE_XLSX_INVALID")
            if info.compress_size and info.file_size / info.compress_size > 200:
                raise ValueError("PORTFOLIO_FILE_XLSX_SIZE_LIMIT")
            if ".." in info.filename.replace("\\", "/").split("/") or info.filename.startswith(("/", "\\")):
                raise ValueError("PORTFOLIO_FILE_XLSX_INVALID")
        if any(name.startswith("xl/externalLinks/") or name.endswith("vbaProject.bin") for name in archive.namelist()):
            raise ValueError("PORTFOLIO_FILE_XLSX_UNSUPPORTED_CONTENT")

        workbook = _safe_xml(archive, "xl/workbook.xml")
        relationships = _safe_xml(archive, "xl/_rels/workbook.xml.rels")
        rel_targets = {}
        for relationship in relationships.findall("pkg:Relationship", _NS):
            if relationship.get("TargetMode") == "External":
                raise ValueError("PORTFOLIO_FILE_XLSX_UNSUPPORTED_CONTENT")
            rel_targets[relationship.get("Id", "")] = relationship.get("Target", "")
        sheet_path = None
        sheets = workbook.find("main:sheets", _NS)
        if sheets is not None:
            for sheet in sheets.findall("main:sheet", _NS):
                if sheet.get("state", "visible") == "visible":
                    target = rel_targets.get(sheet.get("{" + _NS["rel"] + "}id", ""), "")
                    normalized = target.replace("\\", "/")
                    if normalized.startswith("/"):
                        normalized = normalized.lstrip("/")
                    elif not normalized.startswith("xl/"):
                        normalized = "xl/" + normalized
                    parts = []
                    for part in normalized.split("/"):
                        if part in {"", "."}:
                            continue
                        if part == "..":
                            raise ValueError("PORTFOLIO_FILE_XLSX_INVALID")
                        parts.append(part)
                    candidate = "/".join(parts)
                    if not candidate.startswith("xl/worksheets/"):
                        raise ValueError("PORTFOLIO_FILE_XLSX_INVALID")
                    sheet_path = candidate
                    break
        if not sheet_path:
            raise ValueError("PORTFOLIO_FILE_XLSX_NO_VISIBLE_SHEET")

        shared_strings = []
        if "xl/sharedStrings.xml" in archive.namelist():
            strings_root = _safe_xml(archive, "xl/sharedStrings.xml")
            for item in strings_root.findall("main:si", _NS):
                shared_strings.append("".join(node.text or "" for node in item.findall(".//main:t", _NS)))
                if len(shared_strings) > 100_000:
                    raise ValueError("PORTFOLIO_FILE_XLSX_SIZE_LIMIT")

        root = _safe_xml(archive, sheet_path)
        sheet_data = root.find("main:sheetData", _NS)
        if sheet_data is None:
            raise ValueError("PORTFOLIO_FILE_NO_HOLDINGS")
        rows = []
        for row in sheet_data.findall("main:row", _NS):
            row_values: dict[int, object] = {}
            for cell in row.findall("main:c", _NS):
                ref = cell.get("r", "")
                letters = re.match(r"([A-Z]+)", ref)
                if not letters:
                    raise ValueError("PORTFOLIO_FILE_XLSX_INVALID")
                column = 0
                for letter in letters.group(1):
                    column = column * 26 + ord(letter) - 64
                column -= 1
                if column >= MAX_COLUMNS:
                    raise ValueError("PORTFOLIO_FILE_TOO_MANY_COLUMNS")
                if cell.find("main:f", _NS) is not None:
                    raise ValueError("PORTFOLIO_FILE_FORMULAS_UNSUPPORTED")
                value_node = cell.find("main:v", _NS)
                cell_type = cell.get("t")
                if cell_type == "inlineStr":
                    value: object = "".join(node.text or "" for node in cell.findall(".//main:t", _NS))
                elif value_node is None or value_node.text is None:
                    value = ""
                elif cell_type == "s":
                    try:
                        value = shared_strings[int(value_node.text)]
                    except (ValueError, IndexError) as error:
                        raise ValueError("PORTFOLIO_FILE_XLSX_INVALID") from error
                elif cell_type == "str":
                    value = value_node.text
                elif cell_type in (None, "n"):
                    value = value_node.text
                else:
                    value = value_node.text
                if len(str(value)) > 512:
                    raise ValueError("PORTFOLIO_FILE_CELL_TOO_LONG")
                row_values[column] = value
            if len(row_values) > MAX_COLUMNS:
                raise ValueError("PORTFOLIO_FILE_TOO_MANY_COLUMNS")
            if row_values:
                width = max(row_values) + 1
                rows.append([row_values.get(index, "") for index in range(width)])
            else:
                rows.append([])
            if len(rows) > MAX_ROWS + MAX_HEADER_SCAN + 1:
                raise ValueError("PORTFOLIO_FILE_TOO_MANY_ROWS")
        return rows


def parse_portfolio_file(content: bytes, file_format: str, *, price_unit: str,
                         allowed_hosts: set[str] | None,
                         collected_at: datetime | None = None) -> dict:
    """Parse a local export in memory; never writes the uploaded bytes to disk."""
    if not isinstance(content, bytes) or not content or len(content) > MAX_FILE_BYTES:
        raise ValueError("PORTFOLIO_FILE_SIZE_INVALID")
    if file_format == "csv":
        rows = _parse_csv(content)
    elif file_format == "xlsx":
        rows = _xlsx_rows(content)
    else:
        raise ValueError("PORTFOLIO_FILE_FORMAT_UNSUPPORTED")
    return _build_observation(rows, price_unit=price_unit,
                              allowed_hosts=allowed_hosts, collected_at=collected_at)
