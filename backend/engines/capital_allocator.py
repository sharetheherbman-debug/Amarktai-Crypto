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
        """
        Reinvest daily profits according to rules:
        - When exchange is at cap, reinvest profits into best performers on that exchange
        - Use configurable reinvestment rate (50% of realized profit)
        - Never allocate more than available funds
        - Keep ledger history
        """
        try:
            try:
                from rules import (
                    get_max_bots_for_exchange, 
                    get_reinvestment_rate,
                    calculate_reinvestment_amount,
                    SUPPORTED_EXCHANGES
                )
            except ImportError as e:
                logger.error(f"Rules import failed for reinvestment: {e}")
                return {
                    "success": False,
                    "error": "rules_import_failed",
                    "message": "Rules import failed; reinvestment skipped"
                }
            from profit_ledger import profit_ledger
            
            logger.info(f"Processing profit reinvestment for user {user_id}")
            
            reinvested = []
            total_reinvested = 0
            
            # Get all profits
            all_profits = await profit_ledger.get_all_exchange_profits(user_id)
            
            # Process each exchange separately
            for exchange in SUPPORTED_EXCHANGES:
                # Get bot count for this exchange
                bot_count = await db.bots_collection.count_documents({
                    "user_id": user_id,
                    "exchange": exchange,
                    "status": {"$nin": ["deleted", "quarantined"]}
                })
                
                # Check if at cap
                max_bots = get_max_bots_for_exchange(exchange)
                if bot_count < max_bots:
                    # Not at cap, auto-spawn handles growth
                    continue
                
                logger.info(f"Exchange {exchange} at cap ({bot_count}/{max_bots}), checking for reinvestment")
                
                # Get realized profit for this exchange (combined paper + live)
                exchange_profits = all_profits.get(exchange, {})
                realized_profit = exchange_profits.get('combined', 0.0)
                
                if realized_profit <= 0:
                    logger.debug(f"  No profit to reinvest for {exchange}")
                    continue
                
                # Get available funds from wallet manager
                try:
                    from engines.wallet_manager import wallet_manager
                    wallet_data = await wallet_manager.get_master_balance(user_id)
                    available_funds = wallet_data.get('available_zar', 0) if not wallet_data.get('error') else 0
                except:
                    available_funds = 1000  # Fallback minimum
                
                # Calculate reinvestment amount
                reinvest_amount = calculate_reinvestment_amount(realized_profit, available_funds)
                
                if reinvest_amount <= 0:
                    logger.debug(f"  No funds available to reinvest for {exchange}")
                    continue
                
                logger.info(f"  Reinvesting R{reinvest_amount:.2f} from R{realized_profit:.2f} profit")
                
                # Get top performers on this exchange
                top_bots = await db.bots_collection.find({
                    "user_id": user_id,
                    "exchange": exchange,
                    "status": "active"
                }).sort("total_profit", -1).limit(3).to_list(3)
                
                if not top_bots:
                    logger.debug(f"  No active bots found for {exchange}")
                    continue
                
                # Distribute reinvestment across top performers
                amount_per_bot = reinvest_amount / len(top_bots)
                
                for bot in top_bots:
                    await db.bots_collection.update_one(
                        {"id": bot['id']},
                        {
                            "$inc": {"current_capital": amount_per_bot},
                            "$push": {
                                "capital_history": {
                                    "timestamp": datetime.now(timezone.utc).isoformat(),
                                    "amount": amount_per_bot,
                                    "reason": "profit_reinvestment",
                                    "exchange": exchange,
                                    "total_exchange_profit": realized_profit
                                }
                            }
                        }
                    )
                    
                    reinvested.append({
                        "bot_id": bot['id'],
                        "bot_name": bot.get('name', 'unknown'),
                        "exchange": exchange,
                        "amount": round(amount_per_bot, 2)
                    })
                    
                    total_reinvested += amount_per_bot
                    
                    logger.info(f"    ✅ Reinvested R{amount_per_bot:.2f} into {bot.get('name', bot['id'][:8])}")
            
            if reinvested:
                logger.info(f"✅ Total reinvested: R{total_reinvested:.2f} across {len(reinvested)} bots")
            else:
                logger.info("No reinvestments made (no exchanges at cap with sufficient profit)")
            
            return {
                "success": True,
                "reinvested": reinvested,
                "total_amount": round(total_reinvested, 2),
                "count": len(reinvested)
            }
            
        except Exception as e:
            logger.error(f"Reinvest daily profits error: {e}")
            return {"success": False, "error": str(e)}
    
    async def auto_spawn_bot(self, user_id: str, trading_mode: str = 'paper') -> Dict:
        """
        Auto-spawn bot with profit gating:
        - Only spawns when exchange has generated >= R1000 realized profit
        - Enforces per-exchange bot caps (Luno: 5, others: 10)
        - Requires available funds to fund the new bot
        - Uses milestone tracking for idempotency
        - Returns appropriate reason codes on rejection
        
        Args:
            user_id: User ID
            trading_mode: 'paper' or 'live' - determines which profit to check
        """
        try:
            try:
                from rules import (
                    check_bot_cap_limit,
                    get_reason_message,
                    SUPPORTED_EXCHANGES,
                    PROFIT_THRESHOLD_ZAR
                )
            except ImportError as e:
                logger.error(f"Rules import failed for auto-spawn: {e}")
                return {
                    "success": False,
                    "error": "rules_import_failed",
                    "message": "Rules import failed; auto-spawn skipped"
                }
            from profit_ledger import profit_ledger
            from uuid import uuid4
            
            logger.info(f"Checking auto-spawn eligibility for user {user_id} (mode: {trading_mode})")
            
            spawned_bots = []
            reasons = []
            
            # Get wallet balance
            try:
                from engines.wallet_manager import wallet_manager
                wallet_data = await wallet_manager.get_master_balance(user_id)
                available_funds = wallet_data.get('available_zar', 0) if not wallet_data.get('error') else 0
            except:
                available_funds = 0
                logger.warning("Could not get wallet balance, using 0")
            
            # Check each exchange for spawn eligibility
            for exchange in SUPPORTED_EXCHANGES:
                # Get current bot count (exclude deleted and quarantined)
                bot_count = await db.bots_collection.count_documents({
                    "user_id": user_id,
                    "exchange": exchange,
                    "status": {"$nin": ["deleted", "quarantined"]}
                })
                
                # Check bot cap
                can_create, reason_code = check_bot_cap_limit(exchange, bot_count + 1, user_id)
                if not can_create:
                    reasons.append({
                        "exchange": exchange,
                        "reason": reason_code,
                        "message": get_reason_message(reason_code)
                    })
                    logger.debug(f"  {exchange}: {get_reason_message(reason_code)}")
                    continue
                
                # Check profit milestone (idempotent spawn gating)
                can_spawn, current_profit, milestone = await profit_ledger.check_spawn_milestone(
                    user_id, exchange, trading_mode, PROFIT_THRESHOLD_ZAR
                )
                
                if not can_spawn:
                    reasons.append({
                        "exchange": exchange,
                        "reason": "INSUFFICIENT_EXCHANGE_PROFIT" if current_profit < PROFIT_THRESHOLD_ZAR else "MILESTONE_NOT_REACHED",
                        "current_profit": round(current_profit, 2),
                        "threshold": PROFIT_THRESHOLD_ZAR,
                        "current_milestone": milestone
                    })
                    logger.debug(f"  {exchange}: Profit R{current_profit:.2f} (milestone {milestone}, need next milestone)")
                    continue
                
                # Check available funds (minimum R1000 per bot)
                min_funding = 1000
                if available_funds < min_funding:
                    reasons.append({
                        "exchange": exchange,
                        "reason": "INSUFFICIENT_FUNDS_TO_SPAWN",
                        "available": round(available_funds, 2),
                        "required": min_funding
                    })
                    logger.debug(f"  {exchange}: Insufficient funds (have R{available_funds:.2f}, need R{min_funding})")
                    continue
                
                # All checks passed - spawn bot!
                bot_id = str(uuid4())
                new_bot = {
                    'id': bot_id,
                    'user_id': user_id,
                    'name': f'Auto-{exchange.title()}-{milestone}',
                    'exchange': exchange,
                    'risk_mode': 'safe',
                    'trading_mode': trading_mode,
                    'status': 'active',
                    'initial_capital': min_funding,
                    'current_capital': min_funding,
                    'total_profit': 0.0,
                    'trades_count': 0,
                    'created_at': datetime.now(timezone.utc).isoformat(),
                    'spawned_by': 'autopilot',
                    'spawn_milestone': milestone,
                    'spawn_exchange_profit': round(current_profit, 2)
                }
                
                await db.bots_collection.insert_one(new_bot)
                
                # Record milestone to prevent duplicate spawns
                await profit_ledger.record_spawn_milestone(
                    user_id, exchange, trading_mode, milestone, bot_id
                )
                
                spawned_bots.append({
                    "bot_id": bot_id,
                    "bot_name": new_bot['name'],
                    "exchange": exchange,
                    "capital": min_funding,
                    "milestone": milestone,
                    "exchange_profit": round(current_profit, 2)
                })
                
                logger.info(f"  ✅ Spawned bot on {exchange}: {new_bot['name']} (milestone {milestone}, profit R{current_profit:.2f})")
            
            # Summary
            if spawned_bots:
                logger.info(f"✅ Auto-spawned {len(spawned_bots)} bot(s)")
            else:
                logger.info(f"No bots spawned ({len(reasons)} exchanges checked)")
            
            return {
                "success": True,
                "spawned": len(spawned_bots) > 0,
                "bots": spawned_bots,
                "count": len(spawned_bots),
                "reasons": reasons  # Why other exchanges didn't spawn
            }
            
        except Exception as e:
            logger.error(f"Auto-spawn bot error: {e}", exc_info=True)
            return {"success": False, "error": str(e)}

# Global instance
capital_allocator = CapitalAllocator()
