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
        
        if lock_active and not force:
            raise HTTPException(
                status_code=403,
                detail="Cannot resume bots while daily loss lock is active. Reset lock first or use force=true with admin privileges."
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
