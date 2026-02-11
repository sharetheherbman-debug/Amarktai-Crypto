"""Central risk engine for capital protection"""
from datetime import datetime, timezone, timedelta
from typing import Optional
import logging
import database as db
from exchange_limits import get_exchange_limits

logger = logging.getLogger(__name__)

class RiskEngine:
    def __init__(self):
        self.user_daily_loss = {}  # {user_id: loss_today}
        self.last_reset = datetime.now(timezone.utc).date()
    
    async def check_trade_risk(self, user_id: str, bot_id: str, exchange: str, 
                               proposed_notional: float, risk_mode: str) -> tuple[bool, str]:
        """Comprehensive risk check before allowing trade"""
        
        # Get bot details
        bot = await db.bots_collection.find_one({"id": bot_id}, {"_id": 0})
        if not bot:
            return False, "Bot not found"
        
        # Get user's total equity
        user_bots = await db.bots_collection.find({"user_id": user_id}, {"_id": 0}).to_list(100)
        total_equity = sum(b.get("current_capital", 0) for b in user_bots)
        
        if total_equity <= 0:
            return False, "No capital available"
        
        # 1. Check daily loss limit (risk-profile based)
        await self._check_daily_loss(user_id, total_equity)
        daily_loss = self.user_daily_loss.get(user_id, 0)
        user = await db.users_collection.find_one({"id": user_id}, {"_id": 0, "risk_profile": 1})
        profile = (user or {}).get("risk_profile", "balanced")
        profile = profile.lower()
        max_daily_loss_pct = {"safe": 0.15, "balanced": 0.20, "risky": 0.25}.get(profile, 0.20)
        max_daily_loss = total_equity * max_daily_loss_pct
        
        if abs(daily_loss) >= max_daily_loss:
            logger.warning(f"Daily loss limit hit for user {user_id}: {daily_loss}")
            return False, f"Protection mode: Daily loss limit reached (R{max_daily_loss:.2f})"
        
        # 2. Check per-bot capital allocation based on risk mode
        # Use BOT's capital, not total equity (was causing trades to be blocked)
        bot_capital = bot.get("current_capital", 1000)
        max_percent = {
            "safe": 0.25,       # 25% of bot capital
            "balanced": 0.35,   # 35% of bot capital
            "risky": 0.45,      # 45% of bot capital
            "aggressive": 0.60  # 60% of bot capital
        }
        max_notional = bot_capital * max_percent.get(risk_mode, 0.25)
        
        if proposed_notional > max_notional:
            return False, f"Trade size too large for {risk_mode} mode (max R{max_notional:.2f})"
        
        # 3. Check per-asset exposure
        # Extract asset from proposed trade (e.g., BTC from BTC/ZAR)
        # For now, assume we can extract asset from context
        # In production, would need asset parameter passed in
        
        # Get all user's trades to calculate current exposure
        recent_open_trades = await db.trades_collection.find({
            "user_id": user_id,
            "status": {"$in": ["open", "pending"]},  # Only open positions
            "timestamp": {"$gte": (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()}
        }, {"_id": 0}).to_list(1000)
        
        # Calculate per-asset exposure
        asset_exposure = {}
        for trade in recent_open_trades:
            pair = trade.get('pair', '')
            if '/' in pair:
                asset = pair.split('/')[0]  # e.g., BTC from BTC/ZAR
                trade_value = trade.get('entry_price', 0) * trade.get('amount', 0)
                asset_exposure[asset] = asset_exposure.get(asset, 0) + trade_value
        
        # Check if any single asset exceeds 35% of total equity
        for asset, exposure in asset_exposure.items():
            exposure_pct = (exposure / total_equity) if total_equity > 0 else 0
            if exposure_pct > 0.35:
                return False, f"Too much exposure to {asset} ({exposure_pct*100:.1f}% > 35% limit)"
        
        # 4. Check per-exchange exposure (only if user has multiple exchanges)
        exchanges_used = set(b.get("exchange") for b in user_bots)
        
        if len(exchanges_used) > 1:  # Only enforce if using multiple exchanges
            exchange_capital = sum(b.get("current_capital", 0) for b in user_bots if b.get("exchange") == exchange)
            max_exchange_exposure = total_equity * 0.60  # 60% max per exchange
            
            if exchange_capital > max_exchange_exposure:
                return False, f"Too much exposure on {exchange.upper()} (max 60% of equity)"
        
        # 5. Minimum trade notional (avoid tiny wins)
        min_notional = 10  # R10 minimum (lowered for testing)
        if proposed_notional < min_notional:
            return False, f"Trade too small (min R{min_notional})"
        
        return True, "Risk check passed"
    
    async def _check_daily_loss(self, user_id: str, total_equity: float):
        """Calculate today's realized loss using REALIZED net PnL only"""
        today = datetime.now(timezone.utc).date()
        
        # Reset if new day
        if today > self.last_reset:
            self.user_daily_loss.clear()
            self.last_reset = today
        
        # Calculate today's REALIZED loss from closed trades only
        today_start = datetime.combine(today, datetime.min.time()).replace(tzinfo=timezone.utc)
        trades_today = await db.trades_collection.find({
            "user_id": user_id,
            "status": "closed",  # Only closed (realized) trades
            "timestamp": {"$gte": today_start.isoformat()}
        }, {"_id": 0, "net_pnl": 1, "profit_loss": 1}).to_list(1000)
        
        # Use canonical field normalization: net_pnl → fallback profit_loss
        total_pnl = sum(t.get("net_pnl", t.get("profit_loss", 0)) for t in trades_today)
        self.user_daily_loss[user_id] = total_pnl if total_pnl < 0 else 0
    
    async def record_trade_result(self, user_id: str, profit_loss: float):
        """Record trade result for risk tracking"""
        current_loss = self.user_daily_loss.get(user_id, 0)
        if profit_loss < 0:
            self.user_daily_loss[user_id] = current_loss + profit_loss

# Global instance
risk_engine = RiskEngine()
