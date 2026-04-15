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

# Minimum trade notional in ZAR.  Default is 50 — small enough for all
# supported pairs but large enough to cover round-trip fees + slippage on Luno
# (0.4% × 2 × R50 = R0.40 in fees alone; R10 would net essentially zero).
# Override with MIN_TRADE_NOTIONAL_ZAR env var if needed.
MIN_TRADE_NOTIONAL_ZAR = float(os.getenv("MIN_TRADE_NOTIONAL_ZAR", "50"))

MAX_DRAWDOWN_BY_MODE = {
    "safe": float(os.getenv("MAX_DRAWDOWN_SAFE", "0.08")),
    "balanced": float(os.getenv("MAX_DRAWDOWN_BALANCED", "0.12")),
    "risky": float(os.getenv("MAX_DRAWDOWN_RISKY", "0.16")),
    "aggressive": float(os.getenv("MAX_DRAWDOWN_AGGRESSIVE", "0.20")),
}

# MongoDB collection name used to persist per-user peak-equity records so
# the drawdown circuit breaker survives service restarts.
_PEAK_EQUITY_COLLECTION = "risk_peak_equity"


class RiskEngine:
    def __init__(self):
        self.user_daily_loss = {}  # {user_id: loss_today} — rehydrated from DB each call
        self.user_peak_equity = {}  # {user_id: peak_equity} — in-memory cache, persisted to MongoDB
        self.last_reset = datetime.now(timezone.utc).date()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def check_trade_risk(self, user_id: str, bot_id: str, exchange: str,
                               proposed_notional: float, risk_mode: str,
                               entry_price: Optional[float] = None,
                               stop_loss_price: Optional[float] = None) -> tuple[bool, str]:
        """Comprehensive risk check before allowing trade"""
        
        # Get bot details
        bot = await db.bots_collection.find_one({"id": bot_id}, {"_id": 0})
        if not bot:
            return False, "Bot not found"
        
        # Get user's total equity — use canonical ZAR conversion (not raw sum of mixed currencies)
        user_bots = await db.bots_collection.find({"user_id": user_id}, {"_id": 0}).to_list(100)
        from services.reconciliation import compute_equity_zar
        total_equity, equity_breakdown = compute_equity_zar(user_bots)
        
        if total_equity <= 0:
            return False, "No capital available"
        
        # 1. Check daily loss limit — always recalculate from closed trades so the
        #    limit is correct even after a service restart mid-day.
        await self._check_daily_loss(user_id, total_equity)
        daily_loss = self.user_daily_loss.get(user_id, 0)
        max_daily_loss = total_equity * DAILY_MAX_LOSS_PCT
        
        if abs(daily_loss) >= max_daily_loss:
            logger.warning(f"Daily loss limit hit for user {user_id}: {daily_loss}")
            return False, f"Protection mode: Daily loss limit reached (R{max_daily_loss:.2f})"

        # 2. Check global drawdown limit by risk mode/profile
        drawdown_breached, drawdown_reason = await self._check_drawdown_limit(
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
        # Get all user's trades to calculate current exposure
        recent_open_trades = await db.trades_collection.find({
            "user_id": user_id,
            "status": {"$in": ["open", "pending"]},  # Only open positions
            "timestamp": {"$gte": (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()}
        }, {"_id": 0}).to_list(1000)
        
        # Calculate per-asset exposure (convert to ZAR for comparison)
        from services.fx_normalizer import get_quote_currency, get_fx_rate
        usdt_zar_rate, _ = get_fx_rate("USDT", "ZAR")
        asset_exposure: dict = {}
        for trade in recent_open_trades:
            pair = trade.get('pair', '')
            trade_exchange = (trade.get('exchange') or '').lower()
            if '/' in pair:
                asset = pair.split('/')[0]  # e.g., BTC from BTC/ZAR
                raw_value = trade.get('entry_price', 0) * trade.get('amount', 0)
                # Convert trade value to ZAR if quote is USDT
                trade_quote = get_quote_currency(trade_exchange, pair)
                if trade_quote != "ZAR":
                    raw_value = raw_value * usdt_zar_rate
                asset_exposure[asset] = asset_exposure.get(asset, 0) + raw_value
        
        # Check if any single asset exceeds 35% of total equity (both in ZAR)
        for asset, exposure in asset_exposure.items():
            exposure_pct = (exposure / total_equity) if total_equity > 0 else 0
            if exposure_pct > 0.35:
                return False, f"Too much exposure to {asset} ({exposure_pct*100:.1f}% > 35% limit)"
        
        # 5. Check per-exchange exposure (only if user has multiple exchanges)
        # Use canonical ZAR equity per exchange (not raw mixed-currency sum)
        exchanges_used = {b.get("exchange") for b in user_bots if b.get("exchange")}

        if len(exchanges_used) > 1:  # Only enforce if using multiple exchanges
            exchange_bots = [b for b in user_bots if b.get("exchange") == exchange]
            exchange_equity_zar, _ = compute_equity_zar(exchange_bots)
            # Exposure limit:
            #  - 2-exchange setups (e.g. Luno + Binance): 85% — one exchange can
            #    legitimately hold most of the capital in a paired setup.
            #  - 3+ exchange setups: 70% — wider diversification is expected.
            # Paper mode gets a higher ceiling to avoid deadlocking a small fleet.
            _is_paper = (bot or {}).get("trading_mode", "paper") == "paper"
            if len(exchanges_used) == 2:
                max_exchange_exposure = total_equity * (0.90 if _is_paper else 0.85)
            else:
                max_exchange_exposure = total_equity * (0.75 if _is_paper else 0.70)

            if exchange_equity_zar > max_exchange_exposure:
                _pct = round(exchange_equity_zar / total_equity * 100, 1)
                _limit = round(max_exchange_exposure / total_equity * 100, 1)
                return False, f"Too much exposure on {exchange.upper()} ({_pct}% > {_limit}% limit)"
        
        # 6. Minimum trade notional — configurable via MIN_TRADE_NOTIONAL_ZAR env var
        if proposed_notional < MIN_TRADE_NOTIONAL_ZAR:
            return False, f"Trade too small (min R{MIN_TRADE_NOTIONAL_ZAR:.0f})"
        
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

    # ------------------------------------------------------------------
    # Drawdown — persisted to MongoDB so restarts don't reset the high-water mark
    # ------------------------------------------------------------------

    async def _load_peak_equity(self, user_id: str) -> Optional[float]:
        """Load persisted peak equity from MongoDB."""
        try:
            collection = getattr(db, _PEAK_EQUITY_COLLECTION, None)
            if collection is None:
                # Fallback: access by attribute name via db.db handle
                if db.db is not None:
                    collection = db.db[_PEAK_EQUITY_COLLECTION]
                else:
                    return None
            doc = await collection.find_one({"user_id": user_id}, {"_id": 0, "peak_equity": 1})
            if doc:
                return float(doc["peak_equity"])
        except Exception as e:
            logger.debug("Could not load peak equity for %s: %s", user_id, e)
        return None

    async def _save_peak_equity(self, user_id: str, peak_equity: float) -> None:
        """Persist peak equity to MongoDB."""
        try:
            collection = getattr(db, _PEAK_EQUITY_COLLECTION, None)
            if collection is None:
                if db.db is not None:
                    collection = db.db[_PEAK_EQUITY_COLLECTION]
                else:
                    return
            await collection.update_one(
                {"user_id": user_id},
                {"$set": {"peak_equity": peak_equity, "updated_at": datetime.now(timezone.utc).isoformat()}},
                upsert=True,
            )
        except Exception as e:
            logger.warning("Could not persist peak equity for %s: %s", user_id, e)

    async def _check_drawdown_limit(self, user_id: str, current_equity: float, risk_mode: str) -> tuple[bool, str]:
        if current_equity <= 0:
            return False, "Drawdown check skipped: current equity is zero or negative"

        # Load cached value; on first call after restart, fetch from MongoDB.
        if user_id not in self.user_peak_equity:
            persisted = await self._load_peak_equity(user_id)
            self.user_peak_equity[user_id] = persisted if persisted is not None else current_equity

        peak_equity = self.user_peak_equity[user_id]
        if current_equity > peak_equity:
            peak_equity = current_equity
            self.user_peak_equity[user_id] = peak_equity
            await self._save_peak_equity(user_id, peak_equity)

        raw_drawdown = (peak_equity - current_equity) / peak_equity
        drawdown = max(0.0, min(1.0, raw_drawdown))
        limit = MAX_DRAWDOWN_BY_MODE.get(str(risk_mode or "").lower(), MAX_DRAWDOWN_BY_MODE["balanced"])
        if drawdown >= limit:
            return True, (
                f"Protection mode: drawdown limit reached "
                f"({drawdown*100:.2f}% >= {limit*100:.2f}%)"
            )
        return False, ""

    # ------------------------------------------------------------------
    # Daily loss — always recalculated from closed-trade history so the
    # counter is correct even after a service restart mid-day.
    # ------------------------------------------------------------------

    async def _check_daily_loss(self, user_id: str, total_equity: float):
        """Calculate today's realized loss using REALIZED net PnL only."""
        today = datetime.now(timezone.utc).date()

        # Reset in-memory cache if the calendar day has rolled over.
        if today > self.last_reset:
            self.user_daily_loss.clear()
            self.last_reset = today

        # Always recompute from the database so a mid-day restart picks up the
        # correct cumulative loss rather than starting fresh from zero.
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
