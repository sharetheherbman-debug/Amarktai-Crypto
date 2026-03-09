"""
Advanced Trading System API Endpoints
Exposes regime detection, OFI, whale monitoring, sentiment, and alpha fusion
"""

from fastapi import APIRouter, HTTPException, Depends
from typing import Dict, List, Optional
from datetime import datetime, timezone
from pydantic import BaseModel
import logging

from auth import get_current_user
from models import User

logger = logging.getLogger(__name__)

# Create router
router = APIRouter(prefix="/api/advanced", tags=["Advanced Trading"])

# Import advanced trading modules (with error handling)
try:
    from engines.regime_detector import regime_detector, MarketRegime
    REGIME_AVAILABLE = True
except Exception as e:
    logger.warning(f"Regime detector not available: {e}")
    REGIME_AVAILABLE = False

try:
    from engines.order_flow_imbalance import ofi_calculator
    OFI_AVAILABLE = True
except Exception as e:
    logger.warning(f"OFI calculator not available: {e}")
    OFI_AVAILABLE = False

try:
    from engines.on_chain_monitor import whale_monitor
    WHALE_AVAILABLE = True
except Exception as e:
    logger.warning(f"Whale monitor not available: {e}")
    WHALE_AVAILABLE = False

try:
    from engines.sentiment_analyzer import sentiment_analyzer
    SENTIMENT_AVAILABLE = True
except Exception as e:
    logger.warning(f"Sentiment analyzer not available: {e}")
    SENTIMENT_AVAILABLE = False

try:
    from engines.macro_news_monitor import macro_monitor
    MACRO_AVAILABLE = True
except Exception as e:
    logger.warning(f"Macro monitor not available: {e}")
    MACRO_AVAILABLE = False

try:
    from engines.alpha_fusion_engine import alpha_fusion
    FUSION_AVAILABLE = True
except Exception as e:
    logger.warning(f"Alpha fusion not available: {e}")
    FUSION_AVAILABLE = False

try:
    from engines.self_healing_ai import self_healing_ai
    HEALING_AVAILABLE = True
except Exception as e:
    logger.warning(f"Self-healing AI not available: {e}")
    HEALING_AVAILABLE = False


# ============================================================================
# Request/Response Models
# ============================================================================

class UpdatePriceRequest(BaseModel):
    """Request to update price data"""
    symbol: str
    price: float
    volume: float = 0.0


class OrderBookSnapshotRequest(BaseModel):
    """Request to add order book snapshot"""
    symbol: str
    bid_price: float
    bid_qty: float
    ask_price: float
    ask_qty: float


class FusionSymbolsRequest(BaseModel):
    """Request for multi-symbol fusion"""
    symbols: List[str]


# ============================================================================
# System Status
# ============================================================================

@router.get("/status")
async def get_advanced_system_status(current_user: User = Depends(get_current_user)):
    """Get status of all advanced trading modules"""
    return {
        "modules": {
            "regime_detection": REGIME_AVAILABLE,
            "order_flow_imbalance": OFI_AVAILABLE,
            "whale_monitoring": WHALE_AVAILABLE,
            "sentiment_analysis": SENTIMENT_AVAILABLE,
            "macro_monitoring": MACRO_AVAILABLE,
            "alpha_fusion": FUSION_AVAILABLE,
            "self_healing": HEALING_AVAILABLE
        },
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


# ============================================================================
# Regime Detection Endpoints
# ============================================================================

@router.post("/regime/update-price")
async def update_regime_price(
    request: UpdatePriceRequest,
    current_user: User = Depends(get_current_user)
):
    """Update price data for regime detection"""
    if not REGIME_AVAILABLE:
        raise HTTPException(status_code=503, detail="Regime detection not available")
    
    try:
        await regime_detector.update_price_data(
            symbol=request.symbol,
            price=request.price,
            volume=request.volume
        )
        
        return {
            "success": True,
            "message": f"Price data updated for {request.symbol}"
        }
    except Exception as e:
        logger.error(f"Error updating regime price: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/regime/{symbol}")
async def get_regime_for_symbol(
    symbol: str,
    current_user: User = Depends(get_current_user)
):
    """Get current regime for a symbol"""
    if not REGIME_AVAILABLE:
        raise HTTPException(status_code=503, detail="Regime detection not available")
    
    try:
        regime_state = await regime_detector.detect_regime(symbol)
        
        if not regime_state:
            raise HTTPException(status_code=404, detail=f"No regime data for {symbol}")
        
        trading_params = regime_detector.get_trading_parameters(regime_state)
        
        return {
            "symbol": symbol,
            "regime": regime_state.regime.value,
            "confidence": regime_state.confidence,
            "volatility": regime_state.volatility,
            "trend_strength": regime_state.trend_strength,
            "timestamp": regime_state.timestamp.isoformat(),
            "features": regime_state.features,
            "trading_params": trading_params
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting regime: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/regime/summary")
async def get_regime_summary(current_user: User = Depends(get_current_user)):
    """Get summary of all tracked regimes"""
    if not REGIME_AVAILABLE:
        raise HTTPException(status_code=503, detail="Regime detection not available")
    
    try:
        summary = await regime_detector.get_regime_summary()
        return {
            "regimes": summary,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    except Exception as e:
        logger.error(f"Error getting regime summary: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Order Flow Imbalance Endpoints
# ============================================================================

@router.post("/ofi/snapshot")
async def add_ofi_snapshot(
    request: OrderBookSnapshotRequest,
    current_user: User = Depends(get_current_user)
):
    """Add order book snapshot for OFI calculation"""
    if not OFI_AVAILABLE:
        raise HTTPException(status_code=503, detail="OFI not available")
    
    try:
        await ofi_calculator.add_snapshot(
            symbol=request.symbol,
            bid_price=request.bid_price,
            bid_qty=request.bid_qty,
            ask_price=request.ask_price,
            ask_qty=request.ask_qty
        )
        
        return {
            "success": True,
            "message": f"Order book snapshot added for {request.symbol}"
        }
    except Exception as e:
        logger.error(f"Error adding OFI snapshot: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/ofi/{symbol}")
async def get_ofi_signal(
    symbol: str,
    threshold: float = 0.1,
    current_user: User = Depends(get_current_user)
):
    """Get OFI signal for a symbol"""
    if not OFI_AVAILABLE:
        raise HTTPException(status_code=503, detail="OFI not available")
    
    try:
        signal = await ofi_calculator.get_signal(symbol, threshold=threshold)
        
        if not signal:
            raise HTTPException(status_code=404, detail=f"No OFI signal for {symbol}")
        
        return {
            "symbol": signal.symbol,
            "recommendation": signal.recommendation,
            "signal_strength": signal.signal_strength,
            "ofi_value": signal.ofi_value,
            "aggregated_ofi": signal.aggregated_ofi,
            "timestamp": signal.timestamp.isoformat()
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting OFI signal: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/ofi/stats/{symbol}")
async def get_ofi_stats(
    symbol: str,
    current_user: User = Depends(get_current_user)
):
    """Get OFI statistics for a symbol"""
    if not OFI_AVAILABLE:
        raise HTTPException(status_code=503, detail="OFI not available")
    
    try:
        stats = await ofi_calculator.get_ofi_stats(symbol)
        
        if not stats:
            raise HTTPException(status_code=404, detail=f"No OFI stats for {symbol}")
        
        return stats
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting OFI stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Whale Monitoring Endpoints
# ============================================================================

@router.get("/whale/{coin}")
async def get_whale_signal(
    coin: str,
    current_user: User = Depends(get_current_user)
):
    """Get whale activity signal for a coin"""
    if not WHALE_AVAILABLE:
        raise HTTPException(status_code=503, detail="Whale monitoring not available")
    
    try:
        signal = await whale_monitor.get_whale_signal(coin)
        
        if not signal:
            raise HTTPException(status_code=404, detail=f"No whale signal for {coin}")
        
        return {
            "coin": signal.coin,
            "signal": signal.signal,
            "strength": signal.strength,
            "reason": signal.reason,
            "metrics": signal.metrics,
            "recent_transactions": len(signal.recent_transactions),
            "timestamp": signal.timestamp.isoformat()
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting whale signal: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/whale/summary")
async def get_whale_summary(current_user: User = Depends(get_current_user)):
    """Get summary of whale activity for all tracked coins.
    
    Returns empty signals when whale monitoring is not available
    (service unavailable or not configured) instead of raising an error.
    """
    if not WHALE_AVAILABLE:
        return {
            "status": "unavailable",
            "message": "Whale monitoring service is not configured",
            "data": None,
            "summary": None,
            "signals": [],
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    
    try:
        summary = await whale_monitor.get_summary()
        return {
            "status": "success",
            "data": summary,
            "summary": summary,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    except Exception as e:
        logger.error(f"Error getting whale summary: {e}")
        return {
            "status": "error",
            "message": str(e)[:200],
            "data": None,
            "summary": None,
            "signals": [],
            "timestamp": datetime.now(timezone.utc).isoformat()
        }


# ============================================================================
# Sentiment Analysis Endpoints
# ============================================================================

@router.get("/sentiment/{coin}")
async def get_sentiment_signal(
    coin: str,
    hours: int = 24,
    current_user: User = Depends(get_current_user)
):
    """Get sentiment signal for a coin"""
    if not SENTIMENT_AVAILABLE:
        raise HTTPException(status_code=503, detail="Sentiment analysis not available")
    
    try:
        sentiment = await sentiment_analyzer.analyze_coin_sentiment(coin, hours=hours)
        
        if not sentiment:
            raise HTTPException(status_code=404, detail=f"No sentiment data for {coin}")
        
        return {
            "coin": sentiment.coin,
            "sentiment": sentiment.sentiment.value,
            "score": sentiment.score,
            "confidence": sentiment.confidence,
            "article_count": sentiment.article_count,
            "key_topics": sentiment.key_topics,
            "recommendation": sentiment.recommendation,
            "timestamp": sentiment.timestamp.isoformat()
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting sentiment: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sentiment/summary")
async def get_sentiment_summary(current_user: User = Depends(get_current_user)):
    """Get sentiment summary for all tracked coins"""
    if not SENTIMENT_AVAILABLE:
        raise HTTPException(status_code=503, detail="Sentiment analysis not available")
    
    try:
        summary = await sentiment_analyzer.get_sentiment_summary()
        return {
            "summary": summary,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    except Exception as e:
        logger.error(f"Error getting sentiment summary: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Macro News Monitoring Endpoints
# ============================================================================

@router.get("/macro/signal")
async def get_macro_signal(current_user: User = Depends(get_current_user)):
    """Get current macro signal"""
    if not MACRO_AVAILABLE:
        raise HTTPException(status_code=503, detail="Macro monitoring not available")
    
    try:
        signal = await macro_monitor.get_macro_signal()
        
        return {
            "signal": signal.signal,
            "risk_multiplier": signal.risk_multiplier,
            "reason": signal.reason,
            "recent_events": [
                {
                    "timestamp": e.timestamp.isoformat(),
                    "type": e.event_type.value,
                    "title": e.title,
                    "impact": e.impact.value,
                    "risk_adjustment": e.risk_adjustment
                }
                for e in signal.recent_events
            ],
            "timestamp": signal.timestamp.isoformat()
        }
    except Exception as e:
        logger.error(f"Error getting macro signal: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/macro/summary")
async def get_macro_summary(current_user: User = Depends(get_current_user)):
    """Get macro events summary"""
    if not MACRO_AVAILABLE:
        raise HTTPException(status_code=503, detail="Macro monitoring not available")
    
    try:
        summary = await macro_monitor.get_summary()
        return summary
    except Exception as e:
        logger.error(f"Error getting macro summary: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Alpha Fusion Endpoints
# ============================================================================

@router.get("/fusion/{symbol}")
async def get_fusion_signal(
    symbol: str,
    current_user: User = Depends(get_current_user)
):
    """Get fused alpha signal for a symbol"""
    if not FUSION_AVAILABLE:
        raise HTTPException(status_code=503, detail="Alpha fusion not available")
    
    try:
        fused = await alpha_fusion.fuse_signals(symbol)
        
        if not fused:
            raise HTTPException(status_code=404, detail=f"No fusion signal for {symbol}")
        
        return {
            "symbol": fused.symbol,
            "signal": fused.signal.value,
            "confidence": fused.confidence,
            "score": fused.score,
            "position_size_multiplier": fused.position_size_multiplier,
            "stop_loss_pct": fused.stop_loss_pct,
            "take_profit_pct": fused.take_profit_pct,
            "reasoning": fused.reasoning,
            "component_scores": fused.component_scores,
            "component_weights": fused.component_weights,
            "timestamp": fused.timestamp.isoformat()
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting fusion signal: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/fusion/portfolio")
async def get_portfolio_fusion(
    request: FusionSymbolsRequest,
    current_user: User = Depends(get_current_user)
):
    """Get fused signals for multiple symbols"""
    if not FUSION_AVAILABLE:
        raise HTTPException(status_code=503, detail="Alpha fusion not available")
    
    try:
        signals = await alpha_fusion.get_portfolio_signals(request.symbols)
        summary = alpha_fusion.get_summary(signals)
        
        return summary
    except Exception as e:
        logger.error(f"Error getting portfolio fusion: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Self-Healing AI Endpoints
# ============================================================================

@router.get("/self-healing/health")
async def get_self_healing_health(current_user: User = Depends(get_current_user)):
    """Get self-healing system health report"""
    if not HEALING_AVAILABLE:
        raise HTTPException(status_code=503, detail="Self-healing not available")
    
    try:
        report = await self_healing_ai.get_health_report()
        return report
    except Exception as e:
        logger.error(f"Error getting health report: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Export router
__all__ = ['router']
