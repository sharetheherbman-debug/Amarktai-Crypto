"""
AI Super-Brain
- Aggregates learning from all bots
- Generates daily insights using LLM
- Pattern recognition across trades
- Strategic recommendations
"""

import asyncio
from datetime import datetime, timezone, timedelta
from logger_config import logger
import database as db
import os


class AISuperBrain:
    def __init__(self):
        self.openai_key = os.getenv('OPENAI_API_KEY', '')
        self.insights_cache = {}
    
    async def generate_daily_insights(self, user_id: str) -> dict:
        """Generate AI-powered daily insights"""
        try:
            logger.info(f"Generating daily insights for user {user_id}")
            
            # Gather data
            data = await self._gather_trading_data(user_id)
            
            # Analyze patterns
            patterns = await self._analyze_patterns(data)
            
            # Generate insights with AI
            insights = await self._generate_ai_insights(data, patterns)
            
            result = {
                "user_id": user_id,
                "date": datetime.now(timezone.utc).strftime('%Y-%m-%d'),
                "patterns": patterns,
                "insights": insights,
                "recommendations": await self._generate_recommendations(patterns),
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            
            self.insights_cache[user_id] = result
            return result
            
        except Exception as e:
            logger.error(f"Insight generation failed: {e}")
            return {"error": str(e)}
    
    async def _gather_trading_data(self, user_id: str) -> dict:
        """Gather trading data for analysis"""
        # Get last 7 days of trades
        seven_days_ago = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
        
        trades = await db.trades_collection.find({
            "user_id": user_id,
            "timestamp": {"$gte": seven_days_ago}
        }, {"_id": 0}).to_list(10000)
        
        bots = await db.bots_collection.find(
            {"user_id": user_id, "status": "active"},
            {"_id": 0}
        ).to_list(1000)
        
        return {
            "trades": trades,
            "bots": bots,
            "period": "7_days"
        }
    
    async def _analyze_patterns(self, data: dict) -> dict:
        """Analyze trading patterns"""
        trades = data['trades']
        
        if not trades:
            return {"no_data": True}
        
        # Winning patterns
        winning_trades = [t for t in trades if t.get('pnl', 0) > 0]
        losing_trades = [t for t in trades if t.get('pnl', 0) < 0]
        
        # By pair
        pair_performance = {}
        for trade in trades:
            pair = trade.get('pair', 'BTC/ZAR')
            if pair not in pair_performance:
                pair_performance[pair] = {'wins': 0, 'losses': 0, 'total_pnl': 0}
            
            if trade.get('pnl', 0) > 0:
                pair_performance[pair]['wins'] += 1
            else:
                pair_performance[pair]['losses'] += 1
            
            pair_performance[pair]['total_pnl'] += trade.get('pnl', 0)
        
        # By time of day
        hour_performance = {}
        for trade in trades:
            try:
                ts = datetime.fromisoformat(trade.get('timestamp', ''))
                hour = ts.hour
                if hour not in hour_performance:
                    hour_performance[hour] = {'wins': 0, 'losses': 0}
                
                if trade.get('pnl', 0) > 0:
                    hour_performance[hour]['wins'] += 1
                else:
                    hour_performance[hour]['losses'] += 1
            except:
                pass
        
        return {
            "total_trades": len(trades),
            "win_rate": (len(winning_trades) / len(trades)) * 100 if trades else 0,
            "best_pair": max(pair_performance.items(), key=lambda x: x[1]['total_pnl'])[0] if pair_performance else None,
            "worst_pair": min(pair_performance.items(), key=lambda x: x[1]['total_pnl'])[0] if pair_performance else None,
            "pair_performance": pair_performance,
            "best_hour": max(hour_performance.items(), key=lambda x: x[1]['wins'])[0] if hour_performance else None,
            "worst_hour": min(hour_performance.items(), key=lambda x: x[1]['wins'])[0] if hour_performance else None
        }
    
    async def _generate_ai_insights(self, data: dict, patterns: dict) -> str:
        """Generate AI insights using LLM"""
        if not self.openai_key:
            return self._generate_basic_insights(patterns)
        
        try:
            import openai
            openai.api_key = self.openai_key
            
            prompt = f"""
Analyze this crypto trading data and provide actionable insights:

Total Trades: {patterns.get('total_trades', 0)}
Win Rate: {patterns.get('win_rate', 0):.1f}%
Best Performing Pair: {patterns.get('best_pair', 'N/A')}
Worst Performing Pair: {patterns.get('worst_pair', 'N/A')}
Best Trading Hour: {patterns.get('best_hour', 'N/A')}

Provide:
1. Key observations
2. What's working well
3. What needs improvement
4. Actionable recommendations

Keep it concise (3-4 sentences).
"""
            
            response = await asyncio.to_thread(
                openai.ChatCompletion.create,
                model="gpt-4",
                messages=[{"role": "user", "content": prompt}],
                max_tokens=200
            )
            
            return response.choices[0].message.content
            
        except Exception as e:
            logger.error(f"AI insight generation failed: {e}")
            return self._generate_basic_insights(patterns)
    
    def _generate_basic_insights(self, patterns: dict) -> str:
        """Generate basic insights without AI"""
        insights = []
        
        win_rate = patterns.get('win_rate', 0)
        if win_rate > 60:
            insights.append(f"Strong performance with {win_rate:.1f}% win rate.")
        elif win_rate > 50:
            insights.append(f"Decent performance at {win_rate:.1f}% win rate.")
        else:
            insights.append(f"Performance needs improvement at {win_rate:.1f}% win rate.")
        
        best_pair = patterns.get('best_pair')
        if best_pair:
            insights.append(f"{best_pair} is your top performer.")
        
        best_hour = patterns.get('best_hour')
        if best_hour is not None:
            insights.append(f"Trading is most successful around {best_hour}:00.")
        
        return " ".join(insights)
    
    async def _generate_recommendations(self, patterns: dict) -> list:
        """Generate strategic recommendations"""
        recommendations = []
        
        win_rate = patterns.get('win_rate', 0)
        if win_rate < 55:
            recommendations.append("Consider reducing risk mode to 'safe' until win rate improves")
        
        best_pair = patterns.get('best_pair')
        if best_pair:
            recommendations.append(f"Allocate more capital to {best_pair}")
        
        worst_pair = patterns.get('worst_pair')
        if worst_pair:
            recommendations.append(f"Consider pausing {worst_pair} bots temporarily")
        
        if not recommendations:
            recommendations.append("Continue current strategy - performance is stable")
        
        return recommendations

    async def chat(self, user_id: str, message: str, context: dict = None) -> dict:
        """Process a chat message and return AI response.

        This method is used by the AI chat router and can be patched in tests.

        Args:
            user_id: Authenticated user's ID.
            message: User's message text.
            context: Optional additional context dict.

        Returns:
            Dict with 'response' str and optional 'action' key.
        """
        try:
            if not self.openai_key:
                return {
                    "response": "AI chat requires an OpenAI API key. Please add one in Settings → API Keys.",
                    "action": None,
                }

            import openai
            client = openai.AsyncOpenAI(api_key=self.openai_key)

            system_prompt = (
                "You are Amarktai AI, an intelligent crypto trading assistant. "
                "Help users understand their trading bots, diagnose issues, and optimise performance. "
                "Be concise, accurate, and actionable."
            )
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": message},
            ]

            completion = await client.chat.completions.create(
                model="gpt-4o-mini",
                messages=messages,
                max_tokens=500,
                temperature=0.7,
            )
            response_text = completion.choices[0].message.content
            return {"response": response_text, "action": None}
        except Exception as e:
            logger.error(f"AISuperBrain.chat error: {e}")
            return {"response": f"AI error: {str(e)[:200]}", "action": None}


# Global instance
ai_super_brain = AISuperBrain()
