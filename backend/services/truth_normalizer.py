"""
Backend Truth Normalizer

Single source of truth for bot/trade field normalization across
all backend endpoints: radar, status, trades, overview.

Merges canonical bot data with open-trade data so that:
  - symbol always comes from the trade when a trade is open
  - regime/confidence always comes from the trade's canonical fields
  - numeric fields are never NaN or None (safe-floated)
  - reason codes are present and non-empty

Usage:
    from services.truth_normalizer import normalize_bot_trade_truth

    normalized = normalize_bot_trade_truth(bot_doc, open_trade_doc)
    # Use normalized["symbol"], normalized["market_regime"], etc.
"""
from __future__ import annotations

import math
from typing import Any, Dict, Optional


def _sf(value: Any, default: float = 0.0) -> float:
    """Safe float coercion. Returns *default* for None/NaN/Inf/invalid."""
    if value is None:
        return default
    try:
        f = float(value)
        if math.isnan(f) or math.isinf(f):
            return default
        return f
    except (TypeError, ValueError):
        return default


def _ss(value: Any, default: str = "") -> str:
    """Safe string coercion. Returns *default* for None."""
    if value is None:
        return default
    s = str(value).strip()
    return s if s else default


def _first(*values: Any) -> Any:
    """Return the first non-None value from the candidates."""
    for v in values:
        if v is not None:
            return v
    return None


def normalize_bot_trade_truth(
    bot: Dict,
    open_trade: Optional[Dict],
) -> Dict:
    """
    Build a normalized truth payload for a bot + its current open trade.

    When *open_trade* is provided, trade-level canonical fields take priority
    over bot-level fields for symbol, regime, confidence, and entry data.
    Numeric fields are always safe-floated (never NaN/None).

    Returns a plain dict – callers can merge it into their own response as
    needed.
    """
    bot = bot or {}
    trade = open_trade or {}
    has_trade = bool(trade)

    # ── Symbol resolution ──────────────────────────────────────────────────
    # Priority: trade.pair → trade.symbol → bot.pair → bot.symbol
    trade_symbol = _ss(
        _first(trade.get("pair"), trade.get("symbol"), trade.get("trading_pair"))
    )
    bot_symbol = _ss(
        _first(bot.get("pair"), bot.get("symbol"))
    )
    symbol = trade_symbol if trade_symbol else (bot_symbol if bot_symbol else "unknown")

    # ── Exchange ───────────────────────────────────────────────────────────
    exchange = _ss(
        _first(trade.get("exchange"), bot.get("exchange")), default="unknown"
    )

    # ── Side ──────────────────────────────────────────────────────────────
    side: Optional[str] = None
    if has_trade:
        raw_side = _first(trade.get("side"), trade.get("type"), trade.get("direction"))
        side = _ss(raw_side).lower() if raw_side else None

    # ── Market regime ──────────────────────────────────────────────────────
    # Priority when trade open: trade canonical > trade.regime > bot.market_regime
    if has_trade:
        regime_raw = _first(
            trade.get("canonical_market_regime"),
            trade.get("market_regime"),
            trade.get("regime"),
            bot.get("canonical_market_regime"),
            bot.get("market_regime"),
            bot.get("regime_label"),
        )
    else:
        regime_raw = _first(
            bot.get("canonical_market_regime"),
            bot.get("market_regime"),
            bot.get("regime_label"),
        )
    market_regime = _ss(regime_raw, default="unknown")

    # ── Regime confidence ─────────────────────────────────────────────────
    if has_trade:
        rc_raw = _first(
            trade.get("canonical_regime_confidence"),
            trade.get("regime_confidence"),
            bot.get("canonical_regime_confidence"),
            bot.get("confidence_score"),
            bot.get("confidence"),
        )
    else:
        rc_raw = _first(
            bot.get("canonical_regime_confidence"),
            bot.get("confidence_score"),
            bot.get("confidence"),
        )
    regime_confidence = _sf(rc_raw, 0.0)

    # ── Entry confidence ──────────────────────────────────────────────────
    entry_confidence = _sf(
        _first(
            trade.get("entry_confidence_score") if has_trade else None,
            bot.get("entry_confidence_score"),
            bot.get("last_entry_confidence_score"),
        ),
        0.0,
    )

    # ── Expectancy / net edge ─────────────────────────────────────────────
    expectancy_net_edge_pct = _sf(
        _first(
            trade.get("expectancy_net_edge_pct") if has_trade else None,
            bot.get("expectancy_net_edge_pct"),
        ),
        0.0,
    )

    # ── Entry price, current price ─────────────────────────────────────────
    entry_price: Optional[float] = None
    current_price: Optional[float] = None
    if has_trade:
        entry_price = _sf(_first(trade.get("entry_price"), trade.get("price")), 0.0) or None
        current_price = _sf(trade.get("current_price"), 0.0) or entry_price

    # ── Reason codes ──────────────────────────────────────────────────────
    # Decision reason should come from the trade when one is open; else bot.
    decision_reason_code = _ss(
        _first(
            trade.get("trade_close_reason_code") if has_trade else None,
            trade.get("reason_code") if has_trade else None,
            bot.get("decision_reason_code"),
            bot.get("last_decision_reason_code"),
        )
    )
    entry_reason_code = _ss(
        _first(
            trade.get("entry_reason_code") if has_trade else None,
            bot.get("entry_reason_code"),
            bot.get("last_entry_reason_code"),
        )
    )

    # ── V2 edge / cost fields ─────────────────────────────────────────────
    expected_gross_edge_bps = _sf(
        _first(
            trade.get("expected_gross_edge_bps") if has_trade else None,
            bot.get("expected_gross_edge_bps"),
        ),
        0.0,
    )
    all_in_cost_bps = _sf(
        _first(
            trade.get("all_in_cost_bps") if has_trade else None,
            bot.get("all_in_cost_bps"),
        ),
        0.0,
    )
    expected_net_edge_bps = _sf(
        _first(
            trade.get("expected_net_edge_bps") if has_trade else None,
            bot.get("expected_net_edge_bps"),
        ),
        0.0,
    )
    projected_net_profit_quote = _sf(
        _first(
            trade.get("projected_net_profit_quote") if has_trade else None,
            bot.get("projected_net_profit_quote"),
        ),
        0.0,
    )

    return {
        # Identity
        "symbol": symbol,
        "exchange": exchange,
        # Position state
        "has_open_position": has_trade,
        "side": side,
        "entry_price": entry_price,
        "current_price": current_price,
        # Regime truth (from trade canonical fields when available)
        "market_regime": market_regime,
        "regime_confidence": round(regime_confidence, 4),
        # Confidence
        "entry_confidence_score": round(entry_confidence, 4),
        "expectancy_net_edge_pct": round(expectancy_net_edge_pct, 4),
        # Reason codes
        "decision_reason_code": decision_reason_code,
        "entry_reason_code": entry_reason_code,
        # V2 edge/cost fields
        "expected_gross_edge_bps": round(expected_gross_edge_bps, 4),
        "all_in_cost_bps": round(all_in_cost_bps, 4),
        "expected_net_edge_bps": round(expected_net_edge_bps, 4),
        "projected_net_profit_quote": round(projected_net_profit_quote, 4),
    }


def sanitize_decision_payload(payload: Dict) -> Dict:
    """
    Sanitize a decision payload dict in-place, returning the sanitized copy.

    - All numeric fields: NaN/Inf/None → 0.0
    - All string fields: None → ""
    - "approved" / "accepted": coerced to bool
    - Nested dicts are recursively sanitized

    Safe to call on any decision or analytics dict before JSON serialisation.
    """
    if not isinstance(payload, dict):
        return payload

    numeric_keys = {
        "entry_confidence_score", "regime_confidence", "expectancy_net_edge_pct",
        "expected_gross_edge_bps", "all_in_cost_bps", "expected_net_edge_bps",
        "projected_net_profit_quote", "trade_profit_target_quote", "daily_profit_target_quote",
        "net_edge_pct", "required_net_edge_pct", "effective_move_pct", "quality_multiplier",
        "confidence", "minimum_required", "unrealized_pnl", "realized_pnl", "roi",
        "win_rate", "daily_target_pct", "trade_target_pct", "capital_allocated",
        "daily_profit_target", "trade_profit_target",
    }
    string_keys = {
        "decision_reason_code", "entry_reason_code", "reason_code", "reason_text",
        "decision_reason_text", "market_regime", "regime_label", "symbol", "side",
        "next_action", "next_action_reason_code", "next_action_reason_text",
        "target_source", "hold_policy_source", "cost_floor_source",
    }
    bool_keys = {"approved", "accepted", "entry_approved"}

    out: Dict = {}
    for k, v in payload.items():
        if k in bool_keys:
            out[k] = bool(v)
        elif k in numeric_keys:
            out[k] = _sf(v, 0.0)
        elif k in string_keys:
            out[k] = _ss(v, "")
        elif isinstance(v, dict):
            out[k] = sanitize_decision_payload(v)
        elif isinstance(v, list):
            out[k] = [sanitize_decision_payload(i) if isinstance(i, dict) else i for i in v]
        else:
            out[k] = v
    return out
