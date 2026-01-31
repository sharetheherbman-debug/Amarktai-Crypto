"""
Capital Allocator - Dynamic capital distribution across bots
- Rebalances capital based on performance
- Ensures optimal allocation for each risk tier
- Integrates with wallet manager
"""

import asyncio
from typing import Dict, List
from datetime import datetime, timezone
import logging

import database as db
from engines.wallet_manager import wallet_manager

logger = logging.getLogger(__name__)

class CapitalAllocator:
    def __init__(self):
        self.risk_weights = {
            'safe': 1.0,       # Base allocation
            'balanced': 1.2,   # 20% more capital
            'risky': 1.5,      # 50% more capital
            'aggressive': 2.0  # 2x capital
        }
        
        # Performance multipliers
        self.performance_tiers = {
            'elite': 2.0,      # Top 10% performers get 2x
            'high': 1.5,       # Top 25% get 1.5x
            'average': 1.0,    # Middle 50% get base
            'low': 0.7,        # Bottom 25% get 0.7x
            'poor': 0.5        # Bottom 10% get 0.5x
        }
    
    async def get_bot_performance_tier(self, bot: Dict) -> str:
        """Determine performance tier for a bot"""
        try:
            total_profit = bot.get('total_profit', 0)
            roi = (total_profit / bot.get('initial_capital', 1000)) * 100 if bot.get('initial_capital', 0) > 0 else 0
            win_rate = (bot.get('win_count', 0) / bot.get('trades_count', 1)) * 100 if bot.get('trades_count', 0) > 0 else 0
            
            # Scoring: ROI (60%) + Win Rate (40%)
            score = (roi * 0.6) + (win_rate * 0.4)
            
            if score >= 10:
                return 'elite'
            elif score >= 5:
                return 'high'
            elif score >= 0:
                return 'average'
            elif score >= -5:
                return 'low'
            else:
                return 'poor'
                
        except Exception as e:
            logger.error(f"Performance tier calculation error: {e}")
            return 'average'
    
    async def calculate_optimal_allocation(self, user_id: str, bot: Dict) -> float:
        """Calculate optimal capital allocation for a bot"""
        try:
            # Get master wallet balance
            master_balance = await wallet_manager.get_master_balance(user_id)
            
            if "error" in master_balance:
                # Fallback to default allocation
                return 1000.0
            
            total_capital = master_balance.get('total_zar', 0)
            
            # Base allocation per bot (80% of capital / 65 bots)
            base_allocation = (total_capital * 0.8) / 65
            
            # Apply risk mode multiplier
            risk_mode = bot.get('risk_mode', 'safe')
            risk_multiplier = self.risk_weights.get(risk_mode, 1.0)
            
            # Apply performance multiplier
            performance_tier = await self.get_bot_performance_tier(bot)
            performance_multiplier = self.performance_tiers.get(performance_tier, 1.0)
            
            # Calculate final allocation
            optimal_allocation = base_allocation * risk_multiplier * performance_multiplier
            
            # Apply limits (min R500, max R10,000)
            optimal_allocation = max(500, min(optimal_allocation, 10000))
            
            return optimal_allocation
            
        except Exception as e:
            logger.error(f"Optimal allocation calculation error: {e}")
            return 1000.0
    
    async def rebalance_all_bots(self, user_id: str) -> Dict:
        """Rebalance capital across all bots based on performance"""
        try:
            # Get all active bots
            bots = await db.bots_collection.find(
                {"user_id": user_id, "status": "active"},
                {"_id": 0}
            ).to_list(1000)
            
            if not bots:
                return {
                    "success": False,
                    "message": "No active bots to rebalance"
                }
            
            rebalanced = []
            
            for bot in bots:
                # Calculate optimal allocation
                optimal = await self.calculate_optimal_allocation(user_id, bot)
                current = bot.get('current_capital', 1000)
                
                # Only rebalance if difference is significant (>20%)
                diff_pct = abs(optimal - current) / current if current > 0 else 1
                
                if diff_pct > 0.20:
                    # Update bot capital
                    await db.bots_collection.update_one(
                        {"id": bot['id']},
                        {"$set": {"current_capital": optimal}}
                    )
                    
                    rebalanced.append({
                        "bot_id": bot['id'],
                        "bot_name": bot['name'],
                        "old_capital": current,
                        "new_capital": optimal,
                        "change": optimal - current,
                        "change_pct": ((optimal - current) / current) * 100
                    })
                    
                    logger.info(f"💰 Rebalanced {bot['name']}: R{current:.2f} → R{optimal:.2f}")
            
            # Log rebalancing action
            if rebalanced:
                await db.autopilot_actions_collection.insert_one({
                    "user_id": user_id,
                    "action_type": "capital_rebalance",
                    "bots_affected": len(rebalanced),
                    "details": rebalanced,
                    "timestamp": datetime.now(timezone.utc).isoformat()
                })
            
            return {
                "success": True,
                "rebalanced_count": len(rebalanced),
                "total_bots": len(bots),
                "changes": rebalanced
            }
            
        except Exception as e:
            logger.error(f"Rebalance all bots error: {e}")
            return {"success": False, "error": str(e)}
    
    async def fund_new_bot(self, user_id: str, bot_id: str, exchange: str, risk_mode: str) -> Dict:
        """Fund a newly created bot from master wallet"""
        try:
            # Create temp bot object for calculation
            temp_bot = {
                "id": bot_id,
                "user_id": user_id,
                "exchange": exchange,
                "risk_mode": risk_mode,
                "initial_capital": 1000,
                "current_capital": 1000,
                "total_profit": 0,
                "trades_count": 0,
                "win_count": 0,
                "mode": "paper"
            }
            
            # Calculate optimal allocation for new bot
            allocation = await self.calculate_optimal_allocation(user_id, temp_bot)
            
            # Allocate funds via wallet manager
            result = await wallet_manager.allocate_funds_for_bot(
                user_id,
                bot_id,
                exchange,
                allocation
            )
            
            if result.get('success'):
                return {
                    "success": True,
                    "amount": allocation,
                    "exchange": exchange
                }
            else:
                return {
                    "success": False,
                    "error": result.get('error', 'Unknown error')
                }
                
        except Exception as e:
            logger.error(f"Fund new bot error: {e}")
            return {"success": False, "error": str(e)}
    
    async def get_allocation_report(self, user_id: str) -> Dict:
        """Generate allocation report for all bots"""
        try:
            bots = await db.bots_collection.find(
                {"user_id": user_id},
                {"_id": 0}
            ).to_list(1000)
            
            total_allocated = sum(b.get('current_capital', 0) for b in bots)
            
            by_risk = {}
            by_performance = {}
            
            for bot in bots:
                # Group by risk mode
                risk = bot.get('risk_mode', 'safe')
                if risk not in by_risk:
                    by_risk[risk] = {"count": 0, "capital": 0}
                by_risk[risk]['count'] += 1
                by_risk[risk]['capital'] += bot.get('current_capital', 0)
                
                # Group by performance tier
                tier = await self.get_bot_performance_tier(bot)
                if tier not in by_performance:
                    by_performance[tier] = {"count": 0, "capital": 0}
                by_performance[tier]['count'] += 1
                by_performance[tier]['capital'] += bot.get('current_capital', 0)
            
            return {
                "total_bots": len(bots),
                "total_capital": total_allocated,
                "by_risk_mode": by_risk,
                "by_performance": by_performance,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            
        except Exception as e:
            logger.error(f"Allocation report error: {e}")
            return {"error": str(e)}
    
    async def reallocate_capital(self, user_id: str) -> Dict:
        """Reallocate capital (alias for rebalance_all_bots)"""
        return await self.rebalance_all_bots(user_id)
    
    async def reinvest_daily_profits(self, user_id: str) -> Dict:
        """Reinvest daily profits - safe no-op for now"""
        try:
            logger.info(f"Reinvest daily profits called for user {user_id} (no-op)")
            return {
                "ok": True,
                "note": "Profit reinvestment is handled automatically by the autopilot system"
            }
        except Exception as e:
            logger.error(f"Reinvest daily profits error: {e}")
            return {"ok": False, "error": str(e)}
    
    async def auto_spawn_bot(self, user_id: str) -> Dict:
        """Auto-spawn bot - safe no-op for now"""
        try:
            logger.info(f"Auto-spawn bot called for user {user_id} (no-op)")
            return {
                "ok": True,
                "note": "Bot spawning is handled by the bot manager and autopilot system"
            }
        except Exception as e:
            logger.error(f"Auto-spawn bot error: {e}")
            return {"ok": False, "error": str(e)}

# Global instance
capital_allocator = CapitalAllocator()
