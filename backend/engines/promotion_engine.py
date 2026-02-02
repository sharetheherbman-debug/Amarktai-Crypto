"""
Paper → Live Promotion Engine
Tracks bot performance and determines eligibility for live trading
"""
import asyncio
from datetime import datetime, timezone, timedelta
from typing import Dict, Tuple
import database as db
from logger_config import logger
from config import (
    PAPER_TRAINING_DAYS, 
    MIN_WIN_RATE, 
    MIN_PROFIT_PERCENT, 
    MIN_TRADES_FOR_PROMOTION
)


class PromotionEngine:
    def __init__(self):
        pass
    
    async def calculate_bot_performance(self, bot_id: str) -> dict:
        """Calculate bot performance metrics"""
        try:
            # Get bot
            bot = await db.bots_collection.find_one({"id": bot_id}, {"_id": 0})
            if not bot:
                return {"error": "Bot not found"}
            
            # Get all trades for this bot
            trades = await db.trades_collection.find(
                {"bot_id": bot_id},
                {"_id": 0}
            ).to_list(1000)
            
            # Calculate metrics
            total_trades = len(trades)
            winning_trades = len([t for t in trades if t.get('profit_loss', 0) > 0])
            losing_trades = len([t for t in trades if t.get('profit_loss', 0) < 0])
            
            win_rate = (winning_trades / total_trades) if total_trades > 0 else 0
            
            # Calculate profit percentage
            initial_capital = bot.get('initial_capital', 1000)
            current_capital = bot.get('current_capital', 1000)
            profit_pct = ((current_capital - initial_capital) / initial_capital) if initial_capital > 0 else 0
            
            # Calculate days in paper trading
            paper_start = bot.get('paper_start_date')
            if paper_start:
                if isinstance(paper_start, str):
                    paper_start = datetime.fromisoformat(paper_start.replace('Z', '+00:00'))
                days_trading = (datetime.now(timezone.utc) - paper_start).days
            else:
                days_trading = 0
            
            return {
                "bot_id": bot_id,
                "bot_name": bot.get('name'),
                "total_trades": total_trades,
                "winning_trades": winning_trades,
                "losing_trades": losing_trades,
                "win_rate": win_rate,
                "profit_percent": profit_pct,
                "days_trading": days_trading,
                "current_capital": current_capital,
                "initial_capital": initial_capital
            }
        
        except Exception as e:
            logger.error(f"Calculate performance error: {e}")
            return {"error": str(e)}
    
    async def is_eligible_for_live(self, bot_id: str) -> tuple[bool, str, dict]:
        """Check if bot is eligible for live trading promotion"""
        try:
            performance = await self.calculate_bot_performance(bot_id)
            
            if "error" in performance:
                return False, performance["error"], {}
            
            # Check criteria
            checks = {
                "days_requirement": performance['days_trading'] >= PAPER_TRAINING_DAYS,
                "win_rate_requirement": performance['win_rate'] >= MIN_WIN_RATE,
                "profit_requirement": performance['profit_percent'] >= MIN_PROFIT_PERCENT,
                "trades_requirement": performance['total_trades'] >= MIN_TRADES_FOR_PROMOTION
            }
            
            # Build reason message
            reasons = []
            if not checks['days_requirement']:
                reasons.append(f"❌ Need {PAPER_TRAINING_DAYS} days (currently {performance['days_trading']})")
            else:
                reasons.append(f"✅ {performance['days_trading']} days completed")
            
            if not checks['win_rate_requirement']:
                reasons.append(f"❌ Need {MIN_WIN_RATE*100:.0f}% win rate (currently {performance['win_rate']*100:.1f}%)")
            else:
                reasons.append(f"✅ Win rate: {performance['win_rate']*100:.1f}%")
            
            if not checks['profit_requirement']:
                reasons.append(f"❌ Need {MIN_PROFIT_PERCENT*100:.0f}% profit (currently {performance['profit_percent']*100:.1f}%)")
            else:
                reasons.append(f"✅ Profit: {performance['profit_percent']*100:.1f}%")
            
            if not checks['trades_requirement']:
                reasons.append(f"❌ Need {MIN_TRADES_FOR_PROMOTION} trades (currently {performance['total_trades']})")
            else:
                reasons.append(f"✅ {performance['total_trades']} trades completed")
            
            all_eligible = all(checks.values())
            
            message = "\n".join(reasons)
            
            return all_eligible, message, performance
        
        except Exception as e:
            logger.error(f"Eligibility check error: {e}")
            return False, f"Error: {str(e)}", {}
    
    async def get_all_eligible_bots(self, user_id: str) -> list:
        """Get all bots eligible for live promotion"""
        try:
            # Get all paper trading bots
            bots = await db.bots_collection.find({
                "user_id": user_id,
                "trading_mode": "paper",
                "status": "active"
            }, {"_id": 0}).to_list(1000)
            
            eligible = []
            
            for bot in bots:
                is_eligible, reason, performance = await self.is_eligible_for_live(bot['id'])
                if is_eligible:
                    eligible.append({
                        **bot,
                        "performance": performance,
                        "eligibility_reason": reason
                    })
            
            return eligible
        
        except Exception as e:
            logger.error(f"Get eligible bots error: {e}")
            return []
    
    async def promote_to_live(self, bot_id: str, user_confirmed: bool = False, check_system_mode: bool = True) -> dict:
        """Promote bot to live trading"""
        try:
            # Check system-wide live trading enabled flag
            if check_system_mode:
                import database as db
                system_modes = await db.system_modes_collection.find_one({})
                
                if system_modes and not system_modes.get('liveTrading', False):
                    return {
                        "success": False,
                        "message": "❌ Live trading is disabled system-wide. Enable it first."
                    }
            if not user_confirmed:
                return {
                    "success": False,
                    "message": "❌ User confirmation required. Have you funded your exchange wallet?"
                }
            
            # Check eligibility first
            is_eligible, reason, performance = await self.is_eligible_for_live(bot_id)
            
            if not is_eligible:
                return {
                    "success": False,
                    "message": f"❌ Bot not eligible:\n{reason}"
                }
            
            # Promote to live with clean stat separation
            # Archive paper stats and reset live counters
            bot = await db.bots_collection.find_one({"id": bot_id}, {"_id": 0})
            
            # Preserve paper trading history
            paper_history = {
                "paper_total_trades": bot.get("trades_count", 0),
                "paper_winning_trades": bot.get("winning_trades", 0),
                "paper_losing_trades": bot.get("losing_trades", 0),
                "paper_total_profit": bot.get("total_profit", 0),
                "paper_win_rate": performance.get("win_rate", 0),
                "paper_profit_percent": performance.get("profit_percent", 0),
                "paper_max_drawdown": bot.get("max_drawdown", 0),
                "paper_start_date": bot.get("paper_start_date"),
                "paper_end_date": datetime.now(timezone.utc).isoformat()
            }
            
            result = await db.bots_collection.update_one(
                {"id": bot_id},
                {
                    "$set": {
                        "trading_mode": "live",
                        "promoted_at": datetime.now(timezone.utc).isoformat(),
                        "learning_complete": True,
                        # Archive paper stats
                        "paper_history": paper_history,
                        # Reset live counters (clean slate for live trading)
                        "live_trades_count": 0,
                        "live_winning_trades": 0,
                        "live_losing_trades": 0,
                        "live_total_profit": 0,
                        "live_start_date": datetime.now(timezone.utc).isoformat()
                    }
                }
            )
            
            if result.modified_count > 0:
                bot = await db.bots_collection.find_one({"id": bot_id}, {"_id": 0})
                logger.info(f"🚀 Promoted bot {bot.get('name')} to LIVE trading")
                
                return {
                    "success": True,
                    "message": f"🚀 {bot.get('name')} promoted to LIVE trading!",
                    "bot": bot
                }
            
            return {
                "success": False,
                "message": "❌ Failed to promote bot"
            }
        
        except Exception as e:
            logger.error(f"Promote to live error: {e}")
            return {
                "success": False,
                "message": f"❌ Error: {str(e)}"
            }
    
    async def check_promotion_eligibility(self, bot: Dict) -> Tuple[bool, str]:
        """
        Check if bot is eligible for promotion to live trading
        STRICT 7-DAY PAPER TRADING REQUIREMENT
        Uses ONLY paper trades from last 7 days
        """
        try:
            bot_id = bot.get('id')
            
            # 1. Check paper training duration (MUST be >= 7 days)
            paper_start = bot.get('paper_start_date')
            if not paper_start:
                return False, "Paper start date not set"
            
            paper_start_dt = datetime.fromisoformat(paper_start.replace('Z', '+00:00'))
            days_in_paper = (datetime.now(timezone.utc) - paper_start_dt).days
            
            if days_in_paper < PAPER_TRAINING_DAYS:
                return False, f"Paper training incomplete: {days_in_paper}/{PAPER_TRAINING_DAYS} days"
            
            # 2. Get ONLY paper trades from last 7 days
            seven_days_ago = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
            
            paper_trades = await db.trades_collection.find({
                "bot_id": bot_id,
                "is_paper": True,
                "timestamp": {"$gte": seven_days_ago}
            }, {"_id": 0}).to_list(1000)
            
            # 3. Check minimum trades requirement
            if len(paper_trades) < MIN_TRADES_FOR_PROMOTION:
                return False, f"Insufficient trades: {len(paper_trades)}/{MIN_TRADES_FOR_PROMOTION}"
            
            # 4. Calculate win rate from paper trades only
            winning_trades = len([t for t in paper_trades if t.get('profit_loss', 0) > 0])
            win_rate = (winning_trades / len(paper_trades)) * 100
            
            if win_rate < MIN_WIN_RATE:
                return False, f"Win rate too low: {win_rate:.1f}% (min: {MIN_WIN_RATE}%)"
            
            # 5. Calculate profit from paper trades only
            total_profit_from_paper = sum(t.get('profit_loss', 0) for t in paper_trades)
            initial_capital = bot.get('initial_capital', 1000)
            profit_pct = (total_profit_from_paper / initial_capital) * 100
            
            if profit_pct < MIN_PROFIT_PERCENT:
                return False, f"Profit too low: {profit_pct:.1f}% (min: {MIN_PROFIT_PERCENT}%)"
            
            # 6. All checks passed
            return True, f"Eligible: {win_rate:.1f}% win rate, {profit_pct:.1f}% profit over 7 days"
            
        except Exception as e:
            logger.error(f"Check promotion eligibility error: {e}")
            return False, f"Error: {str(e)}"


promotion_engine = PromotionEngine()
