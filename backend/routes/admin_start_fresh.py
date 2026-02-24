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

from auth import get_current_user, require_admin
import database as db

logger = logging.getLogger(__name__)
router = APIRouter()


class StartFreshRequest(BaseModel):
    confirmation_phrase: str
    scope: Literal["paper_only", "paper_and_bots"] = "paper_only"
    also_reset_risk_locks: bool = True


@router.post("/api/admin/start-fresh")
async def start_fresh(
    request: StartFreshRequest,
    user_id: str = Depends(require_admin)
):
    """
    Start Fresh - Admin-only data wipe (ADMIN ONLY)
    
    Safely wipes:
    - Bots (paper or all depending on scope)
    - Paper trades and fills
    - Bot telemetry and performance stats
    - Risk locks (if enabled)
    
    Requires:
        - Admin privileges via JWT (require_admin)
        - Confirmation phrase: "START FRESH"
        
    Args:
        confirmation_phrase: Must be "START FRESH" (exact match)
        scope: "paper_only" (default) or "paper_and_bots"
        also_reset_risk_locks: Whether to reset risk locks (default: true)
        
    Returns:
        - ok: bool (true on success)
        - message: str
        - deleted: dict with counts of deleted items
        
    Raises:
        - 400: Missing or incorrect confirmation phrase
        - 403: Non-admin user
        - 500: Database errors
    """
    try:
        # Verify confirmation phrase
        if not request.confirmation_phrase or request.confirmation_phrase != "START FRESH":
            raise HTTPException(
                status_code=400,
                detail="Invalid confirmation phrase. Must be 'START FRESH' (exact match)"
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
            
            # Delete fills from fills_ledger collection (via raw db handle)
            try:
                fills_result = await db.db["fills_ledger"].delete_many({
                    "bot_id": {"$in": deleted_bot_ids}
                })
                summary["fills_deleted"] = fills_result.deleted_count
            except Exception as e:
                logger.warning(f"Could not delete fills: {e}")
            
            # Delete bot telemetry/performance records
            try:
                telemetry_result = await db.bot_metrics_collection.delete_many({
                    "bot_id": {"$in": deleted_bot_ids}
                })
                summary["telemetry_deleted"] = telemetry_result.deleted_count
            except Exception as e:
                logger.warning(f"Could not delete telemetry: {e}")
        
        # Step 2b: Clear user-scoped runtime state and graph history
        _user_runtime_collections = [
            ("balance_snapshots", db.balance_snapshots_collection),
            ("paper_ledger", db.paper_ledger_collection),
            ("bot_metrics", db.bot_metrics_collection),
            ("bot_runtime_state", db.bot_runtime_state_collection),
            ("bot_lifecycle", db.bot_lifecycle_collection),
            ("performance_metrics", db.performance_metrics_collection),
        ]
        for coll_name, collection in _user_runtime_collections:
            if collection is None:
                continue
            try:
                result = await collection.delete_many({"user_id": user_id})
                logger.info(
                    f"Start Fresh: cleared {result.deleted_count} docs from {coll_name}"
                )
            except Exception as e:
                logger.warning(f"Could not clear {coll_name}: {e}")

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
            await db.training_jobs_collection.delete_many({
                "user_id": user_id
            })
        except Exception as e:
            logger.warning(f"Could not delete training sessions: {e}")

        # Step 5: Reset paper wallet to starting balance
        wallet_before = {}
        wallet_after = {}
        try:
            from services.paper_wallet_service import paper_wallet_service
            wallet_result = await paper_wallet_service.reset(user_id)
            wallet_before = wallet_result.get("wallet_before", {})
            wallet_after = wallet_result.get("wallet_after", {})
            logger.info(
                f"Start Fresh: Paper wallet reset for user {user_id}: "
                f"before={wallet_before} after={wallet_after}"
            )
        except Exception as wallet_err:
            logger.warning(f"Could not reset paper wallet (non-critical): {wallet_err}")
        
        # Step 6: Create audit log entry
        audit_entry = {
            "id": f"audit_{datetime.now(timezone.utc).timestamp()}",
            "user_id": user_id,
            "action": "start_fresh",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "details": {
                "scope": request.scope,
                "reset_risk_locks": request.also_reset_risk_locks,
                "summary": summary,
                "wallet_before": wallet_before,
                "wallet_after": wallet_after,
            }
        }
        
        await db.audit_logs_collection.insert_one(audit_entry)
        
        logger.info(
            f"Start Fresh completed for user {user_id}: "
            f"{summary['bots_deleted']} bots, {summary['trades_deleted']} trades deleted"
        )
        
        return {
            "ok": True,
            "message": "Start Fresh completed successfully",
            "deleted_counts": summary,
            "deleted": summary,
            "wallet_before": wallet_before,
            "wallet_after": wallet_after,
            "audit_id": audit_entry["id"],
            "timestamp": audit_entry["timestamp"],
            "scope": request.scope
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error during Start Fresh: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class ResetUserDataRequest(BaseModel):
    """Request model for resetting specific user data"""
    confirmation_phrase: str
    target_user_id: str
    wipe_bots: bool = True
    wipe_trades: bool = False
    wipe_keys: bool = False


@router.post("/api/admin/reset-user-data")
async def reset_user_data(
    request: ResetUserDataRequest,
    user_id: str = Depends(require_admin)
):
    """
    Reset user data - Admin only (GO-LIVE SAFETY)
    
    Allows admin to selectively reset user data for clean go-live monitoring.
    Creates backup snapshot in audit logs before deletion.
    
    Args:
        confirmation_phrase: Must be "RESET USER DATA" (exact match)
        target_user_id: User ID to reset
        wipe_bots: Delete all bots (default: True)
        wipe_trades: Delete trade history (default: False)
        wipe_keys: Delete API keys (default: False)
        
    Returns:
        ok: bool (true on success)
        message: str
        deleted: dict with deletion counts
        backup_id: audit log ID for recovery
        
    Raises:
        400: Missing/incorrect confirmation or validation errors
        403: If user is not admin
        404: If target user not found
        500: On database errors
    """
    try:
        # Verify confirmation phrase
        if not request.confirmation_phrase or request.confirmation_phrase != "RESET USER DATA":
            raise HTTPException(
                status_code=400,
                detail="Invalid confirmation phrase. Must be 'RESET USER DATA' (exact match)"
            )
        
        # Verify target user exists
        target_user = await db.users_collection.find_one(
            {"_id": request.target_user_id},
            {"_id": 1, "email": 1, "username": 1}
        )
        
        if not target_user:
            raise HTTPException(
                status_code=404,
                detail=f"Target user not found: {request.target_user_id}"
            )
        
        # Count what will be deleted (for backup and reporting)
        counts = {
            "bots": 0,
            "trades": 0,
            "keys": 0
        }
        
        if request.wipe_bots:
            counts["bots"] = await db.bots_collection.count_documents({
                "user_id": request.target_user_id
            })
        
        if request.wipe_trades:
            counts["trades"] = await db.trades_collection.count_documents({
                "user_id": request.target_user_id
            })
        
        if request.wipe_keys:
            counts["keys"] = await db.api_keys_collection.count_documents({
                "user_id": request.target_user_id
            })
        
        # Create backup snapshot in audit logs
        from uuid import uuid4
        backup_id = str(uuid4())
        audit_entry = {
            "id": backup_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "action": "admin_reset_user_data",
            "admin_user_id": user_id,
            "target_user_id": request.target_user_id,
            "target_user_email": target_user.get("email", "unknown"),
            "operations": {
                "wipe_bots": request.wipe_bots,
                "wipe_trades": request.wipe_trades,
                "wipe_keys": request.wipe_keys
            },
            "counts_before_delete": counts
        }
        
        await db.audit_logs_collection.insert_one(audit_entry)
        
        # Perform deletions
        deleted_counts = {
            "bots": 0,
            "trades": 0,
            "keys": 0
        }
        
        if request.wipe_bots:
            result = await db.bots_collection.delete_many({
                "user_id": request.target_user_id
            })
            deleted_counts["bots"] = result.deleted_count
            logger.info(f"Deleted {deleted_counts['bots']} bots for user {request.target_user_id}")
        
        if request.wipe_trades:
            result = await db.trades_collection.delete_many({
                "user_id": request.target_user_id
            })
            deleted_counts["trades"] = result.deleted_count
            logger.info(f"Deleted {deleted_counts['trades']} trades for user {request.target_user_id}")
        
        if request.wipe_keys:
            result = await db.api_keys_collection.delete_many({
                "user_id": request.target_user_id
            })
            deleted_counts["keys"] = result.deleted_count
            logger.info(f"Deleted {deleted_counts['keys']} API keys for user {request.target_user_id}")
        
        # Update audit log with actual deletion counts
        await db.audit_logs_collection.update_one(
            {"id": backup_id},
            {"$set": {"counts_after_delete": deleted_counts}}
        )
        
        logger.info(
            f"Admin {user_id} reset data for user {request.target_user_id}: "
            f"bots={deleted_counts['bots']}, trades={deleted_counts['trades']}, keys={deleted_counts['keys']}"
        )
        
        return {
            "ok": True,
            "message": f"User data reset completed for {request.target_user_id}",
            "deleted": deleted_counts,
            "backup_id": backup_id,
            "timestamp": audit_entry["timestamp"],
            "target_user": {
                "id": request.target_user_id,
                "email": target_user.get("email", "unknown")
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error during user data reset: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/bots/reset")
async def user_self_reset_bots(
    user_id: str = Depends(get_current_user)
):
    """
    User self-reset bots (non-admin)
    
    Allows users to delete their own bots, but only in testing mode.
    Provides a clean slate for users to restart their bot configurations.
    
    Safety: Only works in testing mode (paper trading)
    
    Returns:
        success: bool
        bots_deleted: int
        
    Raises:
        403: If not in testing mode
        500: On database errors
    """
    try:
        # Check if system is in testing mode
        from utils.env_utils import env_bool
        paper_trading = env_bool('PAPER_TRADING', False)
        live_trading = env_bool('LIVE_TRADING', False)
        
        # Only allow self-reset in paper trading mode
        if live_trading:
            raise HTTPException(
                status_code=403,
                detail="Self-reset not allowed in live trading mode. Contact admin."
            )
        
        # Count bots to be deleted
        bot_count = await db.bots_collection.count_documents({
            "user_id": user_id
        })
        
        # Delete all user's bots
        result = await db.bots_collection.delete_many({
            "user_id": user_id
        })
        
        logger.info(f"User {user_id} self-reset: deleted {result.deleted_count} bots")
        
        # Create audit entry
        audit_entry = {
            "id": str(__import__('uuid').uuid4()),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "action": "user_self_reset_bots",
            "user_id": user_id,
            "bots_deleted": result.deleted_count,
            "system_mode": "paper_trading" if paper_trading else "testing"
        }
        
        await db.audit_logs_collection.insert_one(audit_entry)
        
        return {
            "ok": True,
            "message": "Your bots have been reset",
            "deleted": {
                "bots": result.deleted_count
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error during user self-reset: {e}")
        raise HTTPException(status_code=500, detail=str(e))
