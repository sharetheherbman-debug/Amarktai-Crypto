"""
StrategyVersionLoader — Live Strategy Parameter Loader
=======================================================
Reads research/strategies/active.json and exposes the promoted strategy
parameters to the live paper trading engine.

Design
------
- Reads the file at startup (and on operator-triggered reload).
- Caches the active strategy set in memory.
- Never raises on missing file — falls back gracefully (returns None).
- The paper engine reads from here instead of hardcoded config defaults.
- Config-level defaults remain as the ultimate fallback.

File format (research/strategies/active.json)
---------------------------------------------
{
    "momentum": {
        "version": "v2",
        "promoted_at": "...",
        "promoted_by": "operator",
        "config": {
            "exit": {"take_profit_pct": 3.5, "stop_loss_pct": 1.5, ...},
            "risk": {...},
            ...
        }
    },
    "mean_reversion": { ... },
    "scalper": { ... }
}

Usage
-----
    from services.strategy_version_loader import strategy_version_loader

    params = strategy_version_loader.get_strategy_params("momentum")
    tp_pct = params.get("exit", {}).get("take_profit_pct", 3.0)
"""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# Resolve path to research/strategies/active.json regardless of CWD
_HERE = Path(__file__).resolve()
# backend/services/ → backend/ → project_root/
_REPO_ROOT = _HERE.parent.parent.parent
_ACTIVE_JSON = _REPO_ROOT / "research" / "strategies" / "active.json"

# Allow env override for deployments where research/ is at a different path
_ACTIVE_JSON_OVERRIDE = os.getenv("STRATEGY_ACTIVE_JSON_PATH")
if _ACTIVE_JSON_OVERRIDE:
    _ACTIVE_JSON = Path(_ACTIVE_JSON_OVERRIDE)


class StrategyVersionLoader:
    """In-memory cache of promoted strategy versions."""

    def __init__(self) -> None:
        self._active: Optional[Dict[str, Any]] = None
        self._loaded_at: Optional[str] = None

    # -- Load / Reload ------------------------------------------------------

    def _load(self) -> None:
        if not _ACTIVE_JSON.exists():
            logger.debug(
                "StrategyVersionLoader: %s not found — using engine defaults", _ACTIVE_JSON
            )
            self._active = None
            return
        try:
            with open(_ACTIVE_JSON, encoding="utf-8") as f:
                data = json.load(f)
            self._active = data
            from datetime import datetime, timezone
            self._loaded_at = datetime.now(timezone.utc).isoformat()
            logger.info(
                "StrategyVersionLoader: loaded %d strategy(ies) from %s",
                len(data), _ACTIVE_JSON,
            )
            for name, meta in data.items():
                logger.info(
                    "  → %s version=%s promoted_at=%s",
                    name, meta.get("version", "?"), meta.get("promoted_at", "?"),
                )
        except Exception as exc:
            logger.warning("StrategyVersionLoader: failed to load %s: %s", _ACTIVE_JSON, exc)
            self._active = None

    def reload_active_strategy(self) -> None:
        """Re-read active.json from disk. Safe to call at any time."""
        self._load()

    # -- Query helpers ------------------------------------------------------

    def get_active_strategy(self) -> Optional[Dict[str, Any]]:
        """Return the full active strategy set or None."""
        if self._active is None:
            self._load()
        return self._active

    def get_strategy_params(self, strategy_name: Optional[str] = None) -> Dict[str, Any]:
        """Return the config dict for *strategy_name* (or {} if not found).

        If *strategy_name* is None, returns a merged dict of all active
        strategy configs (last-writer-wins on key conflicts).
        """
        active = self.get_active_strategy()
        if not active:
            return {}

        if strategy_name is not None:
            strategy_name = strategy_name.lower()
            entry = active.get(strategy_name)
            if entry:
                return dict(entry.get("config", {}))
            return {}

        # Merge all configs (used when bot_type is unknown)
        merged: Dict[str, Any] = {}
        for _name, entry in active.items():
            cfg = entry.get("config", {})
            for section, values in cfg.items():
                if section not in merged:
                    merged[section] = {}
                if isinstance(values, dict):
                    merged[section].update(values)
        return merged

    def get_active_version_info(self) -> Optional[Dict[str, Any]]:
        """Return metadata (version, promoted_at, …) without the full config."""
        active = self.get_active_strategy()
        if not active:
            return None
        return {
            name: {
                "version": entry.get("version"),
                "promoted_at": entry.get("promoted_at"),
                "promoted_by": entry.get("promoted_by"),
                "stage": entry.get("stage"),
                "notes": entry.get("notes"),
            }
            for name, entry in active.items()
        }

    def current_version_string(self) -> str:
        """Human-readable summary: 'momentum/v2, scalper/v1'."""
        active = self.get_active_strategy()
        if not active:
            return "none (using engine defaults)"
        return ", ".join(
            f"{name}/{entry.get('version', '?')}" for name, entry in active.items()
        )

    @property
    def loaded_at(self) -> Optional[str]:
        return self._loaded_at


# Module-level singleton
strategy_version_loader = StrategyVersionLoader()
