"""
Live Trading Gate - Safety Checks Before Order Placement
Enforces all requirements before allowing live trading
Logs all violations and emits alerts
"""

import logging
import os
from datetime import datetime, timezone
from typing import Dict, List, Tuple
import database as db

logger = logging.getLogger(__name__)
INFINITE_PROFIT_FACTOR = 999.0


class LiveGateService:
    """Validates all requirements before live trading"""
    
    async def can_place_order(
        self,
        user_id: str,
        bot_id: str,
        exchange: str,
        order_type: str = "market"
    ) -> Tuple[bool, List[str]]:
        """Check if order can be placed
        
        Args:
            user_id: User ID
            bot_id: Bot ID
            exchange: Exchange name
            order_type: Order type (market, limit, etc.)
            
        Returns:
            Tuple of (can_place, violations)
        """
        violations = []
        
        try:
            from utils.env_utils import get_trading_flags
            from config import MIN_TRADES_FOR_PROMOTION, MIN_WIN_RATE, MAX_DRAWDOWN_PCT
            flags = get_trading_flags()
            if not flags["enable_trading"]:
                violations.append("ENABLE_TRADING is false")
            if not flags["enable_live_trading"]:
                violations.append("ENABLE_LIVE_TRADING is false")

            # Check 1: System mode must be live
            from services.system_mode_service import system_mode_service
            current_mode = await system_mode_service.get_current_mode(user_id)
            
            if current_mode != 'live':
                violations.append(f"System mode is {current_mode}, not live")
            
            # Check 2: Bot must exist and be active
            bot = await db.bots_collection.find_one(
                {"id": bot_id, "user_id": user_id},
                {"_id": 0}
            )
            
            if not bot:
                violations.append(f"Bot {bot_id} not found")
                # Log violation
                await self._log_violation(user_id, bot_id, "bot_not_found", {
                    "bot_id": bot_id
                })
                return False, violations
            
            if bot.get('status') != 'active':
                violations.append(f"Bot status is {bot.get('status')}, not active")
            
            if bot.get('trading_mode') != 'live':
                violations.append(f"Bot trading_mode is {bot.get('trading_mode')}, not live")
            
            # Check 3: Bot must have validated API keys for exchange
            from services.keys_service import keys_service
            
            api_key_data = await keys_service.get_user_api_key(user_id, exchange)
            
            if not api_key_data:
                violations.append(f"No API key configured for {exchange}")
            elif not api_key_data.get('last_test_ok'):
                violations.append(f"API key for {exchange} not validated")
            
            # Check 4: Training must be complete OR admin override
            training_complete = bot.get('training_complete', False)
            admin_override = bot.get('admin_live_override', False)
            
            if not training_complete and not admin_override:
                violations.append("Bot training not complete and no admin override")

            if admin_override:
                logger.warning(f"LiveGate: Admin override active for bot {bot_id}")

            # Check 4.1: Paper performance gates
            paper_closed = await db.trades_collection.find({
                "bot_id": bot_id,
                "is_paper": True,
                "status": "closed",
            }, {"_id": 0, "profit_loss": 1}).to_list(5000)
            wins = sum(1 for t in paper_closed if (t.get("profit_loss", 0) or 0) > 0)
            losses = sum(1 for t in paper_closed if (t.get("profit_loss", 0) or 0) < 0)
            total = len(paper_closed)
            if total < MIN_TRADES_FOR_PROMOTION:
                violations.append(f"Insufficient paper trades: {total} < {MIN_TRADES_FOR_PROMOTION}")
            win_rate = (wins / total) if total > 0 else 0.0
            if win_rate < MIN_WIN_RATE:
                violations.append(f"Win rate too low: {win_rate:.2%} < {MIN_WIN_RATE:.2%}")
            gross_profit = sum((t.get("profit_loss", 0) or 0) for t in paper_closed if (t.get("profit_loss", 0) or 0) > 0)
            gross_loss = abs(sum((t.get("profit_loss", 0) or 0) for t in paper_closed if (t.get("profit_loss", 0) or 0) < 0))
            profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else (INFINITE_PROFIT_FACTOR if gross_profit > 0 else 0.0)
            if profit_factor <= 1.2:
                violations.append(f"Profit factor too low: {profit_factor:.2f} <= 1.2")
            expectancy = (
                sum((t.get("profit_loss", 0) or 0) for t in paper_closed) / total
                if total > 0 else 0.0
            )
            if expectancy <= 0:
                violations.append(f"Expectancy not positive: {expectancy:.4f}")
            if float(bot.get("max_drawdown", 0.0) or 0.0) > MAX_DRAWDOWN_PCT:
                violations.append(
                    f"Max drawdown too high: {float(bot.get('max_drawdown', 0.0) or 0.0):.2%} > {MAX_DRAWDOWN_PCT:.2%}"
                )

            # Check 5: Bodyguard state must be OK
            from services.bodyguard_service import bodyguard_service
            
            drawdown_status = await bodyguard_service.get_bot_drawdown_status(bot_id)
            
            if drawdown_status and drawdown_status.get('paused_by_bodyguard'):
                violations.append(f"Bot paused by bodyguard: {drawdown_status.get('pause_reason')}")
            
            # Check 6: Emergency stop must not be active
            emergency = await db.emergency_stop_collection.find_one({}) if db.emergency_stop_collection is not None else None
            
            if emergency and emergency.get('enabled'):
                violations.append(f"Emergency stop active: {emergency.get('reason')}")

            # Check 6.1: Macro simulated signal must not influence live mode by default
            macro_weight = float(os.getenv("MACRO_SIGNAL_WEIGHT", "0.0") or 0.0)
            if macro_weight > 0:
                violations.append("MACRO_SIGNAL_WEIGHT must be 0.0 for live unless real provider is validated")
            
            # Check 7: Exchange must be valid
            from config.platforms import is_valid_platform, get_platform_config
            
            if not is_valid_platform(exchange):
                violations.append(f"Invalid exchange: {exchange}")
            else:
                platform_config = get_platform_config(exchange)
                if not platform_config.get('supports_live'):
                    violations.append(f"Exchange {exchange} does not support live trading")

            # Check 8: Signal engine must be healthy for the bot pair before live order placement
            try:
                from services.signal_engine import SignalEngine
                signal_engine = SignalEngine(db.db if hasattr(db, "db") else db)
                signal = await signal_engine.get_signal(
                    user_id=user_id,
                    bot_id=bot_id,
                    exchange=exchange,
                    symbol=bot.get("pair", "BTC/USDT"),
                    side="buy",
                    amount=1.0,
                    price=None,
                )
                if getattr(signal, "signal_status", "ok") != "ok":
                    violations.append(f"Signal engine unhealthy: {getattr(signal, 'signal_status', 'unknown')}")
            except Exception as e:
                violations.append(f"Signal engine check failed: {e}")
            
            # Log if violations found
            if violations:
                await self._log_violation(user_id, bot_id, "live_gate_failed", {
                    "violations": violations,
                    "exchange": exchange,
                    "order_type": order_type
                })
                
                # Emit alert
                await self._emit_alert(user_id, violations)
            
            return len(violations) == 0, violations
            
        except Exception as e:
            logger.error(f"LiveGate check error: {e}", exc_info=True)
            violations.append(f"LiveGate check error: {str(e)}")
            return False, violations
    
    async def _log_violation(
        self,
        user_id: str,
        bot_id: str,
        violation_type: str,
        details: Dict
    ):
        """Log LiveGate violation
        
        Args:
            user_id: User ID
            bot_id: Bot ID
            violation_type: Type of violation
            details: Additional details
        """
        try:
            await db.alerts_collection.insert_one({
                "user_id": user_id,
                "bot_id": bot_id,
                "type": "live_gate_violation",
                "violation_type": violation_type,
                "details": details,
                "severity": "high",
                "created_at": datetime.now(timezone.utc).isoformat(),
                "acknowledged": False
            })
            
            logger.warning(
                f"LiveGate violation for user {user_id[:8]}, bot {bot_id}: "
                f"{violation_type} - {details}"
            )
            
        except Exception as e:
            logger.error(f"Log violation error: {e}")
    
    async def _emit_alert(self, user_id: str, violations: List[str]):
        """Emit realtime alert for violations
        
        Args:
            user_id: User ID
            violations: List of violation messages
        """
        try:
            from services.realtime_service import realtime_service
            
            await realtime_service.broadcast_alert(
                user_id,
                "error",
                f"Live trading blocked: {'; '.join(violations[:3])}",
                {
                    "violations": violations,
                    "type": "live_gate_violation"
                }
            )
            
        except Exception as e:
            logger.error(f"Emit alert error: {e}")
    
    async def emergency_stop_all(
        self,
        reason: str,
        activated_by: str
    ) -> Dict:
        """Activate emergency stop - halt all live trading
        
        Args:
            reason: Reason for emergency stop
            activated_by: User ID who activated
            
        Returns:
            Status dict with affected bots count
        """
        try:
            timestamp = datetime.now(timezone.utc).isoformat()
            
            # Set emergency stop flag
            await db.emergency_stop_collection.update_one(
                {},
                {
                    "$set": {
                        "enabled": True,
                        "reason": reason,
                        "activated_at": timestamp,
                        "activated_by": activated_by
                    }
                },
                upsert=True
            )
            
            # Pause all active live bots
            result = await db.bots_collection.update_many(
                {
                    "trading_mode": "live",
                    "status": "active"
                },
                {
                    "$set": {
                        "status": "paused",
                        "paused_at": timestamp,
                        "pause_reason": f"Emergency stop: {reason}",
                        "paused_by_system": True,
                        "emergency_stop": True
                    }
                }
            )
            
            affected_count = result.modified_count
            
            logger.critical(
                f"🚨 EMERGENCY STOP activated by {activated_by[:8]}: "
                f"{reason} ({affected_count} bots paused)"
            )
            
            # Broadcast to all users
            from websocket_manager_redis import manager
            await manager.broadcast_all({
                "type": "emergency_stop",
                "severity": "critical",
                "reason": reason,
                "affected_bots": affected_count,
                "timestamp": timestamp
            })
            
            return {
                "success": True,
                "affected_bots": affected_count,
                "reason": reason,
                "timestamp": timestamp
            }
            
        except Exception as e:
            logger.error(f"Emergency stop error: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
    async def deactivate_emergency_stop(
        self,
        deactivated_by: str
    ) -> Dict:
        """Deactivate emergency stop
        
        Args:
            deactivated_by: User ID who deactivated
            
        Returns:
            Status dict
        """
        try:
            timestamp = datetime.now(timezone.utc).isoformat()
            
            await db.emergency_stop_collection.update_one(
                {},
                {
                    "$set": {
                        "enabled": False,
                        "deactivated_at": timestamp,
                        "deactivated_by": deactivated_by
                    }
                }
            )
            
            logger.warning(f"Emergency stop deactivated by {deactivated_by[:8]}")
            
            # Broadcast to all users
            from websocket_manager_redis import manager
            await manager.broadcast_all({
                "type": "emergency_stop_deactivated",
                "severity": "warning",
                "timestamp": timestamp
            })
            
            return {
                "success": True,
                "timestamp": timestamp
            }
            
        except Exception as e:
            logger.error(f"Deactivate emergency stop error: {e}")
            return {
                "success": False,
                "error": str(e)
            }


# Global singleton
live_gate_service = LiveGateService()
