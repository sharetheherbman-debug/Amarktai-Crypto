"""
Bot Performance Ranking System
- Ranks bots by performance metrics
- Identifies top and bottom performers
- Calculates Sharpe ratio, win rate, profit factor
- Recent performance weighting (24-48h trades get higher weight)
- Regime-aware fitness scoring
"""

import asyncio
from datetime import datetime, timezone, timedelta
import database as db
from logger_config import logger
import math
import config


class PerformanceRanker:
    def __init__(self):
        self.ranking_cache = {}
        self.last_rank_time = None
    
    async def rank_bots(self, user_id: str) -> list:
        """Rank all user's bots by performance"""
        try:
            bots = await db.bots_collection.find(
                {"user_id": user_id, "status": "active"},
                {"_id": 0}
            ).to_list(1000)
            
            ranked_bots = []
            for bot in bots:
                score = await self._calculate_performance_score(bot)
                ranked_bots.append({
                    **bot,
                    "performance_score": score
                })
            
            # Sort by performance score (descending)
            ranked_bots.sort(key=lambda x: x['performance_score'], reverse=True)
            
            # Add rank
            for idx, bot in enumerate(ranked_bots):
                bot['rank'] = idx + 1
            
            # Cache rankings
            self.ranking_cache[user_id] = {
                "rankings": ranked_bots,
                "timestamp": datetime.now(timezone.utc)
            }
            
            logger.info(f"Ranked {len(ranked_bots)} bots for user {user_id}")
            return ranked_bots
            
        except Exception as e:
            logger.error(f"Bot ranking failed: {e}")
            return []
    
    async def _calculate_performance_score(self, bot: dict) -> float:
        """
        Calculate composite performance score with recent-performance weighting
        
        Weights:
        - Recent trades (24-48h): 2x weight
        - All-time performance: 1x weight
        - Regime awareness: Bonus for matching current regime
        """
        try:
            # Get bot's trades
            trades = await db.trades_collection.find(
                {"bot_id": bot['id']},
                {"_id": 0}
            ).to_list(1000)
            
            if not trades:
                return 0.0
            
            # Separate recent trades (last 24-48 hours)
            now = datetime.now(timezone.utc)
            recent_24h = [t for t in trades if self._is_recent_trade(t, now, hours=24)]
            recent_48h = [t for t in trades if self._is_recent_trade(t, now, hours=48)]
            
            # Calculate all-time metrics
            all_time_score = self._calculate_metrics(trades)
            
            # Calculate recent metrics (with fallback if insufficient data)
            recent_score_24h = self._calculate_metrics(recent_24h) if len(recent_24h) >= 3 else all_time_score
            recent_score_48h = self._calculate_metrics(recent_48h) if len(recent_48h) >= 5 else all_time_score
            
            # Weighted combination: recent performance gets higher weight
            # 40% recent 24h, 30% recent 48h, 30% all-time
            weighted_score = (
                recent_score_24h * 0.40 +
                recent_score_48h * 0.30 +
                all_time_score * 0.30
            )
            
            # Add regime-aware bonus
            regime_bonus = await self._calculate_regime_bonus(bot, trades)
            final_score = weighted_score + regime_bonus
            
            return round(final_score, 2)
            
        except Exception as e:
            logger.error(f"Performance score calculation failed: {e}")
            return 0.0
    
    def _is_recent_trade(self, trade: dict, now: datetime, hours: int) -> bool:
        """Check if trade is within last N hours"""
        try:
            trade_time_str = trade.get('timestamp') or trade.get('created_at')
            if not trade_time_str:
                return False
            
            # Parse timestamp (handle both ISO and string formats)
            if isinstance(trade_time_str, str):
                trade_time = datetime.fromisoformat(trade_time_str.replace('Z', '+00:00'))
            else:
                trade_time = trade_time_str
            
            # Ensure timezone aware
            if trade_time.tzinfo is None:
                trade_time = trade_time.replace(tzinfo=timezone.utc)
            
            time_diff = now - trade_time
            return time_diff <= timedelta(hours=hours)
        except Exception as e:
            logger.debug(f"Trade time parsing error: {e}")
            return False
    
    def _calculate_metrics(self, trades: list) -> float:
        """Calculate performance metrics for a set of trades"""
        if not trades:
            return 0.0
        
        # 1. Win Rate (0-100)
        winning_trades = sum(1 for t in trades if t.get('pnl', 0) > 0)
        win_rate = (winning_trades / len(trades)) * 100
        
        # 2. Profit Factor (ratio of wins to losses)
        total_wins = sum(t.get('pnl', 0) for t in trades if t.get('pnl', 0) > 0)
        total_losses = abs(sum(t.get('pnl', 0) for t in trades if t.get('pnl', 0) < 0))
        profit_factor = total_wins / total_losses if total_losses > 0 else total_wins
        
        # 3. Average profit per trade
        avg_profit = sum(t.get('pnl', 0) for t in trades) / len(trades)
        
        # 4. Sharpe Ratio (simplified)
        returns = [t.get('pnl', 0) for t in trades]
        mean_return = sum(returns) / len(returns)
        std_dev = math.sqrt(sum((r - mean_return) ** 2 for r in returns) / len(returns))
        sharpe = mean_return / std_dev if std_dev > 0 else 0
        
        # 5. Total profit for this set
        total_profit = sum(t.get('pnl', 0) for t in trades)
        
        # Composite score (weighted)
        score = (
            win_rate * 0.25 +           # 25% weight on win rate
            profit_factor * 10 * 0.20 + # 20% weight on profit factor
            sharpe * 20 * 0.15 +        # 15% weight on Sharpe
            total_profit * 0.30 +       # 30% weight on total profit
            avg_profit * 100 * 0.10     # 10% weight on avg profit
        )
        
        return score
    
    async def _calculate_regime_bonus(self, bot: dict, trades: list) -> float:
        """
        Calculate regime-aware bonus
        
        If bot performs well in current market regime, give bonus
        """
        try:
            # Try to get current market regime
            from market_regime import get_current_regime
            
            try:
                current_regime = await get_current_regime()
            except:
                # If market_regime module not available, use simple heuristic
                current_regime = 'neutral'
            
            # Calculate bot's performance in similar regime
            # For now, give bonus if bot is profitable (simple heuristic)
            # In production, this would check regime-specific performance
            if len(trades) > 0:
                total_pnl = sum(t.get('pnl', 0) for t in trades)
                if total_pnl > 0:
                    # Small bonus for profitable bots (regime-agnostic for now)
                    return 10.0
            
            return 0.0
            
        except Exception as e:
            logger.debug(f"Regime bonus calculation skipped: {e}")
            return 0.0
    
    async def get_top_performers(self, user_id: str, limit: int = 5) -> list:
        """Get top N performing bots"""
        ranked = await self.rank_bots(user_id)
        return ranked[:limit]
    
    async def get_bottom_performers(self, user_id: str, limit: int = 5) -> list:
        """Get bottom N performing bots"""
        ranked = await self.rank_bots(user_id)
        return ranked[-limit:] if len(ranked) > limit else ranked
    
    async def get_quarantine_candidates(self, user_id: str) -> list:
        """
        Get bots that should be quarantined (below threshold)
        
        Returns bots with performance below QUARANTINE_THRESHOLD (-5%)
        """
        try:
            ranked = await self.rank_bots(user_id)
            quarantine_threshold = config.QUARANTINE_THRESHOLD
            
            # Find bots below threshold
            candidates = []
            for bot in ranked:
                # Calculate return percentage
                initial_capital = bot.get('initial_capital', 1000)
                total_profit = bot.get('total_profit', 0)
                return_pct = (total_profit / initial_capital) if initial_capital > 0 else 0
                
                if return_pct < quarantine_threshold:
                    candidates.append({
                        **bot,
                        'return_pct': return_pct
                    })
            
            logger.info(f"Found {len(candidates)} quarantine candidates for user {user_id}")
            return candidates
            
        except Exception as e:
            logger.error(f"Quarantine candidate check failed: {e}")
            return []


# Global instance
performance_ranker = PerformanceRanker()
