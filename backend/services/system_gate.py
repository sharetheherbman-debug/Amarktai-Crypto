"""
System Gate Service - Master Trading Gatekeeper
Enforces that trading cannot run unless proper conditions are met.
Prevents scheduler from running trades when system is not in appropriate mode.
"""
import os
from typing import Dict, Tuple
from datetime import datetime, timezone
import database as db
from logger_config import logger
from utils.env_utils import env_bool


class SystemGateService:
    """
    Master gatekeeper for trading operations.
    Enforces strict conditions before allowing any trading activity.
    """
    
    # Valid trading modes
    VALID_TRADING_MODES = ["paper", "live"]
    
    def __init__(self):
        # Read environment flags
        self.trading_enabled = env_bool("ENABLE_TRADING", True)
        self.autopilot_enabled = env_bool("ENABLE_AUTOPILOT", True)
        self.ccxt_enabled = env_bool("ENABLE_CCXT", True)
        
        logger.info(f"System Gate initialized: Trading={self.trading_enabled}, Autopilot={self.autopilot_enabled}")
    
    async def get_system_status(self) -> Dict:
        """
        Get comprehensive system status.
        
        Returns:
            {
                "trading_allowed": bool,
                "mode": str,  # paper/live/disabled
                "trading_enabled": bool,
                "autopilot_enabled": bool,
                "emergency_stop": bool,
                "reason": str  # Why trading is allowed/disallowed
            }
        """
        try:
            # Check global system mode (from first user or system config)
            # For simplicity, we'll check if ANY user has system active
            system_mode_doc = await db.system_modes_collection.find_one({})
            
            # Determine current mode
            mode = "disabled"
            if system_mode_doc:
                if system_mode_doc.get("liveTrading"):
                    mode = "live"
                elif system_mode_doc.get("paperTrading"):
                    mode = "paper"
            else:
                # Default to paper if no mode set
                mode = "paper"
            
            # Check emergency stop
            emergency_stop = False
            users_with_stop = await db.users_collection.count_documents({"emergency_stop": True})
            if users_with_stop > 0:
                emergency_stop = True
            
            # Determine if trading is allowed
            trading_allowed = False
            reason = ""
            
            if emergency_stop:
                reason = "Emergency stop is active"
            elif not self.trading_enabled:
                reason = "Trading is disabled in environment (ENABLE_TRADING=false)"
            elif mode not in self.VALID_TRADING_MODES:
                reason = f"Invalid mode '{mode}' - must be paper or live"
            else:
                trading_allowed = True
                reason = f"System is operational in {mode} mode"
            
            return {
                "trading_allowed": trading_allowed,
                "mode": mode,
                "trading_enabled": self.trading_enabled,
                "autopilot_enabled": self.autopilot_enabled,
                "ccxt_enabled": self.ccxt_enabled,
                "emergency_stop": emergency_stop,
                "reason": reason,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        
        except Exception as e:
            logger.error(f"Error getting system status: {e}")
            return {
                "trading_allowed": False,
                "mode": "error",
                "trading_enabled": False,
                "autopilot_enabled": False,
                "ccxt_enabled": False,
                "emergency_stop": False,
                "reason": f"System error: {str(e)}",
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
    
    async def can_trade(self, user_id: str = None) -> Tuple[bool, str]:
        """
        Check if trading is allowed for the system or a specific user.
        
        Args:
            user_id: Optional user ID to check user-specific stops
        
        Returns:
            (allowed, reason)
        """
        try:
            status = await self.get_system_status()
            
            # Check system-level gate
            if not status["trading_allowed"]:
                return False, status["reason"]
            
            # Check user-specific emergency stop
            if user_id:
                user = await db.users_collection.find_one({"id": user_id})
                if user and user.get("emergency_stop"):
                    return False, f"Emergency stop active for user {user_id[:8]}"
            
            return True, "Trading allowed"
        
        except Exception as e:
            logger.error(f"Error checking can_trade: {e}")
            return False, f"Error: {str(e)}"
    
    async def can_run_autopilot(self) -> Tuple[bool, str]:
        """
        Check if autopilot can run.
        
        Returns:
            (allowed, reason)
        """
        try:
            # Check if autopilot is enabled
            if not self.autopilot_enabled:
                return False, "Autopilot is disabled (ENABLE_AUTOPILOT=false)"
            
            # Check if trading is allowed
            can_trade_result, reason = await self.can_trade()
            if not can_trade_result:
                return False, f"Trading not allowed: {reason}"
            
            return True, "Autopilot can run"
        
        except Exception as e:
            logger.error(f"Error checking can_run_autopilot: {e}")
            return False, f"Error: {str(e)}"
    
    async def set_emergency_stop(self, user_id: str, enabled: bool) -> Tuple[bool, str]:
        """
        Set emergency stop for a user.
        
        Args:
            user_id: User ID
            enabled: True to enable emergency stop, False to disable
        
        Returns:
            (success, message)
        """
        try:
            result = await db.users_collection.update_one(
                {"id": user_id},
                {
                    "$set": {
                        "emergency_stop": enabled,
                        "emergency_stop_at": datetime.now(timezone.utc).isoformat()
                    }
                }
            )
            
            if result.modified_count > 0:
                action = "enabled" if enabled else "disabled"
                logger.info(f"Emergency stop {action} for user {user_id[:8]}")
                
                # Broadcast emergency stop event
                from services.realtime_service import realtime_service
                await realtime_service.broadcast_emergency_stop(user_id, enabled)
                
                return True, f"Emergency stop {action}"
            else:
                return False, "User not found or no change needed"
        
        except Exception as e:
            logger.error(f"Error setting emergency stop: {e}")
            return False, f"Error: {str(e)}"
    
    def validate_scheduler_tick(self) -> Tuple[bool, str]:
        """
        Quick validation for scheduler tick - should it run?
        This is called EVERY scheduler cycle.
        
        Returns:
            (should_run, reason)
        """
        if not self.trading_enabled:
            return False, "Trading disabled (ENABLE_TRADING=false)"
        
        return True, "Scheduler can proceed"


# Singleton instance
system_gate = SystemGateService()
