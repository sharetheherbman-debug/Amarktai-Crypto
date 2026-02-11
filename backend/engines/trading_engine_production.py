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
import random


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
            
            # Simulate price movement
            pair = bot.get('pair', 'BTC/ZAR')
            exchange = bot.get('exchange', 'luno')
            
            # Get current capital
            current_capital = bot.get('current_capital', 1000)
            
            # Random profit/loss between -2% to +4%
            profit_pct = random.uniform(-0.02, 0.04)
            profit_amount = current_capital * profit_pct
            
            # Simulate fees (0.1%)
            fees = abs(current_capital * 0.001)
            net_profit = profit_amount - fees
            
            # Update bot capital
            new_capital = current_capital + net_profit
            new_total_profit = bot.get('total_profit', 0) + net_profit
            
            # Update bot in database
            await db.bots_collection.update_one(
                {"id": bot_id},
                {
                    "$set": {
                        "current_capital": new_capital,
                        "total_profit": new_total_profit
                    },
                    "$inc": {
                        "win_count" if net_profit > 0 else "loss_count": 1
                    }
                }
            )
            
            # Record trade
            await trade_limiter.record_trade(bot_id)
            
            # Save trade to database
            from utils.trade_utils import build_trade_record

            trade = build_trade_record(
                {
                    "id": str(random.randint(100000, 999999)),
                    "bot_id": bot_id,
                    "user_id": bot['user_id'],
                    "exchange": exchange,
                    "pair": pair,
                    "side": "buy" if profit_amount > 0 else "sell",
                    "amount": abs(current_capital * 0.1),
                    "price": random.uniform(1000000, 1200000) if 'BTC' in pair else random.uniform(50000, 60000),
                    "profit_loss": net_profit,
                    "fees": fees,
                    "trading_mode": bot.get('trading_mode', 'paper'),
                    "is_live": bot.get('trading_mode') == 'live',
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "status": "completed"
                },
                user_id=bot['user_id'],
                bot=bot
            )
            
            await db.trades_collection.insert_one(trade)
            
            # Log trade
            emoji = "🟢" if net_profit > 0 else "🔴"
            logger.info(f"{emoji} {bot.get('name')} | {pair} | P/L: R{net_profit:+.2f}")
            
            # Set stop loss and take profit for this position
            try:
                from engines.risk_management import risk_management
                await risk_management.set_position(
                    bot_id=bot['id'],
                    entry_price=trade['price'],  # Use the trade price
                    stop_loss_pct=2.0,  # 2% stop loss
                    take_profit_pct=5.0,  # 5% take profit
                    trailing_stop_pct=3.0  # 3% trailing stop
                )
            except Exception as e:
                logger.error(f"Risk management setup error: {e}")
            
            # Send WebSocket notifications
            try:
                from websocket_manager import manager
                from realtime_events import rt_events
                
                # Trade executed notification
                await manager.send_message(bot['user_id'], {
                    "type": "trade_executed",
                    "trade": trade
                })
                
                # Profit updated notification
                await rt_events.profit_updated(bot['user_id'], new_total_profit, bot.get('name'))
            except Exception as e:
                logger.error(f"WebSocket notification error: {e}")
            
            return True
        
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
