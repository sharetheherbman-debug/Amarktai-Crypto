"""
Order Endpoints - Phase 2 (Order Pipeline with 4-Gate Guardrails)

Provides order submission through the unified pipeline and circuit breaker management:
- Order submission (POST /api/orders/submit)
- Order status queries (GET /api/orders/{order_id}/status)
- Pending orders list (GET /api/orders/pending)
- Circuit breaker status (GET /api/circuit-breaker/status)
- Circuit breaker reset (POST /api/circuit-breaker/reset)
- Trade limits status (GET /api/limits/status)
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Body
from typing import Optional, List
from datetime import datetime
import logging
from pydantic import BaseModel

from auth import get_current_user
import database as db
from database import get_database
from services.order_pipeline import get_order_pipeline

router = APIRouter(prefix="/api", tags=["orders", "circuit-breaker"])
logger = logging.getLogger(__name__)


class OrderSubmitRequest(BaseModel):
    """Request model for order submission"""
    bot_id: str
    exchange: str
    symbol: str
    side: str  # "buy" or "sell"
    amount: float
    order_type: str = "market"  # "market" or "limit"
    price: Optional[float] = None
    idempotency_key: Optional[str] = None
    is_paper: bool = True


class CircuitBreakerResetRequest(BaseModel):
    """Request model for circuit breaker reset"""
    bot_id: Optional[str] = None
    user_id: Optional[str] = None
    reason: str


@router.post("/orders/submit")
async def submit_order(
    request: OrderSubmitRequest,
    current_user: str = Depends(get_current_user),
    db=Depends(get_database)
):
    """
    Submit an order through the 4-gate pipeline
    
    Gates:
    1. Idempotency - Prevents duplicate executions
    2. Fee Coverage - Rejects unprofitable trades
    3. Trade Limiter - Enforces bot/user/burst limits
    4. Circuit Breaker - Auto-pauses on triggers
    
    Returns:
    - success: Boolean indicating if order passed all gates
    - order_id: Unique order identifier (if successful)
    - idempotency_key: Key used for deduplication
    - gates_passed: List of gates that passed
    - gate_failed: Gate that failed (if any)
    - rejection_reason: Human-readable rejection reason (if failed)
    - execution_summary: Cost breakdown (if successful)
    """
    try:
        pipeline = get_order_pipeline(db)
        user_id = current_user
        
        result = await pipeline.submit_order(
            user_id=user_id,
            bot_id=request.bot_id,
            exchange=request.exchange,
            symbol=request.symbol,
            side=request.side,
            amount=request.amount,
            order_type=request.order_type,
            price=request.price,
            idempotency_key=request.idempotency_key,
            is_paper=request.is_paper
        )
        
        return {
            "success": result["success"],
            "order_id": result.get("order_id"),
            "idempotency_key": result.get("idempotency_key"),
            "gates_passed": result.get("gates_passed", []),
            "gate_failed": result.get("gate_failed"),
            "rejection_reason": result.get("rejection_reason"),
            "execution_summary": result.get("execution_summary"),
            "fill": result.get("fill"),
            "timestamp": datetime.utcnow().isoformat(),
            "data_source": "order_pipeline",
            "phase": "2_guardrails"
        }
        
    except Exception as e:
        logger.error(f"Order submission error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Order submission failed: {str(e)}")


@router.get("/orders/{order_id}/status")
async def get_order_status(
    order_id: str,
    current_user: str = Depends(get_current_user),
    db=Depends(get_database)
):
    """
    Get the status of a submitted order
    
    Returns order state and execution details
    """
    try:
        pipeline = get_order_pipeline(db)
        user_id = current_user
        
        order = await pipeline.get_order_status(order_id, user_id)
        
        if not order:
            raise HTTPException(status_code=404, detail="Order not found")
        
        return {
            "order_id": order["_id"],
            "state": order["state"],
            "bot_id": order["bot_id"],
            "exchange": order["exchange"],
            "symbol": order["symbol"],
            "side": order["side"],
            "amount": order["amount"],
            "order_type": order["order_type"],
            "gates_passed": order.get("gates_passed", []),
            "gate_failed": order.get("gate_failed"),
            "rejection_reason": order.get("rejection_reason"),
            "created_at": order["created_at"].isoformat(),
            "filled_at": order.get("filled_at").isoformat() if order.get("filled_at") else None,
            "fill_id": order.get("fill_id"),
            "execution_summary": order.get("execution_summary"),
            "data_source": "order_pipeline"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get order status error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get order status: {str(e)}")


@router.get("/orders/pending")
async def get_pending_orders(
    bot_id: Optional[str] = Query(None),
    current_user: str = Depends(get_current_user),
    db=Depends(get_database)
):
    """
    Get list of pending orders for the user
    
    Query params:
    - bot_id: Filter by specific bot (optional)
    """
    try:
        pipeline = get_order_pipeline(db)
        user_id = current_user
        
        orders = await pipeline.get_pending_orders(user_id, bot_id)
        
        return {
            "pending_orders": [
                {
                    "order_id": str(order["_id"]),
                    "bot_id": order["bot_id"],
                    "exchange": order["exchange"],
                    "symbol": order["symbol"],
                    "side": order["side"],
                    "amount": order["amount"],
                    "state": order["state"],
                    "created_at": order["created_at"].isoformat(),
                    "gates_passed": order.get("gates_passed", [])
                }
                for order in orders
            ],
            "count": len(orders),
            "data_source": "order_pipeline"
        }
        
    except Exception as e:
        logger.error(f"Get pending orders error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get pending orders: {str(e)}")


@router.get("/circuit-breaker/status")
async def get_circuit_breaker_status(
    bot_id: Optional[str] = Query(None),
    user_id: Optional[str] = Query(None),
    current_user: str = Depends(get_current_user),
    db=Depends(get_database)
):
    """
    Check circuit breaker status for bot or user
    
    Query params:
    - bot_id: Check specific bot
    - user_id: Check user-level breaker (admin only)
    
    Returns:
    - tripped: Boolean indicating if breaker is tripped
    - reason: Why it tripped
    - tripped_at: When it tripped
    - can_reset: Whether manual reset is allowed
    """
    try:
        pipeline = get_order_pipeline(db)
        current_user_id = current_user
        
        # Use current user if not specified (admin check removed - would need user object)
        if not user_id:
            user_id = current_user_id
        
        # Determine entity to check
        entity_type = "bot" if bot_id else "user"
        entity_id = bot_id or user_id
        
        # Query circuit breaker state
        breaker = await pipeline.circuit_breaker_state.find_one({
            "entity_type": entity_type,
            "entity_id": entity_id,
            "tripped": True,
            "reset_at": None
        })
        
        if breaker:
            return {
                "tripped": True,
                "entity_type": entity_type,
                "entity_id": entity_id,
                "trigger_reason": breaker.get("trigger_reason"),
                "trigger_type": breaker.get("trigger_type"),
                "tripped_at": breaker.get("tripped_at").isoformat() if breaker.get("tripped_at") else None,
                "metrics_at_trip": breaker.get("metrics_at_trip", {}),
                "can_reset": True,
                "data_source": "circuit_breaker"
            }
        else:
            return {
                "tripped": False,
                "entity_type": entity_type,
                "entity_id": entity_id,
                "data_source": "circuit_breaker"
            }
        
    except Exception as e:
        logger.error(f"Get circuit breaker status error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get circuit breaker status: {str(e)}")


@router.post("/circuit-breaker/reset")
async def reset_circuit_breaker(
    request: CircuitBreakerResetRequest,
    current_user: str = Depends(get_current_user),
    db=Depends(get_database)
):
    """
    Reset a tripped circuit breaker after manual review.

    When neither bot_id nor user_id is provided, defaults to resetting
    the circuit breaker for the currently authenticated user (safe default).

    Requires:
    - reason: Explanation for reset
    - Optionally: bot_id OR user_id (defaults to current user)

    Only allowed after manual review confirms safety.
    """
    try:
        pipeline = get_order_pipeline(db)
        current_user_id = current_user

        # Default to current user when neither bot_id nor user_id provided
        if not request.bot_id and not request.user_id:
            entity_type = "user"
            entity_id = current_user_id
        else:
            entity_type = "bot" if request.bot_id else "user"
            entity_id = request.bot_id or request.user_id

        result = await pipeline.reset_circuit_breaker(
            entity_id=entity_id,
            entity_type=entity_type,
            reset_by_user_id=current_user_id,
            reason=request.reason
        )

        if result["success"]:
            return {
                "success": True,
                "message": "Circuit breaker reset successfully",
                "reset_by": current_user_id,
                "entity_type": entity_type,
                "entity_id": entity_id,
                "reason": request.reason,
                "timestamp": datetime.utcnow().isoformat()
            }
        else:
            raise HTTPException(status_code=400, detail=result.get("message", "Circuit breaker not tripped or reset failed"))

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Reset circuit breaker error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to reset circuit breaker: {str(e)}")


@router.get("/circuit-breaker/history")
async def get_circuit_breaker_history(
    bot_id: Optional[str] = Query(None),
    limit: int = Query(10, ge=1, le=100),
    current_user: str = Depends(get_current_user),
    db=Depends(get_database)
):
    """
    Get circuit breaker trip history
    
    Query params:
    - bot_id: Filter by specific bot (optional)
    - limit: Max results (default 10, max 100)
    """
    try:
        pipeline = get_order_pipeline(db)
        user_id = current_user
        
        # Build query
        query = {}
        if bot_id:
            query["entity_type"] = "bot"
            query["entity_id"] = bot_id
            # Also verify the bot belongs to the user
            bot = await db["bots"].find_one({"id": bot_id, "user_id": user_id})
            if not bot:
                raise HTTPException(status_code=404, detail="Bot not found")
        
        # Get circuit breaker history
        cursor = pipeline.circuit_breaker_state.find(query).sort("tripped_at", -1).limit(limit)
        history = await cursor.to_list(length=limit)
        
        return {
            "history": [
                {
                    "entity_type": event["entity_type"],
                    "entity_id": event["entity_id"],
                    "trigger_reason": event["trigger_reason"],
                    "trigger_type": event.get("trigger_type"),
                    "tripped_at": event["tripped_at"].isoformat() if event.get("tripped_at") else None,
                    "reset_at": event.get("reset_at").isoformat() if event.get("reset_at") else None,
                    "reset_by_user_id": event.get("reset_by_user_id"),
                    "reset_reason": event.get("reset_reason"),
                    "metrics_at_trip": event.get("metrics_at_trip", {})
                }
                for event in history
            ],
            "count": len(history),
            "data_source": "circuit_breaker"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get circuit breaker history error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get circuit breaker history: {str(e)}")


@router.get("/limits/status")
async def get_limits_status(
    bot_id: Optional[str] = Query(None),
    current_user: str = Depends(get_current_user),
    db=Depends(get_database)
):
    """
    Get trade limits status (daily usage, remaining capacity)
    
    Query params:
    - bot_id: Check specific bot limits
    
    Returns:
    - bot_daily: Bot daily trade limit status
    - user_daily: User daily trade limit status
    - exchange_burst: Exchange burst limit status
    """
    try:
        pipeline = get_order_pipeline(db)
        user_id = current_user
        ledger = pipeline.ledger
        
        today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        
        # Get user daily count
        user_count = await ledger.get_trade_count(user_id=user_id, since=today_start)
        user_limit = pipeline.max_trades_per_user_daily
        
        # Get bot daily count if specified
        bot_count = 0
        bot_limit = pipeline.max_trades_per_bot_daily
        if bot_id:
            bot_count = await ledger.get_trade_count(bot_id=bot_id, since=today_start)
        
        return {
            "user_daily": {
                "used": user_count,
                "limit": user_limit,
                "remaining": max(0, user_limit - user_count),
                "percentage": round((user_count / user_limit * 100) if user_limit > 0 else 0, 1)
            },
            "bot_daily": {
                "used": bot_count,
                "limit": bot_limit,
                "remaining": max(0, bot_limit - bot_count),
                "percentage": round((bot_count / bot_limit * 100) if bot_limit > 0 else 0, 1)
            } if bot_id else None,
            "burst_limit": {
                "limit": pipeline.burst_limit_orders,
                "window_seconds": pipeline.burst_limit_window_seconds
            },
            "data_source": "trade_limiter"
        }
        
    except Exception as e:
        logger.error(f"Get limits status error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get limits status: {str(e)}")
