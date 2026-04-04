"""
Hurst Exponent Filter — classifies market memory to improve entry timing.

The Hurst exponent H characterises the long-range dependence of a price series:
  H > 0.55 → trending (persistent)   — favour trend-following entries
  H ≈ 0.50 → random walk             — no edge from direction-based entries
  H < 0.45 → mean-reverting          — favour scalper / mean-reversion entries

Usage
-----
    from services.hurst_filter import hurst_filter

    result = hurst_filter.compute(prices)          # list/array of close prices
    result = hurst_filter.should_enter(prices, bot_type="scalper")

Returns
-------
    compute()       -> dict with keys: hurst, regime, confidence, ok
    should_enter()  -> bool

Graceful degradation
--------------------
If the `hurst` package is unavailable, should_enter() always returns True and
compute() returns a neutral result so the rest of the trading system is unaffected.
"""
from __future__ import annotations

import logging
from typing import Dict, Sequence, Tuple, Union

import numpy as np

logger = logging.getLogger(__name__)

try:
    from hurst import compute_Hc
    _HURST_AVAILABLE = True
except ImportError:
    _HURST_AVAILABLE = False
    logger.warning(
        "hurst library not installed – Hurst filter will always pass. "
        "Install with: pip install hurst"
    )

# Minimum number of candles needed for a reliable Hurst estimate.
MIN_CANDLES: int = 50
# Window used for the RS computation (uses the last N candles of the series).
WINDOW: int = 100

# Entry rules per bot type.
# trend / adaptive → enter only when market is trending (H > 0.55)
# scalper / mean_reversion → enter only when mean-reverting (H < 0.45)
# normal (default) → pass unless market is pure random-walk (H ≈ 0.50 ± 0.03)
_BOT_RULES: Dict[str, Dict] = {
    "trend":           {"min_H": 0.55, "max_H": 1.0,  "regime": "trending"},
    "adaptive":        {"min_H": 0.52, "max_H": 1.0,  "regime": "trending"},
    "scalper":         {"min_H": 0.0,  "max_H": 0.47, "regime": "mean_reverting"},
    "mean_reversion":  {"min_H": 0.0,  "max_H": 0.47, "regime": "mean_reverting"},
    "normal":          {"min_H": 0.0,  "max_H": 1.0,  "regime": "any"},  # always pass
}
_RANDOM_WALK_BAND = (0.47, 0.53)  # suppress normal bots in pure random-walk markets


class HurstFilter:
    """
    Stateless helper that computes the Hurst exponent and decides whether
    entry conditions match the bot's strategy.
    """

    def compute(self, prices: Sequence[float]) -> dict:
        """
        Compute Hurst exponent from a sequence of close prices.

        Parameters
        ----------
        prices : Sequence[float]
            Close prices in chronological order (oldest first).

        Returns
        -------
        dict with:
            hurst      — H value in [0, 1] (0.5 if unavailable / insufficient data)
            regime     — "trending" | "mean_reverting" | "random_walk" | "unknown"
            confidence — float [0, 1] representing how far H is from 0.5
            ok         — True unless data is insufficient
        """
        arr = np.asarray(prices, dtype=float)
        if not np.all(np.isfinite(arr)):
            arr = arr[np.isfinite(arr)]

        if len(arr) < MIN_CANDLES:
            return {"hurst": 0.5, "regime": "unknown", "confidence": 0.0, "ok": False,
                    "reason": f"Need ≥{MIN_CANDLES} candles, got {len(arr)}"}

        # Use the most recent WINDOW candles.
        series = arr[-WINDOW:]

        if not _HURST_AVAILABLE:
            return {"hurst": 0.5, "regime": "unknown", "confidence": 0.0, "ok": True,
                    "reason": "hurst library unavailable"}

        try:
            H, _c, _data = compute_Hc(series, kind="price", simplified=True)
            H = float(H)

            if H > 0.55:
                regime = "trending"
            elif H < 0.45:
                regime = "mean_reverting"
            else:
                regime = "random_walk"

            # Confidence = distance from 0.5 normalised to [0, 1]
            confidence = min(abs(H - 0.5) / 0.5, 1.0)

            return {
                "hurst": round(H, 4),
                "regime": regime,
                "confidence": round(confidence, 4),
                "ok": True,
            }
        except Exception as exc:
            logger.debug("Hurst computation failed: %s", exc)
            return {"hurst": 0.5, "regime": "unknown", "confidence": 0.0, "ok": False,
                    "reason": str(exc)}

    def should_enter(
        self,
        prices: Sequence[float],
        bot_type: str = "normal",
    ) -> Tuple[bool, dict]:
        """
        Decide whether the Hurst regime is suitable for the given bot type.

        Parameters
        ----------
        prices   : Close price sequence.
        bot_type : One of "trend", "adaptive", "scalper", "mean_reversion", "normal".

        Returns
        -------
        (allowed: bool, details: dict)
        """
        if not _HURST_AVAILABLE:
            return True, {"reason": "hurst library unavailable — filter bypassed"}

        result = self.compute(prices)
        if not result["ok"]:
            # Insufficient data → allow trade (don't block on missing info).
            return True, result

        H = result["hurst"]
        bt = (bot_type or "normal").lower()
        rule = _BOT_RULES.get(bt, _BOT_RULES["normal"])

        # Suppress normal bots in pure random-walk (no edge).
        if bt == "normal" and _RANDOM_WALK_BAND[0] <= H <= _RANDOM_WALK_BAND[1]:
            result["allowed"] = False
            result["reason"] = f"Hurst={H:.3f} → random walk, no directional edge for {bt} bot"
            return False, result

        allowed = rule["min_H"] <= H <= rule["max_H"]
        result["allowed"] = allowed
        if not allowed:
            result["reason"] = (
                f"Hurst={H:.3f} ({result['regime']}) does not match "
                f"{bt} bot requirement [{rule['min_H']}, {rule['max_H']}]"
            )
        return allowed, result


# Module-level singleton.
hurst_filter = HurstFilter()
