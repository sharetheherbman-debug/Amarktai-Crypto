"""
Scheduler diagnostics helpers — skip-reason classification.

Extracted to a standalone module so it can be imported without pulling in
the full trading_scheduler dependency chain (which requires motor, ccxt, etc.).

These helpers map raw skip_reason strings from paper/live engine results to
canonical categories exposed in scheduler diagnostics (requirement E).
"""

from __future__ import annotations

from typing import Dict

# Canonical skip-reason categories
SKIP_CATEGORY_OPEN_POSITION = "blocked_by_open_position"
SKIP_CATEGORY_COOLDOWN = "blocked_by_cooldown"
SKIP_CATEGORY_ECONOMICS = "blocked_by_economics"
SKIP_CATEGORY_EXPOSURE = "blocked_by_exposure"
SKIP_CATEGORY_DEFERRED = "deferred_by_staggerer"
SKIP_CATEGORY_OTHER = "other"

_ECONOMICS_KEYWORDS = frozenset([
    "edge", "profit", "abs_profit", "cost", "worth", "feasibility",
    "expectancy", "confidence", "low_entry", "signal",
])
_COOLDOWN_KEYWORDS = frozenset([
    "rate_limit", "cooldown", "reentry", "throttle", "budget",
])
_EXPOSURE_KEYWORDS = frozenset([
    "exposure", "concentration", "drawdown", "circuit_breaker",
    "max_drawdown", "daily_loss", "risk_mode",
])
_OPEN_POSITION_KEYWORDS = frozenset([
    "open_position", "managing_open", "open_trade", "already_open",
])


def classify_skip_reason(skip_reason: str, counts: Dict[str, int]) -> str:
    """Map a raw skip_reason string to a canonical category and increment *counts*.

    Parameters
    ----------
    skip_reason : str
        Raw reason string from paper/live engine result dict.
    counts : dict
        Mutable counter dict that is updated in-place.

    Returns
    -------
    str
        The canonical category string (one of the ``SKIP_CATEGORY_*`` constants).
    """
    if not skip_reason:
        category = SKIP_CATEGORY_OTHER
    else:
        lower = skip_reason.lower()
        if any(kw in lower for kw in _OPEN_POSITION_KEYWORDS):
            category = SKIP_CATEGORY_OPEN_POSITION
        elif any(kw in lower for kw in _COOLDOWN_KEYWORDS):
            category = SKIP_CATEGORY_COOLDOWN
        elif any(kw in lower for kw in _ECONOMICS_KEYWORDS):
            category = SKIP_CATEGORY_ECONOMICS
        elif any(kw in lower for kw in _EXPOSURE_KEYWORDS):
            category = SKIP_CATEGORY_EXPOSURE
        else:
            category = SKIP_CATEGORY_OTHER
    counts[category] = counts.get(category, 0) + 1
    return category


def dominant_skip_category(counts: Dict[str, int]) -> str:
    """Return the skip category with the highest count, or '' if counts is empty."""
    if not counts:
        return ""
    return max(counts, key=counts.__getitem__)
