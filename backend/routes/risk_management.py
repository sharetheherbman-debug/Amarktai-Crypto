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
import time
from typing import Optional, Dict

from auth import get_current_user
import database as db
from utils.datetime_helpers import remaining_seconds
from services.emergency_stop_override_service import emergency_stop_override_service

logger = logging.getLogger(__name__)
router = APIRouter()

# ---------------------------------------------------------------------------
# TTL cache for /api/risk/status — the endpoint runs N per-bot serial DB
# queries (bodyguard drawdown + ledger PnL per bot) which is expensive.
# Cache for 5 seconds per user_id to prevent poll-induced blocking.
# ---------------------------------------------------------------------------
_RISK_STATUS_CACHE: Dict[str, tuple] = {}   # user_id → (timestamp_mono, payload)
_RISK_STATUS_TTL = 30  # seconds — increased from 5s now that N+1 loop is replaced by batch query


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
        # Serve from cache when fresh — this endpoint runs N per-bot serial
        # DB queries which can take 1–3s for large fleets.
        _now_mono = time.monotonic()
        _cached = _RISK_STATUS_CACHE.get(user_id)
        if _cached and (_now_mono - _cached[0]) < _RISK_STATUS_TTL:
            return _cached[1]

        user = await db.users_collection.find_one({"id": user_id}, {"_id": 0})
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        modes = await db.system_modes_collection.find_one({"user_id": user_id}, {"_id": 0})

        bots = await db.bots_collection.find(
            {"user_id": user_id, "status": {"$ne": "deleted"}},
            {"_id": 0, "id": 1, "name": 1, "status": 1, "trading_mode": 1, "mode": 1,
             "quarantine_reason": 1, "retraining_until": 1, "paused_by_bodyguard": 1,
             "pause_reason": 1, "risk_mode": 1, "current_capital": 1, "equity_peak": 1,
             "bodyguard_last_pause_at": 1, "bodyguard_last_breach_at": 1}
        ).to_list(1000)
        bot_ids = [b["id"] for b in bots if b.get("id")]

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

        from services.bodyguard_service import (
            bodyguard_service,
            PAPER_DRAWDOWN_THRESHOLDS,
            LIVE_DRAWDOWN_THRESHOLDS,
        )
        bot_risk_status = []
        per_bot_status = []

        # Batch daily PnL from trades_collection in ONE aggregation instead of
        # N serial ledger calls.  The fills_ledger (used by ledger_service) may
        # be empty for paper bots; trades_collection is the canonical source for
        # paper P&L.  This replaces ~4 serial DB calls × N bots with 1 query.
        # Note: only realized_pnl_zar (pre-converted ZAR) is used to avoid
        # currency mixing when bots trade in different quote currencies (USDT, ZAR).
        # Older trades without this field contribute 0 to the daily total — acceptable
        # for risk display purposes (these are accurate for all new paper trades).
        today_pnl_by_bot: dict = {}
        try:
            if bot_ids and db.trades_collection is not None:
                today_start_iso = datetime.now(timezone.utc).replace(
                    hour=0, minute=0, second=0, microsecond=0
                ).isoformat()
                pnl_pipeline = [
                    {"$match": {
                        "bot_id": {"$in": bot_ids},
                        "status": "closed",
                        "timestamp": {"$gte": today_start_iso},
                        "realized_pnl_zar": {"$exists": True, "$ne": None},
                    }},
                    {"$group": {
                        "_id": "$bot_id",
                        "realized": {"$sum": "$realized_pnl_zar"},
                        "fees": {"$sum": {"$ifNull": ["$fee_display_zar", 0]}},
                    }}
                ]
                pnl_results = await db.trades_collection.aggregate(pnl_pipeline).to_list(1000)
                for r in pnl_results:
                    today_pnl_by_bot[r["_id"]] = float(r["realized"]) - float(r["fees"])
        except Exception as _pnl_err:
            logger.warning("risk/status: batch daily PnL aggregation failed: %s", _pnl_err)

        for bot in bots:
            bot_id = bot.get("id")
            if not bot_id:
                continue

            # Build drawdown data from the already-loaded bot document —
            # avoids a redundant bots_collection.find_one per bot.
            # Compute threshold inline (same logic as BodyguardService._get_drawdown_threshold)
            # to avoid accessing a private method across service boundaries.
            risk_mode = (bot.get("risk_mode") or "balanced").lower()
            if risk_mode == "aggressive":
                risk_mode = "risky"
            if risk_mode not in PAPER_DRAWDOWN_THRESHOLDS:
                risk_mode = "balanced"
            trading_mode = bot.get("trading_mode", "paper")
            thresholds = PAPER_DRAWDOWN_THRESHOLDS if trading_mode == "paper" else LIVE_DRAWDOWN_THRESHOLDS
            threshold = thresholds.get(risk_mode, thresholds.get("balanced", 20.0))

            current_capital = float(bot.get("current_capital") or 0)
            equity_peak = float(bot.get("equity_peak") or current_capital or 0)
            current_drawdown_pct = 0.0
            if equity_peak > 0:
                current_drawdown_pct = max(0.0, (equity_peak - current_capital) / equity_peak * 100)
            paused_by_bodyguard = bool(bot.get("paused_by_bodyguard", False))

            daily_pnl = today_pnl_by_bot.get(bot_id, 0.0)
            daily_loss_pct = 0.0
            if daily_pnl < 0 and current_capital > 0:
                daily_loss_pct = abs(daily_pnl) / current_capital * 100

            bot_risk_status.append({
                "bot_id": bot_id,
                "bot_name": bot.get("name"),
                "risk_mode": risk_mode,
                "drawdown_pct": round(current_drawdown_pct, 2),
                "daily_pnl": round(daily_pnl, 2),
                "daily_loss_pct": round(daily_loss_pct, 2),
                "threshold": threshold,
                "would_pause": current_drawdown_pct >= threshold,
                "paused_by_bodyguard": paused_by_bodyguard,
                "pause_reason": bot.get("pause_reason"),
                "last_decision_time": bot.get("bodyguard_last_pause_at") or bot.get("bodyguard_last_breach_at"),
            })
            bot_state = "ok"
            reason = None
            if bot.get("status") == "quarantined":
                bot_state = "quarantined"
                reason = bot.get("quarantine_reason") or "Bot quarantined"
            elif paused_by_bodyguard:
                bot_state = "warning"
                reason = bot.get("pause_reason") or "Bodyguard pause"
            per_bot_status.append({
                "bot_id": bot_id,
                "bot_name": bot.get("name"),
                "status": bot_state,
                "reason": reason,
            })

        bodyguard_active = len(bodyguard_bots) > 0

        _result = {
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
        _RISK_STATUS_CACHE[user_id] = (time.monotonic(), _result)
        return _result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting risk status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/risk/daily-loss-lock/status")
async def get_daily_loss_lock_status_explicit(user_id: str = Depends(get_current_user)):
    """
    Explicit status endpoint for daily loss lock.

    Returns a standardised shape:
        locked: bool
        reason: str | null
        since: ISO timestamp | null
        scope: "user"
        entity_id: user_id
    """
    try:
        user = await db.users_collection.find_one({"id": user_id}, {"_id": 0})
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        locked = bool(user.get("daily_loss_lock_active", False))
        return {
            "locked": locked,
            "reason": user.get("daily_loss_locked_reason") if locked else None,
            "since": user.get("daily_loss_locked_at") if locked else None,
            "scope": "user",
            "entity_id": user_id,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting daily-loss-lock status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/risk/bodyguard/status")
async def get_bodyguard_status(user_id: str = Depends(get_current_user)):
    """
    Explicit status endpoint for bodyguard (drawdown) lock.

    Returns a standardised shape:
        locked: bool
        reason: str | null
        since: ISO timestamp | null
        scope: "user"
        entity_id: user_id
        bot_ids: list of bot IDs currently paused by bodyguard
    """
    try:
        bots = await db.bots_collection.find(
            {"user_id": user_id, "paused_by_bodyguard": True, "status": {"$ne": "deleted"}},
            {"_id": 0, "id": 1, "pause_reason": 1, "bodyguard_last_pause_at": 1}
        ).to_list(1000)

        locked = len(bots) > 0
        reasons = sorted({b.get("pause_reason") for b in bots if b.get("pause_reason")})
        earliest_since = None
        for b in bots:
            ts = b.get("bodyguard_last_pause_at")
            if ts and (earliest_since is None or ts < earliest_since):
                earliest_since = ts

        return {
            "locked": locked,
            "reason": reasons[0] if reasons else None,
            "since": earliest_since,
            "scope": "user",
            "entity_id": user_id,
            "bot_ids": [b.get("id") for b in bots],
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting bodyguard status: {e}")
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
        
        # Reset the lock via canonical service (idempotent)
        from services.risk_lock_service import risk_lock_service
        await risk_lock_service.clear_daily_loss_lock(
            user_id,
            cleared_by=f"admin:{user_id}",
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
        
        # Reset the lock via canonical service
        from services.risk_lock_service import risk_lock_service
        await risk_lock_service.clear_daily_loss_lock(
            user_id,
            cleared_by=f"admin:{user_id}",
        )
        
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


@router.get("/api/risk/summary")
async def get_risk_summary(user_id: str = Depends(get_current_user)):
    """Canonical risk summary endpoint.

    Aggregates daily-loss lock, bodyguard status, emergency stop, and
    per-bot risk data into a single response for go-live diagnostics.
    """
    try:
        from services.risk_lock_service import risk_lock_service

        # User-level risk state
        user = await db.users_collection.find_one(
            {"id": user_id},
            {"_id": 0, "daily_loss_lock_active": 1, "emergency_stop": 1,
             "daily_loss_pct": 1, "daily_loss_locked_at": 1,
             "daily_loss_locked_reason": 1}
        )
        user = user or {}

        lock_active = user.get("daily_loss_lock_active", False)
        emergency_stop = user.get("emergency_stop", False)

        # Bodyguard status
        bodyguard_status = "unknown"
        try:
            from ai_bodyguard import bodyguard
            bodyguard_status = "active" if getattr(bodyguard, 'enabled', False) else "inactive"
        except Exception:
            pass

        # Count bots by risk state
        total_bots = await db.bots_collection.count_documents({
            "user_id": user_id,
            "status": {"$nin": ["deleted"]},
        })
        quarantined_bots = await db.bots_collection.count_documents({
            "user_id": user_id,
            "status": "quarantined",
        })
        paused_bots = await db.bots_collection.count_documents({
            "user_id": user_id,
            "status": "paused",
        })

        return {
            "daily_loss_lock_active": lock_active,
            "emergency_stop": emergency_stop,
            "bodyguard_status": bodyguard_status,
            "daily_loss_pct": user.get("daily_loss_pct"),
            "total_bots": total_bots,
            "quarantined_bots": quarantined_bots,
            "paused_bots": paused_bots,
            "risk_healthy": not lock_active and not emergency_stop and quarantined_bots == 0,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as exc:
        logger.error(f"risk summary error: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))
