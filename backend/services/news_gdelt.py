"""
GDELT News Provider — DISABLED
Replaced by CoinStats (services/news_coinstats.py).
This stub is kept so any legacy import does not crash the server.
"""
import logging
logger = logging.getLogger(__name__)
logger.warning("services.news_gdelt is disabled. Use services.news_coinstats instead.")

class _DisabledProvider:
    configured = False
    async def get_articles(self, **kw): return []
    async def get_diagnostics(self, **kw):
        return {"configured": False, "source": "gdelt_disabled", "articles_count": 0,
                "last_fetch_ts": None, "last_error": "GDELT disabled — use CoinStats",
                "cache_ttl_seconds": 300}

gdelt_provider = _DisabledProvider()
