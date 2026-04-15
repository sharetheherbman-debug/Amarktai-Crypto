#!/usr/bin/env python3
"""
Amarktai Crypto — Strategy Registry
=====================================
SIDECAR ONLY — not used at runtime by the live engine.

Manages versioned strategy parameter sets and controls promotion between stages:

  experimental → validated → active

The live paper engine looks for the "active" strategy in:
  research/strategies/active.json

Only promote a strategy to "active" after it has passed:
  Stage A: VectorBT sweep (vectorbt_runner.py)
  Stage B: Freqtrade dry-run or backtest (../validation/freqtrade/)

Usage:
    from research.strategy_registry import registry

    # List all strategies
    registry.list_strategies()

    # Get active momentum config
    cfg = registry.get_active("momentum")

    # Promote a strategy
    registry.promote("momentum", version="v2", from_stage="validated", to_stage="active")

    # From CLI:
    python research/strategy_registry.py list
    python research/strategy_registry.py promote momentum v2 validated active
    python research/strategy_registry.py show momentum
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

# Strategies live in research/strategies/
_REGISTRY_DIR = Path(__file__).parent / "strategies"
_INDEX_FILE   = _REGISTRY_DIR / "index.json"

# Allowed promotion path — must move forward, never backward
_VALID_STAGES = ("experimental", "validated", "active")


# ---------------------------------------------------------------------------
# Index management
# ---------------------------------------------------------------------------

def _load_index() -> Dict[str, Any]:
    if _INDEX_FILE.exists():
        with open(_INDEX_FILE) as f:
            return json.load(f)
    return {"strategies": {}}


def _save_index(index: Dict[str, Any]) -> None:
    _REGISTRY_DIR.mkdir(parents=True, exist_ok=True)
    with open(_INDEX_FILE, "w") as f:
        json.dump(index, f, indent=2)


# ---------------------------------------------------------------------------
# Strategy registry class
# ---------------------------------------------------------------------------

class StrategyRegistry:
    """
    Lightweight strategy version registry backed by JSON files.

    Each strategy has a versioned directory:
        research/strategies/<name>/<version>/config.json

    The registry index tracks the current stage for each name+version pair.
    The "active" entry is symlinked/copied to:
        research/strategies/active.json (single file for live engine reading)
    """

    def __init__(self) -> None:
        _REGISTRY_DIR.mkdir(parents=True, exist_ok=True)
        if not _INDEX_FILE.exists():
            _save_index({"strategies": {}})

    # ------------------------------------------------------------------ CRUD

    def register(
        self,
        name: str,
        version: str,
        config: Dict[str, Any],
        stage: str = "experimental",
        notes: str = "",
    ) -> None:
        """
        Register a new strategy version.

        name:    e.g. "momentum", "scalper", "mean_reversion"
        version: e.g. "v1", "v2", "2024-06-01"
        config:  strategy parameter dict (tp_pct, sl_pct, thresholds, etc.)
        stage:   one of "experimental", "validated", "active"
        notes:   optional free-text annotation
        """
        if stage not in _VALID_STAGES:
            raise ValueError(f"stage must be one of {_VALID_STAGES}, got {stage!r}")

        strategy_dir = _REGISTRY_DIR / name / version
        strategy_dir.mkdir(parents=True, exist_ok=True)

        config_file = strategy_dir / "config.json"
        payload = {
            "name":       name,
            "version":    version,
            "stage":      stage,
            "notes":      notes,
            "registered_at": datetime.now(timezone.utc).isoformat(),
            "config":     config,
        }
        with open(config_file, "w") as f:
            json.dump(payload, f, indent=2)

        index = _load_index()
        index["strategies"].setdefault(name, {})[version] = {
            "stage": stage,
            "notes": notes,
            "registered_at": payload["registered_at"],
        }
        _save_index(index)
        print(f"  ✓ Registered {name}/{version} as [{stage}]")

    def promote(
        self,
        name: str,
        version: str,
        from_stage: str,
        to_stage: str,
    ) -> None:
        """
        Promote a strategy from one stage to the next.

        Validates:
        - version exists
        - current stage matches from_stage
        - to_stage is a valid forward promotion

        When promoting to "active":
        - Updates the shared active.json so the live engine can read it.
        """
        if from_stage not in _VALID_STAGES or to_stage not in _VALID_STAGES:
            raise ValueError(f"Invalid stage. Must be one of {_VALID_STAGES}")

        from_idx = _VALID_STAGES.index(from_stage)
        to_idx   = _VALID_STAGES.index(to_stage)
        if to_idx <= from_idx:
            raise ValueError(f"Can only promote forward: {from_stage} → {to_stage} is not valid")

        index = _load_index()
        entry = index["strategies"].get(name, {}).get(version)
        if not entry:
            raise KeyError(f"Strategy {name}/{version} not found in registry")

        if entry["stage"] != from_stage:
            raise ValueError(
                f"Expected stage={from_stage!r} but {name}/{version} is currently {entry['stage']!r}"
            )

        # Load config, update stage, write back
        config_file = _REGISTRY_DIR / name / version / "config.json"
        with open(config_file) as f:
            payload = json.load(f)

        payload["stage"] = to_stage
        if to_stage == "active":
            payload["promoted_to_active_at"] = datetime.now(timezone.utc).isoformat()
        with open(config_file, "w") as f:
            json.dump(payload, f, indent=2)

        entry["stage"] = to_stage
        entry["promoted_at"] = datetime.now(timezone.utc).isoformat()
        _save_index(index)
        print(f"  ✓ Promoted {name}/{version}: {from_stage} → {to_stage}")

        if to_stage == "active":
            self._update_active_json(name, version, payload)

    def _update_active_json(self, name: str, version: str, payload: Dict[str, Any]) -> None:
        """
        Copy active strategy config to strategies/active.json
        (and per-name active file: strategies/<name>/active.json).

        The live engine only reads strategies/active.json for the full set.
        """
        active_path = _REGISTRY_DIR / "active.json"
        # Load current active set (may have multiple strategies active)
        if active_path.exists():
            with open(active_path) as f:
                active_set = json.load(f)
        else:
            active_set = {}

        active_set[name] = {
            "version": version,
            "activated_at": datetime.now(timezone.utc).isoformat(),
            "config": payload["config"],
        }
        with open(active_path, "w") as f:
            json.dump(active_set, f, indent=2)
        print(f"  ✓ Updated strategies/active.json ← {name}/{version}")

    # --------------------------------------------------------------- Queries

    def list_strategies(self, stage: Optional[str] = None) -> List[Dict[str, Any]]:
        """List all registered strategy versions, optionally filtered by stage."""
        index = _load_index()
        rows = []
        for sname, versions in index["strategies"].items():
            for ver, meta in versions.items():
                if stage and meta["stage"] != stage:
                    continue
                rows.append({
                    "name":    sname,
                    "version": ver,
                    "stage":   meta["stage"],
                    "notes":   meta.get("notes", ""),
                    "registered_at": meta.get("registered_at", ""),
                })
        return rows

    def get_config(self, name: str, version: str) -> Optional[Dict[str, Any]]:
        """Load the full config for a specific strategy version."""
        config_file = _REGISTRY_DIR / name / version / "config.json"
        if not config_file.exists():
            return None
        with open(config_file) as f:
            return json.load(f)

    def get_active(self, name: str) -> Optional[Dict[str, Any]]:
        """
        Return the active config for a strategy name.
        Falls back to the latest validated config if no active one exists.
        """
        active_path = _REGISTRY_DIR / "active.json"
        if active_path.exists():
            with open(active_path) as f:
                active_set = json.load(f)
            if name in active_set:
                return active_set[name]["config"]

        # Fallback: look for latest validated
        index = _load_index()
        for ver, meta in sorted(
            index["strategies"].get(name, {}).items(), reverse=True
        ):
            if meta["stage"] in ("validated", "active"):
                return self.get_config(name, ver)

        return None

    def print_table(self, stage: Optional[str] = None) -> None:
        rows = self.list_strategies(stage)
        if not rows:
            print("  (no strategies registered)")
            return
        print(f"\n{'Name':<20} {'Version':<10} {'Stage':<14} {'Notes':<40}")
        print("-" * 90)
        for r in rows:
            print(f"{r['name']:<20} {r['version']:<10} {r['stage']:<14} {r['notes']:<40}")


# Singleton
registry = StrategyRegistry()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _cli_main() -> None:
    parser = argparse.ArgumentParser(
        description="Amarktai Strategy Registry CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("list", help="List all strategy versions")

    p_show = sub.add_parser("show", help="Show config for a strategy")
    p_show.add_argument("name")
    p_show.add_argument("version", nargs="?", default=None)

    p_active = sub.add_parser("active", help="Show active strategy configs")
    p_active.add_argument("name", nargs="?", default=None)

    p_promote = sub.add_parser("promote", help="Promote a strategy to the next stage")
    p_promote.add_argument("name")
    p_promote.add_argument("version")
    p_promote.add_argument("from_stage", choices=_VALID_STAGES)
    p_promote.add_argument("to_stage",   choices=_VALID_STAGES)

    args = parser.parse_args()

    if args.command == "list":
        registry.print_table()

    elif args.command == "show":
        cfg = registry.get_config(args.name, args.version or "v1")
        if cfg:
            print(json.dumps(cfg, indent=2))
        else:
            print(f"Strategy {args.name}/{args.version} not found")
            sys.exit(1)

    elif args.command == "active":
        active_path = _REGISTRY_DIR / "active.json"
        if not active_path.exists():
            print("No active strategies found")
            return
        with open(active_path) as f:
            active_set = json.load(f)
        if args.name:
            if args.name in active_set:
                print(json.dumps(active_set[args.name], indent=2))
            else:
                print(f"No active config for {args.name!r}")
        else:
            print(json.dumps(active_set, indent=2))

    elif args.command == "promote":
        registry.promote(args.name, args.version, args.from_stage, args.to_stage)

    else:
        parser.print_help()


if __name__ == "__main__":
    _cli_main()
