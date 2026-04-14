"""
Signal Engine Service - Canonical Signal Aggregation for Order Pipeline

Aggregates signals from multiple sources to compute real expected edge:
- Market regime analysis
- ML price predictions
- Sentiment analysis
- Alpha fusion engine
- Bot historical performance
- Fetch.ai signals

Used by OrderPipeline Gate B to replace placeholder expected_edge_bps.
"""

import asyncio
import os
from typing import Dict, Any, Optional
from datetime import datetime, timezone
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)

# Module-level singleton for AlphaFusionEngine — instantiated once on first use
_alpha_fusion_instance = None
_alpha_fusion_lock = None


@dataclass
class SignalOutput:
    """
    Canonical signal output for order pipeline
    """
    expected_edge_bps: float  # Expected edge in basis points
    confidence: float  # 0.0 to 1.0
    regime: str  # Market regime classification
    risk_score: float  # 0.0 (low risk) to 1.0 (high risk)
    suggested_order_type: str  # "limit" or "market"
    suggested_size_multiplier: float  # 0.5 to 1.5
    rationale: str  # Short explanation
    diagnostics: Dict[str, Any]  # Optional detailed info


class SignalEngine:
    """
    Aggregates signals from multiple sources to compute expected trading edge.
    
    Sources:
    - market_regime.py: Trend and volatility analysis
    - ml_predictor.py: Price prediction and sentiment
    - engines/alpha_fusion_engine.py: Multi-modal signal fusion
    - fetchai_integration.py: AI-powered market signals
    - Bot historical performance: Win rate, profit factor
    """
    
    def __init__(self, db, config: Optional[Dict] = None):
        self.db = db
        self.config = config or {}
        
        # Minimum thresholds
        self.min_confidence = float(self.config.get("MIN_SIGNAL_CONFIDENCE", 0.5))
        self.min_edge_bps = float(self.config.get("MIN_EDGE_BPS", 10.0))
        
        # Regime filters
        self.avoid_high_volatility = self.config.get("AVOID_HIGH_VOLATILITY", True)
        self.avoid_choppy_regime = self.config.get("AVOID_CHOPPY_REGIME", True)
        
        # Edge scaling factors
        self.ml_weight = float(self.config.get("ML_SIGNAL_WEIGHT", 0.30))
        self.regime_weight = float(self.config.get("REGIME_WEIGHT", 0.20))
        self.alpha_weight = float(self.config.get("ALPHA_FUSION_WEIGHT", 0.30))
        self.history_weight = float(self.config.get("HISTORY_WEIGHT", 0.20))
        
        # Cache for performance
        self.signal_cache = {}
        self.cache_ttl_seconds = int(self.config.get("SIGNAL_CACHE_TTL", 30))
    
    async def get_signal(
        self,
        user_id: str,
        bot_id: str,
        exchange: str,
        symbol: str,
        side: str,
        amount: float,
        price: Optional[float] = None
    ) -> SignalOutput:
        """
        Compute aggregated signal for the given trade parameters.
        
        Args:
            user_id: User ID
            bot_id: Bot ID
            exchange: Exchange name
            symbol: Trading pair (e.g., "BTC/USDT")
            side: "buy" or "sell"
            amount: Trade amount
            price: Limit price (optional)
        
        Returns:
            SignalOutput with expected edge and recommendations
        """
        try:
            # Check cache
            cache_key = f"{symbol}_{side}_{int(datetime.now(timezone.utc).timestamp() / self.cache_ttl_seconds)}"
            if cache_key in self.signal_cache:
                return self.signal_cache[cache_key]
            
            diagnostics = {}
            
            # 1. Get market regime
            regime_data = await self._get_market_regime(symbol, exchange)
            diagnostics['regime'] = regime_data
            
            # 2. Get ML prediction
            ml_data = await self._get_ml_prediction(symbol)
            diagnostics['ml'] = ml_data
            
            # 3. Get alpha fusion signal (if available)
            alpha_data = await self._get_alpha_signal(symbol)
            diagnostics['alpha'] = alpha_data
            
            # 4. Get bot historical performance
            history_data = await self._get_bot_history(bot_id)
            diagnostics['history'] = history_data
            
            # 5. Compute expected edge
            expected_edge_bps = self._compute_edge(
                regime_data, ml_data, alpha_data, history_data, side
            )
            
            # 6. Compute confidence
            confidence = self._compute_confidence(
                regime_data, ml_data, alpha_data, history_data
            )
            
            # 7. Compute risk score
            risk_score = self._compute_risk_score(
                regime_data, ml_data, history_data
            )
            
            # 8. Determine order type suggestion
            suggested_order_type = self._suggest_order_type(
                regime_data, confidence, risk_score
            )
            
            # 9. Determine size multiplier
            suggested_size_multiplier = self._suggest_size_multiplier(
                confidence, risk_score, alpha_data
            )
            
            # 10. Generate rationale
            rationale = self._generate_rationale(
                expected_edge_bps, confidence, regime_data, ml_data, side
            )
            
            # Create output
            output = SignalOutput(
                expected_edge_bps=expected_edge_bps,
                confidence=confidence,
                regime=regime_data.get('regime', 'unknown'),
                risk_score=risk_score,
                suggested_order_type=suggested_order_type,
                suggested_size_multiplier=suggested_size_multiplier,
                rationale=rationale,
                diagnostics=diagnostics
            )
            
            # Cache result
            self.signal_cache[cache_key] = output
            
            return output
            
        except Exception as e:
            logger.error(f"Error generating signal: {e}")
            # Return safe fallback
            return SignalOutput(
                expected_edge_bps=self.min_edge_bps,
                confidence=0.3,
                regime='unknown',
                risk_score=0.8,
                suggested_order_type='limit',
                suggested_size_multiplier=0.5,
                rationale=f"Error in signal generation: {str(e)[:100]}",
                diagnostics={'error': str(e)}
            )
    
    async def _get_market_regime(self, symbol: str, exchange: str) -> Dict[str, Any]:
        """Get market regime analysis"""
        try:
            from market_regime import market_regime_detector

            result = await market_regime_detector.detect_regime(symbol, exchange)
            return result

        except Exception as e:
            logger.warning(f"Market regime detection failed: {e}")
            return {'regime': 'unknown', 'confidence': 0.3, 'volatility': 'moderate'}
    
    async def _get_ml_prediction(self, symbol: str) -> Dict[str, Any]:
        """Get ML price prediction.

        Returns the prediction dict.  If the predictor signals an error or
        marks the result as simulated (``is_simulated=True``), the returned
        dict will carry ``is_simulated=True`` so ``_compute_edge`` can zero-weight
        the contribution when ENABLE_LIVE_TRADING is active.
        """
        try:
            from ml_predictor import MLPredictor
            import os

            predictor = MLPredictor()
            prediction = await predictor.predict_price(symbol.replace('/', '_'))

            # Propagate error / simulated flag to the edge computation layer
            if prediction.get('error') or prediction.get('is_simulated'):
                logger.warning(
                    f"ML prediction for {symbol} is unavailable or simulated: "
                    f"{prediction.get('error', 'is_simulated=True')}"
                )
                return {
                    'direction': 'neutral',
                    'confidence': 0.0,
                    'predicted_change': 0.0,
                    'is_simulated': True,
                }

            return prediction

        except Exception as e:
            logger.warning(f"ML prediction failed: {e}")
            return {'direction': 'neutral', 'confidence': 0.3, 'predicted_change': 0.0, 'is_simulated': True}
    
    async def _get_alpha_signal(self, symbol: str) -> Dict[str, Any]:
        """Get alpha fusion signal. Uses module-level singleton to avoid re-instantiation per call."""
        global _alpha_fusion_instance, _alpha_fusion_lock
        _neutral = {'score': 0.0, 'confidence': 0.3, 'position_multiplier': 1.0}
        try:
            from engines.alpha_fusion_engine import AlphaFusionEngine
        except ImportError as ie:
            logger.warning(f"AlphaFusionEngine not importable: {ie}")
            return _neutral

        # Lazy init singleton (thread-safe with asyncio lock)
        if _alpha_fusion_instance is None:
            import asyncio
            if _alpha_fusion_lock is None:
                _alpha_fusion_lock = asyncio.Lock()
            async with _alpha_fusion_lock:
                if _alpha_fusion_instance is None:
                    _alpha_fusion_instance = AlphaFusionEngine()

        try:
            signals = await _alpha_fusion_instance.get_portfolio_signals([symbol])
            fused = signals.get(symbol)
            if fused is None:
                return _neutral
            return {
                'score': getattr(fused, 'alpha_signal', 0.0),
                'confidence': getattr(fused, 'confidence', 0.3),
                'position_multiplier': getattr(fused, 'position_size_multiplier', 1.0),
            }
        except Exception as e:
            logger.warning(f"AlphaFusionEngine.get_portfolio_signals failed for {symbol}: {e}")
            return _neutral
    
    async def _get_bot_history(self, bot_id: str) -> Dict[str, Any]:
        """Get bot historical performance"""
        try:
            # Get bot from DB
            bot = await self.db['bots'].find_one({'_id': bot_id})
            if not bot:
                return {'win_rate': 0.5, 'profit_factor': 1.0, 'avg_profit_bps': 0.0}
            
            # Calculate from bot stats
            win_rate = bot.get('win_rate', 0.5)
            total_profit = bot.get('total_profit', 0.0)
            trade_count = bot.get('trade_count', 0)
            
            avg_profit_bps = 0.0
            if trade_count > 0:
                # Rough estimate: total_profit / trade_count converted to bps
                avg_profit_bps = (total_profit / max(trade_count, 1)) * 100
            
            return {
                'win_rate': win_rate,
                'profit_factor': max(win_rate / max(1 - win_rate, 0.01), 0.1),
                'avg_profit_bps': avg_profit_bps,
                'trade_count': trade_count
            }
            
        except Exception as e:
            logger.warning(f"Bot history lookup failed: {e}")
            return {'win_rate': 0.5, 'profit_factor': 1.0, 'avg_profit_bps': 0.0}
    
    def _compute_edge(
        self,
        regime: Dict,
        ml: Dict,
        alpha: Dict,
        history: Dict,
        side: str
    ) -> float:
        """
        Compute expected edge in basis points.
        
        Combines:
        - ML predicted change (scaled by confidence)
          Note: ml_change_pct is expected in percentage format (e.g., 2.0 for 2%)
          Converted to bps by multiplying by 100
        - Regime trend alignment
        - Alpha fusion score
        - Bot historical average profit

        When ENABLE_LIVE_TRADING=true, any simulated signal source receives zero weight
        to prevent fabricated data from driving real order decisions.
        """
        live_trading_active = os.getenv("ENABLE_LIVE_TRADING", "false").lower() == "true"

        # Accumulator — must be initialized before any += assignments below.
        edge = 0.0

        # 1. ML prediction contribution
        ml_is_simulated = ml.get('is_simulated', False)
        if live_trading_active and ml_is_simulated:
            logger.debug("ML signal is simulated/unavailable — zeroing weight for live trading")
            ml_weight = 0.0
        else:
            ml_weight = self.ml_weight

        ml_change_pct = ml.get('predicted_change', 0.0)  # Expected: percentage (e.g., 2.0 for 2%)
        ml_confidence = ml.get('confidence', 0.5)
        ml_edge = ml_change_pct * 100 * ml_confidence  # Convert % to bps, scale by confidence
        
        # Align with side (if predicting up and we're buying, it's positive)
        ml_direction = ml.get('direction', 'neutral')
        if (side == 'buy' and ml_direction == 'up') or (side == 'sell' and ml_direction == 'down'):
            edge += ml_edge * ml_weight
        elif ml_direction == 'neutral':
            edge += abs(ml_edge) * 0.5 * ml_weight
        else:
            # Prediction against our direction, negative edge
            edge += ml_edge * ml_weight * -0.5
        
        # 2. Regime contribution
        regime_type = regime.get('regime', 'unknown')
        regime_confidence = regime.get('confidence', 0.5)

        # Cover both market_regime_detector labels (stable_uptrend etc.) and
        # canonical regime_classifier labels (trending_up etc.)
        if regime_type in ('stable_uptrend', 'stable_downtrend', 'trending_up', 'trending_down'):
            edge += 15.0 * regime_confidence * self.regime_weight
        elif regime_type in ('consolidation', 'mean_reversion', 'low_volatility'):
            edge += 5.0 * regime_confidence * self.regime_weight
        elif regime_type in ('volatile_uptrend', 'volatile_downtrend', 'breakout', 'high_volatility'):
            edge += 10.0 * regime_confidence * self.regime_weight
        elif regime_type in ('choppy',):
            edge -= 10.0 * regime_confidence * self.regime_weight
        
        # 3. Alpha fusion contribution
        alpha_score = alpha.get('score', 0.0)
        alpha_confidence = alpha.get('confidence', 0.5)
        edge += alpha_score * 20.0 * alpha_confidence * self.alpha_weight
        
        # 4. Historical performance contribution
        avg_profit_bps = history.get('avg_profit_bps', 0.0)
        win_rate = history.get('win_rate', 0.5)
        edge += avg_profit_bps * win_rate * self.history_weight
        
        # Ensure minimum edge
        return max(edge, self.min_edge_bps)
    
    def _compute_confidence(
        self,
        regime: Dict,
        ml: Dict,
        alpha: Dict,
        history: Dict
    ) -> float:
        """Compute overall signal confidence (0.0 to 1.0)"""
        # Average confidence from all sources
        confidences = [
            regime.get('confidence', 0.5),
            ml.get('confidence', 0.5),
            alpha.get('confidence', 0.5),
            min(history.get('trade_count', 0) / 20.0, 1.0)  # More trades = more confidence
        ]
        
        avg_confidence = sum(confidences) / len(confidences)
        return max(min(avg_confidence, 1.0), 0.0)
    
    def _compute_risk_score(
        self,
        regime: Dict,
        ml: Dict,
        history: Dict
    ) -> float:
        """Compute risk score (0.0 low risk to 1.0 high risk)"""
        risk = 0.5  # Base risk
        
        # High volatility increases risk
        volatility = regime.get('volatility', 'moderate')
        if volatility == 'high':
            risk += 0.2
        elif volatility == 'low':
            risk -= 0.1
        
        # Choppy regime increases risk
        if regime.get('regime') == 'choppy':
            risk += 0.2
        
        # Low confidence increases risk
        confidence = ml.get('confidence', 0.5)
        if confidence < 0.5:
            risk += 0.1
        
        # Poor bot history increases risk
        win_rate = history.get('win_rate', 0.5)
        if win_rate < 0.45:
            risk += 0.15
        
        return max(min(risk, 1.0), 0.0)
    
    def _suggest_order_type(
        self,
        regime: Dict,
        confidence: float,
        risk_score: float
    ) -> str:
        """Suggest order type based on conditions"""
        # Use limit orders in high volatility or low confidence
        if regime.get('volatility') == 'high' or confidence < 0.6 or risk_score > 0.7:
            return 'limit'
        
        # Use market orders in stable conditions with high confidence
        return 'market'
    
    def _suggest_size_multiplier(
        self,
        confidence: float,
        risk_score: float,
        alpha: Dict
    ) -> float:
        """Suggest position size multiplier"""
        # Start with alpha fusion suggestion
        multiplier = alpha.get('position_multiplier', 1.0)
        
        # Adjust based on confidence
        if confidence > 0.7:
            multiplier *= 1.2
        elif confidence < 0.5:
            multiplier *= 0.7
        
        # Adjust based on risk
        if risk_score > 0.7:
            multiplier *= 0.6
        elif risk_score < 0.3:
            multiplier *= 1.1
        
        # Clamp to safe range
        return max(min(multiplier, 1.5), 0.5)
    
    def _generate_rationale(
        self,
        expected_edge_bps: float,
        confidence: float,
        regime: Dict,
        ml: Dict,
        side: str
    ) -> str:
        """Generate short rationale for the signal"""
        parts = []
        
        parts.append(f"Expected edge: {expected_edge_bps:.1f} bps")
        parts.append(f"Confidence: {confidence:.0%}")
        
        regime_type = regime.get('regime', 'unknown')
        if regime_type != 'unknown':
            parts.append(f"Regime: {regime_type}")
        
        ml_direction = ml.get('direction', 'neutral')
        if ml_direction != 'neutral':
            parts.append(f"ML: {ml_direction}")
        
        return " | ".join(parts)
