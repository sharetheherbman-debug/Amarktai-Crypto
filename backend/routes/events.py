"""
Events feed routes.
Provides a per-user events stream for the Overview panel.
"""
from fastapi import APIRouter, Depends, Query
from datetime import datetime, timezone
from typing import Optional
import logging

from auth import get_current_user
import database as db

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/events", tags=["Events"])


async def emit_event(user_id: str, event_type: str, severity: str, message: str, meta: Optional[dict] = None):
    """Emit an event to the user's events collection in Mongo."""
    if db.db is None:
        return
    try:
        await db.db.events.insert_one({
            "user_id": user_id,
            "type": event_type,
            "severity": severity,
            "message": message,
            "ts": datetime.now(timezone.utc),
            "meta": meta or {},
        })
    except Exception as e:
        logger.warning(f"Failed to emit event: {e}")


@router.get("/recent")
async def get_recent_events(
    limit: int = Query(10, ge=1, le=50),
    user_id: str = Depends(get_current_user),
):
    """Get recent events for the current user."""
    if db.db is None:
        return {"events": [], "count": 0}
    try:
        cursor = db.db.events.find(
            {"user_id": user_id},
            {"_id": 0}
        ).sort("ts", -1).limit(limit)
        events = await cursor.to_list(length=limit)
        for ev in events:
            if isinstance(ev.get("ts"), datetime):
                ev["ts"] = ev["ts"].isoformat()
        return {"events": events, "count": len(events)}
    except Exception as e:
        logger.error(f"Error fetching events: {e}")
        return {"events": [], "count": 0, "error": str(e)}


@router.get("/market-intelligence")
async def get_market_intelligence(user_id: str = Depends(get_current_user)):
    """Get the latest automated market intelligence from CoinStats."""
    try:
        from services.market_intelligence_service import get_latest_intelligence
        data = await get_latest_intelligence()
        return data
    except Exception as e:
        logger.error(f"Error fetching market intelligence: {e}")
        return {
            "what_happened": "Market intelligence temporarily unavailable.",
            "why_it_matters": "CoinStats data is collected automatically on a schedule.",
            "what_amarktai_is_doing": "AmarktAI Crypto continues operating with available signals.",
            "confidence": "Pending",
            "mood": "neutral",
            "top_risk": "none",
            "source": "CoinStats",
            "updated_at": None,
        }
