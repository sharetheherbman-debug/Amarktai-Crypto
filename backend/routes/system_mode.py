"""
System Mode Router - Paper vs Live mode management
Enforces exclusivity and provides single source of truth
"""

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional
import logging
from datetime import datetime, timezone

from auth import get_current_user, is_admin
import database as db
from realtime_events import rt_events

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/system", tags=["System Mode"])


class SystemMode(BaseModel):
    """System-wide mode configuration"""
    paperTrading: bool
    liveTrading: bool
    autopilot: bool


class ModeSwitchRequest(BaseModel):
    """Request to switch system mode"""
    mode: str  # 'paper', 'live', or 'autopilot'
    confirmation_token: Optional[str] = None  # Required for switching to live


async def get_system_mode() -> dict:
    """Get current system mode from database
    
    Returns default mode if not set: paper=True, live=False, autopilot=False
    """
    mode_doc = await db.system_modes_collection.find_one({}, {"_id": 0})
    
    if not mode_doc:
        # Initialize with safe defaults
        default_mode = {
            "paperTrading": True,
            "liveTrading": False,
            "autopilot": False,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "updated_by": "system"
        }
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
    
    # Update with timestamp
    new_state["updated_at"] = datetime.now(timezone.utc).isoformat()
    new_state["updated_by"] = user_id
    
    # Upsert mode document
    await db.system_modes_collection.update_one(
        {},  # Match any document (there should only be one)
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
        mode = await get_system_mode()
        
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
        current_mode = await get_system_mode()
        
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
                new_state["paperTrading"] = False  # Mutually exclusive
                # Check readiness for live trading (including 7-day requirement)
                ready, errors = await check_live_readiness(user_id)
                if not ready:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Cannot enable live trading: {'; '.join(errors)}"
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
        
        # Update with timestamp
        new_state["updated_at"] = datetime.now(timezone.utc).isoformat()
        new_state["updated_by"] = user_id
        
        # Persist to database
        await db.system_modes_collection.update_one(
            {},
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


@router.post("/mode/switch")
async def switch_mode(
    data: ModeSwitchRequest,
    user_id: str = Depends(get_current_user),
    admin: bool = Depends(is_admin)
):
    """Switch system mode
    
    Switching to live mode requires:
    - Admin privileges
    - Confirmation token
    - Readiness checks to pass
    
    Args:
        data: Mode switch request with mode and confirmation token
        user_id: Current user ID
        admin: Whether user is admin
        
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
        if mode in ["live", "autopilot"] and not admin:
            raise HTTPException(
                status_code=403,
                detail="Admin privileges required to switch to live or autopilot mode"
            )
        
        # Switching to live requires confirmation token
        if mode == "live":
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
            ready, readiness_errors = await check_live_readiness()
            
            if not ready:
                raise HTTPException(
                    status_code=400,
                    detail=f"System not ready for live trading: {'; '.join(readiness_errors)}"
                )
        
        # Get current mode
        current_mode = await get_system_mode()
        
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
    user_id: str = Depends(get_current_user),
    admin: bool = Depends(is_admin)
):
    """Check if system is ready for live trading
    
    Returns:
        Readiness status with list of checks and any errors
    """
    try:
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
