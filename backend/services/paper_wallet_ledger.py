"""
Paper Wallet Ledger - Per-Bot Capital Management
Enforces realistic paper trading with reserve/debit/credit system.
NO FREE MONEY - Capital must be explicitly allocated.
"""

import logging
from datetime import datetime, timezone
from typing import Dict, Tuple, Optional
import database as db
from logger_config import logger


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
        if not self.collection:
            self.collection = db.paper_ledger_collection
    
    async def reserve_funds(self, user_id: str, bot_id: str, amount: float) -> Tuple[bool, str]:
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
            
            # Check if bot already has reserved funds
            existing = await self.collection.find_one({"bot_id": bot_id, "user_id": user_id})
            if existing:
                return False, f"Bot {bot_id[:8]} already has reserved funds"
            
            # Create ledger entry
            ledger_entry = {
                "user_id": user_id,
                "bot_id": bot_id,
                "initial_balance": amount,
                "current_balance": amount,
                "reserved_at": datetime.now(timezone.utc).isoformat(),
                "last_updated": datetime.now(timezone.utc).isoformat(),
                "total_debits": 0.0,
                "total_credits": 0.0,
                "trade_count": 0,
                "status": "active"
            }
            
            await self.collection.insert_one(ledger_entry)
            logger.info(f"✅ Reserved R{amount:,.2f} paper funds for bot {bot_id[:8]}")
            
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
            
            # Get current balance
            success, balance, msg = await self.get_balance(bot_id)
            if not success:
                return False, msg
            
            # Check sufficient funds
            if balance < amount:
                return False, f"Insufficient funds: R{balance:.2f} < R{amount:.2f}"
            
            # Perform debit
            new_balance = balance - amount
            
            result = await self.collection.update_one(
                {"bot_id": bot_id},
                {
                    "$set": {
                        "current_balance": new_balance,
                        "last_updated": datetime.now(timezone.utc).isoformat()
                    },
                    "$inc": {
                        "total_debits": amount,
                        "trade_count": 1
                    }
                }
            )
            
            if result.modified_count > 0:
                logger.debug(f"Debited R{amount:.2f} from bot {bot_id[:8]}: {reason}")
                return True, f"Debited R{amount:.2f}"
            else:
                return False, "Failed to update ledger"
        
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
            
            # Get current balance
            success, balance, msg = await self.get_balance(bot_id)
            if not success:
                return False, msg
            
            # Perform credit
            new_balance = balance + amount
            
            result = await self.collection.update_one(
                {"bot_id": bot_id},
                {
                    "$set": {
                        "current_balance": new_balance,
                        "last_updated": datetime.now(timezone.utc).isoformat()
                    },
                    "$inc": {
                        "total_credits": amount
                    }
                }
            )
            
            if result.modified_count > 0:
                logger.debug(f"Credited R{amount:.2f} to bot {bot_id[:8]}: {reason}")
                return True, f"Credited R{amount:.2f}"
            else:
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
            
            # Get final balance
            success, balance, msg = await self.get_balance(bot_id)
            
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
                return True, f"Released R{balance:.2f}"
            else:
                return False, "Failed to release funds"
        
        except Exception as e:
            logger.error(f"Error releasing paper funds: {e}")
            return False, f"Error: {str(e)}"
    
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
