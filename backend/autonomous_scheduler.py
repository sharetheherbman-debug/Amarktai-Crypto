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
                    user_id = user.get('id')
                    
                    # 1. Check bot promotions
                    promotions = await bot_lifecycle.check_promotions()
                    if promotions > 0:
                        logger.info(f"Promoted {promotions} bots for user {user_id}")
                    
                    # 2. Rank bot performance
                    await performance_ranker.rank_bots(user_id)
                
                logger.info("✅ Hourly tasks completed")
                
            except Exception as e:
                logger.error(f"Hourly tasks failed: {e}")
            
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
                    user_id = user.get('id')
                    
                    # 1. Reallocate capital
                    reallocation_result = await capital_allocator.reallocate_capital(user_id)
                    logger.info(f"Reallocation for {user_id}: {reallocation_result}")
                    
                    # 2. Reinvest profits
                    reinvest_result = await capital_allocator.reinvest_daily_profits(user_id)
                    logger.info(f"Reinvestment for {user_id}: {reinvest_result}")
                    
                    # 3. Check for auto-spawn
                    spawn_result = await capital_allocator.auto_spawn_bot(user_id)
                    if spawn_result.get('spawned'):
                        logger.info(f"🎉 Auto-spawned bot for {user_id}")
                
                logger.info("Running daily learning...")
                # Trigger self-learning for all users
                # self_learning.run_daily_analysis()
                
                logger.info("Running daily healing checks...")
                # AI Bodyguard + Self-Healing
                # self_healing.scan_all_users()
                
                logger.info("Running auto-promotion check...")
                # Check all bots for 7-day promotion eligibility
                await auto_promotion_manager.run_daily_check()
                
                # Removed "spawn to 65" logic - auto-spawning is now profit-gated per exchange
                # and enforces per-exchange bot caps (Luno: 5, others: 10)
                # See backend/rules/bot_rules.py for details
                
                logger.info("✅ Daily tasks completed")
                
            except Exception as e:
                logger.error(f"Daily tasks failed: {e}")
            
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
