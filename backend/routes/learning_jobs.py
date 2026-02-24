"""
Learning Jobs Endpoints
Run nightly learning loop manually (supports dry-run).
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from datetime import datetime, timezone
import logging
import os

from auth import get_current_user
import database as db
from services.learning_loop import learning_loop

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/learning", tags=["Learning Jobs"])


@router.get("/status")
async def get_learning_status(user_id: str = Depends(get_current_user)):
    """Get learning loop status and last run summary.

    Returns a truth-based status — never claims 'optimized' when no trades
    have been analyzed.  Shape:
        state: "disabled" | "idle" | "running" | "complete" | "insufficient_data" | "error"
        trades_analyzed: int
        bots_evolved: int
        strategy_updates: int
        last_run_at: iso | null
        last_error: str | null
        last_changes: {...} | null
    """
    enabled = os.getenv("ENABLE_LEARNING_LOOP", "false").lower() == "true"

    last_run_at = None
    last_summary = None
    last_error = None
    last_changes = None
    trades_analyzed = 0
    bots_evolved = 0
    strategy_updates = 0
    db_state = "disabled"

    try:
        if db.learning_runs_collection is not None:
            last_run_doc = await db.learning_runs_collection.find_one(
                {"user_id": user_id},
                {"_id": 0},
                sort=[("completed_at", -1)]
            )
            if last_run_doc:
                last_run_at = last_run_doc.get("completed_at")
                last_summary = last_run_doc.get("summary")
                last_error = last_run_doc.get("error")
                trades_analyzed = int(last_run_doc.get("trades_analyzed", 0) or 0)
                bots_evolved = int(last_run_doc.get("bots_evolved", 0) or 0)
                strategy_updates = int(last_run_doc.get("changes_applied", 0) or 0)
                db_status = last_run_doc.get("status", "")
                if db_status == "insufficient_data":
                    db_state = "insufficient_data"
                elif db_status in ("applied", "skipped"):
                    db_state = "complete" if strategy_updates > 0 else "idle"
                elif db_status == "error":
                    db_state = "error"
                else:
                    db_state = "idle"
    except Exception as e:
        logger.warning("Learning status lookup failed: %s", e)
        db_state = "error"
        last_error = str(e)

    if db.learning_changes_collection is not None:
        try:
            changes_doc = await db.learning_changes_collection.find_one(
                {"user_id": user_id},
                {"_id": 0, "parameter": 1, "old_value": 1, "new_value": 1, "reason": 1},
                sort=[("timestamp", -1)]
            )
            if changes_doc:
                last_changes = changes_doc
        except Exception:
            pass

    # Derive final state
    if not enabled:
        state = "disabled"
    elif learning_loop.is_running:
        state = "running"
    elif db_state == "error":
        state = "error"
    elif trades_analyzed == 0:
        # No data yet — must not claim optimized/complete
        state = "idle"
    else:
        state = db_state

    disabled_reason = None
    if not enabled:
        disabled_reason = "ENABLE_LEARNING_LOOP=false"

    last_run_resolved = last_run_at or (
        learning_loop.last_run.isoformat() if learning_loop.last_run else None
    )
    return {
        "success": True,
        "enabled": enabled,
        "state": state,
        "disabled_reason": disabled_reason,
        "trades_analyzed": trades_analyzed,
        "bots_evolved": bots_evolved,
        "strategy_updates": strategy_updates,
        "last_run_at": last_run_resolved,
        "last_summary": last_summary,
        "last_error": last_error,
        "last_changes": last_changes,
        # Keep legacy field for backward compat
        "last_run": last_run_resolved,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.post("/nightly-run")
async def run_nightly_learning(
    dry_run: bool = Query(False, description="Run learning loop without applying changes"),
    user_id: str = Depends(get_current_user)
):
    """Trigger nightly learning loop immediately (admin-only)."""
    user = await db.users_collection.find_one({"id": user_id}, {"_id": 0, "is_admin": 1})
    if not user or not user.get("is_admin"):
        if not dry_run:
            raise HTTPException(status_code=403, detail="Admin access required")

    await learning_loop.run_nightly_learning(dry_run=dry_run)
    logger.info("Manual nightly learning trigger by %s (dry_run=%s)", user_id[:8], dry_run)
    return {
        "success": True,
        "dry_run": dry_run,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
