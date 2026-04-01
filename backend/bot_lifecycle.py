"""
Bot Lifecycle Management
- Enforces 7-day paper trading period for user-created bots
- Auto-promotes bots to live trading after meeting criteria
- Tracks bot origin (user vs AI)
- Validates initial_capital requirements for paper bots
"""

import asyncio
from datetime import datetime, timezone, timedelta
import database as db
from logger_config import logger
from services.paper_wallet_ledger import paper_wallet_ledger


class BotLifecycleManager:
    def __init__(self):
        # Use config values for consistency
        from config import PAPER_TRAINING_DAYS, MIN_WIN_RATE, MIN_PROFIT_PERCENT, MIN_TRADES_FOR_PROMOTION
        self.paper_period_days = PAPER_TRAINING_DAYS  # 7 days
        self.min_trades_for_promotion = MIN_TRADES_FOR_PROMOTION  # 25 trades
        self.min_win_rate = MIN_WIN_RATE  # 52%
        self.min_profit_percent = MIN_PROFIT_PERCENT  # 3%
        self.max_drawdown = 0.15  # 15%
    
    async def check_promotions(self):
        """Check all bots ready for promotion from paper to live"""
        try:
            # Get all user-created bots still in paper mode
            paper_bots = await db.bots_collection.find({
                "origin": "user",
                "trading_mode": "paper",
                "status": "active"
            }, {"_id": 0}).to_list(1000)
            
            promotions = []
            for bot in paper_bots:
                if await self._should_promote(bot):
                    promotions.append(bot)
            
            # Promote eligible bots
            for bot in promotions:
                await self._promote_bot(bot)
                logger.info(f"✅ Promoted bot '{bot['name']}' to live trading")
            
            return len(promotions)
            
        except Exception as e:
            logger.error(f"Bot promotion check failed: {e}")
            return 0
    
    async def _should_promote(self, bot: dict) -> bool:
        """Check if bot meets promotion criteria"""
        try:
            # 1. Check 7-day period
            created_at = datetime.fromisoformat(bot.get('created_at', datetime.now(timezone.utc).isoformat()))
            days_old = (datetime.now(timezone.utc) - created_at).days
            
            if days_old < self.paper_period_days:
                return False
            
            # 2. Check minimum trades
            trades_count = await db.trades_collection.count_documents({
                "bot_id": bot['id'],
                "user_id": bot['user_id']
            })
            
            if trades_count < self.min_trades_for_promotion:
                return False
            
            # 3. Check win rate
            trades = await db.trades_collection.find({
                "bot_id": bot['id']
            }, {"_id": 0}).to_list(1000)
            
            if not trades:
                return False
            
            winning_trades = sum(1 for t in trades if t.get('profit_loss', 0) > 0)
            win_rate = winning_trades / len(trades)
            
            if win_rate < self.min_win_rate:
                logger.info(f"Bot {bot['name']}: Win rate too low ({win_rate:.1%} < {self.min_win_rate:.1%})")
                return False
            
            # 4. Check profit percentage (net profit / initial capital)
            current_capital = bot.get('current_capital', bot.get('initial_capital', 1000))
            initial_capital = bot.get('initial_capital', 1000)
            profit_pct = ((current_capital - initial_capital) / initial_capital) if initial_capital > 0 else 0
            
            if profit_pct < self.min_profit_percent:
                logger.info(f"Bot {bot['name']}: Profit too low ({profit_pct:.1%} < {self.min_profit_percent:.1%})")
                return False
            
            # 5. Check max drawdown (safety check)
            max_capital = max([t.get('new_capital', initial_capital) for t in trades] + [initial_capital])
            drawdown = (max_capital - current_capital) / max_capital if max_capital > 0 else 0
            
            if drawdown > self.max_drawdown:
                logger.info(f"Bot {bot['name']}: Drawdown too high ({drawdown:.1%} > {self.max_drawdown:.1%})")
                return False
            
            # 6. Check profit factor (>= 1.2)
            total_wins = sum(t.get('profit_loss', 0) for t in trades if t.get('profit_loss', 0) > 0)
            total_losses = abs(sum(t.get('profit_loss', 0) for t in trades if t.get('profit_loss', 0) < 0))
            profit_factor = total_wins / total_losses if total_losses > 0 else total_wins
            
            if profit_factor < 1.2:
                logger.info(f"Bot {bot['name']}: Profit factor too low ({profit_factor:.2f} < 1.2)")
                return False
            
            # Compute trade quality: combination of win_rate, profit_factor, and drawdown
            avg_quality = round(min(10.0, (win_rate * 5) + (min(profit_factor, 2) * 2.5) + ((1 - drawdown) * 2.5)), 1)

            logger.info(f"Bot {bot['name']}: ✅ Eligible for promotion (win_rate={win_rate:.1%}, quality={avg_quality:.1f}/10, pf={profit_factor:.2f})")
            return True
            
        except Exception as e:
            logger.error(f"Promotion check failed for bot {bot.get('id')}: {e}")
            return False
    
    async def _promote_bot(self, bot: dict):
        """Promote bot from paper to live trading - RESETS CAPITAL to initial amount"""
        try:
            # Check user's system mode
            system_mode = await db.system_modes_collection.find_one(
                {"user_id": bot['user_id']},
                {"_id": 0}
            )
            
            # Only promote if user has live trading enabled
            if system_mode and system_mode.get('liveTrading', False):
                # Store paper performance for reference
                paper_performance = {
                    "paper_final_capital": bot.get('current_capital', 0),
                    "paper_total_profit": bot.get('total_profit', 0),
                    "paper_trades_count": bot.get('trades_count', 0)
                }
                
                # Reset capital to initial amount for live trading
                # Live trading starts fresh with real funds
                initial_capital = bot.get('initial_capital', 1000)
                
                await db.bots_collection.update_one(
                    {"id": bot['id']},
                    {
                        "$set": {
                            "trading_mode": "live",
                            "promoted_at": datetime.now(timezone.utc).isoformat(),
                            "promotion_reason": "Met 7-day paper criteria",
                            "current_capital": initial_capital,
                            "total_profit": 0.0,
                            "trades_count": 0,
                            "paper_performance": paper_performance,
                            "live_started_at": datetime.now(timezone.utc).isoformat()
                        }
                    }
                )
                logger.info(f"Bot '{bot['name']}' promoted to LIVE trading - Capital reset to R{initial_capital}")
            else:
                logger.info(f"Bot '{bot['name']}' eligible but user not in live mode")
                
        except Exception as e:
            logger.error(f"Bot promotion failed: {e}")
    
    async def tag_new_bot(self, bot_id: str, origin: str = "user", initial_capital: float = 0) -> tuple[bool, str]:
        """
        Tag a newly created bot with origin and paper end date.
        Reserves paper funds in the ledger for paper bots.
        """
        try:
            paper_end_date = None
            if origin == "user":
                paper_end_date = (datetime.now(timezone.utc) + timedelta(days=self.paper_period_days)).isoformat()
            
            # Get bot data to determine user_id
            bot = await db.bots_collection.find_one({"id": bot_id}, {"_id": 0})
            if not bot:
                logger.error(f"Bot {bot_id} not found for tagging")
                return False, "Bot not found"
            
            user_id = bot.get('user_id')
            
            # Reserve paper funds in ledger
            if initial_capital > 0:
                exchange = (bot.get("exchange") or "").lower()
                pair = bot.get("pair", "")
                is_zar_exchange = (exchange == "luno" or "/ZAR" in pair)
                currency = "ZAR" if is_zar_exchange else "USDT"

                if is_zar_exchange:
                    # ZAR exchange: direct ZAR reservation from user wallet + ZAR ledger entry
                    success, msg = await paper_wallet_ledger.reserve_funds(
                        user_id, bot_id, initial_capital, "ZAR"
                    )
                else:
                    # USDT exchange (Binance, KuCoin, etc.) in paper mode:
                    # The user's paper wallet is ZAR-denominated.  Deduct the ZAR economic
                    # base from the user wallet but create the per-bot ledger entry in USDT
                    # so that trade sizing (which uses quote currency) remains correct.
                    # fx_rate_at_creation is ZAR per 1 USDT (e.g. 19.0 → 1 USDT = R19).
                    # Therefore: zar_base = usdt_amount × (ZAR/USDT rate).
                    canonical_zar = float(bot.get("canonical_base_capital_zar") or 0)
                    fx_rate = float(bot.get("fx_rate_at_creation") or 1.0)
                    if canonical_zar <= 0 and fx_rate > 0:
                        # Derive ZAR base from USDT amount: e.g. 52.63 USDT × 19 = R1000
                        canonical_zar = initial_capital * fx_rate
                    if canonical_zar <= 0:
                        canonical_zar = initial_capital  # last-resort fallback

                    success, msg = await paper_wallet_ledger.reserve_funds(
                        user_id, bot_id, initial_capital, "USDT",
                        wallet_amount=canonical_zar,
                        wallet_currency="ZAR",
                    )

                if not success:
                    logger.warning(f"Failed to reserve paper funds for bot {bot_id}: {msg}")
                    return False, msg
            
            await db.bots_collection.update_one(
                {"id": bot_id},
                {
                    "$set": {
                        "origin": origin,
                        "paper_end_date": paper_end_date,
                        "trading_mode": "paper"
                    }
                }
            )
            logger.info(f"Tagged bot {bot_id} as {origin} with paper period and R{initial_capital:,.2f} reserved")
            return True, "Tagged"
            
        except Exception as e:
            logger.error(f"Bot tagging failed: {e}")
            return False, str(e)


# Global instance
bot_lifecycle = BotLifecycleManager()
