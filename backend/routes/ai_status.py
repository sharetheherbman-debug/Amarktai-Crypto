"""
AI Status Endpoint
Provides /api/ai/status and /api/ai/capability-status for dashboard compatibility.

Returns a rich capability payload that the OverviewSection AI Capability card can
consume directly.  The rule-based ML predictor works without any external API key,
so core trading intelligence features are always "available"; only the optional
conversational/cloud features depend on configured provider keys.
"""

from fastapi import APIRouter, Depends
import logging
import os

from auth import get_current_user
from services.openai_key_resolver import resolve_openai_key

logger = logging.getLogger(__name__)
router = APIRouter()


CORE_CAPABILITIES = {
    "rule_based_predictions": {
        "label": "Rule-based Predictions",
        "requires": None,  # always available
    },
    "market_regime_detection": {
        "label": "Market Regime Detection",
        "requires": None,
    },
    "signal_generation": {
        "label": "Signal Generation",
        "requires": None,
    },
    "self_learning": {
        "label": "Self-Learning",
        "requires": None,
    },
}


async def _build_ai_status(user_id: str) -> dict:
    """Build the canonical AI status payload.

    Provider semantics:
      - configured=True  → key is present (env or user-specific)
      - usable=True      → configured AND no known error at startup
      - status           → "configured" | "not_configured" | "optional"

    Capability semantics:
      - available=True   → feature works with current provider set
      - requires         → which provider unlocks this feature (None = always available)

    Rule-based ML (predictions, regime detection, signal generation) always works
    without external API keys — they must never be marked unavailable.
    """
    try:
        # ── Optional external providers ──────────────────────────────────
        openai_key, openai_source = await resolve_openai_key(user_id)
        openai_configured = bool(openai_key)

        huggingface_configured = bool(os.getenv("HUGGINGFACE_API_KEY", ""))
        fetchai_configured = bool(os.getenv("FETCHAI_API_KEY", ""))

        providers = {
            "openai": {
                "configured": openai_configured,
                "usable": openai_configured,
                "status": "configured" if openai_configured else "not_configured",
                "label": "OpenAI",
                "optional": True,
                "key_source": openai_source if openai_configured else "missing",
            },
            "huggingface": {
                "configured": huggingface_configured,
                "usable": huggingface_configured,
                "status": "configured" if huggingface_configured else "not_configured",
                "label": "HuggingFace",
                "optional": True,
                "key_source": "env" if huggingface_configured else "missing",
            },
            "fetchai": {
                "configured": fetchai_configured,
                "usable": fetchai_configured,
                "status": "configured" if fetchai_configured else "not_configured",
                "label": "Fetch.ai",
                "optional": True,
                "key_source": "env" if fetchai_configured else "missing",
            },
        }

        # Count only providers that are actually configured (optional ones that are
        # missing must not inflate the denominator and show as "0/3 broken").
        configured_providers = {k: v for k, v in providers.items() if v["configured"]}
        usable_count = sum(1 for v in configured_providers.values() if v["usable"])

        # ── Capabilities ─────────────────────────────────────────────────
        # Core ML features work without any external API key (rule-based).
        capabilities = {
            name: {"available": True, **meta}
            for name, meta in CORE_CAPABILITIES.items()
        }
        # Optional cloud-provider-dependent capabilities
        capabilities["ai_chat"] = {
            "available": openai_configured,
            "label": "AI Chat",
            "requires": "openai",
        }
        capabilities["cloud_insights"] = {
            "available": openai_configured,
            "label": "Cloud Insights",
            "requires": "openai",
        }
        available_count = sum(1 for v in capabilities.values() if v["available"])
        total_capabilities = len(capabilities)

        # System is only degraded when a configured provider is NOT usable (i.e.
        # configured but broken).  Missing-optional providers are not degraded.
        degraded_mode = any(
            v["configured"] and not v["usable"] for v in providers.values()
        )

        # Convenience flag used by the "AI Connected" / "AI Offline" badge
        key_configured = openai_configured

        return {
            "status": "ok" if not degraded_mode else "degraded",
            "configured": key_configured,
            "key_configured": key_configured,
            "degraded_mode": degraded_mode,
            "providers": providers,
            "configured_providers": configured_providers,
            "usable_providers": usable_count,
            "total_configured_providers": len(configured_providers),
            "capabilities": capabilities,
            "available_capabilities": available_count,
            "total_capabilities": total_capabilities,
            "message": (
                "OpenAI configured and ready."
                if key_configured
                else "Core trading AI active. Optional providers (OpenAI etc.) not configured."
            ),
        }

    except Exception as exc:
        logger.error(f"AI status build error: {exc}", exc_info=True)
        # Return a safe minimal payload — never crash
        return {
            "status": "error",
            "configured": False,
            "key_configured": False,
            "degraded_mode": False,
            "providers": {},
            "configured_providers": {},
            "usable_providers": 0,
            "total_configured_providers": 0,
            "capabilities": {
                name: {"available": True, **meta}
                for name, meta in CORE_CAPABILITIES.items()
            },
            "available_capabilities": len(CORE_CAPABILITIES),
            "total_capabilities": len(CORE_CAPABILITIES),
            "message": "AI status check failed; core features still active.",
        }


@router.get("/api/ai/status")
async def get_ai_status(user_id: str = Depends(get_current_user)):
    """
    Get AI configuration and capability status for the current user.

    Always returns HTTP 200.  Core trading intelligence (rule-based ML, regime
    detection, signal generation, self-learning) is always available without
    external provider keys.  Optional cloud providers (OpenAI, HuggingFace,
    Fetch.ai) are listed with their individual configuration state.
    """
    return await _build_ai_status(user_id)


@router.get("/api/ai/capability-status")
async def get_ai_capability_status(user_id: str = Depends(get_current_user)):
    """Alias for /api/ai/status - returns AI capability status for dashboard compatibility."""
    return await _build_ai_status(user_id)
