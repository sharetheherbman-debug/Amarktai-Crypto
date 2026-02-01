"""
Edge Gate - Expected Value (EV) After Costs Filter
ToS-Safe: Rejects trades with insufficient edge after fees, spread, slippage

NO proxy rotation, IP masking, fingerprint obfuscation, noise trades, wash trades, 
detection avoidance, or latency arbitrage.

Pure mathematical analysis of trade profitability.
"""

import logging
from typing import Dict, Optional
from enum import Enum
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class EdgeGateReason(str, Enum):
    """Reasons for edge gate rejection"""
    EDGE_TOO_LOW = "edge_too_low"
    SPREAD_TOO_WIDE = "spread_too_wide"
    VOL_TOO_HIGH = "vol_too_high"
    EXEC_QUALITY_RED = "exec_quality_red"
    FEES_TOO_HIGH = "fees_too_high"
    SLIPPAGE_TOO_HIGH = "slippage_too_high"


class EdgeGate:
    """
    Edge Gate: Reject trades where Expected Value < Total Costs
    
    Formula: EV = (win_rate * avg_win) - (loss_rate * avg_loss) - fees - spread - slippage - buffer
    """
    
    def __init__(self):
        self.min_edge_bps = 10  # Minimum 10 basis points edge
        self.safety_margin_bps = 5  # Additional 5 bps safety buffer
        self.slippage_buffer_bps = 10  # 10 bps slippage assumption
        
    def evaluate_trade(
        self,
        pair: str,
        exchange: str,
        trade_type: str,
        entry_price: float,
        exit_price: float,
        amount: float,
        win_rate: Optional[float] = None,
        avg_win: Optional[float] = None,
        avg_loss: Optional[float] = None,
        spread_bps: Optional[float] = None,
        volatility: Optional[float] = None,
        execution_quality_score: Optional[float] = None
    ) -> Dict:
        """
        Evaluate if trade has sufficient edge after costs
        
        Args:
            pair: Trading pair
            exchange: Exchange name
            trade_type: 'buy' or 'sell'
            entry_price: Entry price
            exit_price: Expected exit price
            amount: Trade amount
            win_rate: Historical win rate (0-1)
            avg_win: Average win in bps
            avg_loss: Average loss in bps
            spread_bps: Bid-ask spread in basis points
            volatility: Current volatility (0-1)
            execution_quality_score: Recent execution quality (0-1, 1=best)
            
        Returns:
            Dict with pass/fail and reason
        """
        try:
            # Calculate raw edge (before costs)
            if trade_type == 'buy':
                raw_edge_bps = ((exit_price - entry_price) / entry_price) * 10000
            else:  # sell
                raw_edge_bps = ((entry_price - exit_price) / exit_price) * 10000
            
            # Get exchange fees
            maker_fee_bps, taker_fee_bps = self._get_exchange_fees(exchange)
            fee_bps = taker_fee_bps  # Assume taker for conservative estimate
            
            # Estimate spread cost
            if spread_bps is None:
                spread_bps = self._estimate_spread(pair, exchange)
            
            # Calculate total costs
            total_costs_bps = fee_bps + spread_bps + self.slippage_buffer_bps + self.safety_margin_bps
            
            # Calculate net edge
            net_edge_bps = raw_edge_bps - total_costs_bps
            
            # Check if edge meets minimum
            if net_edge_bps < self.min_edge_bps:
                return {
                    "pass": False,
                    "reason": EdgeGateReason.EDGE_TOO_LOW,
                    "message": f"Insufficient edge: {net_edge_bps:.2f} bps < {self.min_edge_bps} bps minimum",
                    "raw_edge_bps": round(raw_edge_bps, 2),
                    "total_costs_bps": round(total_costs_bps, 2),
                    "net_edge_bps": round(net_edge_bps, 2),
                    "details": {
                        "fee_bps": round(fee_bps, 2),
                        "spread_bps": round(spread_bps, 2),
                        "slippage_buffer_bps": self.slippage_buffer_bps,
                        "safety_margin_bps": self.safety_margin_bps
                    }
                }
            
            # Check spread
            if spread_bps > 50:  # 50 bps = 0.5%
                return {
                    "pass": False,
                    "reason": EdgeGateReason.SPREAD_TOO_WIDE,
                    "message": f"Spread too wide: {spread_bps:.2f} bps > 50 bps",
                    "spread_bps": round(spread_bps, 2)
                }
            
            # Check volatility
            if volatility and volatility > 0.05:  # 5% threshold
                return {
                    "pass": False,
                    "reason": EdgeGateReason.VOL_TOO_HIGH,
                    "message": f"Volatility too high: {volatility*100:.2f}% > 5%",
                    "volatility": round(volatility, 4)
                }
            
            # Check execution quality
            if execution_quality_score and execution_quality_score < 0.7:  # 70% threshold
                return {
                    "pass": False,
                    "reason": EdgeGateReason.EXEC_QUALITY_RED,
                    "message": f"Poor execution quality: {execution_quality_score*100:.1f}% < 70%",
                    "execution_quality_score": round(execution_quality_score, 2)
                }
            
            # Trade passes all gates
            return {
                "pass": True,
                "message": "Trade has sufficient edge after costs",
                "raw_edge_bps": round(raw_edge_bps, 2),
                "total_costs_bps": round(total_costs_bps, 2),
                "net_edge_bps": round(net_edge_bps, 2),
                "details": {
                    "fee_bps": round(fee_bps, 2),
                    "spread_bps": round(spread_bps, 2),
                    "slippage_buffer_bps": self.slippage_buffer_bps,
                    "safety_margin_bps": self.safety_margin_bps
                }
            }
            
        except Exception as e:
            logger.error(f"Edge gate evaluation failed: {e}")
            return {
                "pass": False,
                "reason": "EVALUATION_ERROR",
                "message": str(e)
            }
    
    def _get_exchange_fees(self, exchange: str) -> tuple:
        """
        Get maker/taker fees for exchange (basis points)
        
        Returns:
            (maker_fee_bps, taker_fee_bps)
        """
        # Fee schedules (in basis points)
        fees = {
            "luno": (0, 0),  # Zero fees for Luno (ZAR pairs)
            "binance": (10, 10),  # 0.1% maker/taker
            "kucoin": (10, 10),  # 0.1% maker/taker
            "bybit": (2, 6),  # 0.02% maker, 0.06% taker
            "kraken": (16, 26),  # 0.16% maker, 0.26% taker
            "bitget": (10, 10),  # 0.1% maker/taker
            "gateio": (15, 15),  # 0.15% maker/taker
        }
        
        return fees.get(exchange.lower(), (20, 30))  # Conservative default
    
    def _estimate_spread(self, pair: str, exchange: str) -> float:
        """
        Estimate bid-ask spread in basis points
        
        Conservative estimates based on typical spreads
        """
        # Spread estimates by exchange and pair type
        if "BTC" in pair or "ETH" in pair:
            # Major pairs - tighter spreads
            spreads = {
                "luno": 5,
                "binance": 2,
                "kucoin": 3,
                "bybit": 2,
                "kraken": 4,
                "bitget": 3,
                "gateio": 4,
            }
            return spreads.get(exchange.lower(), 5)
        else:
            # Altcoin pairs - wider spreads
            spreads = {
                "luno": 10,
                "binance": 5,
                "kucoin": 8,
                "bybit": 5,
                "kraken": 10,
                "bitget": 8,
                "gateio": 10,
            }
            return spreads.get(exchange.lower(), 15)
    
    def calculate_expected_value(
        self,
        win_rate: float,
        avg_win_bps: float,
        avg_loss_bps: float,
        fee_bps: float,
        spread_bps: float
    ) -> Dict:
        """
        Calculate Expected Value per trade
        
        EV = (P(win) * avg_win) - (P(loss) * avg_loss) - fees - spread
        
        Args:
            win_rate: Probability of winning (0-1)
            avg_win_bps: Average win in basis points
            avg_loss_bps: Average loss in basis points (positive number)
            fee_bps: Trading fees in basis points
            spread_bps: Bid-ask spread cost in basis points
            
        Returns:
            Dict with EV analysis
        """
        loss_rate = 1 - win_rate
        
        gross_ev = (win_rate * avg_win_bps) - (loss_rate * avg_loss_bps)
        costs = fee_bps + spread_bps + self.slippage_buffer_bps + self.safety_margin_bps
        net_ev = gross_ev - costs
        
        return {
            "gross_ev_bps": round(gross_ev, 2),
            "total_costs_bps": round(costs, 2),
            "net_ev_bps": round(net_ev, 2),
            "positive_ev": net_ev > 0,
            "meets_minimum": net_ev >= self.min_edge_bps,
            "details": {
                "win_rate": round(win_rate, 3),
                "loss_rate": round(loss_rate, 3),
                "avg_win_bps": round(avg_win_bps, 2),
                "avg_loss_bps": round(avg_loss_bps, 2),
                "fee_bps": round(fee_bps, 2),
                "spread_bps": round(spread_bps, 2),
                "slippage_buffer_bps": self.slippage_buffer_bps,
                "safety_margin_bps": self.safety_margin_bps
            }
        }
    
    def update_thresholds(
        self,
        min_edge_bps: Optional[int] = None,
        safety_margin_bps: Optional[int] = None,
        slippage_buffer_bps: Optional[int] = None
    ):
        """Update edge gate thresholds"""
        if min_edge_bps is not None:
            self.min_edge_bps = min_edge_bps
        if safety_margin_bps is not None:
            self.safety_margin_bps = safety_margin_bps
        if slippage_buffer_bps is not None:
            self.slippage_buffer_bps = slippage_buffer_bps
        
        logger.info(f"Edge gate thresholds updated: min_edge={self.min_edge_bps}bps, "
                   f"safety={self.safety_margin_bps}bps, slippage={self.slippage_buffer_bps}bps")


# Global instance
edge_gate = EdgeGate()
