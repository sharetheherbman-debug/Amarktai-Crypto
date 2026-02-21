"""
Risk Management System - Stop Loss, Take Profit, Trailing Stop
Critical safety features for live trading
"""
import asyncio
from datetime import datetime, timezone
import database as db
from logger_config import logger
from typing import Optional, Dict

# Default risk parameters
DEFAULT_STOP_LOSS_PCT = 2.0  # 2% stop loss
DEFAULT_TAKE_PROFIT_PCT = 5.0  # 5% take profit
DEFAULT_TRAILING_STOP_PCT = 3.0  # 3% trailing stop

class RiskManagement:
    def __init__(self):
        self.active_positions = {}  # Track entry prices and stops
        self.is_running = False
        self.task = None
    
    async def set_position(self, bot_id: str, entry_price: float, 
                          stop_loss_pct: float = None, 
                          take_profit_pct: float = None,
                          trailing_stop_pct: float = None):
        """
        Set stop loss and take profit for a new position
        
        Args:
            bot_id: Bot identifier
            entry_price: Entry price of the trade
            stop_loss_pct: Stop loss percentage (default 2%)
            take_profit_pct: Take profit percentage (default 5%)
            trailing_stop_pct: Trailing stop percentage (default 3%)
        """
        stop_loss = stop_loss_pct or DEFAULT_STOP_LOSS_PCT
        take_profit = take_profit_pct or DEFAULT_TAKE_PROFIT_PCT
        trailing = trailing_stop_pct or DEFAULT_TRAILING_STOP_PCT
        
        # Calculate absolute prices
        stop_loss_price = entry_price * (1 - stop_loss / 100)
        take_profit_price = entry_price * (1 + take_profit / 100)
        trailing_stop_price = entry_price * (1 - trailing / 100)
        
        self.active_positions[bot_id] = {
            'entry_price': entry_price,
            'stop_loss_pct': stop_loss,
            'take_profit_pct': take_profit,
            'trailing_stop_pct': trailing,
            'stop_loss_price': stop_loss_price,
            'take_profit_price': take_profit_price,
            'trailing_stop_price': trailing_stop_price,
            'highest_price': entry_price,
            'opened_at': datetime.now(timezone.utc)
        }
        
        logger.info(f"🎯 Risk set for bot {bot_id}: SL={stop_loss}%, TP={take_profit}%, Trail={trailing}%")
    
    async def check_position(self, bot_id: str, current_price: float) -> Optional[Dict]:
        """
        Check if stop loss or take profit is triggered
        
        Returns:
            Dict with action ('stop_loss', 'take_profit', 'trailing_stop') or None
        """
        if bot_id not in self.active_positions:
            return None
        
        position = self.active_positions[bot_id]
        entry_price = position['entry_price']
        
        # Calculate current profit/loss percentage
        pnl_pct = ((current_price - entry_price) / entry_price) * 100
        
        # Check STOP LOSS
        if current_price <= position['stop_loss_price']:
            logger.warning(f"🛑 STOP LOSS triggered for bot {bot_id}: {pnl_pct:.2f}%")
            return {
                'action': 'stop_loss',
                'reason': f"Stop loss triggered at {pnl_pct:.2f}%",
                'exit_price': current_price,
                'pnl_pct': pnl_pct
            }
        
        # Check TAKE PROFIT
        if current_price >= position['take_profit_price']:
            logger.info(f"✅ TAKE PROFIT triggered for bot {bot_id}: +{pnl_pct:.2f}%")
            return {
                'action': 'take_profit',
                'reason': f"Take profit triggered at +{pnl_pct:.2f}%",
                'exit_price': current_price,
                'pnl_pct': pnl_pct
            }
        
        # Update TRAILING STOP
        if current_price > position['highest_price']:
            position['highest_price'] = current_price
            # Move trailing stop up
            new_trailing_price = current_price * (1 - position['trailing_stop_pct'] / 100)
            if new_trailing_price > position['trailing_stop_price']:
                position['trailing_stop_price'] = new_trailing_price
                logger.debug(f"📈 Trailing stop updated for bot {bot_id}: R{new_trailing_price:.2f}")
        
        # Check TRAILING STOP
        if current_price <= position['trailing_stop_price'] and position['highest_price'] > entry_price:
            profit_secured = ((position['trailing_stop_price'] - entry_price) / entry_price) * 100
            logger.info(f"🔒 TRAILING STOP triggered for bot {bot_id}: Secured +{profit_secured:.2f}%")
            return {
                'action': 'trailing_stop',
                'reason': f"Trailing stop triggered, profit secured: +{profit_secured:.2f}%",
                'exit_price': current_price,
                'pnl_pct': pnl_pct
            }
        
        return None
    
    async def close_position(self, bot_id: str):
        """Remove position from tracking"""
        if bot_id in self.active_positions:
            del self.active_positions[bot_id]
            logger.debug(f"Position closed for bot {bot_id}")
    
    async def execute_exit(self, bot_id: str, exit_price: float, reason: str) -> bool:
        """
        Execute exit order for a position
        
        Args:
            bot_id: Bot identifier
            exit_price: Exit price
            reason: Reason for exit (stop_loss, take_profit, trailing_stop)
        
        Returns:
            True if successful
        """
        try:
            bot = await db.bots_collection.find_one({"id": bot_id}, {"_id": 0})
            if not bot:
                return False
            
            # Calculate final P&L
            position = self.active_positions.get(bot_id)
            if position:
                entry_price = position['entry_price']
                pnl_pct = ((exit_price - entry_price) / entry_price) * 100
                pnl_amount = bot.get('current_capital', 0) * (pnl_pct / 100)
            else:
                pnl_amount = 0
                pnl_pct = 0
            
            # Update bot capital
            new_capital = bot.get('current_capital', 0) + pnl_amount
            new_total_profit = bot.get('total_profit', 0) + pnl_amount
            
            await db.bots_collection.update_one(
                {"id": bot_id},
                {
                    "$set": {
                        "current_capital": new_capital,
                        "total_profit": new_total_profit,
                        "last_trade_time": datetime.now(timezone.utc)
                    },
                    "$inc": {
                        "trades_count": 1,
                        "win_count": 1 if pnl_amount > 0 else 0,
                        "loss_count": 1 if pnl_amount < 0 else 0
                    }
                }
            )
            
            # Record trade
            from utils.trade_utils import build_trade_record

            trade = build_trade_record(
                {
                    "id": f"{bot_id}_{int(datetime.now(timezone.utc).timestamp())}",
                    "bot_id": bot_id,
                    "bot_name": bot.get('name'),
                    "user_id": bot.get('user_id'),
                    "pair": bot.get('pair', 'BTC/ZAR'),
                    "exchange": bot.get('exchange'),
                    "side": "sell",
                    "amount": 0.01,
                    "price": exit_price,
                    "profit_loss": pnl_amount,
                    "profit_loss_pct": pnl_pct,
                    "exit_reason": reason,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "trading_mode": bot.get("trading_mode", "paper"),
                    "is_live": bot.get("trading_mode") == "live"
                },
                user_id=bot.get('user_id'),
                bot=bot
            )
            
            await db.trades_collection.insert_one(trade)
            
            # Send real-time notification
            try:
                from realtime_events import rt_events
                await rt_events.trade_executed(bot['user_id'], trade)
                await rt_events.profit_updated(bot['user_id'], new_total_profit, bot.get('name'))
            except:
                pass
            
            # Close position tracking
            await self.close_position(bot_id)
            
            emoji = "🛑" if reason == "stop_loss" else "✅" if reason == "take_profit" else "🔒"
            logger.info(f"{emoji} Exit executed for {bot.get('name')}: {reason} at R{exit_price:.2f} ({pnl_pct:+.2f}%)")
            
            return True
        
        except Exception as e:
            logger.error(f"Exit execution error for bot {bot_id}: {e}")
            return False
    
    async def monitoring_loop(self):
        """Monitor all active positions every 10 seconds"""
        logger.info("🎯 Risk management monitoring started")
        
        while self.is_running:
            try:
                if not self.active_positions:
                    await asyncio.sleep(10)
                    continue
                
                # Check each active position
                for bot_id in list(self.active_positions.keys()):
                    bot = await db.bots_collection.find_one({"id": bot_id}, {"_id": 0})
                    if not bot or bot.get('status') != 'active':
                        await self.close_position(bot_id)
                        continue
                    
                    # Get current price from CCXT or DB snapshot
                    position = self.active_positions[bot_id]
                    current_price = None

                    # Try to fetch live price from CCXT (async-safe via to_thread)
                    try:
                        import ccxt
                        exchange_name = bot.get('exchange', 'binance').lower()
                        pair = position.get('symbol', bot.get('trading_pair', 'BTC/USDT'))
                        exchange_cls = getattr(ccxt, exchange_name, None)
                        if exchange_cls:
                            ex = exchange_cls({'enableRateLimit': True})
                            ticker = await asyncio.to_thread(ex.fetch_ticker, pair)
                            current_price = ticker.get('last') or ticker.get('close')
                    except Exception as price_err:
                        logger.debug(f"CCXT price fetch failed for risk monitor ({bot_id}): {price_err}")

                    if current_price is None:
                        # Use last known price from DB (stored in bot doc)
                        current_price = bot.get('last_price') or position['entry_price']
                        logger.debug(f"Risk monitor using cached/entry price for {bot_id}: {current_price}")
                    
                    # Check if exit triggered
                    exit_signal = await self.check_position(bot_id, current_price)
                    
                    if exit_signal:
                        # Execute exit
                        await self.execute_exit(
                            bot_id, 
                            exit_signal['exit_price'], 
                            exit_signal['action']
                        )
                
                await asyncio.sleep(10)  # Check every 10 seconds
            
            except Exception as e:
                logger.error(f"Risk monitoring error: {e}")
                await asyncio.sleep(60)
    
    def start(self):
        """Start risk management monitoring"""
        if not self.is_running:
            self.is_running = True
            self.task = asyncio.create_task(self.monitoring_loop())
            logger.info("✅ Risk management started - Stop Loss, Take Profit, Trailing Stop active")
    
    def stop(self):
        """Stop risk management monitoring"""
        self.is_running = False
        if self.task:
            self.task.cancel()
        logger.info("⏹️ Risk management stopped")


# Global instance
risk_management = RiskManagement()
