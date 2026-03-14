"""
FX Rates API — Live Fiat Exchange Rate Diagnostics
====================================================

Exposes the canonical fiat FX rates used across the system.

Endpoints:
  GET /api/fx/rates      — current ZAR/USD/GBP/EUR rates, source, age
  POST /api/fx/refresh   — force a background refresh from live providers
  GET /api/fx/health     — provider health check (live vs cache vs fallback)

These endpoints are READ-ONLY for display/diagnostics.
They do NOT affect trading execution.
"""

from fastapi import APIRouter, Depends
import logging

from auth import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/fx", tags=["FX Rates"])


@router.get("/rates")
async def get_fiat_rates(user_id: str = Depends(get_current_user)):
    """Return current fiat FX rates used for display-currency conversion.

    Shows ZAR per 1 unit for each supported display currency (USD, GBP, EUR).
    Includes source label so the UI can show "live" vs "cached" vs "fallback".

    Response:
        {
          "rates": {
            "USD": {"rate_zar_per_unit": 18.5, "source": "live_fiat_primary", ...},
            "GBP": {...},
            "EUR": {...}
          },
          "usdt_zar_rate": {"rate": 19.0, "source": "cache"},
          "internal_currency": "ZAR",
          "display_currencies_supported": ["ZAR", "USD", "GBP", "EUR"]
        }
    """
    try:
        from services.fiat_fx_provider import get_rates_snapshot as _snap
        from services.fx_normalizer import (
            get_current_usdt_zar_rate as _usdt_rate,
            SUPPORTED_DISPLAY_CURRENCIES,
        )

        snapshot = _snap()
        usdt_rate, usdt_source = _usdt_rate()

        return {
            **snapshot,
            "usdt_zar_rate": {
                "rate": round(usdt_rate, 4),
                "source": usdt_source,
            },
            "internal_currency": "ZAR",
            "display_currencies_supported": list(SUPPORTED_DISPLAY_CURRENCIES),
        }
    except Exception as exc:
        logger.error("FX rates endpoint error: %s", exc)
        return {
            "error": str(exc),
            "rates": {},
            "internal_currency": "ZAR",
            "display_currencies_supported": ["ZAR", "USD", "GBP", "EUR"],
        }


@router.post("/refresh")
async def refresh_fiat_rates(user_id: str = Depends(get_current_user)):
    """Trigger an immediate background refresh of fiat FX rates.

    Returns the result of the refresh attempt.
    """
    try:
        from services.fiat_fx_provider import refresh_rates_async
        import asyncio

        result = await refresh_rates_async()
        if result:
            return {
                "status": "refreshed",
                "currencies_updated": list(result.keys()),
                "rates": {cur: round(rate, 6) for cur, rate in result.items()},
            }
        return {
            "status": "failed",
            "message": "All fiat FX providers unavailable. Using cached/fallback rates.",
        }
    except Exception as exc:
        logger.error("FX refresh endpoint error: %s", exc)
        return {"status": "error", "error": str(exc)}


@router.get("/health")
async def get_fx_health(user_id: str = Depends(get_current_user)):
    """Return provider health status for fiat FX rates."""
    try:
        from services.fiat_fx_provider import get_rates_snapshot as _snap, CACHE_TTL_SECONDS
        from services.fx_normalizer import get_current_usdt_zar_rate

        snapshot = _snap()
        usdt_rate, usdt_source = get_current_usdt_zar_rate()

        rates_info = snapshot.get("rates", {})
        all_fresh = all(r.get("fresh", False) for r in rates_info.values())
        any_live = any(
            "live" in r.get("source", "") for r in rates_info.values()
        )

        return {
            "fiat_rates_fresh": all_fresh,
            "fiat_rates_source": "live" if any_live else "cache_or_fallback",
            "usdt_zar_rate": usdt_rate,
            "usdt_zar_source": usdt_source,
            "cache_ttl_seconds": CACHE_TTL_SECONDS,
            "currencies": {
                cur: {
                    "rate": info.get("rate_zar_per_unit"),
                    "source": info.get("source"),
                    "fresh": info.get("fresh"),
                    "age_seconds": info.get("age_seconds"),
                }
                for cur, info in rates_info.items()
            },
        }
    except Exception as exc:
        logger.error("FX health endpoint error: %s", exc)
        return {"status": "error", "error": str(exc)}
