"""Synthetic coverage for the local CSV/XLSX portfolio import path."""
from datetime import datetime, timedelta, timezone
from http.server import ThreadingHTTPServer
from io import BytesIO
import http.client
import json
import threading
import unittest
from zipfile import ZIP_DEFLATED, ZipFile

from backend.agents.browser_portfolio import BrowserPortfolioAgent
from backend.portfolio_import import parse_portfolio_file
from backend.server import JackHandler


HEADERS = ["نماد", "تعداد", "میانگین خرید", "آخرین قیمت", "ارزش روز"]
HOLDING = ["فولاد", "1٬000", "1,250", "1,300", "1,300,000"]


def csv_fixture() -> bytes:
    return ("گزارش پرتفوی\n" + ",".join(HEADERS) + "\n" +
            '"فولاد","1٬000","1,250","1,300","1,300,000"\n').encode("utf-8-sig")


def _column_name(number: int) -> str:
    result = ""
    while number:
        number, remainder = divmod(number - 1, 26)
        result = chr(65 + remainder) + result
    return result


def xlsx_fixture(*, formula: bool = False, duplicate_closing_price: bool = False) -> bytes:
    headers = HEADERS + (["قیمت پایانی"] if duplicate_closing_price else [])
    holding = ["فولاد", "1000", "1250", "1300", "1300000"] + (["1200"] if duplicate_closing_price else [])
    values = [headers, holding]
    sheet_rows = []
    for row_index, row in enumerate(values, start=1):
        cells = []
        for column_index, value in enumerate(row, start=1):
            ref = f"{_column_name(column_index)}{row_index}"
            if row_index == 2 and column_index > 1:
                if formula and column_index == 5:
                    cells.append(f'<c r="{ref}"><f>B2*D2</f><v>1300000</v></c>')
                else:
                    cells.append(f'<c r="{ref}"><v>{value}</v></c>')
            else:
                escaped = value.replace("&", "&amp;").replace("<", "&lt;")
                cells.append(f'<c r="{ref}" t="inlineStr"><is><t>{escaped}</t></is></c>')
        sheet_rows.append(f'<row r="{row_index}">{"".join(cells)}</row>')
    files = {
        "xl/workbook.xml": ('<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
                            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
                            '<sheets><sheet name="Portfolio" sheetId="1" r:id="rId1"/></sheets></workbook>'),
        "xl/_rels/workbook.xml.rels": ('<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                                        '<Relationship Id="rId1" Type="worksheet" Target="worksheets/sheet1.xml"/>'
                                        '</Relationships>'),
        "xl/worksheets/sheet1.xml": ('<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                                     f'<sheetData>{"".join(sheet_rows)}</sheetData></worksheet>'),
    }
    stream = BytesIO()
    with ZipFile(stream, "w", ZIP_DEFLATED) as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return stream.getvalue()


class PortfolioFileParserTests(unittest.TestCase):
    def test_csv_finds_persian_headers_and_normalizes_persian_amounts(self):
        content = ("گزارش\n" + ",".join(HEADERS) +
                   '\n"فولاد","۱٬۰۰۰","۱٬۲۵۰","۱٬۳۰۰","۱٬۳۰۰٬۰۰۰"\n').encode("utf-8-sig")
        result = parse_portfolio_file(content, "csv", price_unit="IRR",
                                      allowed_hosts={"d.easytrader.ir"},
                                      collected_at=datetime.fromisoformat("2026-10-05T10:00:00+03:30"))
        self.assertEqual(result["source"], "https://d.easytrader.ir")
        self.assertEqual(result["holdings"][0], {
            "symbol": "فولاد", "quantity": 1000.0, "average_price": 1250.0,
            "last_price": 1300.0, "market_value": 1300000.0,
        })

    def test_easytrader_portfolio_export_headers_are_recognized(self):
        headers = ["نام نماد", "تعداد دارایی", "قیمت میانگین خرید در آخرین دوره با لحاظ کارمزد",
                   "آخرین قیمت", "ارزش فعلی", "تاریخ آخرین تراکنش و رویداد"]
        content = (",".join(headers) + '\n"فولاد","1000","1250","1300","1300000","1405/07/13"\n').encode("utf-8-sig")
        result = parse_portfolio_file(content, "csv", price_unit="IRR",
                                      allowed_hosts={"d.easytrader.ir"},
                                      collected_at=datetime.fromisoformat("2026-10-05T10:00:00+03:30"))
        self.assertEqual(result["holdings"][0], {
            "symbol": "فولاد", "quantity": 1000.0, "average_price": 1250.0,
            "last_price": 1300.0, "market_value": 1300000.0,
        })

    def test_xlsx_first_visible_sheet_parses_without_evaluating_formulas(self):
        result = parse_portfolio_file(xlsx_fixture(), "xlsx", price_unit="IRT",
                                      allowed_hosts={"d.easytrader.ir"})
        self.assertEqual(result["holdings"][0]["symbol"], "فولاد")
        self.assertEqual(result["holdings"][0]["market_value"], 1300000.0)
        with self.assertRaisesRegex(ValueError, "PORTFOLIO_FILE_FORMULAS_UNSUPPORTED"):
            parse_portfolio_file(xlsx_fixture(formula=True), "xlsx", price_unit="IRT",
                                 allowed_hosts={"d.easytrader.ir"})

    def test_xlsx_prefers_live_last_price_when_export_also_has_closing_price(self):
        result = parse_portfolio_file(xlsx_fixture(duplicate_closing_price=True), "xlsx", price_unit="IRT",
                                      allowed_hosts={"d.easytrader.ir"})
        self.assertEqual(result["holdings"][0]["last_price"], 1300.0)

    def test_requires_approved_easytrader_host_and_explicit_unit(self):
        with self.assertRaisesRegex(ValueError, "SOURCE_HOST_NOT_APPROVED"):
            parse_portfolio_file(csv_fixture(), "csv", price_unit="IRR", allowed_hosts=set())
        with self.assertRaisesRegex(ValueError, "PORTFOLIO_FILE_PRICE_UNIT_REQUIRED"):
            parse_portfolio_file(csv_fixture(), "csv", price_unit="", allowed_hosts={"d.easytrader.ir"})

    def test_invalid_columns_values_duplicates_and_oversized_files_block(self):
        with self.assertRaisesRegex(ValueError, "PORTFOLIO_FILE_REQUIRED_COLUMNS_MISSING"):
            parse_portfolio_file(b"symbol,quantity\nA,1\n", "csv", price_unit="IRR", allowed_hosts={"d.easytrader.ir"})
        malformed = (",".join(HEADERS) + '\n"فولاد","1","bad","1300","1300"\n').encode()
        with self.assertRaisesRegex(ValueError, "PORTFOLIO_FILE_NUMBER_INVALID"):
            parse_portfolio_file(malformed, "csv", price_unit="IRR", allowed_hosts={"d.easytrader.ir"})
        duplicate = (",".join(HEADERS) + '\n"فولاد","1","2","3","3"\n"فولاد","1","2","3","3"\n').encode()
        with self.assertRaisesRegex(ValueError, "PORTFOLIO_FILE_DUPLICATE_SYMBOL"):
            parse_portfolio_file(duplicate, "csv", price_unit="IRR", allowed_hosts={"d.easytrader.ir"})
        with self.assertRaisesRegex(ValueError, "PORTFOLIO_FILE_SIZE_INVALID"):
            parse_portfolio_file(b"x" * (5 * 1024 * 1024 + 1), "csv", price_unit="IRR", allowed_hosts={"d.easytrader.ir"})


class PortfolioFileImportHttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), JackHandler)
        cls.server.allowed_brokerage_hosts = {"d.easytrader.ir"}
        cls.server.browser_portfolio_agent = BrowserPortfolioAgent({"d.easytrader.ir"})
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def post(self, content: bytes, *, origin: str | None = None, modified_at: datetime | None = None):
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
        headers = {"Content-Type": "application/octet-stream", "X-Jack-Import-Format": "csv", "X-Jack-Price-Unit": "IRR",
                   "X-Jack-File-Modified": (modified_at or datetime.now(timezone.utc)).isoformat()}
        if origin:
            headers["Origin"] = origin
        connection.request("POST", "/api/portfolio-import", content, headers)
        response = connection.getresponse()
        result = json.loads(response.read())
        status = response.status
        connection.close()
        return status, result

    def test_import_returns_preview_in_memory_and_origin_is_redacted(self):
        status, result = self.post(csv_fixture(), origin=f"http://127.0.0.1:{self.server.server_port}")
        self.assertEqual(status, 200)
        self.assertEqual(result["mode"], "PORTFOLIO_FILE_IMPORT_PREVIEW")
        self.assertEqual(result["portfolio_capture"]["status"], "PORTFOLIO_CAPTURED")
        self.assertEqual(result["portfolio_capture"]["source"], "https://d.easytrader.ir")
        self.assertEqual(result["portfolio_summary"]["reported_total_market_value"], 1300000.0)
        self.assertEqual(result["portfolio_summary"]["positions"][0]["market_value_weight_percent"], 100.0)
        self.assertNotIn(".csv", json.dumps(result))

    def test_cross_origin_and_wrong_content_type_are_rejected(self):
        status, _ = self.post(csv_fixture(), origin="https://attacker.example")
        self.assertEqual(status, 403)
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
        connection.request("POST", "/api/portfolio-import", csv_fixture(), {"Content-Type": "text/plain", "X-Jack-Import-Format": "csv", "X-Jack-Price-Unit": "IRR"})
        response = connection.getresponse()
        response.read()
        self.assertEqual(response.status, 400)
        connection.close()

    def test_stale_export_is_not_marked_as_current(self):
        status, result = self.post(csv_fixture(), modified_at=datetime.now(timezone.utc) - timedelta(hours=1))
        self.assertEqual(status, 422)
        self.assertEqual(result["portfolio_capture"]["status"], "PORTFOLIO_BLOCKED")
        self.assertIn("COLLECTION_TIME_STALE", result["portfolio_capture"]["reason"])


if __name__ == "__main__":
    unittest.main()
