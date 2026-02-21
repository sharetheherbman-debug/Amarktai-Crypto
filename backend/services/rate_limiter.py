"""
Simple async-safe per-user rate limiter using sliding window.
No external dependencies needed — uses asyncio locks.
"""
import asyncio
import os
from collections import deque
from datetime import datetime, timezone
from typing import Dict, Optional
import logging

logger = logging.getLogger(__name__)


class PerUserRateLimiter:
    """Sliding-window rate limiter keyed by user_id (or IP as fallback)."""

    def __init__(self, max_requests: int = 60, window_seconds: int = 3600):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._windows: Dict[str, deque] = {}
        self._lock = asyncio.Lock()

    def _get_limit(self) -> int:
        return int(os.getenv("AI_RATE_LIMIT_PER_HOUR", str(self.max_requests)))

    async def check_and_record(self, key: str, bypass: bool = False) -> tuple[bool, int, int]:
        """
        Check if key is allowed and record the request.
        Returns (allowed, requests_used, retry_after_seconds).
        bypass=True skips the check (admin exemption).
        """
        if bypass:
            return True, 0, 0
        limit = self._get_limit()
        now = datetime.now(timezone.utc).timestamp()
        window_start = now - self.window_seconds
        async with self._lock:
            if key not in self._windows:
                self._windows[key] = deque()
            q = self._windows[key]
            # Remove timestamps outside window
            while q and q[0] < window_start:
                q.popleft()
            used = len(q)
            if used >= limit:
                # Retry after the oldest request falls out of window
                oldest = q[0] if q else now
                retry_after = int(self.window_seconds - (now - oldest)) + 1
                return False, used, retry_after
            q.append(now)
            return True, used + 1, 0


# Module-level singleton
ai_rate_limiter = PerUserRateLimiter(max_requests=60, window_seconds=3600)
