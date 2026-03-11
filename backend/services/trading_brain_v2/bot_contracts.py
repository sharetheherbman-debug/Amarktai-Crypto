"""
BotBehavioralContracts – explicit behavioral rules per bot type.

Each bot type has a distinct trading contract:
- Normal/Adaptive/Trend: larger targets, slower cadence, bigger edge
- Mean Reversion: medium hold, range-aware, breakout protection
- Scalper: short holds, tight targets, microstructure-dependent
"""
import logging
import time

logger = logging.getLogger(__name__)


class _BotContract:
    """Base contract with common defaults."""
    bot_type = "normal"
    order_mode_preference = "maker"
    min_net_edge_bps = 15.0
    min_abs_profit_zar = 5.0
    min_abs_profit_usdt = 0.50
    max_hold_seconds = 21600
    max_trades_per_day = 10
    min_confidence = 0.65
    loss_streak_cooldown_trades = 4
    loss_streak_cooldown_seconds = 1800
    daily_trade_budget = 50
    coverage_throttle_seconds = 300
    time_budget_exit_pct = 0.75  # exit if no progress by 75% of time budget
    maker_urgency_override = False


class TrendAdaptiveContract(_BotContract):
    bot_type = "trend"
    order_mode_preference = "maker"
    min_net_edge_bps = 18.0
    min_abs_profit_zar = 8.0
    min_abs_profit_usdt = 0.80
    max_hold_seconds = 21600
    max_trades_per_day = 8
    min_confidence = 0.68
    loss_streak_cooldown_trades = 3
    loss_streak_cooldown_seconds = 3600
    daily_trade_budget = 30
    coverage_throttle_seconds = 600
    time_budget_exit_pct = 0.7
    maker_urgency_override = True  # switch to taker on breakout urgency


class MeanReversionContract(_BotContract):
    bot_type = "mean_reversion"
    order_mode_preference = "maker"
    min_net_edge_bps = 12.0
    min_abs_profit_zar = 4.0
    min_abs_profit_usdt = 0.40
    max_hold_seconds = 10800
    max_trades_per_day = 12
    min_confidence = 0.65
    loss_streak_cooldown_trades = 3
    loss_streak_cooldown_seconds = 2400
    daily_trade_budget = 40
    coverage_throttle_seconds = 300
    time_budget_exit_pct = 0.7


class ScalperContract(_BotContract):
    bot_type = "scalper"
    order_mode_preference = "taker"  # momentum burst default
    min_net_edge_bps = 8.0
    min_abs_profit_zar = 2.0
    min_abs_profit_usdt = 0.20
    max_hold_seconds = 300
    max_trades_per_day = 50
    min_confidence = 0.72
    loss_streak_cooldown_trades = 3
    loss_streak_cooldown_seconds = 600
    daily_trade_budget = 100
    coverage_throttle_seconds = 30
    time_budget_exit_pct = 0.6
    # Scalper-specific
    stagnation_exit_seconds = 120
    spread_max_bps = 50
    min_ev_bps = 10
    scalper_modes = ["taker_momentum", "maker_spread_capture"]


# ── Registry ──
BOT_CONTRACTS = {
    "normal": _BotContract,
    "trend": TrendAdaptiveContract,
    "adaptive": TrendAdaptiveContract,
    "mean_reversion": MeanReversionContract,
    "scalper": ScalperContract,
}


class BotBehavioralContracts:
    """
    Manages bot-type behavioral contracts and scalper-specific controls.
    """

    def __init__(self):
        # Per-bot loss tracking: {bot_id: {"losses": int, "last_loss_ts": float, "trades_today": int, "day": str}}
        self._bot_state: dict = {}

    def get_contract(self, bot_type: str):
        """Return the contract class for a bot type."""
        bt = (bot_type or "normal").lower()
        return BOT_CONTRACTS.get(bt, _BotContract)

    def check_scalper_readiness(
        self,
        bot_id: str,
        spread_bps: float,
        liquidity_score: float,
        regime_label: str,
        regime_confidence: float,
    ) -> dict:
        """
        Check if scalper-specific conditions are met.
        Returns {ready: bool, reason_code, reason_text, mode}.
        """
        contract = ScalperContract

        # Spread check
        if spread_bps > contract.spread_max_bps:
            return {
                "ready": False,
                "reason_code": "SPREAD_TOO_WIDE",
                "reason_text": f"Spread {spread_bps:.1f} bps > max {contract.spread_max_bps} bps for scalper.",
                "mode": None,
            }

        # Liquidity
        if liquidity_score < 0.3:
            return {
                "ready": False,
                "reason_code": "DEPTH_TOO_THIN",
                "reason_text": f"Liquidity score {liquidity_score:.2f} too low for scalper.",
                "mode": None,
            }

        # Loss streak cooldown
        state = self._bot_state.get(bot_id, {})
        consecutive_losses = state.get("consecutive_losses", 0)
        last_loss_ts = state.get("last_loss_ts", 0)
        if consecutive_losses >= contract.loss_streak_cooldown_trades:
            cooldown_remaining = (last_loss_ts + contract.loss_streak_cooldown_seconds) - time.time()
            if cooldown_remaining > 0:
                return {
                    "ready": False,
                    "reason_code": "SCALPER_LOSS_STREAK_COOLDOWN",
                    "reason_text": f"Loss streak cooldown: {int(cooldown_remaining)}s remaining.",
                    "mode": None,
                }

        # Daily budget
        today = time.strftime("%Y-%m-%d")
        trades_today = state.get("trades_today", 0) if state.get("day") == today else 0
        if trades_today >= contract.daily_trade_budget:
            return {
                "ready": False,
                "reason_code": "SCALPER_DAILY_BUDGET_EXHAUSTED",
                "reason_text": f"Daily budget exhausted ({trades_today}/{contract.daily_trade_budget}).",
                "mode": None,
            }

        # Determine mode
        if regime_label in ("breakout", "high_volatility") and regime_confidence > 0.5:
            mode = "taker_momentum"
        elif regime_label in ("consolidation", "low_volatility") and spread_bps < 25:
            mode = "maker_spread_capture"
        else:
            mode = "taker_momentum"  # default

        return {
            "ready": True,
            "reason_code": "SCALPER_READY",
            "reason_text": f"Scalper ready in {mode} mode.",
            "mode": mode,
        }

    def record_trade_result(self, bot_id: str, bot_type: str, won: bool):
        """Track wins/losses for behavioral controls."""
        today = time.strftime("%Y-%m-%d")
        state = self._bot_state.get(bot_id, {"consecutive_losses": 0, "trades_today": 0, "day": today})

        if state.get("day") != today:
            state["trades_today"] = 0
            state["day"] = today

        state["trades_today"] = state.get("trades_today", 0) + 1

        if won:
            state["consecutive_losses"] = 0
        else:
            state["consecutive_losses"] = state.get("consecutive_losses", 0) + 1
            state["last_loss_ts"] = time.time()

        self._bot_state[bot_id] = state

    def check_coverage_throttle(self, bot_id: str, bot_type: str) -> dict:
        """Check if bot is within coverage throttle timing."""
        contract = self.get_contract(bot_type)
        state = self._bot_state.get(bot_id, {})
        last_trade_ts = state.get("last_trade_ts", 0)
        elapsed = time.time() - last_trade_ts

        if elapsed < contract.coverage_throttle_seconds:
            return {
                "throttled": True,
                "reason_code": "SCALPER_COVERAGE_THROTTLE" if bot_type == "scalper" else "COVERAGE_THROTTLE",
                "wait_seconds": int(contract.coverage_throttle_seconds - elapsed),
            }
        return {"throttled": False, "reason_code": None, "wait_seconds": 0}

    def record_trade_entry(self, bot_id: str):
        """Record that a trade was entered (for throttle tracking)."""
        state = self._bot_state.setdefault(bot_id, {})
        state["last_trade_ts"] = time.time()
