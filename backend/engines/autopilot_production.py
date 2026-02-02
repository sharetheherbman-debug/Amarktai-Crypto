"""
Production Autopilot Engine - Complete Implementation
- Auto-spawn new bots when profit threshold reached
- Intelligent capital rebalancing
- Real-time WebSocket notifications
"""
import asyncio
from datetime import datetime, timezone
import database as db
from engines.bot_manager import bot_manager
from logger_config import logger
from config import (
    NEW_BOT_SEED_CAPITAL_ZAR,
    BOT_SPAWN_PROFIT_THRESHOLD_ZAR,
    MAX_TOTAL_BOTS,
    EXCHANGE_BOT_LIMITS
)

# Autopilot Configuration
REINVEST_THRESHOLD = BOT_SPAWN_PROFIT_THRESHOLD_ZAR  # When to spawn new bot
MIN_BOT_CAPITAL = NEW_BOT_SEED_CAPITAL_ZAR  # Capital for new bot
REBALANCE_INTERVAL = 3600  # 1 hour
CHECK_INTERVAL = 300  # 5 minutes


class ProductionAutopilot:
    def __init__(self):
        self.is_running = False
        self.task = None
        self.last_rebalance = {}
    
    async def calculate_total_profit(self, user_id: str) -> float:
        """Calculate total unreinvested profit across all bots"""
        try:
            bots = await db.bots_collection.find({"user_id": user_id}, {"_id": 0}).to_list(1000)
            total_profit = sum(bot.get('total_profit', 0) for bot in bots)
            return total_profit
        except Exception as e:
            logger.error(f"Calculate profit error: {e}")
            return 0.0
    
    async def reinvest_profits(self, user_id: str) -> dict:
        """
        Bot Spawning Logic:
        - Every BOT_SPAWN_PROFIT_THRESHOLD_ZAR profit → Create new bot OR reinvest in top performers
        - Prioritize creating new bots until limit reached
        - New bots get NEW_BOT_SEED_CAPITAL_ZAR capital
        - Then reinvest in top 5 performing bots
        """
        try:
            total_profit = await self.calculate_total_profit(user_id)
            
            if total_profit < REINVEST_THRESHOLD:
                return {
                    "reinvested": 0,
                    "action": "none",
                    "message": f"Profit R{total_profit:.2f} below R{REINVEST_THRESHOLD} spawn threshold"
                }
            
            # Calculate how many spawn thresholds we've reached
            reinvest_chunks = int(total_profit / REINVEST_THRESHOLD)
            total_to_reinvest = reinvest_chunks * REINVEST_THRESHOLD
            
            # Get current bots
            bots = await db.bots_collection.find({"user_id": user_id}, {"_id": 0}).to_list(1000)
            
            # Check if we can create new bots
            if len(bots) < MAX_TOTAL_BOTS:
                # Try to create new bots
                bots_created = 0
                remaining_capital = total_to_reinvest
                
                for exchange, limit in EXCHANGE_BOT_LIMITS.items():
                    exchange_bots = len([b for b in bots if b.get('exchange') == exchange])
                    
                    # Create bots up to exchange limit
                    while exchange_bots < limit and remaining_capital >= MIN_BOT_CAPITAL and len(bots) + bots_created < MAX_TOTAL_BOTS:
                        bot_number = len(bots) + bots_created + 1
                        result = await bot_manager.create_bot(
                            user_id=user_id,
                            name=f"Auto-Bot-{bot_number}",
                            exchange=exchange,
                            risk_mode='safe',
                            capital=MIN_BOT_CAPITAL
                        )
                        
                        if result['success']:
                            bots_created += 1
                            remaining_capital -= MIN_BOT_CAPITAL
                            exchange_bots += 1
                            logger.info(f"🤖 Autopilot: Created Auto-Bot-{bot_number} on {exchange}")
                            
                            # Send WebSocket notification
                            from websocket_manager import manager
                            await manager.send_message(user_id, {
                                "type": "force_refresh",
                                "message": f"🤖 Autopilot created new bot: Auto-Bot-{bot_number}"
                            })
                        else:
                            break
                
                if bots_created > 0:
                    # DON'T reset profit counter - new bots get fresh capital
                    # The capital used is tracked as their initial_capital
                    # await db.bots_collection.update_many(
                    #     {"user_id": user_id},
                    #     {"$inc": {"total_profit": -total_to_reinvest}}
                    # )
                    
                    return {
                        "reinvested": total_to_reinvest,
                        "action": "create_bots",
                        "bots_created": bots_created,
                        "message": f"✅ Created {bots_created} new bots with R{total_to_reinvest:.2f}"
                    }
            
            # If can't create bots, reinvest in top performers
            if len(bots) >= MAX_TOTAL_BOTS or total_to_reinvest < MIN_BOT_CAPITAL:
                # Get top 5 performing bots
                top_bots = sorted(
                    [b for b in bots if b.get('status') == 'active'],
                    key=lambda b: b.get('total_profit', 0),
                    reverse=True
                )[:5]
                
                if len(top_bots) == 0:
                    return {
                        "reinvested": 0,
                        "action": "none",
                        "message": "No active bots for reinvestment"
                    }
                
                # Distribute profit equally among top performers
                reinvest_per_bot = total_to_reinvest / len(top_bots)
                
                # Track capital injections separately
                from engines.capital_injection_tracker import capital_tracker
                
                for bot in top_bots:
                    new_capital = bot.get('current_capital', 0) + reinvest_per_bot
                    await db.bots_collection.update_one(
                        {"id": bot['id']},
                        {"$set": {"current_capital": new_capital}}
                    )
                    
                    # Record injection (keeps profit reporting accurate)
                    await capital_tracker.record_injection(
                        bot_id=bot['id'],
                        amount=reinvest_per_bot,
                        source="autopilot",
                        reason="Top performer reinvestment"
                    )
                
                # DON'T reset profit counter - injections are tracked separately now
                # await db.bots_collection.update_many(
                #     {"user_id": user_id},
                #     {"$inc": {"total_profit": -total_to_reinvest}}
                # )
                
                logger.info(f"💰 Autopilot: Reinvested R{total_to_reinvest:.2f} into top {len(top_bots)} bots")
                
                # Send WebSocket notification
                from websocket_manager import manager
                await manager.send_message(user_id, {
                    "type": "force_refresh",
                    "message": f"💰 Autopilot reinvested R{total_to_reinvest:.2f} into top performers"
                })
                
                return {
                    "reinvested": total_to_reinvest,
                    "action": "reinvest_top",
                    "bots_boosted": len(top_bots),
                    "message": f"✅ Reinvested R{total_to_reinvest:.2f} into top {len(top_bots)} performers"
                }
        
        except Exception as e:
            logger.error(f"Reinvest profits error: {e}")
            return {
                "reinvested": 0,
                "action": "error",
                "message": f"❌ Error: {str(e)}"
            }
    
    async def rebalance_capital(self, user_id: str) -> dict:
        """
        Intelligent Capital Rebalancing:
        - Move capital from bottom 30% performers to top 30%
        - Only rebalance once per hour per user
        - Preserve minimum capital for each bot
        """
        try:
            # Check if we rebalanced recently
            now = datetime.now(timezone.utc)
            last_rebalance = self.last_rebalance.get(user_id)
            
            if last_rebalance:
                time_since = (now - last_rebalance).total_seconds()
                if time_since < REBALANCE_INTERVAL:
                    return {
                        "rebalanced": 0,
                        "message": f"Rebalance on cooldown ({int(REBALANCE_INTERVAL - time_since)}s remaining)"
                    }
            
            # Get all active bots
            bots = await db.bots_collection.find(
                {"user_id": user_id, "status": "active"},
                {"_id": 0}
            ).to_list(1000)
            
            if len(bots) < 5:  # Need at least 5 bots to rebalance
                return {
                    "rebalanced": 0,
                    "message": "Need at least 5 active bots for rebalancing"
                }
            
            # Sort by performance (ROI)
            for bot in bots:
                initial = bot.get('initial_capital', 1)
                current = bot.get('current_capital', 0)
                bot['roi'] = ((current - initial) / initial * 100) if initial > 0 else 0
            
            sorted_bots = sorted(bots, key=lambda b: b['roi'], reverse=True)
            
            # Calculate cutoff points
            top_30_count = max(1, int(len(sorted_bots) * 0.3))
            bottom_30_count = max(1, int(len(sorted_bots) * 0.3))
            
            top_performers = sorted_bots[:top_30_count]
            bottom_performers = sorted_bots[-bottom_30_count:]
            
            # Calculate capital to move (10% from each bottom performer)
            total_to_move = 0
            for bot in bottom_performers:
                current_capital = bot.get('current_capital', 0)
                min_capital = bot.get('initial_capital', 1000) * 0.5  # Keep at least 50% of initial
                
                if current_capital > min_capital:
                    move_amount = min(current_capital * 0.1, current_capital - min_capital)
                    total_to_move += move_amount
                    
                    # Reduce bottom performer capital
                    await db.bots_collection.update_one(
                        {"id": bot['id']},
                        {"$inc": {"current_capital": -move_amount}}
                    )
            
            if total_to_move < 50:  # Not worth rebalancing if < R50
                return {
                    "rebalanced": 0,
                    "message": "Insufficient capital to rebalance"
                }
            
            # Distribute to top performers
            per_top_bot = total_to_move / len(top_performers)
            
            for bot in top_performers:
                await db.bots_collection.update_one(
                    {"id": bot['id']},
                    {"$inc": {"current_capital": per_top_bot}}
                )
            
            # Update last rebalance time
            self.last_rebalance[user_id] = now
            
            logger.info(f"⚖️ Autopilot: Rebalanced R{total_to_move:.2f} from {len(bottom_performers)} to {len(top_performers)} bots")
            
            # Send WebSocket notification
            from websocket_manager import manager
            await manager.send_message(user_id, {
                "type": "force_refresh",
                "message": f"⚖️ Autopilot rebalanced R{total_to_move:.2f} to top performers"
            })
            
            return {
                "rebalanced": total_to_move,
                "from_bots": len(bottom_performers),
                "to_bots": len(top_performers),
                "message": f"✅ Rebalanced R{total_to_move:.2f}"
            }
        
        except Exception as e:
            logger.error(f"Rebalance capital error: {e}")
            return {
                "rebalanced": 0,
                "message": f"❌ Error: {str(e)}"
            }
    
    async def autopilot_loop(self):
        """Main autopilot loop - runs every 5 minutes"""
        logger.info("🤖 Production Autopilot started")
        
        while self.is_running:
            try:
                # Get all users with autopilot enabled
                modes = await db.system_modes_collection.find(
                    {"autopilot": True},
                    {"_id": 0}
                ).to_list(1000)
                
                for mode in modes:
                    user_id = mode.get('user_id')
                    if not user_id:
                        continue
                    
                    # Check and reinvest profits (every check)
                    reinvest_result = await self.reinvest_profits(user_id)
                    if reinvest_result['reinvested'] > 0:
                        logger.info(f"💰 User {user_id[:8]}: {reinvest_result['message']}")
                    
                    # Rebalance capital (once per hour)
                    rebalance_result = await self.rebalance_capital(user_id)
                    if rebalance_result['rebalanced'] > 0:
                        logger.info(f"⚖️ User {user_id[:8]}: {rebalance_result['message']}")
                
                # Wait before next check
                await asyncio.sleep(CHECK_INTERVAL)
            
            except Exception as e:
                logger.error(f"Autopilot loop error: {e}")
                await asyncio.sleep(60)  # Wait 1 minute on error
    
    def start(self):
        """Start production autopilot"""
        if not self.is_running:
            self.is_running = True
            self.task = asyncio.create_task(self.autopilot_loop())
            logger.info("✅ Production Autopilot started - R500 reinvestment, auto-spawn, rebalancing")
    
    def stop(self):
        """Stop production autopilot"""
        self.is_running = False
        if self.task:
            self.task.cancel()
        logger.info("⏹️ Production Autopilot stopped")


# Global instance
autopilot_production = ProductionAutopilot()
