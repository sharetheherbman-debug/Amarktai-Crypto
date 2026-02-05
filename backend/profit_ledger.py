"""
Profit Ledger - Per-Exchange, Per-Mode Profit Tracking
Tracks realized profits to gate auto-spawn and auto-mutate per exchange
"""

from typing import Dict, List, Optional, Tuple
from datetime import datetime, timezone
import logging
import database as db

logger = logging.getLogger(__name__)


class ProfitLedger:
    """
    Tracks realized profits per (user_id, exchange, trading_mode)
    Supports milestone tracking for idempotent auto-spawn/mutate
    """
    
    async def get_exchange_profit(self, user_id: str, exchange: str, trading_mode: str) -> float:
        """
        Get total realized profit for a specific exchange and mode
        
        Args:
            user_id: User ID
            exchange: Exchange name
            trading_mode: 'paper' or 'live'
            
        Returns:
            Total realized profit in ZAR
        """
        try:
            # Get all closed trades for this user/exchange/mode
            trades = await db.trades_collection.find({
                "user_id": user_id,
                "exchange": exchange,
                "trading_mode": trading_mode,
                "status": "closed",
                "profit_loss": {"$exists": True}
            }).to_list(10000)
            
            total_profit = sum(trade.get('profit_loss', 0) for trade in trades)
            return float(total_profit)
            
        except Exception as e:
            logger.error(f"Error getting exchange profit: {e}")
            return 0.0
    
    async def get_all_exchange_profits(self, user_id: str) -> Dict[str, Dict[str, float]]:
        """
        Get all profits grouped by exchange and mode
        
        Returns:
            {
                'luno': {'paper': 1500.0, 'live': 0.0},
                'binance': {'paper': 2300.0, 'live': 500.0},
                ...
            }
        """
        try:
            from rules import SUPPORTED_EXCHANGES
            
            result = {}
            for exchange in SUPPORTED_EXCHANGES:
                paper_profit = await self.get_exchange_profit(user_id, exchange, 'paper')
                live_profit = await self.get_exchange_profit(user_id, exchange, 'live')
                
                result[exchange] = {
                    'paper': paper_profit,
                    'live': live_profit,
                    'combined': paper_profit + live_profit
                }
            
            return result
            
        except Exception as e:
            logger.error(f"Error getting all exchange profits: {e}")
            return {}
    
    async def check_spawn_milestone(self, user_id: str, exchange: str, 
                                    trading_mode: str, profit_threshold: float = 1000.0) -> Tuple[bool, float, int]:
        """
        Check if user has reached a new spawn milestone for this exchange
        Returns (can_spawn, current_profit, milestone_number)
        
        Milestone tracking prevents spawning multiple bots for the same R1000 increment
        """
        try:
            # Get current profit
            current_profit = await self.get_exchange_profit(user_id, exchange, trading_mode)
            
            # Calculate milestone number (e.g., R2500 profit = milestone 2)
            milestone_number = int(current_profit // profit_threshold)
            
            # Get last spawned milestone from ledger
            ledger_key = f"{user_id}:{exchange}:{trading_mode}"
            ledger_doc = await db.profit_ledger_collection.find_one({
                "ledger_key": ledger_key
            })
            
            last_spawn_milestone = 0
            if ledger_doc:
                last_spawn_milestone = ledger_doc.get('last_spawn_milestone', 0)
            
            # Can spawn if we've reached a new milestone
            can_spawn = milestone_number > last_spawn_milestone
            
            return can_spawn, current_profit, milestone_number
            
        except Exception as e:
            logger.error(f"Error checking spawn milestone: {e}")
            return False, 0.0, 0
    
    async def record_spawn_milestone(self, user_id: str, exchange: str, 
                                     trading_mode: str, milestone: int, bot_id: str):
        """
        Record that a bot was spawned at this milestone
        Prevents duplicate spawns
        """
        try:
            ledger_key = f"{user_id}:{exchange}:{trading_mode}"
            
            await db.profit_ledger_collection.update_one(
                {"ledger_key": ledger_key},
                {
                    "$set": {
                        "user_id": user_id,
                        "exchange": exchange,
                        "trading_mode": trading_mode,
                        "last_spawn_milestone": milestone,
                        "last_spawn_at": datetime.now(timezone.utc).isoformat(),
                        "last_spawn_bot_id": bot_id,
                        "updated_at": datetime.now(timezone.utc).isoformat()
                    },
                    "$inc": {
                        "total_spawns": 1
                    },
                    "$setOnInsert": {
                        "created_at": datetime.now(timezone.utc).isoformat()
                    }
                },
                upsert=True
            )
            
            logger.info(f"Recorded spawn milestone {milestone} for {user_id} on {exchange} ({trading_mode})")
            
        except Exception as e:
            logger.error(f"Error recording spawn milestone: {e}")
    
    async def check_mutate_milestone(self, user_id: str, exchange: str, 
                                     trading_mode: str, profit_threshold: float = 1000.0) -> Tuple[bool, float]:
        """
        Check if mutation is allowed based on exchange profit
        Similar to spawn but doesn't track milestones (can mutate multiple times per milestone)
        """
        try:
            current_profit = await self.get_exchange_profit(user_id, exchange, trading_mode)
            can_mutate = current_profit >= profit_threshold
            
            return can_mutate, current_profit
            
        except Exception as e:
            logger.error(f"Error checking mutate milestone: {e}")
            return False, 0.0
    
    async def get_ledger_summary(self, user_id: str) -> Dict:
        """
        Get summary of profit ledger for user
        """
        try:
            all_profits = await self.get_all_exchange_profits(user_id)
            
            # Get spawn milestones
            milestones = {}
            ledgers = await db.profit_ledger_collection.find({
                "user_id": user_id
            }).to_list(100)
            
            for ledger in ledgers:
                key = f"{ledger['exchange']}:{ledger['trading_mode']}"
                milestones[key] = {
                    'last_spawn_milestone': ledger.get('last_spawn_milestone', 0),
                    'total_spawns': ledger.get('total_spawns', 0),
                    'last_spawn_at': ledger.get('last_spawn_at')
                }
            
            return {
                'profits': all_profits,
                'milestones': milestones,
                'timestamp': datetime.now(timezone.utc).isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error getting ledger summary: {e}")
            return {'profits': {}, 'milestones': {}}


# Global instance
profit_ledger = ProfitLedger()
