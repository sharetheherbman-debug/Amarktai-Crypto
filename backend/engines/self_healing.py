"""
Self-Healing System
Detects and fixes rogue bots and system issues automatically
"""
import asyncio
from datetime import datetime, timezone, timedelta
import database as db
from logger_config import logger
from config import MAX_HOURLY_LOSS_PERCENT, MAX_DRAWDOWN_PERCENT, EXCHANGE_TRADE_LIMITS


class SelfHealingSystem:
    def __init__(self):
        self.is_running = False
        self.last_result = "idle"
        self.task = None
        self.detection_rules = [
            self.detect_excessive_loss,
            self.detect_stuck_bot,
            self.detect_abnormal_trading,
            self.detect_capital_anomaly
        ]
    
    async def detect_excessive_loss(self, bot: dict) -> tuple[bool, str]:
        """Detect if bot lost >15% in 1 hour"""
        try:
            bot_id = bot['id']
            one_hour_ago = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
            
            # Get trades in last hour
            recent_trades = await db.trades_collection.find({
                "bot_id": bot_id,
                "timestamp": {"$gte": one_hour_ago}
            }, {"_id": 0}).to_list(1000)
            
            if not recent_trades:
                return False, "OK"
            
            # Calculate hourly loss
            hourly_loss = sum(t.get('profit_loss', 0) for t in recent_trades)
            current_capital = bot.get('current_capital', 1000)
            loss_percent = abs(hourly_loss / current_capital) if current_capital > 0 else 0
            
            if hourly_loss < 0 and loss_percent > MAX_HOURLY_LOSS_PERCENT:
                return True, f"🚨 Excessive loss: {loss_percent*100:.1f}% in 1 hour"
            
            return False, "OK"
        
        except Exception as e:
            logger.error(f"Detect excessive loss error: {e}", exc_info=True)
            return False, "Error"
    
    async def detect_stuck_bot(self, bot: dict) -> tuple[bool, str]:
        """Detect if bot hasn't traded in 24 hours despite being active - ROBUST timezone handling"""
        try:
            if bot.get('status') != 'active':
                return False, "OK"
            
            last_trade = bot.get('last_trade_time')
            if not last_trade:
                # New bot, give it 24 hours
                created = bot.get('created_at')
                if created:
                    try:
                        # Handle both timezone-aware and naive datetime strings
                        if isinstance(created, str):
                            # Try parsing with Z suffix first
                            if created.endswith('Z'):
                                created_dt = datetime.fromisoformat(created.replace('Z', '+00:00'))
                            else:
                                created_dt = datetime.fromisoformat(created)
                                # If naive, assume UTC
                                if created_dt.tzinfo is None:
                                    created_dt = created_dt.replace(tzinfo=timezone.utc)
                        elif isinstance(created, datetime):
                            created_dt = created
                            if created_dt.tzinfo is None:
                                created_dt = created_dt.replace(tzinfo=timezone.utc)
                        else:
                            return False, "OK"  # Unknown format, skip check
                            
                        hours_since_created = (datetime.now(timezone.utc) - created_dt).total_seconds() / 3600
                        if hours_since_created > 24:
                            return True, "🚨 Bot stuck: No trades in 24 hours since creation"
                    except (ValueError, TypeError) as e:
                        logger.warning(f"Date parsing error in detect_stuck_bot: {e}")
                        return False, "OK"  # Skip check on parse errors
                return False, "OK"
            
            try:
                # Handle both string and datetime types with timezone awareness
                if isinstance(last_trade, str):
                    if last_trade.endswith('Z'):
                        last_trade_dt = datetime.fromisoformat(last_trade.replace('Z', '+00:00'))
                    else:
                        last_trade_dt = datetime.fromisoformat(last_trade)
                        if last_trade_dt.tzinfo is None:
                            last_trade_dt = last_trade_dt.replace(tzinfo=timezone.utc)
                elif isinstance(last_trade, datetime):
                    last_trade_dt = last_trade
                    if last_trade_dt.tzinfo is None:
                        last_trade_dt = last_trade_dt.replace(tzinfo=timezone.utc)
                else:
                    return False, "OK"  # Unknown type, skip check
                
                hours_since_trade = (datetime.now(timezone.utc) - last_trade_dt).total_seconds() / 3600
                
                if hours_since_trade > 24:
                    return True, f"🚨 Bot stuck: No trades in {hours_since_trade:.1f} hours"
                
                return False, "OK"
            except (ValueError, TypeError) as e:
                logger.warning(f"Date parsing error for last_trade_time: {e}")
                return False, "OK"  # Skip check on parse errors
        
        except Exception as e:
            logger.error(f"Detect stuck bot error: {e}", exc_info=True)
            return False, "Error"
    
    async def detect_abnormal_trading(self, bot: dict) -> tuple[bool, str]:
        """Detect abnormal trading patterns (too many trades)"""
        try:
            daily_count = bot.get('daily_trade_count', 0)
            exchange = bot.get('exchange', 'binance').lower()
            
            # Use exchange-specific limit from config (imported at module level)
            limits = EXCHANGE_TRADE_LIMITS.get(exchange, EXCHANGE_TRADE_LIMITS.get('binance', {}))
            abnormal_limit = limits.get('max_trades_per_bot_per_day', 400)
            
            # Check if bot is trying to exceed daily limit
            if daily_count >= abnormal_limit:
                return True, f"🚨 Abnormal trading: {daily_count} trades today (limit: {abnormal_limit})"
            
            return False, "OK"
        
        except Exception as e:
            logger.error(f"Detect abnormal trading error: {e}", exc_info=True)
            return False, "Error"
    
    async def detect_capital_anomaly(self, bot: dict) -> tuple[bool, str]:
        """Detect if capital dropped below critical threshold.

        Only fires when the bot has at least one completed trade — a brand-new
        bot (trades_count == 0) cannot have suffered a real trading loss, so any
        current_capital < initial_capital on such a bot is a data artefact (e.g.
        from a previous buggy allocator run) and must not trigger a pause.
        """
        try:
            initial_capital = bot.get('initial_capital', 1000)
            current_capital = bot.get('current_capital', 1000)

            loss_percent = 1 - (current_capital / initial_capital) if initial_capital > 0 else 0

            if loss_percent > MAX_DRAWDOWN_PERCENT:
                # Guard: a bot with zero trades cannot have a real drawdown.
                trades_count = bot.get('trades_count', 0) or 0
                if trades_count == 0:
                    logger.debug(
                        f"Suppressed false capital anomaly for {bot.get('name')} — "
                        f"no trades yet, current_capital={current_capital} vs "
                        f"initial_capital={initial_capital} (data artefact)"
                    )
                    return False, "OK"
                return True, f"🚨 Capital anomaly: {loss_percent*100:.1f}% drawdown"

            return False, "OK"

        except Exception as e:
            logger.error(f"Detect capital anomaly error: {e}", exc_info=True)
            return False, "Error"
    
    async def fix_rogue_bot(self, bot: dict, issue: str) -> bool:
        """Automatically fix rogue bot"""
        try:
            bot_id = bot['id']
            bot_name = bot.get('name', 'Unknown')
            
            # Pause the bot
            await db.bots_collection.update_one(
                {"id": bot_id},
                {"$set": {
                    "status": "paused",
                    "rogue_detected_at": datetime.now(timezone.utc).isoformat(),
                    "rogue_reason": issue
                }}
            )
            
            logger.warning(f"🛡️ Self-Healing: Paused rogue bot '{bot_name}' - {issue}")
            
            # Send WebSocket notification
            try:
                from websocket_manager import manager
                await manager.send_message(bot['user_id'], {
                    "type": "rogue_bot_detected",
                    "bot_name": bot_name,
                    "issue": issue
                })
            except:
                pass
            
            return True
        
        except Exception as e:
            logger.error(f"Fix rogue bot error: {e}")
            return False
    
    async def scan_all_bots(self):
        """Scan all active bots for issues - NEVER crash the system"""
        try:
            bots = await db.bots_collection.find({"status": "active"}, {"_id": 0}).to_list(1000)
            
            rogue_count = 0
            
            for bot in bots:
                try:
                    # Run all detection rules
                    for detection_rule in self.detection_rules:
                        is_rogue, issue = await detection_rule(bot)
                        
                        if is_rogue:
                            logger.warning(f"⚠️ Rogue bot detected: {bot.get('name')} - {issue}")
                            
                            # Auto-fix
                            if await self.fix_rogue_bot(bot, issue):
                                rogue_count += 1
                            
                            break  # Stop checking other rules for this bot
                except Exception as bot_error:
                    logger.error(f"Error scanning bot {bot.get('id', 'unknown')}: {bot_error}", exc_info=True)
                    continue  # Continue with next bot
            
            if rogue_count > 0:
                logger.info(f"🛡️ Self-Healing: Fixed {rogue_count} rogue bots")
        
            # Record timestamp of successful scan completion so get_status() can
            # return a truthful last_check and last_result to the UI.
            self.last_check = datetime.now(timezone.utc)
            self.last_result = f"scanned_ok:{len(bots)}_bots_{rogue_count}_fixed"

        except Exception as e:
            logger.error(f"Scan all bots error: {e}", exc_info=True)
            # Never crash - log and continue
            self.last_check = datetime.now(timezone.utc)
            self.last_result = f"scan_error:{str(e)[:80]}"
    
    async def scan_all_users(self):
        """
        Scan all users and their bots for issues - wrapper for daily scheduler
        NEVER crash the system - catches all exceptions
        """
        try:
            logger.info("🛡️ Starting daily self-healing scan for all users")
            
            # Get all users
            users = await db.users_collection.find({}, {"_id": 0, "id": 1}).to_list(1000)
            
            scanned_users = 0
            total_issues_fixed = 0
            
            for user in users:
                try:
                    user_id = user.get('id')
                    if not user_id:
                        continue
                    
                    # Get user's active bots
                    bots = await db.bots_collection.find(
                        {"user_id": user_id, "status": "active"},
                        {"_id": 0}
                    ).to_list(1000)
                    
                    user_issues_fixed = 0
                    
                    for bot in bots:
                        try:
                            # Run all detection rules
                            for detection_rule in self.detection_rules:
                                is_rogue, issue = await detection_rule(bot)
                                
                                if is_rogue:
                                    logger.warning(f"⚠️ Rogue bot detected: {bot.get('name')} (user {user_id}) - {issue}")
                                    
                                    # Auto-fix
                                    if await self.fix_rogue_bot(bot, issue):
                                        user_issues_fixed += 1
                                    
                                    break  # Stop checking other rules for this bot
                        except Exception as bot_error:
                            logger.error(f"Error scanning bot {bot.get('id', 'unknown')} for user {user_id}: {bot_error}")
                            continue  # Continue with next bot
                    
                    if user_issues_fixed > 0:
                        logger.info(f"🛡️ Self-Healing: Fixed {user_issues_fixed} issues for user {user_id}")
                        total_issues_fixed += user_issues_fixed
                    
                    scanned_users += 1
                    
                except Exception as user_error:
                    logger.error(f"Error scanning user {user.get('id', 'unknown')}: {user_error}")
                    continue  # Continue with next user
            
            logger.info(f"✅ Daily self-healing scan complete: {scanned_users} users scanned, {total_issues_fixed} issues fixed")
            
        except Exception as e:
            logger.error(f"Scan all users error: {e}", exc_info=True)
            # Never crash - log and continue
    
    async def healing_loop(self):
        """Main self-healing loop - runs every 30 minutes - NEVER crash"""
        logger.info("🛡️ Self-Healing system started")
        
        while self.is_running:
            try:
                await self.scan_all_bots()
                
                # Wait 30 minutes
                await asyncio.sleep(1800)
            
            except asyncio.CancelledError:
                logger.info("🛡️ Self-Healing system cancelled")
                break
            except Exception as e:
                logger.error(f"Healing loop error: {e}", exc_info=True)
                await asyncio.sleep(300)  # Wait 5 minutes on error, then retry
    
    async def start(self):
        """Start self-healing system (async-compatible)."""
        if not self.is_running:
            self.is_running = True
            self._was_started = True
            self.last_started_at = datetime.now(timezone.utc)
            self.task = asyncio.create_task(self.healing_loop())
            logger.info("✅ Self-Healing system started")
    
    async def stop(self):
        """Stop self-healing system (async-compatible)."""
        self.is_running = False
        self.last_result = "stopped"
        if self.task:
            self.task.cancel()
        logger.info("⏹️ Self-Healing system stopped")

    def get_status(self) -> dict:
        """Return canonical self-healing runtime status.

        State semantics:
          - running:  actively monitoring systems (is_running=True)
          - stopped:  was running, now stopped (_was_started=True or last_result="stopped")
          - idle:     initialized but not yet started
          - disabled: not started / service unavailable
        """
        if self.is_running:
            state = "running"
        elif getattr(self, "_was_started", False) or getattr(self, "last_result", None) == "stopped":
            state = "stopped"
        else:
            state = "idle"
        last_check = getattr(self, "last_check", None)
        last_started_at = getattr(self, "last_started_at", None)
        # Determine last_action without a nested ternary for readability
        if self.is_running:
            _last_action = "healing_loop"
        elif state == "stopped":
            _last_action = "stop"
        else:
            _last_action = "initialized"
        return {
            "enabled": self.is_running,
            "state": state,
            "last_check": last_check.isoformat() if last_check else None,
            "last_started_at": last_started_at.isoformat() if last_started_at else None,
            "last_action": _last_action,
            "last_result": self.last_result,
            "last_reason_code": "RUNNING" if self.is_running else "IDLE",
            "last_error": None,
            "monitored_systems": ["bots", "capital", "trading_patterns"],
            "recovery_attempts": {},
        }


self_healing = SelfHealingSystem()
