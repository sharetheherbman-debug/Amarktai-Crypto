"""
Accounting Service - Single Source of Truth for Profit/Trade Metrics

This service unifies profit and trade calculations across the entire application.
It ensures consistency between Overview, Profits page, and Live Trades page.

Key Metrics (DEFINED):
- executed_trades_count: Count of executed trades in trades_collection
- net_realised_pnl_zar: Realised PnL after fees (CASH-OUT truth)
- unrealised_pnl_zar: Informational only (open positions)
- gross_pnl_zar: PnL before fees
- total_fees_zar: Total fees paid

Usage:
    from services.accounting import accounting_service
    
    metrics = await accounting_service.get_unified_metrics(user_id)
    print(f"Net Profit: R{metrics['net_realised_pnl_zar']}")
"""

from typing import Dict, List, Optional
from datetime import datetime, timezone
import logging

import database as db

logger = logging.getLogger(__name__)


class AccountingService:
    """Unified accounting calculations - single source of truth"""
    
    async def get_unified_metrics(
        self,
        user_id: str,
        trading_mode: Optional[str] = None,
        include_unrealised: bool = True
    ) -> Dict:
        """
        Get unified profit/trade metrics - USE THIS FOR ALL VIEWS
        
        Returns consistent metrics for Overview, Profits, and Live Trades pages.
        
        Args:
            user_id: User ID
            trading_mode: Filter by 'paper' or 'live' (None = both)
            include_unrealised: Whether to calculate unrealised PnL
            
        Returns:
            Dict with all key metrics:
            {
                "executed_trades_count": int,
                "net_realised_pnl_zar": float,
                "gross_realised_pnl_zar": float,
                "total_fees_zar": float,
                "unrealised_pnl_zar": float,
                "total_pnl_zar": float,  # realised + unrealised
                "trading_mode": str,
                "last_calculated_at": str (ISO)
            }
        """
        try:
            # Build base query
            query = {"user_id": user_id, "status": "closed"}
            if trading_mode:
                query["trading_mode"] = trading_mode
            
            # Fetch closed trades
            trades = await db.trades_collection.find(
                query,
                {
                    "_id": 0,
                    "net_pnl": 1,
                    "gross_pnl": 1,
                    "profit_loss": 1,
                    "fee_amount": 1,
                    "trading_mode": 1
                }
            ).to_list(10000)
            
            # Calculate realised metrics
            executed_trades_count = len(trades)
            
            # Use net_pnl if available, fallback to profit_loss
            net_realised_pnl_zar = sum(
                t.get("net_pnl", t.get("profit_loss", 0)) 
                for t in trades
            )
            
            # Gross PnL (before fees)
            gross_realised_pnl_zar = sum(
                t.get("gross_pnl", t.get("profit_loss", 0))
                for t in trades
            )
            
            # Total fees
            total_fees_zar = sum(
                t.get("fee_amount", t.get("fee_paid", t.get("fees", 0)))
                for t in trades
            )
            
            # Calculate unrealised PnL if requested
            unrealised_pnl_zar = 0.0
            if include_unrealised:
                unrealised_pnl_zar = await self._calculate_unrealised_pnl(
                    user_id, trading_mode
                )
            
            # Total PnL = realised + unrealised
            total_pnl_zar = net_realised_pnl_zar + unrealised_pnl_zar
            
            return {
                "executed_trades_count": executed_trades_count,
                "net_realised_pnl_zar": round(net_realised_pnl_zar, 2),
                "gross_realised_pnl_zar": round(gross_realised_pnl_zar, 2),
                "total_fees_zar": round(total_fees_zar, 2),
                "unrealised_pnl_zar": round(unrealised_pnl_zar, 2),
                "total_pnl_zar": round(total_pnl_zar, 2),
                "trading_mode": trading_mode or "all",
                "last_calculated_at": datetime.now(timezone.utc).isoformat()
            }
            
        except Exception as e:
            logger.error(f"Get unified metrics error: {e}", exc_info=True)
            return {
                "executed_trades_count": 0,
                "net_realised_pnl_zar": 0.0,
                "gross_realised_pnl_zar": 0.0,
                "total_fees_zar": 0.0,
                "unrealised_pnl_zar": 0.0,
                "total_pnl_zar": 0.0,
                "trading_mode": trading_mode or "all",
                "last_calculated_at": datetime.now(timezone.utc).isoformat(),
                "error": str(e)
            }
    
    async def _calculate_unrealised_pnl(
        self,
        user_id: str,
        trading_mode: Optional[str] = None
    ) -> float:
        """
        Calculate unrealised PnL from open positions
        
        Note: This requires current market prices and open position tracking.
        If not available, returns 0.
        """
        try:
            query = {"user_id": user_id, "status": "open"}
            if trading_mode:
                query["trading_mode"] = trading_mode
            
            open_positions = await db.trades_collection.find(
                query,
                {"_id": 0, "unrealised_profit": 1, "unrealized_profit": 1}
            ).to_list(1000)
            
            # Sum unrealised profit (handle both spellings)
            unrealised_pnl = sum(
                p.get("unrealised_profit", p.get("unrealized_profit", 0))
                for p in open_positions
            )
            
            return unrealised_pnl
            
        except Exception as e:
            logger.error(f"Calculate unrealised PnL error: {e}")
            return 0.0
    
    async def get_trade_list_with_metrics(
        self,
        user_id: str,
        trading_mode: Optional[str] = None,
        limit: int = 100,
        status: str = "closed"
    ) -> Dict:
        """
        Get trade list with consistent metrics for display
        
        Returns trades with standardized fields for display in Profits and Live Trades pages.
        
        Args:
            user_id: User ID
            trading_mode: Filter by mode
            limit: Max trades to return
            status: Trade status filter (closed, open, all)
            
        Returns:
            Dict with trades list and summary metrics
        """
        try:
            # Build query
            query = {"user_id": user_id}
            if status != "all":
                query["status"] = status
            if trading_mode:
                query["trading_mode"] = trading_mode
            
            # Fetch trades
            trades = await db.trades_collection.find(
                query,
                {"_id": 0}
            ).sort("timestamp", -1).limit(limit).to_list(limit)
            
            # Enrich trades with standardized fields
            enriched_trades = []
            for trade in trades:
                # Standardize PnL fields
                net_pnl = trade.get("net_pnl", trade.get("profit_loss", 0))
                gross_pnl = trade.get("gross_pnl", net_pnl)
                fee = trade.get("fee_amount", 0)
                
                enriched_trade = {
                    **trade,
                    "net_pnl": net_pnl,
                    "gross_pnl": gross_pnl,
                    "fee_amount": fee,
                    # Display labels
                    "net_pnl_display": f"R{net_pnl:.2f}",
                    "gross_pnl_display": f"R{gross_pnl:.2f}",
                    "fee_display": f"R{fee:.2f}",
                }
                enriched_trades.append(enriched_trade)
            
            # Calculate summary
            total_net_pnl = sum(t["net_pnl"] for t in enriched_trades)
            total_gross_pnl = sum(t["gross_pnl"] for t in enriched_trades)
            total_fees = sum(t["fee_amount"] for t in enriched_trades)
            
            return {
                "trades": enriched_trades,
                "count": len(enriched_trades),
                "summary": {
                    "total_net_pnl": round(total_net_pnl, 2),
                    "total_gross_pnl": round(total_gross_pnl, 2),
                    "total_fees": round(total_fees, 2),
                },
                "filters": {
                    "trading_mode": trading_mode,
                    "status": status,
                    "limit": limit
                }
            }
            
        except Exception as e:
            logger.error(f"Get trade list error: {e}", exc_info=True)
            return {
                "trades": [],
                "count": 0,
                "summary": {
                    "total_net_pnl": 0.0,
                    "total_gross_pnl": 0.0,
                    "total_fees": 0.0,
                },
                "error": str(e)
            }
    
    async def get_profit_breakdown(
        self,
        user_id: str,
        trading_mode: Optional[str] = None
    ) -> Dict:
        """
        Get detailed profit breakdown by exchange, bot, strategy
        
        Args:
            user_id: User ID
            trading_mode: Filter by mode
            
        Returns:
            Breakdown of profits by various dimensions
        """
        try:
            query = {"user_id": user_id, "status": "closed"}
            if trading_mode:
                query["trading_mode"] = trading_mode
            
            trades = await db.trades_collection.find(query, {"_id": 0}).to_list(10000)
            
            # Group by exchange
            by_exchange = {}
            for trade in trades:
                exchange = trade.get("exchange", "unknown")
                net_pnl = trade.get("net_pnl", trade.get("profit_loss", 0))
                
                if exchange not in by_exchange:
                    by_exchange[exchange] = {"net_pnl": 0, "count": 0}
                by_exchange[exchange]["net_pnl"] += net_pnl
                by_exchange[exchange]["count"] += 1
            
            # Group by bot
            by_bot = {}
            for trade in trades:
                bot_id = trade.get("bot_id", "unknown")
                net_pnl = trade.get("net_pnl", trade.get("profit_loss", 0))
                
                if bot_id not in by_bot:
                    by_bot[bot_id] = {"net_pnl": 0, "count": 0}
                by_bot[bot_id]["net_pnl"] += net_pnl
                by_bot[bot_id]["count"] += 1
            
            # Round all values
            for exchange in by_exchange.values():
                exchange["net_pnl"] = round(exchange["net_pnl"], 2)
            for bot in by_bot.values():
                bot["net_pnl"] = round(bot["net_pnl"], 2)
            
            return {
                "by_exchange": by_exchange,
                "by_bot": by_bot,
                "total_exchanges": len(by_exchange),
                "total_bots": len(by_bot)
            }
            
        except Exception as e:
            logger.error(f"Get profit breakdown error: {e}")
            return {
                "by_exchange": {},
                "by_bot": {},
                "total_exchanges": 0,
                "total_bots": 0,
                "error": str(e)
            }


# Global singleton instance
accounting_service = AccountingService()
