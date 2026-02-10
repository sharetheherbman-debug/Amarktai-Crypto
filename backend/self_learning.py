"""
Self-Learning System - Continuous Improvement
- Analyzes all trade outcomes daily
- Generates learning reports with insights
- Adjusts strategies based on market conditions
- Provides recommendations to users
"""

import asyncio
from datetime import datetime, timezone, timedelta
from ai_service import ai_service
import logging

logger = logging.getLogger(__name__)

class SelfLearningSystem:
    def __init__(self):
        self.db = None
        
    async def init_db(self):
        """Initialize database connection"""
        import database as db
        if db.db is None:
            await db.connect()
        self.db = db
        self.db.trades_collection = db.trades_collection
        self.db.bots_collection = db.bots_collection
        self.db.learning_logs_collection = db.learning_logs_collection
        self.db.alerts_collection = db.alerts_collection
        
    async def analyze_daily_trades(self, user_id: str):
        """Analyze yesterday's trades and generate learning report"""
        try:
            logger.info(f"📚 Analyzing trades for user {user_id}")
            
            # Get yesterday's trades
            yesterday_start = (datetime.now(timezone.utc) - timedelta(days=1)).replace(hour=0, minute=0, second=0)
            yesterday_end = yesterday_start + timedelta(days=1)
            
            trades = await self.db.trades_collection.find({
                'user_id': user_id,
                'timestamp': {
                    '$gte': yesterday_start.isoformat(),
                    '$lt': yesterday_end.isoformat()
                }
            }).to_list(10000)
            
            if not trades:
                logger.info(f"No trades to analyze for user {user_id}")
                return
                
            # Calculate key metrics
            insights = await self.calculate_insights(user_id, trades)
            
            # Generate AI learning report
            report = await ai_service.generate_learning_report(user_id, trades, insights)
            
            # Store learning data
            learning_data = {
                'user_id': user_id,
                'date': yesterday_start.isoformat(),
                'insights': [report],
                'market_conditions': insights.get('market_conditions', {}),
                'bot_performance': insights.get('bot_performance', {}),
                'strategy_adjustments': insights.get('strategy_adjustments', []),
                'daily_summary': report
            }
            
            await self.db.learning_data_collection.insert_one(learning_data)
            
            # ALSO store in new learning_logs collection
            await self.db.learning_logs_collection.insert_one({
                'user_id': user_id,
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'type': 'daily_analysis',
                'trades_analyzed': len(trades),
                'win_rate': insights.get('win_rate', 0),
                'total_profit': insights.get('total_pnl', 0),
                'insights': report,
                'recommendations': insights.get('strategy_adjustments', [])
            })
            
            # Create alert with learning report
            await self.db.alerts_collection.insert_one({
                'user_id': user_id,
                'type': 'learning',
                'severity': 'low',
                'message': f'📚 Daily Learning Report Ready: {report[:100]}...',
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'dismissed': False
            })
            
            logger.info(f"✅ Learning report generated for user {user_id}")
            
        except Exception as e:
            logger.error(f"Daily analysis error: {e}")
            
    async def calculate_insights(self, user_id: str, trades: list) -> dict:
        """Calculate performance insights from trades"""
        try:
            total_trades = len(trades)
            profitable_trades = sum(1 for t in trades if t.get('profit_loss', 0) > 0)
            total_pnl = sum(t.get('profit_loss', 0) for t in trades)
            
            # Win rate
            win_rate = (profitable_trades / total_trades * 100) if total_trades > 0 else 0
            
            # Best performing exchange
            exchange_performance = {}
            for trade in trades:
                exchange = trade.get('exchange', 'unknown')
                pnl = trade.get('profit_loss', 0)
                if exchange not in exchange_performance:
                    exchange_performance[exchange] = {'total': 0, 'count': 0}
                exchange_performance[exchange]['total'] += pnl
                exchange_performance[exchange]['count'] += 1
                
            best_exchange = max(exchange_performance.items(), 
                              key=lambda x: x[1]['total'])[0] if exchange_performance else 'none'
            
            # Optimal trade time analysis
            hour_performance = {}
            for trade in trades:
                try:
                    trade_time = datetime.fromisoformat(trade['timestamp'])
                    hour = trade_time.hour
                    pnl = trade.get('profit_loss', 0)
                    if hour not in hour_performance:
                        hour_performance[hour] = {'total': 0, 'count': 0}
                    hour_performance[hour]['total'] += pnl
                    hour_performance[hour]['count'] += 1
                except:
                    pass
                    
            best_hour = max(hour_performance.items(), 
                          key=lambda x: x[1]['total'])[0] if hour_performance else 12
            
            # Strategy adjustments
            adjustments = []
            
            if win_rate < 40:
                adjustments.append("Consider reducing position sizes - win rate below 40%")
            
            if total_pnl < 0:
                adjustments.append("Daily loss detected - review strategy parameters")
                
            # Market regime detection
            volatility = await self.detect_market_volatility()
            
            return {
                'total_trades': total_trades,
                'profitable_trades': profitable_trades,
                'total_pnl': total_pnl,
                'win_rate': win_rate,
                'best_exchange': best_exchange,
                'best_hour': best_hour,
                'strategy_adjustments': adjustments,
                'market_conditions': {
                    'volatility': volatility,
                    'regime': self.classify_market_regime(volatility)
                },
                'bot_performance': exchange_performance
            }
            
        except Exception as e:
            logger.error(f"Insight calculation error: {e}")
            return {}
            
    async def run_daily_learning(self, user_id: str) -> dict:
        """Run daily learning analysis on demand"""
        try:
            if not self.db:
                await self.db.init_db()
            
            await self.analyze_daily_trades(user_id)
            
            return {
                "success": True,
                "message": "📚 Daily learning analysis completed successfully"
            }
        except Exception as e:
            logger.error(f"Daily learning error: {e}")
            return {
                "success": False,
                "message": f"❌ Learning analysis failed: {str(e)}"
            }
    
    async def detect_market_volatility(self) -> str:
        """Detect market volatility level"""
        try:
            # In production, fetch real BTC price data
            # For now, simulate based on trade patterns
            recent_trades = await self.db.trades_collection.find({}).sort('timestamp', -1).limit(100).to_list(100)
            
            if len(recent_trades) < 10:
                return "normal"
                
            # Calculate price variation
            prices = [t.get('price', 0) for t in recent_trades if t.get('price', 0) > 0]
            if not prices:
                return "normal"
                
            avg_price = sum(prices) / len(prices)
            price_std = (sum((p - avg_price) ** 2 for p in prices) / len(prices)) ** 0.5
            volatility_percent = (price_std / avg_price * 100) if avg_price > 0 else 0
            
            if volatility_percent > 5:
                return "high"
            elif volatility_percent > 2:
                return "moderate"
            else:
                return "low"
                
        except Exception as e:
            logger.error(f"Volatility detection error: {e}")
            return "normal"
            
    def classify_market_regime(self, volatility: str) -> str:
        """Classify market regime based on volatility"""
        if volatility == "high":
            return "volatile"
        elif volatility == "low":
            return "stable"
        else:
            return "normal"
            
    async def adjust_strategies_based_on_learning(self, user_id: str):
        """Adjust bot strategies based on learning data"""
        try:
            # Get recent learning data (last 7 days)
            seven_days_ago = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
            
            learning_data = await self.db.learning_data_collection.find({
                'user_id': user_id,
                'date': {'$gte': seven_days_ago}
            }).to_list(100)
            
            if not learning_data:
                return
                
            # Analyze patterns
            avg_win_rate = sum(ld.get('bot_performance', {}).get('win_rate', 0) 
                             for ld in learning_data) / len(learning_data)
            
            # Get all user bots
            bots = await self.db.bots.find({'user_id': user_id, 'status': 'active'}).to_list(1000)
            
            for bot in bots:
                adjustments = {}
                
                # If consistent underperformance, reduce risk
                if avg_win_rate < 45:
                    current_stop_loss = bot.get('stop_loss_percent', 15)
                    new_stop_loss = max(current_stop_loss - 2, 10)
                    adjustments['stop_loss_percent'] = new_stop_loss
                    logger.info(f"Bot {bot['id']}: Reducing stop-loss to {new_stop_loss}%")
                
                # If consistent strong performance, slightly increase risk
                elif avg_win_rate > 65:
                    current_stop_loss = bot.get('stop_loss_percent', 15)
                    new_stop_loss = min(current_stop_loss + 1, 20)
                    adjustments['stop_loss_percent'] = new_stop_loss
                    logger.info(f"Bot {bot['id']}: Increasing stop-loss to {new_stop_loss}%")
                
                # Apply adjustments
                if adjustments:
                    await self.db.bots.update_one(
                        {'id': bot['id']},
                        {'$set': adjustments}
                    )
                    
        except Exception as e:
            logger.error(f"Strategy adjustment error: {e}")
            
    async def generate_weekly_summary(self, user_id: str):
        """Generate weekly performance summary"""
        try:
            # Get last 7 days of learning data
            seven_days_ago = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
            
            learning_data = await self.db.learning_data_collection.find({
                'user_id': user_id,
                'date': {'$gte': seven_days_ago}
            }).to_list(100)
            
            if not learning_data:
                return
                
            # Aggregate weekly stats
            total_trades = sum(ld.get('insights', {}).get('total_trades', 0) for ld in learning_data)
            total_pnl = sum(ld.get('insights', {}).get('total_pnl', 0) for ld in learning_data)
            
            summary = f"""
📊 Weekly Summary ({len(learning_data)} days analyzed)
- Total Trades: {total_trades}
- Total P&L: R{total_pnl:.2f}
- System Learning: {len(learning_data)} daily reports generated
- Strategy Adjustments: Continuous optimization active
            """
            
            # Create alert
            await self.db.alerts.insert_one({
                'user_id': user_id,
                'type': 'learning',
                'severity': 'low',
                'message': summary,
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'dismissed': False
            })
            
            logger.info(f"📊 Weekly summary generated for user {user_id}")
            
        except Exception as e:
            logger.error(f"Weekly summary error: {e}")

# Global instance
learning_system = SelfLearningSystem()
