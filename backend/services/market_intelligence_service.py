"""
Automatic Market Intelligence Service
Pulls from CoinStats on a schedule, emits events to user feeds.
"""
import asyncio
import logging
import os
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)

# How often to refresh intelligence (default 60 seconds, min 30, max 900)
_REFRESH_INTERVAL = max(30, min(900, int(os.getenv("MARKET_INTEL_REFRESH_SECONDS", "60"))))

_last_brief: Optional[dict] = None


async def get_latest_intelligence() -> dict:
    """Return the most recently computed market intelligence."""
    return _last_brief or {
        "what_happened": "No market data yet — intelligence updates every 15 minutes.",
        "why_it_matters": "Market intelligence is collected automatically from CoinStats.",
        "what_amarktai_is_doing": "Amarktai Crypto monitors markets continuously and adjusts bot strategy.",
        "confidence": "Pending first fetch",
        "mood": "neutral",
        "top_risk": "none",
        "source": "CoinStats",
        "updated_at": None,
    }


async def _fetch_and_process():
    """Fetch CoinStats news and build market brief."""
    global _last_brief
    now = datetime.now(timezone.utc)
    try:
        from services.news_coinstats import coinstats_provider, resolve_coinstats_key
        articles = await coinstats_provider.get_articles(limit=10)

        if not articles:
            # Diagnose why — missing key, rate-limit, network, etc.
            last_error = getattr(coinstats_provider, "_last_error", None)
            key, key_source = await resolve_coinstats_key()
            if not key:
                block_reason = "CoinStats API key not configured. Add COINSTATS_API_KEY env var or save via API Setup."
                fetch_status = "key_missing"
            elif last_error and "429" in str(last_error):
                block_reason = "CoinStats rate-limited (HTTP 429). Retrying on next interval."
                fetch_status = "rate_limited"
            elif last_error and "401" in str(last_error):
                block_reason = "CoinStats API key rejected (HTTP 401). Check your key."
                fetch_status = "invalid_key"
            elif last_error:
                block_reason = f"CoinStats fetch failed: {last_error}"
                fetch_status = "error"
            else:
                block_reason = "CoinStats returned no articles. Will retry on next interval."
                fetch_status = "no_articles"

            logger.warning(f"Market intelligence: no articles — {block_reason}")
            # Update _last_brief with status so updated_at becomes non-null
            _last_brief = {
                "what_happened": block_reason,
                "why_it_matters": "Market intelligence is awaiting CoinStats data.",
                "what_amarktai_is_doing": "Amarktai Crypto is monitoring markets. Data will appear once CoinStats is reachable.",
                "confidence": "Pending first fetch",
                "mood": "neutral",
                "top_risk": "none",
                "source": "CoinStats",
                "fetch_status": fetch_status,
                "block_reason": block_reason,
                "updated_at": now.isoformat(),
            }
            return

        # Build simple mood from sentiment scores
        sentiments = [a.get("sentiment_label", "").upper() for a in articles if a.get("sentiment_label")]
        pos = sentiments.count("POSITIVE")
        neg = sentiments.count("NEGATIVE")

        if pos > neg + 2:
            mood = "positive"
            confidence = "High — majority of recent headlines are positive"
        elif neg > pos + 2:
            mood = "negative"
            confidence = "High — majority of recent headlines are negative"
        else:
            mood = "neutral"
            confidence = "Moderate — mixed market signals"

        # Top headline
        top = articles[0] if articles else {}
        what_happened = top.get("title") or top.get("description") or "No recent headlines"

        # Risk label
        risk_keywords = {
            "hack": "exchange security incident",
            "regulatory": "regulatory headline",
            "sec": "regulatory headline",
            "ban": "regulatory action",
            "crash": "high volatility",
            "volatile": "high volatility",
            "liquidat": "liquidation event",
            "outage": "exchange outage",
            "exploit": "DeFi exploit",
        }
        top_risk = "none"
        all_text = " ".join([a.get("title", "") + " " + a.get("description", "") for a in articles]).lower()
        for keyword, label in risk_keywords.items():
            if keyword in all_text:
                top_risk = label
                break

        now = datetime.now(timezone.utc)
        _last_brief = {
            "what_happened": what_happened,
            "why_it_matters": f"This {mood} signal from CoinStats affects crypto prices and bot entry/exit decisions.",
            "what_amarktai_is_doing": f"Amarktai Crypto bots are operating in {mood} mode — {'seeking opportunities' if mood == 'positive' else 'applying caution' if mood == 'negative' else 'monitoring closely'}.",
            "confidence": confidence,
            "mood": mood,
            "top_risk": top_risk,
            "headlines_count": len(articles),
            "source": "CoinStats",
            "fetch_status": "ok",
            "block_reason": None,
            "updated_at": now.isoformat(),
        }

        logger.info(f"Market intelligence updated: mood={mood}, risk={top_risk}, articles={len(articles)}")

        # Emit event to all active users (best-effort)
        await _emit_intelligence_event()

    except Exception as e:
        logger.warning(f"Market intelligence fetch failed: {e}")
        # Still update _last_brief so updated_at is non-null
        _last_brief = {
            "what_happened": f"Market intelligence fetch error: {str(e)[:200]}",
            "why_it_matters": "An error occurred while fetching CoinStats data.",
            "what_amarktai_is_doing": "Amarktai Crypto is retrying market data fetch on the next interval.",
            "confidence": "Pending",
            "mood": "neutral",
            "top_risk": "none",
            "source": "CoinStats",
            "fetch_status": "error",
            "block_reason": str(e)[:200],
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }


async def _emit_intelligence_event():
    """Emit market brief event to all active users."""
    try:
        import database as db
        if db.db is None or _last_brief is None:
            return
        brief = _last_brief
        mood_emoji = {"positive": "📈", "negative": "📉", "neutral": "➡️"}.get(brief["mood"], "📊")
        message = f"{mood_emoji} Market brief: {brief['what_happened'][:120]}"
        # Emit to all users who have bots or recent activity
        users = await db.users_collection.find({}, {"id": 1}).to_list(length=200)
        from routes.events import emit_event
        for user in users:
            uid = user.get("id") or str(user.get("_id", ""))
            if uid:
                await emit_event(uid, "market_intelligence", "info", message, meta={"mood": brief["mood"], "risk": brief["top_risk"]})
    except Exception as e:
        logger.debug(f"Could not emit intelligence event: {e}")


async def start_intelligence_scheduler():
    """Start the background market intelligence refresh loop."""
    logger.info(f"Market intelligence scheduler starting (interval={_REFRESH_INTERVAL}s)")
    while True:
        await _fetch_and_process()
        await asyncio.sleep(_REFRESH_INTERVAL)
