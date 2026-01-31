"""
Compatibility Endpoints for Dashboard
Provides missing endpoints and backward-compatible aliases to prevent 404s
All routes are production-safe and handle missing data gracefully
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Optional, Dict, List
import logging
from datetime import datetime, timezone

from auth import get_current_user
import database as db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["Compatibility"])


# ============================================================================
# AI Insights - Lightweight system status summary
# ============================================================================

@router.get("/ai/insights")
async def get_ai_insights(user_id: str = Depends(get_current_user)):
    """
    Get AI-powered system insights - lightweight summary
    Aggregates regime, sentiment, whale signals, and recent decisions
    """
    try:
        insights = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "user_id": user_id,
            "regime": {
                "current": "unknown",
                "confidence": 0.0,
                "description": "Market regime detection pending"
            },
            "sentiment": {
                "overall": "neutral",
                "score": 0.0,
                "sources_count": 0
            },
            "whale_signals": {
                "active_count": 0,
                "top_signal": None
            },
            "last_decision": None,
            "system_health": "operational"
        }
        
        # Try to get regime data from advanced endpoints
        try:
            from engines.regime_detector import regime_detector
            regime_state = await regime_detector.get_current_regime()
            if regime_state:
                insights["regime"] = {
                    "current": regime_state.get("regime", "unknown"),
                    "confidence": regime_state.get("confidence", 0.0),
                    "description": regime_state.get("description", "")
                }
        except Exception as e:
            logger.debug(f"Could not fetch regime data: {e}")
        
        # Try to get sentiment data
        try:
            from engines.sentiment_analyzer import sentiment_analyzer
            sentiment = await sentiment_analyzer.get_overall_sentiment()
            if sentiment:
                insights["sentiment"] = {
                    "overall": sentiment.get("sentiment", "neutral"),
                    "score": sentiment.get("score", 0.0),
                    "sources_count": sentiment.get("sources_analyzed", 0)
                }
        except Exception as e:
            logger.debug(f"Could not fetch sentiment data: {e}")
        
        # Try to get recent decision
        try:
            decisions = await db.decisions_collection.find(
                {"user_id": user_id}
            ).sort("timestamp", -1).limit(1).to_list(1)
            
            if decisions:
                decision = decisions[0]
                insights["last_decision"] = {
                    "symbol": decision.get("symbol", "unknown"),
                    "action": decision.get("action", "unknown"),
                    "confidence": decision.get("confidence", 0.0),
                    "timestamp": decision.get("timestamp")
                }
        except Exception as e:
            logger.debug(f"Could not fetch decision data: {e}")
        
        # Check system health
        try:
            # Count active bots
            active_bots = await db.bots_collection.count_documents({
                "user_id": user_id,
                "status": "active"
            })
            
            # Check emergency stop
            modes = await db.system_modes_collection.find_one(
                {"user_id": user_id},
                {"_id": 0}
            )
            
            if modes and modes.get("emergencyStop"):
                insights["system_health"] = "emergency_stop"
            elif active_bots > 0:
                insights["system_health"] = "trading_active"
            else:
                insights["system_health"] = "idle"
                
        except Exception as e:
            logger.debug(f"Could not determine system health: {e}")
        
        return insights
        
    except Exception as e:
        logger.error(f"AI insights error: {e}")
        # Return safe default instead of 500
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "user_id": user_id,
            "regime": {"current": "error", "confidence": 0.0, "description": "Error fetching data"},
            "sentiment": {"overall": "neutral", "score": 0.0, "sources_count": 0},
            "whale_signals": {"active_count": 0, "top_signal": None},
            "last_decision": None,
            "system_health": "error",
            "error": str(e)
        }


# ============================================================================
# ML Predict - Query param compatibility endpoint
# Dashboard calls: /api/ml/predict?symbol=BTC-ZAR&platform=luno
# Backend has: /api/ml/predict/{pair}
# ============================================================================

@router.get("/ml/predict")
async def ml_predict_query_params(
    symbol: Optional[str] = Query(None, description="Trading pair symbol (e.g., BTC-ZAR)"),
    pair: Optional[str] = Query(None, description="Trading pair (e.g., BTC/USDT)"),
    platform: Optional[str] = Query(None, description="Exchange platform"),
    timeframe: str = Query("1h", description="Timeframe for prediction"),
    user_id: str = Depends(get_current_user)
):
    """
    ML prediction endpoint with query parameters (compatibility)
    Accepts both 'symbol' and 'pair' parameters
    """
    try:
        # Determine trading pair from parameters
        trading_pair = pair or symbol
        
        if not trading_pair:
            raise HTTPException(
                status_code=400,
                detail="Either 'symbol' or 'pair' parameter is required"
            )
        
        # Normalize pair format (BTC-ZAR -> BTC/ZAR)
        if '-' in trading_pair:
            trading_pair = trading_pair.replace('-', '/')
        
        # Import and use ML predictor
        from ml_predictor import ml_predictor
        
        prediction = await ml_predictor.predict_price(trading_pair, timeframe)
        
        # Add metadata
        prediction["query"] = {
            "symbol": symbol,
            "pair": trading_pair,
            "platform": platform,
            "timeframe": timeframe
        }
        
        return prediction
        
    except ImportError as e:
        logger.error(f"ML predictor not available: {e}")
        # Return safe default for missing ML predictor
        return {
            "success": False,
            "error": "ML predictor not available",
            "prediction": {
                "direction": "neutral",
                "confidence": 0.0,
                "target_price": None
            },
            "query": {
                "symbol": symbol,
                "pair": trading_pair if 'trading_pair' in locals() else None,
                "platform": platform,
                "timeframe": timeframe
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"ML predict error: {e}")
        # Return safe response instead of 500
        return {
            "success": False,
            "error": str(e),
            "prediction": {
                "direction": "neutral",
                "confidence": 0.0,
                "target_price": None
            },
            "query": {
                "symbol": symbol,
                "pair": trading_pair if 'trading_pair' in locals() else None,
                "platform": platform,
                "timeframe": timeframe
            }
        }


# ============================================================================
# Profits Reinvest - Safe reinvestment trigger
# ============================================================================

@router.post("/profits/reinvest")
async def reinvest_profits(
    amount: Optional[float] = None,
    top_n: int = 3,
    user_id: str = Depends(get_current_user)
):
    """
    Trigger profit reinvestment (paper trading safe)
    Validates rules: max 30 bots, reinvest into top performers
    """
    try:
        # Check current bot count
        bot_count = await db.bots_collection.count_documents({
            "user_id": user_id
        })
        
        if bot_count >= 65:
            return {
                "success": False,
                "message": "Cannot reinvest: maximum bot limit (65) reached",
                "current_bots": bot_count,
                "max_bots": 65
            }
        
        # Try to use the reinvestment service if available
        try:
            from services.daily_reinvestment import get_reinvestment_service
            reinvest_service = get_reinvestment_service(db.db)
            
            # Trigger manual reinvestment
            result = await reinvest_service.execute_reinvestment(
                user_id=user_id,
                manual_trigger=True
            )
            
            return {
                "success": True,
                "message": "Reinvestment triggered successfully",
                "details": result,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            
        except ImportError:
            # Reinvestment service not available - create a reinvest request
            logger.warning("Reinvestment service not available, creating request")
            
            # Store reinvest request for manual processing
            request_doc = {
                "user_id": user_id,
                "requested_at": datetime.now(timezone.utc).isoformat(),
                "amount": amount,
                "top_n": top_n,
                "status": "queued",
                "processed_at": None
            }
            
            await db.reinvest_requests_collection.insert_one(request_doc)
            
            return {
                "success": True,
                "message": "Reinvestment request queued",
                "status": "queued",
                "note": "Manual reinvestment service will process this request",
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            
    except Exception as e:
        logger.error(f"Reinvest profits error: {e}")
        # Return safe error response
        return {
            "success": False,
            "message": f"Reinvestment failed: {str(e)}",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }


# ============================================================================
# Advanced Decisions Recent - Decision trace compatibility
# ============================================================================

@router.get("/advanced/decisions/recent")
async def get_recent_decisions(
    limit: int = Query(100, ge=1, le=1000, description="Number of recent decisions"),
    symbol: Optional[str] = Query(None, description="Filter by symbol"),
    user_id: str = Depends(get_current_user)
):
    """
    Get recent trading decisions for Decision Trace UI
    Compatible with dashboard expectations
    """
    try:
        # Build query
        query = {"user_id": user_id}
        if symbol:
            query["symbol"] = symbol
        
        # Fetch decisions from database
        decisions = await db.decisions_collection.find(
            query,
            {"_id": 0}
        ).sort("timestamp", -1).limit(limit).to_list(limit)
        
        # If no decisions in DB, check for trace data from decision_trace router
        if not decisions:
            try:
                from routes.decision_trace import get_decision_history
                # Call the canonical endpoint
                result = await get_decision_history(
                    limit=limit,
                    symbol=symbol,
                    user_id=user_id
                )
                decisions = result.get("decisions", [])
            except Exception as e:
                logger.debug(f"Could not fetch from decision_trace: {e}")
        
        return {
            "success": True,
            "count": len(decisions),
            "limit": limit,
            "decisions": decisions,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as e:
        logger.error(f"Get recent decisions error: {e}")
        # Return empty list instead of 500
        return {
            "success": False,
            "count": 0,
            "limit": limit,
            "decisions": [],
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "error": str(e)
        }
