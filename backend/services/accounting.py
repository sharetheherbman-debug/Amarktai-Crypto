"""
Accounting Service - Single Source of Truth for Profit/Trade Metrics

This service unifies profit and trade calculations across the entire application.
It ensures consistency between Overview, Profits page, and Live Trades page.

Key Metrics (DEFINED):
- executed_trades_count: Count of executed trades in trades_collection
- net_realised_pnl_zar: Realised PnL after fees — always ZAR (internal truth)
- unrealised_pnl_zar: Informational only (open positions), in ZAR
- gross_pnl_zar: PnL before fees, in ZAR
- total_fees_zar: Total fees paid, in ZAR

Currency rule:
- ALL internal monetary aggregates are in ZAR.
- Trades denominated in USDT (Binance, KuCoin, etc.) are converted via
  fx_normalizer before being included in any sum.
- When display_currency != "ZAR", all aggregated ZAR values are converted
  to the requested display currency before being returned.

Usage:
    from services.accounting import accounting_service

    metrics = await accounting_service.get_unified_metrics(user_id, display_currency="USD")
    print(f"Net Profit: ${metrics['net_realised_pnl_display']}")
"""

from typing import Dict, List, Optional
from datetime import datetime, timezone
import logging

import database as db
from services.fx_normalizer import (
    get_quote_currency as _gqc,
    get_fx_rate as _gfr,
    to_display_currency as _to_display,
    SUPPORTED_DISPLAY_CURRENCIES,
)

logger = logging.getLogger(__name__)


class AccountingService:
    """Unified accounting calculations - single source of truth"""
    
    async def get_unified_metrics(
        self,
        user_id: str,
        trading_mode: Optional[str] = None,
        include_unrealised: bool = True,
        display_currency: str = "ZAR",
    ) -> Dict:
        """
        Get unified profit/trade metrics - USE THIS FOR ALL VIEWS

        Returns consistent metrics for Overview, Profits, and Live Trades pages.
        All monetary values are in the requested *display_currency* (ZAR by default).

        Args:
            user_id: User ID
            trading_mode: Filter by 'paper' or 'live' (None = both)
            include_unrealised: Whether to calculate unrealised PnL
            display_currency: ISO code for final presentation (ZAR/USD/GBP/EUR).
                              Aggregation always happens internally in ZAR.

        Returns:
            Dict with all key metrics.
            "_zar" fields always carry the raw ZAR internal values.
            "_display" fields carry the value in the requested display_currency.
            "display_currency" indicates which currency the _display fields use.
        """
        dc = str(display_currency or "ZAR").upper()
        if dc not in SUPPORTED_DISPLAY_CURRENCIES:
            dc = "ZAR"

        # Pre-compute the ZAR→display rate once; reuse in _cvt to avoid
        # repeated lookups across every monetary field.
        _dc_rate, _dc_source = _gfr("ZAR", dc)

        def _cvt(zar_val):
            if zar_val is None:
                return None
            return round(float(zar_val) * _dc_rate, 2)

        try:
            # Build base query
            query = {"user_id": user_id, "status": "closed"}
            if trading_mode:
                query["trading_mode"] = trading_mode

            # Fetch closed trades — include currency fields for ZAR normalisation
            trades = await db.trades_collection.find(
                query,
                {
                    "_id": 0,
                    "net_pnl": 1,
                    "gross_pnl": 1,
                    "profit_loss": 1,
                    "fee_amount": 1,
                    "fee_paid": 1,
                    "fees": 1,
                    "trading_mode": 1,
                    "realized_pnl_zar": 1,     # Pre-converted ZAR value (preferred)
                    "fee_display_zar": 1,       # Pre-converted ZAR fee (preferred)
                    "exchange": 1,
                    "quote_currency": 1,
                }
            ).to_list(10000)

            # ── Aggregate in ZAR ──────────────────────────────────────────────
            executed_trades_count = len(trades)
            net_realised_pnl_zar = 0.0
            gross_realised_pnl_zar = 0.0
            total_fees_zar = 0.0

            for t in trades:
                exchange = t.get("exchange", "")
                qc = t.get("quote_currency") or _gqc(exchange, "")
                rate, _ = _gfr(qc, "ZAR")

                # Net PnL: prefer pre-converted field; fall back to on-the-fly conversion
                pnl_zar = t.get("realized_pnl_zar")
                if pnl_zar is None:
                    raw_pnl = float(t.get("net_pnl", t.get("profit_loss", 0)) or 0)
                    pnl_zar = raw_pnl * rate
                net_realised_pnl_zar += pnl_zar

                # Gross PnL
                raw_gross = float(t.get("gross_pnl", t.get("profit_loss", 0)) or 0)
                gross_realised_pnl_zar += raw_gross * rate

                # Fees
                fee_zar = t.get("fee_display_zar")
                if fee_zar is None:
                    raw_fee = float(t.get("fee_amount", t.get("fee_paid", t.get("fees", 0))) or 0)
                    fee_zar = raw_fee * rate
                total_fees_zar += fee_zar
            
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
                # Internal ZAR values (always present)
                "net_realised_pnl_zar": round(net_realised_pnl_zar, 2),
                "gross_realised_pnl_zar": round(gross_realised_pnl_zar, 2),
                "total_fees_zar": round(total_fees_zar, 2),
                "unrealised_pnl_zar": round(unrealised_pnl_zar, 2),
                "total_pnl_zar": round(total_pnl_zar, 2),
                # Display-currency values (use pre-computed _dc_rate/_dc_source)
                "net_realised_pnl_display": _cvt(round(net_realised_pnl_zar, 2)),
                "gross_realised_pnl_display": _cvt(round(gross_realised_pnl_zar, 2)),
                "total_fees_display": _cvt(round(total_fees_zar, 2)),
                "unrealised_pnl_display": _cvt(round(unrealised_pnl_zar, 2)),
                "total_pnl_display": _cvt(round(total_pnl_zar, 2)),
                "display_currency": dc,
                "fx_metadata": {
                    "zar_to_display_rate": round(_dc_rate, 6),
                    "zar_to_display_source": _dc_source,
                },
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
                "net_realised_pnl_display": 0.0,
                "gross_realised_pnl_display": 0.0,
                "total_fees_display": 0.0,
                "unrealised_pnl_display": 0.0,
                "total_pnl_display": 0.0,
                "display_currency": dc,
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
            _CURRENCY_SYMBOL_MAP = {"ZAR": "R", "USD": "$", "USDT": "$", "USDC": "$", "BUSD": "$", "TUSD": "$"}
            for trade in trades:
                # Standardize PnL fields
                net_pnl = trade.get("net_pnl", trade.get("profit_loss", 0))
                gross_pnl = trade.get("gross_pnl", net_pnl)
                fee = trade.get("fee_amount", 0)
                # Resolve the correct currency symbol so USDT trades show "$" not "R"
                _exchange = (trade.get("exchange") or "").lower()
                _symbol = trade.get("pair") or trade.get("symbol") or ""
                _quote_currency = (
                    trade.get("quote_currency")
                    or trade.get("fee_currency")
                )
                if not _quote_currency:
                    from services.fx_normalizer import get_quote_currency as _gqc
                    _quote_currency = _gqc(_exchange, _symbol)
                _cur_sym = _CURRENCY_SYMBOL_MAP.get(
                    _quote_currency_upper := (_quote_currency or "ZAR").upper(),
                    _quote_currency_upper + "\u00A0"
                )
                enriched_trade = {
                    **trade,
                    "net_pnl": net_pnl,
                    "gross_pnl": gross_pnl,
                    "fee_amount": fee,
                    "quote_currency": _quote_currency,
                    # Display labels — use the trade's native currency symbol, not "R" always.
                    "net_pnl_display": f"{_cur_sym}{net_pnl:.2f}",
                    "gross_pnl_display": f"{_cur_sym}{gross_pnl:.2f}",
                    "fee_display": f"{_cur_sym}{fee:.2f}",
                }
                enriched_trades.append(enriched_trade)
            
            # Calculate summary — all aggregates in ZAR
            total_net_pnl_zar = 0.0
            total_gross_pnl_zar = 0.0
            total_fees_zar = 0.0
            for t in enriched_trades:
                exchange = (t.get("exchange") or "").lower()
                qc = t.get("quote_currency") or _gqc(exchange, "")
                rate, _ = _gfr(qc, "ZAR")

                pnl_zar = t.get("realized_pnl_zar")
                if pnl_zar is None:
                    pnl_zar = float(t["net_pnl"] or 0) * rate
                total_net_pnl_zar += pnl_zar

                raw_gross = float(t["gross_pnl"] or 0)
                total_gross_pnl_zar += raw_gross * rate

                fee_zar = t.get("fee_display_zar")
                if fee_zar is None:
                    fee_zar = float(t["fee_amount"] or 0) * rate
                total_fees_zar += fee_zar
            
            return {
                "trades": enriched_trades,
                "count": len(enriched_trades),
                "summary": {
                    "total_net_pnl": round(total_net_pnl_zar, 2),
                    "total_gross_pnl": round(total_gross_pnl_zar, 2),
                    "total_fees": round(total_fees_zar, 2),
                    "display_currency": "ZAR",
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
        Get detailed profit breakdown by exchange and bot, all values in ZAR.
        
        Args:
            user_id: User ID
            trading_mode: Filter by mode
            
        Returns:
            Breakdown of profits (ZAR) by various dimensions
        """
        try:
            query = {"user_id": user_id, "status": "closed"}
            if trading_mode:
                query["trading_mode"] = trading_mode
            
            trades = await db.trades_collection.find(
                query,
                {
                    "_id": 0,
                    "exchange": 1,
                    "bot_id": 1,
                    "net_pnl": 1,
                    "profit_loss": 1,
                    "realized_pnl_zar": 1,
                    "quote_currency": 1,
                }
            ).to_list(10000)
            
            # Group by exchange — all values in ZAR
            by_exchange = {}
            for trade in trades:
                exchange = trade.get("exchange", "unknown")
                qc = trade.get("quote_currency") or _gqc(exchange, "")
                rate, _ = _gfr(qc, "ZAR")

                pnl_zar = trade.get("realized_pnl_zar")
                if pnl_zar is None:
                    raw_pnl = float(trade.get("net_pnl", trade.get("profit_loss", 0)) or 0)
                    pnl_zar = raw_pnl * rate

                if exchange not in by_exchange:
                    by_exchange[exchange] = {"net_pnl": 0.0, "count": 0}
                by_exchange[exchange]["net_pnl"] += pnl_zar
                by_exchange[exchange]["count"] += 1
            
            # Group by bot — all values in ZAR
            by_bot = {}
            for trade in trades:
                bot_id = trade.get("bot_id", "unknown")
                exchange = trade.get("exchange", "unknown")
                qc = trade.get("quote_currency") or _gqc(exchange, "")
                rate, _ = _gfr(qc, "ZAR")

                pnl_zar = trade.get("realized_pnl_zar")
                if pnl_zar is None:
                    raw_pnl = float(trade.get("net_pnl", trade.get("profit_loss", 0)) or 0)
                    pnl_zar = raw_pnl * rate

                if bot_id not in by_bot:
                    by_bot[bot_id] = {"net_pnl": 0.0, "count": 0}
                by_bot[bot_id]["net_pnl"] += pnl_zar
                by_bot[bot_id]["count"] += 1
            
            # Round all values
            for exch_data in by_exchange.values():
                exch_data["net_pnl"] = round(exch_data["net_pnl"], 2)
            for bot_data in by_bot.values():
                bot_data["net_pnl"] = round(bot_data["net_pnl"], 2)
            
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
