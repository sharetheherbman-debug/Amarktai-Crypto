"""
GDELT News Provider
Fetches crypto-relevant news from the GDELT Project (free, no API key required).

Configuration (env vars):
  NEWS_PROVIDER=gdelt          (default)
  NEWS_ENABLED=true            (default)
  NEWS_CACHE_TTL_SECONDS=300   (default)

GDELT GKG 2.0 DOC endpoint is used: it returns the latest 15-minute news snapshot.
We filter for cryptocurrency-related mentions using keyword matching.
"""

import os
import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Optional

import aiohttp

logger = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────
NEWS_ENABLED = os.getenv("NEWS_ENABLED", "true").lower() == "true"
NEWS_CACHE_TTL_SECONDS = int(os.getenv("NEWS_CACHE_TTL_SECONDS", "300"))

# GDELT doc endpoint for latest 15-min GKG snapshot list
GDELT_DOC_URL = "https://api.gdeltproject.org/api/v2/doc/doc"

# Keywords used to filter articles for crypto relevance
_CRYPTO_KEYWORDS = {
    "bitcoin", "btc", "ethereum", "eth", "crypto", "blockchain", "defi",
    "altcoin", "stablecoin", "binance", "coinbase", "trading", "forex",
    "rand", "zar", "luno", "bybit", "kraken",
}

# Rate-limit warning: only log fetch errors once per interval
_WARN_INTERVAL = timedelta(minutes=10)


class GDELTNewsProvider:
    """Fetches and caches news from GDELT, filtering for crypto relevance."""

    def __init__(self):
        self._cache: Optional[Dict] = None
        self._cache_ts: Optional[datetime] = None
        self._last_error: Optional[str] = None
        self._last_warn_ts: Optional[datetime] = None
        self._configured = NEWS_ENABLED

    # ── Public API ────────────────────────────────────────────────────────────

    @property
    def configured(self) -> bool:
        return self._configured

    async def get_articles(self, limit: int = 10) -> List[Dict]:
        """Return cached (or fresh) list of crypto-relevant news articles."""
        if not self._configured:
            return []
        cached = await self._maybe_refresh()
        articles = cached.get("articles", [])
        return articles[:limit]

    async def get_diagnostics(self) -> Dict:
        """Return status dict compatible with /api/diagnostics/sentiment-news."""
        cached = await self._maybe_refresh()
        return {
            "configured": self._configured,
            "source": "gdelt",
            "articles_count": len(cached.get("articles", [])),
            "last_fetch_ts": cached.get("fetched_at"),
            "last_error": self._last_error,
            "cache_ttl_seconds": NEWS_CACHE_TTL_SECONDS,
        }

    # ── Internal ──────────────────────────────────────────────────────────────

    async def _maybe_refresh(self) -> Dict:
        """Return valid cache or fetch fresh data."""
        now = datetime.now(timezone.utc)
        if (
            self._cache is not None
            and self._cache_ts is not None
            and (now - self._cache_ts).total_seconds() < NEWS_CACHE_TTL_SECONDS
        ):
            return self._cache

        articles = await self._fetch()
        self._cache = {
            "articles": articles,
            "fetched_at": now.isoformat(),
        }
        self._cache_ts = now
        return self._cache

    async def _fetch(self) -> List[Dict]:
        """Call GDELT DOC API and return filtered articles."""
        query = (
            "cryptocurrency OR bitcoin OR ethereum OR crypto trading"
            " OR blockchain OR DeFi OR altcoin"
        )
        params = {
            "query": query,
            "mode": "artlist",
            "maxrecords": "25",
            "format": "json",
            "timespan": "1h",
            "sort": "datedesc",
        }

        try:
            timeout = aiohttp.ClientTimeout(total=15)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(GDELT_DOC_URL, params=params) as resp:
                    if resp.status == 429:
                        self._rate_limit_warn("GDELT rate-limited (429)")
                        return self._cache.get("articles", []) if self._cache else []
                    if resp.status != 200:
                        self._rate_limit_warn(f"GDELT HTTP {resp.status}")
                        return []
                    data = await resp.json(content_type=None)

            raw_articles = data.get("articles", [])
            articles = []
            for item in raw_articles:
                title = item.get("title", "")
                url = item.get("url", "")
                domain = item.get("domain", "")
                date_str = item.get("seendate", "")
                # Filter for crypto relevance
                if not self._is_crypto_relevant(title):
                    continue
                articles.append({
                    "title": title,
                    "url": url,
                    "source": domain,
                    "published_at": _parse_gdelt_date(date_str),
                    "sentiment": None,  # Filled by sentiment analyzer if needed
                    "provider": "gdelt",
                })

            self._last_error = None
            logger.info("GDELT: fetched %d crypto-relevant articles", len(articles))
            return articles

        except asyncio.TimeoutError:
            self._rate_limit_warn("GDELT request timed out")
            return []
        except Exception as exc:
            self._rate_limit_warn(f"GDELT fetch error: {exc}")
            return []

    def _is_crypto_relevant(self, text: str) -> bool:
        lower = text.lower()
        return any(kw in lower for kw in _CRYPTO_KEYWORDS)

    def _rate_limit_warn(self, msg: str):
        self._last_error = msg
        now = datetime.now(timezone.utc)
        if self._last_warn_ts is None or (now - self._last_warn_ts) >= _WARN_INTERVAL:
            logger.warning("GDELT news: %s (suppressing further warnings for 10 min)", msg)
            self._last_warn_ts = now


def _parse_gdelt_date(date_str: str) -> Optional[str]:
    """Convert GDELT date format (YYYYMMDDTHHMMSSZ) to ISO 8601."""
    if not date_str:
        return None
    try:
        # GDELT format: 20250225T123456Z
        dt = datetime.strptime(date_str, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
        return dt.isoformat()
    except ValueError:
        return date_str


# ── Global singleton ──────────────────────────────────────────────────────────
gdelt_provider = GDELTNewsProvider()
