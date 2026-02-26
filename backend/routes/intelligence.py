"""
Automatic Market Intelligence Routes
Exposes the intelligence pipeline status and latest results.
Intelligence runs automatically on a schedule — no user input required.
"""

from fastapi import APIRouter, Depends
from datetime import datetime, timezone
import logging
import time

from auth import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/intelligence", tags=["Intelligence"])


@router.get("/status")
async def get_intelligence_status(user_id: str = Depends(get_current_user)):
    """
    GET /api/intelligence/status

    Returns the current status of the automatic Market Intelligence pipeline.

    What it does:
      - Fetches latest crypto news headlines from CoinStats every 60 seconds (configurable).
      - Runs sentiment classification on each headline (positive / negative / neutral).
      - Detects risk categories (regulation, hack, volatility, etc.).
      - Produces a plain-English market brief.
      - If a HuggingFace API key is configured, HF models are used for enrichment;
        otherwise, heuristic fallbacks produce equivalent results in real time.

    Returns:
      - running: bool — pipeline is active
      - hf_enabled: bool — HuggingFace enrichment is active
      - last_run_at: ISO timestamp of most recent run (or null)
      - next_run_in_seconds: approximate seconds until next refresh
      - mood: current market mood (positive | negative | neutral)
      - source: "CoinStats"
      - coinstats_configured: bool — whether CoinStats key is resolved for this user
      - key_source: "user" | "env" | "none"
      - resolved_for_user_id: the user_id the key was resolved for
    """
    try:
        from services.market_intelligence_service import (
            get_latest_intelligence,
            get_intelligence_status as _get_status,
            _REFRESH_INTERVAL,
        )
        from services.news_coinstats import resolve_coinstats_key

        brief = await get_latest_intelligence(user_id=user_id)
        status = _get_status()
        last_run_at = brief.get("updated_at") or status.get("last_run_at")

        next_run_in = status.get("next_run_in_seconds")
        if next_run_in is None and last_run_at:
            try:
                last_dt = datetime.fromisoformat(last_run_at.replace("Z", "+00:00"))
                elapsed = (datetime.now(timezone.utc) - last_dt).total_seconds()
                next_run_in = max(0, int(_REFRESH_INTERVAL - elapsed))
            except Exception:
                pass

        # Check HF config (best-effort)
        hf_enabled = False
        try:
            import os
            hf_enabled = bool(os.getenv("HUGGINGFACE_API_KEY") or os.getenv("HF_API_KEY"))
        except Exception:
            pass

        # Resolve CoinStats key for this specific user so status is accurate per-user
        _resolved_key, key_source = await resolve_coinstats_key(user_id)
        coinstats_configured = bool(_resolved_key)

        # Derive fetch_status: if the user has a valid key, never report key_missing
        fetch_status = brief.get("fetch_status", "ok" if last_run_at else "pending")
        if coinstats_configured and fetch_status == "key_missing":
            fetch_status = "ok" if last_run_at else "pending"

        # block_reason is irrelevant when the key is configured for this user
        block_reason = brief.get("block_reason") if not coinstats_configured else None

        return {
            "running": True,
            "hf_enabled": hf_enabled,
            "source": "CoinStats",
            "mood": brief.get("mood", "neutral"),
            "last_run_at": last_run_at,
            "next_run_in_seconds": next_run_in,
            "refresh_interval_seconds": _REFRESH_INTERVAL,
            "last_error": status.get("last_error"),
            "fetch_status": fetch_status,
            "coinstats_configured": coinstats_configured,
            "key_source": key_source,
            "resolved_for_user_id": user_id,
            "block_reason": block_reason,
            "what_it_does": (
                "Automatically fetches CoinStats headlines every "
                f"{_REFRESH_INTERVAL}s, classifies market sentiment, "
                "detects risk events, and generates a plain-English market brief. "
                "No manual input is needed."
            ),
        }
    except Exception as e:
        logger.error(f"Intelligence status error: {e}")
        return {
            "running": False,
            "hf_enabled": False,
            "source": "CoinStats",
            "mood": "neutral",
            "last_run_at": None,
            "next_run_in_seconds": None,
            "refresh_interval_seconds": 60,
            "last_error": str(e),
            "error": str(e),
            "fetch_status": "error",
            "coinstats_configured": False,
            "key_source": "none",
            "resolved_for_user_id": user_id,
            "what_it_does": "Automatic market intelligence pipeline (temporarily unavailable).",
        }


@router.get("/latest")
async def get_latest_intelligence(user_id: str = Depends(get_current_user)):
    """
    GET /api/intelligence/latest

    Returns the most recent automatic intelligence output.

    Fields:
      - mood: positive | negative | neutral
      - brief: Top headline or summary sentence
      - top_risk: Risk label detected (or "none")
      - confidence: Plain-English confidence description
      - what_amarktai_is_doing: How the platform is responding
      - source: "CoinStats"
      - updated_at: ISO timestamp of last update
      - headlines_count: Number of articles processed
    """
    try:
        from services.market_intelligence_service import get_latest_intelligence as _get
        brief = await _get(user_id=user_id)
        return brief
    except Exception as e:
        logger.error(f"Intelligence latest error: {e}")
        return {
            "mood": "neutral",
            "brief": "Intelligence data temporarily unavailable.",
            "top_risk": "none",
            "confidence": "Unknown",
            "what_amarktai_is_doing": "Monitoring markets.",
            "source": "CoinStats",
            "updated_at": None,
            "error": str(e),
        }
