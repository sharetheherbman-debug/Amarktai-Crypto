"""
TargetPolicyV2 – dynamic target computation by bot type.

Replaces trivial static targets with economics-aware, bot-type-specific
target policies. Targets scale with equity, venue, volatility, and cost.
"""
import logging

logger = logging.getLogger(__name__)

# ── Daily profit target percentages by bot type ──
DAILY_TARGET_PCT = {
    "normal": 0.8,         # 0.8% daily target
    "trend": 1.0,
    "adaptive": 0.8,
    "mean_reversion": 0.6,
    "scalper": 0.5,        # scalpers: many small wins
}

# ── Per-trade profit target as % of equity ──
TRADE_TARGET_PCT = {
    "normal": 0.4,
    "trend": 0.5,
    "adaptive": 0.4,
    "mean_reversion": 0.3,
    "scalper": 0.08,
}

# ── Maximum hold seconds by bot type (default, can be overridden) ──
MAX_HOLD_SECONDS = {
    "normal": 21600,       # 6h
    "trend": 21600,
    "adaptive": 21600,
    "mean_reversion": 10800,  # 3h
    "scalper": 300,           # 5m
}

# ── Stop-loss multipliers (fraction of take-profit distance) ──
STOP_LOSS_RATIO = {
    "normal": 0.8,         # stop = 80% of TP distance
    "trend": 0.7,
    "adaptive": 0.8,
    "mean_reversion": 1.0, # symmetric
    "scalper": 0.5,        # tight stop
}

# ── Trailing stop activation (as fraction of TP distance reached) ──
TRAILING_ACTIVATION = {
    "normal": 0.6,
    "trend": 0.5,
    "adaptive": 0.6,
    "mean_reversion": 0.7,
    "scalper": 0.4,
}


class TargetPolicyV2:
    """
    Compute dynamic targets for a trade based on bot type, equity, venue,
    all-in cost, regime, and volatility.
    """

    def compute(
        self,
        bot_type: str,
        venue: str,
        quote_currency: str,
        bot_equity: float,
        notional: float,
        all_in_cost_bps: float,
        horizon_volatility: float = 0.0,
        regime_label: str = "unknown",
        liquidity_score: float = 0.5,
        signal_confidence: float = 0.5,
        entry_price: float = 0.0,
        side: str = "buy",
    ) -> dict:
        """
        Compute target policy for a proposed or open trade.

        Returns render-safe dict with all target fields.
        """
        bt = (bot_type or "normal").lower()
        if bt not in DAILY_TARGET_PCT:
            bt = "normal"

        vc = "zar" if venue and venue.lower() == "luno" else "usdt"
        safe_equity = max(bot_equity, 1.0)
        safe_notional = max(notional, 1.0)

        # ── Daily target ──
        base_daily_pct = DAILY_TARGET_PCT.get(bt, 0.8)
        daily_pct = self._adjust_for_conditions(base_daily_pct, regime_label, liquidity_score, signal_confidence)
        daily_target_quote = safe_equity * (daily_pct / 100.0)

        # ── Trade target ──
        base_trade_pct = TRADE_TARGET_PCT.get(bt, 0.4)
        trade_pct = self._adjust_for_conditions(base_trade_pct, regime_label, liquidity_score, signal_confidence)

        # Ensure trade target covers at least 2x all-in cost
        min_trade_pct = (all_in_cost_bps / 100.0) * 2.0  # cost in % * 2
        trade_pct = max(trade_pct, min_trade_pct)

        trade_target_quote = safe_notional * (trade_pct / 100.0)

        # ── Enforce minimum absolute targets ──
        min_abs_trade = self._min_absolute_target(bt, vc)
        trade_target_quote = max(trade_target_quote, min_abs_trade)
        # Recalculate pct from clamped target
        trade_pct = (trade_target_quote / safe_notional) * 100.0

        # ── Price targets ──
        tp_pct = trade_pct / 100.0
        sl_ratio = STOP_LOSS_RATIO.get(bt, 0.8)
        sl_pct = tp_pct * sl_ratio

        if entry_price > 0:
            if side == "buy":
                take_profit_price = round(entry_price * (1.0 + tp_pct), 8)
                stop_loss_price = round(entry_price * (1.0 - sl_pct), 8)
            else:
                take_profit_price = round(entry_price * (1.0 - tp_pct), 8)
                stop_loss_price = round(entry_price * (1.0 + sl_pct), 8)
        else:
            take_profit_price = 0.0
            stop_loss_price = 0.0

        # ── Trailing stop ──
        trail_activation = TRAILING_ACTIVATION.get(bt, 0.6)
        trailing_config = {
            "enabled": bt in ("normal", "trend", "adaptive", "scalper"),
            "activation_pct": round(tp_pct * trail_activation * 100, 4),
            "trail_pct": round(sl_pct * 0.5 * 100, 4),
        }

        # ── Max hold ──
        max_hold = MAX_HOLD_SECONDS.get(bt, 21600)
        time_stop_reasoning = self._time_reasoning(bt, max_hold, regime_label)

        return {
            "daily_profit_target_quote": round(daily_target_quote, 4),
            "trade_profit_target_quote": round(trade_target_quote, 4),
            "daily_target_pct": round(daily_pct, 4),
            "trade_target_pct": round(trade_pct, 4),
            "take_profit_price": take_profit_price,
            "stop_loss_price": stop_loss_price,
            "trailing_stop_config": trailing_config,
            "max_hold_seconds": max_hold,
            "time_stop_reasoning": time_stop_reasoning,
            "target_source": "target_policy_v2",
            "bot_type": bt,
            "venue_class": vc,
        }

    @staticmethod
    def _adjust_for_conditions(base_pct, regime_label, liquidity_score, confidence):
        """Adjust target % based on market conditions."""
        pct = base_pct

        # Regime adjustments
        if regime_label in ("breakout", "high_volatility"):
            pct *= 1.3  # opportunity in vol
        elif regime_label == "low_volatility":
            pct *= 0.7  # lower expectations
        elif regime_label == "ambiguous":
            pct *= 0.8

        # Liquidity: poor liquidity → lower targets (harder to exit)
        if liquidity_score < 0.3:
            pct *= 0.7
        elif liquidity_score < 0.5:
            pct *= 0.85

        # Confidence: lower confidence → more conservative
        if confidence < 0.5:
            pct *= 0.8
        elif confidence > 0.8:
            pct *= 1.1

        return max(pct, base_pct * 0.5)  # floor at 50% of base

    @staticmethod
    def _min_absolute_target(bot_type, venue_class):
        """Minimum absolute profit target in quote currency."""
        if venue_class == "zar":
            mins = {"normal": 5.0, "trend": 8.0, "adaptive": 5.0,
                    "mean_reversion": 4.0, "scalper": 2.0}
        else:
            mins = {"normal": 0.50, "trend": 0.80, "adaptive": 0.50,
                    "mean_reversion": 0.40, "scalper": 0.20}
        return mins.get(bot_type, mins.get("normal", 5.0))

    @staticmethod
    def _time_reasoning(bot_type, max_hold, regime_label):
        if bot_type == "scalper":
            return f"Scalper: hard {max_hold}s cap. Rapid exit on stagnation."
        if regime_label in ("breakout", "high_volatility"):
            return f"{bot_type}: {max_hold}s cap. Volatile regime, tighter time management."
        return f"{bot_type}: {max_hold}s standard hold cap for {regime_label} regime."
