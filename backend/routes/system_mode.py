"""
System Mode Router - Paper vs Live mode management
Enforces exclusivity and provides single source of truth
"""

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional
import logging
from datetime import datetime, timezone, timedelta
from collections import defaultdict
import hmac
import os

from auth import get_current_user, is_admin
import database as db
from realtime_events import rt_events
from websocket_manager import manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/system", tags=["System Mode"])
PAPER_RESET_MAX_ATTEMPTS = 5
PAPER_RESET_WINDOW = timedelta(minutes=1)
paper_reset_attempts = defaultdict(lambda: {"count": 0, "reset_at": datetime.now(timezone.utc)})


def get_paper_reset_password() -> str:
    reset_password = os.getenv("PAPER_RESET_PASSWORD")
    if not reset_password:
        raise HTTPException(status_code=500, detail="Paper reset password not configured")
    return reset_password


def is_paper_reset_password_valid(candidate: str) -> bool:
    reset_password = get_paper_reset_password()
    return hmac.compare_digest(str(candidate or ""), reset_password)


def check_paper_reset_attempts(user_id: str) -> tuple[bool, int]:
    now = datetime.now(timezone.utc)
    attempts = paper_reset_attempts[user_id]
    if now - attempts["reset_at"] > PAPER_RESET_WINDOW:
        attempts["count"] = 0
        attempts["reset_at"] = now
    if attempts["count"] >= PAPER_RESET_MAX_ATTEMPTS:
        remaining = PAPER_RESET_WINDOW - (now - attempts["reset_at"])
        return False, max(1, int(remaining.total_seconds()))
    attempts["count"] += 1
    return True, 0


def reset_paper_reset_attempts(user_id: str) -> None:
    if user_id in paper_reset_attempts:
        paper_reset_attempts.pop(user_id, None)


def live_trading_enabled() -> bool:
    return os.getenv("ENABLE_LIVE_TRADING", "false").lower() == "true"


class SystemMode(BaseModel):
    """System-wide mode configuration"""
    paperTrading: bool
    liveTrading: bool
    autopilot: bool


class ModeSwitchRequest(BaseModel):
    """Request to switch system mode"""
    mode: str  # 'paper', 'live', or 'autopilot'
    confirmation_token: Optional[str] = None  # Required for switching to live


async def get_system_mode(user_id: str = None) -> dict:
    """Get current system mode from database
    
    Args:
        user_id: Optional user ID for per-user mode (if None, returns global mode)
    
    Returns default mode if not set: paper=True, live=False, autopilot=False
    """
    # Use per-user mode if user_id provided, otherwise global singleton
    query = {"user_id": user_id} if user_id else {}
    mode_doc = await db.system_modes_collection.find_one(query, {"_id": 0})
    
    if not mode_doc:
        # Initialize with safe defaults
        default_mode = {
            "paperTrading": True,
            "liveTrading": False,
            "autopilot": False,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "updated_by": user_id or "system"
        }
        if user_id:
            default_mode["user_id"] = user_id
        await db.system_modes_collection.insert_one(default_mode)
        return default_mode
    
    return mode_doc


async def set_system_mode(mode: str, user_id: str) -> dict:
    """Set system mode with exclusivity enforcement
    
    Args:
        mode: 'paper', 'live', or 'autopilot'
        user_id: User making the change
        
    Returns:
        Updated mode document
    """
    # Determine new state based on requested mode
    if mode == "paper":
        new_state = {
            "paperTrading": True,
            "liveTrading": False,
            "autopilot": False
        }
    elif mode == "live":
        new_state = {
            "paperTrading": False,
            "liveTrading": True,
            "autopilot": False
        }
    elif mode == "autopilot":
        new_state = {
            "paperTrading": False,
            "liveTrading": False,
            "autopilot": True
        }
    else:
        raise ValueError(f"Invalid mode: {mode}. Must be 'paper', 'live', or 'autopilot'")
    
    # Update with timestamp and user_id
    new_state["updated_at"] = datetime.now(timezone.utc).isoformat()
    new_state["updated_by"] = user_id
    new_state["user_id"] = user_id
    
    # Upsert mode document per user
    await db.system_modes_collection.update_one(
        {"user_id": user_id},
        {"$set": new_state},
        upsert=True
    )
    
    logger.info(f"📊 System mode switched to {mode.upper()} by user {user_id[:8]}")
    
    return new_state


async def check_luno_balance(user_id: str) -> tuple[bool, float]:
    """Check if user has sufficient Luno balance for live trading
    
    Args:
        user_id: User ID
        
    Returns:
        (has_sufficient_balance: bool, current_balance: float)
    """
    try:
        # Get Luno API keys for user
        luno_key = await db.api_keys_collection.find_one({
            "user_id": user_id,
            "provider": "luno"
        })
        
        if not luno_key:
            return False, 0.0
        
        # Check if keys are tested
        if not luno_key.get("last_test_ok"):
            return False, 0.0
        
        # Try to get balance from ccxt_service
        try:
            from ccxt_service import ccxt_service
            from routes.api_key_management import decrypt_api_key
            
            # Get decrypted keys
            api_key = decrypt_api_key(luno_key["api_key_encrypted"])
            api_secret = decrypt_api_key(luno_key["api_secret_encrypted"]) if luno_key.get("api_secret_encrypted") else None
            
            # Initialize Luno exchange
            exchange = await ccxt_service.get_exchange_instance(
                "luno",
                api_key,
                api_secret
            )
            
            if exchange:
                balance = await exchange.fetch_balance()
                # Get ZAR balance
                zar_balance = balance.get('ZAR', {}).get('free', 0.0)
                
                # Require minimum R500 for live trading
                MIN_LUNO_BALANCE = 500.0
                
                return zar_balance >= MIN_LUNO_BALANCE, zar_balance
            
        except Exception as e:
            logger.error(f"Error fetching Luno balance: {e}")
            return False, 0.0
        
        return False, 0.0
        
    except Exception as e:
        logger.error(f"Check Luno balance error: {e}")
        return False, 0.0


async def revert_to_paper_and_notify(user_id: str, reason: str):
    """Revert user to paper trading and send email notification
    
    Args:
        user_id: User ID
        reason: Reason for reversion
    """
    try:
        # Update system mode to paper
        await db.system_modes_collection.update_one(
            {"user_id": user_id},
            {
                "$set": {
                    "paperTrading": True,
                    "liveTrading": False,
                    "reverted_at": datetime.now(timezone.utc).isoformat(),
                    "revert_reason": reason
                }
            },
            upsert=True
        )
        
        # Get user email
        user = await db.users_collection.find_one({"id": user_id})
        if user and user.get('email'):
            from email_service import email_service
            
            # Send notification email
            if "Luno" in reason or "deposit" in reason.lower():
                await email_service.send_luno_deposit_required(user['email'])
            else:
                await email_service.send_live_mode_reverted(user['email'], reason)
        
        logger.warning(f"User {user_id[:8]} reverted to paper trading: {reason}")
        
    except Exception as e:
        logger.error(f"Revert to paper error: {e}")


async def check_live_readiness(user_id: str = None) -> tuple[bool, list[str]]:
    """Check if system/user is ready for live trading
    
    Args:
        user_id: Optional user ID to check user-specific requirements
    
    Returns:
        (ready: bool, errors: list[str])
    """
    errors = []
    
    # User-specific checks if user_id provided
    if user_id:
        from routes.live_trading_gate import check_user_live_eligibility
        
        # Check 7-day paper trading requirement and criteria
        eligibility = await check_user_live_eligibility(user_id)
        
        if not eligibility['eligible']:
            errors.extend(eligibility.get('reasons', ['Live trading requirements not met']))

        from services.wallet_summary_service import wallet_summary_service
        summary = await wallet_summary_service.get_summary(user_id)
        if summary.get("shortfall_zar", 0) > 0:
            errors.append(f"Wallet shortfall R{summary.get('shortfall_zar'):.2f}")
    
    # Check 1: At least one exchange key configured and tested
    query = {"provider": {"$in": ["luno", "binance", "kucoin", "bybit", "kraken", "bitget", "gate"]}}
    if user_id:
        query["user_id"] = user_id
    
    keys_cursor = db.api_keys_collection.find(query, {"_id": 0})
    exchange_keys = await keys_cursor.to_list(100)
    
    tested_keys = [k for k in exchange_keys if k.get("last_test_ok") is True]
    
    if not tested_keys:
        errors.append("No exchange API keys tested successfully. At least one exchange must be configured.")
    
    # Check 2: No active runtime errors (check recent trades for errors)
    trade_query = {"status": "error"}
    if user_id:
        trade_query["user_id"] = user_id
    
    recent_trades = await db.trades_collection.find(
        trade_query,
        {"_id": 0}
    ).sort("timestamp", -1).limit(10).to_list(10)
    
    if len(recent_trades) > 5:
        errors.append(f"High error rate: {len(recent_trades)} failed trades recently")
    
    # Check 3: System health check
    try:
        # Verify database connection
        await db.db.command("ping")
    except Exception as e:
        errors.append(f"Database connectivity issue: {str(e)}")
    
    return (len(errors) == 0, errors)


@router.get("/mode")
async def get_mode(user_id: str = Depends(get_current_user)):
    """Get current system mode
    
    Returns:
        Current mode configuration with paper/live/autopilot flags
    """
    try:
        mode = await get_system_mode(user_id)
        
        # Determine active mode string
        if mode.get("paperTrading"):
            active_mode = "paper"
        elif mode.get("liveTrading"):
            active_mode = "live"
        elif mode.get("autopilot"):
            active_mode = "autopilot"
        else:
            active_mode = "unknown"
        
        return {
            "success": True,
            "mode": active_mode,
            "paperTrading": mode.get("paperTrading", False),
            "liveTrading": mode.get("liveTrading", False),
            "autopilot": mode.get("autopilot", False),
            "updated_at": mode.get("updated_at"),
            "updated_by": mode.get("updated_by")
        }
        
    except Exception as e:
        logger.error(f"Get mode error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class ModeToggleRequest(BaseModel):
    """Request to toggle a specific mode on/off"""
    mode: str  # 'paperTrading', 'liveTrading', or 'autopilot'
    enabled: bool
    confirmation_token: Optional[str] = None


class PaperResetRequest(BaseModel):
    """Request to reset paper trading data"""
    password: Optional[str] = None


async def perform_paper_reset(user_id: str) -> dict:
    """Clear paper trading data for a user and return deletion summaries.

    This is the CANONICAL reset path.  Every admin/user reset endpoint must
    call this function so that all resets are guaranteed to cover:
    - bots (hard-delete so ghost bots never pollute truth/admin/radar after reset)
    - trades, orders, positions
    - fills / ledger / paper_ledger
    - wallet_balances / wallets
    - profits / metrics caches
    - bodyguard, daily-loss-lock, circuit-breaker, quarantine flags
    - any stale pause_reason / last_order_error carryover

    PRESERVED (never deleted by paper reset — omit from all deletion lists below):
    - user account / profile
    - api_keys (exchange credentials)
    - strategy_versions (durable learned strategy parameters — carry over resets;
      preserved by NOT including this collection in the deletion loops below)
    - user_memory (AI assistant context and user preferences — carry over resets;
      preserved by NOT including this collection in the deletion loops below)
    """
    # Canonical timestamp for this reset operation — used throughout this function
    # for audit log, user-doc updates, and the return payload.
    delete_timestamp = datetime.now(timezone.utc).isoformat()

    summary = {
        "bots_deleted": 0,
        "trades_deleted": 0,
        "orders_deleted": 0,
        "positions_deleted": 0,
        "metrics_deleted": 0,
        "learning_deleted": 0,
        "decisions_deleted": 0,
        "wallet_reset": False,
        "chat_cleared": 0
    }
    collection_counts = {"bots": 0, "paper_wallet": 0}

    # Collect ALL bot IDs for this user — including already-deleted ones —
    # so that runtime-state rows and linked records for ghost bots are
    # cleaned up too (fixes stale runtime_state drift after partial resets).
    all_bots = await db.bots_collection.find(
        {"user_id": user_id},
        {"_id": 0, "id": 1}
    ).to_list(1000)
    all_bot_ids = [bot.get("id") for bot in all_bots if bot.get("id")]

    # Hard-delete ALL bots for this user (not soft-delete) so that ghost bots
    # cannot pollute truth console / admin / radar / fleet after the reset.
    if all_bot_ids:
        bot_result = await db.bots_collection.delete_many(
            {"user_id": user_id}
        )
        summary["bots_deleted"] = bot_result.deleted_count
        collection_counts["bots"] = bot_result.deleted_count

    bot_linked = [
        ("trades", "trades_deleted", db.trades_collection),
        ("orders", "orders_deleted", db.orders_collection),
        ("positions", "positions_deleted", db.positions_collection),
    ]
    # Use all_bot_ids (includes already-deleted bots) so ghost trade records
    # from prior partial resets are also cleaned up.
    for name, summary_key, collection in bot_linked:
        collection_counts[name] = 0
        if collection is None or not all_bot_ids:
            continue
        result = await collection.delete_many({"bot_id": {"$in": all_bot_ids}})
        summary[summary_key] = result.deleted_count
        collection_counts[name] = result.deleted_count

    user_collections = [
        ("performance_metrics", "metrics_deleted", db.performance_metrics_collection),
        ("balance_snapshots", "metrics_deleted", db.balance_snapshots_collection),
        ("bot_metrics", "metrics_deleted", db.bot_metrics_collection),
        ("bot_runtime_state", "metrics_deleted", db.bot_runtime_state_collection),
        ("bot_lifecycle", "metrics_deleted", db.bot_lifecycle_collection),
        ("wallet_balances", "metrics_deleted", db.wallet_balances_collection),
        ("wallets", "metrics_deleted", db.wallets_collection),
        ("ledger", "metrics_deleted", db.ledger_collection),
        ("capital_injections", "metrics_deleted", db.capital_injections_collection),
        ("funding_plans", "metrics_deleted", db.funding_plans_collection),
        ("wallet_transfers", "metrics_deleted", db.wallet_transfers_collection),
        ("transfer_jobs", "metrics_deleted", db.transfer_jobs_collection),
        ("transfers_ledger", "metrics_deleted", db.transfers_ledger_collection),
        ("training_jobs", "learning_deleted", db.training_jobs_collection),
        ("learning_data", "learning_deleted", db.learning_data_collection),
        ("learning_logs", "learning_deleted", db.learning_logs_collection),
        ("learning_runs", "learning_deleted", db.learning_runs_collection),
        ("learning_changes", "learning_deleted", db.learning_changes_collection),
        ("learning_metrics", "learning_deleted", db.learning_metrics_collection),
        # strategy_versions is PRESERVED — durable learned strategy parameters survive paper resets
        # user_memory is PRESERVED — AI assistant context and user preferences survive paper resets
        ("bot_strategy_assignments", "learning_deleted", db.bot_strategy_assignments_collection),
        ("decisions", "decisions_deleted", db.decisions_collection),
        ("autopilot_actions", "decisions_deleted", db.autopilot_actions_collection),
        ("autopilot_milestones", "decisions_deleted", db.autopilot_milestones_collection),
        ("autopilot_reinvest_events", "decisions_deleted", db.autopilot_reinvest_events_collection),
        ("action_audit_log", "decisions_deleted", db.action_audit_log_collection),
        ("profits", "metrics_deleted", db.profits_collection),
        ("profit_ledger", "metrics_deleted", db.profit_ledger_collection),
        ("reinvest_requests", "metrics_deleted", db.reinvest_requests_collection),
        ("user_countdowns", "metrics_deleted", db.user_countdowns_collection),
        # user_memory is PRESERVED — AI assistant context and user preferences survive paper resets
        ("reports", "metrics_deleted", db.reports_collection),
        ("notifications", "metrics_deleted", db.notifications_collection),
        ("paper_ledger", "metrics_deleted", db.paper_ledger_collection),
        ("chat_messages", "chat_cleared", db.chat_messages_collection),
        ("chatops_actions", "chat_cleared", db.chatops_actions_collection),
        ("chatops_confirmations", "chat_cleared", db.chatops_confirmations_collection),
    ]
    for name, summary_key, collection in user_collections:
        collection_counts[name] = 0
        if collection is None:
            continue
        result = await collection.delete_many({"user_id": user_id})
        summary[summary_key] += result.deleted_count
        collection_counts[name] = result.deleted_count

    # Clear fills_ledger (used by circuit-breaker drawdown + daily-PnL calculations)
    try:
        if db.db is not None:
            fills_result = await db.db["fills_ledger"].delete_many({"user_id": user_id})
            summary["metrics_deleted"] += fills_result.deleted_count
            collection_counts["fills_ledger"] = fills_result.deleted_count
            # Also clear bot-level fills for bots belonging to this user
            if all_bot_ids:
                bot_fills = await db.db["fills_ledger"].delete_many({"bot_id": {"$in": all_bot_ids}})
                summary["metrics_deleted"] += bot_fills.deleted_count

            # Clear stale circuit-breaker state so fresh paper session starts unblocked
            cb_result = await db.db["circuit_breaker_state"].update_many(
                {"entity_id": {"$in": all_bot_ids}} if all_bot_ids else {"entity_id": user_id},
                {"$set": {"reset_at": datetime.now(timezone.utc), "reset_reason": "paper_reset"}},
            )
            collection_counts["circuit_breaker_state"] = cb_result.modified_count
            # Also reset user-level circuit breaker
            await db.db["circuit_breaker_state"].update_many(
                {"entity_id": user_id, "entity_type": "user"},
                {"$set": {"reset_at": datetime.now(timezone.utc), "reset_reason": "paper_reset"}},
            )
            # Clear ledger events for this user
            await db.db["ledger_events"].delete_many({"user_id": user_id})
    except Exception as e:
        logger.warning(f"Fills/circuit-breaker reset failed: {e}")
        collection_counts["fills_ledger"] = 0

    try:
        from services.paper_wallet_service import paper_wallet_service
        await paper_wallet_service.reset(user_id)
        summary["wallet_reset"] = True
        collection_counts["paper_wallet"] = 1
    except Exception as e:
        logger.warning(f"Paper wallet reset failed: {e}")
        collection_counts["paper_wallet"] = 0

    await db.users_collection.update_one(
        {"id": user_id},
        {
            "$set": {
                "daily_loss_lock_active": False,
                "daily_loss_lock_reset_at": delete_timestamp,
                "daily_loss_lock_reset_by": user_id,
                "emergency_stop": False
            },
            "$unset": {
                "daily_loss_locked_at": "",
                "daily_loss_locked_reason": "",
                "daily_loss_pct": "",
                "daily_loss_day_key": ""
            }
        }
    )

    await db.system_modes_collection.update_one(
        {"user_id": user_id},
        {"$set": {"paperTrading": True, "liveTrading": False, "autopilot": False}},
        upsert=True
    )

    # Clear any global_disabled state that was set by a reset operation.
    # If the emergency_stop admin_overrides document has global_disabled=true with
    # global_reason containing "Reset" (case-insensitive), it was set by a prior
    # reset and must be cleared so paper trading is not permanently blocked.
    try:
        if db.emergency_stop_collection is not None:
            override_doc = await db.emergency_stop_collection.find_one(
                {"id": "admin_overrides"}, {"_id": 0}
            )
            if override_doc and override_doc.get("global_disabled"):
                reason = (override_doc.get("global_reason") or "").lower()
                if "reset" in reason or reason == "":
                    await db.emergency_stop_collection.update_one(
                        {"id": "admin_overrides"},
                        {
                            "$set": {
                                "global_disabled": False,
                                "global_reason": "cleared_by_paper_reset",
                                "global_updated_by": user_id,
                                "global_updated_at": delete_timestamp,
                            }
                        },
                        upsert=True,
                    )
                    collection_counts["emergency_stop_override_cleared"] = 1
                    logger.info(
                        "Paper reset cleared global_disabled=true in admin_overrides "
                        "(reason was: %r)", override_doc.get("global_reason")
                    )
    except Exception as e:
        logger.warning(f"Emergency stop override clear failed during paper reset: {e}")

    try:
        await db.audit_logs_collection.insert_one({
            "user_id": user_id,
            "action": "paper_reset",
            "timestamp": delete_timestamp,
            "details": summary
        })
    except Exception as e:
        logger.warning(f"Paper reset audit log failed: {e}")

    await manager.send_message(user_id, {
        "type": "paper_reset",
        "message": "Paper trading data reset completed."
    })
    try:
        from engines.trade_staggerer import trade_staggerer
        await trade_staggerer.clear_user(user_id)
        await trade_staggerer.purge_orphaned_queue()
    except Exception as e:
        logger.warning(f"Paper reset queue cleanup failed: {e}")
    await rt_events.force_refresh(user_id, reason="Paper trading reset completed.")

    return {
        "summary": summary,
        "collection_counts": collection_counts,
        "timestamp": delete_timestamp
    }


@router.post("/paper-reset/validate")
async def validate_paper_reset(
    request: PaperResetRequest,
    user_id: str = Depends(get_current_user)
):
    current_mode = await get_system_mode(user_id)
    if not current_mode.get("paperTrading") or current_mode.get("liveTrading"):
        return {"valid": False, "reason": "Paper reset is only available in paper mode."}
    allowed, retry_after = check_paper_reset_attempts(user_id)
    if not allowed:
        return {"valid": False, "reason": f"Too many attempts. Try again in {retry_after}s."}
    is_valid = is_paper_reset_password_valid(request.password)
    if is_valid:
        reset_paper_reset_attempts(user_id)
    return {"valid": is_valid}


@router.put("/mode")
async def toggle_mode(
    data: ModeToggleRequest,
    user_id: str = Depends(get_current_user)
):
    """Toggle a specific mode on or off (used by frontend toggles)
    
    This endpoint provides a simpler interface for the frontend toggle switches.
    Paper and live modes are mutually exclusive.
    
    Args:
        data: Mode toggle request with mode name and enabled state
        user_id: Current user ID
        
    Returns:
        Updated mode configuration
    """
    try:
        mode_name = data.mode
        enabled = data.enabled
        
        # Get current state
        current_mode = await get_system_mode(user_id)
        
        # Determine new state based on toggle
        new_state = {
            "paperTrading": current_mode.get("paperTrading", False),
            "liveTrading": current_mode.get("liveTrading", False),
            "autopilot": current_mode.get("autopilot", False)
        }
        
        # Apply the toggle
        if mode_name == "paperTrading":
            new_state["paperTrading"] = enabled
            if enabled:
                new_state["liveTrading"] = False  # Mutually exclusive
        elif mode_name == "liveTrading":
            new_state["liveTrading"] = enabled
            if enabled:
                if not live_trading_enabled():
                    raise HTTPException(
                        status_code=403,
                        detail="Live trading is globally disabled. Set ENABLE_LIVE_TRADING=true"
                    )
                if data.confirmation_token != "CONFIRM_LIVE_TRADING":
                    raise HTTPException(
                        status_code=400,
                        detail="Confirmation token required to enable live trading"
                    )
                new_state["paperTrading"] = False  # Mutually exclusive
                # Check readiness for live trading (including 7-day requirement)
                ready, errors = await check_live_readiness(user_id)
                if not ready:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Cannot enable live trading: {'; '.join(errors)}"
                    )
                from services.wallet_summary_service import wallet_summary_service
                summary = await wallet_summary_service.get_summary(user_id)
                if summary.get("shortfall_zar", 0) > 0:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Wallet shortfall R{summary.get('shortfall_zar'):.2f}. Fund wallet before going live."
                    )
                
                # Check Luno balance (primary fiat on-ramp)
                has_balance, zar_balance = await check_luno_balance(user_id)
                if not has_balance:
                    # Revert to paper and notify user
                    await revert_to_paper_and_notify(
                        user_id,
                        f"Insufficient Luno balance (R{zar_balance:.2f}). Minimum R500 required."
                    )
                    raise HTTPException(
                        status_code=400,
                        detail=f"Insufficient Luno balance: R{zar_balance:.2f}. Please deposit funds. Email sent with instructions."
                    )
        elif mode_name == "autopilot":
            new_state["autopilot"] = enabled
            # Sync user.autopilot_enabled so guardrails (growth/reinvest) reflect the same state
            try:
                await db.users_collection.update_one(
                    {"id": user_id},
                    {"$set": {"autopilot_enabled": enabled}}
                )
            except Exception as _e:
                logger.warning(f"Failed to sync user.autopilot_enabled: {_e}")
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid mode: {mode_name}"
            )
        
        # Update with timestamp and user_id
        new_state["updated_at"] = datetime.now(timezone.utc).isoformat()
        new_state["updated_by"] = user_id
        new_state["user_id"] = user_id
        
        # Persist to database per user
        await db.system_modes_collection.update_one(
            {"user_id": user_id},
            {"$set": new_state},
            upsert=True
        )
        
        logger.info(f"📊 Mode {mode_name} toggled to {enabled} by user {user_id[:8]}")
        
        # Emit realtime event
        try:
            await rt_events.mode_switched(user_id, mode_name, new_state)
        except Exception as e:
            logger.warning(f"Failed to emit mode_switched event: {e}")
        
        return {
            "success": True,
            "message": f"{mode_name} {'enabled' if enabled else 'disabled'}",
            "paperTrading": new_state["paperTrading"],
            "liveTrading": new_state["liveTrading"],
            "autopilot": new_state["autopilot"],
            "updated_at": new_state["updated_at"]
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Toggle mode error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/paper-reset")
async def paper_reset(
    request: PaperResetRequest,
    user_id: str = Depends(get_current_user)
):
    """Reset all paper trading data for the authenticated user."""
    try:
        current_mode = await get_system_mode(user_id)
        if not current_mode.get("paperTrading") or current_mode.get("liveTrading"):
            raise HTTPException(
                status_code=400,
                detail="Paper reset is only available in paper mode with live trading disabled."
            )

        result = await perform_paper_reset(user_id)
        return {
            "success": True,
            "message": "Paper trading reset completed.",
            **result
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Paper reset error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/reset-paper")
async def reset_paper_trading(
    request: PaperResetRequest,
    user_id: str = Depends(get_current_user)
):
    """Legacy paper reset endpoint (password via PAPER_RESET_PASSWORD env)."""
    try:
        allowed, retry_after = check_paper_reset_attempts(user_id)
        if not allowed:
            raise HTTPException(status_code=429, detail=f"Too many attempts. Try again in {retry_after}s.")
        if not is_paper_reset_password_valid(request.password):
            raise HTTPException(status_code=403, detail="Invalid reset password")
        reset_paper_reset_attempts(user_id)

        current_mode = await get_system_mode(user_id)
        if not current_mode.get("paperTrading") or current_mode.get("liveTrading"):
            raise HTTPException(
                status_code=400,
                detail="Paper reset is only available in paper mode with live trading disabled."
            )

        result = await perform_paper_reset(user_id)
        return {
            "success": True,
            "message": "Paper trading reset completed.",
            **result
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Paper reset error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/mode/switch")
async def switch_mode(
    data: ModeSwitchRequest,
    user_id: str = Depends(get_current_user)
):
    """Switch system mode
    
    Switching to live mode requires:
    - Admin privileges
    - Confirmation token
    - Readiness checks to pass
    
    Args:
        data: Mode switch request with mode and confirmation token
        user_id: Current user ID (extracted from JWT)
        
    Returns:
        New mode configuration
    """
    try:
        mode = data.mode.lower()
        
        if mode not in ["paper", "live", "autopilot"]:
            raise HTTPException(
                status_code=400,
                detail="Invalid mode. Must be 'paper', 'live', or 'autopilot'"
            )
        
        # Check admin for live/autopilot
        admin = await is_admin(user_id)
        if mode in ["live", "autopilot"] and not admin:
            raise HTTPException(
                status_code=403,
                detail="Admin privileges required to switch to live or autopilot mode"
            )
        
        # Switching to live requires confirmation token
        if mode == "live":
            if not live_trading_enabled():
                raise HTTPException(
                    status_code=403,
                    detail="Live trading is globally disabled. Set ENABLE_LIVE_TRADING=true"
                )
            if not data.confirmation_token:
                raise HTTPException(
                    status_code=400,
                    detail="Confirmation token required to switch to live mode"
                )
            
            # Validate confirmation token (simple check - in production use crypto)
            expected_token = "CONFIRM_LIVE_TRADING"
            if data.confirmation_token != expected_token:
                raise HTTPException(
                    status_code=400,
                    detail="Invalid confirmation token"
                )
            
            # Run readiness checks
            ready, readiness_errors = await check_live_readiness(user_id)
            
            if not ready:
                raise HTTPException(
                    status_code=400,
                    detail=f"System not ready for live trading: {'; '.join(readiness_errors)}"
                )
        
        # Get current mode
        current_mode = await get_system_mode(user_id)
        
        if current_mode.get("paperTrading") and mode == "paper":
            return {
                "success": True,
                "message": "Already in paper trading mode",
                "mode": "paper",
                "paperTrading": True,
                "liveTrading": False,
                "autopilot": False
            }
        
        if current_mode.get("liveTrading") and mode == "live":
            return {
                "success": True,
                "message": "Already in live trading mode",
                "mode": "live",
                "paperTrading": False,
                "liveTrading": True,
                "autopilot": False
            }
        
        # Perform mode switch
        new_mode = await set_system_mode(mode, user_id)
        
        # Emit realtime event
        try:
            await rt_events.mode_switched(user_id, mode, new_mode)
        except Exception as e:
            logger.warning(f"Failed to emit mode_switched event: {e}")
        
        return {
            "success": True,
            "message": f"Switched to {mode} mode",
            "mode": mode,
            "paperTrading": new_mode.get("paperTrading"),
            "liveTrading": new_mode.get("liveTrading"),
            "autopilot": new_mode.get("autopilot"),
            "updated_at": new_mode.get("updated_at")
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Switch mode error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/mode/readiness")
async def check_readiness(
    user_id: str = Depends(get_current_user)
):
    """Check if system is ready for live trading
    
    Returns:
        Readiness status with list of checks and any errors
    """
    try:
        admin = await is_admin(user_id)
        if not admin:
            raise HTTPException(
                status_code=403,
                detail="Admin privileges required to check readiness"
            )
        
        ready, errors = await check_live_readiness()
        
        return {
            "success": True,
            "ready": ready,
            "errors": errors,
            "checks_passed": len(errors) == 0
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Check readiness error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
