"""
Email Scheduler - Send automated daily reports
Runs twice daily: 8 AM and 6 PM
Uses enhanced email service with professional templates
"""
import asyncio
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from datetime import datetime, timezone, timedelta
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from services.enhanced_email_service import enhanced_email_service
from core.settings import FeatureFlags

logger = logging.getLogger(__name__)

class EmailScheduler:
    def __init__(self):
        self.scheduler = AsyncIOScheduler()
        self.db = None
        
    async def init_db(self):
        """Initialize database connection"""
        mongo_url = os.getenv('MONGO_URL', 'mongodb://localhost:27017')
        db_name = os.getenv('DB_NAME', 'amarktai_trading')
        client = AsyncIOMotorClient(mongo_url)
        self.db = client[db_name]
        
    async def start(self):
        """Start email scheduler"""
        await self.init_db()
        
        # Schedule morning report at 8 AM
        self.scheduler.add_job(
            self.send_morning_reports,
            trigger='cron',
            hour=8,
            minute=0,
            timezone='Africa/Johannesburg',
            id='morning_report'
        )
        
        # Schedule evening report at 6 PM
        self.scheduler.add_job(
            self.send_evening_reports,
            trigger='cron',
            hour=18,
            minute=0,
            timezone='Africa/Johannesburg',
            id='evening_report'
        )
        
        self.scheduler.start()
        logger.info("📧 Email Scheduler started - Reports at 8 AM and 6 PM")
        
    async def send_morning_reports(self):
        """Send morning reports to all active users"""
        try:
            logger.info("📧 Sending morning reports...")
            users = await self.db.users.find({'blocked': {'$ne': True}}, {'_id': 0}).to_list(1000)
            
            for user in users:
                try:
                    stats = await self.calculate_daily_stats(user['id'])
                    await self.send_daily_report_email(
                        user['email'],
                        user.get('first_name', 'Trader'),
                        stats,
                        'morning'
                    )
                except Exception as e:
                    logger.error(f"Failed to send morning report to {user['email']}: {e}")
                    
            logger.info(f"✅ Morning reports sent to {len(users)} users")
            
        except Exception as e:
            logger.error(f"Morning report batch error: {e}")
            
    async def send_evening_reports(self):
        """Send evening reports to all active users"""
        try:
            logger.info("📧 Sending evening reports...")
            users = await self.db.users.find({'blocked': {'$ne': True}}, {'_id': 0}).to_list(1000)
            
            for user in users:
                try:
                    stats = await self.calculate_daily_stats(user['id'])
                    await self.send_daily_report_email(
                        user['email'],
                        user.get('first_name', 'Trader'),
                        stats,
                        'evening'
                    )
                except Exception as e:
                    logger.error(f"Failed to send evening report to {user['email']}: {e}")
                    
            logger.info(f"✅ Evening reports sent to {len(users)} users")
            
        except Exception as e:
            logger.error(f"Evening report batch error: {e}")
            
    async def calculate_daily_stats(self, user_id: str) -> dict:
        """Calculate today's trading statistics"""
        try:
            # Get today's start time
            today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0).isoformat()
            
            # Get today's trades
            trades = await self.db.trades.find({
                'user_id': user_id,
                'timestamp': {'$gte': today_start}
            }).to_list(10000)
            
            # Get all user bots
            bots = await self.db.bots.find({'user_id': user_id}, {'_id': 0}).to_list(1000)
            
            # Calculate stats
            total_trades = len(trades)
            winning_trades = sum(1 for t in trades if t.get('profit_loss', 0) > 0)
            losing_trades = total_trades - winning_trades
            win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
            
            total_profit = sum(t.get('profit_loss', 0) for t in trades)
            total_volume = sum(t.get('amount', 0) * t.get('price', 0) for t in trades)
            
            active_bots = sum(1 for b in bots if b.get('status') == 'active')
            total_bots = len(bots)
            
            # Best performing bot
            bot_profits = {}
            for trade in trades:
                bot_id = trade.get('bot_id')
                if bot_id:
                    bot_profits[bot_id] = bot_profits.get(bot_id, 0) + trade.get('profit_loss', 0)
            
            best_bot = None
            best_profit = 0
            if bot_profits:
                best_bot_id = max(bot_profits, key=bot_profits.get)
                best_profit = bot_profits[best_bot_id]
                bot_doc = await self.db.bots.find_one({'id': best_bot_id}, {'_id': 0})
                if bot_doc:
                    best_bot = bot_doc.get('name', 'Unknown')
            
            return {
                'user_id': user_id,
                'total_trades': total_trades,
                'winning_trades': winning_trades,
                'losing_trades': losing_trades,
                'win_rate': win_rate,
                'total_profit': total_profit,
                'total_volume': total_volume,
                'active_bots': active_bots,
                'total_bots': total_bots,
                'best_bot': best_bot,
                'best_bot_profit': best_profit
            }
            
        except Exception as e:
            logger.error(f"Error calculating stats for {user_id}: {e}")
            return {
                'user_id': user_id,
                'total_trades': 0,
                'winning_trades': 0,
                'losing_trades': 0,
                'win_rate': 0,
                'total_profit': 0,
                'total_volume': 0,
                'active_bots': 0,
                'total_bots': 0,
                'best_bot': None,
                'best_bot_profit': 0
            }
            
    async def send_daily_report_email(self, to_email: str, first_name: str, stats: dict, period: str):
        """Send comprehensive daily report email using enhanced email service"""
        
        # Check if email reports are enabled
        if not FeatureFlags.ENABLE_EMAIL_REPORTS:
            logger.debug(f"Email reports disabled, skipping report for {to_email}")
            return False
        
        if not enhanced_email_service.enabled:
            logger.warning(f"Enhanced email service not configured, skipping report for {to_email}")
            return False
        
        # Get exchange breakdown (calculate per-exchange stats)
        exchange_breakdown = await self.calculate_exchange_breakdown(stats.get('user_id', ''))
        
        # Get top performers
        top_performers = await self.get_top_performers(stats.get('user_id', ''))
        
        # Calculate weekly and monthly profits
        weekly_profit = await self.calculate_period_profit(stats.get('user_id', ''), days=7)
        monthly_profit = await self.calculate_period_profit(stats.get('user_id', ''), days=30)
        
        # Prepare report data for enhanced template
        report_data = {
            'date': datetime.now(timezone.utc).strftime('%B %d, %Y'),
            'total_profit': stats.get('cumulative_profit', stats.get('total_profit', 0)),
            'daily_profit': stats.get('total_profit', 0),
            'weekly_profit': weekly_profit,
            'monthly_profit': monthly_profit,
            'trades_today': stats.get('total_trades', 0),
            'win_rate': stats.get('win_rate', 0),
            'active_bots': stats.get('active_bots', 0),
            'exchange_breakdown': exchange_breakdown,
            'top_performers': top_performers
        }
        
        try:
            success = await enhanced_email_service.send_daily_report(to_email, report_data)
            if success:
                logger.info(f"✅ Enhanced daily report sent to {to_email}")
            return success
        except Exception as e:
            logger.error(f"Failed to send enhanced daily report to {to_email}: {e}")
            return False
    
    async def calculate_exchange_breakdown(self, user_id: str) -> dict:
        """Calculate per-exchange trading stats"""
        try:
            today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0).isoformat()
            
            trades = await self.db.trades.find({
                'user_id': user_id,
                'timestamp': {'$gte': today_start}
            }).to_list(10000)
            
            breakdown = {}
            for trade in trades:
                exchange = trade.get('exchange', 'unknown').lower()
                if exchange not in breakdown:
                    breakdown[exchange] = {'profit': 0, 'trades': 0}
                
                breakdown[exchange]['profit'] += trade.get('profit_loss', 0)
                breakdown[exchange]['trades'] += 1
            
            return breakdown
        except Exception as e:
            logger.error(f"Error calculating exchange breakdown: {e}")
            return {}
    
    async def get_top_performers(self, user_id: str, limit: int = 3) -> list:
        """Get top performing bots"""
        try:
            today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0).isoformat()
            
            trades = await self.db.trades.find({
                'user_id': user_id,
                'timestamp': {'$gte': today_start}
            }).to_list(10000)
            
            # Calculate per-bot profits
            bot_stats = {}
            for trade in trades:
                bot_id = trade.get('bot_id')
                if not bot_id:
                    continue
                
                if bot_id not in bot_stats:
                    bot_stats[bot_id] = {
                        'profit': 0,
                        'trades': 0,
                        'wins': 0
                    }
                
                profit = trade.get('profit_loss', 0)
                bot_stats[bot_id]['profit'] += profit
                bot_stats[bot_id]['trades'] += 1
                if profit > 0:
                    bot_stats[bot_id]['wins'] += 1
            
            # Get bot details and calculate win rates
            top_bots = []
            for bot_id, stats in sorted(bot_stats.items(), key=lambda x: x[1]['profit'], reverse=True)[:limit]:
                bot_doc = await self.db.bots.find_one({'id': bot_id}, {'_id': 0})
                if bot_doc:
                    win_rate = (stats['wins'] / stats['trades'] * 100) if stats['trades'] > 0 else 0
                    top_bots.append({
                        'name': bot_doc.get('name', 'Unknown'),
                        'profit': stats['profit'],
                        'exchange': bot_doc.get('exchange', 'unknown'),
                        'win_rate': win_rate
                    })
            
            return top_bots
        except Exception as e:
            logger.error(f"Error getting top performers: {e}")
            return []
    
    async def calculate_period_profit(self, user_id: str, days: int) -> float:
        """Calculate profit for a specific period"""
        try:
            start_date = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
            
            trades = await self.db.trades.find({
                'user_id': user_id,
                'timestamp': {'$gte': start_date}
            }).to_list(10000)
            
            return sum(t.get('profit_loss', 0) for t in trades)
        except Exception as e:
            logger.error(f"Error calculating period profit: {e}")
            return 0.0
            
    def stop(self):
        """Stop the scheduler"""
        self.scheduler.shutdown()
        logger.info("Email Scheduler stopped")

# Global instance
email_scheduler = EmailScheduler()
