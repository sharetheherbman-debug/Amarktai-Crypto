"""
Capital Efficiency Engine
Calculates and tracks capital efficiency (profit / time_in_trade) per bot.
Used to:
  - Exit inefficient trades (low profit relative to hold time)
  - Shift capital toward high-efficiency bots
  - Rank bots for autopilot decisions
"""

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class EfficiencyMetric:
    """Capital efficiency snapshot for a single bot"""
    bot_id: str
    profit_pct: float
    hold_seconds: float
    capital_allocated: float
    efficiency_score: float  # profit_pct / hold_hours
    rank: int = 0
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class CapitalEfficiencyEngine:
    """
    Monitors per-bot capital efficiency and flags underperforming positions.

    efficiency_score = realized_pnl_pct / hold_time_hours

    A high score means the bot generates profit quickly.
    A low/negative score means capital is idle or losing.
    """

    # Thresholds
    MIN_EFFICIENCY = 0.05   # minimum acceptable pct/hour
    IDLE_HOURS = 2.0        # hours after which a low-profit position is considered idle
    EXIT_THRESHOLD = 0.01   # if profit < 0.01% after IDLE_HOURS → suggest exit

    def __init__(self):
        self._metrics: Dict[str, EfficiencyMetric] = {}
        self._history: List[EfficiencyMetric] = []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def evaluate_bot(
        self,
        bot_id: str,
        profit_pct: float,
        hold_seconds: float,
        capital_allocated: float = 0.0,
    ) -> EfficiencyMetric:
        """
        Evaluate efficiency of a single bot / open trade.

        Args:
            bot_id: Unique bot identifier
            profit_pct: Current unrealised PnL as percentage of capital
            hold_seconds: How long the position has been open
            capital_allocated: Capital deployed in the trade (for weighting)

        Returns:
            EfficiencyMetric with computed score
        """
        hold_hours = max(hold_seconds / 3600.0, 0.001)  # avoid division by zero
        efficiency = profit_pct / hold_hours

        metric = EfficiencyMetric(
            bot_id=bot_id,
            profit_pct=profit_pct,
            hold_seconds=hold_seconds,
            capital_allocated=capital_allocated,
            efficiency_score=round(efficiency, 6),
        )
        self._metrics[bot_id] = metric
        return metric

    def evaluate_all(self, bots: List[Dict[str, Any]]) -> List[EfficiencyMetric]:
        """
        Evaluate a list of bots.  Each dict must contain:
          bot_id, profit_pct, hold_seconds  (capital_allocated optional)
        Returns sorted list (best efficiency first) with ranks.
        """
        results = []
        for b in bots:
            m = self.evaluate_bot(
                bot_id=b["bot_id"],
                profit_pct=b.get("profit_pct", 0.0),
                hold_seconds=b.get("hold_seconds", 0.0),
                capital_allocated=b.get("capital_allocated", 0.0),
            )
            results.append(m)

        # Sort by efficiency (highest first) and assign ranks
        results.sort(key=lambda m: m.efficiency_score, reverse=True)
        for idx, m in enumerate(results):
            m.rank = idx + 1
            self._metrics[m.bot_id] = m

        return results

    def should_exit(self, bot_id: str) -> bool:
        """
        Suggest whether a bot's current trade should be exited
        due to capital inefficiency.
        """
        metric = self._metrics.get(bot_id)
        if metric is None:
            return False

        hold_hours = metric.hold_seconds / 3600.0
        # If held past idle threshold with tiny profit → exit
        if hold_hours >= self.IDLE_HOURS and metric.profit_pct < self.EXIT_THRESHOLD:
            return True
        # If efficiency is deeply negative (losing money over time)
        if metric.efficiency_score < -0.1 and hold_hours > 0.5:
            return True
        return False

    def get_reallocation_suggestions(self) -> Dict[str, Any]:
        """
        Return capital reallocation suggestions based on efficiency.
        Top quartile → increase capital
        Bottom quartile → decrease / pause
        """
        if not self._metrics:
            return {"suggestions": []}

        ranked = sorted(
            self._metrics.values(),
            key=lambda m: m.efficiency_score,
            reverse=True,
        )
        n = len(ranked)
        top_q = max(1, n // 4)
        bot_q = max(1, n // 4)

        increase = [m.bot_id for m in ranked[:top_q]]
        decrease = [m.bot_id for m in ranked[-bot_q:] if m.efficiency_score < self.MIN_EFFICIENCY]

        return {
            "increase_capital": increase,
            "decrease_capital": decrease,
            "total_bots_evaluated": n,
        }

    def get_summary(self) -> Dict[str, Any]:
        """Dashboard-friendly summary of capital efficiency."""
        if not self._metrics:
            return {
                "avg_efficiency": 0.0,
                "best_bot": None,
                "worst_bot": None,
                "idle_count": 0,
                "total_evaluated": 0,
            }

        metrics = list(self._metrics.values())
        avg = sum(m.efficiency_score for m in metrics) / len(metrics)
        best = max(metrics, key=lambda m: m.efficiency_score)
        worst = min(metrics, key=lambda m: m.efficiency_score)
        idle = sum(1 for m in metrics if self.should_exit(m.bot_id))

        return {
            "avg_efficiency": round(avg, 4),
            "best_bot": {"bot_id": best.bot_id, "score": best.efficiency_score},
            "worst_bot": {"bot_id": worst.bot_id, "score": worst.efficiency_score},
            "idle_count": idle,
            "total_evaluated": len(metrics),
            "reallocation": self.get_reallocation_suggestions(),
        }

    def get_bot_metric(self, bot_id: str) -> Optional[EfficiencyMetric]:
        return self._metrics.get(bot_id)


# Global instance
capital_efficiency_engine = CapitalEfficiencyEngine()
