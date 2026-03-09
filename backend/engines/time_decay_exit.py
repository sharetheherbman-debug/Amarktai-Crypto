"""
Time Decay Exit Engine
Implements adaptive time-based exit logic:
  - If time_in_trade > expected_hold_time AND profit < target → exit
  - Scalper expected hold: 10s – 5min
  - Normal bot expected hold: 5min – 2h
  - Adaptive targets shrink as hold time increases (urgency escalation)
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class BotClass(str, Enum):
    SCALPER = "scalper"
    NORMAL = "normal"


@dataclass
class TimeDecayResult:
    """Result of time-decay evaluation for a single position"""
    bot_id: str
    bot_class: str
    hold_seconds: float
    expected_hold_seconds: float
    profit_pct: float
    decay_factor: float       # 0-1, how much of the target window has elapsed
    adjusted_target_pct: float  # reduced profit target based on decay
    should_exit: bool
    exit_reason: str = ""


# Default hold-time windows (seconds)
HOLD_WINDOWS = {
    BotClass.SCALPER: {"min": 10, "expected": 120, "max": 300},       # 10s - 2min expected - 5min max
    BotClass.NORMAL: {"min": 300, "expected": 3600, "max": 7200},     # 5min - 1h expected - 2h max
}

# Default profit targets
PROFIT_TARGETS = {
    BotClass.SCALPER: {"min": 0.002, "target": 0.005, "max": 0.008},  # 0.2% - 0.5% - 0.8%
    BotClass.NORMAL: {"min": 0.005, "target": 0.015, "max": 0.03},    # 0.5% - 1.5% - 3%
}


class TimeDecayExitEngine:
    """
    Evaluates whether a position should be exited based on time decay.

    Core rule:
        decay_factor = clamp(hold_time / expected_hold_time, 0, 1)
        adjusted_target = target * (1 - 0.5 * decay_factor)

        if hold_time > expected AND profit < adjusted_target → exit
        if hold_time > max_hold → force exit regardless
    """

    def __init__(self):
        self._config: Dict[str, Dict] = {}

    def evaluate(
        self,
        bot_id: str,
        bot_class: str,
        hold_seconds: float,
        profit_pct: float,
        custom_expected_hold: Optional[float] = None,
        custom_target_pct: Optional[float] = None,
    ) -> TimeDecayResult:
        """
        Evaluate time decay for a position.

        Args:
            bot_id: Bot identifier
            bot_class: 'scalper' or 'normal'
            hold_seconds: Current hold duration
            profit_pct: Current unrealized PnL as fraction (0.01 = 1%)
            custom_expected_hold: Override default expected hold
            custom_target_pct: Override default profit target

        Returns:
            TimeDecayResult with exit recommendation
        """
        bc = BotClass.SCALPER if bot_class == "scalper" else BotClass.NORMAL

        windows = HOLD_WINDOWS[bc]
        targets = PROFIT_TARGETS[bc]

        expected = custom_expected_hold or windows["expected"]
        max_hold = windows["max"]
        target = custom_target_pct or targets["target"]

        # Calculate decay factor (0 at start, 1 at expected hold)
        decay = min(1.0, hold_seconds / expected) if expected > 0 else 1.0

        # Adjusted target: shrinks by up to 50% as decay approaches 1.0
        adjusted_target = target * (1.0 - 0.5 * decay)

        should_exit = False
        reason = ""

        # Rule 1: Hard time limit exceeded → force exit
        if hold_seconds >= max_hold:
            should_exit = True
            reason = f"max_hold_exceeded ({hold_seconds:.0f}s >= {max_hold}s)"

        # Rule 2: Past expected hold AND profit below adjusted target
        elif hold_seconds >= expected and profit_pct < adjusted_target:
            should_exit = True
            reason = (
                f"time_decay_exit (hold={hold_seconds:.0f}s, expected={expected:.0f}s, "
                f"pnl={profit_pct:.4f}, adj_target={adjusted_target:.4f})"
            )

        # Rule 3: Deeply past expected hold with negative profit
        elif hold_seconds >= expected * 1.5 and profit_pct <= 0:
            should_exit = True
            reason = f"extended_hold_no_profit ({hold_seconds:.0f}s, pnl={profit_pct:.4f})"

        return TimeDecayResult(
            bot_id=bot_id,
            bot_class=bot_class,
            hold_seconds=hold_seconds,
            expected_hold_seconds=expected,
            profit_pct=profit_pct,
            decay_factor=round(decay, 4),
            adjusted_target_pct=round(adjusted_target, 6),
            should_exit=should_exit,
            exit_reason=reason,
        )

    def evaluate_batch(self, positions: list[Dict[str, Any]]) -> list[TimeDecayResult]:
        """
        Evaluate multiple positions.

        Each dict needs: bot_id, bot_class, hold_seconds, profit_pct
        """
        return [
            self.evaluate(
                bot_id=p["bot_id"],
                bot_class=p.get("bot_class", "normal"),
                hold_seconds=p.get("hold_seconds", 0),
                profit_pct=p.get("profit_pct", 0),
            )
            for p in positions
        ]

    def get_summary(self, positions: list[Dict[str, Any]]) -> Dict[str, Any]:
        """Dashboard-friendly summary."""
        results = self.evaluate_batch(positions)
        exit_count = sum(1 for r in results if r.should_exit)
        avg_decay = (
            sum(r.decay_factor for r in results) / len(results) if results else 0
        )
        return {
            "total_positions": len(results),
            "exit_recommended": exit_count,
            "avg_decay_factor": round(avg_decay, 3),
            "positions": [
                {
                    "bot_id": r.bot_id,
                    "bot_class": r.bot_class,
                    "hold_seconds": r.hold_seconds,
                    "decay_factor": r.decay_factor,
                    "should_exit": r.should_exit,
                    "exit_reason": r.exit_reason,
                }
                for r in results
                if r.should_exit
            ],
        }


# Global instance
time_decay_exit_engine = TimeDecayExitEngine()
