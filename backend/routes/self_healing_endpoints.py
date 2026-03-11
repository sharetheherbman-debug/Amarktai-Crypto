"""
Self-Healing Status Endpoint
Exposes the canonical self-healing runtime status at /api/self-healing/status.

This is a dedicated top-level route so the frontend and admin consoles can
reach the self-healing service without going through /api/autonomy/.
"""

from fastapi import APIRouter, Depends
from auth import get_current_user

router = APIRouter(prefix="/api/self-healing", tags=["Self-Healing"])


@router.get("/status")
async def get_self_healing_status(user_id: str = Depends(get_current_user)):
    """Return canonical self-healing runtime status from the live service instance."""
    from self_healing import self_healing
    return {
        "success": True,
        **self_healing.get_status(),
    }
