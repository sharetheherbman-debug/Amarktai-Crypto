"""
Numeric utility helpers — no heavy dependencies.

Provides NaN/Inf/None-safe coercion for use across the backend without
importing MongoDB or other heavy packages.
"""
from __future__ import annotations

import math
from typing import Any, Dict, List


def safe_numeric(value: Any, default: float = 0.0) -> float:
    """
    Coerce *value* to a finite float, returning *default* on failure.

    Guards against:
    - None
    - NaN
    - Inf / -Inf
    - Non-numeric strings

    Args:
        value:   Raw value to coerce.
        default: Value to return when coercion fails or result is non-finite.

    Returns:
        Finite float.
    """
    if value is None:
        return default
    try:
        f = float(value)
        if math.isnan(f) or math.isinf(f):
            return default
        return f
    except (TypeError, ValueError):
        return default


def sanitize_numeric_dict(data: Dict[str, Any], keys: List[str], default: float = 0.0) -> Dict[str, Any]:
    """
    Return a copy of *data* with every listed key coerced via safe_numeric().

    Useful for hardening API response dicts before JSON serialisation.

    Args:
        data:    Source dict to sanitize.
        keys:    List of key names that must hold finite floats.
        default: Fallback for any key that is missing, None, NaN, or Inf.

    Returns:
        New dict with specified keys sanitized; other keys unchanged.
    """
    out = dict(data)
    for k in keys:
        out[k] = safe_numeric(data.get(k), default)
    return out
