"""
Emergency Stop System
Provides instant trading halt across all bots and exchanges
"""

from fastapi import APIRouter, HTTPException, Depends
from typing import Dict
import logging
from datetime import datetime, timezone

from auth import get_current_user
import database as db
from engines.audit_logger import audit_logger
from services.emergency_stop_override_service import emergency_stop_override_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/system", tags=["Emergency Stop"])

@router.post("/emergency-stop")
async def activate_emergency_stop(
    reason: str = "User initiated",
    user_id: str = Depends(get_current_user)
):
    """
    Activate emergency stop - immediately halt all trading
    """
    try:
        # Set emergency stop flag
        await db.system_modes_collection.update_one(
            {"user_id": user_id},
            {
                "$set": {
                    "emergencyStop": True,
                    "emergency_stop_reason": reason,
                    "emergency_stop_at": datetime.now(timezone.utc).isoformat(),
                    "emergency_stop_by": user_id
                }
            },
            upsert=True
        )
        
        # Pause all active bots
        result = await db.bots_collection.update_many(
            {"user_id": user_id, "status": "active"},
            {"$set": {"status": "paused"}}
        )
        
        # Log the action
        await audit_logger.log_event(
            event_type="emergency_stop_activated",
            user_id=user_id,
            details={
                "reason": reason,
                "bots_paused": result.modified_count
            },
            severity="critical"
        )
        
        logger.critical(f"🚨 EMERGENCY STOP activated by user {user_id[:8]}: {reason}")
        
        return {
            "success": True,
            "message": "Emergency stop activated - all trading halted",
            "bots_paused": result.modified_count,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as e:
        logger.error(f"Emergency stop error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/emergency-stop/disable")
async def deactivate_emergency_stop(user_id: str = Depends(get_current_user)):
    """
    Deactivate emergency stop - resume normal operations
    DEPRECATED: Use /emergency-resume instead
    """
    return await emergency_resume(user_id)


@router.post("/emergency-resume")
async def emergency_resume(user_id: str = Depends(get_current_user)):
    """
    Resume trading after emergency stop.

    Clears the emergency stop flag and re-activates any bots that were paused
    solely because of EMERGENCY_STOP so they are ready for the next scheduler tick.
    """
    try:
        # Check if emergency stop is active
        modes = await db.system_modes_collection.find_one({"user_id": user_id}, {"_id": 0})
        
        if not modes or not modes.get('emergencyStop'):
            return {
                "success": False,
                "message": "Emergency stop is not active"
            }
        
        now_iso = datetime.now(timezone.utc).isoformat()

        # Clear the primary scheduler gate (system_modes_collection.emergencyStop)
        await db.system_modes_collection.update_one(
            {"user_id": user_id},
            {
                "$set": {
                    "emergencyStop": False,
                    "emergency_stop_disabled_at": now_iso,
                    "emergency_stop_disabled_by": user_id
                }
            }
        )

        # Also clear users_collection.emergency_stop so system_gate.can_trade() passes
        await db.users_collection.update_one(
            {"id": user_id},
            {"$set": {"emergency_stop": False, "emergency_stop_cleared_at": now_iso}},
        )

        # Re-activate bots that were paused SOLELY because of EMERGENCY_STOP.
        # We only touch bots where paused_by_system=True and the stop reason is
        # explicitly EMERGENCY_STOP — this avoids disturbing unrelated risk locks.
        unpaused_result = await db.bots_collection.update_many(
            {
                "user_id": user_id,
                "status": "paused",
                "paused_by_system": True,
                "pause_reason": "EMERGENCY_STOP",
            },
            {
                "$set": {
                    "status": "active",
                    "emergency_stop_cleared_at": now_iso,
                },
                "$unset": {
                    "pause_reason": "",
                    "pause_reason_code": "",
                    "paused_by_system": "",
                    "paused_at": "",
                    "last_intervention": "",
                },
            },
        )
        bots_unpaused = unpaused_result.modified_count

        # Also release bots that were quarantined because of EMERGENCY_STOP so they
        # are not stuck in the quarantine queue waiting out a timer.
        unquarantined_result = await db.bots_collection.update_many(
            {
                "user_id": user_id,
                "status": "quarantined",
                "quarantine_reason_code": "EMERGENCY_STOP",
            },
            {
                "$set": {
                    "status": "active",
                    "emergency_stop_cleared_at": now_iso,
                },
                "$unset": {
                    "quarantine_reason": "",
                    "quarantine_reason_code": "",
                    "quarantined_at": "",
                    "retraining_until": "",
                    "quarantine_duration_seconds": "",
                    "quarantine_count": "",
                    "last_intervention": "",
                },
            },
        )
        bots_unquarantined = unquarantined_result.modified_count

        # Log the action
        await audit_logger.log_event(
            event_type="emergency_stop_deactivated",
            user_id=user_id,
            details={
                "reason": "User resumed operations",
                "bots_unpaused": bots_unpaused,
                "bots_unquarantined": bots_unquarantined,
            },
            severity="warning"
        )
        
        logger.info(
            "✅ Emergency stop deactivated by user %s — bots_unpaused=%d bots_unquarantined=%d",
            user_id[:8], bots_unpaused, bots_unquarantined,
        )
        
        return {
            "success": True,
            "message": "Emergency stop deactivated - trading resumed",
            "bots_unpaused": bots_unpaused,
            "bots_unquarantined": bots_unquarantined,
            "timestamp": now_iso,
        }
        
    except Exception as e:
        logger.error(f"Deactivate emergency stop error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/emergency-stop/clear")
async def clear_emergency_stop(user_id: str = Depends(get_current_user)):
    """
    Canonical idempotent emergency-stop clear path.

    Clears the emergency stop state across ALL truth sources for this user
    unconditionally (even if emergencyStop is already False):

    1. system_modes_collection.emergencyStop  (camelCase — scheduler gate)
    2. users_collection.emergency_stop        (snake_case — system_gate)
    3. bot-level pauses caused by EMERGENCY_STOP
    4. quarantine entries caused by EMERGENCY_STOP

    Unlike /emergency-resume (which returns early when stop is already False),
    this endpoint always clears every layer so it is safe to call as the first
    step before paper testing regardless of current state.
    Bots paused or quarantined for OTHER reasons are left untouched.
    """
    try:
        now_iso = datetime.now(timezone.utc).isoformat()

        # 1. Clear the primary scheduler gate
        await db.system_modes_collection.update_one(
            {"user_id": user_id},
            {
                "$set": {
                    "emergencyStop": False,
                    "emergency_stop_disabled_at": now_iso,
                    "emergency_stop_disabled_by": user_id,
                }
            },
            upsert=True,
        )

        # 2. Clear users_collection.emergency_stop so system_gate.can_trade() passes
        await db.users_collection.update_one(
            {"id": user_id},
            {"$set": {"emergency_stop": False, "emergency_stop_cleared_at": now_iso}},
        )

        # 3. Re-activate bots paused SOLELY because of EMERGENCY_STOP
        unpaused_result = await db.bots_collection.update_many(
            {
                "user_id": user_id,
                "status": "paused",
                "paused_by_system": True,
                "pause_reason": "EMERGENCY_STOP",
            },
            {
                "$set": {
                    "status": "active",
                    "emergency_stop_cleared_at": now_iso,
                },
                "$unset": {
                    "pause_reason": "",
                    "pause_reason_code": "",
                    "paused_by_system": "",
                    "paused_at": "",
                    "last_intervention": "",
                },
            },
        )
        bots_unpaused = unpaused_result.modified_count

        # 4. Release bots quarantined because of EMERGENCY_STOP
        unquarantined_result = await db.bots_collection.update_many(
            {
                "user_id": user_id,
                "status": "quarantined",
                "quarantine_reason_code": "EMERGENCY_STOP",
            },
            {
                "$set": {
                    "status": "active",
                    "emergency_stop_cleared_at": now_iso,
                },
                "$unset": {
                    "quarantine_reason": "",
                    "quarantine_reason_code": "",
                    "quarantined_at": "",
                    "retraining_until": "",
                    "quarantine_duration_seconds": "",
                    "quarantine_count": "",
                    "last_intervention": "",
                },
            },
        )
        bots_unquarantined = unquarantined_result.modified_count

        await audit_logger.log_event(
            event_type="emergency_stop_cleared",
            user_id=user_id,
            details={
                "reason": "Canonical clear — all layers",
                "bots_unpaused": bots_unpaused,
                "bots_unquarantined": bots_unquarantined,
            },
            severity="warning",
        )

        logger.info(
            "✅ Emergency stop fully cleared for user %s — bots_unpaused=%d bots_unquarantined=%d",
            user_id[:8], bots_unpaused, bots_unquarantined,
        )

        return {
            "success": True,
            "message": "Emergency stop cleared across all layers — paper bots will remain active",
            "cleared": {
                "system_modes_emergencyStop": False,
                "users_emergency_stop": False,
                "bots_unpaused": bots_unpaused,
                "bots_unquarantined": bots_unquarantined,
            },
            "timestamp": now_iso,
        }

    except Exception as e:
        logger.error(f"Clear emergency stop error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/emergency-stop/status")
async def get_emergency_stop_status(user_id: str = Depends(get_current_user)):
    """
    Get current emergency stop status
    
    Returns contract required by verify_production_ready.py with fields:
    - success: true (operation success indicator)
    - enabled/active: same value, both included for backward compatibility with different clients
    - reason: reason for emergency stop if active
    - updated_at: timestamp when emergency stop was last changed
    - activated_by: user ID who activated (optional, for audit trail)
    """
    try:
        modes = await db.system_modes_collection.find_one({"user_id": user_id}, {"_id": 0})
        
        if not modes:
            return {
                "success": True,
                "enabled": False,
                "active": False,
                "reason": None,
                "updated_at": None,
                "activated_by": None
            }
        
        stored_active = modes.get('emergencyStop', False)
        evaluation = await emergency_stop_override_service.evaluate(user_id, stored_active)
        is_active = evaluation["effective_active"]
        
        return {
            "success": True,
            "enabled": is_active,
            "active": is_active,
            "reason": modes.get('emergency_stop_reason'),
            "updated_at": modes.get('emergency_stop_at'),
            "activated_by": modes.get('emergency_stop_by'),
            "override": {
                "global_disabled": evaluation["global_disabled"],
                "user_disabled": evaluation["user_disabled"],
                "user_reason": evaluation["user_override"].get("reason")
            }
        }
        
    except Exception as e:
        logger.error(f"Get emergency stop status error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/emergency-gates")
async def get_emergency_gates_status(user_id: str = Depends(get_current_user)):
    """
    Get comprehensive emergency gates status including all safety gates
    
    NOTE: This endpoint is distinct from GET /api/system/status (in system_status.py)
    This endpoint focuses specifically on emergency stop gates and trading permissions
    
    Returns:
        emergency_stop: Whether emergency stop is active
        live_trading_enabled: Whether live trading is allowed (env + user toggle)
        autopilot_enabled: Whether autopilot is allowed (env + user toggle)
        paper_trading_enabled: Whether paper trading is allowed
        system_mode: Current system mode (testing/paper/live)
        features: Dict of enabled features
    """
    try:
        import os
        from utils.env_utils import env_bool
        
        # Get user system modes
        modes = await db.system_modes_collection.find_one({"user_id": user_id}, {"_id": 0})
        user = await db.users_collection.find_one({"id": user_id}, {"_id": 0})
        
        # Emergency stop status
        stored_emergency_stop = modes.get('emergencyStop', False) if modes else False
        evaluation = await emergency_stop_override_service.evaluate(user_id, stored_emergency_stop)
        emergency_stop = evaluation["effective_active"]
        
        # Check environment and user toggles for live trading
        env_live_enabled = env_bool("ENABLE_LIVE_TRADING", False) or env_bool("LIVE_TRADING", False)
        user_live_enabled = modes.get('liveTrading', False) if modes else False
        live_trading_enabled = env_live_enabled and user_live_enabled and not emergency_stop
        
        # Check environment and user toggles for autopilot
        env_autopilot_enabled = env_bool("ENABLE_AUTOPILOT", False) or env_bool("AUTOPILOT_ENABLED", False)
        user_autopilot_enabled = user.get('autopilot_enabled', False) if user else False
        autopilot_enabled = env_autopilot_enabled and user_autopilot_enabled and not emergency_stop
        
        # Paper trading (always safe)
        env_paper_enabled = env_bool("ENABLE_PAPER_TRADING", True) or env_bool("PAPER_TRADING", True)
        paper_trading_enabled = env_paper_enabled and not emergency_stop
        
        # System mode
        system_mode = modes.get('systemMode', 'testing') if modes else 'testing'
        
        # Feature flags
        features = {
            "realtime": env_bool("ENABLE_REALTIME", True),
            "ccxt": env_bool("ENABLE_CCXT", True),
            "schedulers": env_bool("ENABLE_SCHEDULERS", True),
            "wallet_autopilot": env_bool("ENABLE_WALLET_AUTOPILOT", False),
            "withdrawals": env_bool("ENABLE_WITHDRAWALS", False),
            "2fa_required": env_bool("REQUIRE_2FA_FOR_WITHDRAWALS", False)
        }
        
        return {
            "success": True,
            "emergency_stop": emergency_stop,
            "live_trading_enabled": live_trading_enabled,
            "autopilot_enabled": autopilot_enabled,
            "paper_trading_enabled": paper_trading_enabled,
            "system_mode": system_mode,
            "features": features,
            "gates": {
                "env_live_gate": env_live_enabled,
                "user_live_gate": user_live_enabled,
                "env_autopilot_gate": env_autopilot_enabled,
                "user_autopilot_gate": user_autopilot_enabled,
                "emergency_stop_gate": not emergency_stop,
                "emergency_stop_override": {
                    "global_disabled": evaluation["global_disabled"],
                    "user_disabled": evaluation["user_disabled"]
                }
            },
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as e:
        logger.error(f"Get system status error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
