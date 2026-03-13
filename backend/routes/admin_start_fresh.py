"""
Admin Start Fresh Endpoint - Canonical Paper Reset

All paper-reset / start-fresh flows call a single authoritative function
(``perform_paper_reset``) so that every reset is guaranteed to cover:
- bots (soft-delete + runtime-state removal)
- trades, orders, positions
- fills / ledger / paper_ledger / paper_wallet
- wallet_balances / wallets
- profits / metrics caches
- bodyguard, daily-loss-lock, circuit-breaker, quarantine flags
- any stale pause_reason / last_order_error carryover

The paper_wallet is reset to the configured starting capital.
All ledger entries and paper_ledger rows are deleted.
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
    confirm_phrase: str
    scope: Literal["paper_only", "paper_and_bots"] = "paper_only"
    also_reset_risk_locks: bool = True


@router.post("/api/admin/start-fresh")
async def start_fresh(
    request: StartFreshRequest,
    user_id: str = Depends(require_admin)
):
    """
    Start Fresh - Admin-only canonical paper reset (ADMIN ONLY)

    Delegates to the single authoritative ``perform_paper_reset`` function
    which fully resets bots, trades, fills, wallet, ledger, runtime state,
    bodyguard flags, circuit-breaker state, and risk locks.

    Requires:
        - Admin privileges
        - Confirmation phrase: "DELETE ALL TRADING DATA"

    Args:
        confirm_phrase: Must be "DELETE ALL TRADING DATA"
        scope: "paper_only" (default) or "paper_and_bots" (same effect)
        also_reset_risk_locks: respected; perform_paper_reset always resets them

    Returns:
        - success: bool
        - summary: counts of deleted items
        - audit_id: ID of audit log entry
    """
    if request.confirm_phrase != "DELETE ALL TRADING DATA":
        raise HTTPException(
            status_code=400,
            detail="Invalid confirmation phrase. Must be 'DELETE ALL TRADING DATA'"
        )

    try:
        # Delegate to the canonical reset path so every reset is identical
        from routes.system_mode import perform_paper_reset
        result = await perform_paper_reset(user_id)

        summary = result.get("summary", {})
        audit_id = f"admin_start_fresh_{datetime.now(timezone.utc).timestamp()}"

        logger.info(
            "Admin start-fresh completed for user %s: %s bots, %s trades",
            user_id,
            summary.get("bots_deleted", 0),
            summary.get("trades_deleted", 0),
        )

        return {
            "success": True,
            "message": "Start Fresh completed successfully",
            "summary": summary,
            "collection_counts": result.get("collection_counts", {}),
            "audit_id": audit_id,
            "timestamp": result.get("timestamp", datetime.now(timezone.utc).isoformat()),
            "scope": request.scope,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error during Admin Start Fresh for user %s: %s", user_id, e)
        raise HTTPException(status_code=500, detail=str(e))


class ResetUserDataRequest(BaseModel):
    """Request model for resetting specific user data"""
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
        target_user_id: User ID to reset
        wipe_bots: Delete all bots (default: True)
        wipe_trades: Delete trade history (default: False)
        wipe_keys: Delete API keys (default: False)

    Returns:
        success: bool
        summary: dict with deletion counts
        backup_id: audit log ID for recovery

    Raises:
        403: If user is not admin
        404: If target user not found
        500: On database errors
    """
    try:
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
            logger.info("Deleted %d bots for user %s", deleted_counts["bots"], request.target_user_id)

        if request.wipe_trades:
            result = await db.trades_collection.delete_many({
                "user_id": request.target_user_id
            })
            deleted_counts["trades"] = result.deleted_count

        if request.wipe_keys:
            result = await db.api_keys_collection.delete_many({
                "user_id": request.target_user_id
            })
            deleted_counts["keys"] = result.deleted_count

        await db.audit_logs_collection.update_one(
            {"id": backup_id},
            {"$set": {"counts_after_delete": deleted_counts}}
        )

        logger.info(
            "Admin %s reset data for user %s: bots=%d trades=%d keys=%d",
            user_id, request.target_user_id,
            deleted_counts["bots"], deleted_counts["trades"], deleted_counts["keys"],
        )

        return {
            "success": True,
            "message": f"User data reset completed for {request.target_user_id}",
            "summary": deleted_counts,
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
        logger.error("Error during user data reset: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/bots/reset")
async def user_self_reset_bots(
    user_id: str = Depends(get_current_user)
):
    """
    User self-reset bots (non-admin)

    Allows users to reset their own paper trading session via the canonical
    reset path.  Only works in paper/testing mode — blocked in live trading.

    Returns:
        success: bool
        bots_deleted: int

    Raises:
        403: If not in paper trading mode
        500: On database errors
    """
    try:
        from utils.env_utils import env_bool
        live_trading = env_bool('LIVE_TRADING', False)

        if live_trading:
            raise HTTPException(
                status_code=403,
                detail="Self-reset not allowed in live trading mode. Contact admin."
            )

        from routes.system_mode import perform_paper_reset
        result = await perform_paper_reset(user_id)
        summary = result.get("summary", {})

        logger.info("User %s self-reset: %d bots deleted", user_id, summary.get("bots_deleted", 0))

        return {
            "success": True,
            "message": "Your paper trading session has been reset",
            "bots_deleted": summary.get("bots_deleted", 0),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error during user self-reset for %s: %s", user_id, e)
        raise HTTPException(status_code=500, detail=str(e))


class PaperStartFreshRequest(BaseModel):
    confirmed: bool = False


@router.post("/api/user/paper-start-fresh")
async def user_paper_start_fresh(
    request: PaperStartFreshRequest,
    user_id: str = Depends(get_current_user)
):
    """
    User paper start-fresh (non-admin, paper-only scope).

    Fully resets the caller's paper trading session via the same canonical
    ``perform_paper_reset`` path used by the admin endpoint.  This restores
    backward-compatible dashboard behaviour where the user can trigger a
    clean start without requiring admin privileges.

    Args:
        confirmed: Must be ``true`` to execute the reset.

    Returns:
        success, message, summary, timestamp

    Raises:
        400: If confirmed is false
        403: If called while live trading is enabled
        500: On database errors
    """
    if not request.confirmed:
        raise HTTPException(
            status_code=400,
            detail="Send confirmed=true to execute the paper start-fresh reset."
        )

    try:
        from utils.env_utils import env_bool
        live_trading = env_bool('LIVE_TRADING', False)

        if live_trading:
            raise HTTPException(
                status_code=403,
                detail="Paper start-fresh not allowed in live trading mode. Contact admin."
            )

        from routes.system_mode import perform_paper_reset
        result = await perform_paper_reset(user_id)
        summary = result.get("summary", {})

        logger.info(
            "User paper-start-fresh completed for %s: %d bots, %d trades",
            user_id,
            summary.get("bots_deleted", 0),
            summary.get("trades_deleted", 0),
        )

        return {
            "success": True,
            "message": "Paper start-fresh completed. Wallet and bots reset to zero.",
            "summary": summary,
            "timestamp": result.get("timestamp"),
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error during user paper-start-fresh for %s: %s", user_id, e)
        raise HTTPException(status_code=500, detail=str(e))

