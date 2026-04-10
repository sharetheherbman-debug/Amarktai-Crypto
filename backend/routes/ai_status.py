"""
AI Status Endpoint
Provides /api/ai/status for dashboard compatibility.
Returns OpenAI configuration status without crashing.
"""

from fastapi import APIRouter, Depends
import logging
import os

from auth import get_current_user
from services.openai_key_resolver import resolve_openai_key

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/api/ai/status")
async def get_ai_status(user_id: str = Depends(get_current_user)):
    """
    Get AI configuration status for the current user.
    
    Always returns HTTP 200 with status information.
    - If OpenAI key is configured: returns {"status": "ok"}
    - If not configured: returns {"status": "not_configured"}
    
    Args:
        user_id: Current authenticated user ID
        
    Returns:
        JSON with status information
    """
    try:
        # Resolve OpenAI key for the user
        api_key, source = await resolve_openai_key(user_id)
        
        if api_key:
            return {
                "status": "ok",
                "configured": True,
                "key_source": source,
                "message": "OpenAI API key is configured"
            }
        else:
            return {
                "status": "not_configured",
                "configured": False,
                "key_source": "missing",
                "message": "OpenAI API key not configured. Add your key in settings."
            }
            
    except Exception as e:
        # Never crash - degrade gracefully
        logger.error(f"AI status check error: {e}", exc_info=True)
        return {
            "status": "error",
            "configured": False,
            "key_source": "unknown",
            "message": "Unable to check AI configuration status"
        }


@router.get("/api/ai/capability-status")
async def get_ai_capability_status(user_id: str = Depends(get_current_user)):
    """Alias for /api/ai/status - returns AI capability status for dashboard compatibility."""
    return await get_ai_status(user_id)
