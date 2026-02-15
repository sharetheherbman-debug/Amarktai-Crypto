"""
Risk Management Endpoints - Daily Loss Lock Control

Provides admin endpoints to:
- Check daily loss lock status
- Reset daily loss lock (admin-only)
- Resume all bots (with lock guard)
"""

from fastapi import APIRouter, HTTPException, Depends
from datetime import datetime, timezone
import logging
from typing import Optional

from auth import get_current_user
import database as db
from utils.datetime_helpers import remaining_seconds
from services.emergency_stop_override_service import emergency_stop_override_service

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/api/risk/daily-loss-lock")
async def get_daily_loss_lock_status(user_id: str = Depends(get_current_user)):
    """
    Get current daily loss lock status for the user
    
    Returns:
        - active: bool - Whether lock is currently active
        - locked_at: timestamp when lock was triggered
        - locked_reason: reason for the lock
        - loss_pct: percentage loss that triggered lock
        - day_key: date (YYYY-MM-DD) when lock was triggered
    """
    try:
        # Get user's risk lock status
        user = await db.users_collection.find_one({"id": user_id}, {"_id": 0})
        
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        # Check for daily loss lock
        lock_active = user.get("daily_loss_lock_active", False)
        
        if lock_active:
            return {
                "active": True,
                "locked_at": user.get("daily_loss_locked_at"),
                "locked_reason": user.get("daily_loss_locked_reason", "Daily loss limit exceeded"),
                "loss_pct": user.get("daily_loss_pct", 0),
                "day_key": user.get("daily_loss_day_key"),
                "message": "Daily loss lock is active. Contact admin to reset."
            }
        else:
            return {
                "active": False,
                "message": "No active daily loss lock"
            }
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting daily loss lock status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/risk/status")
async def get_risk_status(user_id: str = Depends(get_current_user)):
    """Get consolidated risk lock status for current user."""
    try:
        user = await db.users_collection.find_one({"id": user_id}, {"_id": 0})
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        modes = await db.system_modes_collection.find_one({"user_id": user_id}, {"_id": 0})

        bots = await db.bots_collection.find(
            {"user_id": user_id, "status": {"$ne": "deleted"}},
            {"_id": 0, "id": 1, "name": 1, "status": 1, "trading_mode": 1, "mode": 1, "quarantine_reason": 1, "retraining_until": 1, "paused_by_bodyguard": 1, "pause_reason": 1}
        ).to_list(1000)

        quarantined_bots = [bot for bot in bots if bot.get("status") == "quarantined"]
        bodyguard_bots = [bot for bot in bots if bot.get("paused_by_bodyguard")]

        earliest_release = None
        for bot in quarantined_bots:
            release_at = bot.get("retraining_until")
            if release_at and (earliest_release is None or release_at < earliest_release):
                earliest_release = release_at

        quarantine_remaining_seconds = remaining_seconds(earliest_release) if earliest_release else None

        daily_loss_active = user.get("daily_loss_lock_active", False)
        daily_loss_reason = user.get("daily_loss_locked_reason", "Daily loss lock active") if daily_loss_active else None

        emergency_active = modes.get("emergencyStop", False) if modes else False
        emergency_eval = await emergency_stop_override_service.evaluate(user_id, emergency_active)
        emergency_active = emergency_eval["effective_active"]
        emergency_reason = modes.get("emergency_stop_reason", "Emergency stop active") if emergency_active else None

        bodyguard_reasons = sorted({
            bot.get("pause_reason")
            for bot in bodyguard_bots
            if bot.get("pause_reason")
        })
        quarantine_reasons = sorted({
            bot.get("quarantine_reason")
            for bot in quarantined_bots
            if bot.get("quarantine_reason")
        })
        bodyguard_reason = bodyguard_reasons[0] if bodyguard_reasons else None
        quarantine_reason = quarantine_reasons[0] if quarantine_reasons else None

        from services.bodyguard_service import bodyguard_service
        from services.ledger_service import get_ledger_service
        bot_risk_status = []
        per_bot_status = []
        for bot in bots:
            bot_id = bot.get("id")
            if not bot_id:
                continue
            drawdown_status = await bodyguard_service.get_bot_drawdown_status(bot_id)
            if not drawdown_status:
                continue
            daily_pnl = 0.0
            daily_loss_pct = 0.0
            try:
                if db.db is not None:
                    ledger = get_ledger_service(db.db)
                    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
                    realized = await ledger.compute_realized_pnl(bot_id=bot_id, since=today_start)
                    fees = await ledger.compute_fees_paid(bot_id=bot_id, since=today_start)
                    daily_pnl = realized - fees
                    equity = float(drawdown_status.get("current_capital") or 0)
                    if daily_pnl < 0 and equity > 0:
                        daily_loss_pct = abs(daily_pnl) / equity * 100
            except Exception as e:
                logger.warning(f"Risk status daily pnl fallback: {e}")

            threshold = drawdown_status.get("threshold", 0)
            current_drawdown = drawdown_status.get("current_drawdown_pct", 0)
            bot_risk_status.append({
                "bot_id": bot_id,
                "bot_name": drawdown_status.get("bot_name"),
                "risk_mode": drawdown_status.get("risk_mode"),
                "drawdown_pct": current_drawdown,
                "daily_pnl": round(daily_pnl, 2),
                "daily_loss_pct": round(daily_loss_pct, 2),
                "threshold": threshold,
                "would_pause": current_drawdown >= threshold,
                "paused_by_bodyguard": drawdown_status.get("paused_by_bodyguard", False),
                "pause_reason": drawdown_status.get("pause_reason"),
                "last_decision_time": bot.get("bodyguard_last_pause_at") or bot.get("bodyguard_last_breach_at")
            })
            bot_state = "ok"
            reason = None
            if bot.get("status") == "quarantined":
                bot_state = "quarantined"
                reason = bot.get("quarantine_reason") or "Bot quarantined"
            elif bot.get("paused_by_bodyguard"):
                bot_state = "warning"
                reason = bot.get("pause_reason") or "Bodyguard pause"
            per_bot_status.append({
                "bot_id": bot_id,
                "bot_name": bot.get("name"),
                "status": bot_state,
                "reason": reason,
            })

        bodyguard_active = len(bodyguard_bots) > 0

        return {
            "daily_loss_lock": {
                "active": daily_loss_active,
                "reason": daily_loss_reason,
                "why": daily_loss_reason,
                "locked_at": user.get("daily_loss_locked_at"),
                "loss_pct": user.get("daily_loss_pct", 0),
                "next_action": "Reset daily loss lock or contact admin" if daily_loss_active else None,
            },
            "emergency_stop": {
                "active": emergency_active,
                "reason": emergency_reason,
                "why": emergency_reason,
                "locked_at": modes.get("emergency_stop_at") if modes else None,
                "override": {
                    "global_disabled": emergency_eval["global_disabled"],
                    "user_disabled": emergency_eval["user_disabled"],
                    "user_reason": emergency_eval["user_override"].get("reason"),
                },
                "next_action": "Disable emergency stop to resume trading" if emergency_active else None,
            },
            "bodyguard_lock": {
                "active": bodyguard_active,
                "reason": bodyguard_reason,
                "why": bodyguard_reason,
                "reasons": bodyguard_reasons,
                "bot_ids": [bot.get("id") for bot in bodyguard_bots],
                "next_action": "Wait for drawdown recovery or reset bodyguard lock" if bodyguard_bots else None,
            },
            "quarantine_active": {
                "active": len(quarantined_bots) > 0,
                "reason": quarantine_reason,
                "why": quarantine_reason,
                "reasons": quarantine_reasons,
                "release_at": earliest_release,
                "remaining_seconds": quarantine_remaining_seconds,
                "bot_ids": [bot.get("id") for bot in quarantined_bots],
                "next_action": "Wait for retraining to complete" if quarantined_bots else None,
            },
            "bot_risk": {
                "primary_trigger": "drawdown",
                "bots": bot_risk_status,
            },
            "bodyguard_active": bodyguard_active,
            "bodyguard_reason": bodyguard_reason or ("No active bodyguard lock" if not bodyguard_active else None),
            "per_bot_status": per_bot_status,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting risk status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/admin/reset-risk-lock")
async def admin_reset_risk_lock(
    user_id: str = Depends(get_current_user)
):
    """Admin endpoint to reset daily loss lock (idempotent)
    
    Requires admin privileges
    Resets daily loss lock for the current user
    Idempotent - can be called multiple times safely
    
    Returns:
        - success: bool
        - message: confirmation message
        - was_locked: whether a lock was actually present
    """
    try:
        # Check if user is admin
        user = await db.users_collection.find_one({"id": user_id}, {"_id": 0})
        
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        if not user.get("is_admin", False):
            raise HTTPException(
                status_code=403, 
                detail="Admin privileges required"
            )
        
        # Check if lock is currently active
        was_locked = user.get("daily_loss_lock_active", False)
        
        # Reset the lock (idempotent operation)
        result = await db.users_collection.update_one(
            {"id": user_id},
            {
                "$set": {
                    "daily_loss_lock_active": False,
                    "daily_loss_lock_reset_at": datetime.now(timezone.utc).isoformat(),
                    "daily_loss_lock_reset_by": user_id
                },
                "$unset": {
                    "daily_loss_locked_at": "",
                    "daily_loss_locked_reason": "",
                    "daily_loss_pct": "",
                    "daily_loss_day_key": ""
                }
            }
        )
        
        # Emit realtime event
        try:
            from realtime_events import rt_events
            await rt_events.lock_reset(user_id, "daily_loss")
        except Exception as e:
            logger.warning(f"Failed to emit lock_reset event: {e}")
        
        message = (
            "Daily loss lock reset successfully" if was_locked 
            else "No lock was active (idempotent reset completed)"
        )
        
        logger.info(f"Admin {user_id[:8]} reset daily loss lock (was_locked={was_locked})")
        
        return {
            "success": True,
            "message": message,
            "was_locked": was_locked,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error resetting risk lock: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/api/risk/daily-loss-lock/reset")
async def reset_daily_loss_lock(
    confirmation: str,
    user_id: str = Depends(get_current_user)
):
    """
    Reset daily loss lock (ADMIN ONLY)
    
    Requires:
        - Admin privileges
        - Confirmation token: "RESET_RISK_LOCK"
        
    Returns:
        - success: bool
        - message: confirmation message
        - audit_id: ID of audit log entry
    """
    try:
        # Check if user is admin
        user = await db.users_collection.find_one({"id": user_id}, {"_id": 0})
        
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        if not user.get("is_admin", False):
            raise HTTPException(
                status_code=403, 
                detail="Admin privileges required to reset daily loss lock"
            )
        
        # Verify confirmation token
        if confirmation != "RESET_RISK_LOCK":
            raise HTTPException(
                status_code=400,
                detail="Invalid confirmation token. Must be 'RESET_RISK_LOCK'"
            )
        
        # Reset the lock for the user
        result = await db.users_collection.update_one(
            {"id": user_id},
            {
                "$set": {
                    "daily_loss_lock_active": False,
                    "daily_loss_lock_reset_at": datetime.now(timezone.utc).isoformat(),
                    "daily_loss_lock_reset_by": user_id
                },
                "$unset": {
                    "daily_loss_locked_at": "",
                    "daily_loss_locked_reason": "",
                    "daily_loss_pct": "",
                    "daily_loss_day_key": ""
                }
            }
        )
        
        if result.modified_count == 0:
            logger.warning(f"No lock found to reset for user {user_id}")
        
        # Create audit log entry
        audit_entry = {
            "id": f"audit_{datetime.now(timezone.utc).timestamp()}",
            "user_id": user_id,
            "action": "reset_daily_loss_lock",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "details": {
                "confirmation": confirmation,
                "ip_address": None  # Could be extracted from request if needed
            }
        }
        
        await db.audit_logs_collection.insert_one(audit_entry)
        
        logger.info(f"Daily loss lock reset by admin {user_id}")
        
        return {
            "success": True,
            "message": "Daily loss lock reset successfully",
            "audit_id": audit_entry["id"],
            "timestamp": audit_entry["timestamp"]
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error resetting daily loss lock: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/risk/bodyguard/reset")
async def reset_bodyguard_lock(
    confirmation: str,
    target_user_id: Optional[str] = None,
    user_id: str = Depends(get_current_user)
):
    """
    Reset bodyguard pause/quarantine locks (ADMIN ONLY)
    Requires confirmation token: "RESET_BODYGUARD_LOCK"
    """
    try:
        user = await db.users_collection.find_one({"id": user_id}, {"_id": 0})

        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        if not user.get("is_admin", False):
            raise HTTPException(status_code=403, detail="Admin privileges required to reset bodyguard locks")

        if confirmation != "RESET_BODYGUARD_LOCK":
            raise HTTPException(status_code=400, detail="Invalid confirmation token")

        reset_user_id = target_user_id or user_id

        update_result = await db.bots_collection.update_many(
            {
                "user_id": reset_user_id,
                "$or": [
                    {"paused_by_bodyguard": True},
                    {"status": "quarantined"}
                ]
            },
            {
                "$set": {
                    "status": "paused",
                    "paused_by_bodyguard": False,
                    "paused_by_system": False,
                    "bodyguard_breach_count": 0
                },
                "$unset": {
                    "pause_reason": "",
                    "bodyguard_pause_threshold": "",
                    "bodyguard_pause_drawdown": "",
                    "bodyguard_last_breach_at": "",
                    "bodyguard_last_pause_at": "",
                    "quarantine_reason": "",
                    "quarantined_at": "",
                    "retraining_until": "",
                    "quarantine_count": ""
                }
            }
        )

        try:
            from realtime_events import rt_events
            await rt_events.lock_reset(reset_user_id, "bodyguard")
        except Exception as e:
            logger.warning(f"Failed to emit bodyguard lock reset event: {e}")

        return {
            "success": True,
            "message": "Bodyguard locks cleared",
            "user_id": reset_user_id,
            "bots_reset": update_result.modified_count,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error resetting bodyguard lock: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/risk/resume-all")
async def resume_all_bots_with_risk_check(
    force: bool = False,
    user_id: str = Depends(get_current_user)
):
    """
    Resume all paused bots with risk lock check (admin-preferred endpoint)
    
    This endpoint includes daily loss lock protection and is the recommended
    way to resume all bots. It respects risk management guards.
    
    Args:
        force: If true, bypass daily loss lock check (admin only)
        
    Returns:
        - resumed_count: number of bots resumed
        - skipped_count: number of bots skipped
        - errors: list of errors encountered
    """
    try:
        user = await db.users_collection.find_one({"id": user_id}, {"_id": 0})
        
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        # Check for daily loss lock
        lock_active = user.get("daily_loss_lock_active", False)
        modes = await db.system_modes_collection.find_one({"user_id": user_id}, {"_id": 0})

        if modes and modes.get("emergencyStop"):
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "emergency_stop",
                    "message": modes.get("emergency_stop_reason", "Emergency stop is active"),
                    "next_action": "Disable emergency stop before resuming bots",
                },
            )
        
        if lock_active and not force:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "daily_loss_lock",
                    "message": "Cannot resume bots while daily loss lock is active.",
                    "next_action": "Reset the daily loss lock or use force=true with admin privileges",
                },
            )
        
        # If force=true, verify admin
        if force and not user.get("is_admin", False):
            raise HTTPException(
                status_code=403,
                detail="Admin privileges required to force resume with active lock"
            )
        
        # Get all paused bots (exclude deleted)
        paused_bots = await db.bots_collection.find({
            "user_id": user_id,
            "status": "paused",
            "deleted_at": {"$exists": False}
        }, {"_id": 0}).to_list(1000)
        
        resumed_count = 0
        skipped_count = 0
        errors = []
        
        for bot in paused_bots:
            bot_id = bot["id"]
            
            # Skip quarantined bots
            if bot.get("quarantine_reason"):
                skipped_count += 1
                continue
            
            try:
                # Resume bot
                await db.bots_collection.update_one(
                    {"id": bot_id},
                    {
                        "$set": {
                            "status": "active",
                            "resumed_at": datetime.now(timezone.utc).isoformat(),
                            "last_status_change": datetime.now(timezone.utc).isoformat()
                        },
                        "$unset": {
                            "paused_at": "",
                            "paused_by": "",
                            "paused_reason": ""
                        }
                    }
                )
                
                resumed_count += 1
                logger.info(f"Resumed bot {bot_id} as part of resume-all")
                
                # Send real-time update for this bot (import at top if needed)
                try:
                    from realtime_events import rt_events
                    updated_bot = await db.bots_collection.find_one({"id": bot_id}, {"_id": 0})
                    if updated_bot:
                        await rt_events.bot_resumed(user_id, updated_bot)
                except Exception as rt_err:
                    logger.warning(f"Could not send real-time event for bot {bot_id}: {rt_err}")
                
            except Exception as e:
                errors.append({
                    "bot_id": bot_id,
                    "bot_name": bot.get("name", "unknown"),
                    "error": str(e)
                })
                logger.error(f"Error resuming bot {bot_id}: {e}")
        
        return {
            "success": True,
            "resumed_count": resumed_count,
            "skipped_count": skipped_count,
            "total_paused": len(paused_bots),
            "errors": errors,
            "message": f"Resumed {resumed_count} bots, skipped {skipped_count}"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error resuming all bots: {e}")
        raise HTTPException(status_code=500, detail=str(e))
