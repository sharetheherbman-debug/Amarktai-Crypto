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
    SYMBOL_COOLDOWN_MINUTES,
    SYMBOL_COOLDOWN_HISTORY,
    PORTFOLIO_GUARD_WINDOW_MINUTES,
    PORTFOLIO_GUARD_MAX_SAME_SYMBOL,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Default symbol universes per exchange  (configurable at runtime)
# ---------------------------------------------------------------------------
DEFAULT_SYMBOL_UNIVERSE: Dict[str, List[str]] = {
    "luno": ["XBT/ZAR", "BTC/ZAR", "ETH/ZAR", "XRP/ZAR"],
    "binance": ["BTC/USDT", "ETH/USDT", "SOL/USDT", "XRP/USDT", "BNB/USDT", "ADA/USDT"],
    "kucoin": ["BTC/USDT", "ETH/USDT", "SOL/USDT", "XRP/USDT", "BNB/USDT", "ADA/USDT"],
    "bybit": ["BTC/USDT", "ETH/USDT", "SOL/USDT", "XRP/USDT", "BNB/USDT", "ADA/USDT"],
    "kraken": ["BTC/USDT", "ETH/USDT", "SOL/USDT", "XRP/USDT", "ADA/USDT"],
    "bitget": ["BTC/USDT", "ETH/USDT", "SOL/USDT", "XRP/USDT", "BNB/USDT", "ADA/USDT"],
    "gate": ["BTC/USDT", "ETH/USDT", "SOL/USDT", "XRP/USDT", "ADA/USDT", "DOGE/USDT"],
}

# Penalty multiplier applied to recently-traded symbols (0 = no score, 1 = full score)
_COOLDOWN_PENALTY = 0.15  # 85% penalty during cooldown window
# Penalty applied when a symbol already has an open trade for this user
_DIVERSITY_PENALTY = 0.05  # 95% penalty (strongly discourage, not block outright)


class _SymbolHistory:
    """In-memory per-bot trading history used for anti-repeat logic."""

    def __init__(self) -> None:
        # bot_id -> deque of (symbol, closed_at_utc) pairs
        self._closed: Dict[str, deque] = defaultdict(lambda: deque(maxlen=SYMBOL_COOLDOWN_HISTORY))

    def record_closed(self, bot_id: str, symbol: str) -> None:
        self._closed[bot_id].append((symbol, datetime.now(timezone.utc)))

    def recently_traded(self, bot_id: str, symbol: str, cooldown_minutes: int) -> bool:
        """Return True if *symbol* was closed within *cooldown_minutes* for *bot_id*."""
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=cooldown_minutes)
        for sym, closed_at in self._closed[bot_id]:
            if sym == symbol and closed_at >= cutoff:
                return True
        return False

    def last_n_symbols(self, bot_id: str) -> List[str]:
        return [sym for sym, _ in self._closed[bot_id]]


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

        # 1. Build the allowed universe for this exchange
        universe = (
            bot_override_universe
            or PAPER_PAIR_WHITELIST.get(exchange)
            or DEFAULT_SYMBOL_UNIVERSE.get(exchange)
            or []
        )
        universe_set = set(universe)

        # 2. Filter candidates to those in the universe and available on the exchange
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

        # 3. Score each candidate
        scored: List[Dict] = []
        for sym in candidates:
            score = 1.0
            notes: List[str] = []

            # Anti-repeat: cooldown penalty
            if _symbol_history.recently_traded(bot_id, sym, cooldown_minutes):
                score *= _COOLDOWN_PENALTY
                notes.append(f"cooldown_penalty({cooldown_minutes}min)")

            # Diversity guard: user already has an open trade on this symbol
            if sym in open_symbols:
                score *= _DIVERSITY_PENALTY
                notes.append("diversity_penalty(already_open)")

            scored.append({"symbol": sym, "score": round(score, 4), "notes": notes})

        # 4. Sort descending by score, break ties by original position (stable)
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

    def get_universe(self, exchange: str, bot_override: Optional[List[str]] = None) -> List[str]:
        """Return the symbol universe list for *exchange*."""
        if bot_override:
            return list(bot_override)
        return list(
            PAPER_PAIR_WHITELIST.get(exchange)
            or DEFAULT_SYMBOL_UNIVERSE.get(exchange)
            or []
        )

    def last_n_symbols(self, bot_id: str) -> List[str]:
        """Return the last N closed symbols for *bot_id* (for diagnostics)."""
        return _symbol_history.last_n_symbols(bot_id)


# Module-level singleton
symbol_universe = SymbolUniverseService()
