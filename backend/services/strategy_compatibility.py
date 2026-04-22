"""
Strategy-Exchange Compatibility Enforcement
============================================

Reads the ``compatible_exchanges`` list from each strategy JSON in
research/strategies/ and exposes a single ``check_compatible`` function.

If a strategy JSON includes ``compatible_exchanges``, only those exchanges are
allowed to run bots using that strategy/bot_type.  If the list is absent or
``null`` the strategy is considered compatible with every exchange.

Usage
-----
    from services.strategy_compatibility import check_compatible

    ok, reason = check_compatible(bot_type="scalper", exchange="luno")
    if not ok:
        # reason == "strategy_exchange_incompatible"
        return {"success": False, "skip_reason": reason, ...}

The check is intentionally lightweight (reads files from disk once per
process, cached in-module).  Do NOT do live DB lookups here.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ── Strategy directory ────────────────────────────────────────────────────────
_STRATEGIES_DIR = os.path.realpath(
    os.path.join(
        os.path.dirname(__file__),  # backend/services/
        "..",                        # backend/
        "..",                        # repo root
        "research",
        "strategies",
    )
)

# ── In-process cache ──────────────────────────────────────────────────────────
# Maps bot_type (str) → list of allowed exchanges (lower-case), or None (all).
# Populated lazily on first call to check_compatible().
_compat_cache: Optional[Dict[str, Optional[List[str]]]] = None


def _load_compat_map() -> Dict[str, Optional[List[str]]]:
    """Read all strategy JSON files and build the bot_type → allowed-exchanges map.

    Returns
    -------
    dict
        ``{"scalper": ["binance", "kucoin", ...], "normal": None, ...}``
        ``None`` value means "compatible with all exchanges".
    """
    result: Dict[str, Optional[List[str]]] = {}
    try:
        if not os.path.isdir(_STRATEGIES_DIR):
            logger.warning("strategy_compatibility: strategies dir not found: %s", _STRATEGIES_DIR)
            return result
        for fname in os.listdir(_STRATEGIES_DIR):
            if not fname.endswith(".json"):
                continue
            fpath = os.path.join(_STRATEGIES_DIR, fname)
            try:
                with open(fpath, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception as _fe:
                logger.warning("strategy_compatibility: could not read %s: %s", fname, _fe)
                continue

            bot_type: Optional[str] = None
            # Prefer config.bot_type; fall back to top-level name
            cfg = data.get("config") or {}
            bot_type = (cfg.get("bot_type") or data.get("name") or "").strip().lower()
            if not bot_type:
                continue

            raw_compat = data.get("compatible_exchanges")
            if raw_compat is None:
                # No restriction declared → compatible with all exchanges
                allowed: Optional[List[str]] = None
            elif isinstance(raw_compat, list):
                allowed = [str(e).strip().lower() for e in raw_compat if e is not None and str(e).strip()]
            else:
                logger.warning(
                    "strategy_compatibility: unexpected compatible_exchanges type in %s: %s",
                    fname, type(raw_compat),
                )
                allowed = None

            # If multiple strategy files define the same bot_type, apply the most
            # restrictive rule (intersection of allowed lists).
            if bot_type not in result:
                result[bot_type] = allowed
            else:
                existing = result[bot_type]
                if existing is None:
                    # First file was unrestricted — adopt the new restriction
                    result[bot_type] = allowed
                elif allowed is not None:
                    # Both are restricted — keep the intersection
                    result[bot_type] = [e for e in existing if e in allowed]
                # else: new file is unrestricted, keep existing restriction

    except Exception as _de:
        logger.error("strategy_compatibility: failed to load compat map: %s", _de)
    return result


def _get_compat_map() -> Dict[str, Optional[List[str]]]:
    global _compat_cache
    if _compat_cache is None:
        _compat_cache = _load_compat_map()
    return _compat_cache


def reload_compat_map() -> None:
    """Force reload of the compatibility map (e.g. after a strategy promote)."""
    global _compat_cache
    _compat_cache = None


def check_compatible(bot_type: str, exchange: str) -> Tuple[bool, str]:
    """Return (is_compatible, reason_code) for a bot_type + exchange pair.

    Parameters
    ----------
    bot_type : str
        Bot type string, e.g. ``"scalper"`` or ``"normal"``.
    exchange : str
        Exchange name, e.g. ``"luno"`` or ``"binance"``.

    Returns
    -------
    (True, "allowed")
        The combination is permitted.
    (False, "strategy_exchange_incompatible")
        The active strategy for this bot_type explicitly excludes this exchange.
    """
    _bt = (bot_type or "").strip().lower()
    _ex = (exchange or "").strip().lower()

    compat_map = _get_compat_map()
    allowed_exchanges = compat_map.get(_bt)  # None means "all allowed"

    if allowed_exchanges is None:
        return True, "allowed"

    if _ex in allowed_exchanges:
        return True, "allowed"

    logger.info(
        "strategy_compatibility: bot_type=%s blocked on exchange=%s "
        "(allowed: %s)",
        _bt, _ex, allowed_exchanges,
    )
    return False, "strategy_exchange_incompatible"


def get_allowed_exchanges(bot_type: str) -> Optional[List[str]]:
    """Return the list of allowed exchanges for *bot_type*, or None (unrestricted)."""
    _bt = (bot_type or "").strip().lower()
    return _get_compat_map().get(_bt)


def get_compat_summary() -> Dict[str, object]:
    """Return a diagnostic snapshot of the current compatibility rules."""
    compat_map = _get_compat_map()
    return {
        "rules": {
            bt: (sorted(exch_list) if exch_list is not None else "all")
            for bt, exch_list in compat_map.items()
        },
        "source": _STRATEGIES_DIR,
    }
