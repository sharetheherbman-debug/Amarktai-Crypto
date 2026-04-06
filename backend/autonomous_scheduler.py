"""
Autonomous Scheduler
- Runs daily/hourly tasks for autonomous trading
- Bot lifecycle checks, capital reallocation, profit reinvestment
- Market regime detection
"""

import asyncio
from datetime import datetime, timezone
from logger_config import logger
from bot_lifecycle import bot_lifecycle
from performance_ranker import performance_ranker
from engines.capital_allocator import capital_allocator
from market_regime import market_regime_detector
import database as db
from engines.self_healing import self_healing
from engines.auto_promotion_manager import auto_promotion_manager
from engines.bot_spawner import bot_spawner
from engines.wallet_manager import wallet_manager


class AutonomousScheduler:
    def __init__(self):
        self.is_running = False
        self.tasks = []
    
    async def start(self):
        """Start autonomous scheduler"""
        if self.is_running:
            logger.warning("Autonomous scheduler already running")
            return
        
        self.is_running = True
        logger.info("🤖 Autonomous scheduler started")
        
        # Start background tasks
        self.tasks = [
            asyncio.create_task(self._hourly_tasks()),
            asyncio.create_task(self._daily_tasks()),
            asyncio.create_task(self._regime_monitor())
        ]
    
    async def stop(self):
        """Stop autonomous scheduler"""
        self.is_running = False
        
        for task in self.tasks:
            task.cancel()
        
        logger.info("❌ Autonomous scheduler stopped")
    
    async def _hourly_tasks(self):
        """Tasks that run every hour"""
        while self.is_running:
            try:
                logger.info("⏰ Running hourly autonomous tasks...")
                
                # Get all users
                users = await db.users_collection.find({}, {"_id": 0}).to_list(1000)
                
                for user in users:
                    try:
                        user_id = user.get('id')
                        if not user_id:
                            continue
                        
                        # 1. Check bot promotions
                        try:
                            promotions = await bot_lifecycle.check_promotions()
                            if isinstance(promotions, dict) and promotions.get('promoted_count', 0) > 0:
                                logger.info(f"Promoted {promotions['promoted_count']} bots for user {user_id}")
                        except Exception as e:
                            logger.error(f"Bot promotion check failed for user {user_id}: {e}")
                        
                        # 2. Rank bot performance
                        try:
                            await performance_ranker.rank_bots(user_id)
                        except Exception as e:
                            logger.error(f"Bot ranking failed for user {user_id}: {e}")
                    
                    except Exception as e:
                        logger.error(f"Hourly tasks failed for user {user.get('id', 'unknown')} (sub-task error): {e}")
                        continue  # Continue with next user
                
                logger.info("✅ Hourly tasks completed")
                
            except Exception as e:
                logger.error(f"Hourly tasks loop error: {e}", exc_info=True)
            
            # Wait 1 hour
            await asyncio.sleep(3600)
    
    async def _daily_tasks(self):
        """Tasks that run once per day"""
        while self.is_running:
            try:
                logger.info("🌅 Running daily autonomous tasks...")
                
                # Get all users
                users = await db.users_collection.find({}, {"_id": 0}).to_list(1000)
                
                for user in users:
                    try:
                        user_id = user.get('id')
                        if not user_id:
                            continue
                        
                        # 1. Reallocate capital
                        try:
                            reallocation_result = await capital_allocator.reallocate_capital(user_id)
                            logger.info(f"Reallocation for {user_id}: {reallocation_result}")
                        except Exception as e:
                            logger.error(f"Capital reallocation failed for user {user_id}: {e}")
                        
                        # 2. Reinvest profits
                        try:
                            reinvest_result = await capital_allocator.reinvest_daily_profits(user_id)
                            logger.info(f"Reinvestment for {user_id}: {reinvest_result}")
                        except Exception as e:
                            logger.error(f"Profit reinvestment failed for user {user_id}: {e}")
                        
                        # 3. Check for auto-spawn (use current trading mode)
                        try:
                            modes = await db.system_modes_collection.find_one({"user_id": user_id}, {"_id": 0}) or {}
                            trading_mode = "live" if modes.get("liveTrading") else "paper"
                            spawn_result = await capital_allocator.auto_spawn_bot(user_id, trading_mode=trading_mode)
                            if spawn_result.get('spawned'):
                                logger.info(f"🎉 Auto-spawned bot for {user_id}")
                        except Exception as e:
                            logger.error(f"Auto-spawn failed for user {user_id}: {e}")
                    
                    except Exception as e:
                        logger.error(f"Daily tasks failed for user {user.get('id', 'unknown')}: {e}")
                        continue  # Continue with next user
                
                # Daily system-wide tasks
                try:
                    logger.info("Running daily learning...")
                    # Trigger self-learning for all users
                    # self_learning.run_daily_analysis()
                except Exception as e:
                    logger.error(f"Daily learning failed: {e}")
                
                try:
                    logger.info("Running daily healing checks...")
                    # AI Bodyguard + Self-Healing - runs daily scans of all users
                    await self_healing.scan_all_users()
                except Exception as e:
                    logger.error(f"Daily healing scan failed: {e}")
                
                try:
                    logger.info("Running auto-promotion check...")
                    # Check all bots for 7-day promotion eligibility
                    await auto_promotion_manager.run_daily_check()
                except Exception as e:
                    logger.error(f"Auto-promotion check failed: {e}")
                
                # Removed "spawn to 65" logic - auto-spawning is now profit-gated per exchange
                # and enforces per-exchange bot caps (Luno: 5, others: 10)
                # See backend/rules/bot_rules.py for details
                
                logger.info("✅ Daily tasks completed")
                
            except Exception as e:
                logger.error(f"Daily tasks loop error: {e}", exc_info=True)
            
            # Wait 24 hours
            await asyncio.sleep(86400)
    
    async def _regime_monitor(self):
        """Monitor market regimes every 15 minutes"""
        while self.is_running:
            try:
                logger.info("📊 Monitoring market regimes...")
                
                # Detect regime for major pairs
                pairs = ['BTC/ZAR', 'ETH/ZAR', 'XRP/ZAR']
                regimes = {}
                
                for pair in pairs:
                    regime = await market_regime_detector.detect_regime(pair)
                    regimes[pair] = regime
                
                # Get all active bots and adjust based on their trading pair
                bots = await db.bots_collection.find(
                    {"status": "active"},
                    {"_id": 0}
                ).to_list(1000)
                
                for bot in bots:
                    pair = bot.get('trading_pair', 'BTC/ZAR')
                    if pair in regimes:
                        await market_regime_detector.adjust_bot_for_regime(bot, regimes[pair])
                
                logger.info(f"✅ Regime monitoring completed for {len(pairs)} pairs")
                
            except Exception as e:
                logger.error(f"Regime monitoring failed: {e}")
            
            # Wait 15 minutes
            await asyncio.sleep(900)


# Global instance
autonomous_scheduler = AutonomousScheduler()
