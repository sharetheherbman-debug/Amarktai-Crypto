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
from services.paper_reset_orchestrator import run as _orchestrator_run

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

    Delegates to the shared paper_reset_orchestrator which resets ALL
    performance-related state: equity_peak, daily baselines, circuit
    breaker state, fills, ledger, wallet allocations.

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
        
        # Delegate ALL reset work to the shared orchestrator
        orch_scope = "paper_only" if request.scope == "paper_only" else "full"
        result = await _orchestrator_run(
            user_id=user_id,
            scope=orch_scope,
            also_reset_risk_locks=request.also_reset_risk_locks,
        )

        summary = {
            "bots_deleted": result.get("bots_soft_deleted", 0),
            "trades_deleted": result.get("trades_deleted", 0),
            "orders_deleted": result.get("orders_deleted", 0),
            "fills_deleted": result.get("fills_deleted", 0),
            "telemetry_deleted": result.get("telemetry_deleted", 0),
            "risk_locks_reset": result.get("risk_locks_reset", 0),
        }

        # Clear training/quarantine states (admin-only extra step)
        try:
            await db.training_jobs_collection.delete_many({"user_id": user_id})
        except Exception as e:
            logger.warning(f"Could not delete training sessions: {e}")

        wallet_before = result.get("wallet_before", {})
        wallet_after = result.get("wallet_after", {})

        # Create audit log entry
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
                "orchestrator_warnings": result.get("warnings", []),
            },
        }
        await db.audit_logs_collection.insert_one(audit_entry)

        logger.info(
            "Start Fresh completed for user %s: %d bots, %d trades deleted",
            user_id,
            summary["bots_deleted"],
            summary["trades_deleted"],
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
            "scope": request.scope,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error during Start Fresh: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/user/paper-start-fresh")
async def user_paper_start_fresh(
    request: StartFreshRequest,
    user_id: str = Depends(get_current_user)
):
    """
    User-safe paper reset (no admin required).

    Wipes paper bots, trades, fills, telemetry, risk locks and resets
    the paper wallet — identical scope to /api/admin/start-fresh but
    scoped to "paper_only" and accessible by any authenticated user.

    Requires:
        - Valid JWT (get_current_user)
        - confirmation_phrase == "START FRESH"
        - scope must be "paper_only"

    Returns:
        ok: bool, message: str, deleted: dict
    """
    try:
        if not request.confirmation_phrase or request.confirmation_phrase != "START FRESH":
            raise HTTPException(
                status_code=400,
                detail="Invalid confirmation phrase. Must be 'START FRESH' (exact match)"
            )

        # Force paper_only scope for user-safe reset
        result = await _orchestrator_run(
            user_id=user_id,
            scope="paper_only",
            also_reset_risk_locks=request.also_reset_risk_locks,
        )

        summary = {
            "bots_deleted": result.get("bots_soft_deleted", 0),
            "trades_deleted": result.get("trades_deleted", 0),
            "orders_deleted": result.get("orders_deleted", 0),
            "fills_deleted": result.get("fills_deleted", 0),
            "telemetry_deleted": result.get("telemetry_deleted", 0),
            "risk_locks_reset": result.get("risk_locks_reset", 0),
        }
        wallet_before = result.get("wallet_before", {})
        wallet_after = result.get("wallet_after", {})
        post_reset = result.get("post_reset", {})
        invariant_warnings = result.get("warnings", [])

        logger.info(
            "User paper-start-fresh completed for user %s: %d bots deleted",
            user_id,
            summary["bots_deleted"],
        )

        return {
            "ok": True,
            "message": "Paper reset completed successfully",
            "deleted": summary,
            "wallet_before": wallet_before,
            "wallet_after": wallet_after,
            "post_reset_invariants": post_reset,
            "invariant_warnings": invariant_warnings,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error during user paper-start-fresh: {e}")
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
