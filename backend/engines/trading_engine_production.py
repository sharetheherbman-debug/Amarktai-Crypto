"""
Production Trading Engine
Integrates trade limiter, paper trading, and scheduler
"""
import asyncio
from datetime import datetime, timezone, timedelta
import database as db
from engines.trade_limiter import trade_limiter
from logger_config import logger
from utils.trading_gates import enforce_trading_gates, TradingGateError


class TradingEngineProduction:
    def __init__(self):
        self.is_running = False
        self.task = None
    
    async def execute_trade_for_bot(self, bot: dict) -> bool:
        """Execute a single trade for a bot if allowed"""
        try:
            # TRADING MODE GATE: Check if any trading mode is enabled
            try:
                enforce_trading_gates()
            except TradingGateError as e:
                logger.error(f"Trading gate check failed: {e}")
                return False
            
            bot_id = bot['id']
            
            # Check if bot can trade
            can_trade, reason = await trade_limiter.can_trade(bot_id)
            
            if not can_trade:
                logger.debug(f"Bot {bot.get('name')} cannot trade: {reason}")
                return False
            
            from paper_trading_engine import paper_engine

            result = await paper_engine.run_trading_cycle(
                bot_id,
                bot,
                {"bots": db.bots_collection, "trades": db.trades_collection}
            )

            if result:
                await trade_limiter.record_trade(bot_id)
                return True
            return False
        
        except Exception as e:
            logger.error(f"Trade execution error for bot {bot.get('name')}: {e}")
            return False
    
    async def trading_loop(self):
        """Main trading loop - runs every 5 minutes"""
        logger.info("🔄 Trading engine started")
        
        while self.is_running:
            try:
                # Get all active bots
                bots = await db.bots_collection.find({
                    "status": "active"
                }, {"_id": 0}).to_list(1000)
                
                if not bots:
                    logger.debug("No active bots to trade")
                    await asyncio.sleep(300)  # 5 minutes
                    continue
                
                logger.info(f"🔍 Checking {len(bots)} active bots for trading opportunities")
                
                trades_executed = 0
                
                # Try to execute trades for each bot
                for bot in bots:
                    if await self.execute_trade_for_bot(bot):
                        trades_executed += 1
                        # Small delay between trades
                        await asyncio.sleep(1)
                
                if trades_executed > 0:
                    logger.info(f"✅ Executed {trades_executed} trades")
                
                # Wait 5 minutes before next check
                await asyncio.sleep(300)
            
            except Exception as e:
                logger.error(f"Trading loop error: {e}")
                await asyncio.sleep(60)  # Wait 1 minute on error
    
    def start(self):
        """Start the trading engine"""
        if not self.is_running:
            self.is_running = True
            self.task = asyncio.create_task(self.trading_loop())
            logger.info("✅ Trading engine started")
    
    def stop(self):
        """Stop the trading engine"""
        self.is_running = False
        if self.task:
            self.task.cancel()
        logger.info("⏹️ Trading engine stopped")
    
    async def reset_daily_counters(self):
        """Reset daily trade counters at midnight UTC"""
        from engines.bot_manager import bot_manager
        await bot_manager.reset_daily_trade_counts()


trading_engine = TradingEngineProduction()
