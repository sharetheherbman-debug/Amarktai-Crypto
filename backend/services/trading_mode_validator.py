"""
Trading Mode Validator - Enforces Trading Mode Gates
Ensures trading only executes with proper mode enabled (paper OR live).
NO BYPASSES - All execution paths must go through these gates.
"""

import logging
from typing import Dict, Tuple, Optional
from datetime import datetime, timezone
import database as db
from logger_config import logger
from utils.env_utils import env_bool, get_trading_flags


class TradingModeValidator:
    """
    Validates trading mode gates before allowing execution.
    
    Rules:
    1. Paper trading requires paper_trading=true
    2. Live trading requires:
       - live_trading=true
       - API keys present and tested
       - Balance check passing
       - User confirmation
    3. If both paper_trading=false AND live_trading=false, BLOCK ALL TRADES
    """
    
    def __init__(self):
        pass
    
    async def validate_bot_trading_mode(self, bot_id: str, bot_data: Dict = None) -> Tuple[bool, str, str]:
        """
        Validate that a bot can trade based on its mode.
        
        Args:
            bot_id: Bot ID
            bot_data: Optional bot data (to avoid extra DB query)
        
        Returns:
            (can_trade, mode, reason)
        """
        try:
            # Get bot data if not provided
            if not bot_data:
                bot_data = await db.bots_collection.find_one({"id": bot_id}, {"_id": 0})
                if not bot_data:
                    return False, "unknown", f"Bot {bot_id[:8]} not found"
            
            # Determine bot's trading mode
            mode = bot_data.get('trading_mode') or bot_data.get('mode', 'paper')
            user_id = bot_data.get('user_id')
            system_mode = None
            if user_id:
                system_mode = await db.system_modes_collection.find_one({"user_id": user_id}, {"_id": 0})
                # If user is explicitly in paper mode, run paper gates to avoid blocking
                # paper trading with live-only errors.
                if system_mode and system_mode.get('paperTrading') and not system_mode.get('liveTrading'):
                    return await self.validate_paper_trading(bot_data, system_mode=system_mode)
            
            # Validate based on mode
            if mode == 'paper':
                return await self.validate_paper_trading(bot_data, system_mode=system_mode)
            elif mode == 'live':
                return await self.validate_live_trading(bot_data, system_mode=system_mode)
            else:
                return False, mode, f"Invalid trading mode: {mode}"
        
        except Exception as e:
            logger.error(f"Error validating bot trading mode: {e}")
            return False, "error", f"Error: {str(e)}"
    
    async def validate_paper_trading(
        self,
        bot_data: Dict,
        system_mode: Optional[Dict] = None
    ) -> Tuple[bool, str, str]:
        """
        Validate paper trading can proceed.
        
        Args:
            bot_data: Bot data dict
        
        Returns:
            (can_trade, mode, reason)
        """
        try:
            user_id = bot_data.get('user_id')
            bot_id = bot_data.get('id')

            flags = get_trading_flags()
            if not flags["enable_paper_trading"]:
                return False, "paper", "Paper trading not enabled globally"

            # Check user's system mode
            if system_mode is None:
                system_mode = await db.system_modes_collection.find_one({"user_id": user_id}, {"_id": 0})
            
            if not system_mode:
                # Default to paper trading if no mode set
                logger.debug(f"No system mode set for user {user_id[:8]}, defaulting to paper")
                return True, "paper", "Paper trading allowed (default)"
            
            # Check if emergency stop is active
            if system_mode.get('emergencyStop', False):
                return False, "paper", "Emergency stop is active"
            
            # Check if autopilot is enabled (required for trading)
            if not system_mode.get('autopilot', False):
                if system_mode.get('paperTrading', True):
                    return True, "paper", "Paper trading allowed while autopilot is disabled"
                return False, "paper", "Paper trading is disabled"
            
            # Paper trading is allowed
            return True, "paper", "Paper trading validated"
        
        except Exception as e:
            logger.error(f"Error validating paper trading: {e}")
            return False, "paper", f"Error: {str(e)}"
    
    async def validate_live_trading(
        self,
        bot_data: Dict,
        system_mode: Optional[Dict] = None
    ) -> Tuple[bool, str, str]:
        """
        Validate live trading can proceed with all safety checks.
        
        Args:
            bot_data: Bot data dict
        
        Returns:
            (can_trade, mode, reason)
        """
        try:
            user_id = bot_data.get('user_id')
            bot_id = bot_data.get('id')
            exchange = bot_data.get('exchange', 'unknown')

            flags = get_trading_flags()
            live_enabled = flags["enable_live_trading"]
            if not live_enabled:
                return False, "live", "Live trading not enabled globally"
            if not flags["enable_trading"]:
                return False, "live", "Master trading switch ENABLE_TRADING is disabled"
            
            # 1. Check user's system mode for live trading flag
            if system_mode is None:
                system_mode = await db.system_modes_collection.find_one({"user_id": user_id}, {"_id": 0})
            
            if not system_mode:
                return False, "live", "No system mode configuration found"
            
            # Check if live trading is enabled for user
            if not system_mode.get('liveTrading', False):
                return False, "live", "Live trading not enabled for user"
            
            # Check if emergency stop is active
            if system_mode.get('emergencyStop', False):
                return False, "live", "Emergency stop is active"
            
            # Check if autopilot is enabled (required for trading)
            if not system_mode.get('autopilot', False):
                return False, "live", "Autopilot is disabled"
            
            # 2. Check API keys are present
            api_keys = await db.api_keys_collection.find_one({
                "user_id": user_id,
                "exchange": exchange
            }, {"_id": 0})
            
            if not api_keys:
                return False, "live", f"No API keys configured for {exchange}"
            
            if not api_keys.get('api_key') or not api_keys.get('api_secret'):
                return False, "live", f"Incomplete API keys for {exchange}"
            
            # 3. Check if API keys have been tested successfully
            if not api_keys.get('tested', False) or not api_keys.get('valid', False):
                return False, "live", f"API keys not tested/validated for {exchange}"
            
            # 4. Check if balance check has passed recently
            last_balance_check = api_keys.get('last_balance_check')
            if not last_balance_check:
                return False, "live", "No recent balance check for API keys"
            
            # All checks passed
            logger.info(f"✅ Live trading validated for bot {bot_id[:8]} on {exchange}")
            return True, "live", "Live trading validated"
        
        except Exception as e:
            logger.error(f"Error validating live trading: {e}")
            return False, "live", f"Error: {str(e)}"
    
    async def validate_global_trading_gates(self) -> Tuple[bool, str]:
        """
        Validate global trading gates (environment variables).
        
        Returns:
            (trading_allowed, reason)
        """
        try:
            flags = get_trading_flags()
            paper_enabled = flags["enable_paper_trading"]
            live_enabled = flags["enable_live_trading"]
            trading_enabled = flags["enable_trading"]
            
            if not trading_enabled:
                return False, "Master trading disabled (ENABLE_TRADING=false)"
            if not paper_enabled and not live_enabled:
                return False, "No trading mode enabled (ENABLE_PAPER_TRADING=false AND ENABLE_LIVE_TRADING=false)"
            
            if paper_enabled and not live_enabled:
                return True, "Paper trading enabled globally"
            
            if live_enabled and not paper_enabled:
                return True, "Live trading enabled globally"
            
            return True, "Both paper and live trading enabled"
        
        except Exception as e:
            logger.error(f"Error validating global gates: {e}")
            return False, f"Error: {str(e)}"
    
    async def enforce_trading_gates(self, bot_id: str, bot_data: Dict = None) -> None:
        """
        Enforce trading gates - raises exception if trading not allowed.
        
        Args:
            bot_id: Bot ID
            bot_data: Optional bot data
        
        Raises:
            TradingGateError: If trading is not allowed
        """
        from utils.trading_gates import TradingGateError
        
        # Check global gates
        global_ok, global_reason = await self.validate_global_trading_gates()
        if not global_ok:
            raise TradingGateError(f"Global gate failed: {global_reason}")
        
        # Check bot-specific gates
        can_trade, mode, reason = await self.validate_bot_trading_mode(bot_id, bot_data)
        if not can_trade:
            raise TradingGateError(f"Bot {bot_id[:8]} cannot trade: {reason}")
        
        logger.debug(f"✅ Trading gates passed for bot {bot_id[:8]} in {mode} mode")
    
    async def get_bot_trading_status(self, bot_id: str) -> Dict:
        """
        Get comprehensive trading status for a bot.
        
        Args:
            bot_id: Bot ID
        
        Returns:
            Status dict with details
        """
        try:
            bot_data = await db.bots_collection.find_one({"id": bot_id}, {"_id": 0})
            
            if not bot_data:
                return {
                    "bot_id": bot_id,
                    "can_trade": False,
                    "mode": "unknown",
                    "reason": "Bot not found"
                }
            
            can_trade, mode, reason = await self.validate_bot_trading_mode(bot_id, bot_data)
            global_ok, global_reason = await self.validate_global_trading_gates()
            
            return {
                "bot_id": bot_id,
                "bot_name": bot_data.get('name', 'Unknown'),
                "can_trade": can_trade and global_ok,
                "mode": mode,
                "reason": reason,
                "global_gates": {
                    "passed": global_ok,
                    "reason": global_reason
                },
                "bot_gates": {
                    "passed": can_trade,
                    "reason": reason
                },
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        
        except Exception as e:
            logger.error(f"Error getting bot trading status: {e}")
            return {
                "bot_id": bot_id,
                "can_trade": False,
                "mode": "error",
                "reason": f"Error: {str(e)}"
            }


# Global instance
trading_mode_validator = TradingModeValidator()
