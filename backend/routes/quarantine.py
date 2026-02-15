"""
Bot Quarantine API Endpoints
"""
from fastapi import APIRouter, Depends, HTTPException
from typing import List, Dict
from datetime import datetime, timezone
import logging

from auth import get_current_user
import database as db
from services.bot_quarantine import quarantine_service, QUARANTINE_DURATIONS

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/quarantine", tags=["Bot Quarantine"])

@router.get("/status")
async def get_quarantine_status(user_id: str = Depends(get_current_user)):
    """Get all quarantined bots for current user with countdown timers"""
    try:
        # Find user's quarantined bots
        quarantined = await db.bots_collection.find({
            "user_id": user_id,
            "status": "quarantined"
        }).to_list(100)
        
        now = datetime.now(timezone.utc)
        
        result = []
        for bot in quarantined:
            retraining_until = datetime.fromisoformat(bot.get("retraining_until", now.isoformat()))
            remaining_seconds = max(0, int((retraining_until - now).total_seconds()))
            
            result.append({
                "bot_id": bot["id"],
                "bot_name": bot.get("name"),
                "quarantine_count": bot.get("quarantine_count", 1),
                "quarantine_reason": bot.get("quarantine_reason"),
                "quarantine_reason_code": bot.get("quarantine_reason_code"),
                "quarantine_source": bot.get("quarantine_source"),
                "quarantine_rule": bot.get("quarantine_rule"),
                "quarantine_threshold": bot.get("quarantine_threshold"),
                "last_intervention": bot.get("last_intervention"),
                "quarantined_at": bot.get("quarantined_at"),
                "retraining_until": bot.get("retraining_until"),
                "remaining_seconds": remaining_seconds,
                "remaining_hours": round(remaining_seconds / 3600, 1),
                "next_action": "redeploy" if bot.get("quarantine_count", 0) < 4 else "delete"
            })
        
        return {
            "success": True,
            "quarantined_bots": result,
            "total": len(result)
        }
        
    except Exception as e:
        logger.error(f"Get quarantine status error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/history")
async def get_quarantine_history(user_id: str = Depends(get_current_user)):
    """Get quarantine history for user's bots"""
    try:
        # Find bots that have been quarantined (count > 0)
        bots = await db.bots_collection.find({
            "user_id": user_id,
            "quarantine_count": {"$gt": 0}
        }).to_list(100)
        
        result = []
        for bot in bots:
            result.append({
                "bot_id": bot["id"],
                "bot_name": bot.get("name"),
                "status": bot.get("status"),
                "quarantine_count": bot.get("quarantine_count", 0),
                "quarantine_reason_code": bot.get("quarantine_reason_code"),
                "quarantine_source": bot.get("quarantine_source"),
                "quarantine_rule": bot.get("quarantine_rule"),
                "last_intervention": bot.get("last_intervention"),
                "last_quarantined_at": bot.get("quarantined_at"),
                "last_redeployed_at": bot.get("redeployed_at"),
                "marked_for_deletion": bot.get("status") == "marked_for_deletion"
            })
        
        return {
            "success": True,
            "bots": result,
            "total": len(result)
        }
        
    except Exception as e:
        logger.error(f"Get quarantine history error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/config")
async def get_quarantine_config():
    """Get quarantine duration configuration"""
    return {
        "success": True,
        "durations": {
            "first_pause_hours": QUARANTINE_DURATIONS[1] / 3600,
            "second_pause_hours": QUARANTINE_DURATIONS[2] / 3600,
            "third_pause_hours": QUARANTINE_DURATIONS[3] / 3600,
            "fourth_pause_action": "delete_and_regenerate"
        }
    }
