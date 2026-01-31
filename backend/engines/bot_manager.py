"""
Bot Manager - Enforces limits and manages bot lifecycle
"""
import asyncio
from datetime import datetime, timezone, timedelta
from uuid import uuid4
import database as db
from config import EXCHANGE_BOT_LIMITS, NEW_BOT_CAPITAL
from logger_config import logger
from services.capital_validator import capital_validator


class BotManager:
    def __init__(self):
        self.limits = EXCHANGE_BOT_LIMITS
    
    async def can_create_bot(self, user_id: str, exchange: str) -> tuple[bool, str]:
        """Check if user can create a bot on this exchange"""
        try:
            # Get current bot count for this exchange
            count = await db.bots_collection.count_documents({
                "user_id": user_id,
                "exchange": exchange
            })
            
            limit = self.limits.get(exchange.lower(), 10)
            
            if count >= limit:
                return False, f"❌ Maximum {limit} bots allowed for {exchange.upper()}"
            
            return True, f"✅ Can create bot ({count + 1}/{limit})"
        except Exception as e:
            logger.error(f"Can create bot check error: {e}")
            return False, f"❌ Error: {str(e)}"
    
    async def create_bot(self, user_id: str, name: str, exchange: str, risk_mode: str = 'safe', capital: float = None) -> dict:
        """Create a new bot with all validations"""
        try:
            # Check limits
            can_create, message = await self.can_create_bot(user_id, exchange)
            if not can_create:
                return {"success": False, "message": message}
            
            # Validate capital
            if capital is None:
                capital = NEW_BOT_CAPITAL
            
            # Validate bot funding (capital allocation integrity)
            is_valid, error_code, error_msg = await capital_validator.validate_bot_funding(
                user_id, capital
            )
            if not is_valid:
                return {"success": False, "message": f"❌ {error_msg}", "error_code": error_code}
            
            if capital < NEW_BOT_CAPITAL:
                return {"success": False, "message": f"❌ Minimum capital is R{NEW_BOT_CAPITAL}"}
            
            # Determine trading pair
            pair = "BTC/ZAR" if exchange.lower() == 'luno' else "BTC/USDT"
            
            # Create bot document
            bot_id = str(uuid4())
            bot = {
                "id": bot_id,
                "user_id": user_id,
                "name": name,
                "status": "active",
                "exchange": exchange.lower(),
                "pair": pair,
                "risk_mode": risk_mode,
                "initial_capital": capital,
                "current_capital": capital,
                "allocated_capital": capital,  # NEW: Track allocated capital
                "mode": "paper",  # paper or live
                "trading_mode": "paper",
                "trades_count": 0,
                "daily_trade_count": 0,
                "last_trade_time": None,
                "win_count": 0,
                "loss_count": 0,
                "total_profit": 0,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "paper_start_date": datetime.now(timezone.utc).isoformat(),
                "paper_end_eligible_at": (datetime.now(timezone.utc) + timedelta(days=7)).isoformat(),
                "learning_complete": False
            }
            
            await db.bots_collection.insert_one(bot)
            
            # Atomically allocate capital to this bot
            success, alloc_msg = await capital_validator.allocate_capital_to_bot(
                user_id, bot_id, capital
            )
            if not success:
                # Rollback: delete bot if allocation failed
                await db.bots_collection.delete_one({"id": bot_id})
                return {"success": False, "message": f"❌ Capital allocation failed: {alloc_msg}"}
            
            logger.info(f"✅ Created bot: {name} on {exchange} for user {user_id[:8]} with R{capital:,.2f} allocated")
            
            # Remove _id before returning (MongoDB adds it automatically)
            bot_clean = {k: v for k, v in bot.items() if k != '_id'}
            
            return {
                "success": True,
                "message": f"✅ Created '{name}' on {exchange.upper()} with R{capital:,.0f} ({risk_mode} mode)",
                "bot": bot_clean
            }
        
        except Exception as e:
            logger.error(f"Bot creation error: {e}")
            return {"success": False, "message": f"❌ Error: {str(e)}"}
    
    async def delete_bot(self, user_id: str, bot_id: str = None, bot_name: str = None) -> dict:
        """Delete a bot"""
        try:
            query = {"user_id": user_id}
            if bot_id:
                query["id"] = bot_id
            elif bot_name:
                query["name"] = bot_name
            else:
                return {"success": False, "message": "❌ No bot specified"}
            
            # Get bot before deleting (to release capital)
            bot = await db.bots_collection.find_one(query)
            if not bot:
                return {"success": False, "message": "❌ Bot not found"}
            
            # Release allocated capital back to user
            bot_id_to_release = bot.get("id")
            if bot_id_to_release:
                await capital_validator.release_capital_from_bot(user_id, bot_id_to_release)
            
            # Delete bot
            result = await db.bots_collection.delete_one(query)
            
            if result.deleted_count > 0:
                return {"success": True, "message": "✅ Bot deleted and capital released"}
            return {"success": False, "message": "❌ Bot not found"}
        
        except Exception as e:
            logger.error(f"Delete bot error: {e}")
            return {"success": False, "message": f"❌ Error: {str(e)}"}
    
    async def update_bot_status(self, user_id: str, bot_id: str, status: str) -> dict:
        """Update bot status (active/paused)"""
        try:
            result = await db.bots_collection.update_one(
                {"user_id": user_id, "id": bot_id},
                {"$set": {"status": status}}
            )
            
            if result.modified_count > 0:
                return {"success": True, "message": f"✅ Bot {status}"}
            return {"success": False, "message": "❌ Bot not found"}
        
        except Exception as e:
            logger.error(f"Update status error: {e}")
            return {"success": False, "message": f"❌ Error: {str(e)}"}
    
    async def reset_daily_trade_counts(self):
        """Reset daily trade counts for all bots (called at midnight)"""
        try:
            result = await db.bots_collection.update_many(
                {},
                {"$set": {"daily_trade_count": 0}}
            )
            logger.info(f"✅ Reset daily trade counts for {result.modified_count} bots")
        except Exception as e:
            logger.error(f"Reset daily counts error: {e}")


bot_manager = BotManager()
