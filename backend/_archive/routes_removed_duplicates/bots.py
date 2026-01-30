from fastapi import HTTPException, Depends, APIRouter
from datetime import datetime, timezone, timedelta
from typing import Optional, List
import logging

from models import User, UserLogin, Bot, BotCreate, APIKey, APIKeyCreate, Trade, SystemMode, Alert, ChatMessage, BotRiskMode
import database as db
from auth import create_access_token, get_current_user, get_password_hash, verify_password
from realtime_events import rt_events

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["Bots"])
from trading_scheduler import trading_scheduler


@router.get("/bots")
async def get_bots(user_id: str = Depends(get_current_user)):
    """Get all non-deleted bots for the current user
    
    Filters out bots with status='deleted' to ensure deleted bots
    don't appear in the UI after deletion.
    """
    bots = await db.bots_collection.find(
        {
            "user_id": user_id,
            "status": {"$ne": "deleted"}  # Exclude soft-deleted bots
        },
        {"_id": 0}
    ).to_list(1000)
    return bots


@router.post("/bots/{bot_id}/start")
async def start_bot(bot_id: str, user_id: str = Depends(get_current_user)):
    """Start/resume a bot
    
    Args:
        bot_id: Bot ID to start
        user_id: Current user ID from auth
        
    Returns:
        Updated bot status
    """
    try:
        # Verify bot belongs to user
        bot = await db.bots_collection.find_one({"id": bot_id, "user_id": user_id}, {"_id": 0})
        if not bot:
            raise HTTPException(status_code=404, detail="Bot not found")
        
        # Check if bot is in live training bay
        if bot.get('trading_mode') == 'live' and bot.get('in_live_training_bay'):
            import os
            LIVE_MIN_TRAINING_HOURS = int(os.getenv('LIVE_MIN_TRAINING_HOURS', '24'))
            created_at = bot.get('created_at') or bot.get('spawned_at')
            if created_at:
                if isinstance(created_at, str):
                    created_dt = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                else:
                    created_dt = created_at
                
                if created_dt.tzinfo is None:
                    created_dt = created_dt.replace(tzinfo=timezone.utc)
                
                hours_elapsed = (datetime.now(timezone.utc) - created_dt).total_seconds() / 3600
                
                if hours_elapsed < LIVE_MIN_TRAINING_HOURS:
                    return {
                        "success": False,
                        "message": f"❌ Bot in Live Training Bay - must wait {LIVE_MIN_TRAINING_HOURS}h before trading",
                        "hours_remaining": round(LIVE_MIN_TRAINING_HOURS - hours_elapsed, 1)
                    }
        
        # Start the bot
        await db.bots_collection.update_one(
            {"id": bot_id},
            {"$set": {
                "status": "active",
                "started_at": datetime.now(timezone.utc).isoformat(),
                "paused_at": None,
                "pause_reason": None
            }}
        )
        
        # Get updated bot
        updated_bot = await db.bots_collection.find_one({"id": bot_id}, {"_id": 0})
        
        # Emit realtime event
        await rt_events.bot_resumed(user_id, updated_bot)
        
        logger.info(f"✅ Bot {bot['name']} started")
        
        return {
            "success": True,
            "message": f"Bot '{bot['name']}' started",
            "bot": updated_bot
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Start bot error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/bots/{bot_id}/stop")
async def stop_bot(bot_id: str, user_id: str = Depends(get_current_user)):
    """Stop/pause a bot
    
    Args:
        bot_id: Bot ID to stop
        user_id: Current user ID from auth
        
    Returns:
        Updated bot status
    """
    try:
        # Verify bot belongs to user
        bot = await db.bots_collection.find_one({"id": bot_id, "user_id": user_id}, {"_id": 0})
        if not bot:
            raise HTTPException(status_code=404, detail="Bot not found")
        
        # Stop the bot
        await db.bots_collection.update_one(
            {"id": bot_id},
            {"$set": {
                "status": "paused",
                "paused_at": datetime.now(timezone.utc).isoformat(),
                "pause_reason": "Manually stopped by user"
            }}
        )
        
        # Get updated bot
        updated_bot = await db.bots_collection.find_one({"id": bot_id}, {"_id": 0})
        
        # Emit realtime event
        await rt_events.bot_paused(user_id, updated_bot)
        
        logger.info(f"⏸️ Bot {bot['name']} stopped")
        
        return {
            "success": True,
            "message": f"Bot '{bot['name']}' stopped",
            "bot": updated_bot
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Stop bot error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
