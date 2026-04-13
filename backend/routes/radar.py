"""
Radar Endpoints - Bot Radar / Bot Map visualization data

Provides per-bot radar data derived from ledger/trade truth:
  bot_id, name, exchange, symbol, side,
  entry_price, current_price, target_price, stop_price, trailing_stop_price,
  realized_pnl_today, unrealized_pnl,
  daily_profit_target, trade_profit_target,
  position_opened_at, max_hold_seconds, remaining_hold_seconds,
  next_action, next_action_reason_code, next_action_reason_text,
  market_regime, spread_estimate, slippage_estimate

Display currency contract:
  Every monetary amount field is accompanied by:
    quote_currency     — native trading quote currency ("ZAR" or "USDT")
    display_currency   — always "ZAR" (canonical user-facing currency)
    fx_rate_used       — rate used to convert quote→ZAR
    fx_source          — source of that rate
  Use <field>_display fields for user-facing rendering, not raw fields.
"""

import math

from fastapi import APIRouter, Depends, HTTPException, Query
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional
import logging

from auth import get_current_user
import database as db
from utils.bot_state import normalize_bot_state
from services.hold_policy import resolve_hold_policy
from services.canonical import get_canonical_open_position_count, get_latest_bot_decisions
from services.target_policy import derive_targets
from services.truth_normalizer import normalize_bot_trade_truth
from services.fx_normalizer import get_quote_currency, to_display_zar, get_fx_rate
from services.reconciliation import compute_equity_zar
from config import PAPER_SUPPORTED_EXCHANGES

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/radar", tags=["Radar"])

RISK_THRESHOLD_PCT = 0.03             # 3% unrealized loss triggers risk exit
EXIT_FORECAST_TIME_THRESHOLD = 600    # 600 seconds (10 min) — time exit proximity threshold
NO_STOP_DISTANCE = 999.0              # sentinel — distance when no stop price is configured


def _safe_float(value, default: float) -> float:
    """Convert value to float safely, returning default for None/empty/NaN/Inf/invalid."""
    if value is None or value == "":
        return default
    try:
        result = float(value)
        if math.isnan(result) or math.isinf(result):
            return default
        return result
    except (TypeError, ValueError):
        return default


def _first_non_none(*values):
    """Return the first value that is not None."""
    for v in values:
        if v is not None:
            return v
    return None


def _configured_bot_pct(bot: Dict, *keys: str) -> Optional[float]:
    """Return first configured non-negative percentage from bot payload keys."""
    for key in keys:
        value = bot.get(key)
        if value is None:
            continue
        try:
            pct = float(value)
        except (TypeError, ValueError):
            continue
        return max(0.0, pct)
    return None


def _format_hold_timer(elapsed_seconds: float) -> str:
    """Human-readable hold timer like '2h 15m' or '45s'."""
    if elapsed_seconds < 60:
        return f"{int(elapsed_seconds)}s"
    if elapsed_seconds < 3600:
        return f"{int(elapsed_seconds // 60)}m {int(elapsed_seconds % 60)}s"
    hours = int(elapsed_seconds // 3600)
    mins = int((elapsed_seconds % 3600) // 60)
    return f"{hours}h {mins}m"


def _compute_exit_forecast(
    entry_price: float,
    current_price: float,
    target_price: Optional[float],
    stop_price: Optional[float],
    remaining_seconds: float,
    unrealized_pnl: float,
) -> Optional[str]:
    """Forecast the most likely exit scenario."""
    if remaining_seconds < EXIT_FORECAST_TIME_THRESHOLD:
        return "likely_time_exit"
    if unrealized_pnl < 0:
        return "at_risk"
    if target_price and entry_price > 0:
        dist_to_target = abs(target_price - current_price) / entry_price
        dist_to_stop = abs(current_price - stop_price) / entry_price if stop_price else NO_STOP_DISTANCE
        if dist_to_target <= dist_to_stop or current_price >= entry_price:
            return "likely_target"
        return "holding"
    return "holding"


def _compute_radar_entry(bot: Dict, open_trade: Optional[Dict], now: datetime) -> Dict:
    """Build a single radar entry from bot + its current open trade."""
    bot_id = str(bot.get("id") or bot.get("_id") or bot.get("bot_id", ""))
    hold_policy = resolve_hold_policy(bot, open_trade=open_trade)
    max_hold = int(hold_policy["max_hold_seconds"])
    capital = _safe_float(bot.get("current_capital", bot.get("initial_capital")), 0.0)

    # ── Target policy: bot-configured pcts take priority, then V2, then legacy ────
    _raw_daily_pct = bot.get("daily_profit_target_pct")
    if _raw_daily_pct is None:
        _raw_daily_pct = bot.get("daily_target_pct")
    _raw_trade_pct = bot.get("trade_profit_target_pct")
    if _raw_trade_pct is None:
        _raw_trade_pct = bot.get("per_trade_target_pct")
    if _raw_trade_pct is None:
        _raw_trade_pct = bot.get("trade_target_pct")
    _configured_daily_pct = _safe_float(_raw_daily_pct, None)
    _configured_trade_pct = _safe_float(_raw_trade_pct, None)

    if _configured_daily_pct is not None and _configured_trade_pct is not None and capital > 0:
        # Bot-level configured targets override engine defaults
        daily_target = round(capital * _configured_daily_pct, 2)
        trade_target = round(capital * _configured_trade_pct, 2)
        target_source = "configured"
        daily_target_pct = round(_configured_daily_pct * 100, 4)
        trade_target_pct = round(_configured_trade_pct * 100, 4)
    else:
        _use_v2_targets = False
        try:
            from config import NEW_TRADING_BRAIN_V2
            _use_v2_targets = NEW_TRADING_BRAIN_V2 and capital > 0
        except ImportError:
            pass

        if _use_v2_targets:
            try:
                from services.trading_brain_v2 import TargetPolicyV2
                _tpv2 = TargetPolicyV2()
                bot_type_str = str(bot.get("bot_type") or "normal").lower()
                exchange_str = str(bot.get("exchange") or "binance").lower()
                quote_currency = "ZAR" if exchange_str == "luno" else "USDT"
                _v2t = _tpv2.compute(
                    bot_type=bot_type_str,
                    venue=exchange_str,
                    quote_currency=quote_currency,
                    bot_equity=capital,
                    notional=capital * 0.02,
                    all_in_cost_bps=0.0,
                    entry_price=0.0,
                    side="buy",
                )
                daily_target = _v2t.get("daily_profit_target_quote")
                trade_target = _v2t.get("trade_profit_target_quote")
                target_source = "target_policy_v2"
                daily_target_pct = round(_v2t.get("daily_target_pct", 0) or 0, 4)
                trade_target_pct = round(_v2t.get("trade_target_pct", 0) or 0, 4)
            except Exception as _v2_err:
                logger.warning("TargetPolicyV2 compute failed, falling back to legacy derive_targets: %s", _v2_err)
                _use_v2_targets = False

        if not _use_v2_targets:
            targets = derive_targets(bot)
            daily_target = targets["daily_profit_target"]
            trade_target = targets["trade_profit_target"]
            target_source = targets["target_source"]
            daily_target_pct = targets["daily_target_pct"]
            trade_target_pct = targets["trade_target_pct"]

    # ── Canonical display currency contract ──────────────────────────────────
    # quote_currency = native trading currency for this bot
    # display_currency = always "ZAR" (user-facing canonical)
    # *_display fields = ZAR-converted values for UI rendering
    _exchange_str = str(bot.get("exchange") or "").lower()
    _symbol_str = str(bot.get("pair") or bot.get("symbol") or "")
    _quote_currency = get_quote_currency(_exchange_str, _symbol_str)
    _fx_rate, _fx_source = get_fx_rate(_quote_currency, "ZAR")
    # Canonical funding truth fields — read from stored bot record when available.
    # These are written at bot-creation time by the validator (bot_validator.py).
    _canonical_base_zar = _safe_float(bot.get("canonical_base_capital_zar"), capital * _fx_rate)
    _fx_rate_at_creation = _safe_float(bot.get("fx_rate_at_creation"), _fx_rate)
    _funding_input_amount = _safe_float(bot.get("funding_input_amount"), _canonical_base_zar)
    _funding_input_currency = str(bot.get("funding_input_currency") or "ZAR").upper()

    def _to_zar(raw: Optional[float]) -> Optional[float]:
        """Convert a raw quote-currency value to ZAR for display."""
        if raw is None:
            return None
        return round(float(raw) * _fx_rate, 2)

    entry = {
        "bot_id": bot_id,
        "bot_type": bot.get("bot_type", "normal"),
        "name": bot.get("name", f"Bot-{bot_id[:6]}"),
        "exchange": bot.get("exchange", "unknown"),
        "symbol": bot.get("pair", bot.get("symbol", "unknown")),
        # ── Canonical display currency metadata ──────────────────────────
        # Semantics:
        #   funding_input_amount   — exact amount the user entered (always in funding_input_currency)
        #   funding_input_currency — currency the user entered (always "ZAR" for now)
        #   canonical_base_capital_zar — frozen ZAR economic base at creation (never mutated)
        #   fx_rate_at_creation    — FX rate frozen when bot was created
        #   funding_currency       — the currency the user funded this bot in
        #   funding_amount         — the amount in native quote currency
        #   quote_currency         — the native trading quote currency (may differ from
        #                            funding currency if FX conversion occurred)
        #   display_currency       — always "ZAR" (canonical user-facing currency)
        #   capital_allocated      — capital in quote_currency (native trading units)
        #   capital_allocated_display — capital converted to ZAR for display
        #
        # Example — Binance bot funded with R1000 ZAR:
        #   funding_input_amount   = 1000.0  (what the user typed)
        #   funding_input_currency = "ZAR"
        #   canonical_base_capital_zar = 1000.0  (frozen at creation)
        #   fx_rate_at_creation    = 19.0
        #   quote_currency         = "USDT"
        #   capital_allocated      = 52.63 (USDT — execution amount)
        #   capital_allocated_display = 1000.0 (ZAR — display amount)
        #
        # Example — Luno bot funded with R1000 ZAR:
        #   funding_input_amount   = 1000.0
        #   funding_input_currency = "ZAR"
        #   canonical_base_capital_zar = 1000.0
        #   fx_rate_at_creation    = 1.0
        #   quote_currency         = "ZAR"
        #   capital_allocated      = 1000.0 (ZAR)
        #   capital_allocated_display = 1000.0 (ZAR, no conversion)
        "quote_currency": _quote_currency,
        "display_currency": "ZAR",
        "fx_rate_used": _fx_rate,
        "fx_source": _fx_source,
        "fx_rate_at_creation": _fx_rate_at_creation,
        "canonical_base_capital_zar": _canonical_base_zar,
        "funding_input_amount": _funding_input_amount,
        "funding_input_currency": _funding_input_currency,
        # Funding semantics — always expose the user-facing ZAR entry so that
        # Luno and non-Luno bots display a consistent R-amount here.
        # capital_allocated (below) carries the native quote-currency amount.
        "funding_currency": "ZAR",
        "funding_amount": _canonical_base_zar,
        "side": None,
        "entry_price": None,
        "current_price": None,
        "target_price": None,
        "stop_price": None,
        "trailing_stop_price": None,
        "realized_pnl_today": _safe_float(bot.get("realized_pnl_today"), 0.0),
        "realized_pnl_today_display": _to_zar(_safe_float(bot.get("realized_pnl_today"), 0.0)),
        "unrealized_pnl": 0.0,
        "unrealized_pnl_display": 0.0,
        "capital_allocated": capital,
        # Display is always the ZAR canonical base so non-Luno bots show R1000
        # instead of a FX-converted USDT amount.  canonical_base_capital_zar is
        # the frozen ZAR value written at bot creation and never changes.
        "capital_allocated_display": _to_zar(capital) if _quote_currency == "ZAR" else _canonical_base_zar,
        "capital_summary": bot.get("capital_summary", {}),
        "exposure_pct": 0.0,
        "daily_profit_target": daily_target,
        "daily_profit_target_display": _to_zar(daily_target),
        "trade_profit_target": trade_target,
        "trade_profit_target_display": _to_zar(trade_target),
        "daily_target_pct": daily_target_pct,
        "trade_target_pct": trade_target_pct,
        "target_source": target_source,
        "position_opened_at": None,
        "max_hold_seconds": max_hold,
        "hold_policy_source": hold_policy["source"],
        "remaining_hold_seconds": None,
        "hold_timer_display": None,
        "next_action": "WAIT",
        "next_action_reason_code": "NO_POSITION",
        "next_action_reason_text": "No open position – waiting for entry signal",
        "market_regime": bot.get("market_regime") if bot.get("market_regime") is not None else "unknown",
        "regime_confidence": _safe_float(_first_non_none(bot.get("canonical_regime_confidence"), bot.get("confidence_score"), bot.get("confidence")), 0.0),
        "confidence_score": _safe_float(_first_non_none(bot.get("confidence_score"), bot.get("confidence")), 0.0),
        "decision_reason_code": bot.get("decision_reason_code", bot.get("last_decision_reason_code")),
        "entry_reason_code": bot.get("entry_reason_code", bot.get("last_entry_reason_code")),
        "entry_confidence_score": _safe_float(bot.get("entry_confidence_score", bot.get("last_entry_confidence_score")), 0.0),
        "expectancy_net_edge_pct": _safe_float(bot.get("expectancy_net_edge_pct"), 0.0),
        "strategy_name": bot.get("strategy", bot.get("strategy_type", "balanced")),
        "regime_tag": bot.get("market_regime") if bot.get("market_regime") is not None else "unknown",
        "exit_forecast": None,
        "spread_estimate": bot.get("spread_estimate"),
        "slippage_estimate": bot.get("slippage_estimate"),
        "lifecycle_stage": bot.get("lifecycle_stage", "unknown"),
        "eligible_to_trade": bot.get("eligible_to_trade", False),
        "not_eligible_reasons": bot.get("not_eligible_reasons", []),
        "activity_state": bot.get("activity_state", "active_record"),
        "activity_reason_code": bot.get("activity_reason_code"),
        "runnable": bot.get("eligible_to_trade", False),
        "has_open_position": bool(open_trade),
        # V2 render-safe fields (always present, never NaN/None for numerics)
        "regime_label": str(bot.get("regime_label", bot.get("market_regime", "unknown")) or "unknown"),
        "expected_gross_edge_bps": _safe_float(bot.get("expected_gross_edge_bps"), 0.0),
        "all_in_cost_bps": _safe_float(bot.get("all_in_cost_bps"), 0.0),
        "expected_net_edge_bps": _safe_float(bot.get("expected_net_edge_bps"), 0.0),
        "projected_net_profit_quote": _safe_float(bot.get("projected_net_profit_quote"), 0.0),
        "projected_net_profit_display": _to_zar(_safe_float(bot.get("projected_net_profit_quote"), 0.0)),
        "trade_profit_target_quote": _safe_float(bot.get("trade_profit_target_quote"), trade_target),
        "daily_profit_target_quote": _safe_float(bot.get("daily_profit_target_quote"), daily_target),
        "cost_floor_source": str(bot.get("cost_floor_source", "") or ""),
    }
    if not open_trade and not entry["eligible_to_trade"]:
        reasons = entry.get("not_eligible_reasons") or []
        if not reasons:
            # Derive a truthful reason from the bot's actual state instead of
            # the generic "eligibility_gate_blocked" catch-all.  This makes the
            # radar show actionable information when the scheduler hasn't yet
            # evaluated the bot (e.g. immediately after batch-create).
            bot_status = bot.get("status", "unknown")
            pause_reason = bot.get("pause_reason") or bot.get("paused_reason")
            if bot_status == "paused":
                reasons = [str(pause_reason) if pause_reason else "bot_paused"]
            elif bot_status == "stopped":
                reasons = ["bot_stopped"]
            elif bot_status == "quarantined":
                reasons = ["bot_quarantined"]
            elif bot_status not in ("active", "running"):
                reasons = [f"bot_status_{bot_status}"]
            elif bot.get("paused_by_system"):
                reasons = [str(pause_reason) if pause_reason else "paused_by_system"]
            elif bot.get("paused_by_user"):
                reasons = [str(pause_reason) if pause_reason else "paused_by_user"]
            else:
                # Bot is active but eligible_to_trade is False — check stored
                # reason codes before falling back to the generic code.
                fallback_reason = (
                    entry.get("activity_reason_code")
                    or entry.get("decision_reason_code")
                    or entry.get("entry_reason_code")
                    or "eligibility_gate_blocked"
                )
                reasons = [str(fallback_reason)]
            entry["not_eligible_reasons"] = reasons
        human_reason = ", ".join(reasons) if reasons else "eligibility checks blocked this bot"
        entry["next_action_reason_text"] = f"Waiting: {human_reason}"

    if open_trade:
        side = open_trade.get("side", open_trade.get("type", "buy")).lower()
        entry_price = _safe_float(open_trade.get("entry_price", open_trade.get("price")), 0.0)
        current_price = _safe_float(open_trade.get("current_price"), entry_price)
        tp = open_trade.get("take_profit", open_trade.get("target_price"))
        sl = open_trade.get("stop_loss", open_trade.get("stop_price"))
        trailing = open_trade.get("trailing_stop", open_trade.get("trailing_stop_price"))

        opened_at_raw = open_trade.get("opened_at", open_trade.get("timestamp", open_trade.get("created_at")))
        if isinstance(opened_at_raw, str):
            try:
                opened_at = datetime.fromisoformat(opened_at_raw.replace("Z", "+00:00"))
            except Exception:
                opened_at = now
        elif isinstance(opened_at_raw, datetime):
            opened_at = opened_at_raw if opened_at_raw.tzinfo else opened_at_raw.replace(tzinfo=timezone.utc)
        else:
            opened_at = now

        elapsed = (now - opened_at).total_seconds()
        remaining = max(0, max_hold - elapsed)

        # Unrealized PnL
        qty = _safe_float(open_trade.get("quantity", open_trade.get("qty", open_trade.get("amount"))), 0.0)
        if side == "buy":
            unrealized = (current_price - entry_price) * qty
        else:
            unrealized = (entry_price - current_price) * qty

        # Determine next action
        if remaining <= 0:
            action = "FORCE_EXIT"
            code = "TIME_EXIT"
            text = "Max hold time exceeded – forcing exit"
        elif unrealized <= -(capital * RISK_THRESHOLD_PCT):
            action = "STOP_EXIT"
            code = "RISK_EXIT"
            text = "Unrealized loss exceeds risk threshold"
        elif tp and current_price >= float(tp) and side == "buy":
            action = "TARGET_EXIT"
            code = "TARGET_EXIT"
            text = "Price reached take-profit target"
        elif sl and current_price <= float(sl) and side == "buy":
            action = "STOP_EXIT"
            code = "STOP_EXIT"
            text = "Price hit stop-loss"
        elif trailing and side == "buy" and current_price <= float(trailing):
            action = "TRAIL_EXIT"
            code = "TRAIL_EXIT"
            text = "Trailing stop triggered"
        elif remaining < 600:
            action = "WARN_EXIT"
            code = "TIME_WARNING"
            text = f"Position closing in {int(remaining)}s"
        else:
            action = "HOLD"
            code = "POSITION_OPEN"
            text = f"Holding position – {int(remaining)}s remaining"

        # Symbol: use trade's pair/symbol when available (fixes "unknown" when
        # bot.pair is missing but trade has the canonical trading pair).
        trade_symbol = _first_non_none(
            open_trade.get("pair"),
            open_trade.get("symbol"),
            open_trade.get("trading_pair"),
        )
        resolved_symbol = trade_symbol if trade_symbol else entry["symbol"]

        # Regime: prefer trade canonical fields; fall back to bot fields.
        resolved_regime = (
            open_trade.get("canonical_market_regime")
            or open_trade.get("market_regime")
            or open_trade.get("regime")
            or entry["market_regime"]
        )
        resolved_regime_confidence = _safe_float(
            _first_non_none(
                open_trade.get("canonical_regime_confidence"),
                open_trade.get("regime_confidence"),
            ),
            entry["regime_confidence"],
        )

        entry.update({
            "symbol": resolved_symbol,
            "side": side,
            "entry_price": entry_price,
            "current_price": current_price,
            "target_price": float(tp) if tp else None,
            "stop_price": float(sl) if sl else None,
            "trailing_stop_price": float(trailing) if trailing else None,
            "market_regime": resolved_regime,
            "regime_confidence": resolved_regime_confidence,
            "regime_label": str(resolved_regime or "unknown"),
            "unrealized_pnl": round(unrealized, 2),
            "unrealized_pnl_display": _to_zar(round(unrealized, 2)),
            "exposure_pct": round(abs(unrealized) / capital * 100, 2) if capital > 0 else 0.0,
            "position_opened_at": opened_at.isoformat(),
            "remaining_hold_seconds": round(remaining),
            "hold_timer_display": _format_hold_timer(elapsed),
            "next_action": action,
            "next_action_reason_code": code,
            "next_action_reason_text": text,
            "decision_reason_code": open_trade.get("trade_close_reason_code") or open_trade.get("reason_code") or code,
            "entry_reason_code": open_trade.get("entry_reason_code") or open_trade.get("reason_code"),
            "entry_confidence_score": _safe_float(open_trade.get("entry_confidence_score"), entry["entry_confidence_score"]),
            "expectancy_net_edge_pct": _safe_float(open_trade.get("expectancy_net_edge_pct"), entry["expectancy_net_edge_pct"]),
            "exit_forecast": _compute_exit_forecast(
                entry_price, current_price, float(tp) if tp else None,
                float(sl) if sl else None, remaining, unrealized
            ),
        })
        # Apply canonical truth normalizer overlay for consistent cross-endpoint values.
        # normalize_bot_trade_truth guarantees safe (non-NaN, non-None) values so we
        # can safely overwrite the fields to ensure radar/status/trades consistency.
        _truth = normalize_bot_trade_truth(bot, open_trade)
        for _key in ("symbol", "market_regime", "regime_confidence", "entry_confidence_score",
                     "expectancy_net_edge_pct", "decision_reason_code", "entry_reason_code",
                     "expected_gross_edge_bps", "all_in_cost_bps", "expected_net_edge_bps",
                     "projected_net_profit_quote"):
            entry[_key] = _truth[_key]

    return entry


@router.get("/snapshot")
async def radar_snapshot(user_id: str = Depends(get_current_user)):
    """
    GET /api/radar/snapshot

    Returns per-bot radar data derived from ledger/trade truth.
    Shows each bot's current position on a live price line with
    entry → current → target → stop and time-remaining info.
    """
    now = datetime.now(timezone.utc)

    try:
        # Fetch only non-deleted active/paused bots for user
        bots_cursor = db.bots_collection.find(
            {
                "user_id": user_id,
                "status": {"$nin": ["deleted", "marked_for_deletion"]},
                "deleted": {"$ne": True},
                "is_deleted": {"$ne": True},
                "deleted_at": {"$exists": False},
            },
        )
        bots = await bots_cursor.to_list(length=200)
        bot_ids = [str(b.get("id") or b.get("_id") or "") for b in bots if b.get("id") or b.get("_id")]
        latest_decisions = await get_latest_bot_decisions(user_id, bot_ids)

        radar_entries: List[Dict] = []

        # One-shot wallet check for this user — used to enrich live eligibility
        # context without making per-bot async calls.
        try:
            from services.paper_wallet_service import paper_wallet_service as _pws
            _wallet = await _pws.get_balances(user_id)
            _wallet_funded = float(_wallet.get("total", 0) or 0) > 0
        except Exception as _wallet_err:
            logger.warning("radar_snapshot: wallet balance check failed for user %s: %s", user_id[:8], _wallet_err)
            _wallet_funded = True  # assume funded on error so bots are not falsely blocked

        for raw_bot in bots:
            # Use the canonical string bot ID (not MongoDB _id) — trades are stored with bot.id
            bot_id = raw_bot.get("id") or str(raw_bot.get("_id", ""))
            decision_overlay = latest_decisions.get(str(bot_id), {})
            decision_fallback = {
                key: value
                for key, value in decision_overlay.items()
                if key not in raw_bot or raw_bot.get(key) in (None, "", [])
            }
            bot = normalize_bot_state({**raw_bot, **decision_fallback})

            # Find open trade for this bot FIRST — needed for eligibility check below.
            open_trade = await db.trades_collection.find_one(
                {"bot_id": bot_id, "status": {"$in": ["open", "active", "pending"]}},
                sort=[("timestamp", -1)],
            )

            # Compute live eligibility when the DB field is absent or False.
            # eligible_to_trade is written by the paper engine during ticks, but
            # may be stale (e.g. immediately after bot creation or after a reset).
            # We recompute it here so the radar always shows the current truth.
            if not bot.get("eligible_to_trade") and not open_trade:
                _bot_status = raw_bot.get("status", "unknown")
                _exchange_ok = raw_bot.get("exchange", "").lower() in PAPER_SUPPORTED_EXCHANGES
                _live_eligible = (
                    _bot_status in ("active", "running")
                    and _wallet_funded
                    and _exchange_ok
                )
                if _live_eligible:
                    bot["eligible_to_trade"] = True
                    bot["not_eligible_reasons"] = []
                elif not bot.get("not_eligible_reasons"):
                    # Set truthful reason so the UI can show actionable information
                    _live_reasons: List[str] = []
                    if _bot_status not in ("active", "running"):
                        _pause_reason = raw_bot.get("pause_reason") or raw_bot.get("paused_reason")
                        _live_reasons.append(
                            str(_pause_reason) if _pause_reason else f"bot_status_{_bot_status}"
                        )
                    if not _wallet_funded:
                        _live_reasons.append("wallet_insufficient")
                    if not _exchange_ok:
                        _live_reasons.append("exchange_not_configured")
                    bot["not_eligible_reasons"] = _live_reasons or ["eligibility_gate_blocked"]

            radar_entries.append(_compute_radar_entry(bot, open_trade, now))

        return {
            "timestamp": now.isoformat(),
            "total_bots": len(radar_entries),
            "bots_with_positions": await get_canonical_open_position_count(user_id),
            "radar": radar_entries,
        }
    except Exception as e:
        logger.error(f"Radar snapshot error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Radar snapshot failed: {e}")


@router.get("/timeseries")
async def radar_timeseries(
    user_id: str = Depends(get_current_user),
    bot_type: Optional[str] = Query(None, regex="^(normal|scalper)$"),
    hours: int = Query(24, ge=1, le=168),
):
    """Return hourly-bucketed timeseries for equity, PnL, bot counts, activity.

    Derived from ledger/trades truth. Supports normal/scalper split.
    """
    now = datetime.now(timezone.utc)
    since = now - timedelta(hours=hours)

    # Build bot filter
    bot_query: Dict = {"user_id": user_id, "deleted": {"$ne": True}}
    if bot_type:
        bot_query["bot_type"] = bot_type

    bots = await db.bots_collection.find(bot_query).to_list(500)
    bot_ids = [str(b.get("_id", b.get("bot_id", b.get("id", "")))) for b in bots]

    # Fetch trades in window
    trade_query: Dict = {"user_id": user_id, "timestamp": {"$gte": since.isoformat()}}
    if bot_type and bot_ids:
        trade_query["bot_id"] = {"$in": bot_ids}

    trades = await db.trades_collection.find(trade_query).sort("timestamp", 1).to_list(5000)

    # Bucket into hourly slots
    buckets: Dict = {}
    for h in range(hours + 1):
        t = since + timedelta(hours=h)
        key = t.strftime("%Y-%m-%dT%H:00:00Z")
        buckets[key] = {"timestamp": key, "pnl": 0.0, "trade_count": 0, "equity": 0.0}

    cumulative_pnl = 0.0
    # compute_equity_zar converts each bot's capital to ZAR using the stored
    # canonical_base_capital_zar / fx_rate so USDT bots are not raw-summed with ZAR bots.
    base_equity, _equity_breakdown = compute_equity_zar(bots)

    for trade in trades:
        ts = trade.get("timestamp", "")
        try:
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00")) if isinstance(ts, str) else ts
            key = dt.strftime("%Y-%m-%dT%H:00:00Z")
        except Exception:
            continue
        if key in buckets:
            pnl = _safe_float(trade.get("pnl", trade.get("profit", 0)) or 0, 0.0)
            cumulative_pnl += pnl
            buckets[key]["pnl"] += pnl
            buckets[key]["trade_count"] += 1

    # Fill equity as base + cumulative
    running = 0.0
    for key in sorted(buckets.keys()):
        running += buckets[key]["pnl"]
        buckets[key]["equity"] = round(base_equity + running, 2)
        buckets[key]["pnl"] = round(buckets[key]["pnl"], 2)

    series = [buckets[k] for k in sorted(buckets.keys())]

    return {
        "series": series,
        "bot_count": len(bots),
        "bot_type": bot_type or "all",
        "hours": hours,
        "timestamp": now.isoformat(),
    }
