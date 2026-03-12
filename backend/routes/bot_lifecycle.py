"""
Bot Lifecycle Management Router
Handles pause, resume, cooldown periods, and bot lifecycle operations
"""

from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import JSONResponse
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, TypedDict
import logging
import os

from auth import get_current_user, get_optional_user
import database as db
from websocket_manager import manager
from realtime_events import rt_events
from services.bot_quarantine import quarantine_service
from services.bot_runtime_state import bot_runtime_state
from services.risk_lock_service import risk_lock_service
from services.canonical_metrics import get_canonical_metrics_snapshot
from services.canonical import get_canonical_bot_activity, get_latest_bot_decisions
from engines.audit_logger import audit_logger
from rules.bot_rules import SUPPORTED_EXCHANGES
from utils.datetime_helpers import remaining_seconds
from utils.bot_state import normalize_bot_state
# Canonical trading-gate flags — use config module (supports all env-var aliases)
from config import PAPER_TRADING as _cfg_paper_trading, LIVE_TRADING as _cfg_live_trading
from services.truth_normalizer import normalize_bot_trade_truth
from services.fx_normalizer import get_quote_currency, get_fx_rate

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/bots", tags=["Bot Lifecycle"])
bots_collection = db.bots_collection
ALL_EXCHANGES = list(SUPPORTED_EXCHANGES)


def _paper_trading_enabled() -> bool:
    """Return True when paper trading is enabled (canonical config check)."""
    return _cfg_paper_trading or os.getenv('PAPER_TRADING') == '1' or os.getenv('ENABLE_PAPER_TRADING', 'true').lower() == 'true'


def _live_trading_enabled() -> bool:
    """Return True when live trading is enabled (canonical config check)."""
    return _cfg_live_trading or os.getenv('LIVE_TRADING') == '1' or os.getenv('ENABLE_LIVE_TRADING', 'false').lower() == 'true'

class BlockDetail(TypedDict, total=False):
    code: str
    message: str
    next_action: str
    release_at: str
    remaining_seconds: int

def _build_block_detail(
    code: str,
    message: str,
    next_action: Optional[str] = None,
    release_at: Optional[str] = None,
    remaining_seconds: Optional[int] = None,
) -> BlockDetail:
    """Build structured error details for bot action blockers.

    Args:
        code: Machine-readable reason code.
        message: Human-readable reason message.
        next_action: Suggested next action for the user.
        release_at: Optional ISO timestamp when the block clears.
        remaining_seconds: Optional countdown in seconds.
    """
    detail = {"code": code, "message": message}
    if next_action:
        detail["next_action"] = next_action
    if release_at:
        detail["release_at"] = release_at
    if remaining_seconds is not None:
        detail["remaining_seconds"] = remaining_seconds
    return detail


def _action_payload(
    action: str,
    success: bool,
    bot: Optional[Dict],
    message: str,
    pause_reason: Optional[str] = None,
    lock_reason: Optional[str] = None,
) -> Dict:
    return {
        "success": success,
        "bot": bot,
        "message": message,
        "pause_reason": pause_reason,
        "lock_reason": lock_reason,
        "action": action,
    }


def _bots_status_payload(
    bots: Optional[list] = None,
    exchange_counts: Optional[Dict[str, int]] = None,
    all_exchanges: Optional[list] = None,
    activity: Optional[Dict] = None,
    success: bool = True,
    error: Optional[str] = None,
) -> Dict:
    """Build a safe bots status response payload (platforms kept for backward compatibility)."""
    bots = [] if bots is None else bots
    exchange_counts = {} if exchange_counts is None else exchange_counts
    all_exchanges = [] if all_exchanges is None else all_exchanges
    activity = activity or {}
    active_from_activity = activity.get("active_bot_records", activity.get("active"))
    if active_from_activity is None:
        active_from_activity = sum(
            1
            for bot in bots
            if bot.get("state") == "active" or bot.get("status") == "active"
        )
    active_bots = int(active_from_activity or 0)
    runnable_bots = int(activity.get("runnable_active_bots", activity.get("runnable", active_bots)) or 0)
    return {
        "success": success,
        "active_bots": active_bots,
        "runnable_bots": runnable_bots,
        "bots": bots,
        "platforms": exchange_counts,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "total": len(bots),
        "activity": activity,
        "exchange_counts": exchange_counts,
        "all_exchanges": all_exchanges,
        **({"error": error} if error else {}),
    }


def _blocked_response(action: str, bot: Optional[Dict], blocker: Dict) -> JSONResponse:
    return JSONResponse(
        status_code=409,
        content=_action_payload(
            action=action,
            success=False,
            bot=bot,
            message=blocker.get("message", "Action blocked"),
            pause_reason=blocker.get("message"),
            lock_reason=blocker.get("code"),
        ),
    )


async def _check_bot_blockers(bot: Dict, user_id: str) -> Optional[Dict]:
    # Use the canonical risk lock service to check daily loss lock status.
    # is_locked_today() already handles stale-lock detection (returns False if
    # day_key != today UTC). If the lock is stale, the background midnight job
    # will clear it; the inline guard in the service returns False immediately so
    # the bot is not blocked.
    try:
        is_locked, lock_reason = await risk_lock_service.is_locked_today(user_id)
    except Exception as _rls_err:
        logger.warning(f"[BotBlockers] risk_lock_service.is_locked_today failed: {_rls_err}")
        # Fallback: read the field directly from the DB so we never silently allow a locked user
        user = await db.users_collection.find_one({"id": user_id}, {"_id": 0, "daily_loss_lock_active": 1, "daily_loss_day_key": 1, "daily_loss_locked_reason": 1})
        from datetime import datetime, timezone
        today_key = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        raw_active = bool(user.get("daily_loss_lock_active", False)) if user else False
        raw_day_key = (user or {}).get("daily_loss_day_key", "")
        is_locked = raw_active and raw_day_key == today_key
        lock_reason = (user or {}).get("daily_loss_locked_reason", "Daily loss lock is active") if is_locked else None

    if is_locked:
        return _build_block_detail(
            "daily_loss_lock",
            lock_reason or "Daily loss lock is active",
            "Reset the daily loss lock or contact admin",
        )

    modes = await db.system_modes_collection.find_one({"user_id": user_id}, {"_id": 0})
    if modes and modes.get("emergencyStop", False):
        return _build_block_detail(
            "emergency_stop",
            modes.get("emergency_stop_reason", "Emergency stop is active"),
            "Disable emergency stop before resuming trading",
        )

    if bot.get("status") == "quarantined" or bot.get("retraining_until"):
        release_at = bot.get("retraining_until") or bot.get("quarantine_until")
        seconds_remaining = remaining_seconds(release_at)
        return _build_block_detail(
            "quarantine",
            bot.get("quarantine_reason", "Bot is quarantined for retraining"),
            "Wait for retraining to complete",
            release_at=release_at,
            remaining_seconds=seconds_remaining,
        )

    if bot.get("status") in ["training", "training_failed"] or bot.get("training_in_progress"):
        return _build_block_detail(
            "training",
            bot.get("training_failed_reason", "Training in progress"),
            "Complete training before resuming trading",
        )

    if bot.get("paused_by_bodyguard"):
        try:
            from services.bodyguard_service import bodyguard_service

            bodyguard_status = await bodyguard_service.get_bot_drawdown_status(bot.get("id"))
            if bodyguard_status and not bodyguard_status.get("can_resume", False):
                return _build_block_detail(
                    "drawdown_lock",
                    bodyguard_status.get("pause_reason", "Paused by drawdown protection"),
                    "Wait for drawdown recovery or reset bodyguard lock",
                )
        except Exception as e:
            logger.warning(f"Bodyguard status check failed: {e}")

    return None


@router.get("/status")
async def get_bots_status(
    user_id: Optional[str] = Depends(get_optional_user),
    meta: Optional[int] = 0,
):
    """Get bot status list with states for bot management
    
    Returns all bots with detailed status including training states
    Unauthenticated requests receive empty defaults.
    
    Args:
        user_id: Current user ID (from auth)
        
    Returns:
        List of bots with id, exchange, state, paused_reason, etc.
    """
    all_exchanges = ALL_EXCHANGES
    collection = db.bots_collection
    if collection is None:
        return JSONResponse(
            status_code=503,
            content={"detail": "Bots collection unavailable"},
        )
    exchange_counts = {exchange: 0 for exchange in all_exchanges}
    if not user_id:
        if meta:
            return {"exchange_counts": exchange_counts, "all_exchanges": all_exchanges}
        return _bots_status_payload([], exchange_counts, all_exchanges)

    try:
        activity = await get_canonical_bot_activity(user_id)
        bots = await collection.find(
            {
                "user_id": user_id,
                # Status is the canonical deletion flag; legacy deleted/is_deleted/deleted_at remain until cleanup.
                "status": {"$nin": ["deleted", "marked_for_deletion"]},
                "deleted": {"$ne": True},
                "is_deleted": {"$ne": True},
                "deleted_at": {"$exists": False},
            },
            {"_id": 0},
        ).to_list(1000)
        if not bots:
            if meta:
                return {"exchange_counts": exchange_counts, "all_exchanges": all_exchanges}
            return _bots_status_payload([], exchange_counts, all_exchanges, activity=activity)

        runtime_states = {
            state.get("bot_id"): state
            for state in await bot_runtime_state.list_states(user_id)
        }
        decision_map = await get_latest_bot_decisions(user_id, [str(bot.get("id")) for bot in bots if bot.get("id")])
        canonical_snapshot = await get_canonical_metrics_snapshot(user_id, bots=bots)
        canonical_by_bot = canonical_snapshot.get("by_bot_id", {})

        # Bulk-fetch open trades for all bots in one query so truth_normalizer can
        # resolve symbol/regime/confidence from trade canonical fields without an
        # N+1 DB round-trip per bot.
        bot_ids_all = [str(bot.get("id")) for bot in bots if bot.get("id")]
        try:
            _raw_open_trades = await db.trades_collection.find(
                {"bot_id": {"$in": bot_ids_all}, "status": {"$in": ["open", "active", "pending"]}},
                {"_id": 0},
            ).sort("timestamp", -1).to_list(max(len(bot_ids_all), 100))
        except Exception:
            _raw_open_trades = []
        open_trade_by_bot: dict = {}
        for _t in _raw_open_trades:
            _bid = str(_t.get("bot_id", ""))
            if _bid and _bid not in open_trade_by_bot:
                open_trade_by_bot[_bid] = _t
        
        # Enrich each bot with detailed state
        enriched_bots = []
        for bot in bots:
            status = bot.get('status', 'unknown')
            runtime_state = runtime_states.get(bot.get("id"))
            if runtime_state and runtime_state.get("state") in {"active", "paused", "stopped"}:
                status = runtime_state.get("state")
            decision_overlay = decision_map.get(str(bot.get("id")), {})
            decision_fallback = {
                key: value
                for key, value in decision_overlay.items()
                if key not in bot or bot.get(key) in (None, "", [])
            }
            normalized_bot = normalize_bot_state({**bot, **decision_fallback, "status": status})

            # Merge open-trade canonical truth so symbol/regime/confidence
            # are consistent with what radar and trades endpoints show.
            _open_trade_for_bot = open_trade_by_bot.get(str(bot.get("id")), None)
            _truth = normalize_bot_trade_truth(normalized_bot, _open_trade_for_bot)
            
            # Map status to standard states
            if status == 'active':
                state = 'active'
            elif status == 'paused':
                # Check if ready to activate (paused_ready)
                if bot.get('training_complete') and bot.get('paused_by_user'):
                    state = 'paused_ready'
                else:
                    state = 'paused'
            elif status == 'stopped':
                state = 'stopped'
            elif status == 'training' or bot.get('training_in_progress'):
                state = 'training'
            elif status == 'training_failed' or bot.get('training_failed'):
                state = 'training_failed'
            else:
                state = status

            pause_reason = bot.get('pause_reason') or bot.get('paused_reason')
            if runtime_state and runtime_state.get("reason"):
                pause_reason = runtime_state.get("reason")
            pause_reason_code = None
            pause_reason_message = None
            pause_next_action = None
            quarantine_release_at = None
            quarantine_remaining_seconds = None

            if status == 'quarantined' or bot.get('retraining_until'):
                pause_reason_code = 'quarantine'
                pause_reason_message = bot.get('quarantine_reason') or pause_reason or 'Bot is in quarantine'
                pause_next_action = 'Wait for retraining to complete'
                quarantine_release_at = bot.get('retraining_until') or bot.get('quarantine_until')
                quarantine_remaining_seconds = remaining_seconds(quarantine_release_at)
            elif status in ['training', 'training_failed'] or bot.get('training_in_progress'):
                pause_reason_code = 'training'
                pause_reason_message = bot.get('training_failed_reason') or 'Training in progress'
                pause_next_action = 'Complete training before resuming'
            elif normalized_bot.get('paused_by_bodyguard'):
                pause_reason_code = 'bodyguard_lock'
                pause_reason_message = pause_reason or 'Paused by bodyguard drawdown protection'
                pause_next_action = 'Wait for drawdown recovery or reset bodyguard lock'
            elif normalized_bot.get('paused_by_system'):
                pause_reason_code = 'system_pause'
                pause_reason_message = pause_reason or 'Paused by system'
                pause_next_action = 'Review system status and resume when cleared'
            elif normalized_bot.get('paused_by_user'):
                pause_reason_code = 'manual_pause'
                pause_reason_message = pause_reason or 'Paused by user'
                pause_next_action = 'Resume bot when ready'
            elif status == 'paused':
                pause_reason_code = 'paused'
                pause_reason_message = pause_reason or 'Bot paused'
                pause_next_action = 'Resume bot'
            
            canonical = canonical_by_bot.get(str(bot.get("id")), {})
            base_initial_capital = float(canonical.get("capital_initial", bot.get("initial_capital", bot.get("starting_capital", 0))) or 0)
            base_current_capital = float(canonical.get("capital_current", bot.get("current_capital", bot.get("allocated_capital", base_initial_capital))) or 0)
            base_open_position = float(canonical.get("open_position_value", bot.get("open_position_value", 0)) or 0)
            available_capital = float(canonical.get("capital_available", max(0.0, base_current_capital - base_open_position)))
            total_trades = int(canonical.get("trade_count", bot.get("trades_count", 0)) or 0)
            win_count = int(canonical.get("winning_trades", bot.get("win_count", 0)) or 0)
            loss_count = int(canonical.get("losing_trades", bot.get("loss_count", 0)) or 0)
            realized_pnl = float(canonical.get("profit_realized", bot.get("total_profit", 0)) or 0)
            win_rate = float(canonical.get("win_rate_pct", bot.get("win_rate", 0)) or 0)
            roi = float(canonical.get("roi_pct", 0) or 0)

            # ── Canonical capital truth model ──
            # Derive canonical_base_capital_zar for display so the user can always see
            # their original R-denominated economic base regardless of exchange.
            # Rules:
            #   1. If the bot stored canonical_base_capital_zar at creation → use it directly.
            #   2. For ZAR bots (Luno) with no stored canonical field → current_capital IS the ZAR base.
            #   3. For USDT bots without the canonical field (old bots) → derive from stored capital×fx_rate.
            _bot_quote_currency = get_quote_currency(
                bot.get('exchange', ''),
                bot.get('pair') or bot.get('symbol', ''),
            )
            _fx_rate_canonical, _ = get_fx_rate(_bot_quote_currency, "ZAR")
            # Prefer the explicitly stored canonical field (set at creation for new bots)
            _stored_base_zar = bot.get("canonical_base_capital_zar")
            if _stored_base_zar and float(_stored_base_zar or 0) > 0:
                _canonical_base_zar = round(float(_stored_base_zar), 2)
            else:
                # Compute on-the-fly: for ZAR bots rate is 1.0, for USDT bots multiply
                _canonical_base_zar = round(base_initial_capital * _fx_rate_canonical, 2)
            # total_equity_quote: current equity in native quote currency
            _total_equity_quote = round(base_current_capital + base_open_position, 2)
            # total_equity_display: ZAR equivalent of current equity (for display only)
            _total_equity_display = round(_total_equity_quote * _fx_rate_canonical, 2)
            # profit_display: realized P&L in ZAR
            _profit_display = round(realized_pnl * _fx_rate_canonical, 2)
            # fx_rate_at_creation stored on bot (may differ from current rate)
            _fx_rate_at_creation = float(bot.get("fx_rate_at_creation") or _fx_rate_canonical)

            enriched_bot = {
                "id": bot.get('id'),
                "name": bot.get('name'),
                "exchange": bot.get('exchange', 'unknown'),
                "state": state,
                "status": status,  # Keep original for compatibility
                # --- Bot classification (critical for fleet tab routing) ---
                "bot_type": bot.get('bot_type', 'normal'),
                "profit_routing": bot.get('profit_routing', 'RETURN_TO_MAIN'),
                "strategy_preset": bot.get('strategy_preset'),
                "user_id": bot.get('user_id'),
                "paused_reason": pause_reason,  # Canonical field (support legacy)
                "paused_reason_code": pause_reason_code,
                "paused_reason_message": pause_reason_message,
                "paused_next_action": pause_next_action,
                "paused_at": bot.get('paused_at') or bot.get('quarantined_at'),
                "paused_by_user": bot.get('paused_by_user', False),
                "paused_by_system": bot.get('paused_by_system', False),
                "runtime_state": runtime_state,
                "quarantine_reason": bot.get('quarantine_reason'),
                "quarantine_until": bot.get('quarantine_until'),
                "quarantine_release_at": quarantine_release_at,
                "quarantine_remaining_seconds": quarantine_remaining_seconds,
                "training_state": bot.get('training_state'),
                "trading_mode": bot.get('trading_mode', 'paper'),
                "risk_mode": bot.get('risk_mode', 'balanced'),
                "initial_capital": round(base_initial_capital, 2),
                "current_capital": round(base_current_capital, 2),
                "allocated_capital": round(base_current_capital, 2),
                "available_capital": round(available_capital, 2),
                "open_position_value": round(base_open_position, 2),
                # ── Canonical capital truth fields (problem statement §PHASE1) ──
                # canonical_base_capital_zar: the original ZAR economic base the user
                #   chose when creating this bot. Always R-denominated regardless of exchange.
                # quote_capital / quote_currency: trading capital in native quote currency.
                # total_equity_quote: current equity in quote currency.
                # total_equity_display: ZAR-equivalent of current equity (display only).
                # profit_display: realized P&L in ZAR (display only).
                # fx_rate_used: rate applied for ZAR↔quote conversions.
                "canonical_base_capital_zar": _canonical_base_zar,
                "quote_capital": round(base_initial_capital, 2),
                "quote_currency": _bot_quote_currency,
                "display_currency": "ZAR",
                "fx_rate_used": round(_fx_rate_canonical, 4),
                "fx_rate_at_creation": round(_fx_rate_at_creation, 4),
                "total_equity_quote": _total_equity_quote,
                "total_equity_display": _total_equity_display,
                "profit_quote": round(realized_pnl, 2),
                "profit_display": _profit_display,
                "total_profit": round(realized_pnl, 2),
                "profit": round(realized_pnl, 2),
                "trades_count": total_trades,
                "total_trades": total_trades,
                "win_count": win_count,
                "loss_count": loss_count,
                "win_rate": round(win_rate, 2),
                "roi": round(roi, 2),
                "capital": {
                    "initial": round(base_initial_capital, 2),
                    "current": round(base_current_capital, 2),
                    "allocated": round(base_current_capital, 2),
                    "available": round(available_capital, 2),
                    "open_position_value": round(base_open_position, 2),
                },
                "capital_summary": canonical.get("capital_summary", {
                    "canonical_base_capital_zar": _canonical_base_zar,
                    "initial_capital": round(base_initial_capital, 2),
                    "quote_currency": _bot_quote_currency,
                    "allocated_capital": round(base_current_capital, 2),
                    "available_capital": round(available_capital, 2),
                    "open_position_value": round(base_open_position, 2),
                    "total_equity_quote": _total_equity_quote,
                    "total_equity_display": _total_equity_display,
                    "realized_profit": round(realized_pnl, 2),
                    "profit_display": _profit_display,
                    "unrealized_profit": 0.0,
                    "fx_rate_used": round(_fx_rate_canonical, 4),
                    "semantics": {
                        "canonical_base_capital_zar": "Original ZAR economic base the user entered at creation.",
                        "initial_capital": "Starting capital in native quote currency (ZAR for Luno, USDT for USDT exchanges).",
                        "quote_currency": "Native trading currency for this bot.",
                        "allocated_capital": "Capital currently assigned to this bot for trading (in quote currency).",
                        "available_capital": "Uncommitted capital available for new entries (in quote currency).",
                        "open_position_value": "Current value of capital in open positions (in quote currency).",
                        "total_equity_quote": "Total equity in quote currency (available + open).",
                        "total_equity_display": "Total equity converted to ZAR for display (never inflated by currency confusion).",
                        "realized_profit": "Closed-trade profit/loss in quote currency.",
                        "profit_display": "Closed-trade profit/loss in ZAR (display).",
                        "fx_rate_used": "Exchange rate used to convert quote currency to ZAR display.",
                    },
                }),
                "performance": {
                    "profit_realized": round(realized_pnl, 2),
                    "roi_pct": round(roi, 2),
                    "trade_count": total_trades,
                    "winning_trades": win_count,
                    "losing_trades": loss_count,
                    "win_rate_pct": round(win_rate, 2),
                },
                "last_trade": bot.get('last_trade'),
                "training_complete": bot.get('training_complete', False),
                "training_failed_reason": bot.get('training_failed_reason'),
                "training_in_progress": bot.get('training_in_progress', False),
                "paper_start_date": bot.get('paper_start_date'),
                "active": status == 'active',
                "paused": status == 'paused',
                "in_quarantine": status == 'quarantined',
                "in_training": status in ['training', 'training_failed'] or bot.get('training_in_progress'),
                "eligible_to_trade": normalized_bot.get("eligible_to_trade", False),
                "not_eligible_reasons": normalized_bot.get("not_eligible_reasons", []),
                "activity_state": normalized_bot.get("activity_state", "active_record"),
                "runnable": normalized_bot.get("runnable", False),
                "activity_reason_code": normalized_bot.get("activity_reason_code"),
                "decision_reason_code": _truth.get("decision_reason_code") or normalized_bot.get("decision_reason_code", normalized_bot.get("last_decision_reason_code")),
                "entry_reason_code": _truth.get("entry_reason_code") or normalized_bot.get("entry_reason_code", normalized_bot.get("last_entry_reason_code")),
                "entry_confidence_score": _truth.get("entry_confidence_score") or normalized_bot.get("entry_confidence_score", normalized_bot.get("last_entry_confidence_score")),
                "expectancy_net_edge_pct": _truth.get("expectancy_net_edge_pct") or normalized_bot.get("expectancy_net_edge_pct"),
                "market_regime": _truth.get("market_regime") or normalized_bot.get("market_regime", normalized_bot.get("canonical_market_regime", "unknown")),
                "regime_confidence": _truth.get("regime_confidence") or normalized_bot.get("canonical_regime_confidence", normalized_bot.get("regime_confidence", normalized_bot.get("confidence_score", 0))),
                # symbol from truth (resolves trade.pair first, falls back to bot.pair)
                "symbol": _truth.get("symbol") or bot.get("pair") or bot.get("symbol"),
                "has_open_position": _truth.get("has_open_position", False),
                "created_at": bot.get('created_at'),
                "started_at": bot.get('started_at'),
                "stopped_at": bot.get('stopped_at'),
                # ── Canonical display currency contract ──
                "quote_currency": get_quote_currency(
                    bot.get('exchange', ''),
                    bot.get('pair') or bot.get('symbol', ''),
                ),
                "display_currency": "ZAR",
            }
            enriched_bots.append(enriched_bot)
        
        # Count by exchange to ensure all 7 are represented
        exchange_counts = {exchange: 0 for exchange in all_exchanges}
        for bot in enriched_bots:
            exchange = bot.get('exchange')
            if exchange in exchange_counts:
                exchange_counts[exchange] += 1
        if meta:
            return {"exchange_counts": exchange_counts, "all_exchanges": all_exchanges}
        return _bots_status_payload(enriched_bots, exchange_counts, all_exchanges, activity=activity)
        
    except Exception:
        logger.exception("Get bots status error for user %s", user_id)
        if meta:
            return {"exchange_counts": exchange_counts, "all_exchanges": all_exchanges}
        return _bots_status_payload(
            [],
            exchange_counts,
            all_exchanges,
            activity={"total_bot_records": 0, "active_bot_records": 0, "runnable_active_bots": 0, "paused_bots": 0, "bots_with_open_positions": 0, "blocked_bots": 0, "non_runnable_reasons": {}},
            success=False,
            error="Unable to load bot status",
        )


@router.post("/{bot_id}/start")
async def start_bot(bot_id: str, user_id: str = Depends(get_current_user)):
    """Start a bot's trading activity
    
    Args:
        bot_id: Bot ID to start
        user_id: Current user ID (from auth)
        
    Returns:
        Updated bot status
    """
    try:
        # Verify bot belongs to user
        bot = await db.bots_collection.find_one({"id": bot_id, "user_id": user_id}, {"_id": 0})
        if not bot:
            raise HTTPException(status_code=404, detail="Bot not found")
        
        # Check if already active
        if bot.get('status') == 'active':
            return _action_payload(
                action="start",
                success=False,
                bot=bot,
                message=f"Bot '{bot['name']}' is already active",
                pause_reason=bot.get("pause_reason")
            )

        blocker = await _check_bot_blockers(bot, user_id)
        if blocker:
            return _blocked_response("start", bot, blocker)
        
        # PREFLIGHT VALIDATION: Check requirements before starting bot
        trading_mode = bot.get('trading_mode', 'paper')
        
        # 1. Check wallet balance is available
        current_capital = bot.get('current_capital', 0)
        initial_capital = bot.get('initial_capital', 0)
        if current_capital <= 0 and initial_capital <= 0:
            return _blocked_response(
                "start",
                bot,
                _build_block_detail(
                    "insufficient_funds",
                    f"Cannot start bot '{bot['name']}': No wallet balance available.",
                    "Allocate capital to this bot before starting",
                ),
            )

        modes = await db.system_modes_collection.find_one({"user_id": user_id}, {"_id": 0})
        if trading_mode == 'paper' and modes and not modes.get('paperTrading', True):
            return _blocked_response(
                "start",
                bot,
                _build_block_detail(
                    "system_mode_disabled",
                    "Paper trading is disabled in system mode",
                    "Enable paper trading in System Mode settings",
                ),
            )
        if trading_mode == 'live' and modes and not modes.get('liveTrading', False):
            return _blocked_response(
                "start",
                bot,
                _build_block_detail(
                    "system_mode_disabled",
                    "Live trading is disabled in system mode",
                    "Enable live trading in System Mode settings",
                ),
            )
        
        # 2. Check trading mode is enabled (Paper or Live)
        # Validate that the bot's trading mode (paper/live) is enabled in environment config
        # This prevents starting bots in modes that are disabled system-wide
        paper_trading_enabled = _paper_trading_enabled()
        live_trading_enabled = _live_trading_enabled()
        
        if trading_mode == 'paper' and not paper_trading_enabled:
            return _blocked_response(
                "start",
                bot,
                _build_block_detail(
                    "system_mode_disabled",
                    f"Cannot start bot '{bot['name']}': Paper trading is disabled.",
                    "Set PAPER_TRADING=1 in environment",
                ),
            )
        elif trading_mode == 'live' and not live_trading_enabled:
            return _blocked_response(
                "start",
                bot,
                _build_block_detail(
                    "system_mode_disabled",
                    f"Cannot start bot '{bot['name']}': Live trading is disabled.",
                    "Set LIVE_TRADING=1 in environment",
                ),
            )
        elif not paper_trading_enabled and not live_trading_enabled:
            return _blocked_response(
                "start",
                bot,
                _build_block_detail(
                    "system_mode_disabled",
                    "Cannot start bot: Both paper and live trading are disabled.",
                    "Enable PAPER_TRADING=1 or LIVE_TRADING=1 in environment",
                ),
            )

        if trading_mode == "live":
            api_key = await db.api_keys_collection.find_one(
                {"user_id": user_id, "provider": bot.get("exchange", "")},
                {"_id": 0}
            )
            if not api_key:
                return _blocked_response(
                    "start",
                    bot,
                    _build_block_detail(
                        "key_missing",
                        f"Cannot start bot '{bot['name']}': API keys missing for {bot.get('exchange')}",
                        "Add and test API keys before starting live trading",
                    ),
                )
        
        # 3. Check ledger collection is accessible
        try:
            # Verify ledger collection exists and is accessible
            await db.ledger_collection.find_one({}, {"_id": 1})
        except Exception as e:
            logger.exception("Ledger collection check failed")
            raise HTTPException(
                status_code=500,
                detail=f"Cannot start bot '{bot['name']}': Ledger collection is not accessible. Please contact admin."
            )
        
        # Start the bot
        started_at = datetime.now(timezone.utc).isoformat()
        
        runtime_before = await bot_runtime_state.ensure_state(bot)
        await db.bots_collection.update_one(
            {"id": bot_id},
            {
                "$set": {
                    "status": "active",
                    "started_at": started_at
                },
                "$unset": {
                    "stopped_at": "",
                    "paused_at": "",
                    "pause_reason": "",
                    "paused_by_user": "",
                    "paused_by_system": "",
                    "stop_reason": ""
                }
            }
        )

        await bot_runtime_state.set_state(
            bot_id=bot_id,
            user_id=user_id,
            state="active",
            reason=None,
            source="api"
        )
        
        # Get updated bot
        updated_bot = await db.bots_collection.find_one({"id": bot_id}, {"_id": 0})
        
        # Send real-time notifications
        await rt_events.bot_resumed(user_id, updated_bot)
        await rt_events.bot_state_changed(
            user_id,
            bot_id,
            (runtime_before or {}).get("state", bot.get("status", "unknown")),
            "active",
            None
        )
        await audit_logger.log_bot_action("started", user_id, bot_id, bot.get("name", "bot"))
        
        # Also broadcast overview and platform stats updates
        from services.realtime_service import realtime_service
        await realtime_service.broadcast_overview_update(user_id, f"Bot started: {bot['name']}")
        await realtime_service.broadcast_platform_stats_update(user_id, bot.get('exchange'))
        
        logger.info(f"✅ Bot {bot['name']} started by user {user_id[:8]}")
        
        return _action_payload(
            action="start",
            success=True,
            bot=updated_bot,
            message=f"Bot '{bot['name']}' started successfully",
            pause_reason=updated_bot.get("pause_reason")
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Start bot error")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{bot_id}/stop")
async def stop_bot(bot_id: str, data: Optional[Dict] = None, user_id: str = Depends(get_current_user)):
    """Stop a bot's trading activity permanently
    
    Args:
        bot_id: Bot ID to stop
        data: Optional data with reason for stop
        user_id: Current user ID (from auth)
        
    Returns:
        Updated bot status
    """
    try:
        # Verify bot belongs to user
        bot = await db.bots_collection.find_one({"id": bot_id, "user_id": user_id}, {"_id": 0})
        if not bot:
            raise HTTPException(status_code=404, detail="Bot not found")
        
        # Check if already stopped
        if bot.get('status') == 'stopped':
            return _action_payload(
                action="stop",
                success=False,
                bot=bot,
                message=f"Bot '{bot['name']}' is already stopped",
                pause_reason=bot.get("pause_reason")
            )
        
        # Stop the bot
        if data is None:
            data = {}
        reason = data.get('reason', 'Manual stop by user')
        stopped_at = datetime.now(timezone.utc).isoformat()
        
        runtime_before = await bot_runtime_state.ensure_state(bot)
        await db.bots_collection.update_one(
            {"id": bot_id},
            {
                "$set": {
                    "status": "stopped",
                    "stopped_at": stopped_at,
                    "stop_reason": reason
                }
            }
        )

        await bot_runtime_state.set_state(
            bot_id=bot_id,
            user_id=user_id,
            state="stopped",
            reason=reason,
            source="api"
        )
        
        # Get updated bot
        updated_bot = await db.bots_collection.find_one({"id": bot_id}, {"_id": 0})
        
        # Send real-time notifications
        await manager.send_message(user_id, {
            "type": "bot_stopped",
            "bot": updated_bot,
            "message": f"⏹️ Bot '{bot['name']}' stopped"
        })
        await rt_events.bot_state_changed(
            user_id,
            bot_id,
            (runtime_before or {}).get("state", bot.get("status", "unknown")),
            "stopped",
            reason
        )
        await audit_logger.log_bot_action("stopped", user_id, bot_id, bot.get("name", "bot"), {"reason": reason})
        
        # Also broadcast overview and platform stats updates
        from services.realtime_service import realtime_service
        await realtime_service.broadcast_overview_update(user_id, f"Bot stopped: {bot['name']}")
        await realtime_service.broadcast_platform_stats_update(user_id, bot.get('exchange'))
        
        logger.info(f"✅ Bot {bot['name']} stopped by user {user_id[:8]}")
        
        return _action_payload(
            action="stop",
            success=True,
            bot=updated_bot,
            message=f"Bot '{bot['name']}' stopped successfully",
            pause_reason=updated_bot.get("pause_reason")
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Stop bot error")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{bot_id}/pause")
@router.put("/{bot_id}/pause")
async def pause_bot(bot_id: str, data: Optional[Dict] = None, user_id: str = Depends(get_current_user)):
    """Pause a bot's trading activity
    
    Accepts both POST and PUT methods for compatibility with frontend
    
    Args:
        bot_id: Bot ID to pause
        data: Optional data with reason for pause
        user_id: Current user ID (from auth)
        
    Returns:
        Updated bot status
    """
    try:
        # Verify bot belongs to user
        bot = await db.bots_collection.find_one({"id": bot_id, "user_id": user_id}, {"_id": 0})
        if not bot:
            raise HTTPException(status_code=404, detail="Bot not found")
        
        # Check if already paused
        if bot.get('status') == 'paused':
            return _action_payload(
                action="pause",
                success=False,
                bot=bot,
                message=f"Bot '{bot['name']}' is already paused",
                pause_reason=bot.get("pause_reason")
            )
        
        # Pause the bot
        if data is None:
            data = {}
        reason = data.get('reason', 'Manual pause by user')
        paused_at = datetime.now(timezone.utc).isoformat()
        
        runtime_before = await bot_runtime_state.ensure_state(bot)
        await db.bots_collection.update_one(
            {"id": bot_id},
            {
                "$set": {
                    "status": "paused",
                    "paused_at": paused_at,
                    "pause_reason": reason,
                    "paused_by_user": True
                }
            }
        )

        await bot_runtime_state.set_state(
            bot_id=bot_id,
            user_id=user_id,
            state="paused",
            reason=reason,
            source="api"
        )
        
        # Place bot in quarantine for auto-retraining (only if not manually paused)
        # Manual pauses get lower priority quarantine
        try:
            if not data or not data.get('manual'):
                await quarantine_service.quarantine_bot(bot_id, reason)
        except Exception as e:
            logger.warning(f"Failed to quarantine bot: {e}")
        
        # Get updated bot
        updated_bot = await db.bots_collection.find_one({"id": bot_id}, {"_id": 0})
        
        # Send real-time notifications
        await rt_events.bot_paused(user_id, updated_bot)
        await rt_events.bot_state_changed(
            user_id,
            bot_id,
            (runtime_before or {}).get("state", bot.get("status", "unknown")),
            "paused",
            reason
        )
        await audit_logger.log_bot_action("paused", user_id, bot_id, bot.get("name", "bot"), {"reason": reason})
        
        # Also broadcast overview and platform stats updates
        from services.realtime_service import realtime_service
        await realtime_service.broadcast_overview_update(user_id, f"Bot paused: {bot['name']}")
        await realtime_service.broadcast_platform_stats_update(user_id, bot.get('exchange'))
        
        logger.info(f"✅ Bot {bot['name']} paused by user {user_id[:8]}")
        
        return _action_payload(
            action="pause",
            success=True,
            bot=updated_bot,
            message=f"Bot '{bot['name']}' paused successfully",
            pause_reason=updated_bot.get("pause_reason")
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Pause bot error")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{bot_id}/resume")
@router.put("/{bot_id}/resume")
@router.post("/{bot_id}/unpause")
@router.put("/{bot_id}/unpause")
async def resume_bot(bot_id: str, user_id: str = Depends(get_current_user)):
    """Resume a paused bot's trading activity (also /unpause alias)
    
    Accepts both POST and PUT methods for compatibility with frontend
    
    Args:
        bot_id: Bot ID to resume
        user_id: Current user ID (from auth)
        
    Returns:
        Updated bot status
    """
    try:
        # Verify bot belongs to user
        bot = await db.bots_collection.find_one({"id": bot_id, "user_id": user_id}, {"_id": 0})
        if not bot:
            raise HTTPException(status_code=404, detail="Bot not found")
        
        blocker = await _check_bot_blockers(bot, user_id)
        # Check if currently paused
        if bot.get('status') != 'paused':
            if blocker:
                return _blocked_response("resume", bot, blocker)
            return _action_payload(
                action="resume",
                success=False,
                bot=bot,
                message=f"Bot '{bot['name']}' is not paused (status: {bot.get('status', 'unknown')})",
                pause_reason=bot.get("pause_reason")
            )

        if blocker:
            return _blocked_response("resume", bot, blocker)

        trading_mode = bot.get('trading_mode', 'paper')
        paper_trading_enabled = _paper_trading_enabled()
        live_trading_enabled = _live_trading_enabled()
        modes = await db.system_modes_collection.find_one({"user_id": user_id}, {"_id": 0})
        if trading_mode == 'paper' and modes and not modes.get('paperTrading', True):
            return _blocked_response(
                "resume",
                bot,
                _build_block_detail(
                    "system_mode_disabled",
                    "Paper trading is disabled in system mode",
                    "Enable paper trading in System Mode settings",
                ),
            )
        if trading_mode == 'live' and modes and not modes.get('liveTrading', False):
            return _blocked_response(
                "resume",
                bot,
                _build_block_detail(
                    "system_mode_disabled",
                    "Live trading is disabled in system mode",
                    "Enable live trading in System Mode settings",
                ),
            )

        if trading_mode == 'paper' and not paper_trading_enabled:
            return _blocked_response(
                "resume",
                bot,
                _build_block_detail(
                    "system_mode_disabled",
                    f"Cannot resume bot '{bot['name']}': Paper trading is disabled.",
                    "Set PAPER_TRADING=1 in environment",
                ),
            )
        if trading_mode == 'live' and not live_trading_enabled:
            return _blocked_response(
                "resume",
                bot,
                _build_block_detail(
                    "system_mode_disabled",
                    f"Cannot resume bot '{bot['name']}': Live trading is disabled.",
                    "Set LIVE_TRADING=1 in environment",
                ),
            )
        if not paper_trading_enabled and not live_trading_enabled:
            return _blocked_response(
                "resume",
                bot,
                _build_block_detail(
                    "system_mode_disabled",
                    "Cannot resume bot: Both paper and live trading are disabled.",
                    "Enable PAPER_TRADING=1 or LIVE_TRADING=1 in environment",
                ),
            )

        if trading_mode == "live":
            api_key = await db.api_keys_collection.find_one(
                {"user_id": user_id, "provider": bot.get("exchange", "")},
                {"_id": 0}
            )
            if not api_key:
                return _blocked_response(
                    "resume",
                    bot,
                    _build_block_detail(
                        "key_missing",
                        f"Cannot resume bot '{bot['name']}': API keys missing for {bot.get('exchange')}",
                        "Add and test API keys before resuming live trading",
                    ),
                )
        
        # Resume the bot
        resumed_at = datetime.now(timezone.utc).isoformat()
        
        runtime_before = await bot_runtime_state.ensure_state(bot)
        await db.bots_collection.update_one(
            {"id": bot_id},
            {
                "$set": {
                    "status": "active",
                    "resumed_at": resumed_at
                },
                "$unset": {
                    "paused_at": "",
                    "pause_reason": "",
                    "paused_by_user": "",
                    "paused_by_system": ""
                }
            }
        )

        await bot_runtime_state.set_state(
            bot_id=bot_id,
            user_id=user_id,
            state="active",
            reason=None,
            source="api"
        )
        
        # Get updated bot
        updated_bot = await db.bots_collection.find_one({"id": bot_id}, {"_id": 0})
        
        # Send real-time notification
        await rt_events.bot_resumed(user_id, updated_bot)
        await rt_events.bot_state_changed(
            user_id,
            bot_id,
            (runtime_before or {}).get("state", bot.get("status", "unknown")),
            "active",
            None
        )
        await audit_logger.log_bot_action("resumed", user_id, bot_id, bot.get("name", "bot"))
        
        logger.info(f"✅ Bot {bot['name']} resumed by user {user_id[:8]}")
        
        return _action_payload(
            action="resume",
            success=True,
            bot=updated_bot,
            message=f"Bot '{bot['name']}' resumed successfully",
            pause_reason=updated_bot.get("pause_reason")
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Resume bot error")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{bot_id}/restart")
async def restart_bot(bot_id: str, user_id: str = Depends(get_current_user)):
    """Restart a bot (stop then start) with consistent response shape."""
    try:
        bot = await db.bots_collection.find_one({"id": bot_id, "user_id": user_id}, {"_id": 0})
        if not bot:
            raise HTTPException(status_code=404, detail="Bot not found")

        blocker = await _check_bot_blockers(bot, user_id)
        if blocker:
            return _blocked_response("restart", bot, blocker)

        current_capital = bot.get('current_capital', 0)
        initial_capital = bot.get('initial_capital', 0)
        if current_capital <= 0 and initial_capital <= 0:
            return _blocked_response(
                "restart",
                bot,
                _build_block_detail(
                    "insufficient_funds",
                    f"Cannot restart bot '{bot['name']}': No wallet balance available.",
                    "Allocate capital to this bot before restarting",
                ),
            )

        trading_mode = bot.get('trading_mode', 'paper')
        paper_trading_enabled = _paper_trading_enabled()
        live_trading_enabled = _live_trading_enabled()
        modes = await db.system_modes_collection.find_one({"user_id": user_id}, {"_id": 0})
        if trading_mode == 'paper' and modes and not modes.get('paperTrading', True):
            return _blocked_response(
                "restart",
                bot,
                _build_block_detail(
                    "system_mode_disabled",
                    "Paper trading is disabled in system mode",
                    "Enable paper trading in System Mode settings",
                ),
            )
        if trading_mode == 'live' and modes and not modes.get('liveTrading', False):
            return _blocked_response(
                "restart",
                bot,
                _build_block_detail(
                    "system_mode_disabled",
                    "Live trading is disabled in system mode",
                    "Enable live trading in System Mode settings",
                ),
            )
        if trading_mode == 'paper' and not paper_trading_enabled:
            return _blocked_response(
                "restart",
                bot,
                _build_block_detail(
                    "system_mode_disabled",
                    f"Cannot restart bot '{bot['name']}': Paper trading is disabled.",
                    "Set PAPER_TRADING=1 in environment",
                ),
            )
        if trading_mode == 'live' and not live_trading_enabled:
            return _blocked_response(
                "restart",
                bot,
                _build_block_detail(
                    "system_mode_disabled",
                    f"Cannot restart bot '{bot['name']}': Live trading is disabled.",
                    "Set LIVE_TRADING=1 in environment",
                ),
            )

        if trading_mode == "live":
            api_key = await db.api_keys_collection.find_one(
                {"user_id": user_id, "provider": bot.get("exchange", "")},
                {"_id": 0}
            )
            if not api_key:
                return _blocked_response(
                    "restart",
                    bot,
                    _build_block_detail(
                        "key_missing",
                        f"Cannot restart bot '{bot['name']}': API keys missing for {bot.get('exchange')}",
                        "Add and test API keys before restarting live trading",
                    ),
                )

        started_at = datetime.now(timezone.utc).isoformat()
        await db.bots_collection.update_one(
            {"id": bot_id},
            {
                "$set": {
                    "status": "active",
                    "started_at": started_at,
                    "resumed_at": started_at
                },
                "$unset": {
                    "stopped_at": "",
                    "paused_at": "",
                    "pause_reason": "",
                    "paused_by_user": "",
                    "paused_by_system": "",
                    "stop_reason": ""
                }
            }
        )

        # Sync runtime state — critical to prevent scheduler from re-pausing the bot
        await bot_runtime_state.set_state(
            bot_id=bot_id,
            user_id=user_id,
            state="active",
            reason=None,
            source="api"
        )

        updated_bot = await db.bots_collection.find_one({"id": bot_id}, {"_id": 0})
        await rt_events.bot_resumed(user_id, updated_bot)
        await audit_logger.log_bot_action("restarted", user_id, bot_id, bot.get("name", "bot"))
        logger.info(f"✅ Bot {bot.get('name')} restarted by user {user_id[:8]}")

        return _action_payload(
            action="restart",
            success=True,
            bot=updated_bot,
            message=f"Bot '{bot['name']}' restarted successfully",
            pause_reason=updated_bot.get("pause_reason")
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Restart bot error")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{bot_id}/cooldown")
async def set_bot_cooldown(
    bot_id: str, 
    data: dict,
    user_id: str = Depends(get_current_user)
):
    """Set custom cooldown period for a bot
    
    Args:
        bot_id: Bot ID
        data: {"cooldown_minutes": int} - Cooldown period in minutes
        user_id: Current user ID (from auth)
        
    Returns:
        Updated bot with cooldown settings
    """
    try:
        # Verify bot belongs to user
        bot = await db.bots_collection.find_one({"id": bot_id, "user_id": user_id}, {"_id": 0})
        if not bot:
            raise HTTPException(status_code=404, detail="Bot not found")
        
        # Validate cooldown period
        cooldown_minutes = data.get('cooldown_minutes')
        if not cooldown_minutes or not isinstance(cooldown_minutes, (int, float)):
            raise HTTPException(status_code=400, detail="Invalid cooldown_minutes value")
        
        # Validate range (5 minutes to 120 minutes)
        if cooldown_minutes < 5 or cooldown_minutes > 120:
            raise HTTPException(
                status_code=400, 
                detail="Cooldown period must be between 5 and 120 minutes"
            )
        
        # Update bot cooldown
        await db.bots_collection.update_one(
            {"id": bot_id},
            {
                "$set": {
                    "custom_cooldown_minutes": cooldown_minutes,
                    "cooldown_updated_at": datetime.now(timezone.utc).isoformat()
                }
            }
        )
        
        # Get updated bot
        updated_bot = await db.bots_collection.find_one({"id": bot_id}, {"_id": 0})
        
        logger.info(f"✅ Bot {bot['name']} cooldown set to {cooldown_minutes} minutes")
        
        return {
            "success": True,
            "message": f"Cooldown set to {cooldown_minutes} minutes for '{bot['name']}'",
            "bot": updated_bot,
            "cooldown_minutes": cooldown_minutes
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Set cooldown error")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{bot_id}/status")
async def get_bot_detailed_status(bot_id: str, user_id: str = Depends(get_current_user)):
    """Get detailed status information for a bot
    
    Args:
        bot_id: Bot ID
        user_id: Current user ID (from auth)
        
    Returns:
        Comprehensive bot status including cooldown info, recent trades, etc.
    """
    try:
        # Verify bot belongs to user
        bot = await db.bots_collection.find_one({"id": bot_id, "user_id": user_id}, {"_id": 0})
        if not bot:
            raise HTTPException(status_code=404, detail="Bot not found")
        
        # Calculate cooldown status
        last_trade_time = bot.get('last_trade_time')
        custom_cooldown = bot.get('custom_cooldown_minutes', 15)  # Default 15 minutes
        cooldown_remaining = 0
        can_trade_at = None
        
        if last_trade_time:
            if isinstance(last_trade_time, str):
                last_trade_dt = datetime.fromisoformat(last_trade_time.replace('Z', '+00:00'))
            else:
                last_trade_dt = last_trade_time
            
            next_trade_allowed = last_trade_dt + timedelta(minutes=custom_cooldown)
            now = datetime.now(timezone.utc)
            
            if now < next_trade_allowed:
                cooldown_remaining = int((next_trade_allowed - now).total_seconds() / 60)
                can_trade_at = next_trade_allowed.isoformat()
        
        # Get recent trades (last 10)
        recent_trades = await db.trades_collection.find(
            {"bot_id": bot_id},
            {"_id": 0}
        ).sort("timestamp", -1).limit(10).to_list(10)
        
        # Calculate daily stats
        today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        trades_today = await db.trades_collection.count_documents({
            "bot_id": bot_id,
            "timestamp": {"$gte": today_start.isoformat()}
        })
        
        # Calculate profit today
        today_trades = await db.trades_collection.find(
            {
                "bot_id": bot_id,
                "timestamp": {"$gte": today_start.isoformat()}
            },
            {"_id": 0}
        ).to_list(1000)
        
        profit_today = sum(t.get('net_pnl', t.get('profit_loss', 0)) for t in today_trades)
        
        return {
            "bot": bot,
            "status": {
                "current_status": bot.get('status', 'unknown'),
                "is_active": bot.get('status') == 'active',
                "is_paused": bot.get('status') == 'paused',
                "pause_reason": bot.get('pause_reason'),
                "paused_at": bot.get('paused_at'),
                "paused_by_system": bot.get('paused_by_system', False)
            },
            "cooldown": {
                "custom_cooldown_minutes": custom_cooldown,
                "remaining_minutes": cooldown_remaining,
                "can_trade_now": cooldown_remaining == 0 and bot.get('status') == 'active',
                "next_trade_at": can_trade_at
            },
            "performance": {
                "total_trades": bot.get('trades_count', 0),
                "trades_today": trades_today,
                "total_profit": bot.get('total_profit', 0),
                "profit_today": round(profit_today, 2),
                "current_capital": bot.get('current_capital', 0),
                "win_rate": bot.get('win_rate', 0)
            },
            "recent_trades": recent_trades[:5]  # Last 5 trades
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Get bot status error")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{bot_id}/risk/status")
async def get_bot_risk_status(bot_id: str, user_id: str = Depends(get_current_user)):
    """Get risk status metrics for a bot."""
    try:
        bot = await db.bots_collection.find_one({"id": bot_id, "user_id": user_id}, {"_id": 0})
        if not bot:
            raise HTTPException(status_code=404, detail="Bot not found")

        exchange = bot.get("exchange", "").lower()
        pair = bot.get("pair", "")
        currency = "ZAR" if exchange == "luno" or "/ZAR" in pair else "USDT"

        current_equity = bot.get("current_capital", 0)
        drawdown_pct = 0.0
        daily_pnl = 0.0
        daily_loss_pct = 0.0

        ledger_db = getattr(db, "db", None)
        if ledger_db is not None:
            from services.ledger_service import get_ledger_service
            ledger = get_ledger_service(ledger_db)
            current_equity = await ledger.compute_equity(bot_id=bot_id, currency=currency)
            current_dd, _ = await ledger.compute_drawdown(bot_id=bot_id, currency=currency)
            drawdown_pct = current_dd * 100

            today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
            realized = await ledger.compute_realized_pnl(bot_id=bot_id, since=today_start)
            fees = await ledger.compute_fees_paid(bot_id=bot_id, since=today_start, currency=currency)
            daily_pnl = realized - fees
            funded = await ledger.compute_funded_capital(bot_id=bot_id, currency=currency)
            if funded > 0 and daily_pnl < 0:
                daily_loss_pct = (abs(daily_pnl) / funded) * 100

        equity_peak = bot.get("equity_peak", current_equity)

        return {
            "bot_id": bot_id,
            "exchange": exchange,
            "drawdown_pct": round(drawdown_pct, 2),
            "daily_pnl": round(daily_pnl, 2),
            "daily_loss_pct": round(daily_loss_pct, 2),
            "equity_peak": round(equity_peak, 2),
            "current_equity": round(current_equity, 2),
            "pause_reason": bot.get("pause_reason"),
            "currency": currency
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Bot risk status error")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/pause-all")
async def pause_all_bots(data: Optional[Dict] = None, user_id: str = Depends(get_current_user)):
    """Pause all active bots for a user
    
    Args:
        data: Optional data with reason for pause
        user_id: Current user ID (from auth)
        
    Returns:
        Summary of paused bots
    """
    try:
        if data is None:
            data = {}
        reason = data.get('reason', 'Bulk pause by user')
        paused_at = datetime.now(timezone.utc).isoformat()
        
        # Pause all active bots
        result = await db.bots_collection.update_many(
            {"user_id": user_id, "status": "active"},
            {
                "$set": {
                    "status": "paused",
                    "paused_at": paused_at,
                    "pause_reason": reason,
                    "paused_by_user": True
                }
            }
        )
        
        # Send real-time notification
        await rt_events.force_refresh(user_id, f"Paused {result.modified_count} bots")
        
        logger.info(f"✅ Paused {result.modified_count} bots for user {user_id[:8]}")
        
        return {
            "success": True,
            "message": f"Paused {result.modified_count} bot(s)",
            "paused_count": result.modified_count
        }
        
    except Exception as e:
        logger.exception("Pause all bots error")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{bot_id}/trading-enabled")
@router.post("/{bot_id}/trading-enabled")
async def toggle_bot_trading(bot_id: str, data: Dict, user_id: str = Depends(get_current_user)):
    """Enable or disable trading for a specific bot
    
    This allows users to toggle trading on/off without pausing the bot.
    The bot remains active but won't execute trades when trading_enabled=False.
    
    Args:
        bot_id: Bot ID to toggle
        data: {"enabled": true/false}
        user_id: Current user ID (from auth)
        
    Returns:
        Updated bot status
    """
    try:
        # Verify bot belongs to user
        bot = await db.bots_collection.find_one({"id": bot_id, "user_id": user_id}, {"_id": 0})
        if not bot:
            raise HTTPException(status_code=404, detail="Bot not found")
        
        enabled = data.get('enabled', True)
        
        # Update trading_enabled flag
        await db.bots_collection.update_one(
            {"id": bot_id},
            {
                "$set": {
                    "trading_enabled": enabled,
                    "trading_enabled_updated_at": datetime.now(timezone.utc).isoformat(),
                    "trading_enabled_by_user": True
                }
            }
        )
        
        # Get updated bot
        updated_bot = await db.bots_collection.find_one({"id": bot_id}, {"_id": 0})
        
        # Log audit trail
        from engines.audit_logger import audit_logger
        await audit_logger.log_action(
            user_id=user_id,
            action="bot_trading_toggled",
            details={
                "bot_id": bot_id,
                "bot_name": bot.get('name'),
                "enabled": enabled
            }
        )
        
        # Send real-time notification
        await rt_events.force_refresh(user_id, f"Bot {bot.get('name')} trading {'enabled' if enabled else 'disabled'}")
        
        status_text = "enabled" if enabled else "disabled"
        logger.info(f"✅ Bot {bot['name']} trading {status_text} by user {user_id[:8]}")
        
        return {
            "success": True,
            "message": f"Bot '{bot['name']}' trading {status_text}",
            "bot": updated_bot
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Toggle bot trading error")
        raise HTTPException(status_code=500, detail=str(e))



# NOTE: PUT/PATCH /{bot_id} is the canonical update endpoint for bots.
# It is defined in server.py (api_router) and includes live-trading gate
# enforcement.  Do NOT add a duplicate here — the server's route collision
# detector will refuse to start if both exist.

@router.delete("/{bot_id}")
async def delete_bot(
    bot_id: str,
    user_id: str = Depends(get_current_user)
):
    """Delete a bot permanently
    
    Soft-deletes the bot by setting status to 'deleted' rather than removing from DB.
    This preserves historical data for analytics while removing bot from active use.
    Broadcasts realtime events for immediate UI update.
    
    Args:
        bot_id: Bot ID to delete
        user_id: Current user ID (from auth)
        
    Returns:
        Success response with deletion confirmation
    """
    try:
        # Get bot and verify ownership
        bot = await db.bots_collection.find_one(
            {"id": bot_id, "user_id": user_id},
            {"_id": 0}
        )
        
        if not bot:
            raise HTTPException(
                status_code=404,
                detail=f"Bot {bot_id} not found or access denied"
            )
        
        bot_name = bot.get('name', 'Unknown')
        
        # Soft delete: mark as deleted but keep in DB for history
        await db.bots_collection.update_one(
            {"id": bot_id},
            {
                "$set": {
                    "status": "deleted",
                    "deleted": True,
                    "is_deleted": True,
                    "deleted_at": datetime.now(timezone.utc).isoformat(),
                    "deleted_by": user_id
                }
            }
        )

        await bot_runtime_state.remove(bot_id)
        try:
            from engines.trade_staggerer import trade_staggerer
            await trade_staggerer.clear_bot(bot_id)
        except Exception as e:
            logger.warning(f"Failed to clear scheduler queue/runtime for bot {bot_id}: {e}")

        try:
            from services.paper_wallet_ledger import paper_wallet_ledger
            await paper_wallet_ledger.release_funds(bot_id)
        except Exception as e:
            logger.warning(f"Failed to release paper wallet for bot {bot_id}: {e}")
        
        # Broadcast realtime events
        from services.realtime_service import realtime_service
        
        # Bot deleted event
        await rt_events.bot_deleted(user_id, bot_name)
        await audit_logger.log_bot_action("deleted", user_id, bot_id, bot_name)
        
        # Update overview, profits, and platform stats
        await realtime_service.broadcast_overview_update(user_id, f"Bot deleted: {bot_name}")
        await realtime_service.broadcast_profits_update(user_id, f"Bot deleted: {bot_name}")
        
        # Update platform stats for the bot's exchange
        exchange = bot.get('exchange')
        if exchange:
            await realtime_service.broadcast_platform_stats_update(user_id, exchange)
        
        logger.info(f"Bot {bot_id} ({bot_name}) deleted by user {user_id[:8]}")
        
        return {
            "success": True,
            "message": f"Bot '{bot_name}' deleted successfully",
            "bot_id": bot_id,
            "bot_name": bot_name
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Delete bot error")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{bot_id}/diagnostics")
async def get_bot_diagnostics(bot_id: str, user_id: str = Depends(get_current_user)):
    """Get detailed diagnostics for why a bot is or isn't trading
    
    Returns comprehensive diagnostic information including:
    - Trading gates status (paper/live/autopilot/emergency)
    - Rate limiting and daily budget status
    - Bodyguard metrics and pause reasons
    - API key status and permissions
    - Last trade time and next eligible action
    - Win rate and profitability metrics
    
    Args:
        bot_id: Bot ID to diagnose
        user_id: Current user ID (from auth)
        
    Returns:
        Detailed diagnostic information explaining bot trading status
    """
    try:
        # Get bot
        bot = await db.bots_collection.find_one({"id": bot_id, "user_id": user_id}, {"_id": 0})
        if not bot:
            raise HTTPException(status_code=404, detail="Bot not found")
        
        # Check if deleted
        if bot.get('status') == 'deleted':
            raise HTTPException(status_code=404, detail="Bot has been deleted")
        
        # Get user for system gates
        user = await db.users_collection.find_one({"id": user_id}, {"_id": 0})
        
        diagnostics = {
            "bot_id": bot_id,
            "bot_name": bot.get('name'),
            "exchange": bot.get('exchange'),
            "status": bot.get('status'),
            "can_trade": False,
            "reasons": [],
            "gates": {},
            "limits": {},
            "bodyguard": {},
            "api_keys": {},
            "recent_activity": {}
        }
        
        # Check trading gates
        trading_mode = bot.get('trading_mode', 'paper')
        system_mode = user.get('system_mode') if user else 'testing'
        emergency_stop = user.get('emergency_stop', False) if user else False
        
        diagnostics['gates'] = {
            "trading_mode": trading_mode,
            "system_mode": system_mode,
            "emergency_stop": emergency_stop,
            "autopilot_enabled": user.get('autopilot_enabled', True) if user else True
        }
        
        # Status checks
        if bot.get('status') != 'active':
            diagnostics['reasons'].append(f"Bot status is '{bot.get('status')}', not 'active'")
        
        if emergency_stop:
            diagnostics['reasons'].append("Emergency stop is enabled")
        
        if bot.get('paused_by_bodyguard'):
            diagnostics['reasons'].append(f"Paused by bodyguard: {bot.get('pause_reason', 'Unknown reason')}")
        
        if bot.get('paused_by_system'):
            diagnostics['reasons'].append(f"Paused by system: {bot.get('pause_reason', 'Unknown reason')}")
        
        # Check trade limits
        exchange = bot.get('exchange', 'binance')
        from engines.trade_budget_manager import trade_budget_manager
        
        daily_budget = await trade_budget_manager.calculate_bot_daily_budget(bot_id, exchange)
        remaining = await trade_budget_manager.get_bot_remaining_budget(bot_id, exchange)
        can_trade_budget, budget_reason = await trade_budget_manager.can_execute_trade(bot_id, exchange)
        
        diagnostics['limits'] = {
            "daily_budget": daily_budget,
            "remaining_today": remaining,
            "can_trade": can_trade_budget,
            "reason": budget_reason
        }
        
        if not can_trade_budget:
            diagnostics['reasons'].append(f"Trade limit: {budget_reason}")
        
        # Check bodyguard metrics
        from services.bodyguard_service import bodyguard_service
        bodyguard_status = await bodyguard_service.get_bot_drawdown_status(bot_id)
        
        if bodyguard_status:
            diagnostics['bodyguard'] = bodyguard_status
            
            if bodyguard_status.get('paused_by_bodyguard'):
                diagnostics['reasons'].append(f"Bodyguard paused: {bodyguard_status.get('pause_reason', 'Drawdown exceeded')}")
        
        # Check API keys
        api_key = await db.api_keys_collection.find_one({
            "user_id": user_id,
            "provider": exchange
        }, {"_id": 0})
        
        diagnostics['api_keys'] = {
            "has_keys": api_key is not None,
            "connected": api_key.get('connected', False) if api_key else False,
            "provider": exchange
        }
        
        if trading_mode == 'live' and not api_key:
            diagnostics['reasons'].append(f"No API keys configured for {exchange}")
        
        # Recent activity
        last_trade_time = bot.get('last_trade_time') or bot.get('last_trade')
        diagnostics['recent_activity'] = {
            "last_trade_time": last_trade_time,
            "trades_count": bot.get('trades_count', 0),
            "current_capital": bot.get('current_capital', 0),
            "total_profit": bot.get('total_profit', 0),
            "win_rate": bot.get('win_rate', 0)
        }
        
        # Determine if bot can trade
        diagnostics['can_trade'] = (
            bot.get('status') == 'active' and
            not emergency_stop and
            not bot.get('paused_by_bodyguard') and
            not bot.get('paused_by_system') and
            can_trade_budget
        )
        
        if diagnostics['can_trade']:
            diagnostics['reasons'] = ["Bot is ready to trade"]
        
        diagnostics['timestamp'] = datetime.now(timezone.utc).isoformat()
        
        return diagnostics
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Get bot diagnostics error")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/diagnostics")
async def get_all_bots_diagnostics(user_id: str = Depends(get_current_user)):
    """Get diagnostics for all user bots (bulk endpoint)
    
    Returns summary diagnostics for all non-deleted bots
    
    Args:
        user_id: Current user ID (from auth)
        
    Returns:
        List of bot diagnostics with trading readiness status
    """
    try:
        # Get all non-deleted bots
        bots = await db.bots_collection.find(
            {
                "user_id": user_id,
                "status": {"$nin": ["deleted", "marked_for_deletion"]}
            },
            {"_id": 0}
        ).to_list(1000)
        
        diagnostics_list = []
        
        for bot in bots:
            bot_id = bot['id']
            exchange = bot.get('exchange', 'binance')
            
            # Quick diagnostic check
            from engines.trade_budget_manager import trade_budget_manager
            remaining = await trade_budget_manager.get_bot_remaining_budget(bot_id, exchange)
            can_trade_budget, budget_reason = await trade_budget_manager.can_execute_trade(bot_id, exchange)
            
            can_trade = (
                bot.get('status') == 'active' and
                not bot.get('paused_by_bodyguard') and
                not bot.get('paused_by_system') and
                can_trade_budget
            )
            
            # Build reason summary
            reasons = []
            if bot.get('status') != 'active':
                reasons.append(f"Status: {bot.get('status')}")
            if bot.get('paused_by_bodyguard'):
                reasons.append("Bodyguard pause")
            if not can_trade_budget:
                reasons.append("Budget limit")
            
            diagnostics_list.append({
                "bot_id": bot_id,
                "bot_name": bot.get('name'),
                "exchange": exchange,
                "status": bot.get('status'),
                "can_trade": can_trade,
                "reasons": reasons if reasons else ["Ready to trade"],
                "remaining_budget": remaining,
                "trades_count": bot.get('trades_count', 0),
                "win_rate": bot.get('win_rate', 0),
                "total_profit": bot.get('total_profit', 0)
            })
        
        # Summary statistics
        can_trade_count = len([d for d in diagnostics_list if d['can_trade']])
        paused_count = len([d for d in diagnostics_list if 'pause' in str(d['reasons']).lower()])
        budget_limited_count = len([d for d in diagnostics_list if 'budget' in str(d['reasons']).lower()])
        
        return {
            "diagnostics": diagnostics_list,
            "summary": {
                "total_bots": len(diagnostics_list),
                "can_trade": can_trade_count,
                "paused": paused_count,
                "budget_limited": budget_limited_count
            },
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as e:
        logger.exception("Get all bots diagnostics error")
        raise HTTPException(status_code=500, detail=str(e))
