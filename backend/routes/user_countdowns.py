"""
User Custom Countdowns API
Manages user-defined financial goals and countdown targets
"""

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime, timezone
import logging
import database as db
from auth import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/countdowns", tags=["countdowns"])


class CountdownCreate(BaseModel):
    """Model for creating a new countdown"""
    label: str = Field(..., min_length=1, max_length=50, description="Countdown label (e.g., 'BMW M3')")
    target_amount: float = Field(..., gt=0, description="Target amount in ZAR")


class CountdownUpdate(BaseModel):
    """Model for updating a countdown"""
    label: Optional[str] = Field(None, min_length=1, max_length=50)
    target_amount: Optional[float] = Field(None, gt=0)


class CountdownResponse(BaseModel):
    """Countdown response model"""
    id: str
    user_id: str
    label: str
    target_amount: float
    current_progress: float
    progress_pct: float
    remaining: float
    days_remaining: int
    created_at: str
    updated_at: str


@router.get("/", response_model=List[CountdownResponse])
async def get_user_countdowns(user_id: str = Depends(get_current_user)):
    """Get all countdowns for the current user"""
    try:
        countdowns = await db.user_countdowns_collection.find(
            {"user_id": user_id}
        ).to_list(100)
        
        # Calculate current progress for each countdown
        # Get canonical portfolio value: ZAR + USDT-in-ZAR (avoids undercounting)
        user = await db.users_collection.find_one({"id": user_id}, {"_id": 0})
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        current_capital = await _get_canonical_portfolio_zar(user_id, user)
        
        result = []
        for countdown in countdowns:
            target = countdown["target_amount"]
            progress = min(current_capital, target)
            progress_pct = (progress / target * 100) if target > 0 else 0
            remaining = max(0, target - current_capital)
            
            # Calculate days remaining based on daily ROI
            # Get average daily profit from recent trades
            daily_roi_pct = await calculate_daily_roi(user_id)
            
            if daily_roi_pct > 0 and remaining > 0:
                # Compound interest formula: target = current * (1 + daily_roi)^days
                # Solve for days: days = log(target/current) / log(1 + daily_roi)
                import math
                if current_capital > 0:
                    days_remaining = int(math.log(target / current_capital) / math.log(1 + daily_roi_pct / 100))
                    days_remaining = max(0, min(days_remaining, 9999))
                else:
                    days_remaining = 9999
            else:
                days_remaining = 9999
            
            result.append({
                "id": countdown.get("id", str(countdown.get("_id", ""))),
                "user_id": countdown["user_id"],
                "label": countdown["label"],
                "target_amount": target,
                "current_progress": progress,
                "progress_pct": progress_pct,
                "remaining": remaining,
                "days_remaining": days_remaining,
                "created_at": countdown.get("created_at", ""),
                "updated_at": countdown.get("updated_at", "")
            })
        
        return result
    except Exception as e:
        logger.error(f"Error fetching user countdowns: {e}")
        raise HTTPException(status_code=500, detail=str(e))


async def _get_canonical_portfolio_zar(user_id: str, user_doc=None) -> float:
    """Return canonical portfolio value in ZAR including USDT balances converted to ZAR.

    Priority:
    1. Paper wallet canonical equity (available + allocated, all currencies → ZAR)
    2. Fallback to user.total_capital (ZAR only — less accurate)

    This is the ONE source of truth for countdown / progress / equity displays.
    """
    try:
        from services.canonical import get_canonical_paper_wallet_equity
        equity = await get_canonical_paper_wallet_equity(user_id)
        total = float(equity.get("total_equity", 0) or 0)
        if total > 0:
            return total
    except Exception as _e:
        logger.warning("canonical equity fetch failed for %s: %s", user_id[:8], _e)
    # Fallback: user.total_capital (ZAR only)
    if user_doc is None:
        user_doc = await db.users_collection.find_one({"id": user_id}, {"_id": 0})
    return float((user_doc or {}).get("total_capital", 0.0) or 0.0)


async def calculate_daily_roi(user_id: str) -> float:
    """Calculate average daily ROI from recent trades.

    All profit values are normalised to ZAR before summing so that bots
    trading in USDT (Binance, KuCoin, etc.) are not mixed raw with ZAR
    (Luno) values.  Uses realized_pnl_zar when available (pre-converted by
    enrich_trade_pnl_fields), otherwise falls back to live FX conversion.
    """
    try:
        from datetime import timedelta
        from services.fx_normalizer import get_fx_rate as _gfr, get_quote_currency as _gqc

        seven_days_ago = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()

        trades = await db.trades_collection.find(
            {"user_id": user_id, "created_at": {"$gte": seven_days_ago}},
            {
                "_id": 0,
                "net_pnl": 1,
                "profit_loss": 1,
                "fees": 1,
                "realized_pnl_zar": 1,
                "fee_display_zar": 1,
                "quote_currency": 1,
                "exchange": 1,
            }
        ).to_list(1000)

        if not trades:
            return 0.0

        # Sum all profits in ZAR — use realized_pnl_zar when available,
        # otherwise convert via canonical FX rate for the trade's currency.
        total_profit_zar = 0.0
        for trade in trades:
            if trade.get("realized_pnl_zar") is not None:
                # Pre-converted canonical field — most accurate
                total_profit_zar += float(trade["realized_pnl_zar"])
            else:
                # Legacy: convert raw pnl using trade's quote currency
                net_pnl = trade.get("net_pnl")
                pnl_raw = net_pnl if net_pnl is not None else trade.get("profit_loss", 0)
                fees_raw = float(trade.get("fees", 0) or 0)
                qc = trade.get("quote_currency") or _gqc(trade.get("exchange", ""), "")
                rate, _ = _gfr(qc, "ZAR")
                total_profit_zar += (float(pnl_raw or 0) - fees_raw) * rate

        # Use canonical portfolio value (ZAR + USDT-in-ZAR) as the current capital base
        user = await db.users_collection.find_one({"id": user_id}, {"_id": 0})
        current_capital = await _get_canonical_portfolio_zar(user_id, user)
        starting_capital = current_capital - total_profit_zar

        if starting_capital <= 0:
            return 0.0

        total_roi = (total_profit_zar / starting_capital) * 100
        daily_roi = total_roi / 7

        return max(0, daily_roi)
    except Exception as e:
        logger.warning(f"Error calculating daily ROI: {e}")
        return 0.0


@router.post("/", response_model=CountdownResponse)
async def create_countdown(countdown: CountdownCreate, user_id: str = Depends(get_current_user)):
    """Create a new custom countdown"""
    try:
        # Check if user already has 4 custom countdowns (limit)
        existing = await db.user_countdowns_collection.count_documents({"user_id": user_id})
        if existing >= 4:
            raise HTTPException(
                status_code=400,
                detail="Maximum of 4 custom countdowns allowed per user"
            )
        
        # Generate ID
        import uuid
        countdown_id = str(uuid.uuid4())
        
        now = datetime.now(timezone.utc).isoformat()
        
        countdown_doc = {
            "id": countdown_id,
            "user_id": user_id,
            "label": countdown.label,
            "target_amount": countdown.target_amount,
            "created_at": now,
            "updated_at": now
        }
        
        await db.user_countdowns_collection.insert_one(countdown_doc)
        
        # Get current progress using canonical portfolio value (ZAR + USDT-in-ZAR)
        user = await db.users_collection.find_one({"id": user_id}, {"_id": 0})
        current_capital = await _get_canonical_portfolio_zar(user_id, user)
        
        target = countdown.target_amount
        progress = min(current_capital, target)
        progress_pct = (progress / target * 100) if target > 0 else 0
        remaining = max(0, target - current_capital)
        
        daily_roi_pct = await calculate_daily_roi(user_id)
        if daily_roi_pct > 0 and remaining > 0 and current_capital > 0:
            import math
            days_remaining = int(math.log(target / current_capital) / math.log(1 + daily_roi_pct / 100))
            days_remaining = max(0, min(days_remaining, 9999))
        else:
            days_remaining = 9999
        
        return {
            "id": countdown_id,
            "user_id": user_id,
            "label": countdown.label,
            "target_amount": countdown.target_amount,
            "current_progress": progress,
            "progress_pct": progress_pct,
            "remaining": remaining,
            "days_remaining": days_remaining,
            "created_at": now,
            "updated_at": now
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating countdown: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{countdown_id}", response_model=CountdownResponse)
async def update_countdown(
    countdown_id: str,
    countdown: CountdownUpdate,
    user_id: str = Depends(get_current_user)
):
    """Update a countdown"""
    try:
        existing = await db.user_countdowns_collection.find_one({
            "id": countdown_id,
            "user_id": user_id
        })
        
        if not existing:
            raise HTTPException(status_code=404, detail="Countdown not found")
        
        update_data = {}
        if countdown.label is not None:
            update_data["label"] = countdown.label
        if countdown.target_amount is not None:
            update_data["target_amount"] = countdown.target_amount
        
        if update_data:
            update_data["updated_at"] = datetime.now(timezone.utc).isoformat()
            await db.user_countdowns_collection.update_one(
                {"id": countdown_id, "user_id": user_id},
                {"$set": update_data}
            )
        
        # Get updated countdown
        updated = await db.user_countdowns_collection.find_one({
            "id": countdown_id,
            "user_id": user_id
        })
        
        # Calculate progress using canonical portfolio value (ZAR + USDT-in-ZAR)
        user = await db.users_collection.find_one({"id": user_id}, {"_id": 0})
        current_capital = await _get_canonical_portfolio_zar(user_id, user)
        
        target = updated["target_amount"]
        progress = min(current_capital, target)
        progress_pct = (progress / target * 100) if target > 0 else 0
        remaining = max(0, target - current_capital)
        
        daily_roi_pct = await calculate_daily_roi(user_id)
        if daily_roi_pct > 0 and remaining > 0 and current_capital > 0:
            import math
            days_remaining = int(math.log(target / current_capital) / math.log(1 + daily_roi_pct / 100))
            days_remaining = max(0, min(days_remaining, 9999))
        else:
            days_remaining = 9999
        
        return {
            "id": updated["id"],
            "user_id": updated["user_id"],
            "label": updated["label"],
            "target_amount": target,
            "current_progress": progress,
            "progress_pct": progress_pct,
            "remaining": remaining,
            "days_remaining": days_remaining,
            "created_at": updated.get("created_at", ""),
            "updated_at": updated.get("updated_at", "")
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating countdown: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{countdown_id}")
async def delete_countdown(countdown_id: str, user_id: str = Depends(get_current_user)):
    """Delete a countdown"""
    try:
        result = await db.user_countdowns_collection.delete_one({
            "id": countdown_id,
            "user_id": user_id
        })
        
        if result.deleted_count == 0:
            raise HTTPException(status_code=404, detail="Countdown not found")
        
        return {"message": "Countdown deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting countdown: {e}")
        raise HTTPException(status_code=500, detail=str(e))
