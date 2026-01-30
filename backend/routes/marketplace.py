"""
Strategy Marketplace & Social Sharing
Share and discover trading strategies

Features:
- Publish strategies to marketplace
- Browse and search strategies
- Rate and review strategies
- Leaderboards
- Clone strategies
"""

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional, Dict, List
import logging
from datetime import datetime, timezone

from auth import get_current_user
import database as db

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/marketplace", tags=["Strategy Marketplace"])


class StrategyPublish(BaseModel):
    name: str
    description: str
    strategy_dna: Dict
    tags: List[str] = []
    public: bool = True


class StrategyRating(BaseModel):
    strategy_id: str
    rating: int  # 1-5 stars
    review: Optional[str] = None


@router.post("/strategies/publish")
async def publish_strategy(
    strategy: StrategyPublish,
    user_id: str = Depends(get_current_user)
):
    """
    Publish a trading strategy to the marketplace
    """
    try:
        logger.info(f"Publishing strategy: {strategy.name} by user {user_id}")
        
        strategy_record = {
            "id": f"strategy_{datetime.now(timezone.utc).timestamp()}",
            "user_id": user_id,
            "name": strategy.name,
            "description": strategy.description,
            "strategy_dna": strategy.strategy_dna,
            "tags": strategy.tags,
            "public": strategy.public,
            "views": 0,
            "clones": 0,
            "rating": 0.0,
            "rating_count": 0,
            "published_at": datetime.now(timezone.utc).isoformat()
        }
        
        await db.db['marketplace_strategies'].insert_one(strategy_record)
        
        return {
            "success": True,
            "message": "Strategy published successfully",
            "strategy_id": strategy_record['id']
        }
        
    except Exception as e:
        logger.error(f"Publish strategy error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/strategies")
async def browse_strategies(
    limit: int = 20,
    skip: int = 0,
    tags: Optional[str] = None,
    sort_by: str = "rating"  # rating, views, clones, published_at
):
    """
    Browse marketplace strategies
    
    Optional filtering by tags and sorting
    """
    try:
        query = {"public": True}
        if tags:
            tag_list = [t.strip() for t in tags.split(',')]
            query["tags"] = {"$in": tag_list}
        
        # Map sort_by to MongoDB field
        sort_field = sort_by if sort_by != "published_at" else "published_at"
        sort_order = -1  # Descending
        
        strategies = await db.db['marketplace_strategies'].find(
            query,
            {"_id": 0, "strategy_dna": 0}  # Exclude DNA for listing
        ).sort(sort_field, sort_order).skip(skip).limit(limit).to_list(limit)
        
        return {
            "success": True,
            "strategies": strategies,
            "count": len(strategies)
        }
        
    except Exception as e:
        logger.error(f"Browse strategies error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/strategies/{strategy_id}")
async def get_strategy(strategy_id: str):
    """
    Get full details of a strategy including DNA
    """
    try:
        strategy = await db.db['marketplace_strategies'].find_one(
            {"id": strategy_id, "public": True},
            {"_id": 0}
        )
        
        if not strategy:
            raise HTTPException(status_code=404, detail="Strategy not found")
        
        # Increment view count
        await db.db['marketplace_strategies'].update_one(
            {"id": strategy_id},
            {"$inc": {"views": 1}}
        )
        
        return {
            "success": True,
            "strategy": strategy
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get strategy error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/strategies/{strategy_id}/clone")
async def clone_strategy(
    strategy_id: str,
    user_id: str = Depends(get_current_user)
):
    """
    Clone a strategy from marketplace to user's account
    
    Creates a new bot using the strategy DNA from the marketplace
    """
    try:
        from uuid import uuid4
        from realtime_events import rt_events
        
        # Get strategy
        strategy = await db.db['marketplace_strategies'].find_one(
            {"id": strategy_id, "public": True}
        )
        
        if not strategy:
            raise HTTPException(status_code=404, detail="Strategy not found")
        
        # Extract strategy DNA
        strategy_dna = strategy.get('strategy_dna', {})
        strategy_name = strategy.get('name', 'Cloned Strategy')
        
        # Create bot with cloned strategy DNA
        bot_id = str(uuid4())
        bot_data = {
            "id": bot_id,
            "user_id": user_id,
            "name": f"{strategy_name} (Clone)",
            "exchange": strategy_dna.get('exchange', 'luno'),
            "risk_mode": strategy_dna.get('risk_mode', 'balanced'),
            "trading_mode": "paper",  # Always start cloned strategies in paper mode
            "status": "active",
            "initial_capital": strategy_dna.get('initial_capital', 1000),
            "current_capital": strategy_dna.get('initial_capital', 1000),
            "total_profit": 0,
            "win_rate": 0,
            "trades_count": 0,
            "max_drawdown": 0,
            "stop_loss_percent": strategy_dna.get('stop_loss_percent', 15.0),
            "trailing_stop_percent": strategy_dna.get('trailing_stop_percent'),
            "take_profit_percent": strategy_dna.get('take_profit_percent'),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "paper_start_date": datetime.now(timezone.utc).isoformat(),
            "promoted_to_live": False,
            "strategy": strategy_dna,
            "learned_insights": [],
            # Link to original strategy
            "cloned_from": {
                "strategy_id": strategy_id,
                "strategy_name": strategy_name,
                "author_id": strategy.get('user_id'),
                "cloned_at": datetime.now(timezone.utc).isoformat()
            }
        }
        
        # Insert bot
        await db.db['bots'].insert_one(bot_data)
        
        # Increment clone count
        await db.db['marketplace_strategies'].update_one(
            {"id": strategy_id},
            {"$inc": {"clones": 1}}
        )
        
        # Remove _id for response
        bot_data.pop('_id', None)
        
        # Send real-time notification
        try:
            await rt_events.bot_created(user_id, bot_data)
            await rt_events.force_refresh(user_id, f"Strategy '{strategy_name}' cloned successfully")
        except Exception as rt_error:
            logger.warning(f"Real-time event error: {rt_error}")
        
        logger.info(f"Strategy {strategy_id} cloned by user {user_id}, created bot {bot_id}")
        
        return {
            "success": True,
            "message": "Strategy cloned successfully",
            "bot_id": bot_id,
            "bot": bot_data
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Clone strategy error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/strategies/{strategy_id}/rate")
async def rate_strategy(
    strategy_id: str,
    rating: StrategyRating,
    user_id: str = Depends(get_current_user)
):
    """
    Rate and review a strategy
    """
    try:
        # Validate rating
        if not 1 <= rating.rating <= 5:
            raise HTTPException(status_code=400, detail="Rating must be between 1 and 5")
        
        # Store rating
        rating_record = {
            "id": f"rating_{datetime.now(timezone.utc).timestamp()}",
            "strategy_id": strategy_id,
            "user_id": user_id,
            "rating": rating.rating,
            "review": rating.review,
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        
        await db.db['strategy_ratings'].insert_one(rating_record)
        
        # Update strategy average rating
        ratings = await db.db['strategy_ratings'].find(
            {"strategy_id": strategy_id}
        ).to_list(1000)
        
        avg_rating = sum(r['rating'] for r in ratings) / len(ratings)
        
        await db.db['marketplace_strategies'].update_one(
            {"id": strategy_id},
            {
                "$set": {
                    "rating": round(avg_rating, 2),
                    "rating_count": len(ratings)
                }
            }
        )
        
        return {
            "success": True,
            "message": "Rating submitted successfully",
            "new_average": round(avg_rating, 2)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Rate strategy error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/leaderboard")
async def get_leaderboard(
    metric: str = "profit",  # profit, win_rate, sharpe, rating, clones
    limit: int = 50,
    time_period: str = "all_time"  # all_time, monthly, weekly
):
    """
    Get leaderboard of top strategies
    
    Calculates real performance metrics from bots using each strategy
    and ranks them by the specified metric.
    """
    try:
        from datetime import timedelta
        
        # Build time filter if needed
        time_filter = {}
        if time_period == "monthly":
            cutoff = datetime.now(timezone.utc) - timedelta(days=30)
            time_filter = {"created_at": {"$gte": cutoff.isoformat()}}
        elif time_period == "weekly":
            cutoff = datetime.now(timezone.utc) - timedelta(days=7)
            time_filter = {"created_at": {"$gte": cutoff.isoformat()}}
        
        # Get all strategies
        strategies = await db.db['marketplace_strategies'].find(
            {"public": True},
            {"_id": 0}
        ).to_list(1000)
        
        # For each strategy, calculate real performance from bots that use it
        leaderboard = []
        
        for strategy in strategies:
            strategy_id = strategy.get('id')
            
            # Find bots that were cloned from this strategy
            bots = await db.db['bots'].find({
                "cloned_from.strategy_id": strategy_id,
                **time_filter
            }).to_list(1000)
            
            if not bots and time_period != "all_time":
                # If no bots in time period, skip
                continue
            
            # Calculate aggregate metrics
            total_bots = len(bots)
            if total_bots > 0:
                total_profit = sum(bot.get('total_profit', 0) for bot in bots)
                avg_profit = total_profit / total_bots
                avg_win_rate = sum(bot.get('win_rate', 0) for bot in bots) / total_bots
                total_trades = sum(bot.get('trades_count', 0) for bot in bots)
                
                # Calculate Sharpe ratio (simplified)
                profits = [bot.get('total_profit', 0) for bot in bots]
                if len(profits) > 1:
                    mean_profit = sum(profits) / len(profits)
                    variance = sum((p - mean_profit) ** 2 for p in profits) / len(profits)
                    std_dev = variance ** 0.5
                    sharpe = mean_profit / std_dev if std_dev > 0 else 0
                else:
                    sharpe = 0
            else:
                # Use static metrics from strategy if no bots yet
                total_profit = 0
                avg_profit = 0
                avg_win_rate = strategy.get('performance_metrics', {}).get('win_rate', 0)
                total_trades = 0
                sharpe = 0
            
            leaderboard_entry = {
                "strategy_id": strategy_id,
                "name": strategy.get('name'),
                "description": strategy.get('description', '')[:200],  # Truncate
                "author_id": strategy.get('user_id'),
                "published_at": strategy.get('published_at'),
                "rating": strategy.get('rating', 0),
                "rating_count": strategy.get('rating_count', 0),
                "views": strategy.get('views', 0),
                "clones": strategy.get('clones', 0),
                "tags": strategy.get('tags', []),
                # Performance metrics
                "metrics": {
                    "total_profit": round(total_profit, 2),
                    "avg_profit_per_bot": round(avg_profit, 2),
                    "avg_win_rate": round(avg_win_rate, 2),
                    "total_trades": total_trades,
                    "sharpe_ratio": round(sharpe, 4),
                    "total_bots_using": total_bots
                }
            }
            
            leaderboard.append(leaderboard_entry)
        
        # Sort by specified metric
        metric_map = {
            "profit": lambda x: x['metrics']['total_profit'],
            "win_rate": lambda x: x['metrics']['avg_win_rate'],
            "sharpe": lambda x: x['metrics']['sharpe_ratio'],
            "rating": lambda x: x['rating'],
            "clones": lambda x: x['clones'],
            "views": lambda x: x['views']
        }
        
        sort_key = metric_map.get(metric, metric_map["profit"])
        leaderboard.sort(key=sort_key, reverse=True)
        
        # Limit results
        leaderboard = leaderboard[:limit]
        
        # Add rank
        for idx, entry in enumerate(leaderboard):
            entry['rank'] = idx + 1
        
        return {
            "success": True,
            "leaderboard": leaderboard,
            "count": len(leaderboard),
            "metric": metric,
            "time_period": time_period
        }
        
    except Exception as e:
        logger.error(f"Get leaderboard error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
