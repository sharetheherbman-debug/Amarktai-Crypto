"""
WebSocket Realtime Route
Handles WebSocket connections with authentication
Supports query param and header-based token auth
Implements reconnect/replay logic
"""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query, Header
from typing import Optional
import logging
import jwt
import os

logger = logging.getLogger(__name__)

router = APIRouter(tags=["WebSocket"])


async def get_user_id_from_token(token: Optional[str]) -> Optional[str]:
    """Extract user ID from JWT token
    
    Args:
        token: JWT token string
        
    Returns:
        User ID or None if invalid
    """
    if not token:
        return None
    
    try:
        # Remove "Bearer " prefix if present
        if token.startswith("Bearer "):
            token = token[7:]
        
        # Decode JWT
        secret = os.getenv('JWT_SECRET', 'your-secret-key-change-in-production')
        payload = jwt.decode(token, secret, algorithms=["HS256"])
        
        return payload.get('sub')
        
    except Exception as e:
        logger.error(f"Token decode error: {e}")
        return None


@router.websocket("/api/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    token: Optional[str] = Query(None),
    authorization: Optional[str] = Header(None),
    last_event_id: Optional[int] = Query(None)
):
    """WebSocket endpoint for realtime updates
    
    Authentication via:
    - Query parameter: /api/ws?token=xxx
    - Header: Authorization: Bearer xxx
    
    Reconnect support:
    - Query parameter: /api/ws?token=xxx&last_event_id=123
    
    Args:
        websocket: WebSocket connection
        token: Optional token from query parameter
        authorization: Optional token from header
        last_event_id: Optional last event ID for replay
    """
    # Try to get token from query param or header
    auth_token = token or authorization
    
    # Authenticate
    user_id = await get_user_id_from_token(auth_token)
    
    if not user_id:
        logger.warning(f"❌ WebSocket connection REJECTED: invalid or missing token (client: {websocket.client})")
        await websocket.close(code=1008, reason="Authentication required")
        return
    
    # Import canonical manager used by realtime emitters
    from websocket_manager import manager
    
    # Connect client
    logger.info(f"✅ WebSocket connection ACCEPTED for user {user_id[:8]}... (client: {websocket.client})")
    await manager.connect(websocket, user_id)
    
    try:
        # Keep connection alive and handle messages
        while True:
            # Receive messages from client (ping/pong, etc.)
            data = await websocket.receive_json()
            
            # Handle client messages
            if data.get('type') == 'ping':
                await websocket.send_json({
                    'type': 'pong',
                    'timestamp': data.get('timestamp')
                })
            elif data.get('type') == 'request_replay':
                # Client requests replay from specific sequence
                last_seq = data.get('last_sequence', last_event_id or 0)
                await manager._replay_messages(websocket, user_id, last_seq)
                
    except WebSocketDisconnect:
        logger.info(f"🔌 WebSocket DISCONNECTED (clean) for user {user_id[:8]}...")
    except Exception as e:
        logger.error(f"❌ WebSocket ERROR for user {user_id[:8]}...: {e}")
    finally:
        manager.disconnect(websocket, user_id)
        logger.info(f"🔌 WebSocket cleanup complete for user {user_id[:8]}...")
