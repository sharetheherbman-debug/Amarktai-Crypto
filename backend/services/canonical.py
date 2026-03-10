"""
Canonical Truth Service
=======================

Single source of truth for bot counts and wallet funded status.

ALL endpoints that expose active-bot counts or wallet state MUST call
these helpers rather than computing independently.  This prevents the
endpoint-disagreement issues seen in production.

Public API
----------
get_canonical_bot_counts(user_id)  -> BotCounts
get_canonical_wallet_truth(user_id) -> WalletTruth
"""

from __future__ import annotations

from typing import Dict, Any, List
from datetime import datetime, timezone
import logging

import database as db
from utils.bot_state import normalize_bot_state
from config import PAPER_STARTING_CAPITAL_ZAR
from services.paper_wallet_service import paper_wallet_service

logger = logging.getLogger(__name__)

# Maximum number of bots fetched in a single query (shared constant).
_MAX_BOTS = 500


async def get_canonical_bot_counts(user_id: str) -> Dict[str, Any]:
    """Return canonical bot counts scoped to *user_id*.

    The only bots counted are those whose DB document is not in a
    deletion state.  ``normalize_bot_state`` is applied to each bot so
    that the ``active`` and ``eligible_to_trade`` flags are derived
    identically regardless of which endpoint calls this function.

    Returns
    -------
    dict with keys:
        total          – all non-deleted bots
        active         – status == "active" (not paused/stopped/deleted)
        runnable       – active AND eligible_to_trade
        paused         – paused but not deleted
        stopped        – stopped but not deleted
        training       – in training / quarantined
        scalper_count  – bots with bot_type == "scalper"
        normal_count   – bots with bot_type != "scalper"
        by_exchange    – {exchange: count_of_all_bots}
    """
    if db.bots_collection is None:
        return _empty_counts()

    try:
        raw = await db.bots_collection.find(
            {
                "user_id": user_id,
                "status": {"$nin": ["deleted", "marked_for_deletion"]},
                "deleted": {"$ne": True},
                "is_deleted": {"$ne": True},
                "deleted_at": {"$exists": False},
            },
            {"_id": 0},
        ).to_list(length=_MAX_BOTS)
    except Exception as exc:
        logger.error("get_canonical_bot_counts DB error for user %s: %s", user_id, exc)
        return _empty_counts()

    normalized = [normalize_bot_state(b) for b in raw]

    active = sum(1 for b in normalized if b.get("active"))
    paused = sum(1 for b in normalized if b.get("paused") and not b.get("active"))
    stopped = sum(1 for b in normalized if b.get("stopped"))
    training = sum(
        1 for b in normalized
        if b.get("status") in {"training", "quarantined", "quarantine", "training_failed"}
    )
    runnable = sum(1 for b in normalized if b.get("eligible_to_trade"))
    scalper = sum(1 for b in normalized if b.get("bot_type") == "scalper")
    uagent = sum(1 for b in normalized if b.get("bot_type") == "uagent")
    normal = len(normalized) - scalper - uagent

    by_exchange: Dict[str, int] = {}
    for b in raw:
        ex = b.get("exchange") or "unknown"
        by_exchange[ex] = by_exchange.get(ex, 0) + 1

    return {
        "total": len(normalized),
        "active": active,
        "runnable": runnable,
        "paused": paused,
        "stopped": stopped,
        "training": training,
        "scalper_count": scalper,
        "uagent_count": uagent,
        "normal_count": normal,
        "by_exchange": by_exchange,
    }


async def get_canonical_trade_counts(user_id: str) -> Dict[str, int]:
    """Return canonical closed-trade totals scoped to active user bots.

    This mirrors overview snapshot semantics so diagnostics/countdown/history
    surfaces don't drift from each other.
    """
    if db.bots_collection is None or db.trades_collection is None:
        return {"total": 0, "today": 0}

    try:
        bots = await db.bots_collection.find(
            {
                "user_id": user_id,
                "status": {"$nin": ["deleted", "marked_for_deletion"]},
                "deleted": {"$ne": True},
                "is_deleted": {"$ne": True},
                "deleted_at": {"$exists": False},
            },
            {"_id": 0, "id": 1},
        ).to_list(length=_MAX_BOTS)
        bot_ids = [b.get("id") for b in bots if b.get("id")]
        if not bot_ids:
            return {"total": 0, "today": 0}

        today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
        total = await db.trades_collection.count_documents({
            "bot_id": {"$in": bot_ids},
            "status": "closed",
        })
        today = await db.trades_collection.count_documents({
            "bot_id": {"$in": bot_ids},
            "status": "closed",
            "timestamp": {"$gte": today_start},
        })
        return {"total": int(total or 0), "today": int(today or 0)}
    except Exception as exc:
        logger.warning("get_canonical_trade_counts failed for user %s: %s", user_id, exc)
        return {"total": 0, "today": 0}


async def get_canonical_wallet_truth(user_id: str) -> Dict[str, Any]:
    """Return canonical wallet funded-state for *user_id*.

    Logic (deterministic, no contradictions):
    - ``total``        = available ZAR from paper wallet service
    - ``required``     = sum of initial_capital across all active bots
    - ``shortfall``    = max(0, required - total)
    - ``funded_status`` = "FUNDED" iff shortfall <= 0 AND total > 0
                          "UNFUNDED" otherwise
    - ``status``       = same as funded_status (never contradicts)
    """
    # --- wallet balance --------------------------------------------------
    total = 0.0
    try:
        balances_data = await paper_wallet_service.get_balances(user_id)
        total = float(balances_data.get("total", 0) or 0)
    except Exception as exc:
        logger.warning("get_canonical_wallet_truth: wallet fetch failed: %s", exc)

    # --- required capital ------------------------------------------------
    required = 0.0
    try:
        if db.bots_collection is not None:
            raw = await db.bots_collection.find(
                {
                    "user_id": user_id,
                    "status": {"$nin": ["deleted", "marked_for_deletion"]},
                    "deleted": {"$ne": True},
                    "is_deleted": {"$ne": True},
                    "deleted_at": {"$exists": False},
                },
                {"_id": 0, "status": 1, "initial_capital": 1, "trading_mode": 1, "mode": 1},
            ).to_list(length=_MAX_BOTS)
            for b in raw:
                normalized = normalize_bot_state(b)
                if normalized.get("active"):
                    required += float(b.get("initial_capital") or PAPER_STARTING_CAPITAL_ZAR)
    except Exception as exc:
        logger.warning("get_canonical_wallet_truth: bots query failed: %s", exc)

    shortfall = max(0.0, required - total)
    # A wallet is FUNDED iff:
    #  - it has a positive balance (total > 0), AND
    #  - it covers all active bot requirements (shortfall == 0).
    # total=0 is always UNFUNDED, regardless of required.
    is_funded = (total > 0) and (shortfall <= 0)
    funded_status = "FUNDED" if is_funded else "UNFUNDED"

    return {
        "total": round(total, 2),
        "required": round(required, 2),
        "shortfall": round(shortfall, 2),
        "funded_status": funded_status,
        "status": funded_status,  # always mirrors funded_status
    }


def _empty_counts() -> Dict[str, Any]:
    return {
        "total": 0,
        "active": 0,
        "runnable": 0,
        "paused": 0,
        "stopped": 0,
        "training": 0,
        "scalper_count": 0,
        "uagent_count": 0,
        "normal_count": 0,
        "by_exchange": {},
    }


async def _get_active_user_bot_ids(user_id: str) -> List[str]:
    if db.bots_collection is None:
        return []
    bots = await db.bots_collection.find(
        {
            "user_id": user_id,
            "status": {"$nin": ["deleted", "marked_for_deletion"]},
            "deleted": {"$ne": True},
            "is_deleted": {"$ne": True},
            "deleted_at": {"$exists": False},
        },
        {"_id": 0, "id": 1},
    ).to_list(length=_MAX_BOTS)
    return [str(b.get("id")) for b in bots if b.get("id")]


async def get_canonical_open_position_count(user_id: str) -> int:
    """Canonical open-position count derived from user bots + open trades."""
    if db.trades_collection is None:
        return 0
    try:
        bot_ids = await _get_active_user_bot_ids(user_id)
        if not bot_ids:
            return 0
        return int(await db.trades_collection.count_documents({
            "bot_id": {"$in": bot_ids},
            "status": {"$in": ["open", "active", "pending"]},
        }))
    except Exception as exc:
        logger.warning("get_canonical_open_position_count failed for user %s: %s", user_id, exc)
        return 0


async def get_canonical_paper_wallet_equity(user_id: str) -> Dict[str, Any]:
    """Canonical paper-wallet equity including available + allocated balances."""
    available_total = 0.0
    allocated_total = 0.0
    try:
        available = await paper_wallet_service.get_balances(user_id)
        available_total = float(available.get("total", 0) or 0)
    except Exception as exc:
        logger.warning("paper wallet available fetch failed for %s: %s", user_id, exc)

    try:
        if db.paper_ledger_collection is not None:
            pipeline = [
                {"$match": {"user_id": user_id, "status": "active"}},
                {"$group": {"_id": None, "total": {"$sum": "$current_balance"}}},
            ]
            rows = await db.paper_ledger_collection.aggregate(pipeline).to_list(1)
            if rows:
                allocated_total = float(rows[0].get("total", 0) or 0)
    except Exception as exc:
        logger.warning("paper wallet allocated fetch failed for %s: %s", user_id, exc)

    total_equity = max(0.0, available_total + allocated_total)
    return {
        "total_equity": round(total_equity, 2),
        "available_total": round(available_total, 2),
        "allocated_total": round(allocated_total, 2),
        "source": "paper_wallet_total_equity",
    }
