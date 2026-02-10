"""
Trade utilities for timestamp normalization and parsing.
"""

from datetime import datetime, timezone
from typing import Optional


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
