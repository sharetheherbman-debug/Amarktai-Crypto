"""
Autopilot Engine - Autonomous Bot Management
- Daily profit reinvestment at 23:59 UTC
- Autonomous bot creation based on available profit
- Paper-to-live promotion after 7-day validation
- Capital optimization across bots
"""

import asyncio
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from datetime import datetime, timezone, timedelta
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from utils.env_utils import env_bool
from utils.trading_gates import check_autopilot_gates

logger = logging.getLogger(__name__)

class AutopilotEngine:
    def __init__(self):
        # Initialize scheduler immediately to prevent NoneType errors
        self.scheduler = AsyncIOScheduler()
        self.db = None
        self.running = False
        
    async def init_db(self):
        """Initialize database connection"""
        mongo_url = os.getenv('MONGO_URL', 'mongodb://localhost:27017')
        db_name = os.getenv('DB_NAME', 'amarktai_trading')
        client = AsyncIOMotorClient(mongo_url)
        self.db = client[db_name]
        
    async def start(self):
        """Start the autopilot engine - idempotent, respects feature flags"""
        # AUTOPILOT GATE: Check if autopilot can run
        can_run, message = check_autopilot_gates()
        if not can_run:
            logger.info(f"🤖 Autopilot Engine not started: {message}")
            return
        
        # Prevent multiple starts
        if self.running:
            logger.info("🤖 Autopilot Engine already running, skipping start")
            return
            
        # Check if schedulers should be enabled (separate flag)
        enable_schedulers = env_bool('ENABLE_SCHEDULERS', False)
        
        try:
            await self.init_db()
            self.running = True
            
            # Only add jobs if scheduler is not already running and schedulers are enabled
            if enable_schedulers and not self.scheduler.running:
                # Schedule hourly reinvestment (changed from daily for faster capital redeployment)
                self.scheduler.add_job(
                    self.hourly_reinvestment_cycle,
                    trigger='interval',
                    hours=1,
                    id='hourly_reinvestment'
                )
                
                # Schedule hourly evolution cycle (genetic algorithm optimization)
                self.scheduler.add_job(
                    self.hourly_evolution_cycle,
                    trigger='interval',
                    hours=1,
                    id='hourly_evolution'
                )
                
                # Check paper bot promotions every hour
                self.scheduler.add_job(
                    self.check_paper_bot_promotions,
                    trigger='interval',
                    hours=1,
                    id='paper_bot_check'
                )
                
                # Autopilot strategy optimization every 6 hours
                self.scheduler.add_job(
                    self.optimize_strategies,
                    trigger='interval',
                    hours=6,
                    id='strategy_optimization'
                )
                
                self.scheduler.start()
                logger.info("🤖 Autopilot Engine started with scheduler (hourly reinvestment & evolution)")
            else:
                logger.info("🤖 Autopilot Engine started without scheduler (ENABLE_SCHEDULERS not truthy or already running)")
        except Exception as e:
            logger.error(f"Failed to start Autopilot Engine: {e}")
            self.running = False
            # Don't raise - let server continue
        
    async def hourly_reinvestment_cycle(self):
        """Hourly profit reinvestment - LEDGER-BASED (changed from daily)"""
        try:
            logger.info("💰 Starting hourly reinvestment cycle (ledger-based)...")
            
            # Get all users with autopilot enabled
            users = await self.db.users.find({'autopilot_enabled': True}).to_list(1000)
            
            for user in users:
                user_id = user['id']
                
                # NEW: Use ledger for accurate profit calculation
                try:
                    from services.ledger_service import get_ledger_service
                    ledger = get_ledger_service(self.db)
                    
                    # Get realized PnL and fees from ledger
                    realized_pnl = await ledger.compute_realized_pnl(user_id)
                    fees_paid = await ledger.compute_fees_paid(user_id)
                    
                    # Net profit after fees (single source of truth)
                    total_profit_after_fees = realized_pnl - fees_paid
                    
                    logger.info(f"User {user_id}: Ledger PnL={realized_pnl:.2f}, Fees={fees_paid:.2f}, Net={total_profit_after_fees:.2f}")
                    
                except Exception as ledger_error:
                    # Fallback to bot-based calculation
                    logger.warning(f"Ledger unavailable for user {user_id}, using bot-based: {ledger_error}")
                    
                    bots = await self.db.bots.find({'user_id': user_id}).to_list(1000)
                    
                    # Account for trading fees (0.1% per trade typical)
                    total_profit_after_fees = 0
                    for bot in bots:
                        bot_profit = bot.get('total_profit', 0)
                        trades_count = bot.get('trades_count', 0)
                        
                        # Estimate fees: 0.1% per trade (buy + sell = 0.2% per round trip)
                        estimated_fees = trades_count * 0.002 * bot.get('current_capital', 1000)
                        net_profit = bot_profit - estimated_fees
                        total_profit_after_fees += net_profit
                
                if total_profit_after_fees < 0:
                    logger.info(f"User {user_id}: Negative profit after fees, skipping reinvestment")
                    continue
                
                # Get bot count
                bots = await self.db.bots.find({'user_id': user_id}).to_list(1000)
                bot_count = len(bots)
                
                # Import config to get MAX_TOTAL_BOTS
                import config
                max_bots = config.MAX_TOTAL_BOTS
                
                # Get reinvestment threshold from config
                reinvest_threshold = config.REINVEST_THRESHOLD_ZAR
                new_bot_capital = config.NEW_BOT_CAPITAL
                
                # Strategy: Create new bot if profit >= new_bot_capital (after fees) and under max bots
                # Use the gated spawn function
                if total_profit_after_fees >= new_bot_capital and bot_count < max_bots:
                    result = await self.spawn_bot_if_profit_allows(user_id, new_bot_capital)
                    if result['success']:
                        logger.info(f"User {user_id}: {result['message']} (net profit: R{total_profit_after_fees:.2f})")
                    else:
                        logger.warning(f"User {user_id}: Bot spawn failed - {result.get('message', result.get('error'))}")
                    
                # Strategy: Reinvest in top performing bots (when profit >= threshold)
                elif total_profit_after_fees >= reinvest_threshold:
                    await self.reinvest_in_top_bots(user_id, total_profit_after_fees, bots)
                    
                # Create alert
                await self.db.alerts.insert_one({
                    'user_id': user_id,
                    'type': 'autopilot',
                    'severity': 'low',
                    'message': f'Hourly reinvestment complete. Net profit: R{total_profit_after_fees:.2f}',
                    'timestamp': datetime.now(timezone.utc).isoformat(),
                    'dismissed': False
                })
                
        except Exception as e:
            logger.error(f"Hourly reinvestment error: {e}")
    
    async def spawn_bot_if_profit_allows(self, user_id: str, seed_amount: float = 1000.0) -> dict:
        """
        Bot spawning gate with profit verification
        
        REQUIREMENTS:
        - Computes available_profit_pool = realized_profit_net_fees - reserved_profit
        - Atomically reserves seed_amount via ledger reservation event
        - Returns PROFIT_INSUFFICIENT error if insufficient profit
        - Enforces bot caps (max bots, exchange distribution)
        
        Args:
            user_id: User ID
            seed_amount: Amount of capital to allocate (default 1000 ZAR)
            
        Returns:
            dict with success/error status and details
        """
        try:
            from services.ledger_service import get_ledger_service
            
            # Step 1: Compute available profit pool
            ledger = get_ledger_service(self.db)
            realized_pnl = await ledger.compute_realized_pnl(user_id)
            fees_paid = await ledger.compute_fees_paid(user_id)
            net_profit = realized_pnl - fees_paid
            
            # Get reserved profit (already allocated to other bots)
            reserved = await ledger.compute_reserved_profit(user_id) if hasattr(ledger, 'compute_reserved_profit') else 0
            available_profit = net_profit - reserved
            
            logger.info(f"User {user_id}: PnL={realized_pnl:.2f}, Fees={fees_paid:.2f}, Net={net_profit:.2f}, Reserved={reserved:.2f}, Available={available_profit:.2f}")
            
            # Step 2: Check if sufficient profit
            if available_profit < seed_amount:
                return {
                    "success": False,
                    "error": "PROFIT_INSUFFICIENT",
                    "message": f"Insufficient profit pool. Available: R{available_profit:.2f}, Required: R{seed_amount:.2f}",
                    "available_profit": available_profit,
                    "required": seed_amount
                }
            
            # Step 3: Check bot caps
            bots = await self.db.bots.find({'user_id': user_id}).to_list(1000)
            bot_count = len(bots)
            
            # Import config to get MAX_TOTAL_BOTS
            import config
            max_bots = config.MAX_TOTAL_BOTS
            
            if bot_count >= max_bots:
                return {
                    "success": False,
                    "error": "BOT_LIMIT_REACHED",
                    "message": f"Maximum bot limit reached: {bot_count}/{max_bots}",
                    "current_bots": bot_count,
                    "max_bots": max_bots
                }
            
            # Step 4: Check exchange distribution
            # Supported exchanges: Luno, Binance, KuCoin only
            EXCHANGE_LIMITS = {
                'luno': 15,
                'binance': 15,
                'kucoin': 15
            }
            
            # Count bots per exchange
            exchange_counts = {}
            for bot in bots:
                exchange = bot.get('exchange', '').lower()
                exchange_counts[exchange] = exchange_counts.get(exchange, 0) + 1
            
            # Find exchange with available slots
            target_exchange = None
            for exchange, limit in EXCHANGE_LIMITS.items():
                current = exchange_counts.get(exchange, 0)
                if current < limit:
                    target_exchange = exchange
                    break
            
            if not target_exchange:
                return {
                    "success": False,
                    "error": "EXCHANGE_LIMIT_REACHED",
                    "message": "All exchanges at capacity",
                    "exchange_counts": exchange_counts,
                    "limits": EXCHANGE_LIMITS
                }
            
            # Step 5: Atomically reserve profit via ledger
            import uuid
            reservation_id = f"bot_spawn_{user_id}_{int(datetime.now(timezone.utc).timestamp() * 1000)}_{uuid.uuid4().hex[:8]}"
            await ledger.record_event({
                "user_id": user_id,
                "event_type": "profit_reservation",
                "amount": seed_amount,
                "reservation_id": reservation_id,
                "reason": "bot_spawning",
                "timestamp": datetime.now(timezone.utc).isoformat()
            })
            
            # Step 6: Create bot
            bot_result = await self.create_autonomous_bot(user_id, seed_amount, target_exchange)
            
            return {
                "success": True,
                "message": f"Bot spawned successfully on {target_exchange}",
                "bot_id": bot_result.get('bot_id') if bot_result else None,
                "exchange": target_exchange,
                "seed_amount": seed_amount,
                "available_profit_remaining": available_profit - seed_amount
            }
            
        except Exception as e:
            logger.error(f"Bot spawning gate error: {e}", exc_info=True)
            return {
                "success": False,
                "error": "INTERNAL_ERROR",
                "message": str(e)
            }
            
    async def create_autonomous_bot(self, user_id: str, capital: float, exchange: str = None):
        """Create a new bot autonomously
        
        Args:
            user_id: User ID
            capital: Initial capital for the bot
            exchange: Target exchange (if None, auto-select best performing)
        """
        try:
            # Determine best exchange if not specified
            if not exchange:
                api_keys = await self.db.api_keys.find({'user_id': user_id, 'connected': True}).to_list(10)
                exchanges = [key['provider'] for key in api_keys if key['provider'] in ['luno', 'binance', 'kucoin']]
                
                if not exchanges:
                    logger.warning(f"User {user_id}: No exchange APIs connected")
                    return {"success": False, "error": "NO_EXCHANGES"}
                    
                # Choose exchange with best performance
                exchange = await self.get_best_performing_exchange(user_id, exchanges)
            
            # Create bot ID
            bot_id = f"auto_{datetime.now(timezone.utc).timestamp()}"
            
            # Create bot
            bot = {
                'id': bot_id,
                'user_id': user_id,
                'name': f"Autopilot Bot {datetime.now().strftime('%Y%m%d_%H%M')}",
                'exchange': exchange,
                'risk_mode': 'balanced',
                'trading_mode': 'paper',  # Always start with paper
                'status': 'active',
                'initial_capital': capital,
                'current_capital': capital,
                'total_profit': 0,
                'win_rate': 0,
                'trades_count': 0,
                'max_drawdown': 0,
                'stop_loss_percent': 15.0,
                'created_at': datetime.now(timezone.utc).isoformat(),
                'paper_start_date': datetime.now(timezone.utc).isoformat(),
                'promoted_to_live': False,
                'strategy': {'type': 'adaptive', 'created_by': 'autopilot'},
                'learned_insights': []
            }
            
            await self.db.bots.insert_one(bot)
            logger.info(f"Created autonomous bot: {bot['name']} on {exchange}")
            
            return {"success": True, "bot_id": bot_id, "exchange": exchange}
            
        except Exception as e:
            logger.error(f"Autonomous bot creation error: {e}")
            return {"success": False, "error": str(e)}
            
    async def reinvest_in_top_bots(self, user_id: str, profit: float, bots: list):
        """Reinvest profit in top 5 performing bots"""
        try:
            # Sort bots by win rate and profit
            sorted_bots = sorted(
                [b for b in bots if b['status'] == 'active'],
                key=lambda x: (x.get('win_rate', 0), x.get('total_profit', 0)),
                reverse=True
            )[:5]
            
            if not sorted_bots:
                return
                
            # Distribute profit equally
            profit_per_bot = profit / len(sorted_bots)
            
            for bot in sorted_bots:
                current_capital = bot.get('current_capital', 0)
                new_capital = current_capital + profit_per_bot
                
                await self.db.bots.update_one(
                    {'id': bot['id']},
                    {'$set': {'current_capital': new_capital}}
                )
                
            logger.info(f"User {user_id}: Reinvested R{profit:.2f} across {len(sorted_bots)} bots")
            
        except Exception as e:
            logger.error(f"Reinvestment error: {e}")
            
    async def check_paper_bot_promotions(self):
        """Check if paper bots meet criteria for live trading promotion"""
        try:
            # Get paper bots that are 7+ days old
            seven_days_ago = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
            
            paper_bots = await self.db.bots.find({
                'trading_mode': 'paper',
                'paper_start_date': {'$lte': seven_days_ago},
                'promoted_to_live': False
            }).to_list(1000)
            
            for bot in paper_bots:
                # Calculate performance metrics
                win_rate = bot.get('win_rate', 0)
                max_drawdown = bot.get('max_drawdown', 100)
                trades_count = bot.get('trades_count', 0)
                
                # Promotion criteria
                meets_criteria = (
                    win_rate >= 60 and
                    max_drawdown <= 10 and
                    trades_count >= 20
                )
                
                if meets_criteria:
                    # Check if user has R1000+ balance
                    user_id = bot['user_id']
                    # In production, check actual Luno/exchange balance
                    # For now, check if initial capital >= 1000
                    
                    if bot.get('initial_capital', 0) >= 1000:
                        await self.promote_to_live(bot)
                    else:
                        logger.info(f"Bot {bot['id']}: Meets criteria but insufficient capital")
                        
        except Exception as e:
            logger.error(f"Paper bot promotion check error: {e}")
            
    async def promote_to_live(self, bot: dict):
        """Promote paper trading bot to live trading"""
        try:
            await self.db.bots.update_one(
                {'id': bot['id']},
                {'$set': {
                    'trading_mode': 'live',
                    'promoted_to_live': True
                }}
            )
            
            # Create alert
            await self.db.alerts.insert_one({
                'user_id': bot['user_id'],
                'bot_id': bot['id'],
                'type': 'autopilot',
                'severity': 'medium',
                'message': f"🎉 Bot '{bot['name']}' promoted to LIVE trading! Win rate: {bot['win_rate']}%",
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'dismissed': False
            })
            
            logger.info(f"Promoted bot {bot['id']} to live trading")
            
        except Exception as e:
            logger.error(f"Bot promotion error: {e}")
            
    async def get_best_performing_exchange(self, user_id: str, exchanges: list) -> str:
        """Get the exchange with best bot performance"""
        try:
            exchange_performance = {}
            
            for exchange in exchanges:
                bots = await self.db.bots.find({
                    'user_id': user_id,
                    'exchange': exchange
                }).to_list(100)
                
                if bots:
                    avg_win_rate = sum(b.get('win_rate', 0) for b in bots) / len(bots)
                    exchange_performance[exchange] = avg_win_rate
                    
            if exchange_performance:
                return max(exchange_performance, key=exchange_performance.get)
            else:
                return exchanges[0]  # Default to first available
                
        except Exception as e:
            logger.error(f"Exchange performance calculation error: {e}")
            return exchanges[0] if exchanges else 'binance'
            
    async def optimize_strategies(self):
        """Optimize bot strategies based on market conditions"""
        try:
            logger.info("🔧 Running strategy optimization...")
            
            # Get all active bots
            bots = await self.db.bots.find({'status': 'active'}).to_list(10000)
            
            for bot in bots:
                # Analyze recent performance
                trades = await self.db.trades.find({
                    'bot_id': bot['id']
                }).sort('timestamp', -1).limit(50).to_list(50)
                
                if len(trades) < 10:
                    continue
                    
                # Calculate metrics
                recent_win_rate = sum(1 for t in trades if t.get('profit_loss', 0) > 0) / len(trades) * 100
                
                # Adjust risk if underperforming
                if recent_win_rate < 40:
                    # Reduce risk
                    new_stop_loss = min(bot.get('stop_loss_percent', 15) - 2, 20)
                    await self.db.bots.update_one(
                        {'id': bot['id']},
                        {'$set': {'stop_loss_percent': new_stop_loss}}
                    )
                    logger.info(f"Bot {bot['id']}: Reduced risk (win rate: {recent_win_rate:.1f}%)")
                    
        except Exception as e:
            logger.error(f"Strategy optimization error: {e}")
    
    async def hourly_evolution_cycle(self):
        """Hourly genetic evolution of bot population"""
        try:
            from bot_dna_evolution import bot_dna_evolution
            import config
            
            logger.info("🧬 Starting hourly evolution cycle...")
            
            # Get all users with autopilot enabled
            users = await self.db.users.find({'autopilot_enabled': True}).to_list(1000)
            
            for user in users:
                user_id = user['id']
                
                # Get user's bots
                bots = await self.db.bots.find({
                    'user_id': user_id,
                    'status': 'active'
                }).to_list(1000)
                
                # Need minimum bots for evolution
                if len(bots) < 10:
                    logger.info(f"User {user_id}: Insufficient bots for evolution (need 10+, have {len(bots)})")
                    continue
                
                # Run evolution
                result = await bot_dna_evolution.evolve_bots(user_id)
                
                if result.get('evolved', 0) > 0:
                    logger.info(f"User {user_id}: Evolved {result['evolved']} bots (Generation {result.get('generation', 0)})")
                    
                    # Create alert
                    await self.db.alerts.insert_one({
                        'user_id': user_id,
                        'type': 'evolution',
                        'severity': 'low',
                        'message': f"Evolution complete: {result['evolved']} bots optimized (Gen {result.get('generation', 0)})",
                        'timestamp': datetime.now(timezone.utc).isoformat(),
                        'dismissed': False
                    })
                
            logger.info("🧬 Evolution cycle complete")
            
        except Exception as e:
            logger.error(f"Evolution cycle error: {e}")
            
    async def stop(self):
        """Stop the autopilot engine - async, never raises"""
        try:
            self.running = False
            if self.scheduler is not None and self.scheduler.running:
                try:
                    self.scheduler.shutdown(wait=False)
                    logger.info("🤖 Autopilot Engine stopped")
                except Exception as scheduler_error:
                    # Explicitly catch SchedulerNotRunningError and any other scheduler issues
                    logger.warning(f"Scheduler shutdown warning (ignored): {scheduler_error}")
            else:
                logger.info("🤖 Autopilot Engine already stopped or not running")
        except Exception as e:
            # Never let shutdown crash the process
            logger.error(f"Error stopping Autopilot Engine (non-fatal): {e}")

# Global instance
autopilot = AutopilotEngine()
