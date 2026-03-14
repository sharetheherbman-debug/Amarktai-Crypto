"""
Canonical Metrics Service
=========================

Single source of truth for per-bot and portfolio trading metrics.

This module aggregates closed-trade data and bot capital fields to provide
consistent metrics consumed by routes/UI.

Currency rule:
- ALL internal aggregation is in ZAR (the canonical internal currency).
- Per-bot records expose quote_currency and display_currency so the UI
  can show native values (e.g. "52.63 USDT") alongside the ZAR equivalent.
- When display_currency != "ZAR", all aggregated ZAR totals are converted
  to the requested display currency (USD/GBP/EUR) via fx_normalizer before
  being returned to the caller.
"""

from __future__ import annotations

from typing import Dict, Any, List, Optional

import database as db
import inspect

from services.fx_normalizer import (
    get_quote_currency as _gqc,
    get_fx_rate as _gfr,
    to_display_currency as _to_display,
    SUPPORTED_DISPLAY_CURRENCIES,
)


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
    quote_currency: str = "ZAR",
    display_currency: str = "ZAR",
) -> Dict[str, Any]:
    """Frontend-safe canonical capital semantics for a bot.

    All monetary fields (capital_initial, capital_allocated, etc.) must
    already be expressed in *display_currency* (ZAR) before being passed
    to this function.  The caller is responsible for the FX conversion.
    """
    total_equity = max(0.0, capital_available + open_position_value + unrealized_profit)
    return {
        "initial_capital": round(capital_initial, 2),
        "allocated_capital": round(capital_allocated, 2),
        "available_capital": round(capital_available, 2),
        "open_position_value": round(open_position_value, 2),
        "total_equity": round(total_equity, 2),
        "realized_profit": round(profit_realized, 2),
        "unrealized_profit": round(unrealized_profit, 2),
        "quote_currency": quote_currency,
        "display_currency": display_currency,
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


async def get_canonical_metrics_snapshot(
    user_id: str,
    bots: Optional[List[Dict[str, Any]]] = None,
    display_currency: str = "ZAR",
) -> Dict[str, Any]:
    """
    Return canonical metrics snapshot for user's non-deleted bots.

    Shape:
    - summary: aggregate portfolio metrics (all monetary values in *display_currency*)
    - by_bot_id: per-bot standardized metrics (display values in *display_currency*)

    Internal aggregation is always in ZAR.  The final totals are converted to
    *display_currency* (ZAR/USD/GBP/EUR) before being returned.

    Per-bot entries always expose:
    - quote_currency: native trade currency (e.g. "USDT" for Binance)
    - display_currency: requested presentation currency
    - capital_initial_quote: native amount (e.g. 52.63 USDT)
    - capital_initial: display amount (e.g. 1000.0 ZAR, or 54.05 USD)
    """
    dc = str(display_currency or "ZAR").upper()
    if dc not in SUPPORTED_DISPLAY_CURRENCIES:
        dc = "ZAR"

    # Pre-compute ZAR→display rate once before the per-bot loop to avoid
    # a redundant FX lookup on every monetary field for every bot.
    _dc_rate, _dc_source = _gfr("ZAR", dc)

    def _cvt(zar_val: float) -> float:
        if zar_val is None:
            return 0.0
        return round(float(zar_val) * _dc_rate, 2)

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
        # Prefer realized_pnl_zar (pre-converted ZAR value stored by enrich_trade_pnl_fields).
        # Fall back to net_pnl for older trades that pre-date the reconciliation layer.
        # NOTE: for per-bot aggregates this is safe because each bot only trades on one
        # exchange (single currency), so the raw sum is in a consistent native currency
        # which we then convert to ZAR in the Python loop below.
        pnl_expr = {"$ifNull": ["$net_pnl", {"$ifNull": ["$profit_loss", 0]}]}
        # Use realized_pnl_zar when available so newer trades are already in ZAR.
        pnl_zar_expr = {"$ifNull": ["$realized_pnl_zar", None]}
        trade_stats = await db.trades_collection.aggregate([
            {"$match": {"user_id": user_id, "bot_id": {"$in": bot_ids}, "status": "closed"}},
            {"$group": {
                "_id": "$bot_id",
                "trade_count": {"$sum": 1},
                "winning_trades": {"$sum": {"$cond": [{"$gt": [pnl_expr, 0]}, 1, 0]}},
                "losing_trades": {"$sum": {"$cond": [{"$lt": [pnl_expr, 0]}, 1, 0]}},
                # Sum raw quote-currency PnL — converted to ZAR in the Python loop below
                "profit_realized_raw": {"$sum": pnl_expr},
                # Sum pre-converted ZAR PnL for trades that have it (newer trades)
                "profit_realized_zar_sum": {"$sum": {"$ifNull": ["$realized_pnl_zar", 0]}},
                # Count of trades that have realized_pnl_zar set
                "trades_with_zar_field": {"$sum": {"$cond": [
                    {"$ne": [{"$type": "$realized_pnl_zar"}, "null"]}, 1, 0
                ]}},
            }},
        ]).to_list(5000)
        trade_stats_map = {str(item.get("_id")): item for item in trade_stats}

    by_bot_id: Dict[str, Dict[str, Any]] = {}
    summary = _empty_snapshot()["summary"]

    for bot in bots:
        bot_id = str(bot.get("id", ""))
        if not bot_id:
            continue

        # ── Currency resolution ──────────────────────────────────────────────
        exchange = (bot.get("exchange") or "").lower()
        quote_currency = bot.get("quote_currency") or _gqc(exchange, "")
        fx_rate, fx_source = _gfr(quote_currency, "ZAR")

        # ── Capital in ZAR ───────────────────────────────────────────────────
        # Initial: prefer canonical_base_capital_zar (stored at creation — exact)
        canonical_base_zar = bot.get("canonical_base_capital_zar")
        if canonical_base_zar is not None:
            capital_initial_zar = float(canonical_base_zar)
        else:
            capital_initial_raw = _num(bot.get("initial_capital", bot.get("starting_capital", 0)))
            capital_initial_zar = capital_initial_raw * fx_rate

        # Current: convert live capital at current FX rate
        capital_current_explicit = bot.get("current_capital", bot.get("allocated_capital"))
        if capital_current_explicit is not None:
            capital_current_raw = _num(capital_current_explicit)
        else:
            # Fallback: derive from initial capital (avoids divide-by-zero if fx_rate=0)
            capital_current_raw = capital_initial_zar / fx_rate if fx_rate else 0.0
        capital_current_zar = capital_current_raw * fx_rate

        open_position_value_raw = _num(bot.get("open_position_value", 0))
        open_position_value_zar = open_position_value_raw * fx_rate
        capital_allocated_zar = capital_current_zar
        capital_available_zar = max(0.0, capital_current_zar - open_position_value_zar)

        # ── Profit in ZAR ────────────────────────────────────────────────────
        trade_stats = trade_stats_map.get(bot_id, {})
        trade_count = int(trade_stats.get("trade_count", trade_stats.get("total_trades", bot.get("trades_count", 0))) or 0)
        winning_trades = int(trade_stats.get("winning_trades", trade_stats.get("wins", bot.get("win_count", 0))) or 0)
        losing_trades = int(trade_stats.get("losing_trades", trade_stats.get("losses", bot.get("loss_count", 0))) or 0)

        # Use pre-converted ZAR sum if ALL trades have realized_pnl_zar; otherwise
        # convert the raw sum using the bot's quote currency (safe per-bot since
        # all trades for one bot are in the same currency).
        trades_with_zar = int(trade_stats.get("trades_with_zar_field", 0))
        if trades_with_zar == trade_count and trade_count > 0:
            profit_realized_zar = _num(trade_stats.get("profit_realized_zar_sum", 0))
        else:
            profit_realized_raw = _num(trade_stats.get("profit_realized_raw", trade_stats.get("realized_pnl", bot.get("total_profit", 0))))
            profit_realized_zar = profit_realized_raw * fx_rate

        if trade_count > 0:
            win_rate_pct = (winning_trades / trade_count) * 100.0
        else:
            raw_win = _num(bot.get("win_rate", 0))
            win_rate_pct = raw_win * 100.0 if 0 < raw_win <= 1 else raw_win

        roi_pct = (profit_realized_zar / capital_initial_zar * 100.0) if capital_initial_zar > 0 else 0.0

        by_bot_id[bot_id] = {
            # Display-currency values (presented to the user in their chosen currency)
            "capital_initial": round(_cvt(capital_initial_zar), 2),
            "capital_current": round(_cvt(capital_current_zar), 2),
            "capital_allocated": round(_cvt(capital_allocated_zar), 2),
            "capital_available": round(_cvt(capital_available_zar), 2),
            "open_position_value": round(_cvt(open_position_value_zar), 2),
            "profit_realized": round(_cvt(profit_realized_zar), 2),
            # ZAR internal values (always present for downstream logic)
            "capital_initial_zar": round(capital_initial_zar, 2),
            "capital_current_zar": round(capital_current_zar, 2),
            "profit_realized_zar": round(profit_realized_zar, 2),
            # Native quote values for per-bot display
            # These are the AUTHORITATIVE native amounts (e.g. 52.63 USDT for a
            # Binance bot funded with R1000).  bot_lifecycle.py must use these
            # fields for initial_capital / current_capital so that
            # total_equity_display = quote * fx_rate stays in the ~R1000 range
            # instead of being inflated 19× to ~R19 000.
            "capital_initial_quote": round(_num(bot.get("initial_capital", bot.get("starting_capital", 0))), 2),
            "capital_current_quote": round(capital_current_raw, 2),
            "capital_available_quote": round(max(0.0, capital_current_raw - open_position_value_raw), 2),
            "open_position_value_quote": round(open_position_value_raw, 2),
            "quote_currency": quote_currency,
            "display_currency": dc,
            "fx_rate_used": round(fx_rate, 4),
            "fx_source": fx_source,
            "capital_summary": build_canonical_capital_summary(
                capital_initial=_cvt(capital_initial_zar),
                capital_allocated=_cvt(capital_allocated_zar),
                capital_available=_cvt(capital_available_zar),
                open_position_value=_cvt(open_position_value_zar),
                profit_realized=_cvt(profit_realized_zar),
                unrealized_profit=_cvt(_num(bot.get("unrealized_profit", 0)) * fx_rate),
                quote_currency=quote_currency,
                display_currency=dc,
            ),
            "roi_pct": round(roi_pct, 2),
            "trade_count": trade_count,
            "winning_trades": winning_trades,
            "losing_trades": losing_trades,
            "win_rate_pct": round(win_rate_pct, 2),
        }

        summary["capital_initial"] += capital_initial_zar
        summary["capital_current"] += capital_current_zar
        summary["capital_allocated"] += capital_allocated_zar
        summary["capital_available"] += capital_available_zar
        summary["open_position_value"] += open_position_value_zar
        summary["profit_realized"] += profit_realized_zar
        summary["trade_count"] += trade_count
        summary["winning_trades"] += winning_trades
        summary["losing_trades"] += losing_trades
        summary["bot_count"] += 1

    if summary["trade_count"] > 0:
        summary["win_rate_pct"] = round((summary["winning_trades"] / summary["trade_count"]) * 100.0, 2)
    # ROI uses ZAR internal values (currency-invariant ratio)
    if summary["capital_initial"] > 0:
        summary["roi_pct"] = round((summary["profit_realized"] / summary["capital_initial"]) * 100.0, 2)

    # Convert summary monetary fields to display_currency using pre-computed rate
    for key in ("capital_initial", "capital_current", "capital_allocated", "capital_available", "open_position_value", "profit_realized"):
        summary[key] = round(_cvt(summary[key]), 2)

    summary["display_currency"] = dc
    summary["fx_metadata"] = {
        "zar_to_display_rate": round(_dc_rate, 6),
        "zar_to_display_source": _dc_source,
        "internal_currency": "ZAR",
    }

    return {"summary": summary, "by_bot_id": by_bot_id}
