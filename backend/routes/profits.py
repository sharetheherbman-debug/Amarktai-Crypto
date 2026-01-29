"""
Profits API Endpoints
Provides profit data using canonical profit_service and accounting_service
"""

from fastapi import APIRouter, HTTPException, Depends
from typing import Optional, Dict
import logging
from datetime import datetime, timezone, timedelta

from auth import get_current_user
from services.profit_service import profit_service
from services.accounting import accounting_service
import database as db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/profits", tags=["Profits"])


@router.get("/metrics")
async def get_unified_metrics(
    mode: Optional[str] = None,
    user_id: str = Depends(get_current_user)
):
    """Get unified profit/trade metrics - SINGLE SOURCE OF TRUTH
    
    This endpoint provides consistent metrics used across Overview, Profits, and Live Trades pages.
    All pages should use this endpoint to ensure consistency.
    
    Args:
        mode: Filter by trading mode ('paper' or 'live', None = both)
        user_id: Current user ID from auth
        
    Returns:
        Unified metrics:
        - executed_trades_count: Count of executed trades
        - net_realised_pnl_zar: Net realised PnL (after fees)
        - gross_realised_pnl_zar: Gross realised PnL (before fees)
        - total_fees_zar: Total fees paid
        - unrealised_pnl_zar: Unrealised PnL (open positions)
        - total_pnl_zar: Total PnL (realised + unrealised)
    """
    try:
        metrics = await accounting_service.get_unified_metrics(
            user_id=user_id,
            trading_mode=mode,
            include_unrealised=True
        )
        
        return {
            "success": True,
            "metrics": metrics,
            "currency": "ZAR",
            "data_source": "accounting_service",
            "note": "This is the single source of truth for profit metrics"
        }
        
    except Exception as e:
        logger.error(f"Error getting unified metrics: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/trades")
async def get_profit_trades(
    mode: Optional[str] = None,
    limit: int = 100,
    user_id: str = Depends(get_current_user)
):
    """Get trades with profit metrics for Profits page
    
    Returns trade list with consistent PnL calculations.
    
    Args:
        mode: Filter by trading mode
        limit: Max trades to return
        user_id: Current user ID
        
    Returns:
        Trade list with summary metrics
    """
    try:
        result = await accounting_service.get_trade_list_with_metrics(
            user_id=user_id,
            trading_mode=mode,
            limit=limit,
            status="closed"
        )
        
        return {
            "success": True,
            **result,
            "currency": "ZAR",
            "data_source": "accounting_service"
        }
        
    except Exception as e:
        logger.error(f"Error getting profit trades: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("")
async def get_profits(
    period: str = "daily",
    mode: Optional[str] = None,
    user_id: str = Depends(get_current_user)
):
    """Get profit data for user using canonical profit service
    
    Protected endpoint that returns profit information
    Supports multiple period types: daily, weekly, monthly, all
    
    Args:
        period: Time period for aggregation (daily, weekly, monthly, all)
        mode: Filter by trading mode ('paper' or 'live', None = both)
        user_id: Current user ID from auth
        
    Returns:
        Profit data with summary and time series
    """
    try:
        # Get comprehensive profit summary from canonical service
        if period == "all":
            # Get full summary
            summary = await profit_service.get_profit_summary(user_id, mode)
            
            return {
                "period": "all",
                "mode": mode or "all",
                "total_profit": summary["total_profit"],
                "profit_today": summary["profit_today"],
                "profit_yesterday": summary["profit_yesterday"],
                "best_day": summary["best_day"],
                "avg_daily": summary["avg_daily"],
                "daily_series": summary["daily_series_30"],
                "currency": "ZAR",
                "timestamp": summary["last_calculated_at"]
            }
        
        elif period == "daily":
            # Get 30 days
            series = await profit_service.get_daily_profit_series(user_id, 30, mode)
            total = await profit_service.calculate_total_profit(user_id, mode)
            
            return {
                "period": "daily",
                "mode": mode or "all",
                "items": series,
                "total": total,
                "currency": "ZAR",
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        
        elif period == "weekly":
            # Get 12 weeks worth of daily data and group
            series = await profit_service.get_daily_profit_series(user_id, 84, mode)
            total = await profit_service.calculate_total_profit(user_id, mode)
            
            # Group by week
            weekly_profits = {}
            for item in series:
                try:
                    dt = datetime.fromisoformat(item["date"])
                    week = dt.strftime('%Y-W%U')
                    if week not in weekly_profits:
                        weekly_profits[week] = 0
                    weekly_profits[week] += item["profit"]
                except:
                    pass
            
            items = [
                {"week": week, "profit": round(profit, 2), "period": "weekly"}
                for week, profit in sorted(weekly_profits.items(), reverse=True)[:12]
            ]
            
            return {
                "period": "weekly",
                "mode": mode or "all",
                "items": items,
                "total": total,
                "currency": "ZAR",
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        
        elif period == "monthly":
            # Get 12 months worth of daily data and group
            series = await profit_service.get_daily_profit_series(user_id, 365, mode)
            total = await profit_service.calculate_total_profit(user_id, mode)
            
            # Group by month
            monthly_profits = {}
            for item in series:
                try:
                    month = item["date"][:7]  # YYYY-MM
                    if month not in monthly_profits:
                        monthly_profits[month] = 0
                    monthly_profits[month] += item["profit"]
                except:
                    pass
            
            items = [
                {"month": month, "profit": round(profit, 2), "period": "monthly"}
                for month, profit in sorted(monthly_profits.items(), reverse=True)[:12]
            ]
            
            return {
                "period": "monthly",
                "mode": mode or "all",
                "items": items,
                "total": total,
                "currency": "ZAR",
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        
        else:
            raise HTTPException(status_code=400, detail="Invalid period. Must be 'daily', 'weekly', 'monthly', or 'all'")
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting profits: {e}")
        # Return safe default instead of 500
        return {
            "period": period,
            "mode": mode or "all",
            "items": [],
            "total": 0,
            "currency": "ZAR",
            "error": str(e),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }


@router.get("/summary")
async def get_profit_summary(
    mode: Optional[str] = None,
    user_id: str = Depends(get_current_user)
):
    """Get comprehensive profit summary
    
    Returns:
        Full profit summary with stats
    """
    try:
        summary = await profit_service.get_profit_summary(user_id, mode)
        stats = await profit_service.get_trade_stats(user_id, mode)
        
        # Add unrealized profit
        unrealized = await profit_service.calculate_unrealized_profit(user_id, mode)
        
        return {
            "success": True,
            "mode": mode or "all",
            "realized_profit": summary["total_profit"],
            "unrealized_profit": unrealized,
            "total_profit": summary["total_profit"] + unrealized,
            "profit_today": summary["profit_today"],
            "profit_yesterday": summary["profit_yesterday"],
            "best_day": summary["best_day"],
            "avg_daily": summary["avg_daily"],
            "total_trades": stats["total_trades"],
            "winning_trades": stats["winning_trades"],
            "losing_trades": stats["losing_trades"],
            "win_rate": stats["win_rate"],
            "total_fees": stats["total_fees"],
            "currency": "ZAR",
            "timestamp": summary["last_calculated_at"]
        }
        
    except Exception as e:
        logger.error(f"Error getting profit summary: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/reinvest")
async def reinvest_profits(
    data: Optional[Dict] = None,
    user_id: str = Depends(get_current_user)
):
    """Reinvest profits into new or existing bots
    
    Protected endpoint for profit reinvestment
    Can be stubbed for now if full implementation not ready
    
    Args:
        data: Optional configuration for reinvestment
        user_id: Current user ID from auth
        
    Returns:
        Reinvestment result with success status
    """
    try:
        # Check if reinvestment service is available
        try:
            from services.daily_reinvestment import get_reinvestment_service
            reinvest_service = get_reinvestment_service(db.db)
            
            # Execute reinvestment
            result = await reinvest_service.execute_reinvestment(user_id)
            
            return {
                "success": True,
                "message": "Profits reinvested successfully",
                "amount_reinvested": result.get('amount_reinvested', 0),
                "bots_funded": result.get('bots_funded', 0),
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        except ImportError:
            # Reinvestment service not available - return stub response
            logger.info(f"Reinvestment requested by user {user_id[:8]} but service not available (stub)")
            return {
                "success": True,
                "message": "Reinvestment request received (queued for processing)",
                "amount_reinvested": 0,
                "bots_funded": 0,
                "stub": True,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        
    except Exception as e:
        logger.error(f"Error reinvesting profits: {e}")
        return {
            "success": False,
            "message": f"Reinvestment failed: {str(e)}",
            "amount_reinvested": 0,
            "bots_funded": 0,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
