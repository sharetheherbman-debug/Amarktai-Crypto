"""
Analytics API - Single Source of Truth for PnL and Performance Data
All graphs and dashboards must read from these endpoints only
"""

from fastapi import APIRouter, HTTPException, Depends, Query
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict
import logging

from auth import get_current_user
import database as db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/analytics", tags=["Analytics"])


@router.get("/pnl_timeseries")
async def get_pnl_timeseries(
    range: str = Query("7d", regex="^(1d|7d|30d|90d|1y|all)$"),
    interval: str = Query("1h", regex="^(5m|15m|1h|4h|1d)$"),
    user_id: str = Depends(get_current_user)
):
    """Get PnL timeseries data - SINGLE SOURCE OF TRUTH for all profit graphs
    Uses centralized metrics service
    
    Args:
        range: Time range (1d, 7d, 30d, 90d, 1y, all)
        interval: Data point interval (5m, 15m, 1h, 4h, 1d)
        user_id: Current user ID
        
    Returns:
        Timeseries data with timestamps and cumulative PnL
    """
    try:
        # Use centralized metrics service
        from services.metrics_service import metrics_service
        return await metrics_service.get_profit_history(user_id, range, interval)
        
    except Exception as e:
        logger.error(f"PnL timeseries error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/capital_breakdown")
async def get_capital_breakdown(user_id: str = Depends(get_current_user)):
    """Get detailed capital breakdown - distinguishes funded vs unrealized vs realized
    
    Returns:
        - funded_capital: Total capital deposited/allocated
        - current_capital: Current total capital (funded + realized)
        - unrealized_pnl: Profit/loss from open positions (if any)
        - realized_pnl: Profit/loss from closed trades
    """
    try:
        # Get all user bots
        bots = await db.bots_collection.find(
            {"user_id": user_id},
            {"_id": 0}
        ).to_list(1000)
        
        if not bots:
            return {
                "funded_capital": 0,
                "current_capital": 0,
                "unrealized_pnl": 0,
                "realized_pnl": 0,
                "total_bots": 0,
                "no_data_yet": True,
                "message": "No bots created yet. Create a bot to start trading."
            }
        
        # Calculate totals
        funded_capital = sum(bot.get('initial_capital', 0) for bot in bots)
        current_capital = sum(bot.get('current_capital', 0) for bot in bots)
        realized_pnl = sum(bot.get('total_profit', 0) for bot in bots)
        
        # Unrealized PnL from open positions (paper trading doesn't have open positions)
        unrealized_pnl = 0  # Will be calculated from open positions in live trading
        
        return {
            "funded_capital": round(funded_capital, 2),
            "current_capital": round(current_capital, 2),
            "unrealized_pnl": round(unrealized_pnl, 2),
            "realized_pnl": round(realized_pnl, 2),
            "total_bots": len(bots),
            "breakdown_by_bot": [
                {
                    "bot_id": bot['id'],
                    "bot_name": bot.get('name'),
                    "funded": bot.get('initial_capital', 0),
                    "current": bot.get('current_capital', 0),
                    "realized_pnl": bot.get('total_profit', 0)
                }
                for bot in bots
            ],
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as e:
        logger.error(f"Get capital breakdown error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/performance_summary")
async def get_performance_summary(
    period: str = Query("all", regex="^(today|7d|30d|all)$"),
    user_id: str = Depends(get_current_user)
):
    """Get comprehensive performance summary
    
    Args:
        period: Time period for summary (today, 7d, 30d, all)
    """
    try:
        # Calculate time range
        now = datetime.now(timezone.utc)
        
        if period == "today":
            start_time = now.replace(hour=0, minute=0, second=0, microsecond=0)
        elif period == "7d":
            start_time = now - timedelta(days=7)
        elif period == "30d":
            start_time = now - timedelta(days=30)
        else:  # all
            start_time = datetime(2020, 1, 1, tzinfo=timezone.utc)
        
        # Get trades in period
        trades = await db.trades_collection.find(
            {
                "user_id": user_id,
                "timestamp": {"$gte": start_time.isoformat()}
            },
            {"_id": 0}
        ).to_list(10000)
        
        # Calculate statistics using canonical field normalization
        total_trades = len(trades)
        
        if total_trades == 0:
            return {
                "period": period,
                "start_time": start_time.isoformat(),
                "end_time": now.isoformat(),
                "trades": {"total": 0, "winning": 0, "losing": 0, "win_rate_pct": 0},
                "pnl": {"total": 0, "gross_profit": 0, "gross_loss": 0, "profit_factor": 0},
                "averages": {"avg_win": 0, "avg_loss": 0, "avg_trade": 0},
                "no_data_yet": True,
                "message": "No trades in this period. Bots need to execute trades to generate performance data.",
                "timestamp": now.isoformat()
            }
        
        # Use net_pnl (primary) → fallback profit_loss
        winning_trades = len([t for t in trades if t.get('net_pnl', t.get('profit_loss', 0)) > 0])
        losing_trades = len([t for t in trades if t.get('net_pnl', t.get('profit_loss', 0)) < 0])
        
        total_pnl = sum(t.get('net_pnl', t.get('profit_loss', 0)) for t in trades)
        gross_profit = sum(t.get('net_pnl', t.get('profit_loss', 0)) for t in trades if t.get('net_pnl', t.get('profit_loss', 0)) > 0)
        gross_loss = abs(sum(t.get('net_pnl', t.get('profit_loss', 0)) for t in trades if t.get('net_pnl', t.get('profit_loss', 0)) < 0))
        
        win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
        profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else 0
        
        # Average trade metrics
        avg_win = (gross_profit / winning_trades) if winning_trades > 0 else 0
        avg_loss = (gross_loss / losing_trades) if losing_trades > 0 else 0
        
        return {
            "period": period,
            "start_time": start_time.isoformat(),
            "end_time": now.isoformat(),
            "trades": {
                "total": total_trades,
                "winning": winning_trades,
                "losing": losing_trades,
                "win_rate_pct": round(win_rate, 2)
            },
            "pnl": {
                "total": round(total_pnl, 2),
                "gross_profit": round(gross_profit, 2),
                "gross_loss": round(gross_loss, 2),
                "profit_factor": round(profit_factor, 2)
            },
            "averages": {
                "avg_win": round(avg_win, 2),
                "avg_loss": round(avg_loss, 2),
                "avg_trade": round(total_pnl / total_trades, 2) if total_trades > 0 else 0
            },
            "timestamp": now.isoformat()
        }
        
    except Exception as e:
        logger.error(f"Get performance summary error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/exchange-comparison")
async def get_exchange_comparison(
    period: str = Query("30d", regex="^(7d|30d|90d|all)$"),
    user_id: str = Depends(get_current_user)
):
    """
    Get performance comparison across exchanges (Luno, Binance, KuCoin)
    Shows ROI, trade count, win rate per exchange
    """
    try:
        # Calculate time range
        now = datetime.now(timezone.utc)
        range_map = {
            "7d": timedelta(days=7),
            "30d": timedelta(days=30),
            "90d": timedelta(days=90),
            "all": timedelta(days=3650)
        }
        start_time = now - range_map.get(period, timedelta(days=30))
        
        # Get all trades in range
        trades = await db.trades_collection.find(
            {
                "user_id": user_id,
                "timestamp": {"$gte": start_time.isoformat()}
            },
            {"_id": 0}
        ).to_list(10000)
        
        # Group by exchange
        exchange_data = {}
        # Import supported exchanges from canonical source
        from config.platforms import SUPPORTED_PLATFORMS
        
        for exchange in SUPPORTED_PLATFORMS:
            exchange_trades = [t for t in trades if t.get('exchange', '').lower() == exchange]
            
            if not exchange_trades:
                exchange_data[exchange] = {
                    "exchange": exchange,
                    "trades": 0,
                    "pnl": 0,
                    "roi_pct": 0,
                    "win_rate_pct": 0,
                    "status": "inactive"
                }
                continue
            
            # Calculate metrics using canonical field normalization
            total_trades = len(exchange_trades)
            # Use net_pnl (primary) → fallback profit_loss
            winning = len([t for t in exchange_trades if t.get('net_pnl', t.get('profit_loss', 0)) > 0])
            total_pnl = sum(t.get('net_pnl', t.get('profit_loss', 0)) for t in exchange_trades)
            
            # Estimate initial capital (sum of trade sizes)
            initial_capital = sum(abs(t.get('amount', 0) * t.get('price', 0)) for t in exchange_trades) / total_trades if total_trades > 0 else 1
            roi_pct = (total_pnl / initial_capital * 100) if initial_capital > 0 else 0
            win_rate = (winning / total_trades * 100) if total_trades > 0 else 0
            
            exchange_data[exchange] = {
                "exchange": exchange,
                "trades": total_trades,
                "pnl": round(total_pnl, 2),
                "roi_pct": round(roi_pct, 2),
                "win_rate_pct": round(win_rate, 2),
                "status": "active"
            }
        
        # Sort by PnL descending
        sorted_exchanges = sorted(
            exchange_data.values(),
            key=lambda x: x['pnl'],
            reverse=True
        )
        
        return {
            "period": period,
            "start_time": start_time.isoformat(),
            "end_time": now.isoformat(),
            "exchanges": sorted_exchanges,
            "summary": {
                "total_pnl": sum(e['pnl'] for e in sorted_exchanges),
                "total_trades": sum(e['trades'] for e in sorted_exchanges),
                "active_exchanges": len([e for e in sorted_exchanges if e['status'] == 'active'])
            },
            "timestamp": now.isoformat()
        }
        
    except Exception as e:
        logger.error(f"Get exchange comparison error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/equity")
async def get_equity_curve(
    range: str = Query("7d", regex="^(1d|7d|30d|90d|1y|all)$"),
    user_id: str = Depends(get_current_user)
):
    """Get equity curve showing total P&L over time with realized vs unrealized breakdown
    
    Returns:
        Timeseries data with equity progression, realized/unrealized PnL, and fee analysis
    """
    try:
        now = datetime.now(timezone.utc)
        range_map = {
            "1d": timedelta(days=1),
            "7d": timedelta(days=7),
            "30d": timedelta(days=30),
            "90d": timedelta(days=90),
            "1y": timedelta(days=365),
            "all": timedelta(days=3650)
        }
        start_time = now - range_map.get(range, timedelta(days=7))
        
        # Get all bots for initial capital
        bots = await db.bots_collection.find(
            {"user_id": user_id},
            {"_id": 0, "initial_capital": 1, "current_capital": 1}
        ).to_list(1000)
        
        initial_capital = sum(bot.get('initial_capital', 0) for bot in bots)
        current_capital = sum(bot.get('current_capital', 0) for bot in bots)
        
        # Get trades in time range
        trades = await db.trades_collection.find(
            {
                "user_id": user_id,
                "timestamp": {"$gte": start_time.isoformat()}
            },
            {"_id": 0, "timestamp": 1, "net_pnl": 1, "profit_loss": 1, "fee_amount": 1, "fees": 1, "fee": 1}
        ).sort("timestamp", 1).to_list(10000)
        
        # Build equity curve
        equity_points = []
        cumulative_pnl = 0
        cumulative_fees = 0
        
        if not trades:
            # No trades - return initial state
            equity_points = [{
                "timestamp": start_time.isoformat(),
                "equity": initial_capital,
                "realized_pnl": 0,
                "unrealized_pnl": 0,
                "fees": 0
            }]
        else:
            for trade in trades:
                # Use canonical field normalization
                cumulative_pnl += trade.get('net_pnl', trade.get('profit_loss', 0))
                cumulative_fees += trade.get('fee_amount', trade.get('fees', trade.get('fee', 0)))
                
                equity_points.append({
                    "timestamp": trade['timestamp'],
                    "equity": initial_capital + cumulative_pnl,
                    "realized_pnl": cumulative_pnl,
                    "unrealized_pnl": 0,  # Paper trading has no open positions
                    "fees": cumulative_fees
                })
        
        # Add current point
        equity_points.append({
            "timestamp": now.isoformat(),
            "equity": current_capital,
            "realized_pnl": current_capital - initial_capital,
            "unrealized_pnl": 0,
            "fees": cumulative_fees
        })
        
        return {
            "range": range,
            "start_time": start_time.isoformat(),
            "end_time": now.isoformat(),
            "initial_capital": round(initial_capital, 2),
            "current_equity": round(current_capital, 2),
            "total_pnl": round(current_capital - initial_capital, 2),
            "total_fees": round(cumulative_fees, 2),
            "equity_curve": equity_points,
            "timestamp": now.isoformat()
        }
        
    except Exception as e:
        logger.error(f"Get equity curve error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/drawdown")
async def get_drawdown_analysis(
    range: str = Query("7d", regex="^(1d|7d|30d|90d|1y|all)$"),
    user_id: str = Depends(get_current_user)
):
    """Get drawdown analysis showing maximum drawdown and recovery metrics
    
    Returns:
        Drawdown metrics including max drawdown %, current drawdown, and underwater periods
    """
    try:
        now = datetime.now(timezone.utc)
        range_map = {
            "1d": timedelta(days=1),
            "7d": timedelta(days=7),
            "30d": timedelta(days=30),
            "90d": timedelta(days=90),
            "1y": timedelta(days=365),
            "all": timedelta(days=3650)
        }
        start_time = now - range_map.get(range, timedelta(days=7))
        
        # Get all bots for capital tracking
        bots = await db.bots_collection.find(
            {"user_id": user_id},
            {"_id": 0, "initial_capital": 1, "current_capital": 1}
        ).to_list(1000)
        
        initial_capital = sum(bot.get('initial_capital', 0) for bot in bots)
        current_capital = sum(bot.get('current_capital', 0) for bot in bots)
        
        # Get trades in time range
        trades = await db.trades_collection.find(
            {
                "user_id": user_id,
                "timestamp": {"$gte": start_time.isoformat()}
            },
            {"_id": 0, "timestamp": 1, "net_pnl": 1, "profit_loss": 1}
        ).sort("timestamp", 1).to_list(10000)
        
        # Calculate equity progression and drawdowns
        equity_curve = []
        cumulative_pnl = 0
        peak_equity = initial_capital
        max_drawdown = 0
        max_drawdown_pct = 0
        current_drawdown_pct = 0
        drawdown_points = []
        
        if not trades:
            # No trades yet
            return {
                "range": range,
                "start_time": start_time.isoformat(),
                "end_time": now.isoformat(),
                "max_drawdown_pct": 0,
                "current_drawdown_pct": 0,
                "peak_equity": initial_capital,
                "current_equity": current_capital,
                "underwater_periods": 0,
                "drawdown_curve": [],
                "timestamp": now.isoformat()
            }
        
        for trade in trades:
            # Use canonical field normalization
            cumulative_pnl += trade.get('net_pnl', trade.get('profit_loss', 0))
            equity = initial_capital + cumulative_pnl
            equity_curve.append(equity)
            
            # Update peak
            if equity > peak_equity:
                peak_equity = equity
            
            # Calculate drawdown
            if peak_equity > 0:
                drawdown_pct = ((peak_equity - equity) / peak_equity) * 100
                drawdown_points.append({
                    "timestamp": trade['timestamp'],
                    "drawdown_pct": round(drawdown_pct, 2),
                    "equity": round(equity, 2),
                    "peak_equity": round(peak_equity, 2)
                })
                
                if drawdown_pct > max_drawdown_pct:
                    max_drawdown_pct = drawdown_pct
                    max_drawdown = peak_equity - equity
        
        # Calculate current drawdown
        if peak_equity > 0:
            current_drawdown_pct = ((peak_equity - current_capital) / peak_equity) * 100
        
        # Count underwater periods (consecutive points below peak)
        underwater_periods = 0
        in_underwater = False
        for point in drawdown_points:
            if point['drawdown_pct'] > 0:
                if not in_underwater:
                    underwater_periods += 1
                    in_underwater = True
            else:
                in_underwater = False
        
        return {
            "range": range,
            "start_time": start_time.isoformat(),
            "end_time": now.isoformat(),
            "max_drawdown_pct": round(max_drawdown_pct, 2),
            "max_drawdown_amount": round(max_drawdown, 2),
            "current_drawdown_pct": round(max(0, current_drawdown_pct), 2),
            "peak_equity": round(peak_equity, 2),
            "current_equity": round(current_capital, 2),
            "underwater_periods": underwater_periods,
            "drawdown_curve": drawdown_points,
            "timestamp": now.isoformat()
        }
        
    except Exception as e:
        logger.error(f"Get drawdown analysis error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/win_rate")
async def get_win_rate_stats(
    period: str = Query("all", regex="^(today|7d|30d|all)$"),
    user_id: str = Depends(get_current_user)
):
    """Get comprehensive win rate and trade statistics
    
    Returns:
        Win rate, average win/loss, profit factor, best/worst trades
    """
    try:
        now = datetime.now(timezone.utc)
        
        if period == "today":
            start_time = now.replace(hour=0, minute=0, second=0, microsecond=0)
        elif period == "7d":
            start_time = now - timedelta(days=7)
        elif period == "30d":
            start_time = now - timedelta(days=30)
        else:  # all
            start_time = datetime(2020, 1, 1, tzinfo=timezone.utc)
        
        # Get trades in period
        trades = await db.trades_collection.find(
            {
                "user_id": user_id,
                "timestamp": {"$gte": start_time.isoformat()}
            },
            {"_id": 0}
        ).to_list(10000)
        
        if not trades:
            return {
                "period": period,
                "total_trades": 0,
                "winning_trades": 0,
                "losing_trades": 0,
                "win_rate_pct": 0,
                "avg_win": 0,
                "avg_loss": 0,
                "profit_factor": 0,
                "best_trade": 0,
                "worst_trade": 0,
                "total_pnl": 0,
                "timestamp": now.isoformat()
            }
        
        # Calculate statistics using canonical field normalization
        # Use net_pnl (primary) → fallback profit_loss
        winning_trades = [t for t in trades if t.get('net_pnl', t.get('profit_loss', 0)) > 0]
        losing_trades = [t for t in trades if t.get('net_pnl', t.get('profit_loss', 0)) < 0]
        
        total_trades = len(trades)
        win_count = len(winning_trades)
        loss_count = len(losing_trades)
        
        gross_profit = sum(t.get('net_pnl', t.get('profit_loss', 0)) for t in winning_trades)
        gross_loss = abs(sum(t.get('net_pnl', t.get('profit_loss', 0)) for t in losing_trades))
        total_pnl = sum(t.get('net_pnl', t.get('profit_loss', 0)) for t in trades)
        
        win_rate_pct = (win_count / total_trades * 100) if total_trades > 0 else 0
        avg_win = (gross_profit / win_count) if win_count > 0 else 0
        avg_loss = (gross_loss / loss_count) if loss_count > 0 else 0
        profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else float('inf') if gross_profit > 0 else 0
        
        # Find best and worst trades
        all_pnls = [t.get('net_pnl', t.get('profit_loss', 0)) for t in trades]
        best_trade = max(all_pnls) if all_pnls else 0
        worst_trade = min(all_pnls) if all_pnls else 0
        
        return {
            "period": period,
            "start_time": start_time.isoformat(),
            "end_time": now.isoformat(),
            "total_trades": total_trades,
            "winning_trades": win_count,
            "losing_trades": loss_count,
            "win_rate_pct": round(win_rate_pct, 2),
            "avg_win": round(avg_win, 2),
            "avg_loss": round(avg_loss, 2),
            "profit_factor": round(profit_factor, 2) if profit_factor != float('inf') else 999.99,
            "best_trade": round(best_trade, 2),
            "worst_trade": round(worst_trade, 2),
            "gross_profit": round(gross_profit, 2),
            "gross_loss": round(gross_loss, 2),
            "total_pnl": round(total_pnl, 2),
            "timestamp": now.isoformat()
        }
        
    except Exception as e:
        logger.error(f"Get win rate stats error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/summary")
async def get_analytics_summary(user_id: str = Depends(get_current_user)):
    """Canonical Analytics Summary - SINGLE SOURCE OF TRUTH for all dashboard totals
    
    This endpoint returns all monetary totals, trade stats, and performance metrics.
    All frontend components MUST use this endpoint - no duplicate calculations in JS.
    
    Returns:
        Complete summary with:
        - Gross profit, total fees, net profit (cash-out value)
        - Total equity, initial capital, profit percentage
        - Trade counts and win rate
        - Per-exchange breakdown
        - Per-bot summary
        - Today's performance
    """
    try:
        from services.profit_service import profit_service
        
        # Get all user bots (exclude deleted)
        bots = await db.bots_collection.find(
            {"user_id": user_id, "status": {"$nin": ["deleted", "marked_for_deletion"]}},
            {"_id": 0}
        ).to_list(1000)
        
        # Calculate capital totals
        initial_capital = sum(bot.get('initial_capital', 0) for bot in bots)
        current_capital = sum(bot.get('current_capital', 0) for bot in bots)
        
        # Get trade statistics with gross/fees/net breakdown
        all_stats = await profit_service.get_trade_stats(user_id)
        paper_stats = await profit_service.get_trade_stats(user_id, "paper")
        live_stats = await profit_service.get_trade_stats(user_id, "live")
        
        # Get today's profit
        profit_today = await profit_service.calculate_profit_today(user_id)
        
        # Calculate profit percentage
        profit_pct = ((current_capital - initial_capital) / initial_capital * 100) if initial_capital > 0 else 0
        
        # Per-exchange breakdown
        exchange_breakdown = {}
        for exchange in ["luno", "binance", "kucoin", "bybit", "bitget"]:
            exchange_bots = [b for b in bots if b.get('exchange', '').lower() == exchange]
            if exchange_bots:
                exchange_breakdown[exchange] = {
                    "bot_count": len(exchange_bots),
                    "capital": sum(b.get('current_capital', 0) for b in exchange_bots),
                    "profit": sum(b.get('total_profit', 0) for b in exchange_bots)
                }
        
        # Per-bot summary (top 10 by profit)
        bot_summaries = []
        for bot in sorted(bots, key=lambda b: b.get('total_profit', 0), reverse=True)[:10]:
            bot_summaries.append({
                "bot_id": bot['id'],
                "name": bot.get('name'),
                "exchange": bot.get('exchange'),
                "mode": bot.get('trading_mode'),
                "status": bot.get('status'),
                "capital": round(bot.get('current_capital', 0), 2),
                "profit": round(bot.get('total_profit', 0), 2),
                "win_rate": round(bot.get('win_rate', 0), 2),
                "trades": bot.get('trades_count', 0)
            })
        
        # Quarantine and training counts
        quarantined_count = len([b for b in bots if b.get('status') == 'quarantined'])
        training_count = len([b for b in bots if b.get('status') == 'training'])
        paused_count = len([b for b in bots if b.get('status') == 'paused'])
        active_count = len([b for b in bots if b.get('status') == 'active'])
        
        return {
            # CANONICAL CASH-OUT FIELDS (B1)
            # These are THE authoritative money values users can withdraw
            "equity_current": round(current_capital, 2),  # Sum of current_capital (what's in bots now)
            "pnl_total_net": round(current_capital - initial_capital, 2),  # Total net P&L (equity - starting)
            "pnl_today_net": round(profit_today, 2),  # Today's net P&L only
            "fees_total": round(all_stats['total_fees'], 2),  # All fees paid
            "fees_today": round(all_stats.get('fees_today', 0), 2),  # Today's fees
            
            # Core monetary totals (backend is source of truth)
            "gross_profit": round(all_stats['gross_profit'], 2),
            "total_fees": round(all_stats['total_fees'], 2),
            "net_profit": round(all_stats['net_profit'], 2),  # True cash-out value (same as pnl_total_net)
            
            # Capital breakdown
            "initial_capital": round(initial_capital, 2),
            "current_capital": round(current_capital, 2),
            "profit_pct": round(profit_pct, 2),
            
            # Trade statistics
            "total_trades": all_stats['total_trades'],
            "winning_trades": all_stats['winning_trades'],
            "losing_trades": all_stats['losing_trades'],
            "win_rate": round(all_stats['win_rate'], 2),
            
            # Today's performance
            "profit_today": round(profit_today, 2),
            
            # Mode breakdown
            "paper_stats": {
                "trades": paper_stats['total_trades'],
                "net_profit": round(paper_stats['net_profit'], 2),
                "fees": round(paper_stats['total_fees'], 2)
            },
            "live_stats": {
                "trades": live_stats['total_trades'],
                "net_profit": round(live_stats['net_profit'], 2),
                "fees": round(live_stats['total_fees'], 2)
            },
            
            # Bot status counts
            "bot_counts": {
                "total": len(bots),
                "active": active_count,
                "paused": paused_count,
                "quarantined": quarantined_count,
                "training": training_count
            },
            
            # Exchange breakdown
            "exchanges": exchange_breakdown,
            
            # Top performing bots
            "top_bots": bot_summaries,
            
            # Metadata
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "user_id": user_id
        }
        
    except Exception as e:
        logger.error(f"Get analytics summary error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/countdown")
async def get_countdown_to_target(
    target_amount: Optional[float] = Query(10000.0, description="Target amount to reach"),
    user_id: str = Depends(get_current_user)
):
    """Countdown to target - forecasts days left based on actual net performance (C1)
    
    Countdown starts from FIRST TRADE (not midnight) and updates after every trade.
    Uses avg_daily_net_pnl computed from trade #1 to now.
    
    Args:
        target_amount: Target profit amount (default: 10000)
        user_id: Current user ID
        
    Returns:
        Countdown metrics including:
        - target_amount
        - equity_current
        - net_pnl_total
        - avg_daily_net_pnl (from first trade to now)
        - days_elapsed (since first trade)
        - days_to_target_estimate
        - confidence metric
        - last_updated_at
    """
    try:
        from services.profit_service import profit_service
        
        # Get all user bots (exclude deleted)
        bots = await db.bots_collection.find(
            {"user_id": user_id, "status": {"$nin": ["deleted", "marked_for_deletion"]}},
            {"_id": 0}
        ).to_list(1000)
        
        # Calculate current equity
        equity_current = sum(bot.get('current_capital', 0) for bot in bots)
        initial_capital = sum(bot.get('initial_capital', 0) for bot in bots)
        net_pnl_total = equity_current - initial_capital
        
        # Get first trade timestamp
        first_trade = await db.trades_collection.find_one(
            {"user_id": user_id},
            {"_id": 0, "timestamp": 1},
            sort=[("timestamp", 1)]
        )
        
        if not first_trade:
            # No trades yet
            return {
                "target_amount": target_amount,
                "equity_current": round(equity_current, 2),
                "net_pnl_total": round(net_pnl_total, 2),
                "avg_daily_net_pnl": 0,
                "days_elapsed": 0,
                "days_to_target_estimate": None,
                "confidence": "insufficient_data",
                "message": "No trades yet - countdown will start after first trade",
                "last_updated_at": datetime.now(timezone.utc).isoformat()
            }
        
        # Calculate days elapsed since first trade
        first_trade_time = first_trade['timestamp']
        if isinstance(first_trade_time, str):
            first_trade_dt = datetime.fromisoformat(first_trade_time.replace('Z', '+00:00'))
        else:
            first_trade_dt = first_trade_time
        
        now = datetime.now(timezone.utc)
        days_elapsed = (now - first_trade_dt).total_seconds() / 86400
        
        # Calculate average daily net PnL
        if days_elapsed > 0:
            avg_daily_net_pnl = net_pnl_total / days_elapsed
        else:
            avg_daily_net_pnl = 0
        
        # Calculate days to target
        remaining = target_amount - net_pnl_total
        
        if avg_daily_net_pnl > 0:
            days_to_target_estimate = remaining / avg_daily_net_pnl
        else:
            days_to_target_estimate = None  # Can't estimate with zero or negative avg
        
        # Calculate confidence metric
        # More trades and more days = higher confidence
        total_trades = await db.trades_collection.count_documents({"user_id": user_id})
        
        if total_trades < 10:
            confidence = "low"
        elif total_trades < 50 or days_elapsed < 3:
            confidence = "medium"
        else:
            confidence = "high"
        
        # Calculate volatility (standard deviation of daily pnl)
        # Get daily profit series for volatility
        from services.profit_service import profit_service
        daily_series = await profit_service.get_daily_profit_series(user_id, days=min(int(days_elapsed) + 1, 30))
        
        if len(daily_series) > 1:
            profits = [d['profit'] for d in daily_series]
            mean_profit = sum(profits) / len(profits)
            variance = sum((p - mean_profit) ** 2 for p in profits) / len(profits)
            std_dev = variance ** 0.5
            
            # Adjust confidence based on volatility
            if std_dev > abs(mean_profit) * 2:  # High volatility
                if confidence == "high":
                    confidence = "medium"
                elif confidence == "medium":
                    confidence = "low"
        
        return {
            "target_amount": target_amount,
            "equity_current": round(equity_current, 2),
            "net_pnl_total": round(net_pnl_total, 2),
            "avg_daily_net_pnl": round(avg_daily_net_pnl, 2),
            "days_elapsed": round(days_elapsed, 2),
            "days_to_target_estimate": round(days_to_target_estimate, 2) if days_to_target_estimate is not None else None,
            "confidence": confidence,
            "total_trades": total_trades,
            "first_trade_at": first_trade_time,
            "last_updated_at": datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as e:
        logger.error(f"Get countdown error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/insights")
async def get_trading_insights(user_id: str = Depends(get_current_user)):
    """Trading insights - wins/losses for trend learning (E)
    
    Returns learning records for AI to form trends:
    - Top winning/losing pairs
    - Win rate by exchange + pair
    - Average net pnl per pair
    - Drawdown by bot
    
    Used for training/quarantine reports and chat daily summary.
    """
    try:
        # Get all closed trades
        trades = await db.trades_collection.find(
            {"user_id": user_id, "status": "closed"},
            {"_id": 0}
        ).to_list(10000)
        
        if not trades:
            return {
                "message": "No trades yet - insights will be available after trading",
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        
        # Analyze by pair
        pair_stats = {}
        for trade in trades:
            symbol = trade.get('symbol') or trade.get('pair', 'UNKNOWN')
            if symbol not in pair_stats:
                pair_stats[symbol] = {
                    "total_trades": 0,
                    "wins": 0,
                    "losses": 0,
                    "total_pnl": 0,
                    "total_fees": 0
                }
            
            net_pnl = trade.get('net_pnl', trade.get('profit_loss', 0))
            fee = trade.get('fee_amount', 0)
            
            pair_stats[symbol]["total_trades"] += 1
            pair_stats[symbol]["total_pnl"] += net_pnl
            pair_stats[symbol]["total_fees"] += fee
            
            if net_pnl > 0:
                pair_stats[symbol]["wins"] += 1
            else:
                pair_stats[symbol]["losses"] += 1
        
        # Calculate averages and win rates
        for symbol, stats in pair_stats.items():
            stats["avg_pnl"] = stats["total_pnl"] / stats["total_trades"] if stats["total_trades"] > 0 else 0
            stats["win_rate"] = (stats["wins"] / stats["total_trades"] * 100) if stats["total_trades"] > 0 else 0
        
        # Sort by total PnL
        sorted_pairs = sorted(pair_stats.items(), key=lambda x: x[1]["total_pnl"], reverse=True)
        
        top_winning_pairs = [
            {"symbol": symbol, **stats}
            for symbol, stats in sorted_pairs[:10]
            if stats["total_pnl"] > 0
        ]
        
        top_losing_pairs = [
            {"symbol": symbol, **stats}
            for symbol, stats in sorted(sorted_pairs, key=lambda x: x[1]["total_pnl"])[:10]
            if stats["total_pnl"] < 0
        ]
        
        # Analyze by exchange
        exchange_stats = {}
        for trade in trades:
            exchange = trade.get('exchange', 'unknown')
            if exchange not in exchange_stats:
                exchange_stats[exchange] = {
                    "total_trades": 0,
                    "wins": 0,
                    "total_pnl": 0
                }
            
            net_pnl = trade.get('net_pnl', trade.get('profit_loss', 0))
            exchange_stats[exchange]["total_trades"] += 1
            exchange_stats[exchange]["total_pnl"] += net_pnl
            
            if net_pnl > 0:
                exchange_stats[exchange]["wins"] += 1
        
        # Calculate win rates by exchange
        for exchange, stats in exchange_stats.items():
            stats["win_rate"] = (stats["wins"] / stats["total_trades"] * 100) if stats["total_trades"] > 0 else 0
            stats["avg_pnl"] = stats["total_pnl"] / stats["total_trades"] if stats["total_trades"] > 0 else 0
        
        # Analyze by bot
        bot_stats = {}
        for trade in trades:
            bot_id = trade.get('bot_id')
            if bot_id and bot_id not in bot_stats:
                bot_stats[bot_id] = {
                    "total_trades": 0,
                    "total_pnl": 0,
                    "peak_equity": 0,
                    "current_equity": 0,
                    "max_drawdown": 0
                }
            
            if bot_id:
                net_pnl = trade.get('net_pnl', trade.get('profit_loss', 0))
                bot_stats[bot_id]["total_trades"] += 1
                bot_stats[bot_id]["total_pnl"] += net_pnl
                bot_stats[bot_id]["current_equity"] += net_pnl
                
                # Track peak and drawdown
                if bot_stats[bot_id]["current_equity"] > bot_stats[bot_id]["peak_equity"]:
                    bot_stats[bot_id]["peak_equity"] = bot_stats[bot_id]["current_equity"]
                
                current_dd = bot_stats[bot_id]["peak_equity"] - bot_stats[bot_id]["current_equity"]
                if current_dd > bot_stats[bot_id]["max_drawdown"]:
                    bot_stats[bot_id]["max_drawdown"] = current_dd
        
        # Get bot names
        bots = await db.bots_collection.find(
            {"user_id": user_id},
            {"_id": 0, "id": 1, "name": 1}
        ).to_list(1000)
        bot_names = {bot['id']: bot.get('name') for bot in bots}
        
        # Add bot names to stats
        bot_insights = []
        for bot_id, stats in bot_stats.items():
            bot_insights.append({
                "bot_id": bot_id,
                "bot_name": bot_names.get(bot_id, "Unknown"),
                **stats
            })
        
        return {
            "top_winning_pairs": top_winning_pairs,
            "top_losing_pairs": top_losing_pairs,
            "exchange_performance": exchange_stats,
            "bot_drawdowns": sorted(bot_insights, key=lambda x: x["max_drawdown"], reverse=True)[:10],
            "total_trades_analyzed": len(trades),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as e:
        logger.error(f"Get trading insights error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
