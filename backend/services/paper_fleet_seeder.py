"""
Paper Fleet Seeder — Canonical Seed Path
=========================================

Single source of truth for seeding a paper-trading bot fleet.

ALL reset and start-fresh flows must call ``seed_paper_fleet()`` from this
module.  No other module may contain inline bot-insertion logic for seeding.

Design principles
-----------------
- Exchange-aware: distributes bots across every exchange in *exchanges* list.
- Type-aware: creates the requested normal/scalper split per exchange.
- Capital-correct: uses ``resolve_capital_for_exchange`` so Luno bots store ZAR
  and Binance/KuCoin bots store USDT-converted capital.
- Default pairs: uses exchange-specific default pairs so radar/scheduler can
  immediately pick them up (engine replaces the pair on first tick).
- Non-duplicating: if an exchange already has >= requested bots of a type
  it is skipped, not over-seeded.
- Wallet-aware: auto-funds the ZAR wallet from PAPER_STARTING_CAPITAL_ZAR if
  the balance is 0 before distributing capital across bots.
- Never raises: any per-exchange failure is captured in the result summary so
  the calling reset endpoint can still succeed.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional
from uuid import uuid4

import database as db
from services.paper_wallet_service import paper_wallet_service

logger = logging.getLogger(__name__)

# Canonical default pair per exchange.  The trading engine replaces this on
# the first tick; having a real pair at creation time makes radar/diagnostics
# work immediately after a seed without waiting for the first scheduler tick.
_DEFAULT_PAIR: Dict[str, str] = {
    "luno": "BTC/ZAR",
    "binance": "BTC/USDT",
    "kucoin": "BTC/USDT",
    "bybit": "BTC/USDT",
    "kraken": "BTC/USDT",
    "bitget": "BTC/USDT",
    "gate": "BTC/USDT",
    "coinbase": "BTC/USDT",
}


def _default_pair_for(exchange: str) -> str:
    """Return the canonical default trading pair for *exchange*."""
    return _DEFAULT_PAIR.get(exchange.lower(), "BTC/USDT")


async def seed_paper_fleet(
    user_id: str,
    exchanges: List[str],
    normal_per_exchange: int = 5,
    scalper_per_exchange: int = 5,
    capital_zar_per_bot: float = 0.0,
    source: str = "auto_seed",
) -> Dict:
    """Create a paper-trading fleet for *user_id* across *exchanges*.

    Parameters
    ----------
    user_id:
        Authenticated user's ID.
    exchanges:
        Ordered list of exchange names to seed bots on (e.g. ["luno", "binance"]).
        Only exchanges in PAPER_SUPPORTED_EXCHANGES are processed; others are
        silently skipped.
    normal_per_exchange:
        Number of normal bots to create per exchange (default 5).
    scalper_per_exchange:
        Number of scalper bots to create per exchange (default 5).
    capital_zar_per_bot:
        ZAR economic base per bot.  When 0 (default), the function distributes
        PAPER_STARTING_CAPITAL_ZAR evenly across total_bots (min R1 000/bot).
    source:
        Origin label written into bot documents (e.g. "auto_seed", "api_seed").

    Returns
    -------
    dict with keys::

        {
            "bots_created": int,
            "bots_skipped": int,
            "by_exchange": {exchange: {"normal": int, "scalper": int}},
            "errors": [str],
        }

    Never raises — all errors are captured and returned in *errors*.
    """
    from config import PAPER_STARTING_CAPITAL_ZAR, BOT_MANUAL_MIN_CAPITAL_ZAR
    from config import PAPER_SUPPORTED_EXCHANGES
    from services.fx_normalizer import resolve_capital_for_exchange
    from services.bot_filters import bot_not_deleted_filter
    from rules import check_bot_cap_limit

    result: Dict = {
        "bots_created": 0,
        "bots_skipped": 0,
        "by_exchange": {},
        "errors": [],
    }

    if not exchanges:
        result["errors"].append("No exchanges provided — nothing to seed.")
        return result

    if normal_per_exchange < 0 or scalper_per_exchange < 0:
        result["errors"].append("Counts must be non-negative.")
        return result

    total_bots_requested = len(exchanges) * (normal_per_exchange + scalper_per_exchange)
    if total_bots_requested == 0:
        result["errors"].append("Both normal_per_exchange and scalper_per_exchange are 0 — nothing to seed.")
        return result

    # ── Capital per bot ───────────────────────────────────────────────────
    # Capital is derived from PAPER_STARTING_CAPITAL_ZAR distributed evenly
    # across all bots.  Each exchange wallet is auto-funded independently
    # inside the exchange loop below using the exchange's native currency.
    min_cap = float(BOT_MANUAL_MIN_CAPITAL_ZAR or 1000.0)
    if capital_zar_per_bot <= 0:
        capital_zar_per_bot = max(
            float(PAPER_STARTING_CAPITAL_ZAR or 30000.0) / total_bots_requested
            if total_bots_requested > 0
            else min_cap,
            min_cap,
        )
    else:
        capital_zar_per_bot = max(capital_zar_per_bot, min_cap)

    now_iso = datetime.now(timezone.utc).isoformat()

    for exchange in exchanges:
        exchange_lower = exchange.lower()
        if exchange_lower not in PAPER_SUPPORTED_EXCHANGES:
            logger.warning(
                "seed_paper_fleet: exchange %s not in PAPER_SUPPORTED_EXCHANGES — skipping",
                exchange_lower,
            )
            result["errors"].append(
                f"Exchange '{exchange_lower}' is not a supported paper exchange — skipped."
            )
            continue

        result["by_exchange"].setdefault(exchange_lower, {"normal": 0, "scalper": 0})

        # ── Ensure this exchange's paper wallet is funded ─────────────────
        # Each exchange wallet is funded independently. This block ONLY auto-funds
        # if the wallet is completely empty (not funded at all by the operator).
        # If already funded, the operator-provided amount is the hard truth.
        exch_wallet_funded_zar = 0.0
        try:
            exch_wallet = await paper_wallet_service.get_exchange_wallet(user_id, exchange_lower)
            if not exch_wallet.get("funded") and PAPER_STARTING_CAPITAL_ZAR > 0:
                seed_capital, seed_currency, _ = resolve_capital_for_exchange(
                    float(PAPER_STARTING_CAPITAL_ZAR), exchange_lower
                )
                await paper_wallet_service.fund_exchange_wallet(
                    user_id, exchange_lower, seed_capital, seed_currency
                )
                logger.info(
                    "seed_paper_fleet: auto-funded %s wallet with %.6f %s for user %s",
                    exchange_lower, seed_capital, seed_currency, user_id[:8],
                )
                # Re-read so funded amount reflects the auto-seed
                exch_wallet = await paper_wallet_service.get_exchange_wallet(user_id, exchange_lower)
            # Determine funded ZAR equivalent for affordability gate
            native_amount = float(exch_wallet.get("available", 0) or 0)
            native_currency = exch_wallet.get("native_currency", "ZAR")
            if native_currency.upper() == "ZAR":
                exch_wallet_funded_zar = native_amount
            else:
                # Convert USDT → ZAR using a safe proxy rate
                from services.paper_wallet_service import _get_paper_zar_per_usdt
                _usdt_rate = await _get_paper_zar_per_usdt()
                exch_wallet_funded_zar = native_amount * _usdt_rate
        except Exception as exc:
            logger.warning(
                "seed_paper_fleet: exchange wallet fund/check failed for %s user=%s: %s",
                exchange_lower, user_id[:8], exc,
            )
            result["errors"].append(f"Exchange wallet fund warning ({exchange_lower}): {exc}")

        # ── Affordability gate — hard-block if funded capital can't support bots ──
        # Per-bot capital is derived from the ACTUAL funded wallet amount so the
        # operator cannot silently over-allocate by requesting more bots than the
        # funded wallet can cover.
        total_bots_for_exchange = normal_per_exchange + scalper_per_exchange
        if total_bots_for_exchange > 0 and exch_wallet_funded_zar > 0:
            # If caller passed explicit capital_zar_per_bot, honour it; otherwise
            # distribute the funded amount evenly across the requested bot count.
            if capital_zar_per_bot <= 0:
                _effective_per_bot = max(
                    exch_wallet_funded_zar / total_bots_for_exchange,
                    float(BOT_MANUAL_MIN_CAPITAL_ZAR or 1000.0),
                )
            else:
                _effective_per_bot = capital_zar_per_bot
            _max_affordable = int(exch_wallet_funded_zar // _effective_per_bot)
            if _max_affordable < total_bots_for_exchange:
                _block_msg = (
                    f"{exchange_lower}: insufficient funded capital for requested bot count. "
                    f"Funded=R{exch_wallet_funded_zar:.0f} / per-bot=R{_effective_per_bot:.0f} "
                    f"→ max {_max_affordable} bot(s) but {total_bots_for_exchange} requested. "
                    f"Fund at least R{int(_effective_per_bot * total_bots_for_exchange)} to proceed."
                )
                logger.warning("seed_paper_fleet: AFFORDABILITY_BLOCK %s user=%s", _block_msg, user_id[:8])
                result["bots_skipped"] += total_bots_for_exchange
                result["errors"].append(_block_msg)
                continue
            # Use exchange-specific per-bot capital derived from actual funded amount
            # so bots get an honest capital allocation, not the legacy global constant.
            capital_zar_per_bot = _effective_per_bot

        # Resolve capital for this exchange (ZAR for Luno, USDT for others)
        try:
            quote_capital, quote_currency, fx_rate = resolve_capital_for_exchange(
                capital_zar_per_bot, exchange_lower
            )
        except Exception as exc:
            logger.warning(
                "seed_paper_fleet: resolve_capital_for_exchange failed for %s: %s",
                exchange_lower, exc,
            )
            result["errors"].append(
                f"Capital resolution failed for {exchange_lower}: {exc}"
            )
            continue

        default_pair = _default_pair_for(exchange_lower)

        # Pre-build per-type pair lists for diverse initial assignment.
        # Normal bots cycle through the full DEFAULT_SYMBOL_UNIVERSE so each bot
        # starts on a different pair.  Scalpers cycle through the narrower
        # SCALPER_SYMBOL_UNIVERSE (highest-volume pairs) so their fleet is
        # visibly different from the normal-bot cohort.
        try:
            from services.symbol_universe import DEFAULT_SYMBOL_UNIVERSE, SCALPER_SYMBOL_UNIVERSE
            _normal_pairs = DEFAULT_SYMBOL_UNIVERSE.get(exchange_lower) or [default_pair]
            _scalper_pairs = SCALPER_SYMBOL_UNIVERSE.get(exchange_lower) or (_normal_pairs[:2] if _normal_pairs else [default_pair])
        except Exception:
            _normal_pairs = [default_pair]
            _scalper_pairs = [default_pair]

        for bot_type, requested_count in (
            ("normal", normal_per_exchange),
            ("scalper", scalper_per_exchange),
        ):
            if requested_count <= 0:
                continue

            # Count existing non-deleted bots of this type on this exchange
            try:
                existing_count = await db.bots_collection.count_documents(
                    bot_not_deleted_filter({
                        "user_id": user_id,
                        "exchange": exchange_lower,
                        "bot_type": bot_type,
                        "trading_mode": "paper",
                    })
                )
            except Exception as exc:
                logger.warning(
                    "seed_paper_fleet: count query failed for %s/%s: %s",
                    exchange_lower, bot_type, exc,
                )
                existing_count = 0

            # Check cap — if already at or above cap, skip this cohort
            can_create, reason = check_bot_cap_limit(
                exchange_lower,
                existing_count + requested_count,
                user_id=user_id,
                bot_type=bot_type,
            )
            if not can_create:
                logger.info(
                    "seed_paper_fleet: cap reached for %s/%s user=%s (%s) — skipping",
                    exchange_lower, bot_type, user_id[:8], reason,
                )
                result["bots_skipped"] += requested_count
                result["errors"].append(
                    f"{exchange_lower}/{bot_type}: cap reached ({reason}) — {requested_count} bots skipped."
                )
                continue

            # ── Exchange-strategy compatibility check ─────────────────────
            # If the strategy JSON for this bot_type restricts compatible
            # exchanges, silently skip (and record) incompatible combos here
            # rather than letting bots be created and then immediately blocked
            # by the scheduler on every tick.
            try:
                from services.strategy_compatibility import check_compatible as _chk
                _ok, _why = _chk(bot_type=bot_type, exchange=exchange_lower)
                if not _ok:
                    logger.info(
                        "seed_paper_fleet: COMPAT_SKIP %s/%s — %s",
                        exchange_lower, bot_type, _why,
                    )
                    result["bots_skipped"] += requested_count
                    result["errors"].append(
                        f"{exchange_lower}/{bot_type}: skipped — "
                        f"strategy incompatible with this exchange ({_why}). "
                        "See strategy registry for allowed exchanges."
                    )
                    continue
            except Exception as _ce:
                logger.warning("seed_paper_fleet: compat check failed (non-fatal): %s", _ce)

            # ── Build bot documents ───────────────────────────────────────
            name_prefix = "Scalper" if bot_type == "scalper" else "Normal"
            # Count all existing user bots to get a globally unique sequence number
            try:
                global_count = await db.bots_collection.count_documents(
                    {"user_id": user_id}
                )
            except Exception:
                global_count = 0

            bots_to_insert: List[dict] = []
            # Select the pair-rotation list for this bot type
            _pair_universe = _scalper_pairs if bot_type == "scalper" else _normal_pairs
            for i in range(requested_count):
                # Distribute pairs round-robin so each bot in this cohort starts on
                # a different pair.  Index wraps when the universe is smaller than
                # the requested count.
                initial_pair = _pair_universe[i % len(_pair_universe)] if _pair_universe else default_pair
                seq = global_count + len(bots_to_insert) + 1
                name = f"Seed-{name_prefix}-{exchange_lower.capitalize()}-{seq}"
                record: dict = {
                    "id": str(uuid4()),
                    "user_id": user_id,
                    "name": name,
                    "status": "active",
                    "trading_mode": "paper",
                    "exchange": exchange_lower,
                    "pair": initial_pair,
                    "bot_type": bot_type,
                    "strategy_preset": "scalping" if bot_type == "scalper" else "adaptive",
                    "risk_mode": "safe",
                    # Canonical capital truth fields
                    "canonical_base_capital_zar": round(float(capital_zar_per_bot), 2),
                    "funding_input_amount": round(float(capital_zar_per_bot), 2),
                    "funding_input_currency": "ZAR",
                    "fx_rate_at_creation": fx_rate,
                    "quote_currency": quote_currency,
                    # initial_capital / current_capital in quote_currency units
                    "initial_capital": round(float(quote_capital), 6),
                    "current_capital": round(float(quote_capital), 6),
                    "total_profit": 0.0,
                    "trades_count": 0,
                    "origin": source,
                    "paper_end_date": None,
                    "created_at": now_iso,
                    "last_trade": None,
                    # Phase D: explicit default so diagnostics never show blank/None
                    # before the first scheduler tick populates the real reason.
                    "last_skip_reason": "pending_first_tick",
                    "last_eligibility_code": "pending_first_tick",
                }
                if bot_type == "scalper":
                    record["profit_routing"] = "RETURN_TO_MAIN"
                bots_to_insert.append(record)

            if not bots_to_insert:
                continue

            try:
                await db.bots_collection.insert_many(bots_to_insert)
                result["bots_created"] += len(bots_to_insert)
                result["by_exchange"][exchange_lower][bot_type] += len(bots_to_insert)
                logger.info(
                    "seed_paper_fleet: created %d %s bots on %s "
                    "(R%.2f ZAR / %.6f %s per bot) for user %s",
                    len(bots_to_insert), bot_type, exchange_lower,
                    capital_zar_per_bot, quote_capital, quote_currency,
                    user_id[:8],
                )
                # ── Phase C: pre-seed pair-rotation counters for diversity ──────
                # Each bot starts at a different offset in the symbol_universe
                # scan-counter so that on the first scheduler tick they select
                # different pairs instead of all converging on candidates[0].
                # This is the in-memory singleton shared with paper_trading_engine.
                try:
                    from services.symbol_universe import _symbol_history
                    for _idx, _bot_doc in enumerate(bots_to_insert):
                        _counter_key = f"{_bot_doc['id']}:{exchange_lower}"
                        _symbol_history._scan_counters[_counter_key] = _idx
                except Exception as _sc_err:
                    logger.debug(
                        "seed_paper_fleet: scan counter pre-seed failed (non-fatal): %s",
                        _sc_err,
                    )
            except Exception as exc:
                logger.warning(
                    "seed_paper_fleet: insert failed for %s/%s user=%s: %s",
                    exchange_lower, bot_type, user_id[:8], exc,
                )
                result["bots_skipped"] += len(bots_to_insert)
                result["errors"].append(
                    f"{exchange_lower}/{bot_type}: insert failed — {exc}"
                )

    return result
