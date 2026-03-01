"""
Admin Truth Console Endpoint

GET /api/admin/truth/summary
  — Returns PASS/FAIL per subsystem + evidence fields + reason codes
  — Calls the central Truth Kernel (no duplication)
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
        summary = await compute_truth_summary(user_id, db.database)
        return summary
    except Exception as e:
        logger.error(f"Truth summary error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Truth summary failed: {e}")
