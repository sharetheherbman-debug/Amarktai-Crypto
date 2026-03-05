"""
CoinStats Integration Routes

Provides market intelligence from CoinStats API:
  GET /api/coinstats/status        — connection / key status
  GET /api/coinstats/news          — latest crypto news
  GET /api/coinstats/markets       — top market tickers
"""

from fastapi import APIRouter, HTTPException, Depends
from datetime import datetime, timezone
from typing import Optional
import logging
import os
import httpx

from auth import get_current_user
import database as db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/coinstats", tags=["CoinStats"])

COINSTATS_BASE = "https://openapiv1.coinstats.app"


async def _get_coinstats_key(user_id: str) -> Optional[str]:
    """Retrieve the user's stored CoinStats API key (falls back to env)."""
    doc = await db.api_keys_collection.find_one(
        {"user_id": user_id, "provider": "coinstats"},
        {"_id": 0, "api_key": 1},
    )
    if doc and doc.get("api_key"):
        return doc["api_key"]
    return os.getenv("COINSTATS_API_KEY", "")


@router.get("/status")
async def coinstats_status(user_id: str = Depends(get_current_user)):
    """Check whether CoinStats is configured and reachable."""
    key = await _get_coinstats_key(user_id)
    configured = bool(key)
    reachable = False
    error_msg = None

    if configured:
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                resp = await client.get(
                    f"{COINSTATS_BASE}/coins",
                    headers={"X-API-KEY": key, "accept": "application/json"},
                    params={"limit": 1},
                )
                reachable = resp.status_code == 200
                if not reachable:
                    error_msg = f"HTTP {resp.status_code}"
        except Exception as exc:
            error_msg = str(exc)[:120]

    return {
        "success": True,
        "configured": configured,
        "reachable": reachable,
        "last_error": error_msg,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/news")
async def coinstats_news(user_id: str = Depends(get_current_user)):
    """Return recent crypto news from CoinStats."""
    key = await _get_coinstats_key(user_id)
    if not key:
        return {"news": [], "source": "coinstats", "error": "API key not configured"}

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{COINSTATS_BASE}/news",
                headers={"X-API-KEY": key, "accept": "application/json"},
                params={"limit": 20},
            )
            if resp.status_code != 200:
                return {"news": [], "source": "coinstats", "error": f"HTTP {resp.status_code}"}

            data = resp.json()
            articles = data if isinstance(data, list) else data.get("result", data.get("news", []))
            items = []
            for a in articles[:20]:
                items.append({
                    "title": a.get("title", ""),
                    "description": a.get("description", ""),
                    "source": a.get("source", ""),
                    "url": a.get("link", a.get("url", "")),
                    "image": a.get("imgURL", a.get("imgUrl", "")),
                    "published_at": a.get("feedDate", a.get("date", "")),
                    "coins": a.get("coins", []),
                })

            return {"news": items, "source": "coinstats", "count": len(items)}
    except Exception as exc:
        logger.error(f"CoinStats news error: {exc}")
        return {"news": [], "source": "coinstats", "error": str(exc)[:120]}


@router.get("/markets")
async def coinstats_markets(user_id: str = Depends(get_current_user)):
    """Return top market tickers from CoinStats."""
    key = await _get_coinstats_key(user_id)
    if not key:
        return {"tickers": [], "source": "coinstats", "error": "API key not configured"}

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{COINSTATS_BASE}/coins",
                headers={"X-API-KEY": key, "accept": "application/json"},
                params={"limit": 50, "currency": "USD"},
            )
            if resp.status_code != 200:
                return {"tickers": [], "source": "coinstats", "error": f"HTTP {resp.status_code}"}

            data = resp.json()
            coins = data if isinstance(data, list) else data.get("result", data.get("coins", []))
            tickers = []
            for c in coins[:50]:
                tickers.append({
                    "symbol": c.get("symbol", ""),
                    "name": c.get("name", ""),
                    "price": c.get("price", 0),
                    "market_cap": c.get("marketCap", 0),
                    "volume_24h": c.get("volume", 0),
                    "price_change_1h": c.get("priceChange1h", 0),
                    "price_change_24h": c.get("priceChange1d", 0),
                    "price_change_7d": c.get("priceChange1w", 0),
                    "rank": c.get("rank", 0),
                    "icon": c.get("icon", ""),
                })

            return {"tickers": tickers, "source": "coinstats", "count": len(tickers)}
    except Exception as exc:
        logger.error(f"CoinStats markets error: {exc}")
        return {"tickers": [], "source": "coinstats", "error": str(exc)[:120]}
