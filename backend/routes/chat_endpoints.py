"""
Chat endpoints for frontend compatibility
Provides POST /api/chat/message as an alias to /api/ai/chat
"""

from fastapi import APIRouter, HTTPException, Depends, Body
from fastapi.responses import JSONResponse
from datetime import datetime, timezone
from typing import Dict
import logging

from auth import get_current_user
import database as db
from routes.ai_chat import ai_chat, get_chat_history

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/chat", tags=["Chat"])


@router.post("/message")
async def chat_message(
    payload: Dict = Body(...),
    user_id: str = Depends(get_current_user)
):
    """
    Chat message endpoint - frontend compatibility alias
    
    Accepts either:
    - {"message": "text"} or
    - {"content": "text"}
    
    Routes to main AI chat handler
    """
    try:
        # Normalize payload - support both "message" and "content" keys
        message_text = payload.get('message') or payload.get('content', '')
        
        if not message_text:
            raise HTTPException(status_code=400, detail="Message text required")
        
        # Transform to ai_chat format
        ai_payload = {
            'content': message_text,
            'request_action': payload.get('request_action', False),
            'confirmation_token': payload.get('confirmation_token') or payload.get('confirmation_id'),
            'confirmation_phrase': payload.get('confirmation_phrase')
        }
        
        # Call main AI chat handler
        response = await ai_chat(ai_payload, user_id)
        
        # Ensure response format includes success flag
        if isinstance(response, JSONResponse):
            return response
        if isinstance(response, dict):
            response.setdefault('success', True)
            return response
        else:
            return {
                "success": True,
                "response": str(response),
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Chat message error: {e}")
        return {
            "success": False,
            "error": str(e),
            "response": "Sorry, I encountered an error processing your message.",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }


@router.get("/history")
async def chat_history(
    days: int = 30,
    limit: int = 100,
    user_id: str = Depends(get_current_user)
):
    """Chat history alias for frontend compatibility."""
    return await get_chat_history(days=days, limit=limit, user_id=user_id)
