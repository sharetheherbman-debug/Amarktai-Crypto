"""
Pack Runtime — deterministic policy-pack selector for live/paper bots.

Every bot that enters the decision pipeline must have an active policy pack
resolved before any economics gates run.  This module is the single runtime
resolver so pack selection logic does not scatter across multiple callsites.

Resolution order
----------------
1. bot.policy_pack_name / bot.policy_pack  — explicit DB override
2. risk_mode + bot_type combination map     — most common automatic assignment
3. bot_type default                         — fallback

Exposed constants / functions
------------------------------
resolve_runtime_pack(bot_doc)      → pack dict
resolve_pack_name(bot_doc)         → pack name string (for logging/storage)
RISK_MODE_PACK_MAP                 — the mapping used for automatic assignment
"""
from __future__ import annotations

from typing import Dict, Optional

from .policy_packs import (
    get_policy_pack,
    get_default_pack_for_bot_type,
    ALL_PACKS,
    POLICY_PACK_VERSION,
)

# ── Risk-mode × bot-type → default pack name ──────────────────────────────
# When no explicit override is set, this map provides the automatic assignment.
RISK_MODE_PACK_MAP: Dict[str, Dict[str, str]] = {
    # (risk_mode, bot_type) → pack_name
    ("conservative", "normal"):         "defensive",
    ("conservative", "mean_reversion"): "defensive",
    ("safe",         "normal"):         "balanced",
    ("safe",         "mean_reversion"): "balanced",
    ("moderate",     "normal"):         "balanced",
    ("moderate",     "mean_reversion"): "balanced",
    ("aggressive",   "normal"):         "aggressive",
    ("aggressive",   "mean_reversion"): "aggressive",
    # Scalper packs
    ("conservative", "scalper"):        "scalper_conservative",
    ("safe",         "scalper"):        "scalper_conservative",
    ("moderate",     "scalper"):        "scalper_active",
    ("aggressive",   "scalper"):        "scalper_active",
    # Trend / adaptive → balanced by default
    ("safe",         "trend"):          "balanced",
    ("moderate",     "trend"):          "balanced",
    ("aggressive",   "trend"):          "aggressive",
    ("safe",         "adaptive"):       "balanced",
    ("moderate",     "adaptive"):       "balanced",
    ("aggressive",   "adaptive"):       "aggressive",
}


def resolve_pack_name(bot_doc: dict) -> str:
    """
    Resolve the canonical policy pack name for a bot document.

    Resolution order:
      1. bot.policy_pack_name or bot.policy_pack (explicit override)
      2. RISK_MODE_PACK_MAP[(risk_mode, bot_type)]
      3. default for bot_type
    """
    # 1. Explicit override
    explicit = str(
        bot_doc.get("policy_pack_name") or bot_doc.get("policy_pack") or ""
    ).strip()
    if explicit and explicit in ALL_PACKS:
        return explicit

    # 2. Risk-mode map
    bt = str(bot_doc.get("bot_type") or bot_doc.get("strategy_type") or "normal").lower()
    rm = str(bot_doc.get("risk_mode") or "safe").lower()
    mapped = RISK_MODE_PACK_MAP.get((rm, bt))
    if mapped and mapped in ALL_PACKS:
        return mapped

    # 3. Default for bot type
    return get_default_pack_for_bot_type(bt)["pack_name"]


def resolve_runtime_pack(bot_doc: dict) -> Dict:
    """
    Resolve and return the full policy pack dict for a bot document.

    Always returns a valid pack dict — never raises; falls back to 'balanced'.
    """
    try:
        name = resolve_pack_name(bot_doc)
        return get_policy_pack(name)
    except Exception:
        return ALL_PACKS["balanced"]


def pack_fields_for_trade_record(bot_doc: dict) -> Dict:
    """
    Return the minimal set of pack fields that must be stored on every
    trade entry record for calibration.
    """
    pack = resolve_runtime_pack(bot_doc)
    return {
        "policy_pack_name":    pack["pack_name"],
        "policy_pack_version": pack["pack_version"],
        "policy_pack_id":      pack["pack_name"],   # alias used in payloads
    }
