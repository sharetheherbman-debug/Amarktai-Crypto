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
    """
    try:
        # Get strategy
        strategy = await db.db['marketplace_strategies'].find_one(
            {"id": strategy_id, "public": True}
        )
        
        if not strategy:
            raise HTTPException(status_code=404, detail="Strategy not found")
        
        # TODO: Create bot with cloned strategy DNA
        # TODO: Link to original strategy
        
        # Increment clone count
        await db.db['marketplace_strategies'].update_one(
            {"id": strategy_id},
            {"$inc": {"clones": 1}}
        )
        
        logger.info(f"Strategy {strategy_id} cloned by user {user_id}")
        
        return {
            "success": True,
            "message": "Strategy cloned successfully (stub implementation)"
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
    metric: str = "profit",  # profit, win_rate, sharpe
    limit: int = 50
):
    """
    Get leaderboard of top strategies
    """
    try:
        # TODO: Calculate real performance metrics
        # TODO: Sort by specified metric
        
        return {
            "success": True,
            "leaderboard": [],
            "message": "Stub implementation - leaderboard not yet available"
        }
        
    except Exception as e:
        logger.error(f"Get leaderboard error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
