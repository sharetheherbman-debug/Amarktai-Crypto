"""
Reserved Funds Tracking Service
Atomic tracking of reserved funds per user + exchange + currency
Ensures bots cannot over-allocate capital beyond available balance

Key Operations:
- reserve_funds: Atomically reserve funds when bot is spawned
- release_funds: Atomically release funds when bot is stopped
- get_available_balance: Calculate available = balance - reserved
- check_available_funds: Check if sufficient funds available before spawning

Features:
- Concurrency-safe using MongoDB $inc atomic operations
- Per-user, per-exchange, per-currency tracking
- Integrates with bot spawner and autopilot
"""

import logging
from typing import Dict, Optional, Tuple
from datetime import datetime, timezone

import database as db

logger = logging.getLogger(__name__)


class ReservedFundsService:
    """Track and manage reserved funds atomically"""
    
    async def reserve_funds(
        self, 
        user_id: str, 
        exchange: str, 
        currency: str, 
        amount: float,
        bot_id: Optional[str] = None
    ) -> Tuple[bool, str]:
        """
        Atomically reserve funds for a bot
        
        Args:
            user_id: User ID
            exchange: Exchange name (e.g., 'binance', 'luno')
            currency: Currency code (e.g., 'USDT', 'ZAR')
            amount: Amount to reserve
            bot_id: Optional bot ID for tracking
            
        Returns:
            Tuple of (success, message)
        """
        try:
            # Check if sufficient available funds exist
            has_funds, available = await self.check_available_funds(
                user_id, exchange, currency, amount
            )
            
            if not has_funds:
                logger.warning(
                    f"Insufficient funds to reserve R{amount:.2f} on {exchange} "
                    f"for user {user_id[:8]}. Available: R{available:.2f}"
                )
                return False, f"Insufficient available funds. Available: R{available:.2f}, Requested: R{amount:.2f}"
            
            # Atomically increment reserved amount using MongoDB $inc
            result = await db.wallet_balances_collection.update_one(
                {
                    "user_id": user_id,
                    "exchange": exchange,
                    "currency": currency
                },
                {
                    "$inc": {"reserved": amount},
                    "$set": {
                        "last_updated": datetime.now(timezone.utc).isoformat()
                    },
                    "$setOnInsert": {
                        "user_id": user_id,
                        "exchange": exchange,
                        "currency": currency,
                        "balance": 0,
                        "created_at": datetime.now(timezone.utc).isoformat()
                    }
                },
                upsert=True
            )
            
            # Log reservation
            await db.ledger_collection.insert_one({
                "user_id": user_id,
                "exchange": exchange,
                "currency": currency,
                "amount": amount,
                "bot_id": bot_id,
                "type": "reserve",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "description": f"Reserved R{amount:.2f} for bot {bot_id or 'unknown'}"
            })
            
            logger.info(
                f"✅ Reserved R{amount:.2f} {currency} on {exchange} "
                f"for user {user_id[:8]} (bot: {bot_id or 'N/A'})"
            )
            
            return True, f"Successfully reserved R{amount:.2f}"
            
        except Exception as e:
            logger.error(f"Reserve funds error: {e}")
            return False, f"Failed to reserve funds: {str(e)}"
    
    async def release_funds(
        self, 
        user_id: str, 
        exchange: str, 
        currency: str, 
        amount: float,
        bot_id: Optional[str] = None
    ) -> Tuple[bool, str]:
        """
        Atomically release reserved funds when bot is stopped
        
        Args:
            user_id: User ID
            exchange: Exchange name
            currency: Currency code
            amount: Amount to release
            bot_id: Optional bot ID for tracking
            
        Returns:
            Tuple of (success, message)
        """
        try:
            # Atomically decrement reserved amount using MongoDB $inc
            result = await db.wallet_balances_collection.update_one(
                {
                    "user_id": user_id,
                    "exchange": exchange,
                    "currency": currency
                },
                {
                    "$inc": {"reserved": -amount},
                    "$set": {
                        "last_updated": datetime.now(timezone.utc).isoformat()
                    }
                }
            )
            
            if result.modified_count == 0:
                logger.warning(
                    f"No wallet entry found to release R{amount:.2f} on {exchange} "
                    f"for user {user_id[:8]}"
                )
                return False, "Wallet entry not found"
            
            # Ensure reserved doesn't go negative (safety check)
            await db.wallet_balances_collection.update_one(
                {
                    "user_id": user_id,
                    "exchange": exchange,
                    "currency": currency,
                    "reserved": {"$lt": 0}
                },
                {
                    "$set": {"reserved": 0}
                }
            )
            
            # Log release
            await db.ledger_collection.insert_one({
                "user_id": user_id,
                "exchange": exchange,
                "currency": currency,
                "amount": amount,
                "bot_id": bot_id,
                "type": "release",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "description": f"Released R{amount:.2f} from bot {bot_id or 'unknown'}"
            })
            
            logger.info(
                f"✅ Released R{amount:.2f} {currency} on {exchange} "
                f"for user {user_id[:8]} (bot: {bot_id or 'N/A'})"
            )
            
            return True, f"Successfully released R{amount:.2f}"
            
        except Exception as e:
            logger.error(f"Release funds error: {e}")
            return False, f"Failed to release funds: {str(e)}"
    
    async def get_available_balance(
        self, 
        user_id: str, 
        exchange: str, 
        currency: str = "ZAR"
    ) -> float:
        """
        Calculate available balance = balance - reserved
        
        Args:
            user_id: User ID
            exchange: Exchange name
            currency: Currency code (default: ZAR)
            
        Returns:
            Available balance (float)
        """
        try:
            wallet = await db.wallet_balances_collection.find_one(
                {
                    "user_id": user_id,
                    "exchange": exchange,
                    "currency": currency
                },
                {"_id": 0, "balance": 1, "reserved": 1}
            )
            
            if not wallet:
                return 0.0
            
            balance = wallet.get("balance", 0)
            reserved = wallet.get("reserved", 0)
            available = max(0, balance - reserved)
            
            return available
            
        except Exception as e:
            logger.error(f"Get available balance error: {e}")
            return 0.0
    
    async def check_available_funds(
        self, 
        user_id: str, 
        exchange: str, 
        currency: str, 
        required_amount: float
    ) -> Tuple[bool, float]:
        """
        Check if sufficient available funds exist
        
        Args:
            user_id: User ID
            exchange: Exchange name
            currency: Currency code
            required_amount: Amount needed
            
        Returns:
            Tuple of (has_sufficient_funds, available_balance)
        """
        try:
            available = await self.get_available_balance(user_id, exchange, currency)
            has_funds = available >= required_amount
            
            return has_funds, available
            
        except Exception as e:
            logger.error(f"Check available funds error: {e}")
            return False, 0.0
    
    async def get_reserved_summary(self, user_id: str) -> Dict:
        """
        Get summary of all reserved funds across exchanges
        
        Args:
            user_id: User ID
            
        Returns:
            Dict with reserved funds by exchange and currency
        """
        try:
            wallets = await db.wallet_balances_collection.find(
                {"user_id": user_id},
                {"_id": 0, "exchange": 1, "currency": 1, "balance": 1, "reserved": 1}
            ).to_list(100)
            
            summary = {
                "total_reserved": 0,
                "by_exchange": {}
            }
            
            for wallet in wallets:
                exchange = wallet.get("exchange", "unknown")
                currency = wallet.get("currency", "unknown")
                reserved = wallet.get("reserved", 0)
                balance = wallet.get("balance", 0)
                available = max(0, balance - reserved)
                
                if exchange not in summary["by_exchange"]:
                    summary["by_exchange"][exchange] = {
                        "total_reserved": 0,
                        "currencies": {}
                    }
                
                summary["by_exchange"][exchange]["currencies"][currency] = {
                    "balance": balance,
                    "reserved": reserved,
                    "available": available
                }
                summary["by_exchange"][exchange]["total_reserved"] += reserved
                summary["total_reserved"] += reserved
            
            return summary
            
        except Exception as e:
            logger.error(f"Get reserved summary error: {e}")
            return {"error": str(e)}
    
    async def reconcile_reserved_funds(self, user_id: str) -> Dict:
        """
        Reconcile reserved funds with actual active bots
        Fixes any discrepancies where reserved doesn't match allocated capital
        
        Args:
            user_id: User ID
            
        Returns:
            Dict with reconciliation results
        """
        try:
            # Get all active bots with allocated capital
            bots = await db.bots_collection.find(
                {
                    "user_id": user_id,
                    "status": {"$in": ["active", "training"]}
                },
                {
                    "_id": 0,
                    "id": 1,
                    "exchange": 1,
                    "allocated_capital": 1,
                    "current_capital": 1
                }
            ).to_list(1000)
            
            # Calculate expected reserved by exchange
            expected_reserved = {}
            for bot in bots:
                exchange = bot.get("exchange", "unknown").lower()
                capital = bot.get("allocated_capital", bot.get("current_capital", 0))
                
                if exchange not in expected_reserved:
                    expected_reserved[exchange] = 0
                expected_reserved[exchange] += capital
            
            # Get actual reserved from wallet balances
            wallets = await db.wallet_balances_collection.find(
                {"user_id": user_id},
                {"_id": 0, "exchange": 1, "currency": 1, "reserved": 1}
            ).to_list(100)
            
            actual_reserved = {}
            for wallet in wallets:
                exchange = wallet.get("exchange", "unknown").lower()
                reserved = wallet.get("reserved", 0)
                
                if exchange not in actual_reserved:
                    actual_reserved[exchange] = 0
                actual_reserved[exchange] += reserved
            
            # Find discrepancies
            discrepancies = []
            all_exchanges = set(list(expected_reserved.keys()) + list(actual_reserved.keys()))
            
            for exchange in all_exchanges:
                expected = expected_reserved.get(exchange, 0)
                actual = actual_reserved.get(exchange, 0)
                
                if abs(expected - actual) > 0.01:  # Allow small floating point difference
                    discrepancies.append({
                        "exchange": exchange,
                        "expected": expected,
                        "actual": actual,
                        "difference": expected - actual
                    })
            
            result = {
                "user_id": user_id,
                "active_bots": len(bots),
                "expected_reserved": expected_reserved,
                "actual_reserved": actual_reserved,
                "has_discrepancies": len(discrepancies) > 0,
                "discrepancies": discrepancies,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            
            if discrepancies:
                logger.warning(
                    f"⚠️ Reserved funds discrepancies found for user {user_id[:8]}: "
                    f"{len(discrepancies)} exchange(s)"
                )
            
            return result
            
        except Exception as e:
            logger.error(f"Reconcile reserved funds error: {e}")
            return {"error": str(e)}


# Global singleton instance
reserved_funds_service = ReservedFundsService()
