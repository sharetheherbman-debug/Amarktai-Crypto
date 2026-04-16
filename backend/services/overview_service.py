"""
Overview Service - Single Source of Truth for Dashboard Metrics
================================================================

This service provides ONE canonical snapshot of all system metrics:
- Profit metrics (total, today, gross PnL, net PnL)
- Fee metrics (total fees, today fees)
- Trade metrics (today trades, total trades, win rate)
- Bot metrics (active, paused, training, quarantine)
- Capital metrics (equity, required capital by platform)
- Market prices (BTC/ZAR, ETH/ZAR, XRP/ZAR with source and timestamp)
- Risk metrics (daily loss lock state)

ALL dashboard tiles MUST use this service. No duplicated calculations.

Currency rule:
- ALL internal aggregation is performed in ZAR (the canonical internal currency).
- Mixed-currency portfolios (Luno ZAR + Binance USDT) are normalised via
  services.fx_normalizer before any summing occurs.
- The final snapshot is then optionally re-expressed in the user's chosen
  display_currency (ZAR, USD, GBP, EUR) via to_display_currency().
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Optional, List
import config
import database as db
from config.platforms import SUPPORTED_PLATFORMS, get_platform_config
from utils.trade_utils import parse_trade_timestamp
from utils.bot_state import normalize_bot_state, is_active_bot
from services.fx_normalizer import (
    get_quote_currency as _gqc,
    get_fx_rate as _gfr,
    to_display_currency as _to_display,
    SUPPORTED_DISPLAY_CURRENCIES,
)
from services.reconciliation import compute_equity_zar

logger = logging.getLogger(__name__)


class OverviewService:
    """Centralized overview metrics computation service"""
    
    async def get_snapshot(self, user_id: str, display_currency: str = "ZAR") -> Dict:
        """Get comprehensive overview snapshot for dashboard.

        This is the SINGLE SOURCE OF TRUTH for all dashboard metrics.
        Returns ONE complete snapshot with all data needed by frontend.

        Args:
            user_id: User ID to compute metrics for
            display_currency: ISO currency code for presentation (ZAR/USD/GBP/EUR).
                              Defaults to "ZAR".  All values are first aggregated
                              internally in ZAR, then converted to display_currency
                              before being returned.

        Returns:
            Dict containing profit, fee, trade, capital, bot, and market metrics.
            All monetary values are in *display_currency*.
            The response includes "display_currency" and "fx_metadata" fields.
        """
        try:
            now = datetime.now(timezone.utc)
            today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            dc = str(display_currency or "ZAR").upper()
            if dc not in SUPPORTED_DISPLAY_CURRENCIES:
                logger.warning("Unsupported display_currency %s; defaulting to ZAR", dc)
                dc = "ZAR"

            # Get user info for system modes and lock status
            user = await db.users_collection.find_one({"id": user_id}, {"_id": 0})
            if not user:
                # Return empty snapshot for non-existent user
                return self._empty_snapshot(now)

            # Get all user's bots (exclude deleted) — same filter as /api/bots/status
            # to guarantee counts are consistent across all dashboard tiles.
            bots = await db.bots_collection.find({
                "user_id": user_id,
                "status": {"$nin": ["deleted", "marked_for_deletion"]},
                "deleted": {"$ne": True},
                "is_deleted": {"$ne": True},
                "deleted_at": {"$exists": False},
            }, {"_id": 0}).to_list(1000)

            bot_ids = [b["id"] for b in bots] if bots else []

            # ==================================================================
            # PROFIT METRICS — all values in ZAR internally
            # ==================================================================
            profit_metrics = await self._compute_profit_metrics(bot_ids, today_start)

            # ==================================================================
            # FEE METRICS — all values in ZAR internally
            # ==================================================================
            fee_metrics = await self._compute_fee_metrics(bot_ids, today_start)

            # ==================================================================
            # TRADE METRICS
            # ==================================================================
            trade_metrics = await self._compute_trade_metrics(bot_ids, today_start)

            # ==================================================================
            # BOT METRICS
            # ==================================================================
            bot_metrics = self._compute_bot_metrics(bots)

            # ==================================================================
            # CAPITAL METRICS — all values in ZAR internally
            # ==================================================================
            capital_metrics = self._compute_capital_metrics(bots)

            # ==================================================================
            # DAILY LOSS LOCK STATE
            # ==================================================================
            daily_loss_lock = {
                "active": user.get("daily_loss_lock_active", False),
                "reason": user.get("daily_loss_locked_reason"),
                "locked_at": user.get("daily_loss_locked_at"),
                "loss_pct": user.get("daily_loss_pct", 0),
                "can_reset": user.get("daily_loss_lock_active", False)
            }

            # ==================================================================
            # MARKET PRICES (BTC/ZAR, ETH/ZAR, XRP/ZAR)
            # ==================================================================
            market_prices = await self._get_market_prices()

            # ==================================================================
            # TRADING MODE FLAGS — canonical source is system_modes_collection,
            # NOT the user document.  Reading from the user doc produces stale
            # values because the dashboard toggle writes to system_modes only.
            # ==================================================================
            _modes_doc = await db.system_modes_collection.find_one(
                {"user_id": user_id}, {"_id": 0}
            ) if db.system_modes_collection is not None else None
            _modes_doc = _modes_doc or {}
            trading_mode_flags = {
                "paper_trading": bool(_modes_doc.get("paperTrading", True)),
                "live_trading": bool(_modes_doc.get("liveTrading", False)),
                "autopilot": bool(_modes_doc.get("autopilot", False)),
                "bodyguard": bool(_modes_doc.get("bodyguard", user.get("bodyguard_enabled", True))),
                "learning": bool(_modes_doc.get("learning", user.get("learning_enabled", True))),
                "emergency_stop": bool(_modes_doc.get("emergencyStop", False)),
            }

            # ==================================================================
            # CONVERT ZAR TOTALS → display_currency
            # ==================================================================
            zar_rate, zar_source = _gfr("ZAR", dc)

            def _cvt(zar_val):
                if zar_val is None:
                    return None
                # Re-use the already-fetched rate to avoid a redundant FX lookup
                return round(float(zar_val) * zar_rate, 2)

            # ==================================================================
            # REINVESTMENT / GROWTH METADATA
            # next_reinvest: ISO timestamp of next profit-milestone spawn window.
            # last_rebalance: ISO timestamp of the most recent milestone spawn.
            # These power the "Next Reinvest" and "Last Rebalance" dashboard tiles.
            # ==================================================================
            next_reinvest: Optional[str] = None
            last_rebalance: Optional[str] = None
            capital_growth_pool: float = 0.0
            try:
                if db.autopilot_milestones_collection is not None:
                    _last_ms = await db.autopilot_milestones_collection.find_one(
                        {"user_id": user_id, "status": "spawned"},
                        {"_id": 0, "triggered_at": 1},
                        sort=[("triggered_at", -1)],
                    )
                    if _last_ms:
                        last_rebalance = _last_ms.get("triggered_at")
                    # next_reinvest = last spawn time + cooldown minutes
                    if last_rebalance:
                        try:
                            # Handle both 'Z' and '+00:00' timezone suffixes from MongoDB
                            _ts = str(last_rebalance)
                            if _ts.endswith("Z"):
                                _ts = _ts[:-1] + "+00:00"
                            _last_dt = datetime.fromisoformat(_ts)
                            _next_dt = _last_dt + timedelta(minutes=float(config.AUTO_SPAWN_COOLDOWN_MINUTES))
                            next_reinvest = _next_dt.isoformat()
                        except Exception:
                            pass
                    # capital_growth_pool: sum of profits routed to growth pool
                    # (written by autopilot_growth when MAX_BOTS_REACHED)
                    _pool_doc = await db.autopilot_milestones_collection.find_one(
                        {"user_id": user_id, "type": "capital_growth_pool"},
                        {"_id": 0, "total_zar": 1},
                    )
                    if _pool_doc:
                        capital_growth_pool = float(_pool_doc.get("total_zar", 0) or 0)
            except Exception as _re:
                logger.debug("Could not compute reinvest metadata: %s", _re)

            # ==================================================================
            # ASSEMBLE COMPLETE SNAPSHOT
            # ==================================================================
            return {
                # Profit metrics (in display_currency)
                "total_profit": _cvt(profit_metrics["total_net_pnl"]),
                "today_profit": _cvt(profit_metrics["today_net_pnl"]),
                "gross_pnl": _cvt(profit_metrics["gross_pnl"]),
                "net_pnl": _cvt(profit_metrics["net_pnl"]),

                # Fee metrics (in display_currency)
                "total_fees": _cvt(fee_metrics["total_fees"]),
                "today_fees": _cvt(fee_metrics["today_fees"]),

                # Trade metrics (counts — no currency conversion needed)
                "trades_today": trade_metrics["trades_today"],
                "trades_total": trade_metrics["trades_total"],
                "win_rate": trade_metrics["win_rate"],

                # Capital metrics (in display_currency)
                "equity": _cvt(capital_metrics["equity"]),
                "required_capital_total": _cvt(capital_metrics["required_capital_total"]),
                "required_capital_by_platform": {
                    k: _cvt(v)
                    for k, v in capital_metrics["required_capital_by_platform"].items()
                },

                # Bot metrics
                "bots_active": bot_metrics["active"],
                "bots_paused": bot_metrics["paused"],
                "bots_training": bot_metrics["training"],
                "bots_quarantine": bot_metrics["quarantine"],
                "bots_total": bot_metrics["total"],
                # Bot-type breakdown — same predicate as /api/bots/status by_type
                "bots_by_type": bot_metrics.get("by_type", {"normal": 0, "scalper": 0}),

                # Risk metrics
                "daily_loss_lock": daily_loss_lock,

                # Market data
                "market_prices": market_prices,

                # System flags
                "trading_mode_flags": trading_mode_flags,

                # Reinvestment / growth metadata
                "next_reinvest": next_reinvest,
                "last_rebalance": last_rebalance,
                "capital_growth_pool": _cvt(capital_growth_pool),

                # Display currency metadata
                "display_currency": dc,
                "fx_metadata": {
                    "zar_to_display_rate": round(zar_rate, 6),
                    "zar_to_display_source": zar_source,
                    "internal_currency": "ZAR",
                },

                # Metadata
                "timestamp": now.isoformat(),
                "data_source": "overview_service"
            }

        except Exception as e:
            logger.error(f"Overview snapshot error for user {user_id}: {e}", exc_info=True)
            return self._empty_snapshot(datetime.now(timezone.utc))
    
    async def _compute_profit_metrics(self, bot_ids: List[str], today_start: datetime) -> Dict:
        """Compute profit metrics, normalised to ZAR display currency.

        Uses:
        - realized_pnl_zar (primary, set by enrich_trade_pnl_fields — always ZAR)
        - Falls back to net_pnl × fx_rate(quote_currency) for older trades
        - gross_pnl is also converted via the trade's quote_currency
        """
        if not bot_ids:
            return {
                "total_net_pnl": 0.0,
                "today_net_pnl": 0.0,
                "gross_pnl": 0.0,
                "net_pnl": 0.0
            }
        
        # Get all closed trades — include exchange/quote_currency for FX conversion
        all_trades = await db.trades_collection.find({
            "bot_id": {"$in": bot_ids},
            "status": "closed"
        }, {
            "_id": 0,
            "net_pnl": 1,
            "profit_loss": 1,
            "gross_pnl": 1,
            "realized_pnl_zar": 1,      # Preferred: pre-converted ZAR value
            "exchange": 1,
            "quote_currency": 1,
            "timestamp": 1
        }).to_list(100000)
        
        total_net_pnl = 0.0
        total_gross_pnl = 0.0
        today_net_pnl = 0.0
        
        for trade in all_trades:
            exchange = trade.get("exchange", "")
            qc = trade.get("quote_currency") or _gqc(exchange, "")
            rate, _ = _gfr(qc, "ZAR")

            # ── Net PnL: prefer pre-converted ZAR value; fall back to on-the-fly conversion ──
            net_pnl_zar = trade.get("realized_pnl_zar")
            if net_pnl_zar is None:
                raw_pnl = float(trade.get("net_pnl", trade.get("profit_loss", 0)) or 0)
                net_pnl_zar = raw_pnl * rate

            # ── Gross PnL: prefer gross_pnl, fall back to net_pnl, then profit_loss ──
            raw_gross_pnl = trade.get("gross_pnl")
            if raw_gross_pnl is None:
                raw_gross_pnl = trade.get("net_pnl", trade.get("profit_loss", 0))
            gross_pnl_zar = float(raw_gross_pnl or 0) * rate
            
            total_net_pnl += net_pnl_zar
            total_gross_pnl += gross_pnl_zar
            
            # Check if trade is from today
            trade_time = trade.get("timestamp", "")
            if trade_time and trade_time >= today_start.isoformat():
                today_net_pnl += net_pnl_zar
        
        return {
            "total_net_pnl": round(total_net_pnl, 2),
            "today_net_pnl": round(today_net_pnl, 2),
            "gross_pnl": round(total_gross_pnl, 2),
            "net_pnl": round(total_net_pnl, 2)
        }
    
    async def _compute_fee_metrics(self, bot_ids: List[str], today_start: datetime) -> Dict:
        """Compute fee metrics normalised to ZAR display currency.

        Uses:
        - fee_display_zar (primary, set by enrich_trade_pnl_fields — always ZAR)
        - Falls back to fee_amount × fx_rate(quote_currency) for older trades
        """
        if not bot_ids:
            return {
                "total_fees": 0.0,
                "today_fees": 0.0
            }
        
        # Get all closed trades — include exchange/quote_currency for FX conversion
        all_trades = await db.trades_collection.find({
            "bot_id": {"$in": bot_ids},
            "status": "closed"
        }, {
            "_id": 0,
            "fee_amount": 1,
            "fees": 1,
            "fee": 1,
            "fee_display_zar": 1,   # Preferred: pre-converted ZAR value
            "exchange": 1,
            "quote_currency": 1,
            "timestamp": 1
        }).to_list(100000)
        
        # Calculate totals using ZAR normalisation
        total_fees = 0.0
        today_fees = 0.0
        
        for trade in all_trades:
            exchange = trade.get("exchange", "")
            qc = trade.get("quote_currency") or _gqc(exchange, "")
            rate, _ = _gfr(qc, "ZAR")

            # Prefer pre-converted ZAR fee value; fall back to on-the-fly conversion
            fee_zar = trade.get("fee_display_zar")
            if fee_zar is None:
                raw_fee = float(trade.get("fee_amount", trade.get("fees", trade.get("fee", 0))) or 0)
                fee_zar = raw_fee * rate
            
            total_fees += fee_zar
            
            # Check if trade is from today
            trade_time = parse_trade_timestamp(trade)
            if trade_time >= today_start:
                today_fees += fee_zar
        
        return {
            "total_fees": round(total_fees, 2),
            "today_fees": round(today_fees, 2)
        }
    
    async def _compute_trade_metrics(self, bot_ids: List[str], today_start: datetime) -> Dict:
        """Compute trade count and win rate metrics"""
        if not bot_ids:
            return {
                "trades_today": 0,
                "trades_total": 0,
                "win_rate": 0.0
            }
        
        # Get all closed trades
        all_trades = await db.trades_collection.find({
            "bot_id": {"$in": bot_ids},
            "status": "closed"
        }, {
            "_id": 0,
            "net_pnl": 1,
            "profit_loss": 1,
            "timestamp": 1
        }).to_list(100000)
        
        trades_total = len(all_trades)
        trades_today = 0
        winning_trades = 0
        
        for trade in all_trades:
            # Check if trade is from today
            trade_time = parse_trade_timestamp(trade)
            if trade_time >= today_start:
                trades_today += 1
            
            # Check if trade is winning (use canonical field)
            pnl = trade.get("net_pnl", trade.get("profit_loss", 0))
            if pnl > 0:
                winning_trades += 1
        
        # Calculate win rate
        win_rate = (winning_trades / trades_total * 100) if trades_total > 0 else 0.0
        
        return {
            "trades_today": trades_today,
            "trades_total": trades_total,
            "win_rate": round(win_rate, 1)
        }
    
    def _compute_bot_metrics(self, bots: List[Dict]) -> Dict:
        """Compute bot counts by status and type"""
        normalized = [normalize_bot_state(bot) for bot in bots]
        active = sum(1 for b in normalized if b.get("active"))
        paused = sum(1 for b in normalized if b.get("paused"))
        training = sum(1 for b in normalized if b.get("status") == "training")
        quarantine = sum(1 for b in normalized if b.get("status") in ["quarantined", "quarantine"])

        # Bot-type breakdown (mirrors /api/bots/status by_type counts)
        normal_total = sum(1 for b in bots if (b.get("bot_type") or "normal").lower() != "scalper")
        scalper_total = sum(1 for b in bots if (b.get("bot_type") or "normal").lower() == "scalper")

        return {
            "active": active,
            "paused": paused,
            "training": training,
            "quarantine": quarantine,
            "total": len(bots),
            "by_type": {
                "normal": normal_total,
                "scalper": scalper_total,
            },
        }
    
    def _compute_capital_metrics(self, bots: List[Dict]) -> Dict:
        """Compute equity and required capital metrics, all values in ZAR.

        Uses:
        - compute_equity_zar() from reconciliation for equity (prefers
          canonical_base_capital_zar then falls back to current_capital × fx_rate)
        - canonical_base_capital_zar for required capital (stored at bot creation)
          with fallback to initial_capital × fx_rate(quote_currency)
        """
        # Equity = sum of current capital across all active bots, in ZAR
        active_bots = [b for b in bots if is_active_bot(b)]
        equity_zar, _equity_breakdown = compute_equity_zar(active_bots)
        
        # Required capital = sum of original ZAR economic base across all bots
        required_capital_total = 0.0
        for b in bots:
            base_zar = b.get("canonical_base_capital_zar")
            if base_zar is not None:
                required_capital_total += float(base_zar)
            else:
                # Fallback: convert initial_capital using quote_currency
                initial = float(b.get("initial_capital", 0) or 0)
                qc = b.get("quote_currency") or _gqc(b.get("exchange", ""), "")
                rate, _ = _gfr(qc, "ZAR")
                required_capital_total += initial * rate
        
        # Required capital by platform (ZAR)
        required_capital_by_platform = {}
        for platform in SUPPORTED_PLATFORMS:
            platform_bots = [b for b in bots if b.get("platform") == platform]
            platform_capital = 0.0
            for b in platform_bots:
                base_zar = b.get("canonical_base_capital_zar")
                if base_zar is not None:
                    platform_capital += float(base_zar)
                else:
                    initial = float(b.get("initial_capital", 0) or 0)
                    qc = b.get("quote_currency") or _gqc(b.get("exchange", ""), "")
                    rate, _ = _gfr(qc, "ZAR")
                    platform_capital += initial * rate
            required_capital_by_platform[platform] = round(platform_capital, 2)
        
        return {
            "equity": equity_zar,
            "required_capital_total": round(required_capital_total, 2),
            "required_capital_by_platform": required_capital_by_platform
        }
    
    async def _get_market_prices(self) -> Dict:
        """Get live market prices for BTC/ZAR, ETH/ZAR, XRP/ZAR
        
        Returns prices with % change, source, and timestamp.
        Falls back to last known prices if live fetch fails.
        """
        try:
            # Try to get live prices from Luno (primary ZAR exchange)
            prices = await self._fetch_luno_prices()
            if prices:
                return prices
        except Exception as e:
            logger.warning(f"Failed to fetch live Luno prices: {e}")
        
        # Fallback to static/cached prices (will be updated in Phase 4)
        return {
            "BTC/ZAR": {
                "price": 0.0,
                "change_pct": 0.0,
                "change_24h": 0.0,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "source": "unavailable"
            },
            "ETH/ZAR": {
                "price": 0.0,
                "change_pct": 0.0,
                "change_24h": 0.0,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "source": "unavailable"
            },
            "XRP/ZAR": {
                "price": 0.0,
                "change_pct": 0.0,
                "change_24h": 0.0,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "source": "unavailable"
            }
        }
    
    async def _fetch_luno_prices(self) -> Optional[Dict]:
        """Fetch live prices from Luno via shared TTL cache.

        Returns proper price data structure or None.
        Uses luno_ticker_cache to avoid repeated HTTP calls from multiple
        subsystems that all call this method in the same polling window.
        """
        try:
            from services import luno_ticker_cache as _ticker_cache
            from services.price_snapshot_service import record_snapshot

            prices = {}
            pairs = [("XBTZAR", "BTC/ZAR"), ("ETHZAR", "ETH/ZAR"), ("XRPZAR", "XRP/ZAR")]

            for luno_pair, display_pair in pairs:
                try:
                    ticker = await _ticker_cache.get_ticker(luno_pair)
                    if ticker is None:
                        continue
                    last_trade = ticker.get("last_trade", 0.0)
                    change_pct, _window = await record_snapshot(display_pair, last_trade)
                    prices[display_pair] = {
                        "price": round(last_trade, 2),
                        "change_pct": round(change_pct, 2),
                        "change_24h": round(change_pct, 2),
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "source": ticker.get("source", "luno_public"),
                    }
                except Exception as e:
                    logger.warning(f"Failed to fetch {display_pair}: {e}")
                    continue

            return prices if prices else None

        except Exception as e:
            logger.error(f"Luno price fetch error: {e}")
            return None
    
    def _empty_snapshot(self, now: datetime) -> Dict:
        """Return empty snapshot when user not found or error occurs"""
        return {
            "total_profit": 0.0,
            "today_profit": 0.0,
            "gross_pnl": 0.0,
            "net_pnl": 0.0,
            "total_fees": 0.0,
            "today_fees": 0.0,
            "trades_today": 0,
            "trades_total": 0,
            "win_rate": 0.0,
            "equity": 0.0,
            "required_capital_total": 0.0,
            "required_capital_by_platform": {p: 0.0 for p in SUPPORTED_PLATFORMS},
            "bots_active": 0,
            "bots_paused": 0,
            "bots_training": 0,
            "bots_quarantine": 0,
            "daily_loss_lock": {
                "active": False,
                "reason": None,
                "locked_at": None,
                "loss_pct": 0,
                "can_reset": False
            },
            "market_prices": {
                "BTC/ZAR": {"price": 0.0, "change_pct": 0.0, "timestamp": now.isoformat(), "source": "unavailable"},
                "ETH/ZAR": {"price": 0.0, "change_pct": 0.0, "timestamp": now.isoformat(), "source": "unavailable"},
                "XRP/ZAR": {"price": 0.0, "change_pct": 0.0, "timestamp": now.isoformat(), "source": "unavailable"}
            },
            "trading_mode_flags": {
                "paper_trading": False,
                "live_trading": False,
                "autopilot": False,
                "bodyguard": False,
                "learning": False,
                "emergency_stop": False
            },
            "timestamp": now.isoformat(),
            "data_source": "overview_service"
        }


# Singleton instance
overview_service = OverviewService()
