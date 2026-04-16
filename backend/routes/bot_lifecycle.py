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
import inspect as _inspect

from auth import get_current_user
import database as db
from websocket_manager import manager
from realtime_events import rt_events
from services.bot_quarantine import quarantine_service
from services.bot_runtime_state import bot_runtime_state
from engines.audit_logger import audit_logger
from rules.bot_rules import SUPPORTED_EXCHANGES
from services.fx_normalizer import get_quote_currency as _get_quote_currency
from utils.datetime_helpers import remaining_seconds
from utils.env_utils import env_bool
from utils.numeric_utils import safe_numeric
from json_utils import serialize_doc

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/bots", tags=["Bot Lifecycle"])
bots_collection = db.bots_collection
ALL_EXCHANGES = list(SUPPORTED_EXCHANGES)

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
    success: bool = True,
    error: Optional[str] = None,
) -> Dict:
    """Build a safe bots status response payload (platforms kept for backward compatibility)."""
    bots = [] if bots is None else bots
    exchange_counts = {} if exchange_counts is None else exchange_counts
    all_exchanges = [] if all_exchanges is None else all_exchanges
    active_bots = sum(
        1
        for bot in bots
        if bot.get("state") in ("active", "running") or bot.get("status") in ("active", "running")
    )
    return {
        "success": success,
        "active_bots": active_bots,
        "bots": bots,
        "platforms": exchange_counts,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "total": len(bots),
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
    user = await db.users_collection.find_one({"id": user_id}, {"_id": 0})
    if user and user.get("daily_loss_lock_active", False):
        return _build_block_detail(
            "daily_loss_lock",
            user.get("daily_loss_locked_reason", "Daily loss lock is active"),
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
        # Paper bots are never blocked by training — they trade freely from the first tick.
        if bot.get("trading_mode", "paper") != "paper":
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
    user_id: str = Depends(get_current_user),
    meta: Optional[int] = 0,
):
    """Get bot status list with states for bot management
    
    Returns all bots with detailed status including training states.
    Requires authentication; unauthenticated requests receive 401.
    
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

    try:
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
            return _bots_status_payload([], exchange_counts, all_exchanges)

        runtime_states = {
            state.get("bot_id"): state
            for state in await bot_runtime_state.list_states(user_id)
        }

        # Single query to determine which bots have open/active trades.
        # This powers the "In Position" counter in Bot Operations Center.
        open_position_bot_ids: set = set()
        if db.trades_collection is not None:
            try:
                bot_ids_all = [b.get("id") for b in bots if b.get("id")]
                _distinct_call = db.trades_collection.distinct(
                    "bot_id",
                    {"bot_id": {"$in": bot_ids_all}, "status": {"$in": ["open", "active", "pending"]}},
                )
                _open_ids = await _distinct_call if _inspect.isawaitable(_distinct_call) else _distinct_call
                open_position_bot_ids = set(_open_ids or [])
            except Exception as _e:
                logger.warning("open-position distinct query failed: %s", _e)

        # Enrich each bot with detailed state
        enriched_bots = []
        for bot in bots:
            status = bot.get('status', 'unknown')
            runtime_state = runtime_states.get(bot.get("id"))
            if runtime_state and runtime_state.get("state") in {"active", "paused", "stopped"}:
                status = runtime_state.get("state")
            
            # Map status to standard states
            # Paper bots are never gated by training — they trade freely from the first tick.
            is_paper = bot.get('trading_mode', 'paper') == 'paper'
            training_complete = bot.get('training_complete', True if is_paper else False)
            training_in_progress = bot.get('training_in_progress', False)

            if status in ('training', ) or (training_in_progress and not is_paper):
                state = 'training'
            elif status == 'training_failed' or (bot.get('training_failed') and not is_paper):
                state = 'training_failed'
            elif status == 'active' and not training_complete and not is_paper:
                # Live bots only: marked active but training is not complete — show as training
                state = 'training'
            elif status == 'active':
                # paused_by_user / paused_by_system flags take precedence even when
                # runtime_state has overridden status to "active" — a bot cannot be
                # simultaneously active and paused (fix for A).
                if bot.get('paused_by_user') or bot.get('paused_by_system'):
                    if (training_complete or is_paper) and bot.get('paused_by_user'):
                        state = 'paused_ready'
                    else:
                        state = 'paused'
                else:
                    state = 'active'
            elif status == 'paused':
                # Check if ready to activate (paused_ready)
                if (training_complete or is_paper) and bot.get('paused_by_user'):
                    state = 'paused_ready'
                else:
                    state = 'paused'
            elif status == 'stopped':
                state = 'stopped'
            else:
                state = status

            # Compute training progress fields (paper bots always show complete)
            required_closed = int(bot.get('training_required_closed_trades', bot.get('min_trades_required', 5)))
            completed_closed = int(bot.get('closed_trades_count', bot.get('trades_count', 0)))
            training_progress = {
                "closed_trades_completed": completed_closed,
                "required": required_closed,
                "percent": round(min(100, (completed_closed / required_closed * 100)) if required_closed > 0 else 0, 1),
            } if (not training_complete and not is_paper) else None

            # Determine plain-English training block reason (paper bots have none)
            if state == 'training' and not is_paper:
                if not training_complete and status == 'active':
                    training_block_reason = (
                        f"Bot needs {required_closed} closed trades to complete training "
                        f"({completed_closed}/{required_closed} done). "
                        "It will trade freely once training is complete."
                    )
                elif status == 'training_failed':
                    training_block_reason = bot.get('training_failed_reason') or "Training failed — check bot configuration."
                else:
                    training_block_reason = bot.get('training_failed_reason') or "Training in progress — collecting closed trades."
            else:
                training_block_reason = None

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
            elif (state in ('training', 'training_failed') or training_in_progress) and not is_paper:
                pause_reason_code = 'training'
                pause_reason_message = training_block_reason or bot.get('training_failed_reason') or 'Training in progress'
                pause_next_action = 'Training completes automatically after enough closed trades'
            elif bot.get('paused_by_bodyguard'):
                pause_reason_code = 'bodyguard_lock'
                pause_reason_message = pause_reason or 'Paused by bodyguard drawdown protection'
                pause_next_action = 'Wait for drawdown recovery or reset bodyguard lock'
            elif bot.get('paused_by_system'):
                pause_reason_code = 'system_pause'
                pause_reason_message = pause_reason or 'Paused by system'
                pause_next_action = 'Review system status and resume when cleared'
            elif bot.get('paused_by_user'):
                pause_reason_code = 'manual_pause'
                pause_reason_message = pause_reason or 'Paused by user'
                pause_next_action = 'Resume bot when ready'
            elif status == 'paused':
                pause_reason_code = 'paused'
                pause_reason_message = pause_reason or 'Bot paused'
                pause_next_action = 'Resume bot'
            
            # ── Per-bot position + performance metrics ────────────────────────────
            bot_id_str = bot.get('id', '')
            has_open_position = bot_id_str in open_position_bot_ids

            # Performance object — built from the bot document counters that the
            # trading engine maintains via $inc/$set on trade open/close.
            _win_count = int(bot.get('win_count', 0) or 0)
            _loss_count = int(bot.get('loss_count', 0) or 0)
            _trades_closed = int(bot.get('trades_count', 0) or 0)
            _win_rate_pct = round(_win_count / _trades_closed * 100, 2) if _trades_closed > 0 else 0.0
            _total_profit = safe_numeric(bot.get('total_profit', 0))
            performance = {
                "profit_realized": _total_profit,
                "trade_count": _trades_closed,
                "win_rate_pct": _win_rate_pct,
                "win_count": _win_count,
                "loss_count": _loss_count,
            }

            # Capital summary — derived from bot document fields kept in sync by engine.
            _current_capital = safe_numeric(bot.get('current_capital', 0))
            _initial_capital = safe_numeric(
                bot.get('initial_capital') or bot.get('starting_capital') or _current_capital
            )
            _open_pos_value = safe_numeric(bot.get('open_position_value', 0))
            _unrealized = safe_numeric(bot.get('unrealized_profit', 0))
            # Resolve the native trading quote currency so the frontend can display
            # USDT amounts with "$" and ZAR amounts with "R" — never mix the two.
            _exchange_str = str(bot.get('exchange') or '').lower()
            _pair_str = str(bot.get('pair') or bot.get('symbol') or '')
            _quote_currency = (
                bot.get('quote_currency')
                or _get_quote_currency(_exchange_str, _pair_str)
            )
            capital_summary = {
                "initial_capital": _initial_capital,
                "allocated_capital": _current_capital,
                "available_capital": max(0.0, _current_capital - _open_pos_value),
                "open_position_value": _open_pos_value,
                "total_equity": _current_capital + _unrealized,
                "realized_profit": _total_profit,
                "unrealized_profit": _unrealized,
                "quote_currency": _quote_currency,
            }

            enriched_bot = {
                "id": bot.get('id'),
                "name": bot.get('name'),
                "exchange": bot.get('exchange', 'unknown'),
                # Canonical bot type — must be forwarded so the frontend's
                # Normal/Scalper summary tiles and fleet tab filters work correctly.
                # Without this field every bot reads as '' (empty), which the
                # BotOperationsCenter counts as "normal", producing 20 Normal / 0 Scalper.
                "bot_type": (bot.get('bot_type') or 'normal').lower(),
                # Active trading pair — used by fleet cards, diagnostics, and radar
                "pair": bot.get('pair') or bot.get('symbol') or '',
                "symbol": bot.get('symbol') or bot.get('pair') or '',
                # Last scheduler skip reason — surfaces why individual bots are blocked
                # (e.g. hard_edge_filter, portfolio_guard) so the frontend can display it
                # in the bot card and diagnostics panel for each exchange.
                "last_skip_reason": bot.get('last_skip_reason') or '',
                "last_eligibility_code": bot.get('last_eligibility') or bot.get('last_eligibility_code') or '',
                # Native trading quote currency — used by frontend to show correct symbol
                # (ZAR → "R", USDT → "$").  Must never be absent on a Binance/KuCoin/Bybit bot.
                "quote_currency": _quote_currency,
                "state": state,
                "lifecycle_state": state,  # Canonical lifecycle state
                "display_state": state,  # Single canonical display state for frontend
                "status": status,  # Keep original for compatibility
                "paused_reason": pause_reason,  # Canonical field (support legacy)
                "paused_reason_code": pause_reason_code,
                "paused_reason_message": pause_reason_message,
                "paused_next_action": pause_next_action,
                "paused_at": bot.get('paused_at') or bot.get('quarantined_at'),
                "paused_by_user": bot.get('paused_by_user', False),
                "paused_by_system": bot.get('paused_by_system', False),
                "runtime_state": serialize_doc(runtime_state) if runtime_state else None,
                "quarantine_reason": bot.get('quarantine_reason'),
                "quarantine_until": bot.get('quarantine_until'),
                "quarantine_release_at": quarantine_release_at,
                "quarantine_remaining_seconds": quarantine_remaining_seconds,
                "training_state": bot.get('training_state'),
                "training_progress": training_progress,
                "training_block_reason": training_block_reason,
                "trading_mode": bot.get('trading_mode', 'paper'),
                "risk_mode": bot.get('risk_mode', 'balanced'),
                "current_capital": safe_numeric(bot.get('current_capital', 0)),
                "total_profit": safe_numeric(bot.get('total_profit', 0)),
                "trades_count": int(bot.get('trades_count', 0) or 0),
                "training_complete": training_complete,
                "training_failed_reason": bot.get('training_failed_reason'),
                "training_in_progress": training_in_progress,
                "paper_start_date": bot.get('paper_start_date'),
                "active": state == 'active',
                "paused": state == 'paused' or state == 'paused_ready',
                "in_quarantine": status == 'quarantined',
                "in_training": state in ('training', 'training_failed'),
                "created_at": bot.get('created_at'),
                "started_at": bot.get('started_at'),
                "stopped_at": bot.get('stopped_at'),
                # Per-bot diagnostics: populated by trading engine on each tick/decision
                "last_tick_at": bot.get('last_tick_at') or bot.get('last_trade'),
                "last_decision_at": bot.get('last_decision_at'),
                "last_decision_reason": bot.get('last_decision_reason') or training_block_reason,
                "last_market_price": bot.get('last_market_price'),
                "last_strategy_signal": bot.get('last_strategy_signal'),
                "last_order_attempt_at": bot.get('last_order_attempt_at'),
                "last_order_error": bot.get('last_order_error'),
                "last_trade_simulated_at": bot.get('last_trade_simulated_at') or bot.get('last_trade'),
                # Open position flag — used by Bot Operations Center "In Position" counter
                "has_open_position": has_open_position,
                "open_position": has_open_position,  # legacy alias
                # Performance metrics — used by Bot Fleet panel cards
                "performance": performance,
                # Capital summary — used by Bot Fleet detailed view
                "capital_summary": capital_summary,
            }
            # Serialize to eliminate BSON types (datetime→ISO str, ObjectId→str, etc.)
            # that would cause json.dumps(..., allow_nan=False) to raise ValueError.
            enriched_bots.append(serialize_doc(enriched_bot))
        
        # Count by exchange to ensure all 7 are represented
        exchange_counts = {exchange: 0 for exchange in all_exchanges}
        for bot in enriched_bots:
            exchange = bot.get('exchange')
            if exchange in exchange_counts:
                exchange_counts[exchange] += 1
        if meta:
            return {"exchange_counts": exchange_counts, "all_exchanges": all_exchanges}
        return _bots_status_payload(enriched_bots, exchange_counts, all_exchanges)
        
    except Exception:
        logger.exception("Get bots status error for user %s", user_id)
        if meta:
            return {"exchange_counts": exchange_counts, "all_exchanges": all_exchanges}
        return _bots_status_payload(
            [],
            exchange_counts,
            all_exchanges,
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
        paper_trading_enabled = env_bool('PAPER_TRADING', False) or env_bool('ENABLE_PAPER_TRADING', False)
        live_trading_enabled = env_bool('LIVE_TRADING', False) or env_bool('ENABLE_LIVE_TRADING', False)
        
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
        
        # Emit lifecycle event
        try:
            from routes.events import emit_event
            await emit_event(user_id, "bot_started", "info", f"Bot '{bot['name']}' started on {bot.get('exchange', 'exchange')} in {bot.get('trading_mode', 'paper')} mode", meta={"bot_id": bot_id})
        except Exception:
            pass
        
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
        
        # Emit lifecycle event
        try:
            from routes.events import emit_event
            await emit_event(user_id, "bot_stopped", "info", f"Bot '{bot['name']}' stopped — {reason}", meta={"bot_id": bot_id})
        except Exception:
            pass
        
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
        # Use env_bool for proper parsing of truthy values (1, true, yes, on)
        paper_trading_enabled = env_bool('PAPER_TRADING', False) or env_bool('ENABLE_PAPER_TRADING', False)
        live_trading_enabled = env_bool('LIVE_TRADING', False) or env_bool('ENABLE_LIVE_TRADING', False)
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
        # Use env_bool for proper parsing of truthy values (1, true, yes, on)
        paper_trading_enabled = env_bool('PAPER_TRADING', False) or env_bool('ENABLE_PAPER_TRADING', False)
        live_trading_enabled = env_bool('LIVE_TRADING', False) or env_bool('ENABLE_LIVE_TRADING', False)
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

        updated_bot = await db.bots_collection.find_one({"id": bot_id}, {"_id": 0})
        await rt_events.bot_resumed(user_id, updated_bot)
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
            "status": bot.get('status', 'unknown'),
            "status_detail": {
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
            from services.paper_wallet_ledger import paper_wallet_ledger
            await paper_wallet_ledger.release_funds(bot_id)
        except Exception as e:
            logger.warning(f"Failed to release paper wallet for bot {bot_id}: {e}")
        
        # Broadcast realtime events
        from services.realtime_service import realtime_service
        
        # Bot deleted event (include bot_id so frontend can immediately remove it)
        await rt_events.bot_deleted(user_id, bot_name, bot_id=bot_id)
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
            "performance": {},
            "circuit_breaker": {},
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

        last_order_error = bot.get('last_order_error')
        if last_order_error:
            diagnostics['reasons'].append(f"Last order error: {last_order_error}")

        # ------------------------------------------------------------------
        # Performance / drawdown / circuit-breaker diagnostics
        # ------------------------------------------------------------------
        today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        current_capital = float(bot.get('current_capital') or 0)
        equity_peak = float(bot.get('equity_peak') or current_capital)
        if equity_peak <= 0:
            equity_peak = current_capital

        # Drawdown from equity_peak
        if equity_peak > 0:
            computed_drawdown_pct = max(0.0, (equity_peak - current_capital) / equity_peak * 100)
        else:
            computed_drawdown_pct = 0.0

        # Daily baseline circuit breaker check
        stored_baseline_date = bot.get('daily_baseline_date')
        stored_baseline = float(bot.get('daily_capital_baseline') or 0)
        circuit_breaker_loss_pct = float(bot.get('circuit_breaker_loss_pct', 0.10))
        max_drawdown_pct_limit = float(bot.get('max_drawdown_pct', 0.15))

        if (
            not stored_baseline_date
            or stored_baseline_date != today_str
            or stored_baseline <= 0
        ):
            # Baseline is stale — would be initialized on next tick
            daily_pnl_pct = 0.0
            baseline_status = "stale_will_init_on_next_tick"
        else:
            if stored_baseline > 0:
                daily_pnl_pct = (current_capital - stored_baseline) / stored_baseline
            else:
                daily_pnl_pct = 0.0
            baseline_status = "current"

        cb_would_trip = daily_pnl_pct < -circuit_breaker_loss_pct
        dd_would_trip = (computed_drawdown_pct / 100) > max_drawdown_pct_limit

        diagnostics['performance'] = {
            "current_equity": round(current_capital, 2),
            "equity_peak": round(equity_peak, 2),
            "computed_drawdown_pct": round(computed_drawdown_pct, 2),
            "daily_capital_baseline": round(stored_baseline, 2),
            "daily_baseline_date": stored_baseline_date,
            "baseline_status": baseline_status,
            "daily_pnl_pct": round(daily_pnl_pct * 100, 2),
        }

        diagnostics['circuit_breaker'] = {
            "daily_loss_limit_pct": round(circuit_breaker_loss_pct * 100, 2),
            "max_drawdown_limit_pct": round(max_drawdown_pct_limit * 100, 2),
            "would_trip_daily_loss": cb_would_trip,
            "would_trip_max_drawdown": dd_would_trip,
            "last_order_error": last_order_error,
            "next_action": (
                "Reset daily baseline via paper reset or wait for new day"
                if cb_would_trip else
                f"Reset drawdown baseline via /api/admin/bots/{bot_id}/reset-locks"
                if dd_would_trip else
                "No circuit breaker issues"
            ),
        }

        if cb_would_trip:
            diagnostics['reasons'].append(
                f"Circuit breaker: daily loss {daily_pnl_pct*100:.1f}% exceeds limit "
                f"{circuit_breaker_loss_pct*100:.0f}%. "
                "Next action: reset daily baseline via paper reset."
            )
        if dd_would_trip:
            diagnostics['reasons'].append(
                f"Max drawdown {computed_drawdown_pct:.1f}% exceeds limit "
                f"{max_drawdown_pct_limit*100:.0f}%. "
                "Next action: reset drawdown baseline via admin reset-locks."
            )

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
            "current_capital": current_capital,
            "total_profit": bot.get('total_profit', 0),
            "win_rate": bot.get('win_rate', 0)
        }

        # Determine if bot can trade
        diagnostics['can_trade'] = (
            bot.get('status') == 'active' and
            not emergency_stop and
            not bot.get('paused_by_bodyguard') and
            not bot.get('paused_by_system') and
            can_trade_budget and
            not cb_would_trip and
            not dd_would_trip
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


# ============================================================================
# Seed 5 Luno Paper Bots (Gbot1..Gbot5)
# ============================================================================

_GBOT_DEFINITIONS = [
    {"name": "Gbot1", "risk_mode": "safe"},
    {"name": "Gbot2", "risk_mode": "safe"},
    {"name": "Gbot3", "risk_mode": "balanced"},
    {"name": "Gbot4", "risk_mode": "balanced"},
    {"name": "Gbot5", "risk_mode": "aggressive"},
]


@router.post("/seed-luno-paper")
async def seed_luno_paper_bots(user_id: str = Depends(get_current_user)):
    """
    Seed 5 standard Luno paper-trading bots (Gbot1..Gbot5).

    - Paper mode only; returns 400 if live trading is active.
    - Idempotent: skips bots that already exist (same name + exchange + trading_mode).
    - Enforces MAX 5 bots: returns 409 if user already has >5 non-deleted luno paper bots.
    - Does NOT pre-allocate wallet capital; funds are deducted only when a trade opens.
    - Returns a JSON summary with bot IDs and created/existing status.
    """
    from uuid import uuid4
    from services.paper_wallet_service import paper_wallet_service
    from config import PAPER_STARTING_CAPITAL_ZAR

    try:
        # Guard: paper mode only
        from routes.system_mode import get_system_mode
        mode = await get_system_mode(user_id)
        if mode.get("liveTrading"):
            raise HTTPException(
                status_code=400,
                detail="Seeding paper bots is only allowed when live trading is OFF."
            )

        _luno_paper_filter = {
            "user_id": user_id,
            "exchange": "luno",
            "trading_mode": "paper",
            "deleted_at": {"$exists": False},
        }

        # Guard: enforce MAX 5 bots
        total_existing_count = await db.bots_collection.count_documents(_luno_paper_filter)
        if total_existing_count > 5:
            existing_bots = await db.bots_collection.find(
                _luno_paper_filter,
                {"_id": 0, "id": 1, "name": 1, "status": 1},
            ).to_list(None)
            raise HTTPException(
                status_code=409,
                detail={
                    "error": "bot_limit_exceeded",
                    "message": (
                        f"User already has {total_existing_count} Luno paper bots "
                        f"(max 5). No new bots created."
                    ),
                    "count": total_existing_count,
                    "bots": existing_bots,
                },
            )

        # Determine per-bot capital (canonical: R1000 ZAR per Luno bot; capped to 1/5 of
        # available funds so newly seeded bots get a realistic but non-zero stake).
        # Capital is recorded on the bot doc only — the wallet is NOT debited until a
        # trade actually opens (on-demand allocation model).
        wallet = await paper_wallet_service.get_balances(user_id)
        available_zar = float(wallet.get("balances", {}).get("ZAR", 0))
        starting = float(PAPER_STARTING_CAPITAL_ZAR)

        # If the paper wallet is unfunded (balance is 0), auto-initialise it with
        # PAPER_STARTING_CAPITAL_ZAR.  This mirrors what the dashboard does when the
        # user clicks "Add Funds" for the first time, ensuring the seed endpoint works
        # out-of-the-box in the same way the UI does.
        if available_zar == 0 and starting > 0:
            try:
                await paper_wallet_service.fund(user_id, starting, "ZAR")
                available_zar = starting
            except Exception as _fund_err:
                logger.warning(f"Auto-fund paper wallet failed for user {user_id}: {_fund_err}")

        # Each bot gets 1/5 of starting capital (min R1000 ZAR, max starting/5).
        # This is a notional book-capital for sizing trades, NOT a wallet deduction.
        per_bot_capital = max(1000.0, min(available_zar / 5.0, starting / 5.0))

        results = []
        now_iso = datetime.now(timezone.utc).isoformat()

        for bot_def in _GBOT_DEFINITIONS:
            name = bot_def["name"]
            risk_mode = bot_def["risk_mode"]

            # Check if already exists (non-deleted)
            existing_doc = await db.bots_collection.find_one(
                {
                    "user_id": user_id,
                    "name": name,
                    "exchange": "luno",
                    "trading_mode": "paper",
                    "deleted_at": {"$exists": False},
                },
                {"_id": 0, "id": 1, "name": 1, "status": 1},
            )
            if existing_doc:
                results.append(
                    {"name": name, "bot_id": existing_doc["id"], "status": "existing"}
                )
                continue

            bot_id = str(uuid4())

            # On-demand allocation: do NOT call paper_wallet_ledger.reserve_funds() here.
            # Capital is deducted from the wallet only when a trade actually opens
            # (paper_trading_engine.py: paper_wallet_service.reserve_funds on entry).

            bot_doc = {
                "id": bot_id,
                "user_id": user_id,
                "name": name,
                "status": "active",
                "exchange": "luno",
                "pair": "BTC/ZAR",
                "risk_mode": risk_mode,
                "initial_capital": per_bot_capital,
                "starting_capital": per_bot_capital,
                "current_capital": per_bot_capital,
                "peak_capital": per_bot_capital,
                "allocated_capital": per_bot_capital,
                "mode": "paper",
                "trading_mode": "paper",
                "trades_count": 0,
                "daily_trade_count": 0,
                "last_trade_time": None,
                "win_count": 0,
                "loss_count": 0,
                "total_profit": 0,
                "created_at": now_iso,
                "paper_start_date": now_iso,
                "paper_end_eligible_at": (
                    datetime.now(timezone.utc) + timedelta(days=7)
                ).isoformat(),
                "learning_complete": False,
                # Paper bots are never gated by training — they trade freely immediately.
                "training_complete": True,
                "training_in_progress": False,
                "seeded": True,
                "deleted_at": None,  # Explicit null so partial index uidx_bot_identity covers this bot
            }

            await db.bots_collection.insert_one(bot_doc)
            logger.info(
                f"Seeded Luno paper bot: {name} id={bot_id} capital={per_bot_capital} "
                f"risk={risk_mode} user={user_id[:8]}"
            )
            results.append(
                {"name": name, "bot_id": bot_id, "status": "created", "capital": per_bot_capital}
            )

        created = [r for r in results if r["status"] == "created"]
        existing = [r for r in results if r["status"] == "existing"]
        skipped = [r for r in results if r["status"] == "skipped"]

        return {
            "success": True,
            "created": len(created),
            "existing": len(existing),
            "skipped": len(skipped),
            "bots": results,
            "timestamp": now_iso,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Seed Luno paper bots error")
        raise HTTPException(status_code=500, detail=str(e))



