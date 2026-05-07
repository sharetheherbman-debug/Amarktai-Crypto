"""
Trading Scheduler - CONTINUOUS STAGGERED TRADING
Uses trade_staggerer for 24/7 distributed execution
Actually uses live_trading_engine for live bots
Enforces trading mode gates (paper OR live required)
"""

import asyncio
import logging
from datetime import datetime, timezone
from paper_trading_engine import paper_engine
from engines.trading_engine_live import live_trading_engine
from engines.trade_staggerer import trade_staggerer
import database as db
from websocket_manager import manager
from realtime_events import rt_events
from config import PAPER_SUPPORTED_EXCHANGES
from services.bot_quarantine import quarantine_service
from services.system_gate import system_gate
from services.trading_mode_validator import trading_mode_validator
from services.live_gate_service import live_gate_service
from utils.trading_gates import TradingGateError, enforce_live_trading_gates
from utils.trading_mode import resolve_bot_trading_mode
from services.bot_runtime_state import bot_runtime_state
from services.bot_filters import bot_not_deleted_filter

logger = logging.getLogger(__name__)

# Bot pause reason codes
class BotPauseReason:
    """Standardized bot pause reason codes"""
    MODE_DISABLED = "MODE_DISABLED"  # Autopilot mode disabled
    NO_EXCHANGE_KEYS = "NO_EXCHANGE_KEYS"  # No API keys configured for exchange
    RISK_STOP = "RISK_STOP"  # Risk engine stopped bot
    EMERGENCY_STOP = "EMERGENCY_STOP"  # Emergency stop activated
    BUDGET_EXHAUSTED = "BUDGET_EXHAUSTED"  # Trading budget exhausted
    USER_PAUSED = "USER_PAUSED"  # Manually paused by user
    UNSUPPORTED_EXCHANGE = "UNSUPPORTED_EXCHANGE"  # Exchange not supported for paper trading


def _is_paper_bot(bot: dict) -> bool:
    """Return True when bot mode resolves to paper."""
    return resolve_bot_trading_mode(bot).startswith('paper')

class TradingScheduler:
    """CONTINUOUS STAGGERED TRADING - Uses trade_staggerer for 24/7 execution"""
    
    def __init__(self):
        self.is_running = False
        self.task = None
        self.check_interval = 10  # Check every 10 seconds for ready trades
        self.last_heartbeat = None
        self.heartbeat_interval = 10  # Emit heartbeat every 10 seconds
        self.last_tick = None  # Track last execution time
        self.next_tick = None  # Track next scheduled execution
        self.tick_count = 0    # Count total ticks
        
    async def execute_bot_trades(self):
        """Execute trades using staggered queue - CONTINUOUS OPERATION"""
        try:
            # Update tick tracking
            from datetime import datetime, timezone, timedelta
            self.last_tick = datetime.now(timezone.utc)
            self.next_tick = self.last_tick + timedelta(seconds=self.check_interval)
            self.tick_count += 1
            
            logger.debug("⏱️ execute_bot_trades start")
            
            # Check system gate first
            should_run, gate_reason = system_gate.validate_scheduler_tick()
            if not should_run:
                logger.debug(f"Scheduler tick skipped: {gate_reason}")
                return
            
            logger.info("📊 Paper tick start")
            
            # Get all active bots (guaranteed non-deleted)
            active_bots = await db.bots_collection.find(
                bot_not_deleted_filter({"status": "active"}),
                {"_id": 0}
            ).to_list(1000)
            
            if not active_bots:
                logger.debug("No active bots found")
                return
            
            logger.info(f"📊 Bots scanned: {len(active_bots)} active")
            
            # Filter bots by supported exchanges for paper trading
            supported_bots = []
            unsupported_bots = []
            
            for bot in active_bots:
                exchange = bot.get('exchange', '').lower()
                if exchange in PAPER_SUPPORTED_EXCHANGES:
                    supported_bots.append(bot)
                else:
                    unsupported_bots.append(bot)
            
            # Pause bots on unsupported exchanges
            for bot in unsupported_bots:
                exchange = bot.get('exchange', 'unknown')
                logger.warning(f"⚠️ Bot {bot['name']} on unsupported exchange {exchange} - pausing")
                await db.bots_collection.update_one(
                    {"id": bot['id']},
                    {"$set": {
                        "status": "paused",
                        "pause_reason": BotPauseReason.UNSUPPORTED_EXCHANGE,
                        "pause_reason_code": BotPauseReason.UNSUPPORTED_EXCHANGE,
                        "paused_by_system": True,
                        "paused_at": datetime.now(timezone.utc).isoformat(),
                        "last_intervention": {
                            "source": "trading_scheduler",
                            "rule": "unsupported_exchange",
                            "reason_code": BotPauseReason.UNSUPPORTED_EXCHANGE,
                            "threshold": None,
                            "reason": f"Exchange {exchange} is not supported for paper trading",
                            "timestamp": datetime.now(timezone.utc).isoformat()
                        }
                    }}
                )
                
                # Place bot in quarantine for auto-retraining
                try:
                    await quarantine_service.quarantine_bot(
                        bot['id'],
                        BotPauseReason.UNSUPPORTED_EXCHANGE,
                        {
                            "source": "trading_scheduler",
                            "rule": "unsupported_exchange",
                            "reason_code": BotPauseReason.UNSUPPORTED_EXCHANGE,
                            "threshold": None
                        }
                    )
                except Exception as e:
                    logger.warning(f"Failed to quarantine bot: {e}")
                
                # Emit bot status changed event
                try:
                    await rt_events.bot_status_changed(
                        bot['user_id'], 
                        bot['id'], 
                        "paused", 
                        BotPauseReason.UNSUPPORTED_EXCHANGE
                    )
                except Exception as e:
                    logger.warning(f"Failed to emit bot_status_changed event: {e}")
            
            active_bots = supported_bots

            # Sync with runtime truth store (pause/stopped bots are skipped)
            runtime_filtered = []
            for bot in active_bots:
                runtime_state = await bot_runtime_state.ensure_state(bot)
                state = runtime_state.get("state") if runtime_state else bot.get("status", "active")
                if state in {"paused", "stopped"}:
                    if bot.get("status") != state:
                        await db.bots_collection.update_one(
                            {"id": bot["id"]},
                            {"$set": {"status": state, "pause_reason": runtime_state.get("reason")}}
                        )
                    logger.debug(f"Runtime gate: skipping {bot['name']} ({state})")
                    continue
                runtime_filtered.append(bot)
            active_bots = runtime_filtered
            
            if not active_bots:
                logger.debug("No bots on supported exchanges")
                return
            
            # Check each user's System Mode settings and track reasons
            users_with_trading = {}
            users_pause_reasons = {}
            for bot in active_bots:
                user_id = bot['user_id']
                if user_id not in users_with_trading:
                    modes = await db.system_modes_collection.find_one({"user_id": user_id}, {"_id": 0})
                    
                    # Check various conditions
                    if not modes:
                        users_with_trading[user_id] = False
                        users_pause_reasons[user_id] = BotPauseReason.MODE_DISABLED
                    elif modes.get('emergencyStop', False):
                        users_with_trading[user_id] = False
                        users_pause_reasons[user_id] = BotPauseReason.EMERGENCY_STOP
                    elif not modes.get('autopilot'):
                        users_with_trading[user_id] = False
                        users_pause_reasons[user_id] = BotPauseReason.MODE_DISABLED
                    else:
                        # Autopilot is ON and no emergency stop
                        users_with_trading[user_id] = True
                        users_pause_reasons[user_id] = None
            
            # Update system_state to reflect paper trading status
            for user_id in users_with_trading.keys():
                if users_with_trading[user_id]:
                    # Update system modes to show paperTrading=true by default for safety
                    modes = await db.system_modes_collection.find_one({"user_id": user_id}, {"_id": 0})
                    if modes:
                        # Default to paper trading if liveTrading is not explicitly enabled
                        is_live_trading = modes.get('liveTrading', False)
                        is_paper_trading = not is_live_trading  # Paper by default
                        
                        await db.system_modes_collection.update_one(
                            {"user_id": user_id},
                            {"$set": {"paperTrading": is_paper_trading}},
                            upsert=False
                        )
            
            # Filter bots with trading enabled and pause others with reason.
            # Keep paper bots running when mode is disabled so they are not blocked by MODE_DISABLED.
            paused_bots = []
            runnable_bots = []
            for bot in active_bots:
                user_id = bot['user_id']
                user_can_trade = users_with_trading.get(user_id, False)
                pause_reason = users_pause_reasons.get(user_id, BotPauseReason.MODE_DISABLED)
                if (not user_can_trade and
                        pause_reason == BotPauseReason.MODE_DISABLED and
                        _is_paper_bot(bot)):
                    runnable_bots.append(bot)
                    continue
                if user_can_trade:
                    runnable_bots.append(bot)
                else:
                    paused_bots.append(bot)
            active_bots = runnable_bots
            
            # Update paused bots with pause reason
            for bot in paused_bots:
                user_id = bot['user_id']
                pause_reason = users_pause_reasons.get(user_id, BotPauseReason.MODE_DISABLED)
                
                await db.bots_collection.update_one(
                    {"id": bot['id']},
                    {"$set": {
                        "status": "paused",
                        "pause_reason": pause_reason,
                        "pause_reason_code": pause_reason,
                        "paused_by_system": True,
                        "paused_at": datetime.now(timezone.utc).isoformat(),
                        "last_intervention": {
                            "source": "trading_scheduler",
                            "rule": "system_mode_gate",
                            "reason_code": pause_reason,
                            "threshold": None,
                            "reason": f"Scheduler gate blocked bot ({pause_reason})",
                            "timestamp": datetime.now(timezone.utc).isoformat()
                        }
                    }}
                )
                
                # Place bot in quarantine for auto-retraining
                try:
                    if pause_reason != BotPauseReason.MODE_DISABLED or not _is_paper_bot(bot):
                        await quarantine_service.quarantine_bot(
                            bot['id'],
                            pause_reason,
                            {
                                "source": "trading_scheduler",
                                "rule": "system_mode_gate",
                                "reason_code": pause_reason,
                                "threshold": None
                            }
                        )
                except Exception as e:
                    logger.warning(f"Failed to quarantine bot: {e}")
                
                # Emit bot status changed event
                try:
                    await rt_events.bot_status_changed(
                        user_id, 
                        bot['id'], 
                        "paused", 
                        pause_reason
                    )
                except Exception as e:
                    logger.warning(f"Failed to emit bot_status_changed event: {e}")
            
            if not active_bots:
                return

            # Record tick timestamp for each evaluated bot so that diagnostics
            # endpoints always show a fresh last_tick_at (single source of truth).
            for _tick_bot in active_bots:
                try:
                    await bot_runtime_state.record_tick(_tick_bot['id'], _tick_bot['user_id'])
                except Exception:
                    pass

            # Process ready trades from queue
            logger.debug("🔍 Checking trade queue for ready trades...")
            # Build a fast lookup set of active bot IDs to detect stale queue entries
            active_bot_ids = {b['id'] for b in active_bots}
            for _ in range(5):  # Process up to 5 trades per cycle
                trade_request = await trade_staggerer.get_next_trade()
                
                if not trade_request:
                    logger.debug("📭 No trade ready in queue")
                    break
                
                bot_id = trade_request.get('bot_id')
                if not bot_id:
                    logger.warning(
                        f"⚠️ Malformed queue entry missing bot_id – dropping. payload={trade_request!r}"
                    )
                    continue

                logger.info(f"📤 Dequeued trade: bot_id={bot_id}")

                bot = next((b for b in active_bots if b['id'] == bot_id), None)
                
                if not bot:
                    # Stale queue entry – discard it (do NOT re-queue) so it stops repeating
                    logger.warning(
                        f"⚠️ Bot {bot_id} not found in active bots – discarding stale queue entry"
                    )
                    continue
                
                # PHASE 4B/4C: Validate trading mode gates BEFORE execution
                try:
                    can_trade, mode, reason = await trading_mode_validator.validate_bot_trading_mode(bot_id, bot)
                    
                    if not can_trade:
                        logger.warning(f"⛔ {bot['name']} - Trading blocked (gate): {reason}")
                        # Don't execute - mark reason
                        continue
                    
                    logger.debug(f"✅ Trading gates passed for {bot['name']} in {mode} mode")
                    
                except TradingGateError as e:
                    logger.error(f"⛔ Trading gate error for {bot['name']}: {e}")
                    continue
                
                # Execute trade based on mode
                try:
                    logger.debug(f"🔄 Executing trade for {bot['name']} (bot_id={bot_id})")
                    
                    # Check both 'mode' and 'trading_mode' for backwards compatibility
                    mode = bot.get('mode') or bot.get('trading_mode', 'paper')
                    is_paper_mode = str(mode).strip().lower().startswith('paper')
                    
                    # Register trade start
                    await trade_staggerer.register_trade_start(bot_id, bot.get('exchange'))
                    logger.debug(f"📝 Registered trade start for {bot['name']}")
                    
                    if is_paper_mode:
                        # Paper trading
                        logger.info(f"📊 Trade candidate: {bot['name']} on {bot.get('exchange')}")
                        logger.info(
                            f"▶️  PAPER_SUBMIT | {bot['name']} | bot_id={bot_id[:8]} | "
                            f"exchange={bot.get('exchange')}"
                        )
                        
                        result = await paper_engine.run_trading_cycle(
                            bot['id'],
                            bot,
                            {'bots': db.bots_collection, 'trades': db.trades_collection}
                        )
                        
                        if result and result.get('trade'):
                            trade = result['trade']
                            # Use the trade's own id; fall back to bot_id only for logging
                            trade_log_id = trade.get('id') or trade.get('trade_id') or bot_id
                            profit = trade.get('profit_loss', 0)
                            trade_status = trade.get('status', 'unknown')
                            logger.info(
                                f"✅ PAPER_FILL | {bot['name']} | trade_id={trade_log_id} | "
                                f"status={trade_status} | pnl={profit:.2f}"
                            )
                            logger.info(f"📡 Realtime event emitted: trade_id={trade_log_id}")
                            # Clear any previous order error on successful trade
                            await db.bots_collection.update_one(
                                {"id": bot_id},
                                {"$set": {
                                    "last_tick_at": datetime.now(timezone.utc).isoformat(),
                                    "last_trade_simulated_at": datetime.now(timezone.utc).isoformat(),
                                    "last_order_error": None
                                }}
                            )
                        elif result is None or (isinstance(result, dict) and not result.get('success', True)):
                            # Trade was attempted but blocked/failed - record diagnostics
                            err_msg = result.get('error') if isinstance(result, dict) else "No trade result"
                            skip_reason = result.get('skip_reason') if isinstance(result, dict) else None
                            reason_msg = skip_reason or err_msg or "unknown"
                            # Map known skip reasons to stable codes for easy log grepping
                            _SKIP_CODE_MAP = {
                                "edge_gate": "SKIP_EDGE_GATE",
                                "pair_not_allowed": "SKIP_PAIR_NOT_ALLOWED",
                                "spread_too_wide": "SKIP_SPREAD_WIDE",
                                "low_liquidity": "SKIP_LOW_LIQUIDITY",
                                "open_trade_close_failed": "SKIP_OPEN_CLOSE_FAIL",
                            }
                            skip_code = _SKIP_CODE_MAP.get(skip_reason, "SKIP_OTHER")
                            logger.info(
                                f"⏭️  {skip_code} | {bot['name']} | {reason_msg}"
                            )
                            await db.bots_collection.update_one(
                                {"id": bot_id},
                                {"$set": {
                                    "last_tick_at": datetime.now(timezone.utc).isoformat(),
                                    "last_order_attempt_at": datetime.now(timezone.utc).isoformat(),
                                    "last_order_error": reason_msg
                                }}
                            )
                        else:
                            # Tick happened but no trade (e.g. open position)
                            await db.bots_collection.update_one(
                                {"id": bot_id},
                                {"$set": {"last_tick_at": datetime.now(timezone.utc).isoformat()}}
                            )
                    else:
                        # LIVE TRADING - Use live_trading_engine
                        logger.info(f"🔴 LIVE TRADING: {bot['name']} on {bot.get('exchange')}")
                        
                        # Execute live trade
                        result = await self.execute_live_trade(bot)
                    
                    # Register trade complete
                    await trade_staggerer.register_trade_complete(bot_id, bot.get('exchange'))
                    logger.debug(f"✅ Registered trade complete for {bot['name']}")
                    
                    # Send WebSocket update via rt_events for enhanced tracking
                    if result and isinstance(result, dict):
                        trade_data = result.get('trade', {})
                        if trade_data:
                            # Broadcast trade execution event
                            try:
                                await rt_events.trade_executed(bot['user_id'], {
                                    "bot_id": bot['id'],
                                    "bot_name": bot['name'],
                                    "pair": trade_data.get('pair', 'unknown'),
                                    "side": trade_data.get('side', 'unknown'),
                                    "profit_loss": trade_data.get('profit_loss', 0),
                                    "new_capital": result.get('new_capital', 0),
                                    "total_profit": result.get('total_profit', 0),
                                    "timestamp": datetime.now(timezone.utc).isoformat()
                                })
                            except Exception as e:
                                logger.warning(f"Failed to emit trade_executed event: {e}")
                        
                        # Legacy WebSocket update (keep for backwards compatibility)
                        await manager.send_message(bot['user_id'], {
                            "type": "trade_executed",
                            "bot_id": result.get('bot_id', bot_id),
                            "bot_name": bot['name'],
                            "new_capital": result.get('new_capital', 0),
                            "total_profit": result.get('total_profit', 0),
                            "trade": trade_data
                        })
                    
                except Exception as e:
                    logger.error(f"❌ Trade execution error for {bot['name']}: {e}", exc_info=True)
                    await trade_staggerer.register_trade_complete(bot_id, bot.get('exchange'))
                    # Surface the error into bot document for diagnostics
                    try:
                        await db.bots_collection.update_one(
                            {"id": bot_id},
                            {"$set": {
                                "last_tick_at": datetime.now(timezone.utc).isoformat(),
                                "last_order_attempt_at": datetime.now(timezone.utc).isoformat(),
                                "last_order_error": str(e)
                            }}
                        )
                    except Exception:
                        pass
            
            # Add new trades to queue
            for bot in active_bots:
                bot_id = bot['id']
                exchange = bot.get('exchange', 'binance')
                
                # Check if bot can trade
                can_execute, reason = await trade_staggerer.can_execute_now(bot_id, exchange)
                
                if can_execute:
                    # Add to queue
                    await trade_staggerer.add_to_queue(bot_id, exchange, priority=0)

            # Force-close overdue open trades for all users — this sweeps trades from
            # paused bots that the normal cycle would skip (fix for D exit precedence).
            try:
                user_ids_seen = {b.get('user_id') for b in active_bots if b.get('user_id')}
                for uid in user_ids_seen:
                    await paper_engine.close_overdue_trades(uid)
            except Exception as _sweep_err:
                logger.warning(f"Overdue trade sweep error: {_sweep_err}")
        
        except Exception as e:
            logger.error(f"Trading cycle error: {e}")
    
    async def execute_live_trade(self, bot: dict) -> dict:
        """Execute a live trade using live_trading_engine"""
        try:
            # Get bot's trading pair
            pair = bot.get('pair', 'BTC/ZAR')
            exchange = bot.get('exchange', 'binance')
            
            # Determine trade size based on risk mode
            risk_multipliers = {
                'safe': 0.25,
                'balanced': 0.35,
                'risky': 0.45,
                'aggressive': 0.60
            }
            
            risk_mode = bot.get('risk_mode', 'safe')
            multiplier = risk_multipliers.get(risk_mode, 0.25)
            
            capital = bot.get('current_capital', 1000)
            trade_size = capital * multiplier
            
            # Determine trade side using market regime
            # Prefer regime detector over random coin flip
            try:
                from engines.regime_detector import regime_detector
                regime = await regime_detector.detect_regime(exchange, pair)
                regime_name = regime.regime.value if hasattr(regime, 'regime') else str(regime)
                if regime_name in ('bull', 'trending_up', 'strong_bull'):
                    side = 'buy'
                elif regime_name in ('bear', 'trending_down', 'strong_bear'):
                    side = 'sell'
                else:
                    side = 'buy'  # Default to buy in neutral/unknown regimes
            except Exception:
                side = 'buy'  # Safe default — avoid random

            # Never short spot by default.
            market_type = str(bot.get("market_type", "spot")).lower()
            supports_shorting = bool(bot.get("supports_shorting", False))
            live_shorting_enabled = env_bool("LIVE_SHORTING_ENABLED", False)
            if side == "sell" and not (
                market_type in {"margin", "futures"} and supports_shorting and live_shorting_enabled
            ):
                return {
                    "success": False,
                    "bot_id": bot["id"],
                    "trade_direction": "FLAT",
                    "skip_reason": "bearish_spot_no_short",
                }
            
            # Calculate amount
            # For live trading, we need to get real price first
            
            # Check if user has API keys for this exchange (also check legacy 'provider' field)
            # Guard: never treat AI providers as exchanges
            from config.platforms import SUPPORTED_PLATFORMS as _SUPPORTED_PLATFORMS
            if exchange.lower() not in _SUPPORTED_PLATFORMS:
                logger.warning(f"Exchange '{exchange}' is not a supported exchange – aborting live trade")
                return {"success": False, "bot_id": bot['id'], "skip_reason": f"Unsupported exchange: {exchange}"}

            api_key_doc = await db.api_keys_collection.find_one({
                "user_id": bot['user_id'],
                "$or": [{"exchange": exchange}, {"provider": exchange}]
            }, {"_id": 0})
            
            if not api_key_doc:
                logger.warning(f"No API keys for {exchange} - falling back to paper mode")
                return await paper_engine.run_trading_cycle(
                    bot['id'],
                    bot,
                    {'bots': db.bots_collection, 'trades': db.trades_collection}
                )
            
            try:
                await enforce_live_trading_gates(bot['user_id'], exchange)
            except TradingGateError as e:
                logger.warning(f"Live trading gate blocked: {e}")
                return None

            can_place, violations = await live_gate_service.can_place_order(
                bot['user_id'],
                bot['id'],
                exchange
            )
            if not can_place:
                logger.warning(f"LiveGate blocked trade: {violations}")
                return None

            # Compute trade amount using position sizing logic instead of hardcoded value
            trade_amount = None
            skip_reason = None
            try:
                from engines.position_sizing import PositionSizer
                sizer = PositionSizer()
                sizing = await sizer.get_recommended_position_size(bot['id'], pair)
                if "error" not in sizing:
                    recommended_usd = sizing.get("recommended_position_size", 0)
                    # Convert USD position size to base asset amount using a price estimate
                    price_estimate = await paper_engine.get_real_price(pair, exchange)
                    if price_estimate and price_estimate > 0 and recommended_usd > 0:
                        trade_amount = recommended_usd / price_estimate
                    else:
                        logger.warning(f"Could not compute trade amount for {pair} on {exchange} – no price")
                        skip_reason = "Cannot compute trade amount: price unavailable"
                else:
                    skip_reason = f"Position sizing error: {sizing.get('error')}"
            except Exception as e:
                skip_reason = f"Position sizing exception: {e}"

            if trade_amount is None or trade_amount <= 0:
                effective_reason = skip_reason or "Amount could not be determined"
                logger.warning(f"Skipping live trade for {bot.get('name')}: {effective_reason}")
                return {"success": False, "bot_id": bot['id'], "skip_reason": effective_reason}

            # Execute trade via live engine
            trade_result = await live_trading_engine.execute_trade(
                bot_id=bot['id'],
                bot_data=bot,
                symbol=pair,
                side=side,
                amount=trade_amount,
                price=None,  # Market order
                paper_mode=False  # LIVE MODE
            )
            
            if not trade_result.get('success'):
                logger.error(f"Live trade failed: {trade_result.get('error')}")
                return None
            
            # Record trade in database
            from uuid import uuid4
            from utils.trade_utils import build_trade_record

            entry_price = trade_result.get('entry_price', trade_result.get('price', 0))
            exit_price = trade_result.get('exit_price')
            if exit_price is None:
                logger.error("Live trade missing exit_price; defaulting to entry_price for bot %s", bot['id'])
                exit_price = entry_price
            trade_doc = build_trade_record(
                {
                    "id": str(uuid4()),
                    "bot_id": bot['id'],
                    "user_id": bot['user_id'],
                    "pair": pair,
                    "side": side,
                    "entry_price": entry_price,
                    "exit_price": exit_price,
                    "amount": trade_result.get('amount', 0),
                    "profit_loss": trade_result.get('net_profit', 0),
                    "is_paper": False,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "exchange": exchange,
                    "trading_mode": "live",
                    "is_live": True,
                    "exchange_order_id": trade_result.get("order_id") or trade_result.get("id"),
                    "trade_close_reason": "live_fill",
                    "trade_direction": "LONG" if side == "buy" else "SHORT",
                    "realized_pnl": trade_result.get("net_profit", 0),
                    "fee_paid": trade_result.get("fees", trade_result.get("fee", 0))
                },
                user_id=bot['user_id'],
                bot=bot
            )
            
            await db.trades_collection.insert_one(trade_doc)

            try:
                from services.realtime_service import realtime_service
                await realtime_service.broadcast_trade_execution(bot['user_id'], trade_doc)
            except Exception as e:
                logger.warning(f"Realtime trade broadcast failed: {e}")

            try:
                from services.trade_analyst import record_trade_lesson
                await record_trade_lesson(bot['user_id'], bot['id'], trade_doc)
            except Exception as e:
                logger.debug(f"Trade lesson record failed: {e}")

            # Update bot stats
            from utils.trade_utils import classify_trade_outcome
            net_profit = trade_result.get('net_profit', 0)
            new_capital = capital + net_profit
            outcome = classify_trade_outcome(net_profit)
            
            await db.bots_collection.update_one(
                {"id": bot['id']},
                {
                    "$set": {
                        "current_capital": new_capital,
                        "last_trade_time": datetime.now(timezone.utc).isoformat()
                    },
                    "$inc": {
                        "total_profit": net_profit,
                        "trades_count": 1,
                        "win_count": outcome["win_count"],
                        "loss_count": outcome["loss_count"]
                    }
                }
            )
            
            return {
                "bot_id": bot['id'],
                "new_capital": new_capital,
                "total_profit": bot.get('total_profit', 0) + trade_result.get('net_profit', 0),
                "trade": trade_doc
            }
            
        except Exception as e:
            logger.error(f"Execute live trade error: {e}")
            return None
    
    async def trading_loop(self):
        """Main trading loop - runs continuously"""
        logger.info("🚀 Continuous staggered trading started")
        
        while self.is_running:
            try:
                # Emit heartbeat for realtime monitoring
                current_time = datetime.now(timezone.utc)
                if self.last_heartbeat is None or (current_time - self.last_heartbeat).total_seconds() >= self.heartbeat_interval:
                    self.last_heartbeat = current_time
                    try:
                        from services.autonomy_heartbeat import heartbeat_registry
                        heartbeat_registry.mark_ok("trading_scheduler")
                    except Exception:
                        pass
                    heartbeat_event = {
                        "type": "heartbeat",
                        "timestamp": current_time.isoformat(),
                        "scheduler": "trading_scheduler",
                        "status": "running"
                    }
                    # Broadcast heartbeat to all connected users
                    try:
                        await manager.broadcast(heartbeat_event)
                        logger.debug("💓 Heartbeat emitted")
                    except Exception as e:
                        logger.debug(f"Failed to emit heartbeat: {e}")
                
                await self.execute_bot_trades()
                
                # Clean up stale trades periodically
                await trade_staggerer.clear_stale_trades()
                
                # Wait before next check
                await asyncio.sleep(self.check_interval)
                
            except Exception as e:
                logger.error(f"Trading loop error: {e}")
                try:
                    from services.autonomy_heartbeat import heartbeat_registry
                    heartbeat_registry.mark_error("trading_scheduler", str(e))
                except Exception:
                    pass
                await asyncio.sleep(self.check_interval)
    
    def start(self):
        """Start the trading scheduler"""
        if not self.is_running:
            self.is_running = True
            self.last_tick = None
            self.next_tick = None
            self.tick_count = 0
            self.task = asyncio.create_task(self.trading_loop())
            logger.info("✅ Trading scheduler started - continuous staggered execution")
    
    def stop(self):
        """Stop the trading scheduler"""
        self.is_running = False
        if self.task:
            self.task.cancel()
        logger.info("🔴 Trading scheduler stopped")
    
    def get_status(self) -> dict:
        """Get scheduler status for diagnostics"""
        return {
            "running": self.is_running,
            "last_tick": self.last_tick.isoformat() if self.last_tick else None,
            "next_tick": self.next_tick.isoformat() if self.next_tick else None,
            "tick_count": self.tick_count,
            "check_interval_seconds": self.check_interval,
            "task_active": self.task is not None and not self.task.done() if self.task else False
        }

# Global instance
trading_scheduler = TradingScheduler()
