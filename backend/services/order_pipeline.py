"""
Order Pipeline Service - 4-Gate Execution Guardrails

This service implements a unified order submission pipeline that ALL orders
(paper trading, live trading, manual, automated) must pass through.

The 4 gates ensure:
1. Idempotency - No duplicate executions
2. Fee Coverage - Only profitable trades
3. Trade Limits - Respect bot/user/exchange limits
4. Circuit Breaker - Auto-pause on capital protection triggers

All order outcomes are recorded to the immutable ledger.
"""

import asyncio
import uuid
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from collections import defaultdict
import logging

logger = logging.getLogger(__name__)


class OrderPipeline:
    """
    Unified order submission pipeline with 4 safety gates.
    
    ALL trade executions must go through submit_order() method.
    """
    
    def __init__(self, db, ledger_service, config: Optional[Dict] = None):
        self.db = db
        self.ledger = ledger_service
        self.config = config or {}
        
        # Collections
        self.pending_orders = db["pending_orders"]
        self.circuit_breaker_state = db["circuit_breaker_state"]
        
        # Configuration with safe defaults
        self.max_trades_per_bot_daily = int(self.config.get("MAX_TRADES_PER_BOT_DAILY", 50))
        self.max_trades_per_user_daily = int(self.config.get("MAX_TRADES_PER_USER_DAILY", 500))
        self.burst_limit_orders = int(self.config.get("BURST_LIMIT_ORDERS_PER_EXCHANGE", 10))
        self.burst_limit_window_seconds = int(self.config.get("BURST_LIMIT_WINDOW_SECONDS", 10))
        
        # Circuit breaker thresholds
        self.max_drawdown_percent = float(self.config.get("MAX_DRAWDOWN_PERCENT", 0.20))
        self.max_daily_loss_percent = float(self.config.get("MAX_DAILY_LOSS_PERCENT", 0.10))
        self.max_consecutive_losses = int(self.config.get("MAX_CONSECUTIVE_LOSSES", 5))
        self.max_errors_per_hour = int(self.config.get("MAX_ERRORS_PER_HOUR", 10))
        
        # Fee coverage
        self.min_edge_bps = float(self.config.get("MIN_EDGE_BPS", 10.0))
        self.safety_margin_bps = float(self.config.get("SAFETY_MARGIN_BPS", 5.0))
        self.slippage_buffer_bps = float(self.config.get("SLIPPAGE_BUFFER_BPS", 10.0))
        
        # Exchange fee rates (basis points)
        self.exchange_fees = {
            "binance": {"maker": 7.5, "taker": 10.0},
            "luno": {"maker": 20.0, "taker": 25.0},
            "kucoin": {"maker": 10.0, "taker": 10.0},
            "bybit": {"maker": 10.0, "taker": 10.0},
            "kraken": {"maker": 16.0, "taker": 26.0},
            "bitget": {"maker": 10.0, "taker": 10.0},
            "gate": {"maker": 15.0, "taker": 20.0},
        }
        
        # Spread estimates (basis points)
        self.spread_estimates = {
            "BTC/USDT": 5.0,
            "ETH/USDT": 5.0,
            "BTC/ZAR": 20.0,
            "ETH/ZAR": 20.0,
            "default": 10.0
        }
        
        # In-memory counters for burst protection (would use Redis in production)
        self.burst_counters = defaultdict(list)
        
        # Ensure indexes
        asyncio.create_task(self._ensure_indexes())
    
    async def _ensure_indexes(self):
        """Create MongoDB indexes for performance"""
        try:
            await self.pending_orders.create_index(
                [("idempotency_key", 1)],
                unique=True,
                sparse=True
            )
            await self.pending_orders.create_index(
                [("user_id", 1), ("state", 1), ("created_at", -1)]
            )
            await self.pending_orders.create_index(
                [("expires_at", 1)],
                expireAfterSeconds=0  # TTL index
            )
            await self.circuit_breaker_state.create_index(
                [("entity_type", 1), ("entity_id", 1), ("tripped", 1)]
            )
            logger.info("Order pipeline indexes created")
        except Exception as e:
            logger.error(f"Error creating indexes: {e}")
    
    async def submit_order(
        self,
        user_id: str,
        bot_id: str,
        exchange: str,
        symbol: str,
        side: str,
        amount: float,
        order_type: str,
        price: Optional[float] = None,
        idempotency_key: Optional[str] = None,
        is_paper: bool = True
    ) -> Dict[str, Any]:
        """
        Submit order through 4-gate pipeline.
        
        Args:
            user_id: User identifier
            bot_id: Bot identifier
            exchange: Exchange name (binance, luno, etc)
            symbol: Trading pair (BTC/USDT, etc)
            side: buy or sell
            amount: Order amount
            order_type: market or limit
            price: Limit price (optional for market orders)
            idempotency_key: Unique key for idempotency (auto-generated if not provided)
            is_paper: True for paper trading, False for live
        
        Returns:
            {
                "success": bool,
                "order_id": str (if success),
                "idempotency_key": str,
                "gates_passed": List[str],
                "gate_failed": str (if rejected),
                "rejection_reason": str (if rejected),
                "execution_summary": dict
            }
        """
        # Generate idempotency key if not provided
        if not idempotency_key:
            idempotency_key = str(uuid.uuid4())
        
        # Initialize result
        result = {
            "success": False,
            "idempotency_key": idempotency_key,
            "gates_passed": [],
            "gate_failed": None,
            "rejection_reason": None,
            "execution_summary": {}
        }
        
        try:
            # GATE A: Idempotency Check
            gate_result = await self._gate_a_idempotency(
                idempotency_key, user_id, bot_id, exchange, symbol, side, amount, order_type, price
            )
            if not gate_result["passed"]:
                result["gate_failed"] = "idempotency"
                result["rejection_reason"] = gate_result["reason"]
                return result
            result["gates_passed"].append("idempotency")
            
            # If this is a duplicate, return cached result
            if gate_result.get("cached_result"):
                return gate_result["cached_result"]
            
            # GATE B: Fee Coverage Check
            gate_result = await self._gate_b_fee_coverage(
                exchange, symbol, side, amount, order_type, price
            )
            if not gate_result["passed"]:
                result["gate_failed"] = "fee_coverage"
                result["rejection_reason"] = gate_result["reason"]
                result["execution_summary"] = gate_result.get("details", {})
                await self._record_rejection(idempotency_key, result)
                return result
            result["gates_passed"].append("fee_coverage")
            result["execution_summary"] = gate_result.get("details", {})
            
            # GATE C: Trade Limiter Check
            gate_result = await self._gate_c_trade_limiter(
                user_id, bot_id, exchange
            )
            if not gate_result["passed"]:
                result["gate_failed"] = "trade_limiter"
                result["rejection_reason"] = gate_result["reason"]
                await self._record_rejection(idempotency_key, result)
                return result
            result["gates_passed"].append("trade_limiter")
            
            # GATE D: Circuit Breaker Check
            gate_result = await self._gate_d_circuit_breaker(
                user_id, bot_id
            )
            if not gate_result["passed"]:
                result["gate_failed"] = "circuit_breaker"
                result["rejection_reason"] = gate_result["reason"]
                await self._record_rejection(idempotency_key, result)
                return result
            result["gates_passed"].append("circuit_breaker")
            
            # All gates passed - mark order as approved for execution
            order_id = f"order_{uuid.uuid4().hex[:12]}"
            result["success"] = True
            result["order_id"] = order_id
            
            # Record pending order
            await self._record_pending_order(
                idempotency_key, user_id, bot_id, exchange, symbol,
                side, amount, order_type, price, order_id, result
            )
            
            # Increment counters
            await self._increment_trade_counters(user_id, bot_id, exchange)
            
            logger.info(f"Order {order_id} passed all 4 gates for bot {bot_id}")
            return result
            
        except Exception as e:
            logger.error(f"Error in order pipeline: {e}")
            result["gate_failed"] = "internal_error"
            result["rejection_reason"] = f"Internal error: {str(e)}"
            return result
    
    async def _gate_a_idempotency(
        self, idempotency_key: str, user_id: str, bot_id: str,
        exchange: str, symbol: str, side: str, amount: float,
        order_type: str, price: Optional[float]
    ) -> Dict[str, Any]:
        """Gate A: Idempotency - prevent duplicate executions"""
        try:
            # Check if this idempotency key exists
            existing = await self.pending_orders.find_one({
                "idempotency_key": idempotency_key
            })
            
            if existing:
                # Duplicate request - return cached result
                state = existing.get("state")
                if state == "filled":
                    return {
                        "passed": True,
                        "cached_result": {
                            "success": True,
                            "order_id": existing.get("order_id"),
                            "idempotency_key": idempotency_key,
                            "gates_passed": existing.get("gates_passed", []),
                            "execution_summary": existing.get("execution_summary", {}),
                            "cached": True
                        }
                    }
                elif state in ["rejected", "expired"]:
                    return {
                        "passed": False,
                        "reason": f"Duplicate request - original order was {state}: {existing.get('rejection_reason', 'N/A')}"
                    }
                elif state == "pending":
                    return {
                        "passed": False,
                        "reason": "Duplicate request - order is still pending execution"
                    }
            
            # New order - idempotency check passed
            return {"passed": True}
            
        except Exception as e:
            logger.error(f"Error in idempotency gate: {e}")
            return {"passed": False, "reason": f"Idempotency check failed: {str(e)}"}
    
    async def _gate_b_fee_coverage(
        self, exchange: str, symbol: str, side: str,
        amount: float, order_type: str, price: Optional[float]
    ) -> Dict[str, Any]:
        """Gate B: Fee Coverage - ensure trade is profitable after fees"""
        try:
            # Get fee rates for exchange
            fees = self.exchange_fees.get(exchange.lower(), {"maker": 15.0, "taker": 15.0})
            fee_bps = fees["maker"] if order_type == "limit" else fees["taker"]
            
            # Get spread estimate
            spread_bps = self.spread_estimates.get(symbol, self.spread_estimates["default"])
            
            # Slippage buffer (for market orders)
            slippage_bps = self.slippage_buffer_bps if order_type == "market" else 0.0
            
            # Total cost
            total_cost_bps = fee_bps + spread_bps + slippage_bps + self.safety_margin_bps
            
            # For now, assume a minimum edge requirement
            # In production, this would be calculated from strategy signals
            expected_edge_bps = self.min_edge_bps
            
            # Check if edge covers costs
            profit_margin_bps = expected_edge_bps - total_cost_bps
            
            details = {
                "expected_edge_bps": expected_edge_bps,
                "fee_bps": fee_bps,
                "spread_bps": spread_bps,
                "slippage_bps": slippage_bps,
                "safety_margin_bps": self.safety_margin_bps,
                "total_cost_bps": total_cost_bps,
                "profit_margin_bps": profit_margin_bps
            }
            
            if profit_margin_bps < 0:
                return {
                    "passed": False,
                    "reason": f"Insufficient edge: {expected_edge_bps:.1f} bps expected vs {total_cost_bps:.1f} bps costs (margin: {profit_margin_bps:.1f} bps)",
                    "details": details
                }
            
            return {"passed": True, "details": details}
            
        except Exception as e:
            logger.error(f"Error in fee coverage gate: {e}")
            return {"passed": False, "reason": f"Fee coverage check failed: {str(e)}"}
    
    async def _gate_c_trade_limiter(
        self, user_id: str, bot_id: str, exchange: str
    ) -> Dict[str, Any]:
        """Gate C: Trade Limiter - enforce bot/user/exchange limits"""
        try:
            today = datetime.utcnow().date()
            
            # Check bot daily limit
            bot_count = await self.ledger.get_trade_count(
                bot_id=bot_id,
                since=datetime.combine(today, datetime.min.time())
            )
            if bot_count >= self.max_trades_per_bot_daily:
                return {
                    "passed": False,
                    "reason": f"Bot daily limit reached: {bot_count}/{self.max_trades_per_bot_daily} trades"
                }
            
            # Check user daily limit
            user_count = await self.ledger.get_trade_count(
                user_id=user_id,
                since=datetime.combine(today, datetime.min.time())
            )
            if user_count >= self.max_trades_per_user_daily:
                return {
                    "passed": False,
                    "reason": f"User daily limit reached: {user_count}/{self.max_trades_per_user_daily} trades"
                }
            
            # Check burst limit (rolling window)
            burst_key = f"{exchange}:{user_id}"
            now = datetime.utcnow()
            window_start = now - timedelta(seconds=self.burst_limit_window_seconds)
            
            # Clean old timestamps
            self.burst_counters[burst_key] = [
                ts for ts in self.burst_counters[burst_key]
                if ts > window_start
            ]
            
            if len(self.burst_counters[burst_key]) >= self.burst_limit_orders:
                return {
                    "passed": False,
                    "reason": f"Burst limit reached: {len(self.burst_counters[burst_key])}/{self.burst_limit_orders} orders in {self.burst_limit_window_seconds}s"
                }
            
            return {"passed": True}
            
        except Exception as e:
            logger.error(f"Error in trade limiter gate: {e}")
            return {"passed": False, "reason": f"Trade limiter check failed: {str(e)}"}
    
    async def _gate_d_circuit_breaker(
        self, user_id: str, bot_id: str
    ) -> Dict[str, Any]:
        """Gate D: Circuit Breaker - check if bot/user is tripped"""
        try:
            # Check if bot circuit breaker is tripped
            bot_breaker = await self.circuit_breaker_state.find_one({
                "entity_type": "bot",
                "entity_id": bot_id,
                "tripped": True,
                "reset_at": None
            })
            
            if bot_breaker:
                return {
                    "passed": False,
                    "reason": f"Bot circuit breaker tripped: {bot_breaker.get('trigger_reason', 'Unknown')}"
                }
            
            # Check if user circuit breaker is tripped
            user_breaker = await self.circuit_breaker_state.find_one({
                "entity_type": "user",
                "entity_id": user_id,
                "tripped": True,
                "reset_at": None
            })
            
            if user_breaker:
                return {
                    "passed": False,
                    "reason": f"User circuit breaker tripped: {user_breaker.get('trigger_reason', 'Unknown')}"
                }
            
            # Check if we should trip the circuit breaker now
            should_trip, reason = await self._should_trip_circuit_breaker(user_id, bot_id)
            if should_trip:
                await self._trip_circuit_breaker(bot_id, "bot", reason)
                return {
                    "passed": False,
                    "reason": f"Circuit breaker triggered: {reason}"
                }
            
            return {"passed": True}
            
        except Exception as e:
            logger.error(f"Error in circuit breaker gate: {e}")
            return {"passed": False, "reason": f"Circuit breaker check failed: {str(e)}"}
    
    async def _should_trip_circuit_breaker(
        self, user_id: str, bot_id: str
    ) -> tuple[bool, Optional[str]]:
        """Check if circuit breaker should trip"""
        try:
            # Check drawdown
            current_dd, max_dd = await self.ledger.compute_drawdown(bot_id=bot_id)
            if current_dd > self.max_drawdown_percent:
                return True, f"Drawdown exceeded {self.max_drawdown_percent*100:.0f}% (current: {current_dd*100:.1f}%)"
            
            # Check daily loss
            daily_pnl = await self.ledger.compute_daily_pnl(bot_id=bot_id)
            equity = await self.ledger.compute_equity(bot_id=bot_id)
            if equity > 0 and daily_pnl < 0:
                daily_loss_pct = abs(daily_pnl) / equity
                if daily_loss_pct > self.max_daily_loss_percent:
                    return True, f"Daily loss exceeded {self.max_daily_loss_percent*100:.0f}% (current: {daily_loss_pct*100:.1f}%)"
            
            # Check consecutive losses
            consecutive = await self.ledger.get_consecutive_losses(bot_id=bot_id)
            if consecutive >= self.max_consecutive_losses:
                return True, f"{consecutive} consecutive losses (max: {self.max_consecutive_losses})"
            
            # Check error rate
            error_count = await self.ledger.get_error_rate(bot_id=bot_id, hours=1)
            if error_count >= self.max_errors_per_hour:
                return True, f"{error_count} errors in last hour (max: {self.max_errors_per_hour})"
            
            return False, None
            
        except Exception as e:
            logger.error(f"Error checking circuit breaker triggers: {e}")
            return False, None
    
    async def _trip_circuit_breaker(
        self, entity_id: str, entity_type: str, reason: str
    ):
        """Trip the circuit breaker"""
        try:
            await self.circuit_breaker_state.insert_one({
                "entity_type": entity_type,
                "entity_id": entity_id,
                "tripped": True,
                "trigger_reason": reason,
                "trigger_type": self._classify_trigger(reason),
                "tripped_at": datetime.utcnow(),
                "reset_at": None,
                "reset_by_user_id": None,
                "reset_reason": None,
                "metrics_at_trip": {}
            })
            
            # Record event to ledger
            await self.ledger.append_event(
                user_id=None,  # Will be filled from entity lookup
                bot_id=entity_id if entity_type == "bot" else None,
                event_type="circuit_breaker",
                amount=0,
                currency="",
                description=f"Circuit breaker tripped: {reason}",
                metadata={"trigger_reason": reason}
            )
            
            logger.warning(f"Circuit breaker tripped for {entity_type} {entity_id}: {reason}")
            
        except Exception as e:
            logger.error(f"Error tripping circuit breaker: {e}")
    
    def _classify_trigger(self, reason: str) -> str:
        """Classify trigger type from reason string"""
        reason_lower = reason.lower()
        if "drawdown" in reason_lower:
            return "drawdown"
        elif "daily loss" in reason_lower:
            return "daily_loss"
        elif "consecutive" in reason_lower:
            return "consecutive_losses"
        elif "error" in reason_lower:
            return "error_storm"
        return "unknown"
    
    async def _record_pending_order(
        self, idempotency_key: str, user_id: str, bot_id: str,
        exchange: str, symbol: str, side: str, amount: float,
        order_type: str, price: Optional[float], order_id: str,
        result: Dict[str, Any]
    ):
        """Record pending order"""
        try:
            await self.pending_orders.insert_one({
                "idempotency_key": idempotency_key,
                "user_id": user_id,
                "bot_id": bot_id,
                "exchange": exchange,
                "symbol": symbol,
                "side": side,
                "amount": amount,
                "order_type": order_type,
                "price": price,
                "order_id": order_id,
                "state": "pending",
                "gates_passed": result["gates_passed"],
                "gate_failed": None,
                "rejection_reason": None,
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow(),
                "expires_at": datetime.utcnow() + timedelta(hours=24),
                "filled_at": None,
                "fill_id": None,
                "execution_summary": result["execution_summary"]
            })
        except Exception as e:
            logger.error(f"Error recording pending order: {e}")
    
    async def _record_rejection(
        self, idempotency_key: str, result: Dict[str, Any]
    ):
        """Record rejected order"""
        try:
            await self.pending_orders.update_one(
                {"idempotency_key": idempotency_key},
                {
                    "$set": {
                        "state": "rejected",
                        "gate_failed": result["gate_failed"],
                        "rejection_reason": result["rejection_reason"],
                        "updated_at": datetime.utcnow()
                    }
                },
                upsert=True
            )
        except Exception as e:
            logger.error(f"Error recording rejection: {e}")
    
    async def _increment_trade_counters(
        self, user_id: str, bot_id: str, exchange: str
    ):
        """Increment trade counters"""
        try:
            # Add timestamp to burst counter
            burst_key = f"{exchange}:{user_id}"
            self.burst_counters[burst_key].append(datetime.utcnow())
            
        except Exception as e:
            logger.error(f"Error incrementing counters: {e}")
    
    async def get_pending_orders(
        self, user_id: Optional[str] = None, bot_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Get pending orders"""
        try:
            query = {"state": "pending"}
            if user_id:
                query["user_id"] = user_id
            if bot_id:
                query["bot_id"] = bot_id
            
            cursor = self.pending_orders.find(query).sort("created_at", -1)
            orders = await cursor.to_list(length=100)
            
            # Convert ObjectId to string
            for order in orders:
                order["_id"] = str(order["_id"])
            
            return orders
        except Exception as e:
            logger.error(f"Error getting pending orders: {e}")
            return []
    
    async def reset_circuit_breaker(
        self, entity_id: str, entity_type: str,
        reset_by_user_id: str, reason: str
    ) -> Dict[str, Any]:
        """Reset circuit breaker after manual review"""
        try:
            result = await self.circuit_breaker_state.update_one(
                {
                    "entity_type": entity_type,
                    "entity_id": entity_id,
                    "tripped": True,
                    "reset_at": None
                },
                {
                    "$set": {
                        "tripped": False,
                        "reset_at": datetime.utcnow(),
                        "reset_by_user_id": reset_by_user_id,
                        "reset_reason": reason
                    }
                }
            )
            
            if result.modified_count > 0:
                logger.info(f"Circuit breaker reset for {entity_type} {entity_id} by {reset_by_user_id}")
                return {"success": True, "message": "Circuit breaker reset successfully"}
            else:
                return {"success": False, "message": "No tripped circuit breaker found"}
                
        except Exception as e:
            logger.error(f"Error resetting circuit breaker: {e}")
            return {"success": False, "message": f"Error: {str(e)}"}
    
    async def get_order_status(
        self, order_id: str, user_id: str
    ) -> Optional[Dict[str, Any]]:
        """Get the status of a submitted order"""
        try:
            order = await self.pending_orders.find_one({
                "order_id": order_id,
                "user_id": user_id
            })
            return order
        except Exception as e:
            logger.error(f"Error getting order status: {e}")
            return None
    
    async def record_fill_execution(
        self,
        order_id: str,
        filled_price: float,
        filled_qty: float,
        actual_fee: float,
        fee_currency: str,
        exchange_trade_id: Optional[str] = None,
        timestamp: Optional[datetime] = None
    ) -> Dict[str, Any]:
        """
        Record actual fill execution with real slippage and fees.
        
        This should be called after order execution to record actual execution details.
        
        Args:
            order_id: Order ID from submit_order
            filled_price: Actual fill price received
            filled_qty: Actual quantity filled
            actual_fee: Actual fee charged by exchange
            fee_currency: Currency of fee (e.g., 'ZAR', 'BTC')
            exchange_trade_id: Exchange's trade ID
            timestamp: Fill timestamp (defaults to now)
        
        Returns:
            {
                "success": bool,
                "fill_id": str,
                "slippage_bps": float,  # Actual slippage compared to expected
                "total_cost_bps": float  # Actual total cost
            }
        """
        try:
            # Get pending order
            order = await self.pending_orders.find_one({"order_id": order_id})
            if not order:
                return {"success": False, "error": "Order not found"}
            
            # Calculate actual slippage
            expected_price = order.get("price") or filled_price
            slippage_bps = abs((filled_price - expected_price) / expected_price * 10000) if abs(expected_price) > 0 else 0
            
            # Calculate actual fee in basis points
            notional_value = filled_price * filled_qty
            actual_fee_bps = (actual_fee / notional_value * 10000) if notional_value > 0 else 0
            
            # Get expected costs from execution summary
            execution_summary = order.get("execution_summary", {})
            expected_fee_bps = execution_summary.get("fee_bps", 0)
            expected_slippage_bps = execution_summary.get("slippage_bps", 0)
            
            # Record fill to ledger with metadata
            metadata = {
                "expected_price": expected_price,
                "filled_price": filled_price,
                "expected_fee_bps": expected_fee_bps,
                "actual_fee_bps": actual_fee_bps,
                "expected_slippage_bps": expected_slippage_bps,
                "actual_slippage_bps": slippage_bps,
                "execution_summary": execution_summary,
                "order_type": order.get("order_type"),
                "gates_passed": order.get("gates_passed", [])
            }
            
            fill_id = await self.ledger.append_fill(
                user_id=order["user_id"],
                bot_id=order["bot_id"],
                exchange=order["exchange"],
                symbol=order["symbol"],
                side=order["side"],
                qty=filled_qty,
                price=filled_price,
                fee=actual_fee,
                fee_currency=fee_currency,
                timestamp=timestamp or datetime.utcnow(),
                order_id=order_id,
                client_order_id=order.get("idempotency_key"),
                exchange_trade_id=exchange_trade_id,
                is_paper=order.get("is_paper", True),
                metadata=metadata
            )
            
            # Update order status
            await self.pending_orders.update_one(
                {"order_id": order_id},
                {
                    "$set": {
                        "state": "filled",
                        "filled_at": timestamp or datetime.utcnow(),
                        "fill_id": fill_id,
                        "filled_price": filled_price,
                        "filled_qty": filled_qty,
                        "actual_fee": actual_fee,
                        "actual_slippage_bps": slippage_bps,
                        "actual_fee_bps": actual_fee_bps,
                        "updated_at": datetime.utcnow()
                    }
                }
            )
            
            logger.info(
                f"Recorded fill {fill_id} for order {order_id}: "
                f"slippage={slippage_bps:.2f}bps, fee={actual_fee_bps:.2f}bps"
            )
            
            return {
                "success": True,
                "fill_id": fill_id,
                "slippage_bps": slippage_bps,
                "actual_fee_bps": actual_fee_bps,
                "total_cost_bps": slippage_bps + actual_fee_bps
            }
            
        except Exception as e:
            logger.error(f"Error recording fill execution: {e}")
            return {"success": False, "error": str(e)}


# Singleton instance
_order_pipeline_instance = None

def get_order_pipeline(db, ledger_service=None, config=None):
    """Get or create order pipeline singleton"""
    global _order_pipeline_instance
    if _order_pipeline_instance is None:
        if ledger_service is None:
            from services.ledger_service import get_ledger_service
            ledger_service = get_ledger_service(db)
        _order_pipeline_instance = OrderPipeline(db, ledger_service, config)
    return _order_pipeline_instance
