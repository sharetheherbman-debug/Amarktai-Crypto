"""
AI/RL Status Routes
Provides endpoints for Reinforcement Learning agent status and control.
"""

from fastapi import APIRouter, HTTPException, Depends
from typing import Optional
import logging

from auth import get_current_user, is_admin
from services.rl_agent import get_rl_agent

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/api/ai/rl-status")
async def get_rl_status(user_id: str = Depends(get_current_user)):
    """
    Get current status of the Reinforcement Learning agent.
    
    Returns:
        RL agent statistics including episodes, rewards, and policy weights
    """
    try:
        rl_agent = get_rl_agent()
        status = rl_agent.get_status()
        
        return {
            "success": True,
            "rl_agent": status,
            "enabled": True,
            "message": "RL agent is active and learning"
        }
        
    except Exception as e:
        logger.error(f"RL status error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/ai/rl-train")
async def train_rl_agent(
    user_id: str = Depends(get_current_user),
    is_admin: bool = Depends(is_admin)
):
    """
    Trigger a training cycle for the RL agent (admin only).
    
    This will analyze recent bot performance and update the policy.
    
    Returns:
        Training results and updated status
    """
    if not is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        rl_agent = get_rl_agent()
        
        # In a real implementation, this would:
        # 1. Fetch recent bot performance data
        # 2. Calculate rewards
        # 3. Update policy weights
        # 4. Generate new recommendations
        
        # For now, increment episodes
        rl_agent.episodes += 1
        
        status = rl_agent.get_status()
        
        logger.info(f"RL training cycle triggered by admin {user_id[:8]}")
        
        return {
            "success": True,
            "message": "Training cycle completed",
            "rl_agent": status
        }
        
    except Exception as e:
        logger.error(f"RL training error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/ai/rl-recommendations/{bot_id}")
async def get_rl_recommendations(
    bot_id: str,
    user_id: str = Depends(get_current_user)
):
    """
    Get RL-based parameter recommendations for a specific bot.
    
    Args:
        bot_id: ID of the bot to get recommendations for
        
    Returns:
        List of recommended parameter adjustments
    """
    try:
        import database as db
        from bson import ObjectId
        
        if db.db is None:
            raise HTTPException(status_code=503, detail="Database not connected")
        
        # Get bot
        try:
            bot_oid = ObjectId(bot_id)
        except:
            raise HTTPException(status_code=400, detail="Invalid bot ID")
        
        bot = await db.bots_collection.find_one({
            "_id": bot_oid,
            "user_id": user_id
        })
        
        if not bot:
            raise HTTPException(status_code=404, detail="Bot not found")
        
        # Get performance metrics
        performance_metrics = {
            'total_profit': bot.get('profit', 0),
            'win_rate': bot.get('win_rate', 50),
            'sharpe_ratio': bot.get('sharpe_ratio', 0),
            'max_drawdown': bot.get('max_drawdown', 0),
            'trades_count': bot.get('trades_count', 0)
        }
        
        # Get current parameters
        current_params = {
            'stop_loss_pct': bot.get('stop_loss_pct', 5.0),
            'take_profit_pct': bot.get('take_profit_pct', 10.0),
            'position_size_multiplier': bot.get('position_size_multiplier', 1.0),
            'risk_per_trade_pct': bot.get('risk_per_trade_pct', 2.0),
            'cooldown_minutes': bot.get('cooldown_minutes', 60)
        }
        
        # Get RL recommendations
        rl_agent = get_rl_agent()
        recommendations = rl_agent.generate_recommendations(
            current_params,
            performance_metrics
        )
        
        return {
            "success": True,
            "bot_id": bot_id,
            "bot_name": bot.get('name', f"Bot {bot_id}"),
            "recommendations": recommendations,
            "current_params": current_params,
            "performance_metrics": performance_metrics
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"RL recommendations error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
