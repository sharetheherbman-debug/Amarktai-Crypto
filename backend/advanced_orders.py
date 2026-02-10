"""
Advanced Order Types
- Stop-loss orders
- Trailing stops
- Take-profit orders
- OCO (One-Cancels-Other)
"""

import asyncio
from datetime import datetime, timezone
from logger_config import logger
import database as db


class AdvancedOrderManager:
    def __init__(self):
        self.active_orders = {}
        self.order_monitor_task = None
    
    async def create_stop_loss(self, bot_id: str, pair: str, stop_price: float, current_price: float):
        """Create stop-loss order"""
        order_id = f"sl_{bot_id}_{int(datetime.now(timezone.utc).timestamp())}"
        
        order = {
            "id": order_id,
            "bot_id": bot_id,
            "type": "stop_loss",
            "pair": pair,
            "stop_price": stop_price,
            "status": "active",
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        
        self.active_orders[order_id] = order
        logger.info(f"Stop-loss created: {pair} at R{stop_price:.2f}")
        return order
    
    async def create_trailing_stop(self, bot_id: str, pair: str, trail_percent: float, current_price: float):
        """Create trailing stop order"""
        order_id = f"ts_{bot_id}_{int(datetime.now(timezone.utc).timestamp())}"
        
        order = {
            "id": order_id,
            "bot_id": bot_id,
            "type": "trailing_stop",
            "pair": pair,
            "trail_percent": trail_percent,
            "highest_price": current_price,
            "current_stop": current_price * (1 - trail_percent / 100),
            "status": "active",
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        
        self.active_orders[order_id] = order
        logger.info(f"Trailing stop created: {pair} trail {trail_percent}%")
        return order
    
    async def create_take_profit(self, bot_id: str, pair: str, target_price: float):
        """Create take-profit order"""
        order_id = f"tp_{bot_id}_{int(datetime.now(timezone.utc).timestamp())}"
        
        order = {
            "id": order_id,
            "bot_id": bot_id,
            "type": "take_profit",
            "pair": pair,
            "target_price": target_price,
            "status": "active",
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        
        self.active_orders[order_id] = order
        logger.info(f"Take-profit created: {pair} at R{target_price:.2f}")
        return order
    
    async def monitor_orders(self):
        """Monitor and execute advanced orders"""
        while True:
            try:
                for order_id, order in list(self.active_orders.items()):
                    if order['status'] != 'active':
                        continue
                    
                    # Get current price
                    from paper_trading_engine import paper_engine
                    current_price = await paper_engine.get_real_price(
                        order['pair'], 'luno'
                    )
                    
                    executed = False
                    
                    if order['type'] == 'stop_loss':
                        if current_price <= order['stop_price']:
                            await self._execute_order(order, current_price, 'Stop-loss triggered')
                            executed = True
                    
                    elif order['type'] == 'trailing_stop':
                        # Update highest price
                        if current_price > order['highest_price']:
                            order['highest_price'] = current_price
                            order['current_stop'] = current_price * (
                                1 - order['trail_percent'] / 100
                            )
                        
                        # Check if stop hit
                        if current_price <= order['current_stop']:
                            await self._execute_order(order, current_price, 'Trailing stop triggered')
                            executed = True
                    
                    elif order['type'] == 'take_profit':
                        if current_price >= order['target_price']:
                            await self._execute_order(order, current_price, 'Take-profit triggered')
                            executed = True
                    
                    if executed:
                        del self.active_orders[order_id]
                
            except Exception as e:
                logger.error(f"Order monitoring error: {e}")
            
            await asyncio.sleep(5)  # Check every 5 seconds
    
    async def _execute_order(self, order: dict, price: float, reason: str):
        """Execute advanced order"""
        try:
            # Get bot
            bot = await db.bots_collection.find_one(
                {"id": order['bot_id']},
                {"_id": 0}
            )
            
            if not bot:
                return
            
            # Create trade record
            from utils.trade_utils import build_trade_record

            trade = build_trade_record(
                {
                    "bot_id": order['bot_id'],
                    "user_id": bot['user_id'],
                    "exchange": bot.get('exchange', 'luno'),
                    "pair": order['pair'],
                    "side": "sell",
                    "price": price,
                    "pnl": 0,  # Calculate based on position
                    "reason": reason,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "trading_mode": bot.get("trading_mode", "paper"),
                    "is_live": bot.get("trading_mode") == "live"
                },
                user_id=bot['user_id'],
                bot=bot
            )
            
            await db.trades_collection.insert_one(trade)
            order['status'] = 'executed'
            
            logger.info(f"Order executed: {order['type']} for {order['pair']} at R{price:.2f}")
            
        except Exception as e:
            logger.error(f"Order execution failed: {e}")
    
    async def start(self):
        """Start order monitoring"""
        if self.order_monitor_task is None:
            self.order_monitor_task = asyncio.create_task(self.monitor_orders())
            logger.info("📈 Advanced orders monitoring started")
    
    async def stop(self):
        """Stop order monitoring"""
        if self.order_monitor_task:
            self.order_monitor_task.cancel()
            self.order_monitor_task = None


# Global instance
advanced_orders = AdvancedOrderManager()
