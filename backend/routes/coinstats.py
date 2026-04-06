"""
CoinStats API Routes
Provides connectivity testing for the CoinStats news integration.
"""

import logging

from fastapi import APIRouter, Depends

from auth import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/coinstats", tags=["CoinStats"])


@router.get("/test-connection")
async def coinstats_test_connection(user_id: str = Depends(get_current_user)):
    """Test CoinStats API key connectivity. Always returns structured JSON, never 500."""
    try:
        from services.news_coinstats import coinstats_provider
        return await coinstats_provider.test_connection(user_id=user_id)
    except Exception as e:
        logger.error(f"CoinStats test-connection error: {e}")
        return {
            "status": "error",
            "configured": False,
            "source": "none",
            "message": str(e),
            "http_status": None,
            "latency_ms": None,
        }
