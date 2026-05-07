"""
Paper Wallet Ledger - Per-Bot Capital Management
Enforces realistic paper trading with reserve/debit/credit system.
NO FREE MONEY - Capital must be explicitly allocated.
"""

import logging
from datetime import datetime, timezone
from typing import Dict, Tuple, Optional
from pymongo import ReturnDocument
import database as db
from logger_config import logger
from services.paper_wallet_service import paper_wallet_service


class PaperWalletLedger:
    """
    Manages paper trading capital allocation with strict enforcement.
    
    Features:
    - Per-bot paper wallet tracking
    - Reserve funds on bot creation
    - Debit/credit on trade simulation
    - Enforce fees and slippage
    - Block trades with insufficient funds
    """
    
    def __init__(self):
        self.collection = None
    
    async def init_db(self):
        """Initialize database collection"""
        if self.collection is None:
            self.collection = db.paper_ledger_collection
        if self.collection is None:
            raise RuntimeError("Paper ledger collection not initialized")

    async def _update_user_wallet_balance(
        self,
        user_id: str,
        total_balance: float,
        available_balance: float,
        allocated_balance: float
    ) -> None:
        if db.wallet_balances_collection is None:
            return
        await db.wallet_balances_collection.update_one(
            {"user_id": user_id},
            {
                "$set": {
                    "paper_wallet_balance_zar": round(total_balance, 2),
                    "paper_wallet_available_zar": round(available_balance, 2),
                    "paper_wallet_allocated_zar": round(allocated_balance, 2),
                    "paper_wallet_updated_at": datetime.now(timezone.utc).isoformat()
                },
                "$setOnInsert": {"user_id": user_id}
            },
            upsert=True
        )
    
    def _resolve_bot_currency(self, bot: Dict) -> str:
        exchange = (bot.get("exchange") or "").lower()
        pair = bot.get("pair", "")
        if exchange == "luno" or "/ZAR" in pair:
            return "ZAR"
        return "USDT"

    async def reserve_funds(
        self,
        user_id: str,
        bot_id: str,
        amount: float,
        currency: str = "ZAR"
    ) -> Tuple[bool, str]:
        """
        Reserve paper funds for a new bot.
        
        Args:
            user_id: User ID
            bot_id: Bot ID
            amount: Amount to reserve
        
        Returns:
            (success, message)
        """
        try:
            await self.init_db()
            
            if amount <= 0:
                return False, f"Invalid amount: R{amount}"
            
            currency = (currency or "ZAR").upper()

            # Check if bot already has reserved funds
            existing = await self.collection.find_one({"bot_id": bot_id, "user_id": user_id})
            if existing:
                return False, f"Bot {bot_id[:8]} already has reserved funds"

            # Reserve from user-level paper wallet
            reserved, reserve_msg = await paper_wallet_service.reserve_funds(user_id, amount, currency)
            if not reserved:
                return False, reserve_msg
            
            # Create ledger entry
            ledger_entry = {
                "user_id": user_id,
                "bot_id": bot_id,
                "initial_balance": amount,
                "current_balance": amount,
                "currency": currency,
                "reserved_at": datetime.now(timezone.utc).isoformat(),
                "last_updated": datetime.now(timezone.utc).isoformat(),
                "total_debits": 0.0,
                "total_credits": 0.0,
                "trade_count": 0,
                "status": "active"
            }
            
            try:
                await self.collection.insert_one(ledger_entry)
            except Exception as insert_error:
                await paper_wallet_service.release_funds(user_id, amount, currency)
                raise insert_error
            logger.info(f"✅ Reserved R{amount:,.2f} paper funds for bot {bot_id[:8]}")
            await self.get_user_balance(user_id)
            
            return True, f"Reserved R{amount:,.2f} paper funds"
        
        except Exception as e:
            logger.error(f"Error reserving paper funds: {e}")
            return False, f"Error: {str(e)}"
    
    async def get_balance(self, bot_id: str) -> Tuple[bool, float, str]:
        """
        Get current paper wallet balance for a bot.
        
        Args:
            bot_id: Bot ID
        
        Returns:
            (success, balance, message)
        """
        try:
            await self.init_db()
            
            ledger = await self.collection.find_one({"bot_id": bot_id})

            if not ledger:
                bot = await db.bots_collection.find_one(
                    {"id": bot_id},
                    {"_id": 0, "user_id": 1, "initial_capital": 1, "trading_mode": 1, "mode": 1}
                )
                mode = str((bot or {}).get("trading_mode") or (bot or {}).get("mode") or "paper").lower()
                if bot and mode.startswith("paper") and bot.get("initial_capital", 0) > 0:
                    currency = self._resolve_bot_currency(bot)
                    success, _ = await self.reserve_funds(
                        bot.get("user_id"),
                        bot_id,
                        bot.get("initial_capital", 0),
                        currency
                    )
                    if success:
                        ledger = await self.collection.find_one({"bot_id": bot_id})

            if not ledger:
                return False, 0.0, f"No paper wallet found for bot {bot_id[:8]}"
            
            balance = ledger.get("current_balance", 0.0)
            return True, balance, "Balance retrieved"
        
        except Exception as e:
            logger.error(f"Error getting paper balance: {e}")
            return False, 0.0, f"Error: {str(e)}"
    
    async def can_trade(self, bot_id: str, required_amount: float) -> Tuple[bool, str]:
        """
        Check if bot has sufficient paper funds for a trade.
        
        Args:
            bot_id: Bot ID
            required_amount: Required amount for trade
        
        Returns:
            (can_trade, message)
        """
        try:
            success, balance, msg = await self.get_balance(bot_id)
            
            if not success:
                return False, msg
            
            if balance < required_amount:
                return False, f"Insufficient paper funds: R{balance:.2f} < R{required_amount:.2f}"
            
            return True, f"Sufficient funds: R{balance:.2f}"
        
        except Exception as e:
            logger.error(f"Error checking can_trade: {e}")
            return False, f"Error: {str(e)}"
    
    async def debit(self, bot_id: str, amount: float, reason: str = "trade") -> Tuple[bool, str]:
        """
        Debit (subtract) from paper wallet.
        
        Args:
            bot_id: Bot ID
            amount: Amount to debit
            reason: Reason for debit
        
        Returns:
            (success, message)
        """
        try:
            await self.init_db()
            
            ledger = await self.collection.find_one_and_update(
                {
                    "bot_id": bot_id,
                    "current_balance": {"$gte": amount}
                },
                {
                    "$inc": {
                        "current_balance": -amount,
                        "total_debits": amount,
                        "trade_count": 1
                    },
                    "$set": {
                        "last_updated": datetime.now(timezone.utc).isoformat()
                    }
                },
                return_document=ReturnDocument.AFTER
            )

            if ledger:
                logger.debug(f"Debited R{amount:.2f} from bot {bot_id[:8]}: {reason}")
                if ledger.get("user_id"):
                    await self.get_user_balance(ledger["user_id"])
                return True, f"Debited R{amount:.2f}"

            ledger = await self.collection.find_one({"bot_id": bot_id}, {"_id": 0, "current_balance": 1})
            if not ledger:
                return False, "No paper wallet found for bot"
            balance = ledger.get("current_balance", 0.0)
            return False, f"Insufficient funds: R{balance:.2f} < R{amount:.2f}"
        
        except Exception as e:
            logger.error(f"Error debiting paper funds: {e}")
            return False, f"Error: {str(e)}"
    
    async def credit(self, bot_id: str, amount: float, reason: str = "trade_profit") -> Tuple[bool, str]:
        """
        Credit (add) to paper wallet.
        
        Args:
            bot_id: Bot ID
            amount: Amount to credit
            reason: Reason for credit
        
        Returns:
            (success, message)
        """
        try:
            await self.init_db()
            
            ledger = await self.collection.find_one_and_update(
                {"bot_id": bot_id},
                {
                    "$inc": {
                        "current_balance": amount,
                        "total_credits": amount
                    },
                    "$set": {
                        "last_updated": datetime.now(timezone.utc).isoformat()
                    }
                },
                return_document=ReturnDocument.AFTER
            )

            if ledger:
                logger.debug(f"Credited R{amount:.2f} to bot {bot_id[:8]}: {reason}")
                if ledger.get("user_id"):
                    await self.get_user_balance(ledger["user_id"])
                return True, f"Credited R{amount:.2f}"
            return False, "Failed to update ledger"
        
        except Exception as e:
            logger.error(f"Error crediting paper funds: {e}")
            return False, f"Error: {str(e)}"
    
    async def release_funds(self, bot_id: str) -> Tuple[bool, str]:
        """
        Release paper funds when bot is deleted.
        
        Args:
            bot_id: Bot ID
        
        Returns:
            (success, message)
        """
        try:
            await self.init_db()
            
            ledger = await self.collection.find_one({"bot_id": bot_id}, {"_id": 0})
            if not ledger:
                return False, "No paper wallet found for bot"
            balance = ledger.get("current_balance", 0.0)

            # Mark as released
            result = await self.collection.update_one(
                {"bot_id": bot_id},
                {
                    "$set": {
                        "status": "released",
                        "released_at": datetime.now(timezone.utc).isoformat(),
                        "final_balance": balance
                    }
                }
            )
            
            if result.modified_count > 0:
                logger.info(f"✅ Released paper funds for bot {bot_id[:8]}: R{balance:.2f}")
                ledger = await self.collection.find_one({"bot_id": bot_id}, {"_id": 0, "user_id": 1, "currency": 1})
                if ledger and ledger.get("user_id"):
                    currency = (ledger.get("currency") or "ZAR").upper()
                    await paper_wallet_service.release_funds(ledger["user_id"], balance, currency)
                    await self.get_user_balance(ledger["user_id"])
                return True, f"Released R{balance:.2f}"
            return False, "Failed to release funds"
        
        except Exception as e:
            logger.error(f"Error releasing paper funds: {e}")
            return False, f"Error: {str(e)}"

    async def get_user_balance(self, user_id: str) -> Optional[float]:
        """Return total paper wallet balance for a user."""
        try:
            await self.init_db()

            pipeline = [
                {"$match": {"user_id": user_id, "status": "active"}},
                {"$group": {"_id": "$currency", "total": {"$sum": "$current_balance"}}}
            ]
            results = await self.collection.aggregate(pipeline).to_list(100)
            allocated_total = sum(float(r.get("total", 0) or 0) for r in results)
            available = await paper_wallet_service.get_balances(user_id)
            available_total = float(available.get("total", 0) or 0)
            total = allocated_total + available_total
            await self._update_user_wallet_balance(user_id, total, available_total, allocated_total)
            return total
        except Exception as e:
            logger.error(f"Error getting user paper balance: {e}")
            return None
    
    async def get_ledger_stats(self, bot_id: str) -> Optional[Dict]:
        """
        Get complete ledger statistics for a bot.
        
        Args:
            bot_id: Bot ID
        
        Returns:
            Ledger stats dict or None
        """
        try:
            await self.init_db()
            
            ledger = await self.collection.find_one({"bot_id": bot_id}, {"_id": 0})
            return ledger
        
        except Exception as e:
            logger.error(f"Error getting ledger stats: {e}")
            return None


# Global instance
paper_wallet_ledger = PaperWalletLedger()
