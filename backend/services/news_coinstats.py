"""
CoinStats News Provider + HuggingFace Sentiment Scoring
=======================================================
Fetches real crypto news from CoinStats API and optionally enriches
headlines with HuggingFace sentiment classification.

Config (env vars):
  NEWS_PROVIDER=coinstats           (default)
  NEWS_ENABLED=true                 (default)
  NEWS_CACHE_TTL_SECONDS=300        (default)
  COINSTATS_API_KEY=                (optional; also resolved per-user)
  HF_ENABLED=true                   (default)
  HF_DEFAULT_SENTIMENT_MODEL=distilbert-base-uncased-finetuned-sst-2-english

Key resolution priority:
  1. Per-user saved key (via routes/api_key_management.get_decrypted_key)
  2. COINSTATS_API_KEY env var
  3. None → configured=False (no fake data returned)
"""

import os
import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Optional

import aiohttp

logger = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────
NEWS_ENABLED: bool = os.getenv("NEWS_ENABLED", "true").lower() == "true"
NEWS_CACHE_TTL_SECONDS: int = int(os.getenv("NEWS_CACHE_TTL_SECONDS", "300"))
HF_ENABLED: bool = os.getenv("HF_ENABLED", "true").lower() == "true"
HF_DEFAULT_SENTIMENT_MODEL: str = os.getenv(
    "HF_DEFAULT_SENTIMENT_MODEL",
    "distilbert-base-uncased-finetuned-sst-2-english",
)
_COINSTATS_ENV_KEY: str = os.getenv("COINSTATS_API_KEY", "").strip()

# CoinStats public news endpoint (free tier works without key; key unlocks more)
_COINSTATS_NEWS_URL = "https://openapiv1.coinstats.app/news"

# Rate-limit warnings to once per 10 minutes
_WARN_INTERVAL = timedelta(minutes=10)

# Max articles to pass through HF (avoid long latency)
_HF_MAX_ARTICLES = 20


async def resolve_coinstats_key(user_id: Optional[str] = None) -> tuple[Optional[str], str]:
    """
    Resolve CoinStats API key.

    Priority:
      1. Per-user key from DB
      2. COINSTATS_API_KEY env var
      3. None

    Returns (key, source) where source is "user", "env", or "none".
    """
    if user_id:
        try:
            from routes.api_key_management import get_decrypted_key
            key_data = await get_decrypted_key(user_id, "coinstats")
            if key_data and key_data.get("api_key"):
                k = key_data["api_key"].strip()
                if k:
                    return k, "user"
        except Exception as e:
            logger.warning("CoinStats: failed to fetch user key: %s", e)

    if _COINSTATS_ENV_KEY:
        return _COINSTATS_ENV_KEY, "env"

    return None, "none"


class CoinStatsNewsProvider:
    """Fetches and caches crypto news from CoinStats API."""

    def __init__(self):
        self._cache: Optional[Dict] = None
        self._cache_ts: Optional[datetime] = None
        self._last_error: Optional[str] = None
        self._last_warn_ts: Optional[datetime] = None
        self._articles_count: int = 0

    # ── Public API ────────────────────────────────────────────────────────────

    async def get_articles(
        self,
        limit: int = 25,
        user_id: Optional[str] = None,
        with_sentiment: bool = False,
    ) -> List[Dict]:
        """Return (optionally sentiment-enriched) list of articles."""
        if not NEWS_ENABLED:
            return []
        cached = await self._maybe_refresh(user_id)
        articles = cached.get("articles", [])[:max(1, limit)]
        if with_sentiment and articles:
            articles = await score_articles_sentiment(articles)
        return articles

    async def get_diagnostics(self, user_id: Optional[str] = None) -> Dict:
        """Return status dict for /api/diagnostics/sentiment-news."""
        key, source = await resolve_coinstats_key(user_id)
        cached = await self._maybe_refresh(user_id)
        articles = cached.get("articles", [])

        # Include HF status
        hf_model: Optional[str] = None
        hf_configured = False
        try:
            from services.huggingface_key_resolver import resolve_huggingface_key, HF_DEFAULT_MODELS
            hf_key, _ = await resolve_huggingface_key(user_id)
            hf_configured = bool(hf_key)
            hf_model = HF_DEFAULT_MODELS.get("sentiment") if hf_configured else None
        except Exception:
            pass

        return {
            "configured": bool(key) or not bool(self._last_error),
            "source": "coinstats",
            "articles_count": len(articles),
            "last_fetch_ts": cached.get("fetched_at"),
            "last_error": self._last_error,
            "cache_ttl_seconds": NEWS_CACHE_TTL_SECONDS,
            "hf_configured": hf_configured,
            "hf_model": hf_model,
            "key_source": source,
            "sample": articles[:3],
        }

    async def test_connection(self, user_id: Optional[str] = None) -> Dict:
        """
        Perform a minimal live request and return connection status.
        Returns structured JSON — never raises.
        """
        key, source = await resolve_coinstats_key(user_id)
        if not key:
            return {
                "status": "error",
                "configured": False,
                "source": "none",
                "message": "No CoinStats API key configured. Add COINSTATS_API_KEY or save via API Setup.",
                "http_status": None,
                "latency_ms": None,
            }

        import time
        t0 = time.monotonic()
        try:
            headers = {"X-API-KEY": key, "Accept": "application/json"}
            timeout = aiohttp.ClientTimeout(total=10)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(
                    _COINSTATS_NEWS_URL,
                    headers=headers,
                    params={"limit": "1"},
                ) as resp:
                    latency = round((time.monotonic() - t0) * 1000, 1)
                    if resp.status == 200:
                        return {
                            "status": "success",
                            "configured": True,
                            "source": source,
                            "message": "Connected to CoinStats News API",
                            "http_status": resp.status,
                            "latency_ms": latency,
                        }
                    elif resp.status == 401:
                        return {
                            "status": "error",
                            "configured": True,
                            "source": source,
                            "message": "Invalid CoinStats API key (401 Unauthorized)",
                            "http_status": resp.status,
                            "latency_ms": latency,
                        }
                    else:
                        return {
                            "status": "error",
                            "configured": True,
                            "source": source,
                            "message": f"CoinStats returned HTTP {resp.status}",
                            "http_status": resp.status,
                            "latency_ms": latency,
                        }
        except asyncio.TimeoutError:
            latency = round((time.monotonic() - t0) * 1000, 1)
            return {
                "status": "error",
                "configured": True,
                "source": source,
                "message": "CoinStats request timed out (>10s)",
                "http_status": None,
                "latency_ms": latency,
            }
        except Exception as exc:
            latency = round((time.monotonic() - t0) * 1000, 1)
            return {
                "status": "error",
                "configured": True,
                "source": source,
                "message": f"Connection failed: {str(exc)[:200]}",
                "http_status": None,
                "latency_ms": latency,
            }

    # ── Internal ──────────────────────────────────────────────────────────────

    async def _maybe_refresh(self, user_id: Optional[str] = None) -> Dict:
        now = datetime.now(timezone.utc)
        if (
            self._cache is not None
            and self._cache_ts is not None
            and (now - self._cache_ts).total_seconds() < NEWS_CACHE_TTL_SECONDS
        ):
            return self._cache

        articles = await self._fetch(user_id)
        self._articles_count = len(articles)
        self._cache = {
            "articles": articles,
            "fetched_at": now.isoformat(),
        }
        self._cache_ts = now
        return self._cache

    async def _fetch(self, user_id: Optional[str] = None) -> List[Dict]:
        key, _ = await resolve_coinstats_key(user_id)

        headers: Dict[str, str] = {"Accept": "application/json"}
        if key:
            headers["X-API-KEY"] = key

        params = {"limit": "50"}

        try:
            timeout = aiohttp.ClientTimeout(total=10)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(
                    _COINSTATS_NEWS_URL, headers=headers, params=params
                ) as resp:
                    if resp.status == 429:
                        self._rate_warn("CoinStats rate-limited (429)")
                        return self._cache.get("articles", []) if self._cache else []
                    if resp.status == 401:
                        self._rate_warn("CoinStats: invalid API key (401)")
                        return []
                    if resp.status != 200:
                        self._rate_warn(f"CoinStats HTTP {resp.status}")
                        return []
                    data = await resp.json(content_type=None)

            raw = data if isinstance(data, list) else data.get("news", data.get("data", []))
            articles = []
            for item in raw:
                articles.append({
                    "id": item.get("id") or item.get("feedId", ""),
                    "title": item.get("title", ""),
                    "url": item.get("link") or item.get("url", ""),
                    "source": item.get("source", ""),
                    "published_at": _parse_ts(item.get("feedDate") or item.get("publishedAt")),
                    "tags": item.get("categories", []) or item.get("tags", []),
                    "coins": [c.get("name") or c for c in (item.get("relatedCoins") or [])][:5],
                    "summary": (item.get("description") or "")[:300],
                    "provider": "coinstats",
                })

            self._last_error = None
            logger.info("CoinStats: fetched %d articles", len(articles))
            return articles

        except asyncio.TimeoutError:
            self._rate_warn("CoinStats request timed out")
            return []
        except Exception as exc:
            self._rate_warn(f"CoinStats fetch error: {exc}")
            return []

    def _rate_warn(self, msg: str):
        self._last_error = msg
        now = datetime.now(timezone.utc)
        if self._last_warn_ts is None or (now - self._last_warn_ts) >= _WARN_INTERVAL:
            logger.warning("CoinStats news: %s (suppressing further warnings for 10 min)", msg)
            self._last_warn_ts = now


def _parse_ts(value) -> Optional[str]:
    """Convert various timestamp formats to ISO 8601."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(value, tz=timezone.utc).isoformat()
        except Exception:
            return None
    if isinstance(value, str):
        # Already ISO
        if "T" in value or value.isdigit():
            if value.isdigit():
                return datetime.fromtimestamp(int(value), tz=timezone.utc).isoformat()
            return value
    return str(value)


# ── HuggingFace Sentiment Scoring ─────────────────────────────────────────────

async def score_articles_sentiment(
    articles: List[Dict],
    user_id: Optional[str] = None,
) -> List[Dict]:
    """
    Enrich articles with HuggingFace sentiment labels.

    Returns articles unchanged (with hf_error added) if HF is unavailable.
    Never raises — all errors are returned as metadata.
    """
    if not HF_ENABLED or not articles:
        return articles

    try:
        from services.huggingface_key_resolver import resolve_huggingface_key, HF_DEFAULT_MODELS
        from services.huggingface_key_resolver import HF_INFERENCE_BASE_URL
        hf_key, hf_source = await resolve_huggingface_key(user_id)
        if not hf_key:
            for a in articles:
                a["hf_error"] = "HuggingFace key not configured"
            return articles
    except Exception as e:
        for a in articles:
            a["hf_error"] = f"HF resolver error: {e}"
        return articles

    model = HF_DEFAULT_MODELS.get("sentiment", HF_DEFAULT_SENTIMENT_MODEL)
    model_url = f"{HF_INFERENCE_BASE_URL}/{model}"

    import time
    scored = []
    to_score = articles[:_HF_MAX_ARTICLES]
    remaining = articles[_HF_MAX_ARTICLES:]

    for article in to_score:
        text = (article.get("title") or "") + " " + (article.get("summary") or "")
        text = text.strip()[:512]
        enriched = dict(article)
        if not text:
            enriched["sentiment_label"] = "NEUTRAL"
            enriched["sentiment_score"] = 0.5
            enriched["model_used"] = model
            scored.append(enriched)
            continue

        t0 = time.monotonic()
        try:
            from huggingface_hub import InferenceClient
            client = InferenceClient(token=hf_key, model=model_url)
            raw = client.text_classification(text)
            latency = round((time.monotonic() - t0) * 1000, 1)
            item = raw[0] if raw else {}
            enriched["sentiment_label"] = item.get("label", "NEUTRAL")
            enriched["sentiment_score"] = round(item.get("score", 0.5), 4)
            enriched["model_used"] = model
            enriched["sentiment_latency_ms"] = latency
        except Exception as exc:
            enriched["hf_error"] = str(exc)[:200]
            enriched["sentiment_label"] = None
            enriched["sentiment_score"] = None
            enriched["model_used"] = model
        scored.append(enriched)

    return scored + remaining


# ── Global singleton ──────────────────────────────────────────────────────────
coinstats_provider = CoinStatsNewsProvider()
