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
from services.risk_lock_service import risk_lock_service

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
    DAILY_LOSS_LOCK = "DAILY_LOSS_LOCK"  # Daily loss limit reached — locked until midnight UTC


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
        # --- Pass 3: Observability state ---
        self.last_tick_at = None          # ISO timestamp of last execute_bot_trades call
        self.last_tick_bots = 0           # How many bots were scanned on last tick
        self.last_tick_queued = 0         # How many new trades were queued on last tick
        self.last_tick_executed = 0       # How many trades were executed on last tick
        self.last_tick_processed = 0      # How many trade requests were attempted (dequeued) on last tick
        self.last_tick_noop_reason = None # Why last tick did nothing (if it did nothing)
        self.last_tick_activity = {
            "total_bot_records": 0,
            "active_bot_records": 0,
            "runnable_active_bots": 0,
            "paused_bots": 0,
            "blocked_bots": 0,
        }
        self.last_trade_at = None         # ISO timestamp of last successful trade execution
        self.last_trade_bot = None        # bot_id of last successful trade
        self.last_trade_result = None     # Summary of last trade result
        self.total_ticks = 0             # Total scheduler ticks since start
        self.total_trades_executed = 0   # Total trades executed since start
        self.total_noop_ticks = 0        # Total ticks that produced no trade
        self._queue_rotation_offset = 0  # Fair queue rotation cursor

    def _fair_queue_order(self, bots: list[dict]) -> list[dict]:
        """Rotate bot queue insertion order each tick to avoid starvation by fixed ordering."""
        if not bots:
            return []
        if len(bots) == 1:
            return bots
        start = self._queue_rotation_offset % len(bots)
        ordered = bots[start:] + bots[:start]
        self._queue_rotation_offset = (self._queue_rotation_offset + 1) % len(bots)
        return ordered
        
    async def execute_bot_trades(self):
        """Execute trades using staggered queue - CONTINUOUS OPERATION"""
        tick_time = datetime.now(timezone.utc)
        self.last_tick_at = tick_time.isoformat()
        self.total_ticks += 1
        tick_executed = 0
        tick_queued = 0
        tick_processed = 0  # Trade requests dequeued and attempted (even if result=None)
        try:
            # Check system gate first
            should_run, gate_reason = system_gate.validate_scheduler_tick()
            if not should_run:
                logger.debug(f"Scheduler tick skipped: {gate_reason}")
                self.last_tick_noop_reason = f"gate: {gate_reason}"
                self.last_tick_bots = 0
                self.last_tick_queued = 0
                self.last_tick_executed = 0
                self.last_tick_activity = {
                    "total_bot_records": 0,
                    "active_bot_records": 0,
                    "runnable_active_bots": 0,
                    "paused_bots": 0,
                    "blocked_bots": 0,
                }
                self.total_noop_ticks += 1
                return
            
            logger.info("📊 Paper tick start")
            
            # Get all active bots
            active_bots = await db.bots_collection.find(
                {"status": "active"},
                {"_id": 0}
            ).to_list(1000)

            # Pre-cycle queue hygiene: remove stale/deleted bot queue items.
            active_bot_ids = {bot.get("id") for bot in active_bots if bot.get("id")}
            await trade_staggerer.purge_orphaned_queue(active_bot_ids)

            if not active_bots:
                self.last_tick_noop_reason = "no_active_bots"
                self.last_tick_bots = 0
                self.last_tick_queued = 0
                self.last_tick_executed = 0
                self.last_tick_activity = {
                    "total_bot_records": 0,
                    "active_bot_records": 0,
                    "runnable_active_bots": 0,
                    "paused_bots": 0,
                    "blocked_bots": 0,
                }
                self.total_noop_ticks += 1
                logger.info(
                    "📊 Scheduler tick — Bots scanned: 0 active | "
                    "Noop reason: no_active_bots"
                )
                return
            
            db_active_records = len(active_bots)
            logger.info(f"📊 Scheduler scan — active_bot_records={db_active_records}")
            
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

            # Sync with runtime truth store (pause/stopped bots are skipped).
            # Use reconcile_with_bot_doc so that stale runtime-state rows are
            # overwritten by the authoritative bot document, preventing the scheduler
            # from re-pausing bots that were resumed via the API.
            runtime_filtered = []
            runtime_skipped = 0
            for bot in active_bots:
                runtime_state = await bot_runtime_state.reconcile_with_bot_doc(bot["id"], bot)
                state = runtime_state.get("state") if runtime_state else bot.get("status", "active")
                if state in {"paused", "stopped"}:
                    logger.debug(f"Runtime gate: skipping {bot['name']} ({state})")
                    runtime_skipped += 1
                    continue
                runtime_filtered.append(bot)
            active_bots = runtime_filtered

            if not active_bots:
                self.last_tick_noop_reason = "no_supported_bots"
                self.last_tick_bots = 0
                self.last_tick_queued = 0
                self.last_tick_executed = 0
                self.last_tick_activity = {
                    "total_bot_records": len(supported_bots) + len(unsupported_bots),
                    "active_bot_records": len(supported_bots) + len(unsupported_bots),
                    "runnable_active_bots": 0,
                    "paused_bots": runtime_skipped,
                    "blocked_bots": len(supported_bots) + len(unsupported_bots),
                }
                self.total_noop_ticks += 1
                logger.info(
                    "📊 Scheduler tick — active_bot_records: %d | "
                    "runtime_filtered: %d | runnable_active_bots: 0 | "
                    "Noop reason: no_supported_bots",
                    len(supported_bots) + len(unsupported_bots), runtime_skipped,
                )
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
                    else:
                        # Check daily loss lock (blocks ALL bots for this user today)
                        try:
                            locked, _lock_reason = await risk_lock_service.is_locked_today(user_id)
                        except Exception:
                            locked = False
                        if locked:
                            users_with_trading[user_id] = False
                            users_pause_reasons[user_id] = BotPauseReason.DAILY_LOSS_LOCK
                        elif not modes.get('autopilot'):
                            users_with_trading[user_id] = False
                            users_pause_reasons[user_id] = BotPauseReason.MODE_DISABLED
                        else:
                            # Autopilot is ON and no emergency stop or loss lock
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
                self.last_tick_noop_reason = "all_bots_paused"
                self.last_tick_bots = 0
                self.last_tick_queued = 0
                self.last_tick_executed = 0
                self.last_tick_activity = {
                    "total_bot_records": len(paused_bots),
                    "active_bot_records": len(paused_bots),
                    "runnable_active_bots": 0,
                    "paused_bots": len(paused_bots),
                    "blocked_bots": len(paused_bots),
                }
                self.total_noop_ticks += 1
                # Log the first unique pause reason so dashboards / ops can see why
                sample_reason = None
                if paused_bots:
                    sample_uid = paused_bots[0].get("user_id")
                    sample_reason = users_pause_reasons.get(sample_uid, "unknown")
                logger.info(
                    "📊 Scheduler tick — active_bot_records: %d | "
                    "mode_blocked: %d | runnable_active_bots: 0 | "
                    "Noop reason: all_bots_paused (sample: %s)",
                    len(paused_bots), len(paused_bots), sample_reason,
                )
                return
            
            self.last_tick_bots = len(active_bots)
            self.last_tick_activity = {
                "total_bot_records": db_active_records,
                "active_bot_records": db_active_records,
                "runnable_active_bots": len(active_bots),
                "paused_bots": len(paused_bots),
                "blocked_bots": max(0, db_active_records - len(active_bots)),
            }
            
            # Process ready trades from queue
            for _ in range(5):  # Process up to 5 trades per cycle
                trade_request = await trade_staggerer.get_next_trade()
                
                if not trade_request:
                    break
                
                bot_id = trade_request['bot_id']
                bot = next((b for b in active_bots if b['id'] == bot_id), None)
                
                if not bot:
                    continue
                
                # PHASE 4B/4C: Validate trading mode gates BEFORE execution
                try:
                    can_trade, mode, reason = await trading_mode_validator.validate_bot_trading_mode(bot_id, bot)
                    
                    if not can_trade:
                        logger.warning(f"⛔ {bot['name']} - Trading blocked: {reason}")
                        # Don't execute - mark reason
                        continue
                    
                    logger.debug(f"✅ Trading gates passed for {bot['name']} in {mode} mode")
                    
                except TradingGateError as e:
                    logger.error(f"⛔ Trading gate error for {bot['name']}: {e}")
                    continue
                
                # Execute trade based on mode
                try:
                    # Check both 'mode' and 'trading_mode' for backwards compatibility
                    mode = bot.get('mode') or bot.get('trading_mode', 'paper')
                    is_paper_mode = str(mode).strip().lower().startswith('paper')
                    
                    # Register trade start
                    await trade_staggerer.register_trade_start(bot_id, bot.get('exchange'))
                    
                    if is_paper_mode:
                        # Paper trading
                        logger.info(f"📊 Trade candidate: {bot['name']} on {bot.get('exchange')}")
                        
                        result = await paper_engine.run_trading_cycle(
                            bot['id'],
                            bot,
                            {'bots': db.bots_collection, 'trades': db.trades_collection}
                        )
                        tick_processed += 1
                        
                        if result and result.get('trade'):
                            trade = result['trade']
                            trade_id = trade.get('bot_id', 'unknown')
                            profit = trade.get('profit_loss', 0)
                            logger.info(f"✅ Trade inserted: id={trade_id}, profit={profit:.2f}")
                            logger.info(f"📡 Realtime event emitted: trade_id={trade_id}")
                            # --- Pass 3: Track successful trade ---
                            tick_executed += 1
                            self.last_trade_at = datetime.now(timezone.utc).isoformat()
                            self.last_trade_bot = bot_id
                            self.last_trade_result = {
                                "bot_name": bot.get('name'),
                                "pair": trade.get('pair', trade.get('symbol', 'unknown')),
                                "profit_loss": profit,
                                "side": trade.get('side', 'unknown'),
                                "is_paper": True,
                            }
                    else:
                        # LIVE TRADING - Use live_trading_engine
                        logger.info(f"🔴 LIVE TRADING: {bot['name']} on {bot.get('exchange')}")
                        
                        # Execute live trade
                        result = await self.execute_live_trade(bot)
                        tick_processed += 1
                        if result and isinstance(result, dict) and result.get('trade'):
                            tick_executed += 1
                            self.last_trade_at = datetime.now(timezone.utc).isoformat()
                            self.last_trade_bot = bot_id
                            self.last_trade_result = {
                                "bot_name": bot.get('name'),
                                "pair": result['trade'].get('pair', 'unknown'),
                                "profit_loss": result['trade'].get('profit_loss', 0),
                                "side": result['trade'].get('side', 'unknown'),
                                "is_paper": False,
                            }
                    
                    # Register trade complete
                    await trade_staggerer.register_trade_complete(bot_id, bot.get('exchange'))
                    
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
                        
                        # Canonical trade websocket flow is emitted via rt_events/realtime_service.
                    
                except Exception as e:
                    logger.error(f"Trade execution error for {bot['name']}: {e}")
                    await trade_staggerer.register_trade_complete(bot_id, bot.get('exchange'))
            
            # Add new trades to queue (with dedup — skip bots already queued)
            queued_bot_ids = {item['bot_id'] for item in trade_staggerer.trade_queue}
            for bot in self._fair_queue_order(active_bots):
                bot_id = bot['id']
                exchange = bot.get('exchange', 'binance')
                
                # Skip if bot is already in queue (prevents duplicate queue spam)
                if bot_id in queued_bot_ids:
                    continue
                
                # Check if bot can trade
                can_execute, reason = await trade_staggerer.can_execute_now(bot_id, exchange)
                
                if can_execute:
                    # Add to queue
                    await trade_staggerer.add_to_queue(bot_id, exchange, priority=0)
                    tick_queued += 1
            
            # --- Pass 3: Update tick observability ---
            self.last_tick_queued = tick_queued
            self.last_tick_executed = tick_executed
            self.last_tick_processed = tick_processed
            self.total_trades_executed += tick_executed
            if tick_executed == 0:
                # Differentiate: were trade requests processed (open positions managed) or nothing happened?
                if tick_processed > 0:
                    # Trades were attempted but no new open/close happened — open positions are being managed
                    self.last_tick_noop_reason = "managing_open_positions"
                    self.total_noop_ticks += 1
                    logger.info(
                        "📊 Scheduler tick — active_bot_records: %d | "
                        "runnable_active_bots: %d | processed: %d | queued: %d | "
                        "Noop reason: managing_open_positions",
                        self.last_tick_activity.get("active_bot_records", 0),
                        self.last_tick_activity.get("runnable_active_bots", 0),
                        tick_processed,
                        tick_queued,
                    )
                else:
                    self.last_tick_noop_reason = "no_trades_executed"
                    self.total_noop_ticks += 1
                    logger.info(
                        "📊 Scheduler tick — active_bot_records: %d | "
                        "runnable_active_bots: %d | queued: %d | "
                        "Noop reason: no_trades_executed",
                        self.last_tick_activity.get("active_bot_records", 0),
                        self.last_tick_activity.get("runnable_active_bots", 0),
                        tick_queued,
                    )
            else:
                self.last_tick_noop_reason = None
                logger.info(
                    "📊 Scheduler tick — active_bot_records: %d | "
                    "runnable_active_bots: %d | queued: %d | executed: %d",
                    self.last_tick_activity.get("active_bot_records", 0),
                    self.last_tick_activity.get("runnable_active_bots", 0),
                    tick_queued,
                    tick_executed,
                )
        
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
            
            # Determine trade side (buy or sell)
            import random
            side = 'buy' if random.random() > 0.5 else 'sell'
            
            # Calculate amount
            # For live trading, we need to get real price first
            
            # Check if user has API keys for this exchange
            api_key_doc = await db.api_keys_collection.find_one({
                "user_id": bot['user_id'],
                "exchange": exchange
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

            # Execute trade via live engine
            trade_result = await live_trading_engine.execute_trade(
                bot_id=bot['id'],
                bot_data=bot,
                symbol=pair,
                side=side,
                amount=0.001,  # Small amount for testing
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
    
    def get_health_snapshot(self) -> dict:
        """Return a comprehensive scheduler health snapshot for diagnostics."""
        task = self.task
        task_alive = task is not None and not task.done()
        return {
            "scheduler_running": self.is_running,
            "task_alive": task_alive,
            "last_heartbeat": self.last_heartbeat.isoformat() if self.last_heartbeat else None,
            "check_interval_seconds": self.check_interval,
            "last_tick_at": self.last_tick_at,
            "last_tick_bots": self.last_tick_bots,
            "last_tick_queued": self.last_tick_queued,
            "last_tick_executed": self.last_tick_executed,
            "last_tick_processed": getattr(self, 'last_tick_processed', 0),
            "last_tick_noop_reason": self.last_tick_noop_reason,
            "last_tick_activity": self.last_tick_activity,
            "last_trade_at": self.last_trade_at,
            "last_trade_bot": self.last_trade_bot,
            "last_trade_result": self.last_trade_result,
            "total_ticks": self.total_ticks,
            "total_trades_executed": self.total_trades_executed,
            "total_noop_ticks": self.total_noop_ticks,
            "queue_size": len(trade_staggerer.trade_queue),
            "active_trades": len(trade_staggerer.active_trades),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def start(self):
        """Start the trading scheduler"""
        if not self.is_running:
            self.is_running = True
            self.task = asyncio.create_task(self.trading_loop())
            logger.info("✅ Trading scheduler started - continuous staggered execution")
    
    def stop(self):
        """Stop the trading scheduler"""
        self.is_running = False
        if self.task:
            self.task.cancel()
        logger.info("🔴 Trading scheduler stopped")

# Global instance
trading_scheduler = TradingScheduler()
