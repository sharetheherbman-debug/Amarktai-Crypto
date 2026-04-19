"""
Ledger Endpoints - Phase 1 (Read-Only + Parallel Write)

Provides read-only access to immutable ledger data:
- Portfolio summary (equity, PnL, fees, drawdown)
- Profit series (daily/weekly/monthly)
- Countdown status (equity-based projections)
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Optional, Dict
from datetime import datetime, timedelta, timezone
import logging
import time

from auth import get_current_user
import database as db
from database import get_database
from services.ledger_service import get_ledger_service
from services.bot_filters import bot_not_deleted_filter

router = APIRouter(prefix="/api", tags=["ledger"])
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Short-TTL in-process cache for /portfolio/summary.
# The endpoint runs 8 sequential DB queries and is polled every 15s by two
# independent frontend hooks simultaneously.  A 30s cache ensures concurrent
# dashboard requests share one computation and also survive reconnect storms.
# ---------------------------------------------------------------------------
_PORTFOLIO_CACHE: dict = {}  # user_id → (monotonic_ts: float, result: dict)
_PORTFOLIO_CACHE_TTL = 30  # seconds


@router.get("/portfolio/summary")
async def get_portfolio_summary(
    current_user: str = Depends(get_current_user),
    db=Depends(get_database)
):
    """
    Get portfolio summary from ledger
    
    Returns:
    - equity: Current total equity
    - realized_pnl: Closed position profits
    - unrealized_pnl: Open position profits (Phase 2)
    - fees_total: Total fees paid
    - drawdown_current: Current drawdown %
    - drawdown_max: Maximum drawdown %
    - win_rate: Win rate (if calculable)
    """
    try:
        user_id = current_user

        # Return cached result when still fresh to avoid 8 serial DB queries
        # per frontend poll cycle (two hooks poll this endpoint independently).
        now_mono = time.monotonic()
        cached = _PORTFOLIO_CACHE.get(user_id)
        if cached is not None:
            cache_ts, cache_result = cached
            if (now_mono - cache_ts) < _PORTFOLIO_CACHE_TTL:
                return cache_result

        ledger = get_ledger_service(db)
        
        # Compute core metrics
        equity = await ledger.compute_equity(user_id)
        realized_pnl = await ledger.compute_realized_pnl(user_id)
        unrealized_pnl = await ledger.compute_unrealized_pnl(user_id)
        fees_total = await ledger.compute_fees_paid(user_id)
        current_dd, max_dd = await ledger.compute_drawdown(user_id)
        
        # Get stats
        stats = await ledger.get_stats(user_id)
        
        # Calculate win rate from realized trades using FIFO position tracking
        win_rate = await ledger.calculate_win_rate(user_id)
        if win_rate is not None:
            win_rate = round(win_rate * 100, 2)  # Convert to percentage

        wallet_summary = {}
        try:
            from services.wallet_summary_service import wallet_summary_service
            wallet_summary = await wallet_summary_service.get_summary(user_id)
        except Exception as e:
            logger.warning(f"Wallet summary unavailable: {e}")
        
        result = {
            "equity": round(equity, 2),
            "realized_pnl": round(realized_pnl, 2),
            "unrealized_pnl": round(unrealized_pnl, 2),
            "fees_total": round(fees_total, 2),
            "net_pnl": round(realized_pnl + unrealized_pnl - fees_total, 2),
            "drawdown_current": round(current_dd * 100, 2),
            "drawdown_max": round(max_dd * 100, 2),
            "win_rate": win_rate,
            "total_fills": stats.get("total_fills", 0),
            "total_volume": round(stats.get("total_volume", 0), 2),
            "wallet_summary": wallet_summary,
            "data_source": "ledger",
            "phase": "1_read_only"
        }
        _PORTFOLIO_CACHE[user_id] = (time.monotonic(), result)
        return result
    except Exception as e:
        logger.error(f"Error getting portfolio summary: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get portfolio summary: {str(e)}")


@router.get("/profits")
async def get_profits(
    period: str = Query("daily", regex="^(daily|weekly|monthly)$"),
    limit: int = Query(30, ge=1, le=365),
    current_user: str = Depends(get_current_user),
    db=Depends(get_database)
):
    """
    Get profit time series from ledger
    
    Parameters:
    - period: daily, weekly, or monthly
    - limit: Number of periods to return
    
    Returns: Time series of profits by period
    """
    try:
        ledger = get_ledger_service(db)
        # current_user is now a string user_id, not a dict
        user_id = current_user
        
        series = await ledger.profit_series(user_id, period=period, limit=limit)
        
        return {
            "period": period,
            "limit": limit,
            "series": series,
            "data_source": "ledger",
            "phase": "1_read_only"
        }
    except Exception as e:
        logger.error(f"Error getting profits: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get profits: {str(e)}")


@router.get("/countdown/status")
async def get_countdown_status(
    target: float = Query(1000000, description="Target amount (e.g., R1M = 1000000)"),
    current_user: str = Depends(get_current_user),
    db=Depends(get_database)
):
    """
    Get countdown to target based on actual equity and projections
    
    Returns:
    - current_equity: Current equity from ledger
    - target: Target amount
    - remaining: Amount remaining to target
    - progress_pct: Progress percentage
    - days_to_target_linear: Days at current 30d avg daily profit
    - days_to_target_compound: Days with compound interest model
    """
    try:
        ledger = get_ledger_service(db)
        user_id = current_user
        
        # Get current equity
        current_equity = await ledger.compute_equity(user_id, currency="ZAR")

        # Total trades should count closed trade documents (fills inflate counts).
        trades_total = await db["trades"].count_documents({
            "user_id": user_id,
            "status": "closed",
        })

        if trades_total < 1:
            return {
                "ready": False,
                "message": "No closed trades yet — projections start after first trade",
                "trades_remaining": 1,
                "trades_total": trades_total,
                "current_equity": round(current_equity, 2),
                "target": target,
                "remaining": round(target - current_equity, 2),
                "progress_pct": round((current_equity / target * 100), 2) if target > 0 else 0,
                "data_source": "ledger",
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        
        # Get 30-day profit series to calculate average
        series = await ledger.profit_series(user_id, period="daily", limit=30)
        
        # Calculate average daily profit from series
        if series:
            total_net_profit = sum(day.get("net_profit", 0) for day in series)
            avg_daily_profit = total_net_profit / len(series)
        else:
            avg_daily_profit = 0
        
        remaining = target - current_equity
        progress_pct = (current_equity / target * 100) if target > 0 else 0
        
        # Linear projection
        if avg_daily_profit > 0:
            days_to_target_linear = remaining / avg_daily_profit
        else:
            days_to_target_linear = None
        
        # Compound projection (assume 0.1% daily compound growth)
        daily_compound_rate = 0.001  # 0.1% daily
        if current_equity > 0 and daily_compound_rate > 0:
            import math
            try:
                days_to_target_compound = math.log(target / current_equity) / math.log(1 + daily_compound_rate)
            except (ValueError, ZeroDivisionError):
                days_to_target_compound = None
        else:
            days_to_target_compound = None
        
        return {
            "ready": True,
            "current_equity": round(current_equity, 2),
            "target": target,
            "remaining": round(remaining, 2),
            "progress_pct": round(progress_pct, 2),
            "avg_daily_profit_30d": round(avg_daily_profit, 2),
            "days_to_target_linear": round(days_to_target_linear, 0) if days_to_target_linear else None,
            "days_to_target_compound": round(days_to_target_compound, 0) if days_to_target_compound else None,
            "trades_total": trades_total,
            "data_source": "ledger",
            "phase": "1_read_only"
        }
    except Exception as e:
        logger.error(f"Error getting countdown status: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get countdown status: {str(e)}")


@router.get("/ledger/fills")
async def get_fills(
    bot_id: Optional[str] = None,
    bot_type: Optional[str] = Query(None, regex="^(normal|scalper)$"),
    since: Optional[str] = None,
    until: Optional[str] = None,
    limit: int = Query(100, ge=1, le=1000),
    current_user: str = Depends(get_current_user),
    db=Depends(get_database)
):
    """
    Get fills from ledger with optional filters
    
    Parameters:
    - bot_id: Filter by bot
    - bot_type: Filter by bot type (normal or scalper)
    - since: ISO timestamp (e.g., 2025-01-01T00:00:00Z)
    - until: ISO timestamp
    - limit: Max results
    """
    try:
        import database as db_module

        ledger = get_ledger_service(db)
        user_id = current_user

        effective_bot_id = bot_id
        if bot_type and not bot_id:
            matching_bots = await db_module.bots_collection.find(
                bot_not_deleted_filter({"user_id": user_id, "bot_type": bot_type}),
                {"_id": 0, "id": 1}
            ).to_list(200)
            bot_ids = [b["id"] for b in matching_bots]
        else:
            bot_ids = None

        # Parse dates
        since_dt = datetime.fromisoformat(since.replace('Z', '+00:00')) if since else None
        until_dt = datetime.fromisoformat(until.replace('Z', '+00:00')) if until else None
        
        if bot_ids is not None:
            all_fills = []
            for bid in bot_ids:
                fills_chunk = await ledger.get_fills(
                    user_id=user_id,
                    bot_id=bid,
                    since=since_dt,
                    until=until_dt,
                    limit=limit
                )
                all_fills.extend(fills_chunk)
            all_fills.sort(key=lambda f: f.get("timestamp", ""), reverse=True)
            fills = all_fills[:limit]
        else:
            fills = await ledger.get_fills(
                user_id=user_id,
                bot_id=effective_bot_id,
                since=since_dt,
                until=until_dt,
                limit=limit
            )
        
        return {
            "fills": fills,
            "count": len(fills),
            "filters": {
                "bot_id": bot_id,
                "bot_type": bot_type,
                "since": since,
                "until": until,
                "limit": limit
            },
            "data_source": "ledger",
            "phase": "1_read_only"
        }
    except Exception as e:
        logger.error(f"Error getting fills: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get fills: {str(e)}")


@router.post("/ledger/funding")
async def record_funding(
    amount: float,
    currency: str = "USDT",
    description: Optional[str] = None,
    current_user: str = Depends(get_current_user),
    db=Depends(get_database)
):
    """
    Record a funding event (capital injection)
    
    This is a write endpoint but safe for Phase 1 as it's append-only
    """
    try:
        ledger = get_ledger_service(db)
        user_id = current_user
        
        event_id = await ledger.append_event(
            user_id=user_id,
            event_type="funding",
            amount=amount,
            currency=currency,
            timestamp=datetime.utcnow(),
            description=description or f"Funding: {amount} {currency}"
        )
        
        return {
            "event_id": event_id,
            "message": f"Recorded funding of {amount} {currency}",
            "phase": "1_append_only"
        }
    except Exception as e:
        logger.error(f"Error recording funding: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to record funding: {str(e)}")


@router.get("/ledger/audit-trail")
async def get_audit_trail(
    bot_id: Optional[str] = None,
    limit: int = Query(100, ge=1, le=1000),
    current_user: str = Depends(get_current_user),
    db=Depends(get_database)
):
    """
    Get complete audit trail (fills + events)
    
    Returns chronological list of all ledger entries
    """
    try:
        ledger = get_ledger_service(db)
        user_id = current_user
        
        # Get fills
        fills = await ledger.get_fills(user_id=user_id, bot_id=bot_id, limit=limit)
        
        # Get events
        event_query = {"user_id": user_id}
        if bot_id:
            event_query["bot_id"] = bot_id
        
        events_cursor = ledger.ledger_events.find(event_query).sort("timestamp", -1).limit(limit)
        events = await events_cursor.to_list(length=limit)
        
        # Convert ObjectId
        for event in events:
            event["_id"] = str(event["_id"])
        
        # Combine and sort
        fills_with_type = [{"type": "fill", **f} for f in fills]
        events_with_type = [{"type": "event", **e} for e in events]
        
        all_entries = fills_with_type + events_with_type
        all_entries.sort(key=lambda x: x.get("timestamp", datetime.min), reverse=True)
        
        return {
            "audit_trail": all_entries[:limit],
            "count": len(all_entries[:limit]),
            "filters": {
                "bot_id": bot_id,
                "limit": limit
            },
            "data_source": "ledger",
            "phase": "1_read_only"
        }
    except Exception as e:
        logger.error(f"Error getting audit trail: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to get audit trail: {str(e)}")


@router.get("/ledger/reconcile")
async def reconcile_ledger(
    current_user: str = Depends(get_current_user),
    db=Depends(get_database)
):
    """
    Reconcile ledger with legacy trades collection
    
    Compares ledger-based equity with trades collection totals
    and identifies any discrepancies.
    
    Returns detailed reconciliation report with status and recommendations.
    """
    try:
        ledger = get_ledger_service(db)
        user_id = current_user
        
        report = await ledger.reconcile_with_trades_collection(user_id)
        
        return report
    except Exception as e:
        logger.error(f"Error reconciling ledger: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to reconcile ledger: {str(e)}")


@router.get("/ledger/verify-integrity")
async def verify_ledger_integrity(
    current_user: str = Depends(get_current_user),
    db=Depends(get_database)
):
    """
    Verify ledger integrity for current user
    
    Performs multiple integrity checks:
    - Equity recomputation consistency
    - Fee field completeness
    - Duplicate detection
    - Chronological ordering
    - Required fields presence
    
    Returns detailed verification report with passed/failed checks.
    """
    try:
        ledger = get_ledger_service(db)
        user_id = current_user
        
        report = await ledger.verify_integrity(user_id)
        
        return report
    except Exception as e:
        logger.error(f"Error verifying ledger integrity: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to verify ledger integrity: {str(e)}")


@router.get("/ledger/invariants/check")
async def check_ledger_invariants(
    current_user: str = Depends(get_current_user),
    db=Depends(get_database)
):
    """
    Check ledger invariants: total == available + allocated.

    Computes wallet truth from ledger + open trades and returns invariant
    status.  Always returns 200 with a structured result (never raises 500)
    so that monitoring scripts can poll this endpoint safely.

    Returns:
        invariant_ok: bool – True when total == available + allocated (within rounding)
        available: float
        allocated: float
        total: float
        drift: float – absolute difference (0.0 when invariant holds)
        last_drift_reason: str or null
        computed_from: dict with ledger and trades summaries
    """
    user_id = current_user
    try:
        ledger = get_ledger_service(db)
        equity = await ledger.compute_equity(user_id)

        # Compute allocated from open trades
        allocated = 0.0
        drift_reason = None
        try:
            open_trades_cursor = db.trades_collection.find(
                {"user_id": user_id, "status": "open"},
                {"_id": 0, "entry_value": 1, "trade_amount": 1}
            )
            async for trade in open_trades_cursor:
                ev = float(trade.get("entry_value") or trade.get("trade_amount") or 0)
                allocated += ev
        except Exception as trade_err:
            drift_reason = f"trade_lookup_error: {trade_err}"

        available = max(0.0, equity - allocated)
        total = available + allocated
        drift = abs(total - equity)
        invariant_ok = drift < 0.01  # within rounding (currency-agnostic 1-cent tolerance)

        if not invariant_ok and drift_reason is None:
            drift_reason = f"total={total:.4f} != equity={equity:.4f} (drift={drift:.4f})"

        return {
            "invariant_ok": invariant_ok,
            "available": round(available, 4),
            "allocated": round(allocated, 4),
            "total": round(total, 4),
            "equity": round(equity, 4),
            "drift": round(drift, 6),
            "last_drift_reason": drift_reason,
            "computed_from": {
                "ledger_equity": round(equity, 4),
                "open_trades_allocated": round(allocated, 4),
            },
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as e:
        logger.error(f"Ledger invariants check error: {e}")
        return {
            "invariant_ok": False,
            "available": 0.0,
            "allocated": 0.0,
            "total": 0.0,
            "equity": 0.0,
            "drift": 0.0,
            "last_drift_reason": str(e),
            "computed_from": {},
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
