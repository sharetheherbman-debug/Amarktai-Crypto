"""
Admin Truth Console Endpoint

GET /api/admin/truth/summary
  — Returns PASS/FAIL per subsystem + evidence fields + reason codes
  — Calls the central Truth Kernel (no duplication)
  — Admin-only access

POST /api/admin/truth/repair-bots
  — Reconciles bot document state against runtime state store
  — Clears stale runtime paused flags for bots whose DB status is 'active'
  — Admin-only access
"""

from fastapi import APIRouter, Depends, HTTPException
from datetime import datetime, timezone
from typing import Dict
import logging

from auth import get_current_user, require_admin
import database as db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin/truth", tags=["Admin Truth Console"])


@router.get("/summary")
async def truth_summary(user_id: str = Depends(require_admin)):
    """
    GET /api/admin/truth/summary

    Admin-only. Returns per-subsystem PASS/FAIL with evidence,
    contradiction flags, and rule precedence order.
    Uses the central Truth Kernel — no separate logic.
    """
    try:
        from services.truth_kernel import compute_truth_summary
        summary = await compute_truth_summary(user_id, db.db)
        return summary
    except Exception as e:
        logger.error(f"Truth summary error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Truth summary failed: {e}")


@router.post("/repair-bots")
async def repair_bot_states(user_id: str = Depends(require_admin)):
    """
    POST /api/admin/truth/repair-bots

    Admin-only. Reconciles bot document state vs runtime state store.
    Fixes the common blocker where a bot's DB status is 'active' but
    the runtime state store still says 'paused', causing the scheduler
    to continuously skip the bot and eventually re-pause it.

    Returns a summary of actions taken.
    """
    try:
        from services.bot_runtime_state import bot_runtime_state as _runtime

        now = datetime.now(timezone.utc).isoformat()
        results = {"reconciled": [], "skipped": [], "errors": []}

        # Fetch all non-deleted bots for this admin user
        all_bots = await db.bots_collection.find(
            {
                "status": {"$nin": ["deleted", "marked_for_deletion"]},
                "deleted": {"$ne": True},
                "is_deleted": {"$ne": True},
                "deleted_at": {"$exists": False},
            },
            {"_id": 0}
        ).to_list(2000)

        for bot in all_bots:
            bot_id = bot.get("id")
            if not bot_id:
                continue
            try:
                reconciled = await _runtime.reconcile_with_bot_doc(bot_id, bot)
                doc_status = bot.get("status", "unknown")
                rt_status = reconciled.get("state", "unknown") if reconciled else "removed"
                if doc_status != rt_status:
                    results["reconciled"].append({
                        "bot_id": bot_id,
                        "bot_name": bot.get("name", "?"),
                        "doc_status": doc_status,
                        "runtime_before": rt_status,
                    })
                else:
                    results["skipped"].append(bot_id)
            except Exception as bot_err:
                logger.warning(f"repair-bots: error reconciling bot {bot_id}: {bot_err}")
                results["errors"].append({"bot_id": bot_id, "error": str(bot_err)})

        logger.info(
            "repair-bots: reconciled=%d skipped=%d errors=%d",
            len(results["reconciled"]), len(results["skipped"]), len(results["errors"])
        )
        return {
            "success": True,
            "timestamp": now,
            "reconciled_count": len(results["reconciled"]),
            "skipped_count": len(results["skipped"]),
            "error_count": len(results["errors"]),
            "details": results,
        }
    except Exception as e:
        logger.error(f"repair-bots error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Bot repair failed: {e}")


@router.post("/repair-bot-types")
async def repair_bot_types(user_id: str = Depends(require_admin)):
    """
    POST /api/admin/truth/repair-bot-types

    Admin-only. Backfills missing bot_type fields for bots created before
    the validator fix.  Uses the same heuristics as the startup migration:
    strategy_preset='scalping' or name starts with 'Scalper' → bot_type='scalper'.
    All other bots with a missing/null bot_type get bot_type='normal'.

    This is idempotent — already-correct bots are not modified.
    """
    try:
        from migrations.fix_bot_type_field import run_bot_type_migration

        now = datetime.now(timezone.utc).isoformat()
        fixed_scalper, fixed_normal = await run_bot_type_migration(db)

        return {
            "success": True,
            "timestamp": now,
            "fixed_scalper": fixed_scalper,
            "fixed_normal": fixed_normal,
            "message": (
                f"Promoted {fixed_scalper} bots to scalper, set {fixed_normal} bots to normal"
                if fixed_scalper or fixed_normal
                else "All bots already have bot_type set — no changes needed"
            ),
        }
    except Exception as e:
        logger.error(f"repair-bot-types error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Bot type repair failed: {e}")

