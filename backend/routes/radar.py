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

from fastapi import APIRouter, Depends, HTTPException
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional
import logging

from auth import get_current_user
import database as db
from utils.bot_state import normalize_bot_state

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/radar", tags=["Radar"])

# Default max hold times by risk mode (seconds)
DEFAULT_MAX_HOLD = {
    "safe": 6 * 3600,        # 6 hours
    "balanced": 3 * 3600,    # 3 hours
    "aggressive": 90 * 60,   # 90 minutes
}

# Default profit targets (fraction of capital)
DEFAULT_DAILY_PROFIT_TARGET = 0.015   # 1.5% daily
DEFAULT_TRADE_PROFIT_TARGET = 0.005   # 0.5% per trade


def _compute_radar_entry(bot: Dict, open_trade: Optional[Dict], now: datetime) -> Dict:
    """Build a single radar entry from bot + its current open trade."""
    bot_id = str(bot.get("_id", bot.get("bot_id", "")))
    risk_mode = (bot.get("risk_mode") or bot.get("risk_profile") or "balanced").lower()
    max_hold = DEFAULT_MAX_HOLD.get(risk_mode, DEFAULT_MAX_HOLD["balanced"])
    capital = float(bot.get("current_capital", bot.get("initial_capital", 0)))
    daily_target = round(capital * DEFAULT_DAILY_PROFIT_TARGET, 2)
    trade_target = round(capital * DEFAULT_TRADE_PROFIT_TARGET, 2)

    entry = {
        "bot_id": bot_id,
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
        "daily_profit_target": daily_target,
        "trade_profit_target": trade_target,
        "position_opened_at": None,
        "max_hold_seconds": max_hold,
        "remaining_hold_seconds": None,
        "next_action": "WAIT",
        "next_action_reason_code": "NO_POSITION",
        "next_action_reason_text": "No open position – waiting for entry signal",
        "market_regime": bot.get("market_regime", "unknown"),
        "spread_estimate": bot.get("spread_estimate"),
        "slippage_estimate": bot.get("slippage_estimate"),
        "lifecycle_stage": bot.get("lifecycle_stage", "unknown"),
        "eligible_to_trade": bot.get("eligible_to_trade", False),
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
        elif unrealized <= -(capital * 0.03):
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
            "unrealized_pnl": round(unrealized, 2),
            "position_opened_at": opened_at.isoformat(),
            "remaining_hold_seconds": round(remaining),
            "next_action": action,
            "next_action_reason_code": code,
            "next_action_reason_text": text,
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
        # Fetch all bots for user
        bots_cursor = db.bots_collection.find(
            {"user_id": user_id, "deleted": {"$ne": True}},
        )
        bots = await bots_cursor.to_list(length=200)

        radar_entries: List[Dict] = []
        for raw_bot in bots:
            bot = normalize_bot_state(raw_bot)
            bot_id = str(raw_bot.get("_id", ""))

            # Find open trade for this bot
            open_trade = await db.trades_collection.find_one(
                {"bot_id": bot_id, "status": {"$in": ["open", "active", "pending"]}},
                sort=[("timestamp", -1)],
            )

            radar_entries.append(_compute_radar_entry(bot, open_trade, now))

        return {
            "timestamp": now.isoformat(),
            "total_bots": len(radar_entries),
            "bots_with_positions": sum(1 for e in radar_entries if e["side"] is not None),
            "radar": radar_entries,
        }
    except Exception as e:
        logger.error(f"Radar snapshot error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Radar snapshot failed: {e}")
