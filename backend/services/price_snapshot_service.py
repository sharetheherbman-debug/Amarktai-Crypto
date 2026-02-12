"""
Price Snapshot Service
Stores rolling market snapshots and computes 24h change percentages.
"""

from datetime import datetime, timezone, timedelta
import logging
from typing import Optional, Tuple

import database as db

logger = logging.getLogger(__name__)


async def record_snapshot(pair: str, price: float, timestamp: Optional[datetime] = None) -> Tuple[float, str]:
    """Record a price snapshot and compute change percentage.

    Returns (change_pct, window) where window is "24h", "latest", or "none".
    """
    if not pair:
        return 0.0, "none"

    now = timestamp or datetime.now(timezone.utc)

    if db.price_snapshots_collection is None:
        return 0.0, "none"

    try:
        await db.price_snapshots_collection.insert_one({
            "pair": pair,
            "price": float(price),
            "timestamp": now
        })

        cutoff = now - timedelta(hours=24)

        prior_24h = await db.price_snapshots_collection.find(
            {"pair": pair, "timestamp": {"$lte": cutoff}},
            {"_id": 0, "price": 1, "timestamp": 1}
        ).sort("timestamp", -1).limit(1).to_list(1)

        previous_snapshot = prior_24h[0] if prior_24h else None
        window = "24h"

        if previous_snapshot is None:
            previous_list = await db.price_snapshots_collection.find(
                {"pair": pair, "timestamp": {"$lt": now}},
                {"_id": 0, "price": 1, "timestamp": 1}
            ).sort("timestamp", -1).limit(1).to_list(1)
            previous_snapshot = previous_list[0] if previous_list else None
            window = "latest" if previous_snapshot else "none"

        change_pct = 0.0
        previous_price = previous_snapshot.get("price") if previous_snapshot else None
        if previous_price:
            change_pct = ((float(price) - float(previous_price)) / float(previous_price)) * 100

        # Cleanup snapshots older than 48 hours (best-effort)
        try:
            await db.price_snapshots_collection.delete_many({
                "timestamp": {"$lt": now - timedelta(days=2)}
            })
        except Exception as cleanup_error:
            logger.debug(f"Snapshot cleanup skipped: {cleanup_error}")

        return round(change_pct, 2), window
    except Exception as e:
        logger.warning(f"Price snapshot error for {pair}: {e}")
        return 0.0, "none"
