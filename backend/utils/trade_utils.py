"""
Trade utilities for timestamp normalization and parsing.
"""

from datetime import datetime, timezone
from typing import Optional, Dict, Iterable, Union
from uuid import uuid4


def parse_trade_timestamp(trade: dict) -> datetime:
    """Return a timezone-aware timestamp for a trade."""
    raw_ts = (
        trade.get("timestamp")
        or trade.get("created_at")
        or trade.get("executed_at")
        or trade.get("last_updated")
    )

    if isinstance(raw_ts, datetime):
        dt = raw_ts
    elif raw_ts:
        try:
            dt = datetime.fromisoformat(str(raw_ts).replace("Z", "+00:00"))
        except ValueError:
            dt = datetime.now(timezone.utc)
    else:
        dt = datetime.now(timezone.utc)

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)

    return dt


def normalize_trade_timestamps(trade: dict) -> dict:
    """Ensure trade has both timestamp and created_at in ISO format."""
    dt = parse_trade_timestamp(trade)
    iso_ts = dt.isoformat()
    trade["timestamp"] = iso_ts
    trade["created_at"] = trade.get("created_at") or iso_ts
    return trade


def _first_non_empty_value(record: Dict, keys: Iterable[str], default=None):
    for key in keys:
        value = record.get(key)
        if value not in (None, ""):
            return value
    return default


def build_trade_record(trade: Dict, user_id: Optional[str] = None, bot: Optional[Dict] = None) -> Dict:
    """Build a canonical trade record with required fields populated."""
    import logging as _logging
    _logger = _logging.getLogger(__name__)
    bot = bot or {}
    record = dict(trade)
    now = datetime.now(timezone.utc).isoformat()
    record_user_id = user_id or record.get("user_id") or bot.get("user_id")
    bot_id = record.get("bot_id") or bot.get("id")
    trading_mode = record.get("trading_mode") or record.get("mode") or bot.get("trading_mode") or bot.get("mode") or "paper"
    is_live = record.get("is_live")
    if is_live is None:
        is_live = trading_mode == "live" or not record.get("is_paper", True)

    # Resolve trade id – must never be None or empty
    trade_id = record.get("id") or record.get("trade_id")
    if not trade_id:
        trade_id = str(uuid4())
        _logger.warning("build_trade_record: id was missing, auto-generated %s", trade_id)

    record.update({
        "id": trade_id,
        "user_id": record_user_id,
        "bot_id": bot_id,
        "bot_name": record.get("bot_name") or bot.get("name") or "Unknown",
        "exchange": record.get("exchange") or bot.get("exchange") or "unknown",
        "pair": record.get("pair") or record.get("symbol") or bot.get("pair") or "UNKNOWN",
        "side": record.get("side") or record.get("trade_type") or "buy",
        "price": record.get("price") or record.get("entry_price") or record.get("exit_price") or 0,
        "qty": record.get("qty") or record.get("quantity") or record.get("amount") or 0,
        "fee_amount": record.get("fee_amount") or record.get("fees") or record.get("fee") or 0,
        "fee_currency": record.get("fee_currency") or record.get("fee_asset") or record.get("currency") or "ZAR",
        "mode": record.get("mode") or trading_mode,
        "trading_mode": trading_mode,
        "is_live": is_live,
        "exchange_order_id": _first_non_empty_value(
            record,
            ["exchange_order_id", "order_id", "orderId"],
            ""
        ),
        "created_at": record.get("created_at") or record.get("timestamp") or now,
    })

    gross_pnl = _first_non_empty_value(record, ["gross_pnl", "gross_profit"], 0)
    fees_total = _first_non_empty_value(record, ["fees_total", "fees", "fee_paid", "fee_amount"], 0)
    slippage_cost = _first_non_empty_value(record, ["slippage_cost", "slippage"], 0)
    net_pnl = _first_non_empty_value(record, ["net_pnl", "net_profit", "profit_loss", "realized_pnl"], 0)
    net_pnl_quote = _first_non_empty_value(record, ["net_pnl_quote", "net_profit_zar", "net_pnl"], net_pnl)

    record.update({
        "gross_pnl": gross_pnl,
        "fees_total": fees_total,
        "slippage_cost": slippage_cost,
        "net_pnl": net_pnl,
        "net_pnl_quote": net_pnl_quote,
        "profit_loss": record.get("profit_loss", net_pnl),
    })

    normalize_trade_timestamps(record)
    return record


def calculate_trade_pnl(
    entry_value: float,
    exit_value: float,
    fees: float,
    slippage: float = 0.0
) -> Dict[str, float]:
    """Calculate gross and net PnL for a trade."""
    gross_profit = exit_value - entry_value
    net_profit = gross_profit - fees - slippage
    return {
        "gross_profit": gross_profit,
        "net_profit": net_profit,
        "fees": fees,
        "slippage": slippage,
    }


def classify_trade_outcome(net_profit: float) -> Dict[str, Union[int, str]]:
    """Classify a trade outcome for win/loss counters.

    Returns dict with win_count, loss_count, and result keys.
    """
    if net_profit > 0:
        return {"win_count": 1, "loss_count": 0, "result": "win"}
    if net_profit < 0:
        return {"win_count": 0, "loss_count": 1, "result": "loss"}
    return {"win_count": 0, "loss_count": 0, "result": "flat"}
