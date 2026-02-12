"""
LIVE TRADING ENGINE - Real Exchange Orders
Replaces simulated trading with actual CCXT order execution
"""

import asyncio
import os
import ccxt
from typing import Dict, Optional, List
from datetime import datetime, timezone, timedelta
from decimal import Decimal
import logging

import database as db
from ccxt_service import CCXTService
from engines.risk_management import risk_management
from utils.trading_gates import enforce_live_trading_gates, TradingGateError
from config import *

logger = logging.getLogger(__name__)

class LiveTradingEngine:
    def __init__(self):
        self.ccxt_service = CCXTService()
        self.active_exchanges = {}  # user_id -> {exchange_name: ccxt_instance}
        self.open_orders = {}  # order_id -> order_data
        
    async def init_user_exchanges(self, user_id: str) -> Dict[str, ccxt.Exchange]:
        """Initialize all exchange connections for a user"""
        try:
            api_keys = await db.api_keys_collection.find(
                {"user_id": user_id},
                {"_id": 0}
            ).to_list(100)
            
            exchanges = {}
            for key_doc in api_keys:
                exchange_name = key_doc['exchange'].lower()
                try:
                    exchange = self.ccxt_service.init_exchange(
                        exchange_name,
                        key_doc['api_key'],
                        key_doc['api_secret'],
                        testnet=False,
                        passphrase=key_doc.get('passphrase')
                    )
                    exchanges[exchange_name] = exchange
                    logger.info(f"✅ Initialized {exchange_name} for user {user_id[:8]}")
                except Exception as e:
                    logger.error(f"❌ Failed to init {exchange_name}: {e}")
                    
            return exchanges
        except Exception as e:
            logger.error(f"Failed to init user exchanges: {e}")
            return {}
    
    def normalize_symbol(self, symbol: str, exchange_name: str) -> str:
        """Normalize symbol for specific exchange"""
        symbol_map = {
            'luno': {
                'BTC/ZAR': 'XBTZAR',
                'ETH/ZAR': 'ETHZAR',
                'XRP/ZAR': 'XRPZAR'
            },
            'binance': {
                'BTC/ZAR': 'BTC/ZAR',
                'ETH/ZAR': 'ETH/ZAR',
                'BTC/USDT': 'BTC/USDT'
            },
            'kucoin': {
                'BTC/USDT': 'BTC/USDT',
                'ETH/USDT': 'ETH/USDT'
            }
        }
        
        return symbol_map.get(exchange_name, {}).get(symbol, symbol)
    
    async def get_real_price(self, exchange: ccxt.Exchange, symbol: str) -> Optional[float]:
        """Get real current price from unified market data"""
        try:
            from paper_trading_engine import paper_engine

            snapshot = await paper_engine.get_market_snapshot(symbol, exchange.id if exchange else "luno")
            return snapshot.get("mid")
        except Exception as e:
            logger.error(f"Failed to fetch price for {symbol}: {e}")
            return None
    
    async def place_limit_order(self, exchange: ccxt.Exchange, symbol: str, 
                               side: str, amount: float, price: float) -> Optional[Dict]:
        """Place real limit order"""
        try:
            order = await asyncio.to_thread(
                exchange.create_limit_order,
                symbol, side, amount, price
            )
            
            logger.info(f"✅ Limit order placed: {side} {amount} {symbol} @ {price}")
            return order
            
        except ccxt.InsufficientFunds as e:
            logger.error(f"❌ Insufficient funds: {e}")
            return None
        except ccxt.InvalidOrder as e:
            logger.error(f"❌ Invalid order: {e}")
            return None
        except ccxt.RateLimitExceeded as e:
            logger.error(f"⏳ Rate limit exceeded: {e}")
            await asyncio.sleep(2)
            return None
        except Exception as e:
            logger.error(f"❌ Order placement failed: {e}")
            return None
    
    async def place_market_order(self, exchange: ccxt.Exchange, symbol: str, 
                                 side: str, amount: float) -> Optional[Dict]:
        """Place real market order"""
        try:
            order = await asyncio.to_thread(
                exchange.create_market_order,
                symbol, side, amount
            )
            
            logger.info(f"✅ Market order placed: {side} {amount} {symbol}")
            return order
            
        except ccxt.InsufficientFunds as e:
            logger.error(f"❌ Insufficient funds: {e}")
            return None
        except ccxt.InvalidOrder as e:
            logger.error(f"❌ Invalid order: {e}")
            return None
        except ccxt.RateLimitExceeded as e:
            logger.error(f"⏳ Rate limit exceeded: {e}")
            await asyncio.sleep(2)
            return None
        except Exception as e:
            logger.error(f"❌ Order placement failed: {e}")
            return None
    
    async def check_order_status(self, exchange: ccxt.Exchange, order_id: str, 
                                 symbol: str) -> Optional[Dict]:
        """Check status of an order"""
        try:
            order = await asyncio.to_thread(
                exchange.fetch_order,
                order_id, symbol
            )
            return order
        except Exception as e:
            logger.error(f"Failed to check order status: {e}")
            return None
    
    async def cancel_order(self, exchange: ccxt.Exchange, order_id: str, 
                          symbol: str) -> bool:
        """Cancel an open order"""
        try:
            await asyncio.to_thread(exchange.cancel_order, order_id, symbol)
            logger.info(f"✅ Order {order_id} cancelled")
            return True
        except Exception as e:
            logger.error(f"Failed to cancel order: {e}")
            return False
    
    async def execute_trade(self, bot_id: str, bot_data: Dict, symbol: str, 
                           side: str, amount: float, price: Optional[float] = None,
                           paper_mode: bool = True) -> Dict:
        """Execute a single trade (paper or live)"""
        try:
            user_id = bot_data['user_id']
            exchange_name = bot_data['exchange'].lower()
            expected_move_pct = abs(float(bot_data.get("expected_move_pct", 0) or 0))
            
            # TRADING MODE GATE: Check if live trading before placing real orders
            if not paper_mode:
                try:
                    await enforce_live_trading_gates(user_id, exchange_name)
                except TradingGateError as e:
                    logger.error(f"Live trading gate check failed: {e}")
                    return {
                        "success": False,
                        "error": str(e)
                    }
            
            # Get exchange instance
            if user_id not in self.active_exchanges:
                self.active_exchanges[user_id] = await self.init_user_exchanges(user_id)
            
            exchange = self.active_exchanges[user_id].get(exchange_name)
            
            if not exchange and not paper_mode:
                return {
                    "success": False,
                    "error": f"Exchange {exchange_name} not initialized"
                }
            
            # Normalize symbol
            normalized_symbol = self.normalize_symbol(symbol, exchange_name)
            
            # Paper trading (realistic simulation with real prices)
            if paper_mode:
                current_price = await self.get_real_price(exchange, normalized_symbol) if exchange else None
                if not current_price:
                    # Fallback to default prices if exchange unavailable
                    current_price = 1000000 if 'BTC' in symbol else 50000
                
                # Calculate realistic outcome
                entry_price = current_price
                
                # Simulate a realistic exit (small price movement)
                import random
                if side == 'buy':
                    # Simulate 0.5-2% price movement
                    exit_price = entry_price * random.uniform(1.005, 1.02)
                else:
                    exit_price = entry_price * random.uniform(0.98, 0.995)
                
                # Calculate fees (exchange-specific)
                fee_rates = {
                    'luno': 0.0025,  # 0.25%
                    'binance': 0.001,  # 0.1%
                    'kucoin': 0.001   # 0.1%
                }
                fee_rate = fee_rates.get(exchange_name, 0.001)
                
                gross_profit = (exit_price - entry_price) * amount
                fees = (entry_price * amount * fee_rate) + (exit_price * amount * fee_rate)
                net_profit = gross_profit - fees
                
                return {
                    "success": True,
                    "order_id": f"paper_{datetime.now(timezone.utc).timestamp()}",
                    "symbol": symbol,
                    "side": side,
                    "amount": amount,
                    "entry_price": entry_price,
                    "exit_price": exit_price,
                    "gross_profit": gross_profit,
                    "fees": fees,
                    "net_profit": net_profit,
                    "paper": True,
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
            
            # LIVE TRADING - Real orders
            else:
                # Check risk before placing order
                position_value = amount * (price or await self.get_real_price(exchange, normalized_symbol))
                risk_ok, risk_reason = await risk_management.check_trade_risk(
                    user_id, bot_id, exchange_name, position_value, bot_data.get('risk_mode', 'safe')
                )
                
                if not risk_ok:
                    return {
                        "success": False,
                        "error": f"Risk check failed: {risk_reason}"
                    }

                # Optional edge gate for live trading
                try:
                    from config import EDGE_GATE_LIVE, EDGE_BUFFER_PCT
                    from exchange_limits import get_fee_rate
                    if EDGE_GATE_LIVE and expected_move_pct:
                        from paper_trading_engine import paper_engine
                        snapshot = await paper_engine.get_market_snapshot(normalized_symbol, exchange_name)
                        bid = snapshot.get("bid")
                        ask = snapshot.get("ask")
                        if bid and ask and bid > 0:
                            spread_pct = ((ask - bid) / ((ask + bid) / 2)) * 100
                        else:
                            spread_pct = 0.1
                        fee_pct_roundtrip = get_fee_rate(exchange_name, "taker") * 2 * 100
                        slippage_pct_roundtrip = float(os.getenv("LIVE_SLIPPAGE_PCT", "0.05")) * 2
                        estimated_cost_pct = fee_pct_roundtrip + slippage_pct_roundtrip + spread_pct
                        if expected_move_pct < estimated_cost_pct + EDGE_BUFFER_PCT:
                            return {
                                "success": False,
                                "error": "Edge gate blocked trade",
                                "skip_reason": "edge_gate",
                                "details": {
                                    "expected_move_pct": expected_move_pct,
                                    "estimated_cost_pct": round(estimated_cost_pct, 4),
                                    "edge_buffer_pct": EDGE_BUFFER_PCT,
                                    "spread_pct": round(spread_pct, 4)
                                }
                            }
                except Exception as e:
                    logger.debug(f"Live edge gate skipped: {e}")
                
                # Place order
                if price:
                    # Limit order
                    order = await self.place_limit_order(exchange, normalized_symbol, side, amount, price)
                else:
                    # Market order
                    order = await self.place_market_order(exchange, normalized_symbol, side, amount)
                
                if not order:
                    return {
                        "success": False,
                        "error": "Order placement failed"
                    }
                
                # Store order for monitoring
                self.open_orders[order['id']] = {
                    "bot_id": bot_id,
                    "order": order,
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
                
                # Wait for fill (or timeout after 30 seconds for limit orders)
                filled_order = await self.wait_for_fill(exchange, order['id'], normalized_symbol, timeout=30)
                
                if filled_order and filled_order['status'] == 'closed':
                    # Extract real data from filled order
                    avg_price = filled_order.get('average') or filled_order.get('price')
                    filled_amount = filled_order.get('filled', amount)
                    
                    # Get real fee from exchange
                    fee_data = filled_order.get('fee', {})
                    fee_amount = fee_data.get('cost', 0)
                    fee_currency = fee_data.get('currency', 'USDT')
                    
                    return {
                        "success": True,
                        "order_id": order['id'],
                        "symbol": symbol,
                        "side": side,
                        "amount": filled_amount,
                        "price": avg_price,
                        "fee_amount": fee_amount,
                        "fee_currency": fee_currency,
                        "paper": False,
                        "timestamp": filled_order.get('timestamp'),
                        "exchange_response": filled_order
                    }
                else:
                    # Order not filled - cancel it
                    await self.cancel_order(exchange, order['id'], normalized_symbol)
                    return {
                        "success": False,
                        "error": "Order not filled within timeout"
                    }
                    
        except Exception as e:
            logger.error(f"Trade execution error: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    async def wait_for_fill(self, exchange: ccxt.Exchange, order_id: str, 
                           symbol: str, timeout: int = 30) -> Optional[Dict]:
        """Wait for order to fill"""
        start_time = datetime.now(timezone.utc)
        
        while (datetime.now(timezone.utc) - start_time).seconds < timeout:
            order = await self.check_order_status(exchange, order_id, symbol)
            
            if order and order['status'] in ['closed', 'filled']:
                return order
            elif order and order['status'] in ['canceled', 'rejected', 'expired']:
                return order
            
            await asyncio.sleep(1)  # Check every second
        
        return None
    
    async def monitor_open_positions(self, user_id: str):
        """Monitor open positions for stop loss / take profit"""
        try:
            # Get all active live bots for user
            bots = await db.bots_collection.find(
                {"user_id": user_id, "status": "active", "mode": "live"},
                {"_id": 0}
            ).to_list(100)
            
            for bot in bots:
                # Get bot's open positions (from recent trades)
                recent_trades = await db.trades_collection.find(
                    {"bot_id": bot['id'], "status": "open"},
                    {"_id": 0}
                ).sort("timestamp", -1).to_list(10)
                
                for trade in recent_trades:
                    # Get current price
                    exchange = self.active_exchanges.get(user_id, {}).get(bot['exchange'])
                    if not exchange:
                        continue
                    
                    current_price = await self.get_real_price(exchange, trade['pair'])
                    if not current_price:
                        continue
                    
                    # Check stop loss
                    entry_price = trade.get('entry_price', 0)
                    stop_loss_pct = bot.get('stop_loss_pct', 0.02)  # Default 2%
                    
                    if trade['side'] == 'buy':
                        # Long position - check if price dropped below stop loss
                        stop_loss_price = entry_price * (1 - stop_loss_pct)
                        if current_price <= stop_loss_price:
                            logger.warning(f"🚨 Stop loss triggered for {bot['name']} - {trade['pair']}")
                            # Close position
                            await self.close_position(bot, trade, current_price, "stop_loss")
                    else:
                        # Short position - check if price rose above stop loss
                        stop_loss_price = entry_price * (1 + stop_loss_pct)
                        if current_price >= stop_loss_price:
                            logger.warning(f"🚨 Stop loss triggered for {bot['name']} - {trade['pair']}")
                            await self.close_position(bot, trade, current_price, "stop_loss")
                
        except Exception as e:
            logger.error(f"Position monitoring error: {e}")
    
    async def close_position(self, bot: Dict, trade: Dict, exit_price: float, reason: str):
        """Close a position (stop loss or take profit)"""
        try:
            # Calculate P/L
            entry_price = trade['entry_price']
            amount = trade['amount']
            
            if trade['side'] == 'buy':
                pnl = (exit_price - entry_price) * amount
            else:
                pnl = (entry_price - exit_price) * amount
            
            # Update trade in database
            await db.trades_collection.update_one(
                {"id": trade['id']},
                {"$set": {
                    "status": "closed",
                    "exit_price": exit_price,
                    "exit_reason": reason,
                    "profit_loss": pnl,
                    "closed_at": datetime.now(timezone.utc).isoformat()
                }}
            )
            
            # Update bot capital
            new_capital = bot['current_capital'] + pnl
            await db.bots_collection.update_one(
                {"id": bot['id']},
                {"$set": {"current_capital": new_capital}}
            )
            
            # Create alert
            await db.alerts_collection.insert_one({
                "user_id": bot['user_id'],
                "type": "stop_loss" if reason == "stop_loss" else "take_profit",
                "severity": "high",
                "message": f"Position closed: {bot['name']} - {trade['pair']} at R{exit_price:.2f} ({reason})",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "dismissed": False
            })
            
            logger.info(f"✅ Position closed: {bot['name']} - {reason}")
            
        except Exception as e:
            logger.error(f"Close position error: {e}")

# Global instance
live_trading_engine = LiveTradingEngine()
