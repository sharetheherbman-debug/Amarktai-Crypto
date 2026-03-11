"""
Self-Healing Status Endpoint
Exposes the canonical self-healing runtime status at /api/self-healing/status.

This is a dedicated top-level route so the frontend and admin consoles can
reach the self-healing service without going through /api/autonomy/.

Imports self_healing from engines.self_healing — the canonical singleton
started by services/lifecycle.py. The root-level self_healing.py is a
re-export shim for legacy compatibility; both give the same singleton.
"""

from fastapi import APIRouter, Depends
from auth import get_current_user

router = APIRouter(prefix="/api/self-healing", tags=["Self-Healing"])


@router.get("/status")
async def get_self_healing_status(user_id: str = Depends(get_current_user)):
    """Return canonical self-healing runtime status from the live service instance."""
    from engines.self_healing import self_healing
    return {
        "success": True,
        **self_healing.get_status(),
    }
