"""
Bot Quarantine & Auto-Retraining Service
Ensures no bots remain paused indefinitely
"""
import asyncio
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict
import logging
import database as db

logger = logging.getLogger(__name__)

# Quarantine durations (in seconds)
QUARANTINE_DURATIONS = {
    1: 3600,      # 1st pause: 1 hour
    2: 10800,     # 2nd pause: 3 hours  
    3: 86400,     # 3rd pause: 24 hours
    4: None       # 4th pause: delete & regenerate
}

NON_STRATEGY_REASON_CODES = {
    "MODE_DISABLED",
    "NO_EXCHANGE_KEYS",
    "UNSUPPORTED_EXCHANGE",
    "USER_PAUSED"
}

class BotQuarantineService:
    def __init__(self):
        self.running = False
        self.check_interval = 60  # Check every minute
        
    async def quarantine_bot(self, bot_id: str, reason: str, metadata: Optional[Dict] = None) -> Dict:
        """
        Place bot in quarantine with auto-retraining
        
        Returns:
            {
                "quarantine_count": int,
                "quarantine_duration_seconds": int,
                "retraining_until": str (ISO timestamp),
                "action": "retraining" | "deletion"
            }
        """
        try:
            metadata = metadata or {}

            # Get bot document
            bot = await db.bots_collection.find_one({"id": bot_id})
            if not bot:
                return {"error": "Bot not found"}

            trading_mode = str(bot.get("trading_mode") or bot.get("mode") or "paper").strip().lower()
            is_paper = trading_mode.startswith("paper")
            reason_code = str(metadata.get("reason_code") or reason or "").strip().upper().replace(" ", "_")

            if is_paper and reason_code == "MODE_DISABLED":
                return {
                    "quarantine_count": bot.get("quarantine_count", 0),
                    "action": "skipped",
                    "message": "Paper bot not quarantined for MODE_DISABLED"
                }
            
            # Increment quarantine count
            quarantine_count = bot.get("quarantine_count", 0) + 1
            
            # Determine action based on count
            if quarantine_count >= 4:
                # 4th pause: Delete and regenerate
                logger.warning(f"🗑️ Bot {bot_id[:8]} reached 4th pause - marking for deletion")
                
                await db.bots_collection.update_one(
                    {"id": bot_id},
                    {
                        "$set": {
                            "status": "marked_for_deletion",
                            "quarantine_count": quarantine_count,
                            "deletion_scheduled_at": datetime.now(timezone.utc).isoformat(),
                            "deletion_reason": "Exceeded max quarantine attempts"
                        }
                    }
                )
                
                # Schedule bot regeneration (will be handled by async task)
                return {
                    "quarantine_count": quarantine_count,
                    "action": "deletion",
                    "message": "Bot marked for deletion and regeneration"
                }
            else:
                # 1st/2nd/3rd pause: Quarantine with retraining
                duration = QUARANTINE_DURATIONS[quarantine_count]
                if is_paper and reason_code in NON_STRATEGY_REASON_CODES:
                    duration = min(duration, 60)
                retraining_until = datetime.now(timezone.utc) + timedelta(seconds=duration)
                
                logger.info(f"🔒 Bot {bot_id[:8]} entering quarantine #{quarantine_count} for {duration/3600:.1f} hours")
                
                await db.bots_collection.update_one(
                    {"id": bot_id},
                    {
                        "$set": {
                            "status": "quarantined",
                            "quarantine_count": quarantine_count,
                            "quarantine_reason": reason,
                            "quarantine_reason_code": reason_code,
                            "quarantine_source": metadata.get("source", "quarantine"),
                            "quarantine_rule": metadata.get("rule", "manual_quarantine"),
                            "quarantine_threshold": metadata.get("threshold"),
                            "last_intervention": {
                                "source": metadata.get("source", "quarantine"),
                                "rule": metadata.get("rule", "manual_quarantine"),
                                "reason_code": reason_code,
                                "threshold": metadata.get("threshold"),
                                "reason": reason,
                                "mode": trading_mode,
                                "timestamp": datetime.now(timezone.utc).isoformat()
                            },
                            "quarantined_at": datetime.now(timezone.utc).isoformat(),
                            "retraining_until": retraining_until.isoformat(),
                            "quarantine_duration_seconds": duration
                        }
                    }
                )
                
                return {
                    "quarantine_count": quarantine_count,
                    "quarantine_duration_seconds": duration,
                    "retraining_until": retraining_until.isoformat(),
                    "action": "retraining",
                    "message": f"Bot in retraining for {duration/3600:.1f} hours"
                }
                
        except Exception as e:
            logger.error(f"Quarantine bot error: {e}")
            return {"error": str(e)}
    
    async def check_quarantine_timeouts(self):
        """Check for bots that completed retraining and redeploy them"""
        try:
            now = datetime.now(timezone.utc)
            
            # Find bots whose retraining period has expired
            quarantined_bots = await db.bots_collection.find({
                "status": "quarantined",
                "retraining_until": {"$lte": now.isoformat()}
            }).to_list(100)
            
            for bot in quarantined_bots:
                bot_id = bot["id"]
                logger.info(f"✅ Bot {bot_id[:8]} completed retraining - redeploying")
                
                # Redeploy bot (change status back to active)
                await db.bots_collection.update_one(
                    {"id": bot_id},
                    {
                        "$set": {
                            "status": "active",
                            "redeployed_at": now.isoformat()
                        },
                        "$unset": {
                            "quarantine_reason": "",
                            "quarantined_at": "",
                            "retraining_until": "",
                            "quarantine_duration_seconds": ""
                        }
                    }
                )
                
                # Emit realtime event
                try:
                    from realtime_events import rt_events
                    await rt_events.bot_status_changed(
                        bot["user_id"], 
                        bot_id, 
                        "active", 
                        f"Retraining completed (attempt #{bot.get('quarantine_count', 0)})"
                    )
                except Exception as e:
                    logger.warning(f"Failed to emit bot_status_changed event: {e}")
                    
        except Exception as e:
            logger.error(f"Check quarantine timeouts error: {e}")
    
    async def handle_bot_deletions(self):
        """Handle bots marked for deletion - delete and regenerate"""
        try:
            # Find bots marked for deletion
            bots_to_delete = await db.bots_collection.find({
                "status": "marked_for_deletion"
            }).to_list(100)
            
            for bot in bots_to_delete:
                bot_id = bot["id"]
                user_id = bot["user_id"]
                
                logger.warning(f"🗑️ Deleting bot {bot_id[:8]} after 4 quarantine failures")
                
                # Delete bot and its trades
                await db.bots_collection.delete_one({"id": bot_id})
                await db.trades_collection.delete_many({"bot_id": bot_id})
                
                # Auto-generate replacement bot
                logger.info(f"🤖 Auto-generating replacement bot for user {user_id[:8]}")
                
                # Create new bot with similar config
                import uuid
                new_bot_id = str(uuid.uuid4())
                new_bot = {
                    "id": new_bot_id,
                    "user_id": user_id,
                    "name": bot.get("name", "Bot") + " (Auto-Regenerated)",
                    "exchange": bot.get("exchange", "binance"),
                    "mode": "paper",  # Always start in paper mode
                    "status": "active",
                    "initial_capital": bot.get("initial_capital", 1000.0),
                    "current_capital": bot.get("initial_capital", 1000.0),
                    "quarantine_count": 0,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "auto_generated": True,
                    "replaced_bot_id": bot_id
                }
                
                await db.bots_collection.insert_one(new_bot)
                
                logger.info(f"✅ Created replacement bot {new_bot_id[:8]}")
                
                # Emit realtime event
                try:
                    from realtime_events import rt_events
                    await rt_events.bot_status_changed(
                        user_id, 
                        new_bot_id, 
                        "active", 
                        f"Auto-generated to replace failing bot"
                    )
                except Exception as e:
                    logger.warning(f"Failed to emit bot_status_changed event: {e}")
                    
        except Exception as e:
            logger.error(f"Handle bot deletions error: {e}")
    
    async def run(self):
        """Main quarantine service loop"""
        self.running = True
        logger.info("🔒 Bot Quarantine Service started")
        
        while self.running:
            try:
                # Check for completed retraining periods
                await self.check_quarantine_timeouts()
                
                # Handle bot deletions and regenerations
                await self.handle_bot_deletions()
                
                # Sleep before next check
                await asyncio.sleep(self.check_interval)
                
            except Exception as e:
                logger.error(f"Quarantine service error: {e}")
                await asyncio.sleep(self.check_interval)
    
    def stop(self):
        """Stop the quarantine service"""
        self.running = False
        logger.info("🔒 Bot Quarantine Service stopped")

# Global instance
quarantine_service = BotQuarantineService()
