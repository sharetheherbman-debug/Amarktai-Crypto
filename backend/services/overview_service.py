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
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Optional, List
import database as db
from config.platforms import SUPPORTED_PLATFORMS, get_platform_config

logger = logging.getLogger(__name__)


class OverviewService:
    """Centralized overview metrics computation service"""
    
    async def get_snapshot(self, user_id: str) -> Dict:
        """Get comprehensive overview snapshot for dashboard
        
        This is the SINGLE SOURCE OF TRUTH for all dashboard metrics.
        Returns ONE complete snapshot with all data needed by frontend.
        
        Args:
            user_id: User ID to compute metrics for
            
        Returns:
            Dict containing:
            - total_profit: Total net PnL across all trades
            - today_profit: Net PnL from today's trades
            - gross_pnl: Total gross profit before fees
            - net_pnl: Total net profit after fees
            - total_fees: Total fees paid across all trades
            - today_fees: Fees paid today
            - trades_today: Number of trades today
            - trades_total: Total number of trades
            - win_rate: Percentage of winning trades
            - equity: Current total capital across all bots
            - required_capital_total: Total capital required for all bots
            - required_capital_by_platform: Capital required per platform
            - bots_active: Count of active bots
            - bots_paused: Count of paused bots
            - bots_training: Count of training bots
            - bots_quarantine: Count of quarantined bots
            - daily_loss_lock: Daily loss lock state
            - market_prices: BTC/ZAR, ETH/ZAR, XRP/ZAR with % change, source, timestamp
            - trading_mode_flags: System mode flags
            - timestamp: When snapshot was generated
        """
        try:
            now = datetime.now(timezone.utc)
            today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            
            # Get user info for system modes and lock status
            user = await db.users_collection.find_one({"id": user_id}, {"_id": 0})
            if not user:
                # Return empty snapshot for non-existent user
                return self._empty_snapshot(now)
            
            # Get all user's bots (exclude deleted)
            bots = await db.bots_collection.find({
                "user_id": user_id,
                "status": {"$ne": "deleted"},
                "deleted_at": {"$exists": False}
            }, {"_id": 0}).to_list(1000)
            
            bot_ids = [b["id"] for b in bots] if bots else []
            
            # ==================================================================
            # PROFIT METRICS (using canonical field normalization)
            # ==================================================================
            profit_metrics = await self._compute_profit_metrics(bot_ids, today_start)
            
            # ==================================================================
            # FEE METRICS (using canonical field normalization)
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
            # CAPITAL METRICS
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
                "can_reset": user.get("daily_loss_lock_active", False)  # Only if locked
            }
            
            # ==================================================================
            # MARKET PRICES (BTC/ZAR, ETH/ZAR, XRP/ZAR)
            # ==================================================================
            market_prices = await self._get_market_prices()
            
            # ==================================================================
            # TRADING MODE FLAGS
            # ==================================================================
            trading_mode_flags = {
                "paper_trading": user.get("system_mode") in ["testing", "paper"],
                "live_trading": user.get("system_mode") == "live_trading",
                "autopilot": user.get("autopilot_enabled", False),
                "bodyguard": user.get("bodyguard_enabled", True),
                "learning": user.get("learning_enabled", True),
                "emergency_stop": user.get("emergency_stop", False)
            }
            
            # ==================================================================
            # ASSEMBLE COMPLETE SNAPSHOT
            # ==================================================================
            return {
                # Profit metrics
                "total_profit": profit_metrics["total_net_pnl"],
                "today_profit": profit_metrics["today_net_pnl"],
                "gross_pnl": profit_metrics["gross_pnl"],
                "net_pnl": profit_metrics["net_pnl"],
                
                # Fee metrics
                "total_fees": fee_metrics["total_fees"],
                "today_fees": fee_metrics["today_fees"],
                
                # Trade metrics
                "trades_today": trade_metrics["trades_today"],
                "trades_total": trade_metrics["trades_total"],
                "win_rate": trade_metrics["win_rate"],
                
                # Capital metrics
                "equity": capital_metrics["equity"],
                "required_capital_total": capital_metrics["required_capital_total"],
                "required_capital_by_platform": capital_metrics["required_capital_by_platform"],
                
                # Bot metrics
                "bots_active": bot_metrics["active"],
                "bots_paused": bot_metrics["paused"],
                "bots_training": bot_metrics["training"],
                "bots_quarantine": bot_metrics["quarantine"],
                
                # Risk metrics
                "daily_loss_lock": daily_loss_lock,
                
                # Market data
                "market_prices": market_prices,
                
                # System flags
                "trading_mode_flags": trading_mode_flags,
                
                # Metadata
                "timestamp": now.isoformat(),
                "data_source": "overview_service"
            }
            
        except Exception as e:
            logger.error(f"Overview snapshot error for user {user_id}: {e}", exc_info=True)
            # Return empty snapshot on error
            return self._empty_snapshot(datetime.now(timezone.utc))
    
    async def _compute_profit_metrics(self, bot_ids: List[str], today_start: datetime) -> Dict:
        """Compute profit metrics using canonical field normalization
        
        Uses:
        - net_pnl (primary) → fallback profit_loss
        - gross_pnl if available
        """
        if not bot_ids:
            return {
                "total_net_pnl": 0.0,
                "today_net_pnl": 0.0,
                "gross_pnl": 0.0,
                "net_pnl": 0.0
            }
        
        # Get all closed trades
        all_trades = await db.trades_collection.find({
            "bot_id": {"$in": bot_ids},
            "status": "closed"
        }, {
            "_id": 0,
            "net_pnl": 1,
            "profit_loss": 1,
            "gross_pnl": 1,
            "timestamp": 1
        }).to_list(100000)
        
        # Calculate totals using canonical field normalization
        total_net_pnl = 0.0
        total_gross_pnl = 0.0
        today_net_pnl = 0.0
        
        for trade in all_trades:
            # Use net_pnl if available, fallback to profit_loss
            net_pnl = trade.get("net_pnl", trade.get("profit_loss", 0))
            gross_pnl = trade.get("gross_pnl", net_pnl)  # Fallback to net if gross not available
            
            total_net_pnl += net_pnl
            total_gross_pnl += gross_pnl
            
            # Check if trade is from today
            trade_time = trade.get("timestamp", "")
            if trade_time and trade_time >= today_start.isoformat():
                today_net_pnl += net_pnl
        
        return {
            "total_net_pnl": round(total_net_pnl, 2),
            "today_net_pnl": round(today_net_pnl, 2),
            "gross_pnl": round(total_gross_pnl, 2),
            "net_pnl": round(total_net_pnl, 2)  # Same as total_net_pnl
        }
    
    async def _compute_fee_metrics(self, bot_ids: List[str], today_start: datetime) -> Dict:
        """Compute fee metrics using canonical field normalization
        
        Uses:
        - fee_amount (primary) → fallback fees → fallback fee
        """
        if not bot_ids:
            return {
                "total_fees": 0.0,
                "today_fees": 0.0
            }
        
        # Get all closed trades
        all_trades = await db.trades_collection.find({
            "bot_id": {"$in": bot_ids},
            "status": "closed"
        }, {
            "_id": 0,
            "fee_amount": 1,
            "fees": 1,
            "fee": 1,
            "timestamp": 1
        }).to_list(100000)
        
        # Calculate totals using canonical field normalization
        total_fees = 0.0
        today_fees = 0.0
        
        for trade in all_trades:
            # Use fee_amount if available, fallback to fees, then fee
            fee = trade.get("fee_amount", trade.get("fees", trade.get("fee", 0)))
            
            total_fees += fee
            
            # Check if trade is from today
            trade_time = trade.get("timestamp", "")
            if trade_time and trade_time >= today_start.isoformat():
                today_fees += fee
        
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
            trade_time = trade.get("timestamp", "")
            if trade_time and trade_time >= today_start.isoformat():
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
        """Compute bot counts by status"""
        active = sum(1 for b in bots if b.get("status") == "active")
        paused = sum(1 for b in bots if b.get("status") == "paused")
        training = sum(1 for b in bots if b.get("status") == "training")
        quarantine = sum(1 for b in bots if b.get("status") in ["quarantined", "quarantine"])
        
        return {
            "active": active,
            "paused": paused,
            "training": training,
            "quarantine": quarantine,
            "total": len(bots)
        }
    
    def _compute_capital_metrics(self, bots: List[Dict]) -> Dict:
        """Compute equity and required capital metrics"""
        # Equity = sum of current capital across all active bots
        equity = sum(b.get("current_capital", 0) for b in bots if b.get("status") == "active")
        
        # Required capital = sum of initial capital across all bots (not just active)
        # This is what the system expects to have allocated
        required_capital_total = sum(b.get("initial_capital", 0) for b in bots)
        
        # Required capital by platform
        required_capital_by_platform = {}
        for platform in SUPPORTED_PLATFORMS:
            platform_bots = [b for b in bots if b.get("platform") == platform]
            platform_capital = sum(b.get("initial_capital", 0) for b in platform_bots)
            required_capital_by_platform[platform] = round(platform_capital, 2)
        
        return {
            "equity": round(equity, 2),
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
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "source": "unavailable"
            },
            "ETH/ZAR": {
                "price": 0.0,
                "change_pct": 0.0,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "source": "unavailable"
            },
            "XRP/ZAR": {
                "price": 0.0,
                "change_pct": 0.0,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "source": "unavailable"
            }
        }
    
    async def _fetch_luno_prices(self) -> Optional[Dict]:
        """Fetch live prices from Luno API
        
        Returns proper price data structure or None.
        """
        try:
            import httpx
            
            prices = {}
            pairs = [("XBTZAR", "BTC/ZAR"), ("ETHZAR", "ETH/ZAR"), ("XRPZAR", "XRP/ZAR")]
            
            async with httpx.AsyncClient(timeout=5.0) as client:
                for luno_pair, display_pair in pairs:
                    try:
                        url = f"https://api.luno.com/api/1/ticker?pair={luno_pair}"
                        response = await client.get(url)
                        response.raise_for_status()
                        
                        data = response.json()
                        last_trade = float(data.get("last_trade", 0))
                        
                        prices[display_pair] = {
                            "price": round(last_trade, 2),
                            "change_pct": 0.0,  # Future: Track 24h change (see DEPLOYMENT_NOTES.md)
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                            "source": "luno_public"
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
