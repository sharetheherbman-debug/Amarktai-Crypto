"""
Canonical Policy Pack Architecture for Trading Brain V2.

A policy pack is a named, versioned set of trading parameters that fully
defines how a bot enters, manages, and exits trades.  Multiple packs can
coexist — each bot is assigned one active pack which can be promoted or
demoted by the self-learning evaluator (future phase).

Policy packs replace the ad-hoc threshold scatter across entry_thresholds.py,
trade_feasibility_gate.py, and open_trade_manager.py with explicit, auditable
named presets.

Available packs
---------------
  defensive              — low-frequency, high-quality normal-bot trades only
  balanced               — default normal-bot pack, balanced quality/frequency
  aggressive             — higher frequency, lower quality bar, normal bots
  scalper_conservative   — scalper pack with strict conditions
  scalper_active         — scalper pack with standard conditions

Each pack surfaces:
  - pack_name            — machine-readable identifier
  - pack_version         — semver string (pack set version)
  - display_name         — human-readable
  - bot_types_supported  — list of bot types this pack is valid for
  - regime_allowlist     — regimes permitted for entry
  - min_entry_confidence — minimum aggregated entry confidence score
  - min_net_edge_bps     — minimum net edge after round-trip costs
  - min_projected_net_profit_multiplier — × canonical min_profit_required
  - min_consensus_sources — minimum number of signal sources in agreement
  - min_market_quality   — minimum market quality score (0–1)
  - max_spread_pct       — max allowed spread for entry
  - max_slippage_pct     — max estimated slippage before entry is rejected
  - max_hold_seconds     — maximum trade hold time
  - cooldown_seconds     — minimum re-entry cooldown after close
  - stop_loss_pct        — stop loss as fraction of notional (0.01 = 1%)
  - take_profit_pct      — take profit as fraction of notional
  - trailing_stop_pct    — trailing stop (0 = disabled)
  - early_exit_fraction  — no-progress exit fires at this time budget fraction
  - description          — explanation of the pack's philosophy

Usage
-----
    from services.trading_brain_v2.policy_packs import (
        get_policy_pack,
        get_default_pack_for_bot_type,
        ALL_PACKS,
        POLICY_PACK_VERSION,
    )

    pack = get_policy_pack("balanced")
    pack_scalper = get_default_pack_for_bot_type("scalper")
"""
from __future__ import annotations

import os
from typing import Dict, List, Optional

# Increment whenever any pack definition changes
POLICY_PACK_VERSION: str = "v1.0"

# Scalper cooldown can be tuned at runtime (lower = more trades per day).
# Default 30s allows up to ~120 scalper trades/bot/hour in active markets.
_SCALPER_COOLDOWN_SECONDS = int(os.getenv("SCALPER_POLICY_COOLDOWN_SECONDS", "30"))

# Regime sets (re-exported for readability)
_NORMAL_REGIMES = frozenset({
    "trending_up", "trending_down", "consolidation",
    "mean_reversion", "breakout", "low_volatility",
})
_SCALPER_REGIMES = frozenset({
    "consolidation", "low_volatility", "mean_reversion",
})
_MEAN_REV_REGIMES = frozenset({
    "mean_reversion", "consolidation", "low_volatility",
})


def _pack(
    pack_name: str,
    display_name: str,
    bot_types: List[str],
    regime_allowlist: frozenset,
    *,
    min_entry_confidence: float,
    min_net_edge_bps: float,
    min_projected_net_profit_multiplier: float,
    min_consensus_sources: int,
    min_market_quality: float,
    max_spread_pct: float,
    max_slippage_pct: float,
    max_hold_seconds: int,
    cooldown_seconds: int,
    stop_loss_pct: float,
    take_profit_pct: float,
    trailing_stop_pct: float,
    early_exit_fraction: float,
    description: str,
) -> Dict:
    return {
        "pack_name":                          pack_name,
        "pack_version":                       POLICY_PACK_VERSION,
        "display_name":                       display_name,
        "bot_types_supported":                list(bot_types),
        "regime_allowlist":                   sorted(regime_allowlist),
        "min_entry_confidence":               min_entry_confidence,
        "min_net_edge_bps":                   min_net_edge_bps,
        "min_projected_net_profit_multiplier": min_projected_net_profit_multiplier,
        "min_consensus_sources":              min_consensus_sources,
        "min_market_quality":                 min_market_quality,
        "max_spread_pct":                     max_spread_pct,
        "max_slippage_pct":                   max_slippage_pct,
        "max_hold_seconds":                   max_hold_seconds,
        "cooldown_seconds":                   cooldown_seconds,
        "stop_loss_pct":                      stop_loss_pct,
        "take_profit_pct":                    take_profit_pct,
        "trailing_stop_pct":                  trailing_stop_pct,
        "early_exit_fraction":                early_exit_fraction,
        "description":                        description,
    }


# ══════════════════════════════════════════════════════════════════════════
# Policy pack definitions
# ══════════════════════════════════════════════════════════════════════════

PACK_DEFENSIVE = _pack(
    pack_name="defensive",
    display_name="Defensive (High Quality)",
    bot_types=["normal", "mean_reversion"],
    regime_allowlist=_NORMAL_REGIMES,
    min_entry_confidence=0.72,
    min_net_edge_bps=22.0,
    min_projected_net_profit_multiplier=2.0,  # 2× the canonical min floor
    min_consensus_sources=3,
    min_market_quality=0.55,
    max_spread_pct=0.20,
    max_slippage_pct=0.10,
    max_hold_seconds=14400,          # 4 hours
    cooldown_seconds=300,            # 5 min
    stop_loss_pct=0.012,             # 1.2%
    take_profit_pct=0.025,           # 2.5%
    trailing_stop_pct=0.008,         # 0.8% trailing
    early_exit_fraction=0.70,        # no-progress exit at 70% of time budget
    description=(
        "Fewer trades, strict quality bar. "
        "Requires strong multi-source consensus, high confidence, "
        "and meaningful edge. Best for capital preservation."
    ),
)

PACK_BALANCED = _pack(
    pack_name="balanced",
    display_name="Balanced (Default)",
    bot_types=["normal", "mean_reversion"],
    regime_allowlist=_NORMAL_REGIMES,
    min_entry_confidence=0.62,
    min_net_edge_bps=15.0,
    min_projected_net_profit_multiplier=1.5,  # 1.5× the canonical min floor
    min_consensus_sources=2,
    min_market_quality=0.40,
    max_spread_pct=0.30,
    max_slippage_pct=0.15,
    max_hold_seconds=21600,          # 6 hours
    cooldown_seconds=180,            # 3 min
    stop_loss_pct=0.015,             # 1.5%
    take_profit_pct=0.020,           # 2.0%
    trailing_stop_pct=0.006,         # 0.6% trailing
    early_exit_fraction=0.75,        # no-progress exit at 75%
    description=(
        "Default pack for normal bots. "
        "Balanced frequency and quality. Good all-round pack "
        "when no specific regime bias is needed."
    ),
)

PACK_AGGRESSIVE = _pack(
    pack_name="aggressive",
    display_name="Aggressive (High Frequency)",
    bot_types=["normal"],
    regime_allowlist=_NORMAL_REGIMES,
    min_entry_confidence=0.50,
    min_net_edge_bps=12.0,
    min_projected_net_profit_multiplier=1.2,  # 1.2× min floor — lower bar
    min_consensus_sources=1,
    min_market_quality=0.30,
    max_spread_pct=0.35,
    max_slippage_pct=0.20,
    max_hold_seconds=21600,          # 6 hours
    cooldown_seconds=120,            # 2 min
    stop_loss_pct=0.018,             # 1.8%
    take_profit_pct=0.016,           # 1.6%
    trailing_stop_pct=0.005,         # 0.5% trailing
    early_exit_fraction=0.80,        # later no-progress exit
    description=(
        "High trade frequency, lower quality bar. "
        "Accepts more marginal setups. Suitable only when "
        "calibration is good (qualified win rate ≥ 55%)."
    ),
)

PACK_SCALPER_CONSERVATIVE = _pack(
    pack_name="scalper_conservative",
    display_name="Scalper Conservative",
    bot_types=["scalper"],
    regime_allowlist=_SCALPER_REGIMES,
    min_entry_confidence=0.72,
    min_net_edge_bps=25.0,           # higher edge requirement
    min_projected_net_profit_multiplier=1.8,
    min_consensus_sources=2,
    min_market_quality=0.50,
    max_spread_pct=0.15,             # tight spread requirement
    max_slippage_pct=0.08,           # very tight slippage
    max_hold_seconds=180,            # 3 min max
    cooldown_seconds=_SCALPER_COOLDOWN_SECONDS,  # env-tunable (default 30s)
    stop_loss_pct=0.005,             # 0.5% tight stop
    take_profit_pct=0.008,           # 0.8% target
    trailing_stop_pct=0.003,         # 0.3% trail
    early_exit_fraction=0.50,        # exit at 50% time budget if no progress
    description=(
        "Conservative scalper pack. Requires pristine microstructure, "
        "narrow spreads, strong consensus. "
        "Exits quickly on any regime deterioration."
    ),
)

PACK_SCALPER_ACTIVE = _pack(
    pack_name="scalper_active",
    display_name="Scalper Active (Default)",
    bot_types=["scalper"],
    regime_allowlist=_SCALPER_REGIMES,
    min_entry_confidence=0.60,
    min_net_edge_bps=20.0,
    min_projected_net_profit_multiplier=1.5,
    min_consensus_sources=1,
    min_market_quality=0.35,
    max_spread_pct=0.20,             # 0.20% = 20 basis points of mid-price as spread cap
    max_slippage_pct=0.12,
    max_hold_seconds=300,            # 5 min max
    cooldown_seconds=_SCALPER_COOLDOWN_SECONDS,  # env-tunable (default 30s)
    stop_loss_pct=0.007,             # 0.7% stop
    take_profit_pct=0.010,           # 1.0% target
    trailing_stop_pct=0.004,         # 0.4% trail
    early_exit_fraction=0.60,        # no-progress exit at 60% time budget
    description=(
        "Default scalper pack. Standard frequency and execution quality. "
        "Allows consolidation/low-vol/mean-reversion regimes only. "
        "Recycles quickly when no progress."
    ),
)


# ── Registry ──────────────────────────────────────────────────────────────

ALL_PACKS: Dict[str, Dict] = {
    p["pack_name"]: p
    for p in [
        PACK_DEFENSIVE,
        PACK_BALANCED,
        PACK_AGGRESSIVE,
        PACK_SCALPER_CONSERVATIVE,
        PACK_SCALPER_ACTIVE,
    ]
}

# Default pack assigned when no explicit pack is chosen
_DEFAULT_BY_BOT_TYPE: Dict[str, str] = {
    "normal":           "balanced",
    "mean_reversion":   "balanced",
    "scalper":          "scalper_active",
    "trend":            "balanced",
    "adaptive":         "balanced",
}


def get_policy_pack(pack_name: str) -> Dict:
    """
    Return the full policy pack dict for a named pack.

    Raises ValueError for unknown pack names.
    """
    pack = ALL_PACKS.get(pack_name)
    if pack is None:
        known = sorted(ALL_PACKS.keys())
        raise ValueError(
            f"Unknown policy pack '{pack_name}'. "
            f"Known packs: {known}"
        )
    return pack


def get_default_pack_for_bot_type(bot_type: str) -> Dict:
    """
    Return the default policy pack for a given bot type.

    Falls back to 'balanced' for unknown bot types.
    """
    bt = (bot_type or "normal").lower()
    pack_name = _DEFAULT_BY_BOT_TYPE.get(bt, "balanced")
    return ALL_PACKS[pack_name]


def select_pack_for_bot(bot: dict) -> Dict:
    """
    Select the correct policy pack for a bot document.

    Priority:
      1. bot.policy_pack_name if set and valid
      2. default for bot_type
    """
    requested = bot.get("policy_pack_name") or bot.get("policy_pack")
    if requested and requested in ALL_PACKS:
        return ALL_PACKS[requested]
    bot_type = (bot.get("bot_type") or bot.get("strategy_type") or "normal").lower()
    return get_default_pack_for_bot_type(bot_type)


def validate_pack_for_bot_type(pack_name: str, bot_type: str) -> dict:
    """
    Validate whether a named pack is valid for a given bot type.

    Returns:
        valid         — bool
        reason        — human-readable validation message
        supported_bots — list of supported bot types for this pack
    """
    try:
        pack = get_policy_pack(pack_name)
    except ValueError as exc:
        return {"valid": False, "reason": str(exc), "supported_bots": []}

    bt = (bot_type or "normal").lower()
    if bt not in pack["bot_types_supported"]:
        return {
            "valid": False,
            "reason": (
                f"Pack '{pack_name}' does not support bot type '{bt}'. "
                f"Supported: {pack['bot_types_supported']}"
            ),
            "supported_bots": pack["bot_types_supported"],
        }
    return {
        "valid": True,
        "reason": f"Pack '{pack_name}' is valid for '{bt}'.",
        "supported_bots": pack["bot_types_supported"],
    }


def list_packs_for_bot_type(bot_type: str) -> List[Dict]:
    """Return all policy packs that support a given bot type."""
    bt = (bot_type or "normal").lower()
    return [p for p in ALL_PACKS.values() if bt in p["bot_types_supported"]]


def pack_summary() -> Dict:
    """Return a lightweight summary of all packs for diagnostics."""
    return {
        name: {
            "display_name":   p["display_name"],
            "bot_types":      p["bot_types_supported"],
            "pack_version":   p["pack_version"],
            "min_confidence": p["min_entry_confidence"],
            "max_hold_s":     p["max_hold_seconds"],
            "regime_count":   len(p["regime_allowlist"]),
        }
        for name, p in ALL_PACKS.items()
    }
