"""
Canonical Metrics Service
=========================

Single source of truth for per-bot and portfolio trading metrics.

This module aggregates closed-trade data and bot capital fields to provide
consistent metrics consumed by routes/UI.
"""

from __future__ import annotations

from typing import Dict, Any, List, Optional

# database import is deferred to individual async functions to allow
# this module to be imported in environments without motor/pymongo.
import inspect


def _num(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _empty_snapshot() -> Dict[str, Any]:
    return {
        "summary": {
            "capital_initial": 0.0,
            "capital_current": 0.0,
            "capital_allocated": 0.0,
            "capital_available": 0.0,
            "open_position_value": 0.0,
            "profit_realized": 0.0,
            "roi_pct": 0.0,
            "trade_count": 0,
            "winning_trades": 0,
            "losing_trades": 0,
            "win_rate_pct": 0.0,
            "bot_count": 0,
        },
        "by_bot_id": {},
    }


def build_canonical_capital_summary(
    *,
    capital_initial: float,
    capital_allocated: float,
    capital_available: float,
    open_position_value: float,
    profit_realized: float,
    unrealized_profit: float = 0.0,
) -> Dict[str, Any]:
    """Frontend-safe canonical capital semantics for a bot."""
    total_equity = max(0.0, capital_available + open_position_value + unrealized_profit)
    return {
        "initial_capital": round(capital_initial, 2),
        "allocated_capital": round(capital_allocated, 2),
        "available_capital": round(capital_available, 2),
        "open_position_value": round(open_position_value, 2),
        "total_equity": round(total_equity, 2),
        "realized_profit": round(profit_realized, 2),
        "unrealized_profit": round(unrealized_profit, 2),
        "semantics": {
            "initial_capital": "Starting capital assigned when the bot was created.",
            "allocated_capital": "Capital currently assigned to this bot for trading.",
            "available_capital": "Uncommitted capital available for new entries.",
            "open_position_value": "Current marked value of capital in open positions.",
            "total_equity": "Available capital + open position value + unrealized profit.",
            "realized_profit": "Closed-trade profit/loss already realized.",
            "unrealized_profit": "Profit/loss on currently open positions (estimate).",
        },
    }


async def backfill_missing_current_capital(user_id: str) -> int:
    """Set current_capital=initial_capital where missing/null for user's active bots."""
    import database as db  # deferred to avoid import-time motor dependency
    if db.bots_collection is None or not hasattr(db.bots_collection, "update_many"):
        return 0
    update_call = db.bots_collection.update_many(
        {
            "user_id": user_id,
            "status": {"$nin": ["deleted", "marked_for_deletion"]},
            "$or": [
                {"current_capital": {"$exists": False}},
                {"current_capital": None},
            ],
            "initial_capital": {"$exists": True},
        },
        [{"$set": {"current_capital": "$initial_capital"}}],
    )
    result = await update_call if inspect.isawaitable(update_call) else update_call
    return int(result.modified_count or 0)


async def get_canonical_metrics_snapshot(user_id: str, bots: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """
    Return canonical metrics snapshot for user's non-deleted bots.

    Shape:
    - summary: aggregate portfolio metrics
    - by_bot_id: per-bot standardized metrics
    """
    import database as db  # deferred to avoid import-time motor dependency
    if bots is None and db.bots_collection is None:
        return _empty_snapshot()

    if db.bots_collection is not None:
        await backfill_missing_current_capital(user_id)

    if bots is None:
        bots = await db.bots_collection.find(
            {
                "user_id": user_id,
                "status": {"$nin": ["deleted", "marked_for_deletion"]},
                "deleted": {"$ne": True},
                "is_deleted": {"$ne": True},
                "deleted_at": {"$exists": False},
            },
            {"_id": 0},
        ).to_list(2000)

    bot_ids = [b.get("id") for b in bots if b.get("id")]
    trade_stats_map: Dict[str, Dict[str, Any]] = {}

    if bot_ids and db.trades_collection is not None:
        pnl_expr = {"$ifNull": ["$net_pnl", {"$ifNull": ["$profit_loss", 0]}]}
        trade_stats = await db.trades_collection.aggregate([
            {"$match": {"user_id": user_id, "bot_id": {"$in": bot_ids}, "status": "closed"}},
            {"$group": {
                "_id": "$bot_id",
                "trade_count": {"$sum": 1},
                "winning_trades": {"$sum": {"$cond": [{"$gt": [pnl_expr, 0]}, 1, 0]}},
                "losing_trades": {"$sum": {"$cond": [{"$lt": [pnl_expr, 0]}, 1, 0]}},
                "profit_realized": {"$sum": pnl_expr},
            }},
        ]).to_list(5000)
        trade_stats_map = {str(item.get("_id")): item for item in trade_stats}

    by_bot_id: Dict[str, Dict[str, Any]] = {}
    summary = _empty_snapshot()["summary"]

    for bot in bots:
        bot_id = str(bot.get("id", ""))
        if not bot_id:
            continue

        capital_initial = _num(bot.get("initial_capital", bot.get("starting_capital", 0)))
        capital_current = _num(bot.get("current_capital", bot.get("allocated_capital", capital_initial)))
        open_position_value = _num(bot.get("open_position_value", 0))
        capital_allocated = capital_current
        capital_available = max(0.0, capital_current - open_position_value)

        trade_stats = trade_stats_map.get(bot_id, {})
        trade_count = int(trade_stats.get("trade_count", trade_stats.get("total_trades", bot.get("trades_count", 0))) or 0)
        winning_trades = int(trade_stats.get("winning_trades", trade_stats.get("wins", bot.get("win_count", 0))) or 0)
        losing_trades = int(trade_stats.get("losing_trades", trade_stats.get("losses", bot.get("loss_count", 0))) or 0)
        profit_realized = _num(trade_stats.get("profit_realized", trade_stats.get("realized_pnl", bot.get("total_profit", 0))))

        if trade_count > 0:
            win_rate_pct = (winning_trades / trade_count) * 100.0
        else:
            raw_win = _num(bot.get("win_rate", 0))
            win_rate_pct = raw_win * 100.0 if 0 < raw_win <= 1 else raw_win

        roi_pct = (profit_realized / capital_initial * 100.0) if capital_initial > 0 else 0.0

        by_bot_id[bot_id] = {
            "capital_initial": round(capital_initial, 2),
            "capital_current": round(capital_current, 2),
            "capital_allocated": round(capital_allocated, 2),
            "capital_available": round(capital_available, 2),
            "open_position_value": round(open_position_value, 2),
            "profit_realized": round(profit_realized, 2),
            "capital_summary": build_canonical_capital_summary(
                capital_initial=capital_initial,
                capital_allocated=capital_allocated,
                capital_available=capital_available,
                open_position_value=open_position_value,
                profit_realized=profit_realized,
                unrealized_profit=_num(bot.get("unrealized_profit", 0)),
            ),
            "roi_pct": round(roi_pct, 2),
            "trade_count": trade_count,
            "winning_trades": winning_trades,
            "losing_trades": losing_trades,
            "win_rate_pct": round(win_rate_pct, 2),
        }

        summary["capital_initial"] += capital_initial
        summary["capital_current"] += capital_current
        summary["capital_allocated"] += capital_allocated
        summary["capital_available"] += capital_available
        summary["open_position_value"] += open_position_value
        summary["profit_realized"] += profit_realized
        summary["trade_count"] += trade_count
        summary["winning_trades"] += winning_trades
        summary["losing_trades"] += losing_trades
        summary["bot_count"] += 1

    if summary["trade_count"] > 0:
        summary["win_rate_pct"] = round((summary["winning_trades"] / summary["trade_count"]) * 100.0, 2)
    if summary["capital_initial"] > 0:
        summary["roi_pct"] = round((summary["profit_realized"] / summary["capital_initial"]) * 100.0, 2)

    for key in ("capital_initial", "capital_current", "capital_allocated", "capital_available", "open_position_value", "profit_realized"):
        summary[key] = round(summary[key], 2)

    return {"summary": summary, "by_bot_id": by_bot_id}
