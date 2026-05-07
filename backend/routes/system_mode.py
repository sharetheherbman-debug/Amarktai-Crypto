"""
System Mode Router - Paper vs Live mode management
Enforces exclusivity and provides single source of truth
"""

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Any, Optional
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
PAPER_RESET_ACCEPTED_FIELDS = (
    "password",
    "resetPassword",
    "reset_password",
    "confirmation",
    "confirmation_phrase",
    "confirm",
)


def _load_paper_reset_password() -> str:
    reset_password = os.getenv("PAPER_RESET_PASSWORD")
    if not reset_password:
        env_path = "/etc/amarktai/amarktai.env"
        try:
            if os.path.exists(env_path):
                with open(env_path, "r", encoding="utf-8") as f:
                    for raw_line in f:
                        line = raw_line.strip()
                        if not line or line.startswith("#") or "=" not in line:
                            continue
                        key, value = line.split("=", 1)
                        if key.strip() == "PAPER_RESET_PASSWORD":
                            reset_password = value.strip().strip('"').strip("'")
                            break
        except Exception as e:
            logger.warning("Failed reading PAPER_RESET_PASSWORD from %s: %s", env_path, e)
    return str(reset_password or "").strip()


def get_paper_reset_password() -> str:
    reset_password = _load_paper_reset_password()
    if not reset_password:
        raise HTTPException(
            status_code=500,
            detail="Paper reset password not configured. Set PAPER_RESET_PASSWORD environment variable to enable runtime reset functionality."
        )
    return reset_password


def is_paper_reset_password_valid(candidate: str) -> tuple[bool, bool]:
    reset_password = _load_paper_reset_password()
    normalized_candidate = str(candidate or "").strip()
    if not reset_password:
        return False, False
    return hmac.compare_digest(normalized_candidate, reset_password), True


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
        
        # Determine active mode string (label only — never overwrite explicit user choice)
        if mode.get("paperTrading"):
            active_mode = "paper"
        elif mode.get("liveTrading"):
            active_mode = "live"
        elif mode.get("autopilot"):
            active_mode = "autopilot"
        else:
            # All flags are False: user explicitly disabled paper trading.
            # Return the actual state from the DB so the UI reflects reality.
            # (The get_system_mode() helper already handles the "no document" case
            # by inserting paperTrading=True defaults, so we never reach here on
            # first load — only when the user has deliberately turned everything off.)
            active_mode = "paper"
        
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


class ModeSetRequest(BaseModel):
    """Canonical request to set all mode flags at once.

    Accepted by POST /api/system/mode.  Maps the human-readable boolean
    fields to the internal storage flags (paperTrading / liveTrading / autopilot).

    Rules:
    - paper_trading and live_trading are mutually exclusive.
    - autonomous (autopilot) may coexist with paper_trading.
    """
    paper_trading: bool = False
    live_trading: bool = False
    autonomous: bool = False


class PaperResetRequest(BaseModel):
    """Request to reset paper trading data"""
    password: Optional[str] = None
    resetPassword: Optional[str] = None
    reset_password: Optional[str] = None
    confirmation: Optional[str] = None
    confirmation_phrase: Optional[str] = None
    confirm: Optional[str] = None


def _extract_reset_password(request: "PaperResetRequest") -> tuple[str, list[str]]:
    accepted_fields = [field for field in PAPER_RESET_ACCEPTED_FIELDS if getattr(request, field, None)]
    for field in PAPER_RESET_ACCEPTED_FIELDS:
        value = getattr(request, field, None)
        if value is not None and str(value).strip():
            return str(value).strip(), accepted_fields
    return "", accepted_fields


async def _paper_reset_debug_enabled(user_id: str) -> bool:
    env_name = (
        os.getenv("APP_ENV")
        or os.getenv("ENVIRONMENT")
        or os.getenv("NODE_ENV")
        or "development"
    ).strip().lower()
    if env_name != "production":
        return True
    try:
        return bool(await is_admin(user_id))
    except Exception:
        return False


async def _build_paper_reset_debug_payload(
    user_id: str,
    *,
    accepted_fields: list[str],
    password_configured: bool,
    reason: Optional[str] = None,
) -> dict[str, Any]:
    if not await _paper_reset_debug_enabled(user_id):
        return {}
    payload: dict[str, Any] = {
        "password_configured": password_configured,
        "accepted_fields": accepted_fields,
    }
    if reason:
        payload["reason"] = reason
    return payload


async def perform_paper_reset(user_id: str) -> dict:
    """Clear paper trading data for a user via the canonical orchestrator."""
    from services.paper_reset_orchestrator import run as run_paper_reset

    delete_timestamp = datetime.now(timezone.utc).isoformat()
    result = await run_paper_reset(user_id=user_id, scope="paper_only", also_reset_risk_locks=True)

    await db.system_modes_collection.update_one(
        {"user_id": user_id},
        {"$set": {"paperTrading": True, "liveTrading": False, "autopilot": False}},
        upsert=True,
    )

    try:
        await db.audit_logs_collection.insert_one({
            "user_id": user_id,
            "action": "paper_reset",
            "timestamp": delete_timestamp,
            "details": result,
        })
    except Exception as e:
        logger.warning(f"Paper reset audit log failed: {e}")

    await manager.send_message(user_id, {
        "type": "paper_reset",
        "message": "Paper trading data reset completed."
    })
    await rt_events.force_refresh(user_id, reason="Paper trading reset completed.")

    return {
        "summary": {
            "bots_deleted": result.get("bots_soft_deleted", 0),
            "open_trades_deleted": result.get("open_trades_deleted", 0),
            "fills_deleted": result.get("fills_deleted", 0),
            "trades_deleted": result.get("trades_deleted", 0),
            "runtime_deleted": result.get("runtime_deleted", 0),
            "risk_locks_cleared": result.get("risk_locks_reset", 0),
            "wallet_reset": result.get("wallet_reset", False),
        },
        "collection_counts": {
            "bots": result.get("bots_soft_deleted", 0),
            "paper_wallet": result.get("paper_balance", 0),
        },
        "post_reset": result.get("post_reset", {}),
        "invariant_warnings": result.get("warnings", []),
        "timestamp": delete_timestamp,
        "bots_deleted": result.get("bots_soft_deleted", 0),
        "open_trades_deleted": result.get("open_trades_deleted", 0),
        "fills_deleted": result.get("fills_deleted", 0),
        "trades_deleted": result.get("trades_deleted", 0),
        "runtime_deleted": result.get("runtime_deleted", 0),
        "risk_locks_cleared": result.get("risk_locks_reset", 0),
        "wallet_reset": result.get("wallet_reset", False),
        "wallet_available": result.get("wallet_available", 0),
        "paper_balance": result.get("paper_balance", 0),
        "remaining_paper_bots": result.get("remaining_paper_bots", 0),
        "remaining_open_paper_trades": result.get("remaining_open_paper_trades", 0),
        "remaining_paper_fills": result.get("remaining_paper_fills", 0),
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
    candidate, accepted_fields = _extract_reset_password(request)
    is_valid, password_configured = is_paper_reset_password_valid(candidate)
    reason = None
    if not password_configured:
        reason = "missing_password"
    elif not is_valid:
        reason = "wrong_password"
    if is_valid:
        reset_paper_reset_attempts(user_id)
    return {
        "valid": is_valid,
        **await _build_paper_reset_debug_payload(
            user_id,
            accepted_fields=accepted_fields,
            password_configured=password_configured,
            reason=reason,
        ),
    }


@router.post("/mode")
async def set_mode(
    data: ModeSetRequest,
    user_id: str = Depends(get_current_user)
):
    """Canonical API to set system mode from boolean flags.

    Intended for scripts and automation.  Accepts:
        {"paper_trading": true, "live_trading": false, "autonomous": true}

    Rules
    -----
    - paper_trading and live_trading are mutually exclusive.
    - autonomous may coexist with paper_trading (enables autopilot in paper mode).
    - live_trading is refused if ENABLE_LIVE_TRADING env flag is false.

    Returns the same shape as GET /api/system/mode.
    """
    if data.paper_trading and data.live_trading:
        raise HTTPException(
            status_code=400,
            detail="paper_trading and live_trading are mutually exclusive"
        )

    if data.live_trading and not live_trading_enabled():
        raise HTTPException(
            status_code=403,
            detail="Live trading is globally disabled. Set ENABLE_LIVE_TRADING=true"
        )

    new_state = {
        "paperTrading": data.paper_trading,
        "liveTrading": data.live_trading,
        "autopilot": data.autonomous,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "updated_by": user_id,
        "user_id": user_id,
    }

    await db.system_modes_collection.update_one(
        {"user_id": user_id},
        {"$set": new_state},
        upsert=True
    )

    if data.live_trading:
        effective_mode = "live"
    elif data.paper_trading:
        effective_mode = "paper"
    elif data.autonomous:
        effective_mode = "autopilot"
    else:
        effective_mode = "disabled"

    logger.info(
        f"📊 Mode set via POST /mode: paper={data.paper_trading} "
        f"live={data.live_trading} autonomous={data.autonomous} "
        f"by user {user_id[:8]}"
    )

    try:
        await rt_events.mode_switched(user_id, effective_mode, new_state)
    except Exception as e:
        logger.warning(f"Failed to emit mode_switched event: {e}")

    return {
        "success": True,
        "mode": effective_mode,
        "paperTrading": new_state["paperTrading"],
        "liveTrading": new_state["liveTrading"],
        "autopilot": new_state["autopilot"],
        "updated_at": new_state["updated_at"],
    }


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
        allowed, retry_after = check_paper_reset_attempts(user_id)
        if not allowed:
            raise HTTPException(status_code=429, detail=f"Too many attempts. Try again in {retry_after}s.")
        candidate, accepted_fields = _extract_reset_password(request)
        password_valid, password_configured = is_paper_reset_password_valid(candidate)
        if not password_configured:
            raise HTTPException(
                status_code=500,
                detail={
                    "message": "Paper reset password not configured.",
                    **await _build_paper_reset_debug_payload(
                        user_id,
                        accepted_fields=accepted_fields,
                        password_configured=False,
                        reason="missing_password",
                    ),
                },
            )
        if not password_valid:
            logger.warning("Paper reset denied for user=%s: invalid password/confirmation", user_id[:8])
            raise HTTPException(
                status_code=403,
                detail={
                    "message": "Invalid reset password or confirmation phrase",
                    **await _build_paper_reset_debug_payload(
                        user_id,
                        accepted_fields=accepted_fields,
                        password_configured=True,
                        reason="wrong_password",
                    ),
                },
            )
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
            **await _build_paper_reset_debug_payload(
                user_id,
                accepted_fields=accepted_fields,
                password_configured=True,
            ),
            **result
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Paper reset server error for user=%s: %s", user_id[:8], e)
        raise HTTPException(
            status_code=500,
            detail={
                "message": "Paper reset failed due to server error",
                **await _build_paper_reset_debug_payload(
                    user_id,
                    accepted_fields=[],
                    password_configured=bool(_load_paper_reset_password()),
                    reason="reset_failed",
                ),
            },
        )


@router.post("/reset-paper")
async def reset_paper_trading(
    request: PaperResetRequest,
    user_id: str = Depends(get_current_user)
):
    """Legacy paper reset endpoint (password via PAPER_RESET_PASSWORD env)."""
    return await paper_reset(request=request, user_id=user_id)


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
