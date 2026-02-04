"""
Bot Lifecycle Control Endpoints - Pause, Resume, Start

Idempotent endpoints for controlling bot state with realtime event broadcasting.
"""

from fastapi import APIRouter, HTTPException, Depends
from datetime import datetime, timezone
import logging
from typing import Dict

from auth import get_current_user
import database as db
from realtime_events import manager

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/bots/{bot_id}/pause")
async def pause_bot(bot_id: str, user_id: str = Depends(get_current_user)):
    """
    Pause a bot (idempotent)
    
    Sets bot status to 'paused' and emits realtime event.
    If bot is already paused, returns success without error.
    """
    try:
        # Check bot exists and belongs to user
        bot = await db.bots_collection.find_one(
            {"id": bot_id, "user_id": user_id},
            {"_id": 0}
        )
        
        if not bot:
            raise HTTPException(status_code=404, detail="Bot not found")
        
        # Check if deleted
        if bot.get("status") == "deleted" or bot.get("deleted_at"):
            raise HTTPException(status_code=410, detail="Bot has been deleted")
        
        # If already paused, return success (idempotent)
        if bot.get("status") == "paused":
            logger.info(f"Bot {bot_id} already paused (idempotent)")
            return {
                "success": True,
                "bot_id": bot_id,
                "status": "paused",
                "message": "Bot already paused",
                "idempotent": True
            }
        
        # Update bot status to paused
        await db.bots_collection.update_one(
            {"id": bot_id},
            {
                "$set": {
                    "status": "paused",
                    "paused_at": datetime.now(timezone.utc).isoformat(),
                    "paused_by": "user",
                    "paused_reason": "user_requested",  # Canonical field
                    "paused_by_system": False,
                    "paused_by_user": True,
                    "last_status_change": datetime.now(timezone.utc).isoformat()
                }
            }
        )
        
        # Emit realtime event
        await manager.broadcast_json({
            "type": "bot_paused",
            "bot_id": bot_id,
            "user_id": user_id,
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
        
        logger.info(f"Bot {bot_id} paused by user {user_id}")
        
        return {
            "success": True,
            "bot_id": bot_id,
            "status": "paused",
            "message": "Bot paused successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error pausing bot {bot_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/bots/{bot_id}/resume")
async def resume_bot(bot_id: str, user_id: str = Depends(get_current_user)):
    """
    Resume a paused bot (idempotent)
    
    Sets bot status to 'active' and emits realtime event.
    If bot is already active, returns success without error.
    """
    try:
        # Check bot exists and belongs to user
        bot = await db.bots_collection.find_one(
            {"id": bot_id, "user_id": user_id},
            {"_id": 0}
        )
        
        if not bot:
            raise HTTPException(status_code=404, detail="Bot not found")
        
        # Check if deleted
        if bot.get("status") == "deleted" or bot.get("deleted_at"):
            raise HTTPException(status_code=410, detail="Bot has been deleted")
        
        # Check if quarantined
        if bot.get("status") == "quarantined":
            raise HTTPException(
                status_code=400, 
                detail="Cannot resume quarantined bot. Complete training first."
            )
        
        # If already active, return success (idempotent)
        if bot.get("status") == "active":
            logger.info(f"Bot {bot_id} already active (idempotent)")
            return {
                "success": True,
                "bot_id": bot_id,
                "status": "active",
                "message": "Bot already active",
                "idempotent": True
            }
        
        # Update bot status to active
        await db.bots_collection.update_one(
            {"id": bot_id},
            {
                "$set": {
                    "status": "active",
                    "resumed_at": datetime.now(timezone.utc).isoformat(),
                    "last_status_change": datetime.now(timezone.utc).isoformat()
                },
                "$unset": {
                    "paused_at": "",
                    "paused_by": "",
                    "paused_reason": ""
                }
            }
        )
        
        # Emit realtime event
        await manager.broadcast_json({
            "type": "bot_resumed",
            "bot_id": bot_id,
            "user_id": user_id,
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
        
        logger.info(f"Bot {bot_id} resumed by user {user_id}")
        
        return {
            "success": True,
            "bot_id": bot_id,
            "status": "active",
            "message": "Bot resumed successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error resuming bot {bot_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/bots/{bot_id}/start")
async def start_bot(bot_id: str, user_id: str = Depends(get_current_user)):
    """
    Start a bot (idempotent)
    
    Similar to resume but can also start a newly created bot.
    Sets bot status to 'active' and emits realtime event.
    """
    try:
        # Check bot exists and belongs to user
        bot = await db.bots_collection.find_one(
            {"id": bot_id, "user_id": user_id},
            {"_id": 0}
        )
        
        if not bot:
            raise HTTPException(status_code=404, detail="Bot not found")
        
        # Check if deleted
        if bot.get("status") == "deleted" or bot.get("deleted_at"):
            raise HTTPException(status_code=410, detail="Bot has been deleted")
        
        # Check if quarantined
        if bot.get("status") == "quarantined":
            raise HTTPException(
                status_code=400,
                detail="Cannot start quarantined bot. Complete training first."
            )
        
        # If already active, return success (idempotent)
        current_status = bot.get("status", "inactive")
        if current_status == "active":
            logger.info(f"Bot {bot_id} already active (idempotent)")
            return {
                "success": True,
                "bot_id": bot_id,
                "status": "active",
                "message": "Bot already running",
                "idempotent": True
            }
        
        # Update bot status to active
        await db.bots_collection.update_one(
            {"id": bot_id},
            {
                "$set": {
                    "status": "active",
                    "started_at": datetime.now(timezone.utc).isoformat(),
                    "last_status_change": datetime.now(timezone.utc).isoformat()
                },
                "$unset": {
                    "paused_at": "",
                    "paused_by": "",
                    "paused_reason": ""
                }
            }
        )
        
        # Emit realtime event
        await manager.broadcast_json({
            "type": "bot_started",
            "bot_id": bot_id,
            "user_id": user_id,
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
        
        logger.info(f"Bot {bot_id} started by user {user_id}")
        
        return {
            "success": True,
            "bot_id": bot_id,
            "status": "active",
            "message": "Bot started successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error starting bot {bot_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/bots/{bot_id}/status")
async def get_bot_status(bot_id: str, user_id: str = Depends(get_current_user)):
    """
    Get current bot status
    
    Returns detailed status information including:
    - Current status (active, paused, quarantined, deleted)
    - Last status change timestamp
    - Pause/quarantine reasons if applicable
    """
    try:
        bot = await db.bots_collection.find_one(
            {"id": bot_id, "user_id": user_id},
            {"_id": 0, "status": 1, "paused_at": 1, "paused_by": 1, "paused_reason": 1,
             "quarantine_reason": 1, "last_status_change": 1, "deleted_at": 1}
        )
        
        if not bot:
            raise HTTPException(status_code=404, detail="Bot not found")
        
        return {
            "bot_id": bot_id,
            "status": bot.get("status", "unknown"),
            "is_active": bot.get("status") == "active",
            "is_paused": bot.get("status") == "paused",
            "is_quarantined": bot.get("status") == "quarantined",
            "is_deleted": bot.get("status") == "deleted" or bot.get("deleted_at") is not None,
            "paused_at": bot.get("paused_at"),
            "paused_by": bot.get("paused_by"),
            "paused_reason": bot.get("paused_reason"),
            "quarantine_reason": bot.get("quarantine_reason"),
            "last_status_change": bot.get("last_status_change")
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting bot status {bot_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
