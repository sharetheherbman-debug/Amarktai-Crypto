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
import inspect

import database as db
from utils.bot_state import normalize_bot_state
from config import PAPER_STARTING_CAPITAL_ZAR
from services.paper_wallet_service import paper_wallet_service

logger = logging.getLogger(__name__)

# Maximum number of bots fetched in a single query (shared constant).
_MAX_BOTS = 500


async def get_canonical_bot_activity(user_id: str) -> Dict[str, Any]:
    """Return canonical bot activity semantics snapshot scoped to *user_id*.

    Canonical meaning:
    - total_bot_records: all non-deleted bot documents
    - active_bot_records: active docs (status active after normalization)
    - runnable_active_bots: active docs with eligible_to_trade=True
    - paused_bots: paused docs
    - bots_with_open_positions: active bots that currently have open trades
    - blocked_bots: active docs not runnable
    - non_runnable_reasons: machine-readable reasons grouped with counts

    This function is the canonical source used by routes and scheduler-facing
    summaries so "active" and "runnable" are never conflated.
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

    active_bots = [b for b in normalized if b.get("active")]
    active = len(active_bots)
    paused = sum(1 for b in normalized if b.get("paused") and not b.get("active"))
    stopped = sum(1 for b in normalized if b.get("stopped"))
    training = sum(
        1 for b in normalized
        if b.get("status") in {"training", "quarantined", "quarantine", "training_failed"}
    )
    runnable = sum(1 for b in active_bots if b.get("eligible_to_trade"))
    scalper = sum(1 for b in normalized if b.get("bot_type") == "scalper")
    uagent = sum(1 for b in normalized if b.get("bot_type") == "uagent")
    normal = len(normalized) - scalper - uagent

    blocked_reasons: Dict[str, int] = {}
    for bot in active_bots:
        if bot.get("eligible_to_trade"):
            continue
        for reason in bot.get("not_eligible_reasons", []):
            blocked_reasons[reason] = blocked_reasons.get(reason, 0) + 1

    bots_with_open_positions = 0
    active_bot_ids = [str(b.get("id")) for b in active_bots if b.get("id")]
    if active_bot_ids and db.trades_collection is not None and hasattr(db.trades_collection, "distinct"):
        try:
            distinct_call = db.trades_collection.distinct(
                "bot_id",
                {"bot_id": {"$in": active_bot_ids}, "status": {"$in": ["open", "active", "pending"]}},
            )
            open_bot_ids = await distinct_call if inspect.isawaitable(distinct_call) else distinct_call
            bots_with_open_positions = len(open_bot_ids or [])
        except Exception as exc:
            logger.warning("get_canonical_bot_activity open-position query failed for user %s: %s", user_id, exc)

    by_exchange: Dict[str, int] = {}
    for b in raw:
        ex = b.get("exchange") or "unknown"
        by_exchange[ex] = by_exchange.get(ex, 0) + 1

    return {
        "total_bot_records": len(normalized),
        "active_bot_records": active,
        "runnable_active_bots": runnable,
        "paused_bots": paused,
        "bots_with_open_positions": bots_with_open_positions,
        "blocked_bots": max(0, active - runnable),
        "non_runnable_reasons": blocked_reasons,
        # Backward-compatible aliases
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


async def get_canonical_bot_counts(user_id: str) -> Dict[str, Any]:
    """Backward-compatible wrapper for canonical bot activity semantics."""
    return await get_canonical_bot_activity(user_id)


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
        "total_bot_records": 0,
        "active_bot_records": 0,
        "runnable_active_bots": 0,
        "paused_bots": 0,
        "bots_with_open_positions": 0,
        "blocked_bots": 0,
        "non_runnable_reasons": {},
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


async def get_latest_bot_decisions(user_id: str, bot_ids: List[str]) -> Dict[str, Dict[str, Any]]:
    """Return latest machine-readable decision payload per bot for radar/status surfaces."""
    collection = getattr(db, "decisions_collection", None)
    if collection is None or not bot_ids:
        return {}

    latest: Dict[str, Dict[str, Any]] = {}
    try:
        fetch_limit = max(len(bot_ids) * 5, 50)
        rows = await collection.find(
            {"user_id": user_id, "bot_id": {"$in": bot_ids}},
            {"_id": 0, "bot_id": 1, "decision": 1, "reason_code": 1, "details": 1, "timestamp": 1},
        ).sort("timestamp", -1).limit(fetch_limit).to_list(length=fetch_limit)
    except Exception as exc:
        logger.warning("get_latest_bot_decisions failed for user %s: %s", user_id, exc)
        return {}

    for row in rows:
        bot_id = str(row.get("bot_id") or "")
        if not bot_id or bot_id in latest:
            continue
        details = row.get("details") or {}
        regime_details = details.get("regime") if isinstance(details.get("regime"), dict) else {}
        reason_code = row.get("reason_code")
        fallback_reasons = [str(reason_code).lower()] if row.get("decision") in {"reject", "stand_down"} and reason_code else []
        latest[bot_id] = {
            "decision": row.get("decision"),
            "decision_reason_code": reason_code,
            "entry_reason_code": details.get("entry_reason_code") or reason_code,
            "entry_confidence_score": details.get("entry_confidence_score"),
            "expectancy_net_edge_pct": details.get("expectancy_net_edge_pct"),
            "market_regime": regime_details.get("regime"),
            "canonical_regime_confidence": regime_details.get("confidence"),
            "not_eligible_reasons": details.get("rejection_reasons") or fallback_reasons,
        }
    return latest
