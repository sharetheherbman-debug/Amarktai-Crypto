"""
Strategy Tuner — UCB-lite adaptive parameter tuning for paper trading bots.

Uses Upper Confidence Bound (UCB1) logic to explore and exploit parameter
settings, adjusted per user + exchange + risk_mode.

Parameters tuned (all within strict bounds):
  take_profit_pct        : target profit per trade
  stop_loss_pct          : loss limit per trade
  min_edge_pct           : minimum expected edge to enter a trade
  time_exit_minutes      : dynamic time-based exit window (mapped to SOFT_MAX_HOLD)
  max_spread_allowed     : maximum spread % accepted at entry
  confidence_threshold   : minimum AI confidence score to open a trade

Design
------
* UCB1 score: mean_reward + C * sqrt(log(total_pulls) / arm_pulls)
* A "pull" is one trading cycle using a given parameter set.
* Reward = trade EXPECTANCY = (win_rate * avg_win) - (loss_rate * avg_loss)
            - round_trip_cost.  Never a raw win-rate metric.
* Changes are bounded: never more than STEP_PERCENT per update.
* State is persisted to DB (strategy_params_collection).
"""

from __future__ import annotations

import logging
import math
import random
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Parameter bounds and defaults per risk_mode
# ---------------------------------------------------------------------------
_PARAM_BOUNDS: Dict[str, Dict[str, Tuple[float, float, float]]] = {
    # key: (min, max, default)
    "safe": {
        "take_profit_pct":    (0.005, 0.05,  0.015),
        "stop_loss_pct":      (0.005, 0.03,  0.015),
        "min_edge_pct":       (0.001, 0.01,  0.003),
        "time_exit_minutes":  (5.0,   30.0,  15.0),
        "max_spread_allowed": (0.05,  0.50,  0.25),
        "confidence_threshold": (0.55, 0.85, 0.65),
    },
    "balanced": {
        "take_profit_pct":    (0.008, 0.08,  0.025),
        "stop_loss_pct":      (0.008, 0.05,  0.02),
        "min_edge_pct":       (0.001, 0.015, 0.004),
        "time_exit_minutes":  (5.0,   25.0,  12.0),
        "max_spread_allowed": (0.05,  0.50,  0.30),
        "confidence_threshold": (0.50, 0.80, 0.60),
    },
    "aggressive": {
        "take_profit_pct":    (0.01,  0.15,  0.04),
        "stop_loss_pct":      (0.01,  0.08,  0.03),
        "min_edge_pct":       (0.001, 0.02,  0.005),
        "time_exit_minutes":  (3.0,   20.0,  10.0),
        "max_spread_allowed": (0.05,  0.60,  0.35),
        "confidence_threshold": (0.45, 0.75, 0.55),
    },
    "risky": {
        "take_profit_pct":    (0.015, 0.20,  0.06),
        "stop_loss_pct":      (0.015, 0.10,  0.04),
        "min_edge_pct":       (0.001, 0.025, 0.006),
        "time_exit_minutes":  (3.0,   15.0,  8.0),
        "max_spread_allowed": (0.05,  0.70,  0.40),
        "confidence_threshold": (0.40, 0.70, 0.50),
    },
}
# Fallback to 'balanced' for unknown risk modes
_DEFAULT_RISK_MODE = "balanced"

# UCB exploration constant (higher → more exploration)
_UCB_C: float = 1.4

# Maximum fractional change per update cycle (10%)
_STEP_PERCENT: float = 0.10

# Minimum pulls before UCB is trusted
_MIN_PULLS: int = 3


def _bounds(risk_mode: str) -> Dict[str, Tuple[float, float, float]]:
    return _PARAM_BOUNDS.get(risk_mode.lower(), _PARAM_BOUNDS[_DEFAULT_RISK_MODE])


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


# ---------------------------------------------------------------------------
# Expectancy model
# ---------------------------------------------------------------------------

def compute_expectancy(
    wins: List[float],
    losses: List[float],
    round_trip_cost_pct: float = 0.0,
    trade_value_zar: float = 1.0,
) -> float:
    """
    Compute per-trade expectancy in ZAR.

        E = (win_rate × avg_win_zar) − (loss_rate × avg_loss_zar) − cost_zar

    Parameters
    ----------
    wins          : list of positive net-PnL values (ZAR) for winning trades
    losses        : list of non-positive net-PnL values (ZAR) for losing trades
                    (pass raw values; abs() is applied internally)
    round_trip_cost_pct : estimated total round-trip cost as a fraction of
                          trade value (fees + spread + slippage, e.g. 0.003)
    trade_value_zar     : representative trade size in ZAR used to convert
                          `round_trip_cost_pct` to an absolute cost

    Returns
    -------
    Expectancy per trade in ZAR.  Positive = system has edge.
    Negative = system loses money on average and should stand down.
    """
    total = len(wins) + len(losses)
    if total == 0:
        return 0.0

    win_rate = len(wins) / total
    loss_rate = len(losses) / total

    avg_win = sum(wins) / len(wins) if wins else 0.0
    avg_loss = abs(sum(losses) / len(losses)) if losses else 0.0

    cost_zar = round_trip_cost_pct * trade_value_zar

    return (win_rate * avg_win) - (loss_rate * avg_loss) - cost_zar


# ---------------------------------------------------------------------------
# UCB Arm state (per parameter per risk_mode)
# ---------------------------------------------------------------------------

class _UCBArmState:
    """Tracks pull count and cumulative reward for one parameter value."""

    def __init__(self, value: float) -> None:
        self.value = value
        self.pulls: int = 0
        self.total_reward: float = 0.0

    @property
    def mean_reward(self) -> float:
        return self.total_reward / self.pulls if self.pulls else 0.0

    def ucb_score(self, total_pulls: int) -> float:
        if self.pulls == 0:
            return float("inf")
        return self.mean_reward + _UCB_C * math.sqrt(math.log(total_pulls + 1) / self.pulls)

    def to_dict(self) -> dict:
        return {"value": self.value, "pulls": self.pulls, "total_reward": self.total_reward}

    @classmethod
    def from_dict(cls, d: dict) -> "_UCBArmState":
        arm = cls(d["value"])
        arm.pulls = d.get("pulls", 0)
        arm.total_reward = d.get("total_reward", 0.0)
        return arm


# ---------------------------------------------------------------------------
# StrategyTuner
# ---------------------------------------------------------------------------

class StrategyTuner:
    """
    UCB1-based strategy parameter tuner.

    For each (user_id, exchange, risk_mode) triple, maintains a small set of
    "arms" (parameter values) per tunable dimension.  Each tick of the learning
    loop provides a reward signal, which updates the arm statistics and shifts
    the active parameter set toward better-performing values.
    """

    def __init__(self) -> None:
        # Nested dict: user_id → exchange → risk_mode → param_name → list[_UCBArmState]
        self._arms: Dict[str, Dict[str, Dict[str, Dict[str, List[_UCBArmState]]]]] = {}

    # -----------------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------------

    def get_params(
        self,
        user_id: str,
        exchange: str,
        risk_mode: str,
    ) -> Dict[str, float]:
        """Return the current best-estimate parameter set for a given context."""
        bounds = _bounds(risk_mode)
        arms = self._get_arms(user_id, exchange, risk_mode)
        result: Dict[str, float] = {}
        for param, arm_list in arms.items():
            if not arm_list:
                result[param] = bounds[param][2]  # default
                continue
            # Select arm with highest UCB score
            total_pulls = sum(a.pulls for a in arm_list)
            best = max(arm_list, key=lambda a: a.ucb_score(total_pulls))
            result[param] = round(best.value, 6)
        return result

    def update(
        self,
        user_id: str,
        exchange: str,
        risk_mode: str,
        reward: float,
        used_params: Optional[Dict[str, float]] = None,
    ) -> List[Dict]:
        """
        Update arm statistics after observing a reward signal.

        reward: per-trade EXPECTANCY in ZAR, computed as:
                (win_rate × avg_win) − (loss_rate × avg_loss) − round_trip_cost.
                Positive = system has edge; negative = system loses money on average.
        used_params: the parameter set that was active during the observed period.
                     If None, the current best estimate is assumed.

        Returns list of change records for audit.
        """
        bounds = _bounds(risk_mode)
        arms = self._get_arms(user_id, exchange, risk_mode)

        if used_params is None:
            used_params = self.get_params(user_id, exchange, risk_mode)

        changes: List[Dict] = []

        for param, arm_list in arms.items():
            if param not in used_params:
                continue
            used_val = used_params[param]
            # Find the matching arm (or closest)
            arm = min(arm_list, key=lambda a: abs(a.value - used_val), default=None)
            if arm is None:
                continue
            old_val = arm.value
            arm.pulls += 1
            arm.total_reward += reward

            # After enough pulls, nudge the arm value toward exploited direction
            if arm.pulls >= _MIN_PULLS:
                direction = 1.0 if reward > 0 else -1.0
                low, high, _ = bounds[param]
                step = arm.value * _STEP_PERCENT * direction
                new_val = _clamp(arm.value + step, low, high)
                if abs(new_val - arm.value) > 1e-8:
                    arm.value = round(new_val, 6)
                    changes.append({
                        "parameter": param,
                        "old": round(old_val, 6),
                        "new": round(arm.value, 6),
                        "reward": round(reward, 4),
                        "pulls": arm.pulls,
                        "reason": "UCB1 exploitation nudge",
                    })

        return changes

    def serialize_state(
        self,
        user_id: str,
        exchange: str,
        risk_mode: str,
    ) -> dict:
        """Return serializable state for DB persistence."""
        arms = self._get_arms(user_id, exchange, risk_mode)
        return {
            "user_id": user_id,
            "exchange": exchange,
            "risk_mode": risk_mode,
            "arms": {
                param: [a.to_dict() for a in arm_list]
                for param, arm_list in arms.items()
            },
            "current_params": self.get_params(user_id, exchange, risk_mode),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

    def load_state(self, doc: dict) -> None:
        """Restore state from a DB document produced by serialize_state()."""
        uid = doc.get("user_id", "")
        exch = doc.get("exchange", "")
        rmode = doc.get("risk_mode", "")
        if not (uid and exch and rmode):
            return
        arms_data = doc.get("arms", {})
        arms = self._get_arms(uid, exch, rmode)
        for param, arm_list_data in arms_data.items():
            if param in arms:
                arms[param] = [_UCBArmState.from_dict(d) for d in arm_list_data]

    # -----------------------------------------------------------------------
    # Private helpers
    # -----------------------------------------------------------------------

    def _get_arms(
        self,
        user_id: str,
        exchange: str,
        risk_mode: str,
    ) -> Dict[str, List[_UCBArmState]]:
        """Lazily initialize arm lists for a given context."""
        uid_store = self._arms.setdefault(user_id, {})
        exch_store = uid_store.setdefault(exchange, {})
        rmode_store = exch_store.setdefault(risk_mode, {})
        bounds = _bounds(risk_mode)

        for param, (low, high, default) in bounds.items():
            if param not in rmode_store:
                # Initialise with 3 arms: default and ±step
                step = default * _STEP_PERCENT
                rmode_store[param] = [
                    _UCBArmState(_clamp(default - step, low, high)),
                    _UCBArmState(default),
                    _UCBArmState(_clamp(default + step, low, high)),
                ]
        return rmode_store


# Module-level singleton
strategy_tuner = StrategyTuner()
