"""
Bot Eligibility Logger — Structured Reason Codes
=================================================
Provides a canonical set of skip/block reason codes and a structured log
emitter so every ineligible bot is annotated with a machine-readable reason.

Usage in trading_scheduler.py or paper_trading_engine.py:
    from services.bot_eligibility_logger import elig_log

    elig_log.skip(bot, reason_code=EligibilityCode.SPREAD_TOO_WIDE,
                  details={"spread_pct": 0.31, "max_allowed_pct": 0.25})

    elig_log.allow(bot, details={"regime": "consolidation", "confidence": 0.41})

The structured events are also written to the bot document's `last_eligibility`
field via MongoDB, making them available to all monitoring APIs.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Canonical eligibility reason codes
# All skip/block decisions in the system must use one of these codes.
# ---------------------------------------------------------------------------

class EligibilityCode(str, Enum):
    # ── Trade entry blocks ──────────────────────────────────────────────────
    ALLOWED                   = "allowed"
    SPREAD_TOO_WIDE           = "spread_too_wide"
    LOW_CONFIDENCE            = "low_confidence"
    HARD_EDGE_FILTER          = "hard_edge_filter"
    EDGE_GATE                 = "edge_gate"
    NO_USABLE_SIGNAL          = "no_usable_signal"
    BEARISH_LONG_BLOCKED      = "bearish_long_blocked"
    LOW_EXPECTANCY            = "low_expectancy"
    HURST_MISMATCH            = "hurst_mismatch"
    REGIME_STAND_DOWN         = "regime_standdown"
    ADAPTIVE_STAND_DOWN       = "adaptive_stand_down"
    OPEN_POSITION_ACTIVE      = "open_position_active"

    # ── System / infrastructure blocks ─────────────────────────────────────
    NO_PRICE_DATA             = "no_price_data"
    EXCHANGE_EXPOSURE         = "exchange_exposure"
    DRAWDOWN_LIMIT            = "drawdown_limit"
    PAIR_NOT_ALLOWED          = "pair_not_allowed"
    LOW_LIQUIDITY             = "low_liquidity"
    MODE_DISABLED             = "mode_disabled"
    EMERGENCY_STOP            = "emergency_stop"
    BUDGET_EXHAUSTED          = "budget_exhausted"
    USER_PAUSED               = "user_paused"
    UNSUPPORTED_EXCHANGE      = "unsupported_exchange"
    SYMBOL_COOLDOWN           = "symbol_cooldown"
    PORTFOLIO_GUARD           = "portfolio_guard"

    # ── Growth / auto-spawn blocks ──────────────────────────────────────────
    GROWTH_CAP_REACHED        = "growth_cap_reached"
    GROWTH_STALE_BOTS         = "growth_stale_bots"
    GROWTH_INSUFFICIENT_FUNDS = "growth_insufficient_funds"

    # ── Scalper-specific blocks ─────────────────────────────────────────────
    SCALPER_EV_TOO_LOW        = "scalper_ev_too_low"
    SCALPER_SPREAD_TOO_WIDE   = "scalper_spread_too_wide"

    # ── Signal / data quality blocks ────────────────────────────────────────
    SIGNAL_MISMATCH           = "signal_mismatch"
    EXPECTANCY_GATE           = "expectancy_gate"
    PNL_VALIDATION_FAILED     = "pnl_validation_failed"

    # ── Close-path blocks (trade open, exit attempted but no condition met) ─
    CLOSE_EXCEPTION           = "close_exception"
    OPEN_TRADE_CLOSE_FAILED   = "open_trade_close_failed"

    # ── Runtime / cycle errors ───────────────────────────────────────────────
    CYCLE_ERROR               = "cycle_error"
    TRADE_REJECTED            = "trade_rejected"

    # ── Entry-quality blocks (Phase 1–4) ────────────────────────────────────
    LOSS_COOLDOWN             = "loss_cooldown"
    LOW_VOLATILITY_BLOCK      = "low_volatility_block"
    EDGE_BELOW_COST           = "edge_below_cost"

    # ── Symbol-level stagnation cooldown (Luno normal) ───────────────────────
    STAGNATION_SYMBOL_COOLDOWN = "stagnation_symbol_cooldown"

    # ── Luno-normal hard entry gates ─────────────────────────────────────────
    LUNO_MIN_EDGE_NOT_MET       = "luno_min_edge_not_met"
    LUNO_NO_TRADE_CONSOLIDATION = "luno_no_trade_consolidation"
    TRADE_TOO_SMALL_FOR_LUNO    = "trade_too_small_for_luno"

    # ── Exchange-strategy compatibility ──────────────────────────────────────
    STRATEGY_EXCHANGE_INCOMPATIBLE = "strategy_exchange_incompatible"

    # ── Symbol integrity ─────────────────────────────────────────────────────
    SYMBOL_STATE_MISMATCH         = "symbol_state_mismatch"

    # ── Catch-all (use only when no specific code applies) ──────────────────
    UNKNOWN                   = "unknown"


# Human-readable descriptions for each code (used in UI tooltips)
ELIGIBILITY_DESCRIPTIONS: Dict[str, str] = {
    EligibilityCode.ALLOWED:                  "Bot is eligible to trade",
    EligibilityCode.SPREAD_TOO_WIDE:          "Market bid/ask spread exceeds max allowed %",
    EligibilityCode.LOW_CONFIDENCE:           "Composite signal confidence below threshold",
    EligibilityCode.HARD_EDGE_FILTER:         "Net edge (expected move − costs) is negative or zero",
    EligibilityCode.EDGE_GATE:                "Expected move < required move (cost + safety buffer)",
    EligibilityCode.NO_USABLE_SIGNAL:         "ML prediction is zero and OHLCV fallback returned nothing",
    EligibilityCode.BEARISH_LONG_BLOCKED:     "Signals strongly bearish — long entry blocked",
    EligibilityCode.LOW_EXPECTANCY:           "Estimated expectancy in ZAR below minimum threshold",
    EligibilityCode.HURST_MISMATCH:           "Hurst exponent indicates regime mismatch for this bot type",
    EligibilityCode.REGIME_STAND_DOWN:        "Market regime is stand-down (extreme volatile downtrend)",
    EligibilityCode.ADAPTIVE_STAND_DOWN:      "Consecutive losses triggered adaptive stand-down period",
    EligibilityCode.OPEN_POSITION_ACTIVE:     "Bot already has an open trade position",
    EligibilityCode.NO_PRICE_DATA:            "Exchange returned no valid price data",
    EligibilityCode.EXCHANGE_EXPOSURE:        "Exchange capital exposure exceeds platform limit",
    EligibilityCode.DRAWDOWN_LIMIT:           "Account drawdown exceeds configured maximum",
    EligibilityCode.PAIR_NOT_ALLOWED:         "Trading pair is not in the allowed whitelist",
    EligibilityCode.LOW_LIQUIDITY:            "Order book depth below minimum required notional",
    EligibilityCode.MODE_DISABLED:            "Autopilot trading mode is disabled",
    EligibilityCode.EMERGENCY_STOP:           "Emergency stop is activated",
    EligibilityCode.BUDGET_EXHAUSTED:         "Bot's trading capital is below minimum threshold",
    EligibilityCode.USER_PAUSED:              "Bot was manually paused by user",
    EligibilityCode.UNSUPPORTED_EXCHANGE:     "Exchange is not supported for paper trading",
    EligibilityCode.SYMBOL_COOLDOWN:          "Pair is in cooldown period after recent trade",
    EligibilityCode.PORTFOLIO_GUARD:          "Portfolio guard: same symbol already in too many bots",
    EligibilityCode.GROWTH_CAP_REACHED:       "Exchange bot cap reached — cannot spawn more bots",
    EligibilityCode.GROWTH_STALE_BOTS:        "Stale paused bots are consuming cap slots",
    EligibilityCode.GROWTH_INSUFFICIENT_FUNDS:"Insufficient capital for new bot spawn",
    EligibilityCode.SCALPER_EV_TOO_LOW:       "Scalper: expected value below minimum for this spread",
    EligibilityCode.SCALPER_SPREAD_TOO_WIDE:  "Scalper: spread exceeds SCALPER_MAX_SPREAD_PCT",
    EligibilityCode.SIGNAL_MISMATCH:          "Signal direction contradicts predicted price change — corrupt signal skipped",
    EligibilityCode.EXPECTANCY_GATE:          "Estimated expectancy does not support trade (edge − costs < threshold)",
    EligibilityCode.PNL_VALIDATION_FAILED:    "Exit P&L failed validation check — trade held open",
    EligibilityCode.CLOSE_EXCEPTION:          "Trade close attempt raised an exception — trade being monitored",
    EligibilityCode.OPEN_TRADE_CLOSE_FAILED:  "Trade close failed and was abandoned — marked as failed",
    EligibilityCode.CYCLE_ERROR:              "Unhandled error during trading cycle execution",
    EligibilityCode.TRADE_REJECTED:           "Trade rejected by execution layer (entry conditions not met)",
    EligibilityCode.LOSS_COOLDOWN:            "Post-loss cooldown active — bot waiting before re-entry after a losing trade",
    EligibilityCode.LOW_VOLATILITY_BLOCK:     "Market volatility too low — 10-candle price range below minimum threshold",
    EligibilityCode.EDGE_BELOW_COST:          "Expected move below cost × multiplier — insufficient structural edge over fees+spread",
    EligibilityCode.STAGNATION_SYMBOL_COOLDOWN: "Symbol in post-stagnation cooldown — Luno normal bots blocked from re-entering this pair after a stagnation or fee-break-even exit",
    EligibilityCode.STRATEGY_EXCHANGE_INCOMPATIBLE: "Strategy is not compatible with this exchange — see strategy registry notes",
    EligibilityCode.SYMBOL_STATE_MISMATCH:          "Symbol integrity violation: market snapshot was for a different symbol than requested — trade blocked to prevent wrong-symbol execution",
    EligibilityCode.LUNO_MIN_EDGE_NOT_MET:      "Luno normal: expected move < 2.5% hard floor — insufficient edge to clear Luno fees and spread",
    EligibilityCode.LUNO_NO_TRADE_CONSOLIDATION: "Luno normal: consolidation/choppy regime detected — no trade in flat/sideways market",
    EligibilityCode.TRADE_TOO_SMALL_FOR_LUNO:   "Luno normal: trade size below 400 ZAR minimum — small trades eaten by Luno fees and spread",
    EligibilityCode.UNKNOWN:                  "Ineligible for unspecified reason",
}


# ---------------------------------------------------------------------------
# Logger class
# ---------------------------------------------------------------------------

class BotEligibilityLogger:
    """
    Emits structured eligibility events for every bot decision.

    Every emitted event includes:
    - bot_id, bot_name, exchange, pair
    - decision: "allowed" or "blocked"
    - reason_code: EligibilityCode value
    - details: dict of numeric/string diagnostics
    - timestamp

    Events are logged at INFO level with the prefix [ELIG] for easy grepping,
    and optionally persisted to the bot document's `last_eligibility` field.
    """

    def _build_event(
        self,
        bot: Dict[str, Any],
        decision: str,
        reason_code: EligibilityCode,
        details: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        return {
            "bot_id":       bot.get("id", "?"),
            "bot_name":     bot.get("name", "?"),
            "exchange":     bot.get("exchange", "?"),
            "pair":         bot.get("pair", "?"),
            "bot_type":     bot.get("bot_type", "normal"),
            "decision":     decision,
            "reason_code":  str(reason_code),
            "description":  ELIGIBILITY_DESCRIPTIONS.get(reason_code, ""),
            "details":      details or {},
            "timestamp":    datetime.now(timezone.utc).isoformat(),
        }

    def skip(
        self,
        bot: Dict[str, Any],
        reason_code: EligibilityCode,
        details: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Log a bot being skipped/blocked."""
        event = self._build_event(bot, "blocked", reason_code, details)
        logger.info(
            "[ELIG] BLOCKED | %s | %s | %s | %s | %s",
            bot.get("name", "?"),
            bot.get("exchange", "?"),
            bot.get("pair", "?"),
            reason_code,
            details or {},
        )
        return event

    def allow(
        self,
        bot: Dict[str, Any],
        details: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Log a bot being allowed to trade."""
        event = self._build_event(bot, "allowed", EligibilityCode.ALLOWED, details)
        logger.info(
            "[ELIG] ALLOWED | %s | %s | %s | %s",
            bot.get("name", "?"),
            bot.get("exchange", "?"),
            bot.get("pair", "?"),
            details or {},
        )
        return event

    async def skip_and_persist(
        self,
        bot: Dict[str, Any],
        reason_code: EligibilityCode,
        details: Optional[Dict[str, Any]] = None,
        db_collection=None,
    ) -> Dict[str, Any]:
        """
        Log a skip and persist `last_eligibility` to MongoDB.
        Pass db_collection=db.bots_collection to enable persistence.
        """
        event = self.skip(bot, reason_code, details)

        if db_collection is not None:
            try:
                await db_collection.update_one(
                    {"id": bot.get("id")},
                    {"$set": {
                        "last_eligibility": event,
                        "last_eligibility_code": str(reason_code),  # top-level string for easy querying
                        "last_skip_reason":  str(reason_code),
                        "last_tick_at":      event["timestamp"],
                    }},
                )
            except Exception as err:
                logger.debug("last_eligibility persist failed (non-fatal): %s", err)

        return event

    @staticmethod
    def format_block_summary(events: list) -> str:
        """
        Format a human-readable block summary for log output.
        Useful for printing a batch summary at the end of a trading tick.
        """
        if not events:
            return "No blocked bots this tick."

        from collections import Counter
        codes = Counter(e.get("reason_code", "unknown") for e in events)
        parts = [f"{code}×{count}" for code, count in codes.most_common()]
        return f"Blocked {len(events)} bots: " + ", ".join(parts)


# Module-level singleton
elig_log = BotEligibilityLogger()

__all__ = ["elig_log", "EligibilityCode", "ELIGIBILITY_DESCRIPTIONS", "BotEligibilityLogger"]
