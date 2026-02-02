"""
Balance Sync Service
Real-time balance fetching from all 7 exchanges using CCXT
Stores snapshots, detects deposits/withdrawals, emits realtime events

Features:
- Fetches balances from all 7 exchanges (luno, binance, kucoin, bybit, kraken, bitget, gate)
- Stores balance snapshots in balance_snapshots collection
- Detects deposits/withdrawals by comparing snapshots
- Emits wallet_balance_updated realtime events
- Runs every 5 minutes as background task
- Graceful error handling (logs and continues)
- Handles missing API keys gracefully
"""

import asyncio
import logging
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timezone

import database as db
from config.platforms import SUPPORTED_PLATFORMS, get_platform_config
from ccxt_service import CCXTService
from realtime_events import manager

logger = logging.getLogger(__name__)


class BalanceSyncService:
    """Real-time balance synchronization across all exchanges"""
    
    def __init__(self):
        self.ccxt_service = CCXTService()
        self.is_running = False
        self.sync_task = None
        self.sync_interval = 300  # 5 minutes
    
    async def fetch_exchange_balance(
        self, 
        user_id: str, 
        exchange: str,
        api_key: str,
        api_secret: str,
        passphrase: Optional[str] = None
    ) -> Dict:
        """
        Fetch balance from a single exchange
        
        Args:
            user_id: User ID
            exchange: Exchange name
            api_key: API key
            api_secret: API secret
            passphrase: Optional passphrase (for kucoin, bitget)
            
        Returns:
            Dict with balance data or error
        """
        try:
            # Get platform config for CCXT ID
            platform_config = get_platform_config(exchange)
            if not platform_config:
                return {
                    "success": False,
                    "exchange": exchange,
                    "error": f"Unknown exchange: {exchange}"
                }
            
            ccxt_id = platform_config.get("ccxt_id", exchange)
            
            # Initialize exchange
            exchange_instance = self.ccxt_service.init_exchange(
                ccxt_id,
                api_key,
                api_secret,
                testnet=False,
                passphrase=passphrase
            )
            
            # Fetch balance using asyncio.to_thread for blocking CCXT call
            balance_data = await asyncio.to_thread(exchange_instance.fetch_balance)
            
            # Extract relevant balances (non-zero free, used, total)
            balances = {}
            for currency, amounts in balance_data.items():
                if currency in ['free', 'used', 'total', 'info']:
                    continue
                
                if isinstance(amounts, dict):
                    free = amounts.get('free', 0)
                    used = amounts.get('used', 0)
                    total = amounts.get('total', 0)
                    
                    # Only include currencies with non-zero balance
                    if total > 0:
                        balances[currency] = {
                            "free": free,
                            "used": used,
                            "total": total
                        }
            
            return {
                "success": True,
                "exchange": exchange,
                "balances": balances,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            
        except Exception as e:
            logger.error(f"Failed to fetch balance from {exchange} for user {user_id[:8]}: {e}")
            return {
                "success": False,
                "exchange": exchange,
                "error": str(e),
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
    
    async def fetch_all_balances(self, user_id: str) -> Dict:
        """
        Fetch balances from all exchanges for a user
        
        Args:
            user_id: User ID
            
        Returns:
            Dict with balances from all exchanges
        """
        try:
            # Get user's API keys for all exchanges
            api_keys = await db.api_keys_collection.find(
                {"user_id": user_id},
                {"_id": 0}
            ).to_list(100)
            
            if not api_keys:
                logger.info(f"No API keys found for user {user_id[:8]}")
                return {
                    "user_id": user_id,
                    "exchanges": {},
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "message": "No API keys configured"
                }
            
            # Create tasks for all exchanges
            tasks = []
            key_mapping = {}
            
            for key_doc in api_keys:
                provider = key_doc.get("provider", "").lower()
                
                # Only process supported platforms
                if provider not in SUPPORTED_PLATFORMS:
                    continue
                
                api_key = key_doc.get("api_key")
                api_secret = key_doc.get("api_secret")
                passphrase = key_doc.get("passphrase")
                
                if not api_key or not api_secret:
                    logger.warning(f"Incomplete API key for {provider}, skipping")
                    continue
                
                # Decrypt keys if encrypted (assuming they are stored encrypted)
                # For now, assuming they are already decrypted or using plaintext in dev
                
                task = self.fetch_exchange_balance(
                    user_id,
                    provider,
                    api_key,
                    api_secret,
                    passphrase
                )
                tasks.append(task)
                key_mapping[provider] = key_doc.get("id")
            
            # Fetch all balances concurrently
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Process results
            exchanges = {}
            successful_syncs = 0
            failed_syncs = 0
            
            for result in results:
                if isinstance(result, Exception):
                    logger.error(f"Balance fetch exception: {result}")
                    failed_syncs += 1
                    continue
                
                exchange = result.get("exchange", "unknown")
                
                if result.get("success"):
                    exchanges[exchange] = {
                        "balances": result.get("balances", {}),
                        "timestamp": result.get("timestamp"),
                        "status": "success"
                    }
                    successful_syncs += 1
                else:
                    exchanges[exchange] = {
                        "error": result.get("error", "Unknown error"),
                        "timestamp": result.get("timestamp"),
                        "status": "failed"
                    }
                    failed_syncs += 1
            
            logger.info(
                f"Balance sync for user {user_id[:8]}: "
                f"{successful_syncs} successful, {failed_syncs} failed"
            )
            
            return {
                "user_id": user_id,
                "exchanges": exchanges,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "successful_syncs": successful_syncs,
                "failed_syncs": failed_syncs
            }
            
        except Exception as e:
            logger.error(f"Fetch all balances error for user {user_id[:8]}: {e}")
            return {
                "user_id": user_id,
                "exchanges": {},
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "error": str(e)
            }
    
    async def store_balance_snapshot(self, user_id: str, balance_data: Dict) -> bool:
        """
        Store balance snapshot in database
        
        Args:
            user_id: User ID
            balance_data: Balance data to store
            
        Returns:
            True if stored successfully, False otherwise
        """
        try:
            snapshot = {
                "user_id": user_id,
                "exchanges": balance_data.get("exchanges", {}),
                "timestamp": balance_data.get("timestamp"),
                "successful_syncs": balance_data.get("successful_syncs", 0),
                "failed_syncs": balance_data.get("failed_syncs", 0)
            }
            
            await db.balance_snapshots_collection.insert_one(snapshot)
            
            return True
            
        except Exception as e:
            logger.error(f"Store balance snapshot error: {e}")
            return False
    
    async def detect_balance_changes(
        self, 
        user_id: str, 
        current_balances: Dict,
        previous_balances: Optional[Dict] = None
    ) -> List[Dict]:
        """
        Detect deposits/withdrawals by comparing balance snapshots
        
        Args:
            user_id: User ID
            current_balances: Current balance data
            previous_balances: Previous balance data (if None, fetch from DB)
            
        Returns:
            List of detected changes (deposits/withdrawals)
        """
        try:
            # Get previous snapshot if not provided
            if previous_balances is None:
                previous_snapshot = await db.balance_snapshots_collection.find_one(
                    {"user_id": user_id},
                    {"_id": 0},
                    sort=[("timestamp", -1)]
                )
                
                if not previous_snapshot:
                    logger.debug(f"No previous snapshot for user {user_id[:8]}, skipping change detection")
                    return []
                
                previous_balances = previous_snapshot.get("exchanges", {})
            
            changes = []
            current_exchanges = current_balances.get("exchanges", {})
            
            # Compare balances for each exchange
            for exchange, current_data in current_exchanges.items():
                if current_data.get("status") != "success":
                    continue
                
                current_bals = current_data.get("balances", {})
                previous_data = previous_balances.get(exchange, {})
                previous_bals = previous_data.get("balances", {})
                
                # Check each currency
                for currency, current_amounts in current_bals.items():
                    current_total = current_amounts.get("total", 0)
                    previous_total = previous_bals.get(currency, {}).get("total", 0)
                    
                    difference = current_total - previous_total
                    
                    # Detect significant changes (> 0.01 to avoid floating point noise)
                    if abs(difference) > 0.01:
                        change_type = "deposit" if difference > 0 else "withdrawal"
                        
                        changes.append({
                            "user_id": user_id,
                            "exchange": exchange,
                            "currency": currency,
                            "type": change_type,
                            "amount": abs(difference),
                            "previous_balance": previous_total,
                            "current_balance": current_total,
                            "timestamp": current_balances.get("timestamp"),
                            "detected_at": datetime.now(timezone.utc).isoformat()
                        })
                        
                        logger.info(
                            f"💰 Detected {change_type} for user {user_id[:8]}: "
                            f"{abs(difference):.8f} {currency} on {exchange}"
                        )
            
            return changes
            
        except Exception as e:
            logger.error(f"Detect balance changes error: {e}")
            return []
    
    async def sync_user_balances(self, user_id: str) -> Dict:
        """
        Sync balances for a single user
        Main orchestration method
        
        Args:
            user_id: User ID
            
        Returns:
            Dict with sync results
        """
        try:
            # Fetch all balances
            balance_data = await self.fetch_all_balances(user_id)
            
            # Detect changes
            changes = await self.detect_balance_changes(user_id, balance_data)
            
            # Store snapshot
            snapshot_stored = await self.store_balance_snapshot(user_id, balance_data)
            
            # Emit realtime event
            try:
                await manager.send_message(user_id, {
                    "type": "wallet_balance_updated",
                    "exchanges": balance_data.get("exchanges", {}),
                    "changes": changes,
                    "timestamp": balance_data.get("timestamp"),
                    "message": "💰 Wallet balances updated"
                })
            except Exception as e:
                logger.warning(f"Failed to emit realtime event: {e}")
            
            return {
                "success": True,
                "user_id": user_id,
                "successful_syncs": balance_data.get("successful_syncs", 0),
                "failed_syncs": balance_data.get("failed_syncs", 0),
                "changes_detected": len(changes),
                "changes": changes,
                "snapshot_stored": snapshot_stored,
                "timestamp": balance_data.get("timestamp")
            }
            
        except Exception as e:
            logger.error(f"Sync user balances error for user {user_id[:8]}: {e}")
            return {
                "success": False,
                "user_id": user_id,
                "error": str(e),
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
    
    async def sync_all_users(self) -> Dict:
        """
        Sync balances for all users
        Called by background task every 5 minutes
        
        Returns:
            Dict with sync summary
        """
        try:
            # Get all users with API keys
            users_with_keys = await db.api_keys_collection.distinct("user_id")
            
            if not users_with_keys:
                logger.debug("No users with API keys to sync")
                return {
                    "success": True,
                    "users_synced": 0,
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
            
            logger.info(f"🔄 Starting balance sync for {len(users_with_keys)} users")
            
            # Sync each user sequentially to avoid rate limits
            results = []
            successful = 0
            failed = 0
            
            for user_id in users_with_keys:
                try:
                    result = await self.sync_user_balances(user_id)
                    results.append(result)
                    
                    if result.get("success"):
                        successful += 1
                    else:
                        failed += 1
                    
                    # Small delay to avoid rate limits
                    await asyncio.sleep(1)
                    
                except Exception as e:
                    logger.error(f"Failed to sync user {user_id[:8]}: {e}")
                    failed += 1
            
            logger.info(
                f"✅ Balance sync completed: {successful} successful, {failed} failed"
            )
            
            return {
                "success": True,
                "users_synced": len(users_with_keys),
                "successful": successful,
                "failed": failed,
                "results": results,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            
        except Exception as e:
            logger.error(f"Sync all users error: {e}")
            return {
                "success": False,
                "error": str(e),
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
    
    async def start_background_sync(self):
        """Start background balance sync task"""
        if self.is_running:
            logger.warning("Balance sync already running")
            return
        
        self.is_running = True
        self.sync_task = asyncio.create_task(self._background_sync_loop())
        logger.info(f"✅ Balance sync started (interval: {self.sync_interval}s)")
    
    async def stop_background_sync(self):
        """Stop background balance sync task"""
        self.is_running = False
        
        if self.sync_task:
            self.sync_task.cancel()
            try:
                await self.sync_task
            except asyncio.CancelledError:
                pass
        
        logger.info("⏹️ Balance sync stopped")
    
    async def _background_sync_loop(self):
        """Background sync loop"""
        while self.is_running:
            try:
                await self.sync_all_users()
            except Exception as e:
                logger.error(f"Background sync error: {e}")
            
            # Wait for next sync interval
            try:
                await asyncio.sleep(self.sync_interval)
            except asyncio.CancelledError:
                break


# Global singleton instance
balance_sync_service = BalanceSyncService()
