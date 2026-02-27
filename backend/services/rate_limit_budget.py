"""
RateLimitBudget — Exchange-agnostic order rate budget with jittered backoff.

Design
------
* Each exchange has a per-second and per-minute order budget.
* `acquire()` checks whether the budget allows submitting now; if not it returns
  a `wait_seconds` value so callers can sleep and retry.
* Tracks 429 / 418 / 5xx responses and applies exponential back-off with
  full-jitter (to avoid thundering-herd after cooldown periods).
* Bots are never permanently locked — the maximum backoff is bounded.
* All state is in-process; for multi-process deployments a Redis layer can be
  swapped in without changing the public API.

Usage
-----
    budget = rate_limit_budget.for_exchange("binance")
    ok, wait = budget.acquire("bot_id")
    if not ok:
        await asyncio.sleep(wait)
        ok, wait = budget.acquire("bot_id")   # retry once after sleep

    # After exchange response:
    budget.record_response(status_code=429)   # triggers backoff
    budget.record_response(status_code=200)   # resets error streak
"""

from __future__ import annotations

import logging
import math
import random
import time
from collections import defaultdict, deque
from typing import Dict, Optional, Tuple

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Exchange-specific rate limit configurations
# ---------------------------------------------------------------------------
# Values are conservative (below documented limits) to leave headroom.
# ref: Binance API limit 1200 req/min (weight), Bybit 10 req/s per endpoint,
#      Kraken 20 req/s max, Luno 60 req/min, KuCoin 10 req/s public.
_EXCHANGE_BUDGETS: Dict[str, Dict] = {
    "luno":    {"per_sec": 1,  "per_min": 40,  "burst": 3},
    "binance": {"per_sec": 8,  "per_min": 400, "burst": 15},
    "kucoin":  {"per_sec": 8,  "per_min": 400, "burst": 15},
    "bybit":   {"per_sec": 8,  "per_min": 400, "burst": 12},
    "kraken":  {"per_sec": 10, "per_min": 400, "burst": 15},
    "bitget":  {"per_sec": 8,  "per_min": 300, "burst": 12},
    "gate":    {"per_sec": 8,  "per_min": 300, "burst": 12},
    # Default for unknown exchanges
    "_default": {"per_sec": 2, "per_min": 60,  "burst": 4},
}

# Maximum backoff cap (seconds) — bots are never locked longer than this
_MAX_BACKOFF_SECONDS: float = 120.0
_MIN_BACKOFF_SECONDS: float = 1.0
# Retry delay returned when the per-second burst slot is full (try again soon)
_BURST_RETRY_DELAY_SECONDS: float = 0.1


class ExchangeRateLimitBudget:
    """Per-exchange rate limit budget tracker with jittered exponential backoff."""

    def __init__(self, exchange: str) -> None:
        cfg = _EXCHANGE_BUDGETS.get(exchange.lower(), _EXCHANGE_BUDGETS["_default"])
        self.exchange = exchange
        self._per_sec: int = cfg["per_sec"]
        self._per_min: int = cfg["per_min"]
        self._burst: int = cfg["burst"]

        # Sliding window tracking: timestamps of recent requests
        self._second_window: deque = deque()   # last 1-second window
        self._minute_window: deque = deque()   # last 60-second window

        # Back-off state
        self._error_streak: int = 0            # consecutive 4xx/5xx responses
        self._backoff_until: float = 0.0       # epoch time when backoff clears
        self._in_cooldown: bool = False        # True while in imposed cooldown

        # Per-bot request counts (informational)
        self._bot_counts: Dict[str, int] = defaultdict(int)

    # -----------------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------------

    def acquire(self, bot_id: str = "") -> Tuple[bool, float]:
        """
        Check if a new order can be submitted now.

        Returns (allowed: bool, wait_seconds: float).
        If allowed is False the caller should sleep wait_seconds and retry.
        """
        now = time.monotonic()

        # Hard backoff in effect
        if now < self._backoff_until:
            return False, round(self._backoff_until - now, 2)

        # Purge stale entries from windows
        self._purge_windows(now)

        # Per-second check (burst allowance)
        if len(self._second_window) >= self._burst:
            return False, _BURST_RETRY_DELAY_SECONDS

        # Per-minute check
        if len(self._minute_window) >= self._per_min:
            oldest = self._minute_window[0]
            return False, round(60.0 - (now - oldest) + 0.05, 2)

        # Budget OK — record the request
        self._second_window.append(now)
        self._minute_window.append(now)
        if bot_id:
            self._bot_counts[bot_id] += 1
        return True, 0.0

    def record_response(self, status_code: int, bot_id: str = "") -> None:
        """
        Inform the budget of an HTTP response.  4xx/5xx trigger backoff.

        * 429 / 418 → exponential backoff with jitter
        * 5xx        → smaller backoff (transient server error)
        * 2xx        → reset error streak
        """
        if status_code in (200, 201, 204):
            self._error_streak = 0
            self._in_cooldown = False
            return

        if status_code in (429, 418):
            # Rate-limited by exchange
            self._error_streak += 1
            backoff = self._calc_backoff(base=10.0)
            self._backoff_until = time.monotonic() + backoff
            self._in_cooldown = True
            logger.warning(
                "RateLimitBudget[%s] HTTP %s — backoff %.1fs (streak=%d)",
                self.exchange, status_code, backoff, self._error_streak,
            )
        elif status_code >= 500:
            self._error_streak += 1
            backoff = self._calc_backoff(base=3.0)
            self._backoff_until = time.monotonic() + backoff
            logger.warning(
                "RateLimitBudget[%s] HTTP %s — backoff %.1fs (streak=%d)",
                self.exchange, status_code, backoff, self._error_streak,
            )
        else:
            # 4xx client error (not rate-limit) — do not backoff, but note it
            logger.debug("RateLimitBudget[%s] HTTP %s (client error, no backoff)", self.exchange, status_code)

    def get_status(self) -> dict:
        """Return diagnostic snapshot of current budget state."""
        now = time.monotonic()
        self._purge_windows(now)
        return {
            "exchange": self.exchange,
            "requests_last_second": len(self._second_window),
            "requests_last_minute": len(self._minute_window),
            "per_sec_limit": self._burst,
            "per_min_limit": self._per_min,
            "in_backoff": now < self._backoff_until,
            "backoff_remaining_seconds": round(max(0.0, self._backoff_until - now), 2),
            "error_streak": self._error_streak,
            "in_cooldown": self._in_cooldown,
        }

    # -----------------------------------------------------------------------
    # Private helpers
    # -----------------------------------------------------------------------

    def _purge_windows(self, now: float) -> None:
        while self._second_window and now - self._second_window[0] > 1.0:
            self._second_window.popleft()
        while self._minute_window and now - self._minute_window[0] > 60.0:
            self._minute_window.popleft()

    def _calc_backoff(self, base: float = 5.0) -> float:
        """Full-jitter exponential backoff: random(0, min(cap, base * 2^streak))."""
        cap = _MAX_BACKOFF_SECONDS
        raw = base * math.pow(2, max(0, self._error_streak - 1))
        # Full jitter: uniformly sample [0, min(cap, raw)]
        jittered = random.uniform(_MIN_BACKOFF_SECONDS, min(cap, max(_MIN_BACKOFF_SECONDS, raw)))
        return round(jittered, 2)


class RateLimitBudgetRegistry:
    """Application-level registry of per-exchange budgets (singleton)."""

    def __init__(self) -> None:
        self._budgets: Dict[str, ExchangeRateLimitBudget] = {}

    def for_exchange(self, exchange: str) -> ExchangeRateLimitBudget:
        key = exchange.lower()
        if key not in self._budgets:
            self._budgets[key] = ExchangeRateLimitBudget(key)
        return self._budgets[key]

    def get_all_status(self) -> Dict[str, dict]:
        return {exch: b.get_status() for exch, b in self._budgets.items()}

    def acquire(self, exchange: str, bot_id: str = "") -> Tuple[bool, float]:
        """Convenience: acquire budget for an exchange."""
        return self.for_exchange(exchange).acquire(bot_id)

    def record_response(self, exchange: str, status_code: int, bot_id: str = "") -> None:
        """Convenience: record a response for an exchange."""
        self.for_exchange(exchange).record_response(status_code, bot_id)


# Module-level singleton
rate_limit_budget = RateLimitBudgetRegistry()
