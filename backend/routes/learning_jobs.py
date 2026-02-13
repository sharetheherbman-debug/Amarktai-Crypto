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
    """Get learning loop status and last run summary."""
    enabled = os.getenv("ENABLE_LEARNING_LOOP", "false").lower() == "true"
    last_run = None
    last_summary = None

    try:
        if db.learning_runs_collection is not None:
            last_run_doc = await db.learning_runs_collection.find_one(
                {"user_id": user_id},
                {"_id": 0, "completed_at": 1, "summary": 1, "status": 1},
                sort=[("completed_at", -1)]
            )
            if last_run_doc:
                last_run = last_run_doc.get("completed_at")
                last_summary = last_run_doc.get("summary")
    except Exception as e:
        logger.warning("Learning status lookup failed: %s", e)

    disabled_reason = None
    if not enabled:
        disabled_reason = "ENABLE_LEARNING_LOOP=false"

    return {
        "success": True,
        "enabled": enabled,
        "disabled_reason": disabled_reason,
        "last_run": last_run or (learning_loop.last_run.isoformat() if learning_loop.last_run else None),
        "last_summary": last_summary,
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
