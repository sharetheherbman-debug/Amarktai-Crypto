"""
Treasury & Compounding System Endpoints
Manages capital allocation, reinvestment, and bot funding
"""

from fastapi import APIRouter, HTTPException, Depends, Body
from datetime import datetime, timezone
from typing import Dict, Optional
import logging

from auth import get_current_user
import database as db
import config

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/treasury", tags=["Treasury"])


@router.get("/status")
async def get_treasury_status(user_id: str = Depends(get_current_user)):
    """
    Get treasury status
    
    Rules:
    - BOT_MAX_CAPITAL_ZAR cap per bot (default 10000)
    - Excess swept to treasury bucket
    - Daily reinvest to top 5 performers
    
    Returns:
        - Treasury balance
        - Available for reinvestment
        - Reserved for bots
        - Top performers
        - Reinvestment history
    """
    try:
        # Get all user's bots
        bots = await db.bots_collection.find(
            {"user_id": user_id},
            {"_id": 0, "id": 1, "name": 1, "current_capital": 1, "total_profit": 1, "status": 1}
        ).to_list(100)
        
        # Calculate treasury
        BOT_MAX_CAPITAL = getattr(config, 'BOT_MAX_CAPITAL_ZAR', 10000)
        
        total_capital = 0
        excess_capital = 0
        reserved_capital = 0
        
        for bot in bots:
            capital = bot.get("current_capital", 0)
            total_capital += capital
            
            if capital > BOT_MAX_CAPITAL:
                excess = capital - BOT_MAX_CAPITAL
                excess_capital += excess
                reserved_capital += BOT_MAX_CAPITAL
            else:
                reserved_capital += capital
        
        # Get treasury bucket
        treasury_doc = await db.db["treasury"].find_one({"user_id": user_id})
        treasury_balance = treasury_doc.get("balance", 0) if treasury_doc else 0
        
        # Add excess capital to treasury balance
        total_treasury = treasury_balance + excess_capital
        
        # Get top 5 performers
        top_performers = sorted(
            [b for b in bots if b.get("status") == "active"],
            key=lambda x: x.get("total_profit", 0),
            reverse=True
        )[:5]
        
        # Calculate available for reinvestment (treasury - already reserved)
        available_for_reinvestment = total_treasury
        
        # Get recent reinvestments
        recent_reinvestments = await db.db["treasury_reinvestments"].find(
            {"user_id": user_id},
            {"_id": 0}
        ).sort("timestamp", -1).limit(10).to_list(10)
        
        # Get last reinvestment date
        last_reinvestment = recent_reinvestments[0].get("timestamp") if recent_reinvestments else None
        
        return {
            "success": True,
            "treasury": {
                "total_balance": round(total_treasury, 2),
                "available_for_reinvestment": round(available_for_reinvestment, 2),
                "reserved_for_bots": round(reserved_capital, 2),
                "excess_capital_to_sweep": round(excess_capital, 2)
            },
            "limits": {
                "bot_max_capital_zar": BOT_MAX_CAPITAL
            },
            "top_performers": [
                {
                    "id": bot.get("id"),
                    "name": bot.get("name"),
                    "current_capital": round(bot.get("current_capital", 0), 2),
                    "total_profit": round(bot.get("total_profit", 0), 2),
                    "can_receive_more": bot.get("current_capital", 0) < BOT_MAX_CAPITAL
                }
                for bot in top_performers
            ],
            "last_reinvestment": last_reinvestment,
            "recent_reinvestments": recent_reinvestments,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as e:
        logger.error(f"Treasury status error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/rebalance")
async def rebalance_treasury(
    payload: Dict = Body(...),
    user_id: str = Depends(get_current_user)
):
    """
    Rebalance treasury - reinvest to top performers
    
    Body:
        dry_run: bool - If true, only simulate without executing
    
    Returns:
        Rebalancing plan and execution results
    """
    try:
        dry_run = payload.get("dry_run", False)
        
        # Get treasury status
        status_response = await get_treasury_status(user_id)
        treasury_data = status_response["treasury"]
        top_performers = status_response["top_performers"]
        
        available = treasury_data["available_for_reinvestment"]
        BOT_MAX_CAPITAL = status_response["limits"]["bot_max_capital_zar"]
        
        if available <= 0:
            return {
                "success": False,
                "message": "No funds available for reinvestment",
                "available": available
            }
        
        # Calculate allocation to top 5 performers
        allocations = []
        remaining = available
        
        for bot in top_performers:
            if remaining <= 0:
                break
            
            current_capital = bot["current_capital"]
            max_additional = BOT_MAX_CAPITAL - current_capital
            
            if max_additional > 0:
                # Allocate up to max, or remaining amount, whichever is smaller
                allocation = min(max_additional, remaining)
                allocations.append({
                    "bot_id": bot["id"],
                    "bot_name": bot["name"],
                    "current_capital": current_capital,
                    "allocation": round(allocation, 2),
                    "new_capital": round(current_capital + allocation, 2)
                })
                remaining -= allocation
        
        total_allocated = sum(a["allocation"] for a in allocations)
        
        # Execute if not dry run
        execution_results = []
        if not dry_run and allocations:
            for allocation in allocations:
                try:
                    # Update bot capital
                    result = await db.bots_collection.update_one(
                        {"id": allocation["bot_id"], "user_id": user_id},
                        {
                            "$inc": {"current_capital": allocation["allocation"]},
                            "$set": {"updated_at": datetime.now(timezone.utc).isoformat()}
                        }
                    )
                    
                    execution_results.append({
                        "bot_id": allocation["bot_id"],
                        "success": result.modified_count > 0,
                        "amount": allocation["allocation"]
                    })
                    
                except Exception as e:
                    logger.error(f"Failed to allocate to bot {allocation['bot_id']}: {e}")
                    execution_results.append({
                        "bot_id": allocation["bot_id"],
                        "success": False,
                        "error": str(e)
                    })
            
            # Record reinvestment
            await db.db["treasury_reinvestments"].insert_one({
                "user_id": user_id,
                "total_allocated": total_allocated,
                "allocations": allocations,
                "execution_results": execution_results,
                "timestamp": datetime.now(timezone.utc).isoformat()
            })
            
            # Update treasury balance
            await db.db["treasury"].update_one(
                {"user_id": user_id},
                {
                    "$inc": {"balance": -total_allocated},
                    "$set": {"updated_at": datetime.now(timezone.utc).isoformat()}
                },
                upsert=True
            )
        
        return {
            "success": True,
            "dry_run": dry_run,
            "plan": {
                "available_for_reinvestment": round(available, 2),
                "total_allocated": round(total_allocated, 2),
                "remaining_in_treasury": round(available - total_allocated, 2),
                "allocations": allocations
            },
            "execution": execution_results if not dry_run else None,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as e:
        logger.error(f"Treasury rebalance error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sweep")
async def sweep_excess_capital(
    payload: Dict = Body(...),
    user_id: str = Depends(get_current_user)
):
    """
    Sweep excess capital from bots to treasury
    
    Removes capital above BOT_MAX_CAPITAL_ZAR from each bot
    and moves it to treasury bucket
    
    Body:
        dry_run: bool - If true, only simulate without executing
    
    Returns:
        Sweep plan and execution results
    """
    try:
        dry_run = payload.get("dry_run", False)
        
        BOT_MAX_CAPITAL = getattr(config, 'BOT_MAX_CAPITAL_ZAR', 10000)
        
        # Get bots with excess capital
        bots = await db.bots_collection.find({
            "user_id": user_id,
            "current_capital": {"$gt": BOT_MAX_CAPITAL}
        }, {"_id": 0, "id": 1, "name": 1, "current_capital": 1}).to_list(100)
        
        if not bots:
            return {
                "success": True,
                "message": "No bots with excess capital",
                "swept_amount": 0
            }
        
        # Calculate sweep amounts
        sweeps = []
        total_swept = 0
        
        for bot in bots:
            excess = bot["current_capital"] - BOT_MAX_CAPITAL
            sweeps.append({
                "bot_id": bot["id"],
                "bot_name": bot["name"],
                "current_capital": bot["current_capital"],
                "excess": round(excess, 2),
                "new_capital": BOT_MAX_CAPITAL
            })
            total_swept += excess
        
        # Execute if not dry run
        execution_results = []
        if not dry_run:
            for sweep in sweeps:
                try:
                    # Update bot capital
                    result = await db.bots_collection.update_one(
                        {"id": sweep["bot_id"], "user_id": user_id},
                        {
                            "$set": {
                                "current_capital": BOT_MAX_CAPITAL,
                                "updated_at": datetime.now(timezone.utc).isoformat()
                            }
                        }
                    )
                    
                    execution_results.append({
                        "bot_id": sweep["bot_id"],
                        "success": result.modified_count > 0,
                        "swept_amount": sweep["excess"]
                    })
                    
                except Exception as e:
                    logger.error(f"Failed to sweep from bot {sweep['bot_id']}: {e}")
                    execution_results.append({
                        "bot_id": sweep["bot_id"],
                        "success": False,
                        "error": str(e)
                    })
            
            # Add to treasury
            await db.db["treasury"].update_one(
                {"user_id": user_id},
                {
                    "$inc": {"balance": total_swept},
                    "$set": {"updated_at": datetime.now(timezone.utc).isoformat()}
                },
                upsert=True
            )
            
            # Record sweep
            await db.db["treasury_sweeps"].insert_one({
                "user_id": user_id,
                "total_swept": total_swept,
                "sweeps": sweeps,
                "execution_results": execution_results,
                "timestamp": datetime.now(timezone.utc).isoformat()
            })
        
        return {
            "success": True,
            "dry_run": dry_run,
            "total_swept": round(total_swept, 2),
            "bots_affected": len(sweeps),
            "sweeps": sweeps,
            "execution": execution_results if not dry_run else None,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as e:
        logger.error(f"Treasury sweep error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
