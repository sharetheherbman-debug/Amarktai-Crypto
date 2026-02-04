"""
Admin Start Fresh Endpoint - Safe Data Wipe

Provides admin-only endpoint to:
- Delete all paper trading bots
- Wipe paper trading history
- Reset bot telemetry
- Clear risk locks
"""

from fastapi import APIRouter, HTTPException, Depends
from datetime import datetime, timezone
import logging
from pydantic import BaseModel
from typing import Optional, Literal

from auth import get_current_user
import database as db

logger = logging.getLogger(__name__)
router = APIRouter()


class StartFreshRequest(BaseModel):
    confirm_phrase: str
    scope: Literal["paper_only", "paper_and_bots"] = "paper_only"
    also_reset_risk_locks: bool = True


@router.post("/api/admin/start-fresh")
async def start_fresh(
    request: StartFreshRequest,
    user_id: str = Depends(get_current_user)
):
    """
    Start Fresh - Admin-only data wipe (ADMIN ONLY)
    
    Safely wipes:
    - Bots (paper or all depending on scope)
    - Paper trades and fills
    - Bot telemetry and performance stats
    - Risk locks (if enabled)
    
    Requires:
        - Admin privileges
        - Confirmation phrase: "DELETE_ALL_PAPER_DATA"
        
    Args:
        confirm_phrase: Must be "DELETE_ALL_PAPER_DATA"
        scope: "paper_only" (default) or "paper_and_bots"
        also_reset_risk_locks: Whether to reset risk locks (default: true)
        
    Returns:
        - success: bool
        - summary: counts of deleted items
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
                detail="Admin privileges required for Start Fresh operation"
            )
        
        # Verify confirmation phrase
        if request.confirm_phrase != "DELETE_ALL_PAPER_DATA":
            raise HTTPException(
                status_code=400,
                detail="Invalid confirmation phrase. Must be 'DELETE_ALL_PAPER_DATA'"
            )
        
        summary = {
            "bots_deleted": 0,
            "trades_deleted": 0,
            "orders_deleted": 0,
            "fills_deleted": 0,
            "telemetry_deleted": 0,
            "risk_locks_reset": 0
        }
        
        # Step 1: Stop/Delete bots based on scope
        if request.scope == "paper_only":
            # Delete only paper trading bots
            bot_query = {
                "user_id": user_id,
                "trading_mode": "paper",
                "deleted_at": {"$exists": False}
            }
        else:
            # Delete all bots (paper and live)
            bot_query = {
                "user_id": user_id,
                "deleted_at": {"$exists": False}
            }
        
        # Mark bots as deleted (soft delete)
        delete_timestamp = datetime.now(timezone.utc).isoformat()
        
        result = await db.bots_collection.update_many(
            bot_query,
            {
                "$set": {
                    "status": "deleted",
                    "deleted_at": delete_timestamp,
                    "deleted_by": user_id,
                    "deletion_reason": "start_fresh_wipe"
                }
            }
        )
        
        summary["bots_deleted"] = result.modified_count
        logger.info(f"Start Fresh: Deleted {result.modified_count} bots for user {user_id}")
        
        # Step 2: Delete paper trading history
        # Get bot IDs that were deleted
        deleted_bots = await db.bots_collection.find(
            {"user_id": user_id, "deletion_reason": "start_fresh_wipe"},
            {"_id": 0, "id": 1}
        ).to_list(1000)
        
        deleted_bot_ids = [bot["id"] for bot in deleted_bots]
        
        if deleted_bot_ids:
            # Delete trades
            trades_result = await db.trades_collection.delete_many({
                "bot_id": {"$in": deleted_bot_ids}
            })
            summary["trades_deleted"] = trades_result.deleted_count
            
            # Delete orders
            orders_result = await db.orders_collection.delete_many({
                "bot_id": {"$in": deleted_bot_ids}
            })
            summary["orders_deleted"] = orders_result.deleted_count
            
            # Delete fills (if collection exists)
            try:
                fills_result = await db.fills_collection.delete_many({
                    "bot_id": {"$in": deleted_bot_ids}
                })
                summary["fills_deleted"] = fills_result.deleted_count
            except Exception as e:
                logger.warning(f"Could not delete fills: {e}")
            
            # Delete bot telemetry/performance records
            try:
                telemetry_result = await db.bot_performance_collection.delete_many({
                    "bot_id": {"$in": deleted_bot_ids}
                })
                summary["telemetry_deleted"] = telemetry_result.deleted_count
            except Exception as e:
                logger.warning(f"Could not delete telemetry: {e}")
        
        # Step 3: Reset risk locks if requested
        if request.also_reset_risk_locks:
            risk_result = await db.users_collection.update_one(
                {"id": user_id},
                {
                    "$set": {
                        "daily_loss_lock_active": False,
                        "daily_loss_lock_reset_at": datetime.now(timezone.utc).isoformat(),
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
            
            if risk_result.modified_count > 0:
                summary["risk_locks_reset"] = 1
                logger.info(f"Start Fresh: Reset risk locks for user {user_id}")
        
        # Step 4: Clear training/quarantine states
        try:
            await db.training_sessions_collection.delete_many({
                "user_id": user_id
            })
        except Exception as e:
            logger.warning(f"Could not delete training sessions: {e}")
        
        # Step 5: Create audit log entry
        audit_entry = {
            "id": f"audit_{datetime.now(timezone.utc).timestamp()}",
            "user_id": user_id,
            "action": "start_fresh",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "details": {
                "scope": request.scope,
                "reset_risk_locks": request.also_reset_risk_locks,
                "summary": summary
            }
        }
        
        await db.audit_logs_collection.insert_one(audit_entry)
        
        logger.info(
            f"Start Fresh completed for user {user_id}: "
            f"{summary['bots_deleted']} bots, {summary['trades_deleted']} trades deleted"
        )
        
        return {
            "success": True,
            "message": "Start Fresh completed successfully",
            "summary": summary,
            "audit_id": audit_entry["id"],
            "timestamp": audit_entry["timestamp"],
            "scope": request.scope
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error during Start Fresh: {e}")
        raise HTTPException(status_code=500, detail=str(e))
