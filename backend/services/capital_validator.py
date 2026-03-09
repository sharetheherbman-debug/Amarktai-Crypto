"""
Capital Validation Service - Single Source of Truth for Fund Allocation
Ensures bots cannot spawn without actual allocated funds.
"""
from typing import Tuple, Optional, Dict
from datetime import datetime, timezone
import database as db
from logger_config import logger
from config import NEW_BOT_CAPITAL

ALLOCATION_SYNC_TOLERANCE = 0.01


class CapitalValidator:
    """
    Validates and manages capital allocation integrity across the system.
    Prevents bots from spawning without actual funds.
    """
    
    async def get_user_capital_status(self, user_id: str) -> Dict:
        """
        Get comprehensive capital status for a user.
        
        Returns:
            {
                "balance": float,  # Total balance
                "allocated_balance": float,  # Allocated to active bots
                "reserved_balance": float,  # Reserved/locked
                "available_balance": float,  # Available for new bots
                "active_bot_count": int,
                "total_bot_capital": float  # Sum of all bot capitals
            }
        """
        try:
            # Get user document
            user = await db.users_collection.find_one({"id": user_id})
            if not user:
                return self._empty_capital_status()
            
            # Get balance fields (with defaults if missing)
            balance = user.get("balance", 0.0)
            stored_allocated_balance = user.get("allocated_balance", 0.0)
            reserved_balance = user.get("reserved_balance", 0.0)
            
            # Get all active bots
            active_bots = await db.bots_collection.find({
                "user_id": user_id,
                "status": {"$in": ["active", "paused"]}  # Not stopped/deleted
            }).to_list(None)
            
            # Calculate total allocated capital from bots (canonical source).
            # Bot documents are the execution source-of-truth; user aggregate
            # fields can drift after partial resets/retries and are synchronized below.
            def _bot_allocated_value(bot_doc: Dict) -> float:
                if "allocated_capital" in bot_doc and bot_doc.get("allocated_capital") is not None:
                    return float(bot_doc.get("allocated_capital") or 0.0)
                if "current_capital" in bot_doc and bot_doc.get("current_capital") is not None:
                    return float(bot_doc.get("current_capital") or 0.0)
                return float(bot_doc.get("initial_capital") or 0.0)

            total_bot_capital = sum(_bot_allocated_value(bot) for bot in active_bots)
            allocated_balance = round(total_bot_capital, 2)

            # Paper wallet fallback when balance is not set
            if balance <= 0:
                try:
                    from services.paper_wallet_service import paper_wallet_service
                    paper_wallet = await paper_wallet_service.get_balances(user_id)
                    balance = max(balance, paper_wallet.get("total", 0.0))
                except Exception as e:
                    logger.debug(f"Paper wallet fallback skipped: {e}")

            # Keep user aggregate in sync with canonical bot allocation total.
            if abs(float(stored_allocated_balance or 0.0) - allocated_balance) > ALLOCATION_SYNC_TOLERANCE:
                await db.users_collection.update_one(
                    {"id": user_id},
                    {"$set": {
                        "allocated_balance": allocated_balance,
                        "updated_at": datetime.now(timezone.utc).isoformat(),
                    }},
                )
            
            # Calculate available balance
            available = balance - allocated_balance - reserved_balance
            
            return {
                "balance": balance,
                "allocated_balance": allocated_balance,
                "reserved_balance": reserved_balance,
                "available_balance": max(0, available),  # Never negative
                "active_bot_count": len(active_bots),
                "total_bot_capital": allocated_balance
            }
        
        except Exception as e:
            logger.error(f"Error getting capital status for user {user_id}: {e}")
            return self._empty_capital_status()
    
    def _empty_capital_status(self) -> Dict:
        """Return empty capital status"""
        return {
            "balance": 0.0,
            "allocated_balance": 0.0,
            "reserved_balance": 0.0,
            "available_balance": 0.0,
            "active_bot_count": 0,
            "total_bot_capital": 0.0
        }
    
    async def validate_bot_funding(
        self,
        user_id: str,
        required_capital: float,
        bot_id: Optional[str] = None
    ) -> Tuple[bool, str, str]:
        """
        Validate that a user has sufficient funds for a bot.
        
        Args:
            user_id: User ID
            required_capital: Capital needed for the bot
            bot_id: Optional bot ID (for updates)
        
        Returns:
            (is_valid, error_code, error_message)
            
        Error codes:
            - INSUFFICIENT_FUNDS: Not enough available balance
            - CAPITAL_NOT_ALLOCATED: Capital not properly allocated
            - BELOW_MINIMUM: Below minimum capital requirement
            - OK: Validation passed
        """
        try:
            # Check minimum capital requirement
            if required_capital < NEW_BOT_CAPITAL:
                return False, "BELOW_MINIMUM", f"Minimum capital is R{NEW_BOT_CAPITAL:,.0f}"
            
            # Get capital status
            status = await self.get_user_capital_status(user_id)
            available = status["available_balance"]
            
            # For existing bot updates, we may need to check allocated capital
            if bot_id:
                bot = await db.bots_collection.find_one({"id": bot_id, "user_id": user_id})
                if bot:
                    # When updating, we can use currently allocated capital
                    currently_allocated = bot.get("allocated_capital", bot.get("current_capital", 0.0))
                    available += currently_allocated
            
            # Check if sufficient funds available
            if available < required_capital:
                return False, "INSUFFICIENT_FUNDS", \
                    f"Insufficient funds. Available: R{available:,.2f}, Required: R{required_capital:,.2f}"
            
            return True, "OK", "Funding validated"
        
        except Exception as e:
            logger.error(f"Error validating bot funding: {e}")
            return False, "VALIDATION_ERROR", f"Error validating funds: {str(e)}"
    
    async def allocate_capital_to_bot(
        self,
        user_id: str,
        bot_id: str,
        capital: float
    ) -> Tuple[bool, str]:
        """
        Atomically allocate capital to a bot.
        Updates user's allocated_balance and bot's allocated_capital.
        
        Returns:
            (success, message)
        """
        try:
            # Validate funding first
            is_valid, error_code, error_msg = await self.validate_bot_funding(user_id, capital)
            if not is_valid:
                return False, error_msg
            
            # Get current user status
            status = await self.get_user_capital_status(user_id)
            
            # Update user's allocated balance
            new_allocated = status["allocated_balance"] + capital
            await db.users_collection.update_one(
                {"id": user_id},
                {
                    "$set": {
                        "allocated_balance": new_allocated,
                        "updated_at": datetime.now(timezone.utc).isoformat()
                    }
                }
            )
            
            # Update bot's allocated capital
            await db.bots_collection.update_one(
                {"id": bot_id, "user_id": user_id},
                {
                    "$set": {
                        "allocated_capital": capital,
                        "current_capital": capital,
                        "initial_capital": capital,
                        "updated_at": datetime.now(timezone.utc).isoformat()
                    }
                }
            )
            
            logger.info(f"✅ Allocated R{capital:,.2f} to bot {bot_id[:8]} for user {user_id[:8]}")
            return True, f"Allocated R{capital:,.2f} successfully"
        
        except Exception as e:
            logger.error(f"Error allocating capital to bot: {e}")
            return False, f"Error: {str(e)}"
    
    async def release_capital_from_bot(
        self,
        user_id: str,
        bot_id: str
    ) -> Tuple[bool, str]:
        """
        Release capital from a stopped/deleted bot back to available balance.
        
        Returns:
            (success, message)
        """
        try:
            # Get bot
            bot = await db.bots_collection.find_one({"id": bot_id, "user_id": user_id})
            if not bot:
                return False, "Bot not found"
            
            allocated_capital = bot.get("allocated_capital", 0.0)
            if allocated_capital <= 0:
                return True, "No capital to release"
            
            # Get current user status
            user = await db.users_collection.find_one({"id": user_id})
            if not user:
                return False, "User not found"
            
            current_allocated = user.get("allocated_balance", 0.0)
            new_allocated = max(0, current_allocated - allocated_capital)
            
            # Update user's allocated balance
            await db.users_collection.update_one(
                {"id": user_id},
                {
                    "$set": {
                        "allocated_balance": new_allocated,
                        "updated_at": datetime.now(timezone.utc).isoformat()
                    }
                }
            )
            
            # Clear bot's allocated capital
            await db.bots_collection.update_one(
                {"id": bot_id},
                {
                    "$set": {
                        "allocated_capital": 0.0,
                        "updated_at": datetime.now(timezone.utc).isoformat()
                    }
                }
            )
            
            logger.info(f"✅ Released R{allocated_capital:,.2f} from bot {bot_id[:8]} for user {user_id[:8]}")
            return True, f"Released R{allocated_capital:,.2f} back to available balance"
        
        except Exception as e:
            logger.error(f"Error releasing capital from bot: {e}")
            return False, f"Error: {str(e)}"
    
    async def recalculate_user_allocation(self, user_id: str) -> Tuple[bool, str]:
        """
        Recalculate and fix user's allocated_balance based on active bots.
        Used for migration and consistency checks.
        
        Returns:
            (success, message)
        """
        try:
            # Get all active bots
            active_bots = await db.bots_collection.find({
                "user_id": user_id,
                "status": {"$in": ["active", "paused"]}
            }).to_list(None)
            
            # Calculate total allocated
            total_allocated = sum(
                bot.get("allocated_capital", bot.get("current_capital", 0.0))
                for bot in active_bots
            )
            
            # Update user's allocated balance
            await db.users_collection.update_one(
                {"id": user_id},
                {
                    "$set": {
                        "allocated_balance": total_allocated,
                        "updated_at": datetime.now(timezone.utc).isoformat()
                    }
                }
            )
            
            logger.info(f"✅ Recalculated allocation for user {user_id[:8]}: R{total_allocated:,.2f}")
            return True, f"Allocated balance updated to R{total_allocated:,.2f}"
        
        except Exception as e:
            logger.error(f"Error recalculating allocation: {e}")
            return False, f"Error: {str(e)}"


# Singleton instance
capital_validator = CapitalValidator()
