"""
Bot-to-Bot Coordinator - Dibs & Pivot System
ToS-Safe: Prevents bots from stepping on each other's trades

Coordination prevents simultaneous trades on same pair/exchange.
When conflict detected, other bots pivot/skip/reduce.
"""

import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional
from enum import Enum

import database as db
from realtime_events import manager

logger = logging.getLogger(__name__)


class CoordinationAction(str, Enum):
    """Actions bots can take on coordination conflict"""
    PIVOT = "pivot"  # Trade different pair
    SKIP = "skip"  # Skip this trade
    REDUCE = "reduce"  # Reduce trade size
    WAIT = "wait"  # Wait for lock to expire


class BotCoordinator:
    """
    Coordinate trading between multiple bots
    Prevents conflicts using lock-based "dibs" system
    """
    
    def __init__(self):
        self.lock_ttl_seconds = 60  # Lock expires after 60 seconds
        self.max_lock_retries = 3
        
    async def request_dibs(
        self,
        bot_id: str,
        user_id: str,
        exchange: str,
        pair: str,
        trade_type: str,
        amount: float,
        priority: int = 0
    ) -> Dict:
        """
        Request exclusive trading rights (dibs) for a pair
        
        Args:
            bot_id: Bot requesting dibs
            user_id: User ID
            exchange: Exchange name
            pair: Trading pair
            trade_type: 'buy' or 'sell'
            amount: Trade amount
            priority: Bot priority (higher = more important)
            
        Returns:
            Dict with granted status and lock_id
        """
        try:
            lock_key = f"{exchange}:{pair}"
            
            # Check for existing lock
            existing_lock = await db.db["coordination_locks"].find_one({
                "lock_key": lock_key,
                "user_id": user_id,
                "expires_at": {"$gt": datetime.now(timezone.utc).isoformat()}
            })
            
            if existing_lock:
                # Lock exists - check if it's this bot or another
                if existing_lock["bot_id"] == bot_id:
                    # Extend lock for same bot
                    new_expiry = datetime.now(timezone.utc) + timedelta(seconds=self.lock_ttl_seconds)
                    await db.db["coordination_locks"].update_one(
                        {"_id": existing_lock["_id"]},
                        {
                            "$set": {
                                "expires_at": new_expiry.isoformat(),
                                "updated_at": datetime.now(timezone.utc).isoformat()
                            }
                        }
                    )
                    
                    return {
                        "granted": True,
                        "lock_id": existing_lock["lock_id"],
                        "message": "Lock extended",
                        "expires_at": new_expiry.isoformat()
                    }
                else:
                    # Lock held by another bot - conflict!
                    conflict_result = await self._handle_conflict(
                        bot_id=bot_id,
                        user_id=user_id,
                        exchange=exchange,
                        pair=pair,
                        existing_lock=existing_lock,
                        priority=priority
                    )
                    
                    return conflict_result
            
            # No existing lock - grant dibs
            lock_id = f"lock_{bot_id}_{datetime.now(timezone.utc).timestamp()}"
            expires_at = datetime.now(timezone.utc) + timedelta(seconds=self.lock_ttl_seconds)
            
            lock_doc = {
                "lock_id": lock_id,
                "lock_key": lock_key,
                "bot_id": bot_id,
                "user_id": user_id,
                "exchange": exchange,
                "pair": pair,
                "trade_type": trade_type,
                "amount": amount,
                "priority": priority,
                "granted_at": datetime.now(timezone.utc).isoformat(),
                "expires_at": expires_at.isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat()
            }
            
            await db.db["coordination_locks"].insert_one(lock_doc)
            
            # Emit dibs granted event
            await manager.broadcast_to_user(user_id, {
                "type": "dibs_granted",
                "bot_id": bot_id,
                "exchange": exchange,
                "pair": pair,
                "lock_id": lock_id,
                "expires_at": expires_at.isoformat(),
                "timestamp": datetime.now(timezone.utc).isoformat()
            })
            
            logger.info(f"Dibs granted: bot={bot_id}, {exchange}:{pair}")
            
            return {
                "granted": True,
                "lock_id": lock_id,
                "message": "Dibs granted",
                "expires_at": expires_at.isoformat()
            }
            
        except Exception as e:
            logger.error(f"Request dibs failed: {e}")
            return {
                "granted": False,
                "error": str(e),
                "action": CoordinationAction.SKIP
            }
    
    async def release_dibs(self, lock_id: str, bot_id: str) -> Dict:
        """
        Release trading lock
        
        Args:
            lock_id: Lock ID to release
            bot_id: Bot releasing the lock
            
        Returns:
            Dict with release status
        """
        try:
            result = await db.db["coordination_locks"].delete_one({
                "lock_id": lock_id,
                "bot_id": bot_id
            })
            
            if result.deleted_count > 0:
                logger.info(f"Dibs released: lock={lock_id}, bot={bot_id}")
                return {"success": True, "message": "Lock released"}
            else:
                return {"success": False, "message": "Lock not found or already released"}
                
        except Exception as e:
            logger.error(f"Release dibs failed: {e}")
            return {"success": False, "error": str(e)}
    
    async def _handle_conflict(
        self,
        bot_id: str,
        user_id: str,
        exchange: str,
        pair: str,
        existing_lock: Dict,
        priority: int
    ) -> Dict:
        """
        Handle coordination conflict when another bot holds the lock
        
        Strategy:
        1. If requesting bot has higher priority, suggest wait
        2. Otherwise, suggest alternative action (pivot, skip, reduce)
        """
        try:
            # Compare priorities
            existing_priority = existing_lock.get("priority", 0)
            
            if priority > existing_priority:
                # Requesting bot has higher priority - suggest wait
                action = CoordinationAction.WAIT
                suggestion = {
                    "action": action,
                    "wait_seconds": 30,
                    "message": f"Higher priority bot. Wait for lock expiry."
                }
            else:
                # Existing bot has equal or higher priority
                # Suggest alternative action based on situation
                action = await self._suggest_alternative_action(
                    user_id=user_id,
                    exchange=exchange,
                    pair=pair,
                    conflicting_bot=existing_lock["bot_id"]
                )
                
                suggestion = {
                    "action": action,
                    "message": f"Lock held by bot {existing_lock['bot_id']}. Suggested action: {action}"
                }
                
                if action == CoordinationAction.PIVOT:
                    # Suggest alternative pair
                    alt_pairs = await self._get_alternative_pairs(exchange, pair)
                    suggestion["alternative_pairs"] = alt_pairs
                
                elif action == CoordinationAction.REDUCE:
                    # Suggest reduced size
                    suggestion["size_multiplier"] = 0.5  # Trade half size
            
            # Emit conflict event
            await manager.broadcast_to_user(user_id, {
                "type": "dibs_conflict",
                "bot_id": bot_id,
                "exchange": exchange,
                "pair": pair,
                "conflicting_bot": existing_lock["bot_id"],
                "suggested_action": action,
                "timestamp": datetime.now(timezone.utc).isoformat()
            })
            
            logger.info(f"Dibs conflict: bot={bot_id}, {exchange}:{pair}, action={action}")
            
            return {
                "granted": False,
                "conflict": True,
                "conflicting_bot": existing_lock["bot_id"],
                "conflicting_lock_expires": existing_lock["expires_at"],
                **suggestion
            }
            
        except Exception as e:
            logger.error(f"Conflict handling failed: {e}")
            return {
                "granted": False,
                "error": str(e),
                "action": CoordinationAction.SKIP
            }
    
    async def _suggest_alternative_action(
        self,
        user_id: str,
        exchange: str,
        pair: str,
        conflicting_bot: str
    ) -> CoordinationAction:
        """
        Suggest alternative action for bot on conflict
        
        Logic:
        - If many alternative pairs available: PIVOT
        - If low system load: WAIT
        - If high system load: SKIP
        - Default: REDUCE (trade smaller size on same pair later)
        """
        try:
            # Check how many pairs have active locks
            active_locks = await db.db["coordination_locks"].count_documents({
                "user_id": user_id,
                "exchange": exchange,
                "expires_at": {"$gt": datetime.now(timezone.utc).isoformat()}
            })
            
            # Check total bot count
            total_bots = await db.bots_collection.count_documents({
                "user_id": user_id,
                "status": "active"
            })
            
            # Decision logic
            if active_locks < total_bots * 0.3:  # Less than 30% of bots active
                # Low contention - suggest pivot to different pair
                return CoordinationAction.PIVOT
            
            elif active_locks < total_bots * 0.6:  # 30-60% active
                # Medium contention - reduce size
                return CoordinationAction.REDUCE
            
            else:
                # High contention - skip this opportunity
                return CoordinationAction.SKIP
            
        except Exception as e:
            logger.error(f"Alternative action suggestion failed: {e}")
            return CoordinationAction.SKIP
    
    async def _get_alternative_pairs(self, exchange: str, original_pair: str) -> List[str]:
        """
        Get alternative trading pairs on same exchange
        
        Returns pairs that don't currently have locks
        """
        try:
            # Get all active pairs on exchange
            # (In production, would query exchange API for markets)
            all_pairs = [
                "BTC/USD", "ETH/USD", "BTC/ZAR", "ETH/ZAR",
                "XRP/USD", "ADA/USD", "SOL/USD", "DOGE/USD"
            ]
            
            # Get locked pairs
            locked_pairs = await db.db["coordination_locks"].distinct("pair", {
                "exchange": exchange,
                "expires_at": {"$gt": datetime.now(timezone.utc).isoformat()}
            })
            
            # Return unlocked pairs (excluding original)
            alternatives = [p for p in all_pairs if p not in locked_pairs and p != original_pair]
            
            return alternatives[:3]  # Return top 3 alternatives
            
        except Exception as e:
            logger.error(f"Get alternative pairs failed: {e}")
            return []
    
    async def get_coordination_status(self, user_id: str) -> Dict:
        """
        Get current coordination status for user's bots
        
        Returns:
            Dict with active locks and coordination stats
        """
        try:
            # Get active locks
            active_locks = await db.db["coordination_locks"].find({
                "user_id": user_id,
                "expires_at": {"$gt": datetime.now(timezone.utc).isoformat()}
            }).to_list(100)
            
            # Group by exchange
            by_exchange = {}
            for lock in active_locks:
                exchange = lock["exchange"]
                if exchange not in by_exchange:
                    by_exchange[exchange] = []
                by_exchange[exchange].append({
                    "bot_id": lock["bot_id"],
                    "pair": lock["pair"],
                    "expires_at": lock["expires_at"]
                })
            
            # Count conflicts in last hour
            one_hour_ago = datetime.now(timezone.utc) - timedelta(hours=1)
            conflicts_1h = await db.db["coordination_conflicts"].count_documents({
                "user_id": user_id,
                "timestamp": {"$gt": one_hour_ago.isoformat()}
            })
            
            return {
                "success": True,
                "active_locks": len(active_locks),
                "locks_by_exchange": by_exchange,
                "conflicts_last_hour": conflicts_1h,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            
        except Exception as e:
            logger.error(f"Get coordination status failed: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    async def cleanup_expired_locks(self):
        """Cleanup expired locks (background task)"""
        try:
            result = await db.db["coordination_locks"].delete_many({
                "expires_at": {"$lt": datetime.now(timezone.utc).isoformat()}
            })
            
            if result.deleted_count > 0:
                logger.info(f"Cleaned up {result.deleted_count} expired coordination locks")
                
        except Exception as e:
            logger.error(f"Lock cleanup failed: {e}")


# Global instance
bot_coordinator = BotCoordinator()


async def cleanup_locks_task():
    """Background task to cleanup expired locks"""
    while True:
        try:
            await bot_coordinator.cleanup_expired_locks()
            await asyncio.sleep(60)  # Run every minute
        except Exception as e:
            logger.error(f"Lock cleanup task error: {e}")
            await asyncio.sleep(60)
