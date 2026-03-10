"""
Radar Endpoints - Bot Radar / Bot Map visualization data

Provides per-bot radar data derived from ledger/trade truth:
  bot_id, name, exchange, symbol, side,
  entry_price, current_price, target_price, stop_price, trailing_stop_price,
  realized_pnl_today, unrealized_pnl,
  daily_profit_target, trade_profit_target,
  position_opened_at, max_hold_seconds, remaining_hold_seconds,
  next_action, next_action_reason_code, next_action_reason_text,
  market_regime, spread_estimate, slippage_estimate
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional
import logging

from auth import get_current_user
import database as db
from utils.bot_state import normalize_bot_state
from services.hold_policy import resolve_hold_policy
from services.canonical import get_canonical_open_position_count, get_latest_bot_decisions

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/radar", tags=["Radar"])

RISK_THRESHOLD_PCT = 0.03             # 3% unrealized loss triggers risk exit
EXIT_FORECAST_TIME_THRESHOLD = 600    # 600 seconds (10 min) — time exit proximity threshold
NO_STOP_DISTANCE = 999.0              # sentinel — distance when no stop price is configured


def _safe_float(value, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _configured_bot_pct(bot: Dict, *keys: str) -> Optional[float]:
    """Return first configured non-negative percentage from bot payload keys."""
    for key in keys:
        value = bot.get(key)
        if value is None:
            continue
        try:
            pct = float(value)
        except (TypeError, ValueError):
            continue
        return max(0.0, pct)
    return None


def _format_hold_timer(elapsed_seconds: float) -> str:
    """Human-readable hold timer like '2h 15m' or '45s'."""
    if elapsed_seconds < 60:
        return f"{int(elapsed_seconds)}s"
    if elapsed_seconds < 3600:
        return f"{int(elapsed_seconds // 60)}m {int(elapsed_seconds % 60)}s"
    hours = int(elapsed_seconds // 3600)
    mins = int((elapsed_seconds % 3600) // 60)
    return f"{hours}h {mins}m"


def _compute_exit_forecast(
    entry_price: float,
    current_price: float,
    target_price: Optional[float],
    stop_price: Optional[float],
    remaining_seconds: float,
    unrealized_pnl: float,
) -> Optional[str]:
    """Forecast the most likely exit scenario."""
    if target_price and entry_price > 0:
        dist_to_target = abs(target_price - current_price) / entry_price
        dist_to_stop = abs(current_price - stop_price) / entry_price if stop_price else NO_STOP_DISTANCE
        if dist_to_target < dist_to_stop:
            return "likely_target"
        elif remaining_seconds < EXIT_FORECAST_TIME_THRESHOLD:
            return "likely_time_exit"
        elif unrealized_pnl < 0:
            return "at_risk"
        else:
            return "holding"
    if remaining_seconds < EXIT_FORECAST_TIME_THRESHOLD:
        return "likely_time_exit"
    if unrealized_pnl < 0:
        return "at_risk"
    return "holding"


def _compute_radar_entry(bot: Dict, open_trade: Optional[Dict], now: datetime) -> Dict:
    """Build a single radar entry from bot + its current open trade."""
    bot_id = str(bot.get("id") or bot.get("_id") or bot.get("bot_id", ""))
    hold_policy = resolve_hold_policy(bot, open_trade=open_trade)
    max_hold = int(hold_policy["max_hold_seconds"])
    capital = float(bot.get("current_capital", bot.get("initial_capital", 0)))
    daily_target_pct = _configured_bot_pct(bot, "daily_profit_target_pct", "daily_target_pct")
    trade_target_pct = _configured_bot_pct(bot, "trade_profit_target_pct", "per_trade_target_pct")
    daily_target = round(capital * daily_target_pct, 2) if daily_target_pct is not None else None
    trade_target = round(capital * trade_target_pct, 2) if trade_target_pct is not None else None

    entry = {
        "bot_id": bot_id,
        "bot_type": bot.get("bot_type", "normal"),
        "name": bot.get("name", f"Bot-{bot_id[:6]}"),
        "exchange": bot.get("exchange", "unknown"),
        "symbol": bot.get("pair", bot.get("symbol", "unknown")),
        "side": None,
        "entry_price": None,
        "current_price": None,
        "target_price": None,
        "stop_price": None,
        "trailing_stop_price": None,
        "realized_pnl_today": float(bot.get("realized_pnl_today", 0)),
        "unrealized_pnl": 0.0,
        "capital_allocated": capital,
        "exposure_pct": 0.0,
        "daily_profit_target": daily_target,
        "trade_profit_target": trade_target,
        "targets_configured": daily_target_pct is not None and trade_target_pct is not None,
        "target_source": "configured" if (daily_target_pct is not None or trade_target_pct is not None) else "not_configured",
        "position_opened_at": None,
        "max_hold_seconds": max_hold,
        "hold_policy_source": hold_policy["source"],
        "remaining_hold_seconds": None,
        "hold_timer_display": None,
        "next_action": "WAIT",
        "next_action_reason_code": "NO_POSITION",
        "next_action_reason_text": "No open position – waiting for entry signal",
        "market_regime": bot.get("market_regime", "unknown"),
        "regime_confidence": float(bot.get("canonical_regime_confidence", bot.get("confidence_score", bot.get("confidence", 0)))),
        "confidence_score": float(bot.get("confidence_score", bot.get("confidence", 0))),
        "decision_reason_code": bot.get("decision_reason_code", bot.get("last_decision_reason_code")),
        "entry_reason_code": bot.get("entry_reason_code", bot.get("last_entry_reason_code")),
        "entry_confidence_score": bot.get("entry_confidence_score", bot.get("last_entry_confidence_score")),
        "expectancy_net_edge_pct": bot.get("expectancy_net_edge_pct"),
        "strategy_name": bot.get("strategy", bot.get("strategy_type", "balanced")),
        "regime_tag": bot.get("market_regime", "unknown"),
        "exit_forecast": None,
        "spread_estimate": bot.get("spread_estimate"),
        "slippage_estimate": bot.get("slippage_estimate"),
        "lifecycle_stage": bot.get("lifecycle_stage", "unknown"),
        "eligible_to_trade": bot.get("eligible_to_trade", False),
        "not_eligible_reasons": bot.get("not_eligible_reasons", []),
        "activity_state": bot.get("activity_state", "active_record"),
        "activity_reason_code": bot.get("activity_reason_code"),
        "runnable": bot.get("runnable", False),
    }

    if open_trade:
        side = open_trade.get("side", open_trade.get("type", "buy")).lower()
        entry_price = float(open_trade.get("entry_price", open_trade.get("price", 0)))
        current_price = float(open_trade.get("current_price", entry_price))
        tp = open_trade.get("take_profit", open_trade.get("target_price"))
        sl = open_trade.get("stop_loss", open_trade.get("stop_price"))
        trailing = open_trade.get("trailing_stop", open_trade.get("trailing_stop_price"))

        opened_at_raw = open_trade.get("opened_at", open_trade.get("timestamp", open_trade.get("created_at")))
        if isinstance(opened_at_raw, str):
            try:
                opened_at = datetime.fromisoformat(opened_at_raw.replace("Z", "+00:00"))
            except Exception:
                opened_at = now
        elif isinstance(opened_at_raw, datetime):
            opened_at = opened_at_raw if opened_at_raw.tzinfo else opened_at_raw.replace(tzinfo=timezone.utc)
        else:
            opened_at = now

        elapsed = (now - opened_at).total_seconds()
        remaining = max(0, max_hold - elapsed)

        # Unrealized PnL
        qty = float(open_trade.get("quantity", open_trade.get("qty", open_trade.get("amount", 0))))
        if side == "buy":
            unrealized = (current_price - entry_price) * qty
        else:
            unrealized = (entry_price - current_price) * qty

        # Determine next action
        if remaining <= 0:
            action = "FORCE_EXIT"
            code = "TIME_EXIT"
            text = "Max hold time exceeded – forcing exit"
        elif unrealized <= -(capital * RISK_THRESHOLD_PCT):
            action = "STOP_EXIT"
            code = "RISK_EXIT"
            text = "Unrealized loss exceeds risk threshold"
        elif tp and current_price >= float(tp) and side == "buy":
            action = "TARGET_EXIT"
            code = "TARGET_EXIT"
            text = "Price reached take-profit target"
        elif sl and current_price <= float(sl) and side == "buy":
            action = "STOP_EXIT"
            code = "STOP_EXIT"
            text = "Price hit stop-loss"
        elif trailing and side == "buy" and current_price <= float(trailing):
            action = "TRAIL_EXIT"
            code = "TRAIL_EXIT"
            text = "Trailing stop triggered"
        elif remaining < 600:
            action = "WARN_EXIT"
            code = "TIME_WARNING"
            text = f"Position closing in {int(remaining)}s"
        else:
            action = "HOLD"
            code = "POSITION_OPEN"
            text = f"Holding position – {int(remaining)}s remaining"

        entry.update({
            "side": side,
            "entry_price": entry_price,
            "current_price": current_price,
            "target_price": float(tp) if tp else None,
            "stop_price": float(sl) if sl else None,
            "trailing_stop_price": float(trailing) if trailing else None,
            "market_regime": open_trade.get("canonical_market_regime", entry["market_regime"]),
            "regime_confidence": float(open_trade.get("canonical_regime_confidence", entry["regime_confidence"])),
            "unrealized_pnl": round(unrealized, 2),
            "exposure_pct": round(abs(unrealized) / capital * 100, 2) if capital > 0 else 0.0,
            "position_opened_at": opened_at.isoformat(),
            "remaining_hold_seconds": round(remaining),
            "hold_timer_display": _format_hold_timer(elapsed),
            "next_action": action,
            "next_action_reason_code": code,
            "next_action_reason_text": text,
            "decision_reason_code": open_trade.get("trade_close_reason_code") or open_trade.get("reason_code") or code,
            "entry_reason_code": open_trade.get("entry_reason_code") or open_trade.get("reason_code"),
            "entry_confidence_score": open_trade.get("entry_confidence_score"),
            "expectancy_net_edge_pct": open_trade.get("expectancy_net_edge_pct"),
            "exit_forecast": _compute_exit_forecast(
                entry_price, current_price, float(tp) if tp else None,
                float(sl) if sl else None, remaining, unrealized
            ),
        })

    return entry


@router.get("/snapshot")
async def radar_snapshot(user_id: str = Depends(get_current_user)):
    """
    GET /api/radar/snapshot

    Returns per-bot radar data derived from ledger/trade truth.
    Shows each bot's current position on a live price line with
    entry → current → target → stop and time-remaining info.
    """
    now = datetime.now(timezone.utc)

    try:
        # Fetch only non-deleted active/paused bots for user
        bots_cursor = db.bots_collection.find(
            {
                "user_id": user_id,
                "status": {"$nin": ["deleted", "marked_for_deletion"]},
                "deleted": {"$ne": True},
                "is_deleted": {"$ne": True},
                "deleted_at": {"$exists": False},
            },
        )
        bots = await bots_cursor.to_list(length=200)
        bot_ids = [str(b.get("id") or b.get("_id") or "") for b in bots if b.get("id") or b.get("_id")]
        latest_decisions = await get_latest_bot_decisions(user_id, bot_ids)

        radar_entries: List[Dict] = []
        for raw_bot in bots:
            # Use the canonical string bot ID (not MongoDB _id) — trades are stored with bot.id
            bot_id = raw_bot.get("id") or str(raw_bot.get("_id", ""))
            decision_overlay = latest_decisions.get(str(bot_id), {})
            bot = normalize_bot_state({**raw_bot, **decision_overlay})

            # Find open trade for this bot
            open_trade = await db.trades_collection.find_one(
                {"bot_id": bot_id, "status": {"$in": ["open", "active", "pending"]}},
                sort=[("timestamp", -1)],
            )

            radar_entries.append(_compute_radar_entry(bot, open_trade, now))

        return {
            "timestamp": now.isoformat(),
            "total_bots": len(radar_entries),
            "bots_with_positions": await get_canonical_open_position_count(user_id),
            "radar": radar_entries,
        }
    except Exception as e:
        logger.error(f"Radar snapshot error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Radar snapshot failed: {e}")


@router.get("/timeseries")
async def radar_timeseries(
    user_id: str = Depends(get_current_user),
    bot_type: Optional[str] = Query(None, regex="^(normal|scalper)$"),
    hours: int = Query(24, ge=1, le=168),
):
    """Return hourly-bucketed timeseries for equity, PnL, bot counts, activity.

    Derived from ledger/trades truth. Supports normal/scalper split.
    """
    now = datetime.now(timezone.utc)
    since = now - timedelta(hours=hours)

    # Build bot filter
    bot_query: Dict = {"user_id": user_id, "deleted": {"$ne": True}}
    if bot_type:
        bot_query["bot_type"] = bot_type

    bots = await db.bots_collection.find(bot_query).to_list(500)
    bot_ids = [str(b.get("_id", b.get("bot_id", b.get("id", "")))) for b in bots]

    # Fetch trades in window
    trade_query: Dict = {"user_id": user_id, "timestamp": {"$gte": since.isoformat()}}
    if bot_type and bot_ids:
        trade_query["bot_id"] = {"$in": bot_ids}

    trades = await db.trades_collection.find(trade_query).sort("timestamp", 1).to_list(5000)

    # Bucket into hourly slots
    buckets: Dict = {}
    for h in range(hours + 1):
        t = since + timedelta(hours=h)
        key = t.strftime("%Y-%m-%dT%H:00:00Z")
        buckets[key] = {"timestamp": key, "pnl": 0.0, "trade_count": 0, "equity": 0.0}

    cumulative_pnl = 0.0
    base_equity = sum(float(b.get("current_capital", b.get("initial_capital", 0))) for b in bots)

    for trade in trades:
        ts = trade.get("timestamp", "")
        try:
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00")) if isinstance(ts, str) else ts
            key = dt.strftime("%Y-%m-%dT%H:00:00Z")
        except Exception:
            continue
        if key in buckets:
            pnl = float(trade.get("pnl", trade.get("profit", 0)) or 0)
            cumulative_pnl += pnl
            buckets[key]["pnl"] += pnl
            buckets[key]["trade_count"] += 1

    # Fill equity as base + cumulative
    running = 0.0
    for key in sorted(buckets.keys()):
        running += buckets[key]["pnl"]
        buckets[key]["equity"] = round(base_equity + running, 2)
        buckets[key]["pnl"] = round(buckets[key]["pnl"], 2)

    series = [buckets[k] for k in sorted(buckets.keys())]

    return {
        "series": series,
        "bot_count": len(bots),
        "bot_type": bot_type or "all",
        "hours": hours,
        "timestamp": now.isoformat(),
    }
