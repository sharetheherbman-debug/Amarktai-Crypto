"""
AI Bodyguard - Continuous System Monitoring
- Monitors every 5 minutes for anomalies
- Detects extreme drawdowns (>15% in 1 hour)
- Identifies rogue bot behavior
- Auto-pauses suspicious bots
- Self-healing capabilities
"""

import asyncio
from datetime import datetime, timezone, timedelta
import logging
import os

logger = logging.getLogger(__name__)

class AIBodyguard:
    def __init__(self):
        self.db = None
        self.monitoring = False
        self.check_interval = 300  # 5 minutes in seconds
        
    async def init_db(self):
        """Initialize database connection"""
        import database

        if database.db is None:
            await database.connect()
        self.db = database.db
        
    async def start(self):
        """Start continuous monitoring"""
        await self.init_db()
        self.monitoring = True
        logger.info("🛡️ AI Bodyguard started - monitoring every 5 minutes")
        
        while self.monitoring:
            try:
                await self.monitor_all_systems()
                await asyncio.sleep(self.check_interval)
            except Exception as e:
                logger.error(f"Bodyguard monitoring error: {e}")
                await asyncio.sleep(60)  # Wait 1 min on error
                
    async def monitor_all_systems(self):
        """Main monitoring loop"""
        try:
            # Get all users
            users = await self.db.users.find({}).to_list(1000)
            
            for user in users:
                if user.get('emergency_stop', False):
                    continue  # Skip users with emergency stop
                    
                user_id = user['id']
                await self.check_user_bots(user_id)
                await self.check_system_health(user_id)
                
        except Exception as e:
            logger.error(f"System monitoring error: {e}")
            
    async def check_user_bots(self, user_id: str):
        """Check all bots for a specific user"""
        try:
            # Use new bodyguard service for drawdown checks
            from services.bodyguard_service import bodyguard_service
            
            # Check all user bots with new recovery-aware service
            result = await bodyguard_service.check_all_user_bots(user_id)
            
            if result.get('paused', 0) > 0 or result.get('resumed', 0) > 0:
                logger.info(
                    f"Bodyguard checked {result.get('checked', 0)} bots for user {user_id[:8]}: "
                    f"{result.get('paused', 0)} paused, {result.get('resumed', 0)} resumed"
                )
            
            # Still run legacy checks for other patterns (not covered by new service)
            bots = await self.db.bots.find({'user_id': user_id, 'status': 'active'}).to_list(1000)
            
            for bot in bots:
                bot_id = bot['id']
                
                # Legacy checks (suspicious patterns, duplicates)
                await self.check_suspicious_patterns(user_id, bot_id, bot)
                await self.check_duplicate_bots(user_id, bot)
                
        except Exception as e:
            logger.error(f"Bot check error for user {user_id}: {e}")
            
    async def check_extreme_drawdown(self, user_id: str, bot_id: str, bot: dict):
        """Detect extreme drawdowns (>15% in 1 hour)"""
        try:
            # Get trades from last hour
            one_hour_ago = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
            
            recent_trades = await self.db.trades.find({
                'bot_id': bot_id,
                'timestamp': {'$gte': one_hour_ago}
            }).to_list(1000)
            
            if not recent_trades:
                return
                
            # Calculate hourly drawdown
            total_pnl = sum(trade.get('profit_loss', 0) for trade in recent_trades)
            initial_capital = bot.get('current_capital', 1000)
            drawdown_percent = abs(total_pnl / initial_capital * 100) if initial_capital > 0 else 0
            
            # Critical threshold: 15%
            if drawdown_percent > 15:
                await self.pause_bot_with_alert(
                    user_id, 
                    bot_id, 
                    'critical',
                    f"🚨 EXTREME DRAWDOWN: Bot '{bot['name']}' lost {drawdown_percent:.1f}% in 1 hour! Auto-paused for protection."
                )
                logger.warning(f"Bot {bot_id}: Extreme drawdown detected ({drawdown_percent:.1f}%)")
                
        except Exception as e:
            logger.error(f"Drawdown check error: {e}")
            
    async def check_risk_violation(self, user_id: str, bot_id: str, bot: dict):
        """Check if bot is violating its risk parameters"""
        try:
            # Check if bot exceeded its stop-loss
            max_drawdown = bot.get('max_drawdown', 0)
            stop_loss = bot.get('stop_loss_percent', 15)
            
            if max_drawdown > stop_loss:
                await self.pause_bot_with_alert(
                    user_id,
                    bot_id,
                    'high',
                    f"⚠️ Risk Violation: Bot '{bot['name']}' exceeded stop-loss ({max_drawdown:.1f}% > {stop_loss}%). Paused."
                )
                logger.warning(f"Bot {bot_id}: Risk violation (drawdown {max_drawdown:.1f}%)")
                
        except Exception as e:
            logger.error(f"Risk check error: {e}")
            
    async def check_suspicious_patterns(self, user_id: str, bot_id: str, bot: dict):
        """Detect suspicious trading patterns"""
        try:
            # Get recent trades
            recent_trades = await self.db.trades.find({
                'bot_id': bot_id
            }).sort('timestamp', -1).limit(20).to_list(20)
            
            if len(recent_trades) < 10:
                return
                
            # Pattern 1: All trades are losses
            all_losses = all(trade.get('profit_loss', 0) <= 0 for trade in recent_trades[:10])
            
            if all_losses:
                await self.pause_bot_with_alert(
                    user_id,
                    bot_id,
                    'high',
                    f"🔍 Suspicious Pattern: Bot '{bot['name']}' has 10 consecutive losses. Reviewing strategy."
                )
                logger.warning(f"Bot {bot_id}: Suspicious pattern - consecutive losses")
                
            # Pattern 2: Extremely high trade frequency (> 100 trades/hour)
            one_hour_ago = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
            hourly_trades = await self.db.trades.count_documents({
                'bot_id': bot_id,
                'timestamp': {'$gte': one_hour_ago}
            })
            
            if hourly_trades > 100:
                await self.pause_bot_with_alert(
                    user_id,
                    bot_id,
                    'medium',
                    f"⚡ High Frequency Detected: Bot '{bot['name']}' executed {hourly_trades} trades in 1 hour. Possible runaway bot."
                )
                logger.warning(f"Bot {bot_id}: High frequency trading detected")
                
        except Exception as e:
            logger.error(f"Pattern check error: {e}")
            
    async def check_duplicate_bots(self, user_id: str, bot: dict):
        """Detect duplicate bots (same config running multiple times)"""
        try:
            # Find bots with same exchange and risk mode
            similar_bots = await self.db.bots.find({
                'user_id': user_id,
                'exchange': bot['exchange'],
                'risk_mode': bot['risk_mode'],
                'status': 'active'
            }).to_list(100)
            
            # If more than 5 identical bots, flag as suspicious
            if len(similar_bots) > 5:
                await self.create_alert(
                    user_id,
                    None,
                    'medium',
                    f"⚠️ Duplicate Detection: You have {len(similar_bots)} similar bots on {bot['exchange']}. Consider consolidating."
                )
                
        except Exception as e:
            logger.error(f"Duplicate check error: {e}")
            
    async def check_system_health(self, user_id: str):
        """Check overall system health for user"""
        try:
            # Check daily loss limit - support MAX_DAILY_LOSS_PERCENT env var
            # MAX_DAILY_LOSS_PERCENT can be either decimal (0.15 = 15%) or percentage (15 = 15%)
            max_daily_loss_env = os.getenv('MAX_DAILY_LOSS_PERCENT', '0.15')
            max_daily_loss = float(max_daily_loss_env)
            # If value is < 1, treat as decimal (0.15 = 15%), otherwise treat as percentage (15 = 15%)
            if max_daily_loss < 1:
                max_daily_loss = max_daily_loss * 100  # Convert decimal to percentage
            
            today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0).isoformat()
            
            today_trades = await self.db.trades.find({
                'user_id': user_id,
                'timestamp': {'$gte': today_start}
            }).to_list(10000)
            
            if today_trades:
                daily_pnl = sum(trade.get('profit_loss', 0) for trade in today_trades)
                
                # Get total capital
                bots = await self.db.bots.find({'user_id': user_id}).to_list(1000)
                total_capital = sum(bot.get('current_capital', 0) for bot in bots)
                
                if total_capital > 0:
                    daily_loss_percent = abs(daily_pnl / total_capital * 100)
                    
                    if daily_loss_percent >= max_daily_loss:
                        # Pause all bots
                        await self.db.bots.update_many(
                            {'user_id': user_id},
                            {'$set': {'status': 'paused'}}
                        )
                        
                        await self.create_alert(
                            user_id,
                            None,
                            'critical',
                            f"🚨 DAILY LOSS LIMIT TRIGGERED\n\n"
                            f"Limit: Daily loss exceeds {max_daily_loss:.1f}%\n"
                            f"Current Daily P&L: {daily_pnl:.2f} ZAR ({daily_loss_percent:.1f}%)\n"
                            f"Daily Loss Threshold: {max_daily_loss:.1f}% of total capital\n\n"
                            f"Action Taken: All bots have been paused for protection.\n"
                            f"Next Steps: Contact admin to review trading strategy and reset lock."
                        )
                        logger.critical(f"User {user_id}: Daily loss limit triggered")
                        
        except Exception as e:
            logger.error(f"System health check error: {e}")
            
    async def pause_bot_with_alert(self, user_id: str, bot_id: str, severity: str, message: str):
        """Pause a bot and create an alert"""
        try:
            # Pause the bot
            await self.db.bots.update_one(
                {'id': bot_id},
                {'$set': {'status': 'paused'}}
            )
            
            # Create alert
            await self.create_alert(user_id, bot_id, severity, message)
            
        except Exception as e:
            logger.error(f"Pause bot error: {e}")
            
    async def create_alert(self, user_id: str, bot_id: str, severity: str, message: str):
        """Create an alert in the database"""
        try:
            alert = {
                'user_id': user_id,
                'bot_id': bot_id,
                'type': 'bodyguard',
                'severity': severity,
                'message': message,
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'dismissed': False
            }
            
            await self.db.alerts.insert_one(alert)
            logger.info(f"Alert created: {message}")
            
        except Exception as e:
            logger.error(f"Alert creation error: {e}")
            
    async def self_heal(self):
        """Self-healing capabilities"""
        try:
            # Check if backend is responsive
            # In production, this would check health endpoints, restart services, etc.
            logger.info("🔧 Running self-healing checks...")
            
            # Example: Check database connection
            try:
                await self.db.users.count_documents({})
                logger.info("✅ Database connection healthy")
            except Exception as e:
                logger.error(f"❌ Database connection issue: {e}")
                # In production: attempt reconnection, send alerts
                
        except Exception as e:
            logger.error(f"Self-healing error: {e}")
            
    def stop(self):
        """Stop monitoring"""
        self.monitoring = False
        logger.info("AI Bodyguard stopped")

# Global instance
bodyguard = AIBodyguard()
