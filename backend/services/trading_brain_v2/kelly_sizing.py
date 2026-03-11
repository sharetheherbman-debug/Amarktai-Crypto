"""
KellySizingV2 – guarded fractional-Kelly sizing with caps.

Does NOT allow naive or over-optimized sizing.
Uses setup-family historical performance with aggressive caps.
"""
import logging
import math

logger = logging.getLogger(__name__)

# ── Guardrails ──
MAX_POSITION_PCT = {
    "normal": 5.0,
    "trend": 5.0,
    "adaptive": 5.0,
    "mean_reversion": 4.0,
    "scalper": 3.0,
}
MIN_POSITION_PCT = 1.0
KELLY_FRACTION = 0.25           # quarter-Kelly
DEFENSE_SIZE_MULTIPLIER = 0.5   # halve size in defense mode
LOW_LIQUIDITY_MULTIPLIER = 0.6  # reduce in poor liquidity
LOW_CALIBRATION_MULTIPLIER = 0.7  # reduce when calibration is poor


class KellySizingV2:
    """
    Fractional Kelly sizing with conservative guardrails.
    """

    def compute(
        self,
        bot_type: str,
        bot_equity: float,
        win_rate: float = 0.5,
        avg_win: float = 0.0,
        avg_loss: float = 0.0,
        num_trades: int = 0,
        defense_mode: bool = False,
        liquidity_score: float = 0.5,
        confidence_calibration: float = 0.5,
        regime_size_multiplier: float = 1.0,
    ) -> dict:
        """
        Compute position size as % of equity.

        Returns:
            {
                position_pct, position_quote, kelly_raw, kelly_fraction,
                applied_caps, size_source
            }
        """
        bt = (bot_type or "normal").lower()
        if bt not in MAX_POSITION_PCT:
            bt = "normal"

        safe_equity = max(bot_equity, 0.0)
        max_pct = MAX_POSITION_PCT.get(bt, 5.0)

        # ── Kelly calculation ──
        kelly_raw = self._raw_kelly(win_rate, avg_win, avg_loss)
        kelly_frac = kelly_raw * KELLY_FRACTION

        # Bootstrap: if too few trades, use conservative default
        if num_trades < 20:
            kelly_frac = min(kelly_frac, MIN_POSITION_PCT * 1.5)
            size_source = "bootstrap_conservative"
        else:
            size_source = "fractional_kelly"

        # ── Apply guardrails ──
        position_pct = max(MIN_POSITION_PCT, min(kelly_frac * 100, max_pct))

        caps_applied = []

        # Defense mode
        if defense_mode:
            position_pct *= DEFENSE_SIZE_MULTIPLIER
            caps_applied.append("defense_mode")

        # Poor liquidity
        if liquidity_score < 0.3:
            position_pct *= LOW_LIQUIDITY_MULTIPLIER
            caps_applied.append("low_liquidity")

        # Poor calibration
        if confidence_calibration < 0.3 and num_trades >= 20:
            position_pct *= LOW_CALIBRATION_MULTIPLIER
            caps_applied.append("low_calibration")

        # Regime adjustment
        if regime_size_multiplier < 1.0:
            position_pct *= regime_size_multiplier
            caps_applied.append("regime_reduced")

        # Final clamp
        position_pct = max(MIN_POSITION_PCT, min(position_pct, max_pct))
        position_quote = safe_equity * (position_pct / 100.0)

        return {
            "position_pct": round(position_pct, 4),
            "position_quote": round(position_quote, 4),
            "kelly_raw": round(kelly_raw, 6),
            "kelly_fraction": round(kelly_frac, 6),
            "applied_caps": caps_applied,
            "size_source": size_source,
            "max_position_pct": max_pct,
            "min_position_pct": MIN_POSITION_PCT,
        }

    @staticmethod
    def _raw_kelly(win_rate: float, avg_win: float, avg_loss: float) -> float:
        """
        Raw Kelly criterion: f* = (b*p - q) / b
        where b = avg_win/avg_loss, p = win_rate, q = 1-p
        """
        p = max(0.01, min(0.99, win_rate or 0.5))
        q = 1.0 - p

        if avg_loss <= 0 or avg_win <= 0:
            # Not enough data → use proportional estimate
            return max(0.0, p - q)

        b = avg_win / avg_loss  # payoff ratio
        kelly = (b * p - q) / b

        if kelly <= 0 or math.isnan(kelly) or math.isinf(kelly):
            return 0.0

        return min(kelly, 1.0)  # cap raw kelly at 100%
