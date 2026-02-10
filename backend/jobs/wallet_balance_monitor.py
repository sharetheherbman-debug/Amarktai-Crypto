"""
Wallet Balance Monitoring Job
Periodically fetches and stores exchange balances for all users
"""

import asyncio
from datetime import datetime, timezone
import logging

import database as db
from engines.wallet_manager import wallet_manager
from realtime_events import rt_events

logger = logging.getLogger(__name__)


class WalletBalanceMonitor:
    """Background job to monitor wallet balances"""
    
    def __init__(self):
        self.check_interval = 300  # Check every 5 minutes
        self.is_running = False
        self.task = None
    
    async def monitor_loop(self):
        """Main monitoring loop"""
        logger.info("🔍 Wallet balance monitor started")
        
        while self.is_running:
            try:
                await self.update_all_balances()
                await asyncio.sleep(self.check_interval)
            except Exception as e:
                logger.error(f"Balance monitor error: {e}")
                await asyncio.sleep(60)
    
    async def update_all_balances(self):
        """Update balances for all users"""
        try:
            # Get all active users
            users = await db.users_collection.find(
                {"status": {"$ne": "blocked"}},
                {"_id": 0, "id": 1}
            ).to_list(1000)
            
            for user in users:
                user_id = user['id']
                await self.update_user_balances(user_id)
            
            logger.debug(f"✅ Updated balances for {len(users)} users")
            
        except Exception as e:
            logger.error(f"Update all balances error: {e}")
    
    async def update_user_balances(self, user_id: str):
        """Update balances for a specific user"""
        try:
            # Get master wallet balance
            master_balance = await wallet_manager.get_master_balance(user_id)
            
            # Get all exchange balances
            from config.platforms import SUPPORTED_PLATFORMS
            exchanges = SUPPORTED_PLATFORMS
            exchange_balances = {}
            
            for exchange in exchanges:
                balance = await wallet_manager.get_exchange_balance(user_id, exchange)
                if not balance.get('error'):
                    exchange_balances[exchange] = balance
            
            # Store in database
            balance_doc = {
                "user_id": user_id,
                "master_wallet": master_balance,
                "exchanges": exchange_balances,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "last_updated": datetime.now(timezone.utc).isoformat()
            }
            
            # Upsert balance document
            if db.wallet_balances_collection is None:
                logger.warning("wallet_balances_collection not initialized")
                return

            result = await db.wallet_balances_collection.update_one(
                {"user_id": user_id},
                {"$set": balance_doc},
                upsert=True
            )
            
            # Emit WebSocket event for real-time UI updates
            if result.modified_count > 0 or result.upserted_id:
                try:
                    await rt_events.balance_updated(user_id, balance_doc)
                    await rt_events.wallet_update(user_id, {
                        "master": master_balance,
                        "exchanges": exchange_balances,
                        "timestamp": balance_doc["timestamp"]
                    })
                except Exception as ws_error:
                    logger.debug(f"WebSocket emission error: {ws_error}")
            
        except Exception as e:
            logger.debug(f"Update user balance error for {user_id[:8]}: {e}")
    
    def start(self):
        """Start the monitoring job"""
        if not self.is_running:
            self.is_running = True
            self.task = asyncio.create_task(self.monitor_loop())
            logger.info("✅ Wallet balance monitor started")
    
    def stop(self):
        """Stop the monitoring job"""
        self.is_running = False
        if self.task:
            self.task.cancel()
        logger.info("🛑 Wallet balance monitor stopped")

# Global instance
wallet_balance_monitor = WalletBalanceMonitor()
