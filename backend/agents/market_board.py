"""پروزه اتوماسیون بورسی — ایجنت تابلو.

این ایجنت تنها مشاهدهٔ ساختاریافتهٔ تابلو را کنترل و خلاصه می‌کند؛ نه به
کارگزاری وارد می‌شود و نه سفارش یا اقدام مالی انجام می‌دهد.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from backend.numeric import finite_number
from backend.freshness import validate_collected_at
from backend.url_safety import safe_https_origin
from uuid import uuid4


AGENT_NAME = "ایجنت تابلو"
AGENT_ID = "market-board-agent"
AGENT_VERSION = "0.2"
TEHRAN = timezone(timedelta(hours=3, minutes=30), "Asia/Tehran")
MARKET_STATUSES = {"open", "closed", "suspended"}


def _run_metadata() -> dict[str, str]:
    return {
        "name": AGENT_NAME,
        "id": AGENT_ID,
        "version": AGENT_VERSION,
        "run_id": f"mba-{uuid4().hex}",
        "started_at": datetime.now(TEHRAN).isoformat(timespec="seconds"),
    }


class MarketBoardAgent:
    """کنترل وضعیت تابلو، حجم و جریان حقیقی/حقوقی بدون رأی معامله."""

    def __init__(self, allowed_hosts: set[str]) -> None:
        self.allowed_hosts = {host.lower() for host in allowed_hosts}

    def inspect(self, report: dict[str, Any], observation: object | None) -> dict[str, Any]:
        agent = _run_metadata()
        symbol = report["symbols"][0]
        if symbol.get("data_status") != "VALID":
            report["market_board"] = self._skipped("تا پیش از دادهٔ معتبر بازار، تحلیل تابلو اجرا نمی‌شود.")
            report["market_board_agent"] = agent | {"status": "SKIPPED"}
            return self._with_agent_chain(report)
        if observation is None:
            report["market_board"] = self._skipped("مشاهدهٔ تابلو به درخواست داده افزوده نشده است؛ اتصال خودکار منبع تابلو هنوز ساخته نشده است.")
            report["market_board"]["findings"] = [{
                "code": "BOARD_SOURCE_NOT_CONNECTED", "severity": "warning",
                "message": "ایجنت تابلو فقط مشاهدهٔ ثبت‌شده را کنترل می‌کند و هنوز دادهٔ زنده دریافت نمی‌کند.",
            }]
            report["market_board_agent"] = agent | {"status": "SKIPPED"}
            return self._with_agent_chain(report)
        try:
            board = self._validate(symbol, observation)
        except ValueError as error:
            finding = {"code": "BOARD_OBSERVATION_INVALID", "severity": "blocker", "message": str(error)}
            report["market_board"] = {"status": "BOARD_BLOCKED", "reason": str(error), "findings": [finding]}
            self._block_quality(symbol, finding, "دادهٔ تابلو نامعتبر است و تحلیل ادامه نمی‌یابد.")
            report["market_board_agent"] = agent | {"status": "BOARD_BLOCKED"}
            return self._with_agent_chain(report)
        if board["market_status"] == "suspended":
            finding = {"code": "MARKET_SUSPENDED", "severity": "blocker", "message": "نماد در مشاهدهٔ تابلو متوقف اعلام شده است."}
            report["market_board"] = {"status": "MARKET_SUSPENDED", "reason": "نماد متوقف است؛ نتیجهٔ معامله‌محور ساخته نمی‌شود.", "observation": board, "findings": [finding]}
            self._block_quality(symbol, finding, "نماد متوقف است؛ برای جلوگیری از نتیجه‌گیری نادرست تحلیل مسدود شد.")
            report["market_board_agent"] = agent | {"status": "MARKET_SUSPENDED"}
            return self._with_agent_chain(report)

        volume_ratio = round(board["volume"] / board["average_volume_20"], 2)
        volume_state = "ABOVE_AVERAGE" if volume_ratio > 1.2 else "BELOW_AVERAGE" if volume_ratio < 0.8 else "NEAR_AVERAGE"
        individual_net = round(board["individual_buy_volume"] - board["individual_sell_volume"], 4)
        legal_net = round(board["legal_buy_volume"] - board["legal_sell_volume"], 4)
        queue_state = self._queue_state(board["buy_queue_value"], board["sell_queue_value"])
        powers = self._powers(board)
        status = "MARKET_CLOSED" if board["market_status"] == "closed" else "OBSERVED"
        reason = "بازار در مشاهدهٔ ثبت‌شده بسته است؛ اعداد برای گزارش نگهداری شد اما داده زنده تلقی نمی‌شود." if status == "MARKET_CLOSED" else "تابلو اعتبارسنجی شد؛ خروجی فقط مشاهده و محاسبه است، نه پیشنهاد معامله."
        report["market_board"] = {
            "status": status,
            "reason": reason,
            "observation": board,
            "metrics": {
                "volume_ratio_to_average_20": volume_ratio,
                "volume_state": volume_state,
                "individual_net_volume": individual_net,
                "legal_net_volume": legal_net,
                "queue_state": queue_state,
                "individual_buy_power": powers["individual_buy_power"],
                "individual_sell_power": powers["individual_sell_power"],
                "legal_buy_power": powers["legal_buy_power"],
                "legal_sell_power": powers["legal_sell_power"],
                "trade_count": board.get("trade_count"),
                "turnover_value": board.get("turnover_value"),
                "market_value": board.get("market_value"),
                "best_bid_price": board.get("best_bid_price"),
                "best_ask_price": board.get("best_ask_price"),
            },
            "findings": [],
        }
        report["market_board_agent"] = agent | {"status": status}
        return self._with_agent_chain(report)

    @staticmethod
    def _skipped(reason: str) -> dict[str, Any]:
        return {"status": "SKIPPED", "reason": reason, "findings": []}

    def _validate(self, symbol: dict[str, Any], observation: object) -> dict[str, Any]:
        if not isinstance(observation, dict):
            raise ValueError("مشاهدهٔ تابلو باید یک شیء JSON باشد.")
        required = (
            "symbol", "source", "collected_at", "timezone", "price_unit", "market_status", "last_price", "volume",
            "average_volume_20", "individual_buy_volume", "individual_sell_volume", "legal_buy_volume", "legal_sell_volume",
            "buy_queue_value", "sell_queue_value",
        )
        missing = [key for key in required if key not in observation]
        if missing:
            raise ValueError("فیلدهای لازم مشاهدهٔ تابلو وجود ندارند: " + ", ".join(missing))
        if observation["symbol"] != symbol["symbol"]:
            raise ValueError("نماد مشاهدهٔ تابلو با نماد دادهٔ بازار یکسان نیست.")
        source_origin = safe_https_origin(observation["source"], self.allowed_hosts)
        collected_at = validate_collected_at(observation["collected_at"], "board").isoformat()
        if observation["timezone"] != "Asia/Tehran":
            raise ValueError("منطقهٔ زمانی مشاهدهٔ تابلو باید Asia/Tehran باشد.")
        if observation["price_unit"] != symbol["market_metadata"]["price_unit"]:
            raise ValueError("واحد قیمت تابلو با دادهٔ بازار یکسان نیست.")
        if observation["market_status"] not in MARKET_STATUSES:
            raise ValueError("وضعیت بازار تابلو باید open، closed یا suspended باشد.")
        checked: dict[str, Any] = {
            key: observation[key] for key in ("symbol", "collected_at", "timezone", "price_unit", "market_status")
        }
        checked["source"] = source_origin
        checked["collected_at"] = collected_at
        for key in required[6:]:
            try:
                value = finite_number(observation[key])
            except (TypeError, ValueError) as error:
                raise ValueError(f"مقدار {key} در مشاهدهٔ تابلو نامعتبر است.") from error
            if value < 0 or (key in {"last_price", "average_volume_20"} and value == 0):
                raise ValueError(f"مقدار {key} در مشاهدهٔ تابلو نامعتبر است.")
            checked[key] = value
        for key in ("individual_buy_count", "individual_sell_count", "legal_buy_count", "legal_sell_count", "trade_count", "turnover_value", "market_value", "best_bid_price", "best_ask_price"):
            if key in observation:
                try:
                    value = finite_number(observation[key])
                except (TypeError, ValueError) as error:
                    raise ValueError(f"مقدار {key} در مشاهدهٔ تابلو نامعتبر است.") from error
                if value < 0:
                    raise ValueError(f"مقدار {key} در مشاهدهٔ تابلو نامعتبر است.")
                checked[key] = value
        return checked

    @staticmethod
    def _powers(board: dict[str, Any]) -> dict[str, float | None]:
        def power(volume_key: str, count_key: str) -> float | None:
            count = board.get(count_key)
            if count is None or count <= 0:
                return None
            return round(board[volume_key] / count, 4)
        return {
            "individual_buy_power": power("individual_buy_volume", "individual_buy_count"),
            "individual_sell_power": power("individual_sell_volume", "individual_sell_count"),
            "legal_buy_power": power("legal_buy_volume", "legal_buy_count"),
            "legal_sell_power": power("legal_sell_volume", "legal_sell_count"),
        }

    @staticmethod
    def _queue_state(buy_queue_value: float, sell_queue_value: float) -> str:
        if buy_queue_value > sell_queue_value * 1.2:
            return "BUY_QUEUE_DOMINANT"
        if sell_queue_value > buy_queue_value * 1.2:
            return "SELL_QUEUE_DOMINANT"
        return "QUEUES_BALANCED_OR_EMPTY"

    @staticmethod
    def _block_quality(symbol: dict[str, Any], finding: dict[str, Any], reason: str) -> None:
        quality = symbol.setdefault("quality", {"status": "QA_BLOCKED", "findings": []})
        quality["status"] = "QA_BLOCKED"
        quality.setdefault("findings", []).append(finding)
        symbol["data_status"] = "DATA_BLOCKED"
        symbol["jack_decision"] = "DATA_BLOCKED"
        symbol["reason"] = reason

    @staticmethod
    def _with_agent_chain(report: dict[str, Any]) -> dict[str, Any]:
        chain = list(report.get("agents", []))
        chain.append(report["market_board_agent"])
        report["agents"] = chain
        return report
