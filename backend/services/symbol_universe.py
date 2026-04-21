"""
Symbol Universe — diversified pair selection with anti-repeat + portfolio guard.

Responsibilities:
  - Provide a per-exchange allowed symbol universe (configurable).
  - Score and rank candidates, applying penalty to recently-traded symbols.
  - Enforce a "diversity guard": strongly discourage re-opening a symbol that
    the user already has an open trade on.
  - Expose diagnostic information: candidate_count, filtered_out_reasons,
    top-5 scored symbols with scores, and why the winner won.

Usage (paper trading engine):
    from services.symbol_universe import symbol_universe
    winner, diagnostics = await symbol_universe.select(
        bot_id="bot_abc",
        user_id="user_xyz",
        exchange="binance",
        available_pairs=["BTC/USDT", "ETH/USDT", ...],
        open_symbols_for_user=["BTC/USDT"],   # symbols with open trades this user
    )
"""

from __future__ import annotations

import logging
from collections import defaultdict, deque
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Tuple

from config import (
    PAPER_PAIR_WHITELIST,
    PAPER_PAIR_WHITELIST_ENABLED,
    SYMBOL_COOLDOWN_MINUTES,
    SYMBOL_COOLDOWN_HISTORY,
    PORTFOLIO_GUARD_WINDOW_MINUTES,
    PORTFOLIO_GUARD_MAX_SAME_SYMBOL,
    STOP_LOSS_COOLDOWN_MINUTES,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Default symbol universes per exchange  (configurable at runtime)
# ---------------------------------------------------------------------------
# Note: CCXT normalises Luno's native XBT ticker to BTC, so available_pairs
# from load_markets() will contain 'BTC/ZAR' rather than 'XBT/ZAR'.
# The universe is ordered from most liquid to least — the rotation counter
# cycles through all entries so bots naturally diversify over time.
DEFAULT_SYMBOL_UNIVERSE: Dict[str, List[str]] = {
    "luno":     ["BTC/ZAR", "ETH/ZAR", "XRP/ZAR", "SOL/ZAR", "LTC/ZAR"],
    "binance":  ["BTC/USDT", "ETH/USDT", "SOL/USDT", "XRP/USDT", "BNB/USDT", "ADA/USDT", "DOGE/USDT"],
    "kucoin":   ["BTC/USDT", "ETH/USDT", "SOL/USDT", "XRP/USDT", "ADA/USDT", "DOGE/USDT"],
    "bybit":    ["BTC/USDT", "ETH/USDT", "SOL/USDT", "XRP/USDT", "ADA/USDT", "DOGE/USDT"],
    "kraken":   ["BTC/USDT", "ETH/USDT", "SOL/USDT", "XRP/USDT", "ADA/USDT"],
    "bitget":   ["BTC/USDT", "ETH/USDT", "SOL/USDT", "XRP/USDT", "ADA/USDT", "DOGE/USDT"],
    "gate":     ["BTC/USDT", "ETH/USDT", "SOL/USDT", "XRP/USDT", "ADA/USDT", "DOGE/USDT"],
    "coinbase": ["BTC/USDT", "ETH/USDT", "SOL/USDT", "XRP/USDT", "ADA/USDT"],
}

# Scalper-specific symbol universe: restricted to the highest-volume, tightest-spread
# pairs on each exchange.  Scalpers trade for small, fast moves; wider-spread or
# lower-volume pairs eat into the thin edge a scalp targets.
# Two pairs per exchange forces measurable diversity: roughly half the scalper fleet
# will be on BTC, half on ETH.
SCALPER_SYMBOL_UNIVERSE: Dict[str, List[str]] = {
    "luno":     ["BTC/ZAR", "ETH/ZAR"],
    "binance":  ["BTC/USDT", "ETH/USDT"],
    "kucoin":   ["BTC/USDT", "ETH/USDT"],
    "bybit":    ["BTC/USDT", "ETH/USDT"],
    "kraken":   ["BTC/USDT", "ETH/USDT"],
    "bitget":   ["BTC/USDT", "ETH/USDT"],
    "gate":     ["BTC/USDT", "ETH/USDT"],
    "coinbase": ["BTC/USDT", "ETH/USDT"],
}

# Penalty multiplier applied to recently-traded symbols (0 = no score, 1 = full score)
_COOLDOWN_PENALTY = 0.15  # 85% penalty during cooldown window
# Penalty applied when a symbol already has an open trade for this user
_DIVERSITY_PENALTY = 0.05  # 95% penalty (strongly discourage, not block outright)
# Maximum number of stop-loss events stored per bot (avoids unbounded growth)
_MAX_STOP_LOSS_HISTORY = 10


class _SymbolHistory:
    """In-memory per-bot trading history used for anti-repeat logic."""

    def __init__(self) -> None:
        # bot_id -> deque of (symbol, closed_at_utc) pairs
        self._closed: Dict[str, deque] = defaultdict(lambda: deque(maxlen=SYMBOL_COOLDOWN_HISTORY))
        # bot_id -> list of (symbol, stop_loss_at_utc) for stop-loss specific cooldown
        self._stop_losses: Dict[str, List] = defaultdict(list)
        # "bot_id:exchange" -> call count for pair-scan rotation
        self._scan_counters: Dict[str, int] = {}

    def record_closed(self, bot_id: str, symbol: str) -> None:
        self._closed[bot_id].append((symbol, datetime.now(timezone.utc)))

    def record_stop_loss(self, bot_id: str, symbol: str) -> None:
        """Record a stop-loss close so the symbol gets a longer cooldown."""
        self._stop_losses[bot_id].append((symbol, datetime.now(timezone.utc)))
        # Trim to avoid unbounded growth
        if len(self._stop_losses[bot_id]) > _MAX_STOP_LOSS_HISTORY:
            self._stop_losses[bot_id] = self._stop_losses[bot_id][-_MAX_STOP_LOSS_HISTORY:]

    def recently_traded(self, bot_id: str, symbol: str, cooldown_minutes: int) -> bool:
        """Return True if *symbol* was closed within *cooldown_minutes* for *bot_id*."""
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=cooldown_minutes)
        for sym, closed_at in self._closed[bot_id]:
            if sym == symbol and closed_at >= cutoff:
                return True
        return False

    def recently_stop_lossed(self, bot_id: str, symbol: str) -> bool:
        """Return True if *symbol* had a stop-loss within STOP_LOSS_COOLDOWN_MINUTES."""
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=STOP_LOSS_COOLDOWN_MINUTES)
        for sym, sl_at in self._stop_losses.get(bot_id, []):
            if sym == symbol and sl_at >= cutoff:
                return True
        return False

    def last_n_symbols(self, bot_id: str) -> List[str]:
        return [sym for sym, _ in self._closed[bot_id]]

    def get_and_increment_scan_counter(self, bot_id: str, exchange: str) -> int:
        """Return current scan counter for (bot_id, exchange) then increment it.

        Used to rotate the pair candidate list each call so that stable-sort
        tiebreaks cycle through all pairs instead of always picking index 0.
        """
        key = f"{bot_id}:{exchange}"
        count = self._scan_counters.get(key, 0)
        self._scan_counters[key] = count + 1
        return count


# Module-level singleton (shared by all engine instances)
_symbol_history = _SymbolHistory()


class SymbolUniverseService:
    """Stateless service wrapping the shared _symbol_history singleton."""

    # ---------------------------------------------------------------------------
    # Public API
    # ---------------------------------------------------------------------------

    def record_closed(self, bot_id: str, symbol: str) -> None:
        """Call this whenever a trade is closed so anti-repeat tracking stays current."""
        _symbol_history.record_closed(bot_id, symbol)

    def record_stop_loss(self, bot_id: str, symbol: str) -> None:
        """Call this on a stop-loss close to apply the longer stop-loss cooldown."""
        _symbol_history.record_stop_loss(bot_id, symbol)

    async def select(
        self,
        *,
        bot_id: str,
        user_id: str,
        exchange: str,
        available_pairs: List[str],
        open_symbols_for_user: Optional[List[str]] = None,
        bot_override_universe: Optional[List[str]] = None,
        cooldown_minutes: Optional[int] = None,
    ) -> Tuple[Optional[str], Dict]:
        """
        Select the best symbol from *available_pairs* using scoring + anti-repeat.

        Returns (winner_symbol, diagnostics_dict).
        winner_symbol is None only when *available_pairs* is empty after filtering.

        diagnostics_dict keys:
          candidate_count         int
          filtered_out_reasons    dict[symbol -> reason]
          top5_scored             list[{symbol, score, notes}]
          winner                  str | None
          winner_reason           str
          exchange                str
          bot_id                  str
        """
        if cooldown_minutes is None:
            cooldown_minutes = SYMBOL_COOLDOWN_MINUTES

        open_symbols = set(open_symbols_for_user or [])
        filtered_out: Dict[str, str] = {}

        # 1. Build the allowed universe for this exchange.
        # When PAPER_PAIR_WHITELIST_ENABLED is False (default) the whitelist is
        # skipped so bots can evaluate any pair returned by dynamic exchange
        # discovery.  The whitelist is only consulted when explicitly enabled
        # (e.g. PAPER_PAIR_WHITELIST_ENABLED=true env var) to act as a curated
        # safety universe.
        whitelist = PAPER_PAIR_WHITELIST.get(exchange) if PAPER_PAIR_WHITELIST_ENABLED else None
        # Use explicit None check so an intentionally empty bot_override_universe
        # list is treated as "no override" rather than silently falling through to
        # the whitelist (an empty list is falsy in Python).
        universe = (
            bot_override_universe if bot_override_universe is not None else (whitelist or [])
        )
        universe_set = set(universe)

        # 2. Filter candidates to those in the universe (only when a universe is
        # defined) and available on the exchange.
        candidates: List[str] = []
        for sym in available_pairs:
            if universe_set and sym not in universe_set:
                filtered_out[sym] = "not_in_universe"
                continue
            candidates.append(sym)

        candidate_count = len(candidates)

        if not candidates:
            diag = self._build_diagnostics(
                bot_id=bot_id,
                exchange=exchange,
                candidate_count=candidate_count,
                filtered_out=filtered_out,
                scored=[],
                winner=None,
                winner_reason="no_candidates_after_filtering",
            )
            return None, diag

        # 3. Rotate candidates so that stable-sort tiebreaks cycle through all pairs
        #    rather than always picking the first candidate when scores are equal.
        #    Each call advances the rotation offset by 1, producing round-robin pair
        #    selection across the candidate list over successive calls for the same bot.
        _n_cand = len(candidates)
        if _n_cand > 1:
            _rot = _symbol_history.get_and_increment_scan_counter(bot_id, exchange) % _n_cand
            if _rot:
                candidates = candidates[_rot:] + candidates[:_rot]

        # 4. Score each candidate
        scored: List[Dict] = []
        for sym in candidates:
            score = 1.0
            notes: List[str] = []

            # Anti-repeat: cooldown penalty
            if _symbol_history.recently_traded(bot_id, sym, cooldown_minutes):
                score *= _COOLDOWN_PENALTY
                notes.append(f"cooldown_penalty({cooldown_minutes}min)")

            # Stop-loss cooldown: extra heavy penalty after a stop-loss on this symbol.
            # Applied on top of the regular cooldown to discourage immediately re-entering
            # a symbol that just triggered a stop-loss (typically means adverse momentum).
            if _symbol_history.recently_stop_lossed(bot_id, sym):
                score *= _COOLDOWN_PENALTY  # additional 85% penalty
                notes.append(f"stop_loss_cooldown({STOP_LOSS_COOLDOWN_MINUTES}min)")

            # Diversity guard: user already has an open trade on this symbol
            if sym in open_symbols:
                score *= _DIVERSITY_PENALTY
                notes.append("diversity_penalty(already_open)")

            scored.append({"symbol": sym, "score": round(score, 4), "notes": notes})

        # 5. Sort descending by score, break ties by rotated position (stable)
        scored.sort(key=lambda x: -x["score"])

        winner_entry = scored[0]
        winner = winner_entry["symbol"]
        winner_notes = winner_entry["notes"]

        if winner_notes:
            winner_reason = "best_available_despite_penalties: " + ", ".join(winner_notes)
        else:
            winner_reason = "highest_score_no_penalties"

        diag = self._build_diagnostics(
            bot_id=bot_id,
            exchange=exchange,
            candidate_count=candidate_count,
            filtered_out=filtered_out,
            scored=scored,
            winner=winner,
            winner_reason=winner_reason,
        )
        return winner, diag

    # ---------------------------------------------------------------------------
    # Helpers
    # ---------------------------------------------------------------------------

    @staticmethod
    def _build_diagnostics(
        *,
        bot_id: str,
        exchange: str,
        candidate_count: int,
        filtered_out: Dict[str, str],
        scored: List[Dict],
        winner: Optional[str],
        winner_reason: str,
    ) -> Dict:
        # Summarise filter reasons
        reason_summary: Dict[str, int] = defaultdict(int)
        for reason in filtered_out.values():
            reason_summary[reason] += 1

        return {
            "bot_id": bot_id,
            "exchange": exchange,
            "candidate_count": candidate_count,
            "filtered_out_count": len(filtered_out),
            "filtered_out_reasons_summary": dict(reason_summary),
            "filtered_out_detail": filtered_out,
            "top5_scored": scored[:5],
            "winner": winner,
            "winner_reason": winner_reason,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def get_universe(self, exchange: str, bot_override: Optional[List[str]] = None, bot_type: str = "normal") -> List[str]:
        """Return the symbol universe list for *exchange*.

        When PAPER_PAIR_WHITELIST_ENABLED is False (default) the dynamic
        exchange pair list is used and this returns the DEFAULT_SYMBOL_UNIVERSE
        (or SCALPER_SYMBOL_UNIVERSE for scalpers) as a reference / diagnostic
        aid only (not used as a hard filter).
        """
        if bot_override:
            return list(bot_override)
        if PAPER_PAIR_WHITELIST_ENABLED:
            whitelist = PAPER_PAIR_WHITELIST.get(exchange)
            if whitelist:
                return list(whitelist)
        if str(bot_type).lower() == "scalper":
            return list(SCALPER_SYMBOL_UNIVERSE.get(exchange) or DEFAULT_SYMBOL_UNIVERSE.get(exchange) or [])
        return list(DEFAULT_SYMBOL_UNIVERSE.get(exchange) or [])

    def last_n_symbols(self, bot_id: str) -> List[str]:
        """Return the last N closed symbols for *bot_id* (for diagnostics)."""
        return _symbol_history.last_n_symbols(bot_id)


# Module-level singleton
symbol_universe = SymbolUniverseService()
