"""
Multi-Modal Alpha Fusion Engine
Combines signals from multiple sources:
- Regime detection (HMM/GMM)
- Order Flow Imbalance (OFI)
- On-chain whale activity
- Sentiment analysis (news/social)
- Macro news events

Generates unified trading signals with confidence scores
"""

from typing import Dict, List, Optional, Tuple
from datetime import datetime, timezone
from dataclasses import dataclass
from enum import Enum
import logging
import numpy as np
import os

from engines.regime_detector import regime_detector, MarketRegime, RegimeState
from engines.order_flow_imbalance import ofi_calculator, OFISignal
from engines.on_chain_monitor import whale_monitor, WhaleSignal
from engines.sentiment_analyzer import sentiment_analyzer, AggregatedSentiment
from engines.macro_news_monitor import macro_monitor, MacroSignal

logger = logging.getLogger(__name__)

# Position sizing constants
MIN_POSITION_MULTIPLIER = 0.5  # Minimum position size (50% of base)
MAX_POSITION_MULTIPLIER = 1.5  # Maximum position size (150% of base)


class SignalStrength(Enum):
    """Signal strength classification"""
    STRONG_BUY = "strong_buy"
    BUY = "buy"
    NEUTRAL = "neutral"
    SELL = "sell"
    STRONG_SELL = "strong_sell"


@dataclass
class FusedSignal:
    """Unified trading signal from all sources"""
    timestamp: datetime
    symbol: str
    signal: SignalStrength
    confidence: float  # 0.0 to 1.0
    score: float  # -1.0 (strong sell) to 1.0 (strong buy)
    position_size_multiplier: float  # Suggested position size adjustment
    stop_loss_pct: float
    take_profit_pct: float
    
    # Component signals
    regime_signal: Optional[RegimeState]
    ofi_signal: Optional[OFISignal]
    whale_signal: Optional[WhaleSignal]
    sentiment_signal: Optional[AggregatedSentiment]
    macro_signal: Optional[MacroSignal]
    
    # Signal weights
    component_weights: Dict[str, float]
    component_scores: Dict[str, float]
    
    # Reasoning
    reasoning: List[str]


class AlphaFusionEngine:
    """
    Fuses signals from multiple data sources into unified trading recommendations
    Uses configurable weights for each signal type
    """
    
    def __init__(
        self,
        regime_weight: float = 0.25,
        ofi_weight: float = 0.20,
        whale_weight: float = 0.20,
        sentiment_weight: float = 0.20,
        macro_weight: Optional[float] = None
    ):
        """
        Initialize alpha fusion engine
        
        Args:
            regime_weight: Weight for regime detection signal (default: 0.25)
            ofi_weight: Weight for OFI signal (default: 0.20)
            whale_weight: Weight for whale activity signal (default: 0.20)
            sentiment_weight: Weight for sentiment signal (default: 0.20)
            macro_weight: Weight for macro news signal (default: 0.15)
        """
        # Normalize weights to sum to 1.0
        if macro_weight is None:
            macro_weight = float(os.getenv("MACRO_SIGNAL_WEIGHT", "0.0"))
        total = regime_weight + ofi_weight + whale_weight + sentiment_weight + macro_weight
        
        self.weights = {
            'regime': regime_weight / total,
            'ofi': ofi_weight / total,
            'whale': whale_weight / total,
            'sentiment': sentiment_weight / total,
            'macro': macro_weight / total
        }
        
        logger.info(f"Alpha Fusion Engine initialized with weights: {self.weights}")
    
    def _normalize_score(self, value: float, min_val: float, max_val: float) -> float:
        """
        Normalize value to [-1, 1] range
        
        Args:
            value: Value to normalize
            min_val: Minimum possible value
            max_val: Maximum possible value
            
        Returns:
            Normalized score
        """
        if max_val == min_val:
            return 0.0
        
        return 2 * (value - min_val) / (max_val - min_val) - 1
    
    def _regime_to_score(self, regime_state: Optional[RegimeState]) -> Tuple[float, float]:
        """
        Convert regime state to signal score
        
        Args:
            regime_state: Current regime
            
        Returns:
            (score, confidence)
        """
        if regime_state is None:
            return 0.0, 0.0
        
        # Map regimes to scores
        regime_scores = {
            MarketRegime.BULLISH_CALM: 0.7,
            MarketRegime.SQUEEZE: 0.2,
            MarketRegime.BEARISH_VOLATILE: -0.6,
            MarketRegime.UNKNOWN: 0.0
        }
        
        score = regime_scores.get(regime_state.regime, 0.0)
        confidence = regime_state.confidence
        
        return score, confidence
    
    def _ofi_to_score(self, ofi_signal: Optional[OFISignal]) -> Tuple[float, float]:
        """
        Convert OFI signal to score
        
        Args:
            ofi_signal: OFI signal
            
        Returns:
            (score, confidence)
        """
        if ofi_signal is None:
            return 0.0, 0.0
        
        # OFI signal_strength is already normalized to [-1, 1]
        score = ofi_signal.signal_strength
        
        # Confidence based on magnitude
        confidence = min(abs(score) * 2, 1.0)
        
        return score, confidence
    
    def _whale_to_score(self, whale_signal: Optional[WhaleSignal]) -> Tuple[float, float]:
        """
        Convert whale signal to score
        
        Args:
            whale_signal: Whale activity signal
            
        Returns:
            (score, confidence)
        """
        if whale_signal is None:
            return 0.0, 0.0
        
        # Map whale signals to scores
        if whale_signal.signal == 'bullish':
            score = 0.6
        elif whale_signal.signal == 'bearish':
            score = -0.6
        else:
            score = 0.0
        
        confidence = whale_signal.strength
        
        return score, confidence
    
    def _sentiment_to_score(self, sentiment_signal: Optional[AggregatedSentiment]) -> Tuple[float, float]:
        """
        Convert sentiment signal to score
        
        Args:
            sentiment_signal: Aggregated sentiment
            
        Returns:
            (score, confidence)
        """
        if sentiment_signal is None:
            return 0.0, 0.0
        
        # Sentiment score is already in the right range
        score = sentiment_signal.score
        confidence = sentiment_signal.confidence
        
        return score, confidence
    
    def _macro_to_score(self, macro_signal: Optional[MacroSignal]) -> Tuple[float, float]:
        """
        Convert macro signal to score
        
        Args:
            macro_signal: Macro news signal
            
        Returns:
            (score, confidence)
        """
        if macro_signal is None:
            return 0.0, 0.0
        
        # Convert risk multiplier to score
        # risk_multiplier: 0.5 to 1.5
        # score: -1 to 1
        score = (macro_signal.risk_multiplier - 1.0) * 2
        score = max(-1.0, min(1.0, score))
        
        # Confidence based on number of recent events
        confidence = min(len(macro_signal.recent_events) / 5.0, 1.0)
        
        return score, confidence
    
    async def fuse_signals(self, symbol: str) -> Optional[FusedSignal]:
        """
        Combine all signals for a symbol
        
        Args:
            symbol: Trading pair
            
        Returns:
            FusedSignal with unified recommendation
        """
        # Collect all signals
        regime_state = regime_detector.current_regimes.get(symbol)
        ofi_signal = await ofi_calculator.get_signal(symbol)
        
        # Extract coin from symbol (e.g., "BTC/USDT" -> "BTC")
        coin = symbol.split('/')[0]
        whale_signal = await whale_monitor.get_whale_signal(coin)
        sentiment_signal = await sentiment_analyzer.analyze_coin_sentiment(coin, hours=24)
        macro_signal = await macro_monitor.get_macro_signal()
        
        # Convert each signal to score
        regime_score, regime_conf = self._regime_to_score(regime_state)
        ofi_score, ofi_conf = self._ofi_to_score(ofi_signal)
        whale_score, whale_conf = self._whale_to_score(whale_signal)
        sentiment_score, sentiment_conf = self._sentiment_to_score(sentiment_signal)
        macro_score, macro_conf = self._macro_to_score(macro_signal)
        live_enabled = os.getenv("ENABLE_LIVE_TRADING", "false").lower() == "true"
        if live_enabled and macro_signal:
            has_real_macro = any(not getattr(evt, "is_simulated", False) for evt in macro_signal.recent_events)
            if not has_real_macro:
                macro_score = 0.0
                macro_conf = 0.0
        
        # Store component scores
        component_scores = {
            'regime': regime_score,
            'ofi': ofi_score,
            'whale': whale_score,
            'sentiment': sentiment_score,
            'macro': macro_score
        }
        
        # Calculate weighted average score
        weighted_score = (
            regime_score * self.weights['regime'] * regime_conf +
            ofi_score * self.weights['ofi'] * ofi_conf +
            whale_score * self.weights['whale'] * whale_conf +
            sentiment_score * self.weights['sentiment'] * sentiment_conf +
            macro_score * self.weights['macro'] * macro_conf
        )
        
        # Calculate average confidence (weighted by signal confidence)
        total_conf_weight = (
            self.weights['regime'] * regime_conf +
            self.weights['ofi'] * ofi_conf +
            self.weights['whale'] * whale_conf +
            self.weights['sentiment'] * sentiment_conf +
            self.weights['macro'] * macro_conf
        )
        
        avg_confidence = total_conf_weight if total_conf_weight > 0 else 0.0
        
        # Classify signal strength
        if weighted_score >= 0.5:
            signal_strength = SignalStrength.STRONG_BUY
        elif weighted_score >= 0.2:
            signal_strength = SignalStrength.BUY
        elif weighted_score <= -0.5:
            signal_strength = SignalStrength.STRONG_SELL
        elif weighted_score <= -0.2:
            signal_strength = SignalStrength.SELL
        else:
            signal_strength = SignalStrength.NEUTRAL
        
        # Calculate position sizing and risk parameters
        # Adjust based on signal strength and confidence
        position_multiplier = 1.0 + (weighted_score * avg_confidence * 0.5)
        position_multiplier = max(MIN_POSITION_MULTIPLIER, min(MAX_POSITION_MULTIPLIER, position_multiplier))
        
        # Get regime-based parameters if available
        if regime_state:
            params = regime_detector.get_trading_parameters(regime_state)
            stop_loss_pct = params['stop_loss_pct']
            take_profit_pct = params['take_profit_pct']
        else:
            stop_loss_pct = 2.5
            take_profit_pct = 4.0
        
        # Adjust by macro risk
        if macro_signal:
            position_multiplier *= macro_signal.risk_multiplier
            stop_loss_pct *= (2.0 - macro_signal.risk_multiplier)  # Tighter stops in risk-off
        
        # Build reasoning
        reasoning = []
        
        if regime_state and abs(regime_score) > 0.3:
            reasoning.append(f"Market regime: {regime_state.regime.value} (confidence: {regime_conf:.0%})")
        
        if ofi_signal and abs(ofi_score) > 0.3:
            reasoning.append(f"Order flow: {ofi_signal.recommendation} (strength: {ofi_conf:.0%})")
        
        if whale_signal and abs(whale_score) > 0.3:
            reasoning.append(f"Whale activity: {whale_signal.signal} - {whale_signal.reason}")
        
        if sentiment_signal and abs(sentiment_score) > 0.3:
            reasoning.append(
                f"Sentiment: {sentiment_signal.sentiment.value} "
                f"({sentiment_signal.article_count} articles)"
            )
        
        if macro_signal and abs(macro_score) > 0.3:
            reasoning.append(f"Macro: {macro_signal.reason}")
        
        if not reasoning:
            reasoning.append("Neutral signals across all sources")
        
        fused_signal = FusedSignal(
            timestamp=datetime.now(timezone.utc),
            symbol=symbol,
            signal=signal_strength,
            confidence=avg_confidence,
            score=weighted_score,
            position_size_multiplier=position_multiplier,
            stop_loss_pct=stop_loss_pct,
            take_profit_pct=take_profit_pct,
            regime_signal=regime_state,
            ofi_signal=ofi_signal,
            whale_signal=whale_signal,
            sentiment_signal=sentiment_signal,
            macro_signal=macro_signal,
            component_weights=self.weights,
            component_scores=component_scores,
            reasoning=reasoning
        )
        
        logger.info(
            f"Alpha fusion for {symbol}: {signal_strength.value} "
            f"(score: {weighted_score:.2f}, confidence: {avg_confidence:.0%})"
        )
        logger.info(f"Reasoning: {' | '.join(reasoning)}")
        
        return fused_signal
    
    async def get_portfolio_signals(self, symbols: List[str]) -> Dict[str, FusedSignal]:
        """
        Get fused signals for multiple symbols
        
        Args:
            symbols: List of trading pairs
            
        Returns:
            Dictionary of symbol -> FusedSignal
        """
        signals = {}
        
        for symbol in symbols:
            try:
                signal = await self.fuse_signals(symbol)
                if signal:
                    signals[symbol] = signal
            except Exception as e:
                logger.error(f"Error fusing signals for {symbol}: {e}")
        
        return signals
    
    def get_summary(self, signals: Dict[str, FusedSignal]) -> Dict:
        """
        Get summary of portfolio signals
        
        Args:
            signals: Dictionary of fused signals
            
        Returns:
            Summary dictionary
        """
        if not signals:
            return {'message': 'No signals available'}
        
        # Count signal types
        signal_counts = {}
        for sig_strength in SignalStrength:
            count = sum(1 for s in signals.values() if s.signal == sig_strength)
            if count > 0:
                signal_counts[sig_strength.value] = count
        
        # Average scores and confidence
        avg_score = np.mean([s.score for s in signals.values()])
        avg_confidence = np.mean([s.confidence for s in signals.values()])
        avg_position_mult = np.mean([s.position_size_multiplier for s in signals.values()])
        
        summary = {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'total_symbols': len(signals),
            'signal_distribution': signal_counts,
            'average_score': float(avg_score),
            'average_confidence': float(avg_confidence),
            'average_position_multiplier': float(avg_position_mult),
            'weights': self.weights,
            'signals': {
                symbol: {
                    'signal': s.signal.value,
                    'score': s.score,
                    'confidence': s.confidence,
                    'position_multiplier': s.position_size_multiplier,
                    'stop_loss_pct': s.stop_loss_pct,
                    'take_profit_pct': s.take_profit_pct,
                    'reasoning': s.reasoning,
                    'component_scores': s.component_scores
                }
                for symbol, s in signals.items()
            }
        }
        
        return summary


# Global instance
alpha_fusion = AlphaFusionEngine()
