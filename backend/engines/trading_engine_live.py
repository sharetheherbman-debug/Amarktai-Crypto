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
        """Normalize symbol for specific exchange.

        Uses a static map for exchanges that require non-slash formats.
        Falls back to the unified slash notation for all others (CCXT
        handles the final conversion to exchange-native IDs internally).
        """
        symbol_map = {
            # Luno uses non-standard concatenated format
            'luno': {
                'BTC/ZAR': 'XBTZAR',
                'ETH/ZAR': 'ETHZAR',
                'XRP/ZAR': 'XRPZAR',
                'LTC/ZAR': 'LTCZAR',
                'BCH/ZAR': 'BCHZAR',
                'USDC/ZAR': 'USDCZAR',
            },
            # Binance — unified slash format works; include common ZAR pairs
            'binance': {
                'BTC/ZAR': 'BTC/ZAR',
                'ETH/ZAR': 'ETH/ZAR',
                'BTC/USDT': 'BTC/USDT',
                'ETH/USDT': 'ETH/USDT',
                'BNB/USDT': 'BNB/USDT',
                'XRP/USDT': 'XRP/USDT',
            },
            # KuCoin — unified slash format works natively via CCXT
            'kucoin': {
                'BTC/USDT': 'BTC/USDT',
                'ETH/USDT': 'ETH/USDT',
                'XRP/USDT': 'XRP/USDT',
                'BNB/USDT': 'BNB/USDT',
                'SOL/USDT': 'SOL/USDT',
            },
            # Bybit — CCXT accepts slash format; no custom mapping needed
            'bybit': {
                'BTC/USDT': 'BTC/USDT',
                'ETH/USDT': 'ETH/USDT',
                'XRP/USDT': 'XRP/USDT',
                'SOL/USDT': 'SOL/USDT',
            },
            # Kraken uses XBT for Bitcoin in some market IDs
            'kraken': {
                'BTC/USD': 'XBT/USD',
                'BTC/USDT': 'XBT/USDT',
                'ETH/USD': 'ETH/USD',
                'ETH/USDT': 'ETH/USDT',
            },
            # Bitget — CCXT accepts slash format
            'bitget': {
                'BTC/USDT': 'BTC/USDT',
                'ETH/USDT': 'ETH/USDT',
                'XRP/USDT': 'XRP/USDT',
            },
            # Gate.io uses underscore format for some pairs
            'gate': {
                'BTC/USDT': 'BTC_USDT',
                'ETH/USDT': 'ETH_USDT',
                'XRP/USDT': 'XRP_USDT',
                'SOL/USDT': 'SOL_USDT',
            },
            # Coinbase uses hyphen format
            'coinbase': {
                'BTC/USD': 'BTC-USD',
                'ETH/USD': 'ETH-USD',
                'BTC/USDT': 'BTC-USDT',
                'ETH/USDT': 'ETH-USDT',
                'SOL/USDT': 'SOL-USDT',
            },
        }

        static = symbol_map.get(exchange_name, {}).get(symbol)
        if static:
            return static

        # Dynamic CCXT fallback: if we have a live exchange instance, use
        # its market map to resolve the canonical unified symbol.
        try:
            for _user_exchanges in self.active_exchanges.values():
                exchange_instance = _user_exchanges.get(exchange_name)
                if exchange_instance and hasattr(exchange_instance, 'markets') and exchange_instance.markets:
                    if symbol in exchange_instance.markets:
                        return symbol  # already valid
                    # Try common reformats
                    for candidate in (symbol, symbol.replace('/', ''), symbol.replace('/', '-'), symbol.replace('/', '_')):
                        if candidate in exchange_instance.markets:
                            return candidate
                    break
        except Exception:
            pass

        # Default: return symbol unchanged — CCXT handles most slash-format symbols natively
        return symbol
    
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
                                 side: str, amount: float, _internal_only: bool = False) -> Optional[Dict]:
        """
        Place real market order
        
        WARNING: This method should ONLY be called internally after OrderPipeline approval.
        All external order requests must go through services/order_pipeline.py -> submit_order()
        
        Args:
            _internal_only: Must be True to execute. Prevents direct external calls.
        """
        if not _internal_only:
            raise RuntimeError(
                "Direct order placement is not allowed. "
                "All orders must go through OrderPipeline.submit_order() for safety gates."
            )
        
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

    # Maximum number of rate-limit retry attempts before giving up.
    # At attempt 5 the backoff wait is 2^5 + jitter ≈ 33 s, so the total
    # worst-case delay is ~1+2+4+8+16+32 ≈ 63 s before the call returns None.
    _MAX_RATE_LIMIT_ATTEMPTS = 5

    async def _rate_limit_backoff(self, attempt: int) -> None:
        """Exponential backoff with jitter for rate-limit errors.

        Waits 2^attempt seconds (capped at 60) plus up to 1 second of jitter
        to avoid synchronised retries across concurrent bots.
        """
        delay = min(2 ** attempt, 60)
        # Deterministic jitter: use the full microsecond range (0–999999) → 0..0.999999 s
        jitter = datetime.now(timezone.utc).microsecond / 1_000_000.0
        total = delay + jitter
        logger.warning(f"⏳ Rate-limit backoff: sleeping {total:.2f}s (attempt {attempt})")
        await asyncio.sleep(total)

    async def place_limit_order(self, exchange: ccxt.Exchange, symbol: str,
                               side: str, amount: float, price: float) -> Optional[Dict]:
        """Place real limit order"""
        for attempt in range(self._MAX_RATE_LIMIT_ATTEMPTS + 1):
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
            except ccxt.AuthenticationError as e:
                logger.error(
                    f"❌ Authentication error on {exchange.id} — API key may be expired or revoked: {e}"
                )
                return None
            except ccxt.InvalidNonce as e:
                logger.error(
                    f"❌ Invalid nonce on {exchange.id} — check server clock / NTP sync: {e}"
                )
                return None
            except ccxt.ExchangeNotAvailable as e:
                logger.error(
                    f"❌ Exchange {exchange.id} unavailable (outage or maintenance): {e}"
                )
                return None
            except ccxt.RateLimitExceeded as e:
                if attempt >= self._MAX_RATE_LIMIT_ATTEMPTS:
                    logger.error(
                        f"❌ Rate limit exceeded on limit order after {attempt} retries — giving up: {e}"
                    )
                    return None
                logger.warning(f"⏳ Rate limit exceeded on limit order: {e}")
                await self._rate_limit_backoff(attempt=attempt)
            except Exception as e:
                logger.error(f"❌ Order placement failed: {e}")
                return None
        return None

    async def place_market_order(self, exchange: ccxt.Exchange, symbol: str,
                                 side: str, amount: float) -> Optional[Dict]:
        """Place real market order"""
        for attempt in range(self._MAX_RATE_LIMIT_ATTEMPTS + 1):
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
            except ccxt.AuthenticationError as e:
                logger.error(
                    f"❌ Authentication error on {exchange.id} — API key may be expired or revoked: {e}"
                )
                return None
            except ccxt.InvalidNonce as e:
                logger.error(
                    f"❌ Invalid nonce on {exchange.id} — check server clock / NTP sync: {e}"
                )
                return None
            except ccxt.ExchangeNotAvailable as e:
                logger.error(
                    f"❌ Exchange {exchange.id} unavailable (outage or maintenance): {e}"
                )
                return None
            except ccxt.RateLimitExceeded as e:
                if attempt >= self._MAX_RATE_LIMIT_ATTEMPTS:
                    logger.error(
                        f"❌ Rate limit exceeded on market order after {attempt} retries — giving up: {e}"
                    )
                    return None
                logger.warning(f"⏳ Rate limit exceeded on market order: {e}")
                await self._rate_limit_backoff(attempt=attempt)
            except Exception as e:
                logger.error(f"❌ Order placement failed: {e}")
                return None
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
                
                # Use real current price for both entry and exit (instantaneous paper fill)
                # This avoids random drift and gives honest paper P&L based on actual prices
                entry_price = current_price
                exit_price = current_price  # Paper fill at market price — no random slippage
                
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
        """Monitor open live positions — enforces stop-loss, take-profit, and max-hold exits."""
        try:
            import os as _os
            live_max_hold_minutes = int(_os.getenv("LIVE_MAX_HOLD_MINUTES", "120"))

            # Query bots using both canonical trading_mode and legacy mode field
            bots = await db.bots_collection.find(
                {
                    "user_id": user_id,
                    "status": "active",
                    "$or": [{"trading_mode": "live"}, {"mode": "live"}],
                },
                {"_id": 0},
            ).to_list(100)

            for bot in bots:
                open_trades = await db.trades_collection.find(
                    {"bot_id": bot['id'], "status": "open"},
                    {"_id": 0},
                ).sort("timestamp", -1).to_list(20)

                for trade in open_trades:
                    # Resolve exchange instance (may be absent if server restarted)
                    exchange = self.active_exchanges.get(user_id, {}).get(
                        bot.get('exchange', '').lower()
                    )

                    current_price = await self.get_real_price(exchange, trade.get('pair', ''))
                    if not current_price:
                        logger.debug(
                            f"monitor_open_positions: no price for {trade.get('pair')} "
                            f"({bot.get('exchange')}) — skipping"
                        )
                        continue

                    entry_price = float(trade.get('entry_price') or 0)
                    if entry_price <= 0:
                        continue

                    side = trade.get('side', 'buy')
                    stop_loss_pct = float(trade.get('stop_loss_pct') or bot.get('stop_loss_pct', 0.02))
                    take_profit_pct = float(trade.get('take_profit_pct') or bot.get('take_profit_pct', 0.03))

                    stop_loss_price = (
                        entry_price * (1 - stop_loss_pct)
                        if side == 'buy'
                        else entry_price * (1 + stop_loss_pct)
                    )
                    take_profit_price = (
                        entry_price * (1 + take_profit_pct)
                        if side == 'buy'
                        else entry_price * (1 - take_profit_pct)
                    )

                    # Check stop-loss
                    hit_stop = (
                        (side == 'buy' and current_price <= stop_loss_price) or
                        (side == 'sell' and current_price >= stop_loss_price)
                    )
                    if hit_stop:
                        logger.warning(
                            f"🚨 Stop-loss triggered: {bot.get('name')} {trade.get('pair')} "
                            f"price={current_price:.4f} sl={stop_loss_price:.4f}"
                        )
                        await self.close_position(bot, trade, current_price, "stop_loss")
                        continue

                    # Check take-profit
                    hit_tp = (
                        (side == 'buy' and current_price >= take_profit_price) or
                        (side == 'sell' and current_price <= take_profit_price)
                    )
                    if hit_tp:
                        logger.info(
                            f"✅ Take-profit triggered: {bot.get('name')} {trade.get('pair')} "
                            f"price={current_price:.4f} tp={take_profit_price:.4f}"
                        )
                        await self.close_position(bot, trade, current_price, "take_profit")
                        continue

                    # Check time-based max-hold exit
                    if live_max_hold_minutes > 0:
                        try:
                            opened_at_str = trade.get('timestamp') or trade.get('created_at')
                            if opened_at_str:
                                from datetime import datetime, timezone, timedelta
                                opened_at = datetime.fromisoformat(
                                    str(opened_at_str).replace('Z', '+00:00')
                                )
                                hold_minutes = (
                                    datetime.now(timezone.utc) - opened_at
                                ).total_seconds() / 60.0
                                if hold_minutes >= live_max_hold_minutes:
                                    logger.info(
                                        f"⏰ Max-hold exit: {bot.get('name')} {trade.get('pair')} "
                                        f"held {hold_minutes:.0f}m (limit {live_max_hold_minutes}m)"
                                    )
                                    await self.close_position(bot, trade, current_price, "max_hold_exit")
                        except Exception as _te:
                            logger.debug(f"Time-exit calc error: {_te}")

        except Exception as e:
            logger.error(f"monitor_open_positions error: {e}")
    
    async def close_position(self, bot: Dict, trade: Dict, exit_price: float, reason: str):
        """Close a live position and record realised P&L.

        This is the single exit path for all live trades.  It:
        - Marks the trade as closed with exit_price and reason
        - Calculates net P&L (including entry fee already paid)
        - Updates bot capital, total_profit, trades_count, win_count / loss_count
        - Creates an alert
        - Broadcasts a realtime event
        """
        try:
            entry_price = float(trade.get('entry_price') or 0)
            amount = float(trade.get('amount') or trade.get('qty') or 0)
            side = trade.get('side', 'buy')
            fee_paid = float(trade.get('fee_paid') or trade.get('fee_amount') or 0)

            if side == 'buy':
                pnl = (exit_price - entry_price) * amount - fee_paid
            else:
                pnl = (entry_price - exit_price) * amount - fee_paid

            closed_at = datetime.now(timezone.utc).isoformat()

            # --- Update trade record ---
            await db.trades_collection.update_one(
                {"id": trade['id']},
                {"$set": {
                    "status": "closed",
                    "exit_price": exit_price,
                    "exit_reason": reason,
                    "trade_close_reason": reason,
                    "profit_loss": pnl,
                    "net_pnl": pnl,
                    "realized_pnl": pnl,
                    "closed_at": closed_at,
                }}
            )

            # --- Update bot capital and performance stats ---
            new_capital = float(bot.get('current_capital', 0)) + pnl
            win_inc = 1 if pnl > 0 else 0
            loss_inc = 1 if pnl < 0 else 0

            await db.bots_collection.update_one(
                {"id": bot['id']},
                {
                    "$set": {
                        "current_capital": new_capital,
                        "last_trade_time": closed_at,
                    },
                    "$inc": {
                        "total_profit": pnl,
                        "trades_count": 1,
                        "win_count": win_inc,
                        "loss_count": loss_inc,
                    },
                }
            )

            # --- Alert ---
            alert_type = "stop_loss" if reason == "stop_loss" else "take_profit" if reason == "take_profit" else "trade_closed"
            pnl_label = f"+R{pnl:.2f}" if pnl >= 0 else f"-R{abs(pnl):.2f}"
            await db.alerts_collection.insert_one({
                "user_id": bot['user_id'],
                "type": alert_type,
                "severity": "high" if reason == "stop_loss" else "info",
                "message": (
                    f"Live position closed ({reason}): {bot.get('name')} "
                    f"{trade.get('pair')} @ {exit_price:.4f}  P&L {pnl_label}"
                ),
                "timestamp": closed_at,
                "dismissed": False,
                "bot_id": bot['id'],
                "trade_id": trade['id'],
            })

            # --- Realtime broadcast ---
            try:
                from services.realtime_service import realtime_service
                await realtime_service.broadcast_trade_execution(bot['user_id'], {
                    **trade,
                    "status": "closed",
                    "exit_price": exit_price,
                    "profit_loss": pnl,
                    "exit_reason": reason,
                    "closed_at": closed_at,
                })
            except Exception as _rt_err:
                logger.debug(f"Realtime broadcast error on close: {_rt_err}")

            logger.info(
                f"✅ Live position closed ({reason}): {bot.get('name')} "
                f"{trade.get('pair')} P&L={pnl:.4f} capital={new_capital:.2f}"
            )

        except Exception as e:
            logger.error(f"close_position error: {e}")

# Global instance
live_trading_engine = LiveTradingEngine()
