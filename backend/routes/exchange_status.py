"""
Exchange Status & Test Endpoints

Provides:
  GET  /api/exchanges/status  — status of all 7 exchanges for the authenticated user
  POST /api/exchanges/test    — test connectivity to a specific exchange
"""

from fastapi import APIRouter, Depends, HTTPException, Body
from typing import Dict
import logging

from auth import get_current_user
from services.exchange_adapter import exchange_adapter, SUPPORTED_EXCHANGES

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/exchanges", tags=["Exchanges"])


@router.get("/status")
async def exchanges_status(user_id: str = Depends(get_current_user)):
    """
    GET /api/exchanges/status

    Returns configuration + readiness status for all 7 supported exchanges.
    Shows: configured/not, last tested, pass/fail, error reason, default pairs.
    """
    results = []
    for ex in SUPPORTED_EXCHANGES:
        status = await exchange_adapter.get_exchange_status(ex, user_id=user_id)
        results.append(status)

    return {
        "total": len(results),
        "configured_count": sum(1 for s in results if s.get("configured")),
        "exchanges": results,
    }


@router.post("/test")
async def test_exchange(
    user_id: str = Depends(get_current_user),
    payload: Dict = Body(...),
):
    """
    POST /api/exchanges/test

    Test connectivity to a specific exchange.
    Body: { "exchange": "binance" }
    Optional: { "exchange": "binance", "api_key": "...", "secret": "..." }
    """
    exchange = payload.get("exchange", "").lower()
    if not exchange:
        raise HTTPException(status_code=400, detail="exchange is required")
    if not exchange_adapter.is_supported(exchange):
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported exchange: {exchange}. Supported: {SUPPORTED_EXCHANGES}",
        )

    api_key = payload.get("api_key", "")
    secret = payload.get("secret", "")
    passphrase = payload.get("passphrase", "")

    result = await exchange_adapter.test_connection(
        exchange, api_key=api_key, secret=secret, passphrase=passphrase
    )

    return result
