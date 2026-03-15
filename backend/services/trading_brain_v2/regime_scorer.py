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
# Scalpers thrive in quiet/sideways markets (tight spreads, range-bound price).
# They are blocked during strong trends and high-volatility breakouts where
# momentum overwhelms microstructure edge.
STRATEGY_REGIME_MAP = {
    "scalper": {REGIME_CONSOLIDATION, REGIME_LOW_VOL, REGIME_MEAN_REVERSION},
    "normal": {REGIME_TRENDING_UP, REGIME_TRENDING_DOWN, REGIME_CONSOLIDATION, REGIME_MEAN_REVERSION,
               REGIME_BREAKOUT, REGIME_LOW_VOL, REGIME_HIGH_VOL},
    "mean_reversion": {REGIME_MEAN_REVERSION, REGIME_CONSOLIDATION, REGIME_LOW_VOL},
}

# Hysteresis: must score above enter_threshold to enter a regime,
# and below exit_threshold to leave it
HYSTERESIS_ENTER = 0.55
HYSTERESIS_EXIT = 0.35
REGIME_COOLDOWN_SEC = 30  # min time between regime transitions

# ── Scalper-specific microstructure thresholds ────────────────────────────────
# These are separate from normal-bot regime logic so that scalper admission
# can be tuned independently.
SCALPER_MAX_SPREAD_PCT = 0.20          # block if spread >= 0.20%
SCALPER_MIN_DEPTH_NOTIONAL = 20_000   # block if depth < $20k / R20k equivalent
SCALPER_MIN_LIQUIDITY_SCORE = 0.40    # block below this liquidity score
SCALPER_MAX_VOL_SCORE = 0.65          # block in chaotic high-volatility
SCALPER_MAX_TREND_SCORE = 0.55        # block if momentum too strong (trend-dominant)


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


class ScalperAdmissionPolicy:
    """
    Dedicated scalper admission policy.

    This is intentionally separate from the normal-bot regime logic.
    Scalper requires valid microstructure conditions in addition to a
    compatible regime — passing the regime check alone is NOT sufficient.

    Allowed regimes: consolidation, low_volatility, mean_reversion.
    Required conditions on top of regime check:
      - spread is acceptable (< SCALPER_MAX_SPREAD_PCT)
      - depth is sufficient (>= SCALPER_MIN_DEPTH_NOTIONAL)
      - liquidity score is adequate (>= SCALPER_MIN_LIQUIDITY_SCORE)
      - volatility is not chaotic (vol_score < SCALPER_MAX_VOL_SCORE)
      - momentum not dominant (trend_score < SCALPER_MAX_TREND_SCORE)

    Blocked conditions:
      - dead liquidity: depth too thin OR spread too wide
      - chaotic whipsaw: vol_score >= SCALPER_MAX_VOL_SCORE
      - cost-dominant: net_edge_bps is too small after costs
      - insufficient short-horizon range: price range too tight to hit target
    """

    ALLOWED_REGIMES = STRATEGY_REGIME_MAP["scalper"]

    @classmethod
    def evaluate(
        cls,
        *,
        regime_label: str,
        regime_confidence: float,
        spread_pct: float,
        depth_notional: float,
        liquidity_score: float,
        vol_score: float,
        trend_score: float,
        net_edge_bps: float = 0.0,
        projected_net_profit_quote: float = 0.0,
        min_profit_quote: float = 0.0,
    ) -> dict:
        """
        Evaluate whether microstructure is good enough for a scalper entry.

        Returns dict with:
          eligible           – True / False
          action             – 'approved' / 'blocked'
          block_reason_code  – structured reason if blocked
          block_reason_text  – human-readable reason
          details            – dict of scores used in the decision
        """
        details = {
            "regime_label":      regime_label,
            "regime_confidence": round(regime_confidence, 4),
            "spread_pct":        round(float(spread_pct or 0), 4),
            "depth_notional":    float(depth_notional or 0),
            "liquidity_score":   round(float(liquidity_score or 0), 4),
            "vol_score":         round(float(vol_score or 0), 4),
            "trend_score":       round(float(trend_score or 0), 4),
            "net_edge_bps":      round(float(net_edge_bps or 0), 4),
        }

        # ── 1. Regime must be in allowed set ─────────────────────────────
        if regime_label not in cls.ALLOWED_REGIMES and regime_label != REGIME_AMBIGUOUS:
            return {
                "eligible": False,
                "action": "blocked",
                "block_reason_code": "SCALPER_REGIME_INCOMPATIBLE",
                "block_reason_text": (
                    f"Scalper blocked: regime '{regime_label}' is not consolidation / "
                    f"low_volatility / mean_reversion."
                ),
                "details": details,
            }

        # ── 2. Dead liquidity check ───────────────────────────────────────
        if float(spread_pct or 0) >= SCALPER_MAX_SPREAD_PCT:
            return {
                "eligible": False,
                "action": "blocked",
                "block_reason_code": "SCALPER_SPREAD_TOO_WIDE",
                "block_reason_text": (
                    f"Scalper blocked: spread {spread_pct:.3f}% >= "
                    f"{SCALPER_MAX_SPREAD_PCT:.2f}% threshold (dead/costly liquidity)."
                ),
                "details": details,
            }
        if float(depth_notional or 0) < SCALPER_MIN_DEPTH_NOTIONAL:
            return {
                "eligible": False,
                "action": "blocked",
                "block_reason_code": "SCALPER_DEPTH_TOO_THIN",
                "block_reason_text": (
                    f"Scalper blocked: depth {depth_notional:.0f} < "
                    f"{SCALPER_MIN_DEPTH_NOTIONAL:.0f} (insufficient order book depth)."
                ),
                "details": details,
            }
        if float(liquidity_score or 0) < SCALPER_MIN_LIQUIDITY_SCORE:
            return {
                "eligible": False,
                "action": "blocked",
                "block_reason_code": "SCALPER_LIQUIDITY_LOW",
                "block_reason_text": (
                    f"Scalper blocked: liquidity score {liquidity_score:.2f} < "
                    f"{SCALPER_MIN_LIQUIDITY_SCORE:.2f} (market quality too low)."
                ),
                "details": details,
            }

        # ── 3. Chaotic whipsaw check ─────────────────────────────────────
        if float(vol_score or 0) >= SCALPER_MAX_VOL_SCORE:
            return {
                "eligible": False,
                "action": "blocked",
                "block_reason_code": "SCALPER_VOLATILITY_TOO_HIGH",
                "block_reason_text": (
                    f"Scalper blocked: vol_score {vol_score:.2f} >= "
                    f"{SCALPER_MAX_VOL_SCORE:.2f} (chaotic / whipsaw conditions)."
                ),
                "details": details,
            }

        # ── 4. Trend-dominant check (momentum overwhelms microstructure) ─
        if float(trend_score or 0) >= SCALPER_MAX_TREND_SCORE:
            return {
                "eligible": False,
                "action": "blocked",
                "block_reason_code": "SCALPER_TREND_DOMINANT",
                "block_reason_text": (
                    f"Scalper blocked: trend_score {trend_score:.2f} >= "
                    f"{SCALPER_MAX_TREND_SCORE:.2f} (directional momentum too strong)."
                ),
                "details": details,
            }

        # ── 5. Cost-dominant check ────────────────────────────────────────
        # Net edge must be positive; projection must clear profit floor
        if float(net_edge_bps or 0) <= 0:
            return {
                "eligible": False,
                "action": "blocked",
                "block_reason_code": "SCALPER_COST_DOMINANT",
                "block_reason_text": (
                    f"Scalper blocked: net_edge_bps {net_edge_bps:.1f} <= 0 "
                    f"(costs dominate projected edge)."
                ),
                "details": details,
            }
        if min_profit_quote > 0 and float(projected_net_profit_quote or 0) < min_profit_quote:
            return {
                "eligible": False,
                "action": "blocked",
                "block_reason_code": "SCALPER_PROFIT_BELOW_FLOOR",
                "block_reason_text": (
                    f"Scalper blocked: projected net profit "
                    f"{projected_net_profit_quote:.4f} < floor {min_profit_quote:.4f}."
                ),
                "details": details,
            }

        # ── All checks passed ─────────────────────────────────────────────
        return {
            "eligible": True,
            "action": "approved",
            "block_reason_code": "",
            "block_reason_text": (
                f"Scalper approved: regime={regime_label}, "
                f"spread={spread_pct:.3f}%, depth={depth_notional:.0f}, "
                f"vol={vol_score:.2f}, trend={trend_score:.2f}."
            ),
            "details": details,
        }
