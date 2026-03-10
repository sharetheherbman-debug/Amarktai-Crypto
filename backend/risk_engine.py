"""Central risk engine for capital protection"""
from datetime import datetime, timezone, timedelta
from typing import Optional
import logging
import os
import database as db
from exchange_limits import get_exchange_limits

logger = logging.getLogger(__name__)

FIXED_FRACTIONAL_RISK_MIN = float(os.getenv("FIXED_FRACTIONAL_RISK_MIN", "0.01"))
FIXED_FRACTIONAL_RISK_MAX = float(os.getenv("FIXED_FRACTIONAL_RISK_MAX", "0.02"))
FIXED_FRACTIONAL_RISK_DEFAULT = float(os.getenv("FIXED_FRACTIONAL_RISK_DEFAULT", "0.015"))
DAILY_MAX_LOSS_PCT = float(os.getenv("DAILY_MAX_LOSS_PCT", "0.03"))

MAX_DRAWDOWN_BY_MODE = {
    "safe": float(os.getenv("MAX_DRAWDOWN_SAFE", "0.08")),
    "balanced": float(os.getenv("MAX_DRAWDOWN_BALANCED", "0.12")),
    "risky": float(os.getenv("MAX_DRAWDOWN_RISKY", "0.16")),
    "aggressive": float(os.getenv("MAX_DRAWDOWN_AGGRESSIVE", "0.20")),
}

class RiskEngine:
    def __init__(self):
        self.user_daily_loss = {}  # {user_id: loss_today}
        self.user_peak_equity = {}  # {user_id: peak_equity}
        self.last_reset = datetime.now(timezone.utc).date()
    
    async def check_trade_risk(self, user_id: str, bot_id: str, exchange: str, 
                               proposed_notional: float, risk_mode: str,
                               entry_price: Optional[float] = None,
                               stop_loss_price: Optional[float] = None) -> tuple[bool, str]:
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
        
        # 1. Check daily loss limit
        await self._check_daily_loss(user_id, total_equity)
        daily_loss = self.user_daily_loss.get(user_id, 0)
        max_daily_loss = total_equity * DAILY_MAX_LOSS_PCT
        
        if abs(daily_loss) >= max_daily_loss:
            logger.warning(f"Daily loss limit hit for user {user_id}: {daily_loss}")
            return False, f"Protection mode: Daily loss limit reached (R{max_daily_loss:.2f})"

        # 2. Check global drawdown limit by risk mode/profile
        drawdown_breached, drawdown_reason = self._check_drawdown_limit(
            user_id=user_id,
            current_equity=total_equity,
            risk_mode=risk_mode,
        )
        if drawdown_breached:
            return False, drawdown_reason

        # 3. Fixed-fractional position sizing (1-2% risk-per-trade)
        bot_capital = bot.get("current_capital", 1000)
        risk_fraction = self._resolve_risk_fraction(bot, risk_mode)
        max_notional = self._calculate_max_notional_for_risk(
            bot=bot,
            bot_capital=bot_capital,
            risk_fraction=risk_fraction,
            entry_price=entry_price,
            stop_loss_price=stop_loss_price,
        )
        
        if proposed_notional > max_notional:
            return False, (
                f"Trade size exceeds fixed-fractional risk cap "
                f"(risk={risk_fraction*100:.2f}%, max_notional=R{max_notional:.2f})"
            )
        
        # 4. Check per-asset exposure
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
        
        # 5. Check per-exchange exposure (only if user has multiple exchanges)
        exchanges_used = set(b.get("exchange") for b in user_bots)
        
        if len(exchanges_used) > 1:  # Only enforce if using multiple exchanges
            exchange_capital = sum(b.get("current_capital", 0) for b in user_bots if b.get("exchange") == exchange)
            max_exchange_exposure = total_equity * 0.60  # 60% max per exchange
            
            if exchange_capital > max_exchange_exposure:
                return False, f"Too much exposure on {exchange.upper()} (max 60% of equity)"
        
        # 6. Minimum trade notional (avoid tiny wins)
        min_notional = 10  # R10 minimum (lowered for testing)
        if proposed_notional < min_notional:
            return False, f"Trade too small (min R{min_notional})"
        
        return True, "Risk check passed"

    def _resolve_risk_fraction(self, bot: dict, risk_mode: str) -> float:
        configured = bot.get("fixed_fractional_risk_pct")
        if configured is None:
            configured = {
                "safe": 0.01,
                "balanced": 0.015,
                "risky": 0.018,
                "aggressive": 0.02,
            }.get(str(risk_mode or "").lower(), FIXED_FRACTIONAL_RISK_DEFAULT)
        try:
            configured_val = float(configured)
        except (TypeError, ValueError):
            configured_val = FIXED_FRACTIONAL_RISK_DEFAULT
        return max(FIXED_FRACTIONAL_RISK_MIN, min(FIXED_FRACTIONAL_RISK_MAX, configured_val))

    def _calculate_max_notional_for_risk(
        self,
        bot: dict,
        bot_capital: float,
        risk_fraction: float,
        entry_price: Optional[float] = None,
        stop_loss_price: Optional[float] = None,
    ) -> float:
        if bot_capital <= 0:
            return 0.0

        risk_amount = bot_capital * risk_fraction

        stop_distance_fraction = None
        if entry_price and stop_loss_price and entry_price > 0:
            stop_distance_fraction = abs(entry_price - stop_loss_price) / entry_price

        if not stop_distance_fraction or stop_distance_fraction <= 0:
            default_stop_pct = bot.get("stop_loss_pct", 0.005)
            try:
                stop_distance_fraction = abs(float(default_stop_pct))
            except (TypeError, ValueError):
                stop_distance_fraction = 0.005
            stop_distance_fraction = max(stop_distance_fraction, 0.001)

        max_notional = risk_amount / stop_distance_fraction
        return max(0.0, min(max_notional, bot_capital))

    def _check_drawdown_limit(self, user_id: str, current_equity: float, risk_mode: str) -> tuple[bool, str]:
        if current_equity <= 0:
            return False, ""
        peak_equity = self.user_peak_equity.get(user_id, current_equity)
        if current_equity > peak_equity:
            peak_equity = current_equity
        self.user_peak_equity[user_id] = peak_equity
        drawdown = max(0.0, min(1.0, (peak_equity - current_equity) / peak_equity)) if peak_equity > 0 else 0.0
        limit = MAX_DRAWDOWN_BY_MODE.get(str(risk_mode or "").lower(), MAX_DRAWDOWN_BY_MODE["balanced"])
        if drawdown >= limit:
            return True, (
                f"Protection mode: drawdown limit reached "
                f"({drawdown*100:.2f}% >= {limit*100:.2f}%)"
            )
        return False, ""
    
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
