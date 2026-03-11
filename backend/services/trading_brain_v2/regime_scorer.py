"""
RegimeScorerV2 – continuous regime scoring with hysteresis.

Replaces brittle regime classification with continuous scores.
Stops REGIME_UNKNOWN_BLOCK spam. Uses cooldowns and hysteresis to
reduce noisy state thrashing.
"""
import logging
import time

logger = logging.getLogger(__name__)

# ── Regime labels ──
REGIME_TRENDING_UP = "trending_up"
REGIME_TRENDING_DOWN = "trending_down"
REGIME_CONSOLIDATION = "consolidation"
REGIME_MEAN_REVERSION = "mean_reversion"
REGIME_BREAKOUT = "breakout"
REGIME_HIGH_VOL = "high_volatility"
REGIME_LOW_VOL = "low_volatility"
REGIME_AMBIGUOUS = "ambiguous"

# ── Strategy eligibility by regime ──
STRATEGY_REGIME_MAP = {
    "scalper": {REGIME_BREAKOUT, REGIME_HIGH_VOL, REGIME_CONSOLIDATION, REGIME_TRENDING_UP, REGIME_TRENDING_DOWN},
    "normal": {REGIME_TRENDING_UP, REGIME_TRENDING_DOWN, REGIME_CONSOLIDATION, REGIME_MEAN_REVERSION,
               REGIME_BREAKOUT, REGIME_LOW_VOL, REGIME_HIGH_VOL},
    "mean_reversion": {REGIME_MEAN_REVERSION, REGIME_CONSOLIDATION, REGIME_LOW_VOL},
}

# Hysteresis: must score above enter_threshold to enter a regime,
# and below exit_threshold to leave it
HYSTERESIS_ENTER = 0.55
HYSTERESIS_EXIT = 0.35
REGIME_COOLDOWN_SEC = 30  # min time between regime transitions


class RegimeScorerV2:
    """
    Continuous regime scorer with hysteresis and cooldowns.

    Produces:
        trend_score, vol_score, liquidity_score,
        regime_label, regime_confidence, regime_reason_code, regime_reason_text
    """

    def __init__(self):
        # Per-symbol state for hysteresis
        self._state: dict = {}

    def score(
        self,
        symbol: str,
        trend_pct: float = 0.0,
        volatility_pct: float = 0.0,
        spread_pct: float = 0.0,
        depth_notional: float = 0.0,
        volume_24h: float = 0.0,
    ) -> dict:
        """
        Compute continuous regime scores and classify.

        Returns render-safe dict with all required fields.
        """
        # ── Continuous scores (0.0 – 1.0) ──
        trend_score = self._compute_trend_score(trend_pct)
        vol_score = self._compute_vol_score(volatility_pct)
        liquidity_score = self._compute_liquidity_score(spread_pct, depth_notional)

        # ── Candidate regime + confidence ──
        candidate, confidence = self._classify(trend_score, vol_score, liquidity_score, volatility_pct, trend_pct)

        # ── Hysteresis: prevent thrashing ──
        prev = self._state.get(symbol, {})
        prev_label = prev.get("regime_label", REGIME_AMBIGUOUS)
        prev_ts = prev.get("ts", 0)
        now = time.time()

        if candidate != prev_label:
            if confidence < HYSTERESIS_ENTER:
                candidate = prev_label
                confidence = max(confidence, prev.get("regime_confidence", 0.0) * 0.9)
            elif (now - prev_ts) < REGIME_COOLDOWN_SEC:
                candidate = prev_label
        else:
            if confidence < HYSTERESIS_EXIT:
                candidate = REGIME_AMBIGUOUS
                confidence = confidence

        # ── Update state ──
        if candidate != prev_label:
            self._state[symbol] = {
                "regime_label": candidate,
                "regime_confidence": confidence,
                "ts": now,
            }
        else:
            self._state.setdefault(symbol, {})
            self._state[symbol]["regime_confidence"] = confidence

        # ── Reason ──
        reason_code, reason_text = self._make_reason(candidate, confidence)

        return {
            "trend_score": round(max(0.0, min(1.0, trend_score)), 4),
            "vol_score": round(max(0.0, min(1.0, vol_score)), 4),
            "liquidity_score": round(max(0.0, min(1.0, liquidity_score)), 4),
            "regime_label": candidate,
            "regime_confidence": round(max(0.0, min(1.0, confidence)), 4),
            "regime_reason_code": reason_code,
            "regime_reason_text": reason_text,
        }

    def is_eligible(self, strategy_type: str, regime_result: dict) -> dict:
        """
        Check if a strategy is eligible under the current regime.

        Instead of hard-blocking on ambiguous regimes, returns graduated
        response: approved / reduced_size / standby / blocked.
        """
        label = regime_result.get("regime_label", REGIME_AMBIGUOUS)
        confidence = regime_result.get("regime_confidence", 0.0)
        allowed = STRATEGY_REGIME_MAP.get(strategy_type, STRATEGY_REGIME_MAP["normal"])

        if label == REGIME_AMBIGUOUS:
            if strategy_type == "scalper" and confidence >= 0.3:
                return {
                    "eligible": True,
                    "action": "microstructure_only",
                    "size_multiplier": 0.5,
                    "edge_multiplier": 1.5,
                    "reason": "Regime ambiguous – scalper microstructure-only mode.",
                }
            elif confidence >= 0.4:
                return {
                    "eligible": True,
                    "action": "reduced_size",
                    "size_multiplier": 0.6,
                    "edge_multiplier": 1.3,
                    "reason": "Regime ambiguous – reduced size, stricter edge.",
                }
            else:
                return {
                    "eligible": False,
                    "action": "standby",
                    "size_multiplier": 0.0,
                    "edge_multiplier": 0.0,
                    "reason": "Regime ambiguous with low confidence – standby.",
                }

        if label not in allowed:
            return {
                "eligible": False,
                "action": "blocked",
                "size_multiplier": 0.0,
                "edge_multiplier": 0.0,
                "reason": f"Regime '{label}' not allowed for {strategy_type}.",
            }

        if confidence < 0.4:
            return {
                "eligible": True,
                "action": "reduced_size",
                "size_multiplier": 0.7,
                "edge_multiplier": 1.2,
                "reason": f"Regime '{label}' allowed but low confidence ({confidence:.0%}).",
            }

        return {
            "eligible": True,
            "action": "full",
            "size_multiplier": 1.0,
            "edge_multiplier": 1.0,
            "reason": f"Regime '{label}' approved for {strategy_type}.",
        }

    # ── Internal scoring ──

    @staticmethod
    def _compute_trend_score(trend_pct: float) -> float:
        """0 = flat, 1 = strong trend (either direction)."""
        abs_trend = abs(trend_pct or 0.0)
        if abs_trend >= 3.0:
            return 1.0
        if abs_trend >= 1.5:
            return 0.6 + (abs_trend - 1.5) / 1.5 * 0.4
        if abs_trend >= 0.5:
            return 0.2 + (abs_trend - 0.5) / 1.0 * 0.4
        return abs_trend / 0.5 * 0.2

    @staticmethod
    def _compute_vol_score(volatility_pct: float) -> float:
        """0 = dead calm, 1 = extreme volatility."""
        vol = abs(volatility_pct or 0.0)
        if vol >= 5.0:
            return 1.0
        if vol >= 2.0:
            return 0.5 + (vol - 2.0) / 3.0 * 0.5
        if vol >= 0.5:
            return 0.15 + (vol - 0.5) / 1.5 * 0.35
        return vol / 0.5 * 0.15

    @staticmethod
    def _compute_liquidity_score(spread_pct: float, depth_notional: float) -> float:
        """0 = illiquid, 1 = very liquid."""
        spread = abs(spread_pct or 0.0)
        depth = max(depth_notional or 0.0, 0.0)

        # Spread component (lower is better)
        if spread <= 0.05:
            s = 1.0
        elif spread <= 0.15:
            s = 0.7 + (0.15 - spread) / 0.10 * 0.3
        elif spread <= 0.35:
            s = 0.3 + (0.35 - spread) / 0.20 * 0.4
        else:
            s = max(0.0, 0.3 - (spread - 0.35) / 0.5 * 0.3)

        # Depth component
        if depth >= 500000:
            d = 1.0
        elif depth >= 100000:
            d = 0.5 + (depth - 100000) / 400000 * 0.5
        elif depth >= 50000:
            d = 0.3 + (depth - 50000) / 50000 * 0.2
        else:
            d = max(0.0, depth / 50000 * 0.3)

        return s * 0.5 + d * 0.5

    @staticmethod
    def _classify(trend_score, vol_score, liq_score, volatility_pct, trend_pct):
        """Determine regime label + confidence from continuous scores."""
        candidates = []

        abs_trend = abs(trend_pct or 0.0)

        # Breakout: high vol + trend starting
        if vol_score >= 0.6 and trend_score >= 0.3:
            conf = min(1.0, (vol_score + trend_score) / 2)
            candidates.append((REGIME_BREAKOUT, conf))

        # Trending
        if trend_score >= 0.5:
            label = REGIME_TRENDING_UP if (trend_pct or 0) > 0 else REGIME_TRENDING_DOWN
            conf = min(1.0, trend_score * 0.7 + (1 - vol_score) * 0.3)
            candidates.append((label, conf))

        # High volatility
        if vol_score >= 0.7:
            conf = vol_score
            candidates.append((REGIME_HIGH_VOL, conf))

        # Mean reversion: low trend, moderate vol
        if trend_score < 0.3 and 0.2 <= vol_score <= 0.6:
            conf = min(1.0, (1 - trend_score) * 0.5 + vol_score * 0.3 + liq_score * 0.2)
            candidates.append((REGIME_MEAN_REVERSION, conf))

        # Consolidation: low trend, low vol
        if trend_score < 0.25 and vol_score < 0.3:
            conf = min(1.0, (1 - trend_score) * 0.4 + (1 - vol_score) * 0.4 + liq_score * 0.2)
            candidates.append((REGIME_CONSOLIDATION, conf))

        # Low vol
        if vol_score < 0.15:
            conf = 1.0 - vol_score
            candidates.append((REGIME_LOW_VOL, conf))

        if not candidates:
            return REGIME_AMBIGUOUS, 0.3

        # Pick highest confidence candidate
        candidates.sort(key=lambda x: x[1], reverse=True)
        best_label, best_conf = candidates[0]

        # If top two candidates are very close, mark as ambiguous
        if len(candidates) >= 2 and (candidates[0][1] - candidates[1][1]) < 0.1:
            if best_conf < 0.5:
                return REGIME_AMBIGUOUS, best_conf * 0.8

        return best_label, min(1.0, best_conf)

    @staticmethod
    def _make_reason(label, confidence):
        if label == REGIME_AMBIGUOUS:
            return "REGIME_AMBIGUOUS_STANDBY", f"Regime ambiguous (confidence {confidence:.0%}) – reduced activity."
        return f"REGIME_{label.upper()}", f"Regime: {label} (confidence {confidence:.0%})"
