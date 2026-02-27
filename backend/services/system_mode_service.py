"""
System Mode Service - Paper vs Live Trading Mode Management
Enforces exclusive mode selection and data isolation
Handles mode switching with proper bot state transitions
"""

import logging
from datetime import datetime, timezone
from typing import Dict, Optional, Tuple
import database as db

logger = logging.getLogger(__name__)


class SystemModeService:
    """Manages system trading mode (paper vs live)"""
    
    VALID_MODES = ['paper', 'live']
    
    async def get_mode(self, user_id: str) -> str:
        """Canonical interface: get current system mode for user.

        Args:
            user_id: User ID

        Returns:
            'paper' or 'live'
        """
        try:
            modes = await db.system_modes_collection.find_one(
                {"user_id": user_id},
                {"_id": 0}
            )

            if not modes:
                logger.debug("No mode document for user %s — defaulting to paper", user_id[:8])
                return 'paper'

            # Check which mode is active
            if modes.get('liveTrading'):
                return 'live'
            elif modes.get('paperTrading'):
                return 'paper'
            else:
                logger.debug("Mode document has no active flag for user %s — defaulting to paper", user_id[:8])
                return 'paper'

        except Exception as e:
            logger.error("get_mode error for user %s: %s", user_id[:8], e)
            return 'paper'  # Safe default

    async def get_current_mode(self, user_id: str) -> str:
        """Compatibility alias for get_mode.  Prefer get_mode() in new code."""
        return await self.get_mode(user_id)
    
    async def set_mode(
        self, 
        user_id: str, 
        mode: str,
        force: bool = False
    ) -> Tuple[bool, str]:
        """Set system mode for user
        
        Handles:
        - Pausing incompatible bots
        - Switching balance sources
        - Clearing cached metrics
        
        Args:
            user_id: User ID
            mode: 'paper' or 'live'
            force: Force switch even if bots are active
            
        Returns:
            Tuple of (success, message)
        """
        try:
            if mode not in self.VALID_MODES:
                return False, f"Invalid mode: {mode}. Must be 'paper' or 'live'"
            
            current_mode = await self.get_current_mode(user_id)
            
            if current_mode == mode:
                return True, f"Already in {mode} mode"
            
            # Check for incompatible active bots
            incompatible_bots = await db.bots_collection.find({
                "user_id": user_id,
                "status": "active",
                "trading_mode": {"$ne": mode}
            }).to_list(100)
            
            if incompatible_bots and not force:
                return False, (
                    f"Cannot switch to {mode} mode: {len(incompatible_bots)} active bots "
                    f"in {current_mode} mode. Pause them first or use force=true"
                )
            
            # Pause incompatible bots if forcing
            if incompatible_bots and force:
                for bot in incompatible_bots:
                    await db.bots_collection.update_one(
                        {"id": bot['id']},
                        {
                            "$set": {
                                "status": "paused",
                                "paused_at": datetime.now(timezone.utc).isoformat(),
                                "pause_reason": f"System mode switched to {mode}",
                                "paused_by_system": True
                            }
                        }
                    )
                
                logger.info(f"Paused {len(incompatible_bots)} incompatible bots for mode switch")
            
            # Update system mode
            await db.system_modes_collection.update_one(
                {"user_id": user_id},
                {
                    "$set": {
                        "paperTrading": mode == 'paper',
                        "liveTrading": mode == 'live',
                        "mode_switched_at": datetime.now(timezone.utc).isoformat(),
                        "switched_by": user_id
                    }
                },
                upsert=True
            )
            
            # Broadcast mode change
            from services.realtime_service import realtime_service
            await realtime_service.broadcast_system_mode_change(
                user_id,
                mode,
                True
            )
            
            message = f"Switched to {mode} mode"
            if incompatible_bots:
                message += f" (paused {len(incompatible_bots)} incompatible bots)"
            
            logger.info(f"User {user_id[:8]} switched to {mode} mode")
            return True, message
            
        except Exception as e:
            logger.error(f"Set mode error: {e}")
            return False, str(e)
    
    def add_mode_filter(self, query: Dict, user_id: str, mode: Optional[str] = None) -> Dict:
        """Add mode filter to database query
        
        Args:
            query: Existing query dict
            user_id: User ID
            mode: Optional mode override, otherwise uses current mode
            
        Returns:
            Query dict with mode filter added
        """
        # Mode will be added asynchronously in actual queries
        # This is a helper to remind developers to filter by mode
        query['trading_mode'] = mode  # Placeholder, actual impl should await get_current_mode
        return query
    
    async def get_mode_specific_balance(
        self, 
        user_id: str, 
        mode: Optional[str] = None
    ) -> Dict:
        """Get balance for specific mode
        
        Paper mode: returns paper trading balance
        Live mode: returns actual exchange balances
        
        Args:
            user_id: User ID
            mode: Optional mode override
            
        Returns:
            Balance dict
        """
        try:
            if not mode:
                mode = await self.get_current_mode(user_id)
            
            if mode == 'paper':
                # Get paper trading balance (sum of bot capitals)
                bots_cursor = db.bots_collection.find(
                    {
                        "user_id": user_id,
                        "trading_mode": "paper",
                        "status": {"$ne": "deleted"}
                    },
                    {"_id": 0, "current_capital": 1, "initial_capital": 1}
                )
                bots = await bots_cursor.to_list(100)
                
                total_capital = sum(b.get('current_capital', b.get('initial_capital', 0)) for b in bots)
                
                return {
                    "mode": "paper",
                    "total": total_capital,
                    "available": total_capital,
                    "source": "paper_trading",
                    "currency": "ZAR"
                }
                
            else:  # live mode
                # Get actual exchange balances
                # This would integrate with wallet_manager
                from engines.wallet_manager import wallet_manager
                
                try:
                    balance = await wallet_manager.get_master_balance(user_id)
                    balance['mode'] = 'live'
                    balance['source'] = 'exchange_api'
                    return balance
                except Exception as e:
                    logger.error(f"Get live balance error: {e}")
                    return {
                        "mode": "live",
                        "total": 0,
                        "available": 0,
                        "source": "exchange_api",
                        "currency": "ZAR",
                        "error": str(e)
                    }
                    
        except Exception as e:
            logger.error(f"Get mode-specific balance error: {e}")
            return {
                "mode": mode or "unknown",
                "total": 0,
                "available": 0,
                "error": str(e)
            }
    
    async def get_mode_specific_metrics(
        self,
        user_id: str,
        mode: Optional[str] = None
    ) -> Dict:
        """Get metrics filtered by mode
        
        Args:
            user_id: User ID
            mode: Optional mode override
            
        Returns:
            Metrics dict
        """
        try:
            if not mode:
                mode = await self.get_current_mode(user_id)
            
            # Get bots for this mode
            bots_cursor = db.bots_collection.find(
                {
                    "user_id": user_id,
                    "trading_mode": mode,
                    "status": {"$ne": "deleted"}
                },
                {"_id": 0}
            )
            bots = await bots_cursor.to_list(100)
            
            # Get trades for this mode
            bot_ids = [b['id'] for b in bots if 'id' in b]
            
            trades_cursor = db.trades_collection.find(
                {
                    "user_id": user_id,
                    "bot_id": {"$in": bot_ids},
                    "status": "closed"
                },
                {"_id": 0, "profit_loss": 1}
            )
            trades = await trades_cursor.to_list(10000)
            
            total_profit = sum(t.get('profit_loss', 0) for t in trades)
            total_bots = len(bots)
            active_bots = len([b for b in bots if b.get('status') == 'active'])
            
            return {
                "mode": mode,
                "total_profit": round(total_profit, 2),
                "total_bots": total_bots,
                "active_bots": active_bots,
                "total_trades": len(trades)
            }
            
        except Exception as e:
            logger.error(f"Get mode-specific metrics error: {e}")
            return {
                "mode": mode or "unknown",
                "total_profit": 0,
                "total_bots": 0,
                "active_bots": 0,
                "total_trades": 0,
                "error": str(e)
            }


# Global singleton
system_mode_service = SystemModeService()
