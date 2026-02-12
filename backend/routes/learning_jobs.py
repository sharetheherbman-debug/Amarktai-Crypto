"""
Learning Jobs Endpoints
Run nightly learning loop manually (supports dry-run).
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from datetime import datetime, timezone
import logging

from auth import get_current_user
import database as db
from services.learning_loop import learning_loop

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/learning", tags=["Learning Jobs"])


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
