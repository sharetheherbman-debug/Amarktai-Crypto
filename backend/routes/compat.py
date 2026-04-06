"""
Compatibility Layer for Legacy Frontend API Calls

This module provides backward-compatible endpoints for older frontend code
that may reference deprecated or renamed API paths. Each endpoint logs a
warning so we can track usage and eventually migrate/remove these aliases.

⚠️ DEPRECATION NOTICE: These endpoints exist for backward compatibility only.
   New code should use the canonical endpoints directly.
"""

from fastapi import APIRouter, HTTPException, Depends, Query
from datetime import datetime, timezone
import logging

from auth import get_current_user
import database as db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["Compatibility Layer"])


# ============================================================================
# ANALYTICS COMPATIBILITY
# ============================================================================

@router.get("/analytics/performance")
async def compat_analytics_performance(
    period: str = Query("all", regex="^(today|7d|30d|all)$"),
    user_id: str = Depends(get_current_user)
):
    """
    COMPAT: GET /api/analytics/performance
    
    ⚠️ DEPRECATED: Use GET /api/analytics/performance_summary instead
    
    This endpoint exists for backward compatibility with older frontend code.
    It returns the same data as /api/analytics/performance_summary but with
    a slightly different response structure that legacy code expects.
    """
    logger.warning(
        f"[COMPAT] /api/analytics/performance called by user {user_id} - "
        "migrate to /api/analytics/performance_summary"
    )
    
    try:
        # Import the actual endpoint function
        from routes.analytics_api import get_performance_summary
        
        # Get data from canonical endpoint
        summary = await get_performance_summary(period=period, user_id=user_id)
        
        # Return frontend-compatible format
        return {
            "total_trades": summary["trades"]["total"],
            "win_rate": summary["trades"]["win_rate_pct"],
            "winning_trades": summary["trades"]["winning"],
            "losing_trades": summary["trades"]["losing"],
            "total_pnl": summary["pnl"]["total"],
            "profit_factor": summary["pnl"]["profit_factor"],
            "gross_profit": summary["pnl"]["gross_profit"],
            "gross_loss": summary["pnl"]["gross_loss"],
            "avg_win": summary["averages"]["avg_win"],
            "avg_loss": summary["averages"]["avg_loss"],
            "period": period,
            "timestamp": summary["timestamp"]
        }
    except Exception as e:
        logger.error(f"[COMPAT] Performance endpoint error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# ORDERS COMPATIBILITY
# ============================================================================

@router.get("/orders")
async def compat_orders_root(user_id: str = Depends(get_current_user)):
    """
    COMPAT: GET /api/orders
    
    ⚠️ DEPRECATED: Use GET /api/orders/pending or /api/orders/history instead
    
    Returns all orders (pending + filled) for backward compatibility.
    New code should use the more specific endpoints.
    """
    logger.warning(
        f"[COMPAT] /api/orders called by user {user_id} - "
        "migrate to /api/orders/pending or /api/orders/history"
    )
    
    try:
        # Get all orders from database
        orders = await db.orders_collection.find(
            {"user_id": user_id},
            {"_id": 0}
        ).to_list(1000)
        
        return {
            "orders": orders,
            "count": len(orders),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    except Exception as e:
        logger.error(f"[COMPAT] Orders endpoint error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# TRADES COMPATIBILITY
# ============================================================================

@router.get("/trades")
async def compat_trades_root(
    limit: int = Query(100, ge=1, le=1000),
    user_id: str = Depends(get_current_user)
):
    """
    COMPAT: GET /api/trades
    
    ⚠️ DEPRECATED: Use GET /api/trades/recent instead
    
    Returns recent trades for backward compatibility.
    """
    logger.warning(
        f"[COMPAT] /api/trades called by user {user_id} - "
        "migrate to /api/trades/recent"
    )
    
    try:
        # Get recent trades
        trades = await db.trades_collection.find(
            {"user_id": user_id},
            {"_id": 0}
        ).sort("timestamp", -1).limit(limit).to_list(limit)
        
        return {
            "trades": trades,
            "count": len(trades),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    except Exception as e:
        logger.error(f"[COMPAT] Trades endpoint error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# LEDGER COMPATIBILITY
# ============================================================================

@router.get("/ledger/summary")
async def compat_ledger_summary(user_id: str = Depends(get_current_user)):
    """
    COMPAT: GET /api/ledger/summary
    
    ⚠️ DEPRECATED: Use GET /api/ledger/balance instead
    
    Returns ledger balance summary for backward compatibility.
    """
    logger.warning(
        f"[COMPAT] /api/ledger/summary called by user {user_id} - "
        "migrate to /api/ledger/balance"
    )
    
    try:
        # Try to use the canonical ledger endpoint
        try:
            from routes.ledger_endpoints import router as ledger_router
            # Get balance from canonical endpoint
            # This would need to be adapted based on actual ledger endpoint structure
            pass
        except:
            pass
        
        # Fallback: calculate from non-deleted bots only.
        # Exclude soft-deleted bots so a post-start-fresh call returns 0.
        bots = await db.bots_collection.find(
            {
                "user_id": user_id,
                "status": {"$ne": "deleted"},
                "deleted_at": {"$exists": False},
            },
            {"_id": 0, "initial_capital": 1, "current_capital": 1, "total_profit": 1}
        ).to_list(1000)
        
        total_initial = sum(bot.get('initial_capital', 0) for bot in bots)
        total_current = sum(bot.get('current_capital', 0) for bot in bots)
        total_profit = sum(bot.get('total_profit', 0) for bot in bots)
        
        return {
            "initial_capital": round(total_initial, 2),
            "current_capital": round(total_current, 2),
            "total_profit": round(total_profit, 2),
            "total_bots": len(bots),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    except Exception as e:
        logger.error(f"[COMPAT] Ledger summary endpoint error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# LIMITS COMPATIBILITY
# ============================================================================

@router.get("/limits")
async def compat_limits_root(user_id: str = Depends(get_current_user)):
    """
    COMPAT: GET /api/limits
    
    ⚠️ DEPRECATED: Use GET /api/limits/user or /api/limits/system instead
    
    Returns user limits for backward compatibility.
    """
    logger.warning(
        f"[COMPAT] /api/limits called by user {user_id} - "
        "migrate to /api/limits/user or /api/limits/system"
    )
    
    try:
        # Get user limits from database
        user = await db.users_collection.find_one(
            {"id": user_id},
            {"_id": 0}
        )
        
        if not user:
            return {
                "max_bots": 10,
                "max_capital_per_bot": 10000,
                "max_total_capital": 100000,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        
        return {
            "max_bots": user.get('max_bots', 10),
            "max_capital_per_bot": user.get('max_capital_per_bot', 10000),
            "max_total_capital": user.get('max_total_capital', 100000),
            "current_bots": user.get('current_bots', 0),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    except Exception as e:
        logger.error(f"[COMPAT] Limits endpoint error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# HEALTH CHECK
# ============================================================================

@router.get("/compat/status")
async def compat_layer_status():
    """
    Check compatibility layer status and list all available compat endpoints.
    
    This endpoint is useful for debugging and understanding which legacy
    endpoints are still being supported.
    """
    return {
        "status": "active",
        "message": "Compatibility layer is operational",
        "compat_endpoints": [
            {
                "path": "GET /api/analytics/performance",
                "canonical": "GET /api/analytics/performance_summary",
                "status": "active"
            },
            {
                "path": "GET /api/orders",
                "canonical": "GET /api/orders/pending or /api/orders/history",
                "status": "active"
            },
            {
                "path": "GET /api/trades",
                "canonical": "GET /api/trades/recent",
                "status": "active"
            },
            {
                "path": "GET /api/ledger/summary",
                "canonical": "GET /api/ledger/balance",
                "status": "active"
            },
            {
                "path": "GET /api/limits",
                "canonical": "GET /api/limits/user or /api/limits/system",
                "status": "active"
            },
            {
                "path": "* /api/api-keys/*",
                "canonical": "* /api/keys/*",
                "status": "active"
            }
        ],
        "note": "These endpoints log warnings when used. Migrate to canonical endpoints.",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


# ============================================================================
# API KEYS COMPATIBILITY - /api/api-keys/* => /api/keys/*
# ============================================================================

@router.get("/api-keys/list")
async def compat_api_keys_list(user_id: str = Depends(get_current_user)):
    """
    COMPAT: GET /api/api-keys/list
    
    ⚠️ DEPRECATED: Use GET /api/keys/list instead
    """
    logger.warning(
        f"[COMPAT] /api/api-keys/list called by user {user_id} - "
        "migrate to /api/keys/list"
    )
    
    try:
        from routes.keys import list_user_keys
        return await list_user_keys(user_id=user_id)
    except Exception as e:
        logger.error(f"[COMPAT] API keys list error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api-keys/save")
async def compat_api_keys_save(
    data: dict,
    user_id: str = Depends(get_current_user)
):
    """
    COMPAT: POST /api/api-keys/save
    
    ⚠️ DEPRECATED: Use POST /api/keys/save instead
    """
    logger.warning(
        f"[COMPAT] /api/api-keys/save called by user {user_id} - "
        "migrate to /api/keys/save"
    )
    
    try:
        from routes.keys import save_key, APIKeySaveRequest
        request = APIKeySaveRequest(**data)
        return await save_key(data=request, user_id=user_id)
    except Exception as e:
        logger.error(f"[COMPAT] API keys save error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api-keys/test")
async def compat_api_keys_test(
    data: dict,
    user_id: str = Depends(get_current_user)
):
    """
    COMPAT: POST /api/api-keys/test
    
    ⚠️ DEPRECATED: Use POST /api/keys/test instead
    """
    logger.warning(
        f"[COMPAT] /api/api-keys/test called by user {user_id} - "
        "migrate to /api/keys/test"
    )
    
    try:
        from routes.keys import test_key, APIKeyTestRequest
        request = APIKeyTestRequest(**data)
        return await test_key(data=request, user_id=user_id)
    except Exception as e:
        logger.error(f"[COMPAT] API keys test error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/api-keys/{provider}")
async def compat_api_keys_delete(
    provider: str,
    user_id: str = Depends(get_current_user)
):
    """
    COMPAT: DELETE /api/api-keys/{provider}
    
    ⚠️ DEPRECATED: Use DELETE /api/keys/{provider} instead
    """
    logger.warning(
        f"[COMPAT] /api/api-keys/{provider} DELETE called by user {user_id} - "
        "migrate to /api/keys/{provider}"
    )
    
    try:
        from routes.keys import delete_key
        return await delete_key(provider=provider, user_id=user_id)
    except Exception as e:
        logger.error(f"[COMPAT] API keys delete error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
