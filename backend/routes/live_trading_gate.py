"""
Live Trading Gate - 7-Day Paper Trading Learning Period
Enforces paper-first trading and evaluates readiness for live trading
"""

from fastapi import APIRouter, HTTPException, Depends
from datetime import datetime, timezone, timedelta
from typing import Dict, List
import logging

from auth import get_current_user
import database as db
from config import PAPER_TRAINING_DAYS, MIN_WIN_RATE, MIN_PROFIT_PERCENT, MIN_TRADES_FOR_PROMOTION

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/system", tags=["Live Trading Gate"])


async def check_user_live_eligibility(user_id: str) -> Dict:
    """Check if user meets criteria for live trading
    
    Returns:
        Dict with eligible status and reasons
    """
    reasons = []
    warnings = []
    
    # Check if paper learning period completed
    user = await db.users_collection.find_one({"id": user_id}, {"_id": 0})
    if not user:
        return {"eligible": False, "reasons": ["User not found"]}
    
    paper_start = user.get('paper_learning_start_ts')
    if not paper_start:
        # No paper trading started yet
        return {
            "eligible": False,
            "reasons": ["Paper trading learning period not started"],
            "action": "Start paper trading to begin 7-day learning period"
        }
    
    # Parse timestamp
    if isinstance(paper_start, str):
        paper_start_dt = datetime.fromisoformat(paper_start.replace('Z', '+00:00'))
    else:
        paper_start_dt = paper_start
    
    days_elapsed = (datetime.now(timezone.utc) - paper_start_dt).days
    required_days = user.get('paper_learning_days_required', PAPER_TRAINING_DAYS)
    
    if days_elapsed < required_days:
        reasons.append(f"Paper trading period incomplete: {days_elapsed}/{required_days} days")
    
    # Check profitability and performance
    user_bots = await db.bots_collection.find(
        {"user_id": user_id, "trading_mode": "paper"},
        {"_id": 0}
    ).to_list(1000)
    
    if not user_bots:
        reasons.append("No paper trading bots found")
        return {"eligible": False, "reasons": reasons}
    
    bot_ids = [bot['id'] for bot in user_bots]

    # ── BLOCKER 9 FIX: read trade counts from trades_collection, not bot.trades_count ──
    # bot.trades_count is a denormalised counter that can become stale after
    # restores/migrations.  trades_collection is the canonical source.
    total_trades = await db.trades_collection.count_documents({
        "bot_id": {"$in": bot_ids},
        "user_id": user_id,
    })

    # Win/loss rate from trades_collection (exclude open positions)
    winning_trades = await db.trades_collection.count_documents({
        "bot_id": {"$in": bot_ids},
        "user_id": user_id,
        "profit_loss": {"$gt": 0},
        "status": {"$ne": "open"},
    })
    losing_trades = await db.trades_collection.count_documents({
        "bot_id": {"$in": bot_ids},
        "user_id": user_id,
        "profit_loss": {"$lt": 0},
        "status": {"$ne": "open"},
    })
    win_rate = (
        winning_trades / (winning_trades + losing_trades)
        if (winning_trades + losing_trades) > 0
        else 0
    )

    # Capital / profit aggregates still come from bot documents
    # (trades_collection P&L aggregation would be more accurate but these fields
    #  are updated synchronously with each close and are reliable enough here)
    total_profit = sum(bot.get('total_profit', 0) for bot in user_bots)
    total_capital = sum(bot.get('current_capital', 0) for bot in user_bots)
    initial_capital = sum(bot.get('initial_capital', 0) for bot in user_bots)
    
    if total_trades < MIN_TRADES_FOR_PROMOTION:
        reasons.append(f"Insufficient trades: {total_trades}/{MIN_TRADES_FOR_PROMOTION} minimum")
    
    # win_rate already computed from trades_collection above
    if win_rate < MIN_WIN_RATE:
        reasons.append(f"Win rate too low: {win_rate:.1%} (minimum {MIN_WIN_RATE:.1%})")
    
    # Check profitability
    profit_pct = (total_profit / initial_capital * 100) if initial_capital > 0 else 0
    
    if profit_pct < MIN_PROFIT_PERCENT * 100:
        reasons.append(f"Profit percentage too low: {profit_pct:.2f}% (minimum {MIN_PROFIT_PERCENT * 100:.1f}%)")
    elif profit_pct < 0:
        reasons.append(f"Overall loss: {profit_pct:.2f}%")
    
    # Check for emergency stop
    modes = await db.system_modes_collection.find_one({"user_id": user_id}, {"_id": 0})
    if modes and modes.get('emergencyStop', False):
        reasons.append("Emergency stop is active")
    
    # Check for risk violations
    max_drawdown = max((bot.get('max_drawdown', 0) for bot in user_bots), default=0)
    if max_drawdown > 0.25:  # 25% max drawdown threshold
        warnings.append(f"High max drawdown detected: {max_drawdown:.1%}")
    
    # Budget compliance check
    from engines.trade_budget_manager import trade_budget_manager
    
    violations = 0
    for bot in user_bots:
        can_trade, reason = await trade_budget_manager.can_execute_trade(bot['id'], bot.get('exchange', 'binance'))
        if not can_trade and 'budget' in reason.lower():
            violations += 1
    
    if violations > 0:
        warnings.append(f"{violations} bot(s) have budget compliance issues")
    
    eligible = len(reasons) == 0
    
    return {
        "eligible": eligible,
        "reasons": reasons,
        "warnings": warnings,
        "statistics": {
            "days_elapsed": days_elapsed,
            "required_days": required_days,
            "total_trades": total_trades,
            "win_rate": round(win_rate * 100, 2),
            "profit_pct": round(profit_pct, 2),
            "total_bots": len(user_bots),
            "max_drawdown": round(max_drawdown * 100, 2)
        }
    }


@router.post("/request-live")
async def request_live_trading(user_id: str = Depends(get_current_user)):
    """Request live trading activation (admin-level check)
    
    Evaluates user's paper trading performance and determines eligibility
    for live trading based on:
    - 7-day paper trading period completed
    - Minimum trades executed
    - Acceptable win rate
    - Profitable or acceptable drawdown
    - No risk violations or emergency stops
    """
    try:
        # Check eligibility
        eligibility = await check_user_live_eligibility(user_id)
        
        if eligibility['eligible']:
            # Update user's live_allowed flag
            await db.users_collection.update_one(
                {"id": user_id},
                {
                    "$set": {
                        "live_allowed": True,
                        "live_approved_at": datetime.now(timezone.utc).isoformat()
                    }
                }
            )
            
            logger.info(f"✅ Live trading approved for user {user_id[:8]}")
            
            return {
                "success": True,
                "message": "Live trading approved! You can now switch bots to live mode.",
                "approved_at": datetime.now(timezone.utc).isoformat(),
                "statistics": eligibility.get('statistics', {}),
                "warnings": eligibility.get('warnings', [])
            }
        else:
            logger.info(f"❌ Live trading request denied for user {user_id[:8]}: {eligibility['reasons']}")
            
            return {
                "success": False,
                "message": "Live trading request denied. Please complete requirements.",
                "reasons": eligibility['reasons'],
                "warnings": eligibility.get('warnings', []),
                "statistics": eligibility.get('statistics', {}),
                "action": eligibility.get('action')
            }
        
    except Exception as e:
        logger.error(f"Request live trading error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/live-eligibility")
async def get_live_eligibility(user_id: str = Depends(get_current_user)):
    """Get current live trading eligibility status
    
    Returns detailed breakdown of requirements and current status
    """
    try:
        eligibility = await check_user_live_eligibility(user_id)
        
        # Check if already approved
        user = await db.users_collection.find_one({"id": user_id}, {"_id": 0})
        live_allowed = user.get('live_allowed', False) if user else False
        
        return {
            "live_allowed": live_allowed,
            "eligible": eligibility['eligible'],
            "requirements": {
                "paper_training_days": PAPER_TRAINING_DAYS,
                "min_trades": MIN_TRADES_FOR_PROMOTION,
                "min_win_rate_pct": MIN_WIN_RATE * 100,
                "min_profit_pct": MIN_PROFIT_PERCENT * 100
            },
            "current_status": eligibility.get('statistics', {}),
            "reasons": eligibility.get('reasons', []),
            "warnings": eligibility.get('warnings', []),
            "approved_at": user.get('live_approved_at') if user else None,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as e:
        logger.error(f"Get live eligibility error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/start-paper-learning")
async def start_paper_learning(user_id: str = Depends(get_current_user)):
    """Start the 7-day paper trading learning period
    
    Records the start timestamp for tracking learning period completion
    """
    try:
        user = await db.users_collection.find_one({"id": user_id}, {"_id": 0})
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        # Check if already started
        if user.get('paper_learning_start_ts'):
            return {
                "success": False,
                "message": "Paper learning period already started",
                "started_at": user.get('paper_learning_start_ts')
            }
        
        # Start learning period
        start_ts = datetime.now(timezone.utc).isoformat()
        
        await db.users_collection.update_one(
            {"id": user_id},
            {
                "$set": {
                    "paper_learning_start_ts": start_ts,
                    "paper_learning_days_required": PAPER_TRAINING_DAYS
                }
            }
        )
        
        logger.info(f"✅ Paper learning period started for user {user_id[:8]}")
        
        return {
            "success": True,
            "message": f"{PAPER_TRAINING_DAYS}-day paper trading learning period started",
            "started_at": start_ts,
            "required_days": PAPER_TRAINING_DAYS,
            "completion_date": (datetime.now(timezone.utc) + timedelta(days=PAPER_TRAINING_DAYS)).isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Start paper learning error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
