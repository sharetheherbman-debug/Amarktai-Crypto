"""
Order Flow Imbalance (OFI) Calculator
Implements micro-scale entry decision-making using order book imbalances
Formula: e_n = I{P^b_n >= P^b_{n-1}}q^b_n - I{P^b_n <= P^b_{n-1}}q^b_{n-1} 
              - I{P^a_n <= P^a_{n-1}}q^a_n + I{P^a_n >= P^a_{n-1}}q^a_{n-1}
"""

import numpy as np
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass
from collections import deque
import logging

logger = logging.getLogger(__name__)


@dataclass
class OrderBookSnapshot:
    """Order book snapshot at time n"""
    timestamp: datetime
    bid_price: float  # P^b_n
    bid_qty: float    # q^b_n
    ask_price: float  # P^a_n
    ask_qty: float    # q^a_n


@dataclass
class OFISignal:
    """Order flow imbalance signal"""
    timestamp: datetime
    symbol: str
    ofi_value: float
    aggregated_ofi: float
    signal_strength: float  # -1 to 1
    recommendation: str  # 'buy', 'sell', 'neutral'


class OrderFlowImbalanceCalculator:
    """
    Calculates Order Flow Imbalance (OFI) for micro-scale trading decisions
    Aggregates imbalances over configurable intervals (default: 1 second)
    """
    
    def __init__(self, aggregation_window: int = 1, lookback_seconds: int = 60):
        """
        Initialize OFI calculator
        
        Args:
            aggregation_window: Seconds to aggregate OFI (default: 1)
            lookback_seconds: History to maintain (default: 60)
        """
        self.aggregation_window = aggregation_window
        self.lookback_seconds = lookback_seconds
        
        # Store order book snapshots per symbol
        self.snapshots: Dict[str, deque] = {}
        
        # Store calculated OFI values per symbol
        self.ofi_history: Dict[str, deque] = {}
        
        # Aggregated OFI per symbol
        self.aggregated_ofi: Dict[str, List[float]] = {}
    
    def _indicator(self, condition: bool) -> int:
        """Indicator function: I{condition} = 1 if True, 0 if False"""
        return 1 if condition else 0
    
    async def add_snapshot(
        self,
        symbol: str,
        bid_price: float,
        bid_qty: float,
        ask_price: float,
        ask_qty: float
    ) -> None:
        """
        Add order book snapshot
        
        Args:
            symbol: Trading pair
            bid_price: Best bid price
            bid_qty: Quantity at best bid
            ask_price: Best ask price
            ask_qty: Quantity at best ask
        """
        if symbol not in self.snapshots:
            self.snapshots[symbol] = deque(maxlen=self.lookback_seconds * 10)
            self.ofi_history[symbol] = deque(maxlen=self.lookback_seconds * 10)
            self.aggregated_ofi[symbol] = []
        
        snapshot = OrderBookSnapshot(
            timestamp=datetime.now(timezone.utc),
            bid_price=bid_price,
            bid_qty=bid_qty,
            ask_price=ask_price,
            ask_qty=ask_qty
        )
        
        self.snapshots[symbol].append(snapshot)
        
        # Calculate OFI if we have previous snapshot
        if len(self.snapshots[symbol]) >= 2:
            ofi = self._calculate_ofi(symbol)
            if ofi is not None:
                self.ofi_history[symbol].append((snapshot.timestamp, ofi))
    
    def _calculate_ofi(self, symbol: str) -> Optional[float]:
        """
        Calculate Order Flow Imbalance for latest snapshot
        
        Formula:
        e_n = I{P^b_n >= P^b_{n-1}}q^b_n - I{P^b_n <= P^b_{n-1}}q^b_{n-1}
              - I{P^a_n <= P^a_{n-1}}q^a_n + I{P^a_n >= P^a_{n-1}}q^a_{n-1}
        
        Where:
        - P^b = Bid price, P^a = Ask price
        - q^b = Bid quantity, q^a = Ask quantity
        - I{condition} = Indicator function (1 if true, 0 if false)
        - n = current snapshot, n-1 = previous snapshot
        
        Positive OFI indicates buying pressure (bid side strengthening)
        Negative OFI indicates selling pressure (ask side strengthening)
        
        Args:
            symbol: Trading pair
            
        Returns:
            OFI value (positive = buying pressure, negative = selling pressure)
        """
        if len(self.snapshots[symbol]) < 2:
            return None
        
        # Get current and previous snapshots
        current = self.snapshots[symbol][-1]  # n
        previous = self.snapshots[symbol][-2]  # n-1
        
        # Extract values
        P_b_n = current.bid_price
        P_b_n_1 = previous.bid_price
        q_b_n = current.bid_qty
        q_b_n_1 = previous.bid_qty
        
        P_a_n = current.ask_price
        P_a_n_1 = previous.ask_price
        q_a_n = current.ask_qty
        q_a_n_1 = previous.ask_qty
        
        # Calculate OFI using the formula
        # Term 1: Bid improvement component
        term1 = self._indicator(P_b_n >= P_b_n_1) * q_b_n
        # Term 2: Bid deterioration component
        term2 = self._indicator(P_b_n <= P_b_n_1) * q_b_n_1
        # Term 3: Ask deterioration component
        term3 = self._indicator(P_a_n <= P_a_n_1) * q_a_n
        # Term 4: Ask improvement component
        term4 = self._indicator(P_a_n >= P_a_n_1) * q_a_n_1
        
        e_n = term1 - term2 - term3 + term4
        
        return e_n
    
    async def get_aggregated_ofi(
        self,
        symbol: str,
        window_seconds: Optional[int] = None
    ) -> Optional[float]:
        """
        Get aggregated OFI over time window
        
        Args:
            symbol: Trading pair
            window_seconds: Aggregation window (default: self.aggregation_window)
            
        Returns:
            Aggregated OFI value
        """
        if symbol not in self.ofi_history or len(self.ofi_history[symbol]) == 0:
            return None
        
        if window_seconds is None:
            window_seconds = self.aggregation_window
        
        cutoff_time = datetime.now(timezone.utc) - timedelta(seconds=window_seconds)
        
        # Aggregate OFI values within window
        recent_ofi = [
            ofi for ts, ofi in self.ofi_history[symbol]
            if ts >= cutoff_time
        ]
        
        if not recent_ofi:
            return None
        
        aggregated = sum(recent_ofi)
        
        return aggregated
    
    async def get_signal(self, symbol: str, threshold: float = 0.1) -> Optional[OFISignal]:
        """
        Generate trading signal from OFI
        
        Args:
            symbol: Trading pair
            threshold: Threshold for signal generation (default: 0.1)
            
        Returns:
            OFISignal with recommendation
        """
        if symbol not in self.ofi_history or len(self.ofi_history[symbol]) < 5:
            return None
        
        # Get aggregated OFI
        aggregated_ofi = await self.get_aggregated_ofi(symbol)
        
        if aggregated_ofi is None:
            return None
        
        # Get current OFI
        current_time, current_ofi = self.ofi_history[symbol][-1]
        
        # Calculate signal strength (normalized)
        # Use recent history to normalize
        recent_values = [ofi for _, ofi in list(self.ofi_history[symbol])[-30:]]
        std_dev = np.std(recent_values) if len(recent_values) > 1 else 1.0
        
        if std_dev == 0:
            std_dev = 1.0
        
        signal_strength = aggregated_ofi / (std_dev * 3)  # 3-sigma normalization
        signal_strength = max(-1.0, min(1.0, signal_strength))  # Clip to [-1, 1]
        
        # Generate recommendation
        if signal_strength > threshold:
            recommendation = 'buy'
        elif signal_strength < -threshold:
            recommendation = 'sell'
        else:
            recommendation = 'neutral'
        
        signal = OFISignal(
            timestamp=current_time,
            symbol=symbol,
            ofi_value=current_ofi,
            aggregated_ofi=aggregated_ofi,
            signal_strength=signal_strength,
            recommendation=recommendation
        )
        
        logger.debug(
            f"OFI Signal for {symbol}: {recommendation} "
            f"(strength: {signal_strength:.3f}, agg_ofi: {aggregated_ofi:.3f})"
        )
        
        return signal
    
    async def get_predictive_features(self, symbol: str) -> Optional[Dict[str, float]]:
        """
        Extract predictive features from OFI for ML models
        
        Args:
            symbol: Trading pair
            
        Returns:
            Dictionary of features
        """
        if symbol not in self.ofi_history or len(self.ofi_history[symbol]) < 10:
            return None
        
        # Get recent OFI values
        recent_ofi = [ofi for _, ofi in list(self.ofi_history[symbol])[-30:]]
        
        if len(recent_ofi) < 10:
            return None
        
        # Calculate features
        features = {
            'ofi_mean': float(np.mean(recent_ofi)),
            'ofi_std': float(np.std(recent_ofi)),
            'ofi_min': float(np.min(recent_ofi)),
            'ofi_max': float(np.max(recent_ofi)),
            'ofi_current': float(recent_ofi[-1]),
            'ofi_trend': float(np.mean(recent_ofi[-5:]) - np.mean(recent_ofi[-10:-5])),
            'ofi_momentum': float(recent_ofi[-1] - recent_ofi[-5]),
            'buy_pressure_ratio': float(sum(1 for x in recent_ofi if x > 0) / len(recent_ofi)),
            'sell_pressure_ratio': float(sum(1 for x in recent_ofi if x < 0) / len(recent_ofi))
        }
        
        return features
    
    async def get_ofi_stats(self, symbol: str) -> Optional[Dict]:
        """
        Get statistics about OFI for a symbol
        
        Args:
            symbol: Trading pair
            
        Returns:
            Dictionary of OFI statistics
        """
        if symbol not in self.ofi_history or len(self.ofi_history[symbol]) == 0:
            return None
        
        ofi_values = [ofi for _, ofi in self.ofi_history[symbol]]
        
        aggregated = await self.get_aggregated_ofi(symbol)
        signal = await self.get_signal(symbol)
        features = await self.get_predictive_features(symbol)
        
        stats = {
            'symbol': symbol,
            'total_snapshots': len(self.snapshots.get(symbol, [])),
            'total_ofi_calculations': len(ofi_values),
            'current_ofi': ofi_values[-1] if ofi_values else None,
            'aggregated_ofi': aggregated,
            'mean_ofi': float(np.mean(ofi_values)),
            'std_ofi': float(np.std(ofi_values)),
            'min_ofi': float(np.min(ofi_values)),
            'max_ofi': float(np.max(ofi_values)),
            'positive_ofi_ratio': sum(1 for x in ofi_values if x > 0) / len(ofi_values),
            'signal': {
                'recommendation': signal.recommendation if signal else 'unknown',
                'strength': signal.signal_strength if signal else 0.0
            } if signal else None,
            'features': features
        }
        
        return stats
    
    async def simulate_market_data(
        self,
        symbol: str,
        base_price: float = 50000.0,
        n_ticks: int = 100
    ) -> None:
        """
        Simulate market data for testing.

        This method is intentionally only for local testing.
        It will NOT run when ENABLE_LIVE_TRADING=true.
        """
        import os
        if os.getenv("ENABLE_LIVE_TRADING", "false").lower() == "true":
            logger.warning(
                "OFI simulate_market_data() called while ENABLE_LIVE_TRADING=true — "
                "skipping simulation to prevent fake signals affecting live orders. "
                "Wire real CCXT order book data instead."
            )
            return

        import random
        
        price = base_price
        
        for _ in range(n_ticks):
            # Random walk
            price_change = random.gauss(0, price * 0.0001)
            price += price_change
            
            # Generate order book
            spread = price * 0.0005  # 0.05% spread
            bid_price = price - spread / 2
            ask_price = price + spread / 2
            
            bid_qty = random.uniform(0.1, 5.0)
            ask_qty = random.uniform(0.1, 5.0)
            
            await self.add_snapshot(
                symbol=symbol,
                bid_price=bid_price,
                bid_qty=bid_qty,
                ask_price=ask_price,
                ask_qty=ask_qty
            )
            
            # Small delay to simulate real-time
            import asyncio
            await asyncio.sleep(0.01)


# Global instance
ofi_calculator = OrderFlowImbalanceCalculator()
