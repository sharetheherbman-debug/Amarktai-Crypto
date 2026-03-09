"""
Bot Genetics Module
- Spawn child bots from successful parents
- Inherit strategy type with randomised parameters
- Population management to prevent explosion
"""

import logging
import random
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Defaults
MAX_POPULATION = 50          # hard cap on total genetic children
MUTATION_RANGE = 0.20        # ±20 % parameter mutation
MIN_WIN_RATE = 0.55          # parent must exceed this to reproduce
MIN_TRADES = 10              # parent must have at least this many trades


class BotGenetics:
    """
    Manages genetic mutation and child bot spawning.

    A *parent* bot that meets fitness criteria can spawn a *child* that
    inherits the parent's strategy type but mutates numeric parameters
    (lot size, stop‑loss %, take‑profit %, entry conditions).
    """

    def __init__(
        self,
        max_population: int = MAX_POPULATION,
        mutation_range: float = MUTATION_RANGE,
        min_win_rate: float = MIN_WIN_RATE,
        min_trades: int = MIN_TRADES,
    ):
        self.max_population = max_population
        self.mutation_range = mutation_range
        self.min_win_rate = min_win_rate
        self.min_trades = min_trades
        # In‑memory registry of spawned children (id → parent_id)
        self._children: Dict[str, str] = {}

    # ------------------------------------------------------------------
    # Fitness check
    # ------------------------------------------------------------------

    def is_fit_parent(self, bot: Dict) -> bool:
        """
        Return True if *bot* qualifies as a parent for reproduction.

        Criteria:
            - trades_count >= min_trades
            - win_rate >= min_win_rate
            - total_profit > 0
            - status == 'active'
        """
        trades = bot.get("trades_count", 0)
        if trades < self.min_trades:
            return False

        wins = bot.get("win_count", 0)
        win_rate = wins / trades if trades > 0 else 0
        if win_rate < self.min_win_rate:
            return False

        if bot.get("total_profit", 0) <= 0:
            return False

        if bot.get("status") != "active":
            return False

        return True

    # ------------------------------------------------------------------
    # Mutation
    # ------------------------------------------------------------------

    def _mutate_value(self, value: float, floor: float = 0.0) -> float:
        """Apply random mutation within ± mutation_range."""
        factor = 1.0 + random.uniform(-self.mutation_range, self.mutation_range)
        return max(floor, round(value * factor, 4))

    def mutate_params(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Return a mutated copy of *params*.
        Only numeric values are mutated; non-numeric values are inherited.
        """
        mutated: Dict[str, Any] = {}
        for key, val in params.items():
            if isinstance(val, (int, float)):
                mutated[key] = self._mutate_value(float(val))
                if isinstance(val, int):
                    mutated[key] = int(round(mutated[key]))
            else:
                mutated[key] = val
        return mutated

    # ------------------------------------------------------------------
    # Spawning
    # ------------------------------------------------------------------

    def spawn_child(self, parent_bot: Dict, capital_fraction: float = 0.5) -> Optional[Dict]:
        """
        Create a child bot definition from *parent_bot*.

        Args:
            parent_bot: The parent bot document.
            capital_fraction: Fraction of parent's current capital to assign.

        Returns:
            A new bot dict ready for insertion, or None if population cap
            is reached or parent is unfit.
        """
        if len(self._children) >= self.max_population:
            logger.warning("Bot genetics population cap (%d) reached", self.max_population)
            return None

        if not self.is_fit_parent(parent_bot):
            logger.info(
                "Bot %s does not meet fitness criteria for reproduction",
                parent_bot.get("id", "?"),
            )
            return None

        parent_id = parent_bot.get("id", str(uuid.uuid4()))
        child_id = f"gen_{parent_id}_{uuid.uuid4().hex[:8]}"

        # Mutate strategy parameters
        parent_params = parent_bot.get("strategy_params", {})
        child_params = self.mutate_params(parent_params)

        # Mutate risk parameters
        child_stop_loss = self._mutate_value(
            parent_bot.get("stop_loss_pct", 2.0), floor=0.5
        )
        child_take_profit = self._mutate_value(
            parent_bot.get("take_profit_pct", 5.0), floor=1.0
        )

        # Compute capital
        parent_capital = parent_bot.get("current_capital", 0)
        child_capital = round(parent_capital * capital_fraction, 2)

        child_bot = {
            "id": child_id,
            "name": f"Child of {parent_bot.get('name', parent_id)}",
            "user_id": parent_bot.get("user_id"),
            "exchange": parent_bot.get("exchange"),
            "pair": parent_bot.get("pair", "BTC/ZAR"),
            "bot_type": parent_bot.get("bot_type", "normal"),
            "strategy": parent_bot.get("strategy", "trend_following"),
            "strategy_params": child_params,
            "stop_loss_pct": child_stop_loss,
            "take_profit_pct": child_take_profit,
            "initial_capital": child_capital,
            "current_capital": child_capital,
            "total_profit": 0,
            "trades_count": 0,
            "win_count": 0,
            "loss_count": 0,
            "status": "paused",  # start paused; operator must activate
            "trading_mode": parent_bot.get("trading_mode", "paper"),
            "parent_id": parent_id,
            "generation": parent_bot.get("generation", 0) + 1,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "genetics": {
                "parent_id": parent_id,
                "mutation_range": self.mutation_range,
                "parent_win_rate": parent_bot.get("win_count", 0) / max(parent_bot.get("trades_count", 1), 1),
                "parent_profit": parent_bot.get("total_profit", 0),
            },
        }

        self._children[child_id] = parent_id
        logger.info(
            "🧬 Spawned child bot %s from parent %s (gen %d, capital %.2f)",
            child_id,
            parent_id,
            child_bot["generation"],
            child_capital,
        )
        return child_bot

    # ------------------------------------------------------------------
    # Population queries
    # ------------------------------------------------------------------

    def get_population(self) -> Dict[str, str]:
        """Return dict of child_id → parent_id."""
        return dict(self._children)

    def population_count(self) -> int:
        return len(self._children)

    def get_lineage(self, child_id: str) -> List[str]:
        """Return lineage from child → … → root parent."""
        lineage = [child_id]
        current = child_id
        while current in self._children:
            parent = self._children[current]
            lineage.append(parent)
            current = parent
        return lineage


# ---------------------------------------------------------------------------
# Global singleton
# ---------------------------------------------------------------------------
bot_genetics = BotGenetics()
