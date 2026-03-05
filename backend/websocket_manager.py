"""
WebSocket Manager for Real-Time Updates
Handles WebSocket connections and broadcasts
"""
import asyncio
from fastapi import WebSocket
from typing import Dict, Set, Any
import json
import logging
from datetime import datetime, timezone
from bson import ObjectId

logger = logging.getLogger(__name__)


def sanitize_for_json(obj: Any) -> Any:
    """
    Recursively sanitize data for JSON serialization.
    Converts ObjectId to str and datetime to timezone-aware ISO string.
    
    Args:
        obj: Object to sanitize (can be dict, list, or primitive)
        
    Returns:
        JSON-serializable version of obj
    """
    if isinstance(obj, ObjectId):
        return str(obj)
    elif isinstance(obj, datetime):
        # Ensure timezone-aware
        if obj.tzinfo is None:
            obj = obj.replace(tzinfo=timezone.utc)
        return obj.isoformat()
    elif isinstance(obj, dict):
        return {k: sanitize_for_json(v) for k, v in obj.items()}
    elif isinstance(obj, (list, tuple)):
        return [sanitize_for_json(item) for item in obj]
    elif isinstance(obj, (str, int, float, bool, type(None))):
        return obj
    else:
        # Fallback: convert to string for unknown types
        return str(obj)

class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, Set[WebSocket]] = {}
        self.ping_intervals: Dict[WebSocket, asyncio.Task] = {}
        self.ping_interval = 30  # Ping every 30 seconds
        self.pong_timeout = 10  # Wait 10 seconds for pong
        self.last_event: "dict | None" = None  # Track last broadcast event for diagnostics
        
    async def connect(self, websocket: WebSocket, user_id: str):
        """Accept and register new WebSocket connection"""
        await websocket.accept()
        
        if user_id not in self.active_connections:
            self.active_connections[user_id] = set()
        
        self.active_connections[user_id].add(websocket)
        logger.info(f"WebSocket connected for user {user_id}")
        
        # Start ping task
        task = asyncio.create_task(self._ping_loop(websocket))
        self.ping_intervals[websocket] = task
        
        # Send initial connection message
        await self.send_personal_message({
            "type": "connection",
            "status": "Connected",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }, websocket)
        
    async def disconnect(self, websocket: WebSocket, user_id: str):
        """Remove WebSocket connection"""
        if user_id in self.active_connections:
            self.active_connections[user_id].discard(websocket)
            
            if not self.active_connections[user_id]:
                del self.active_connections[user_id]
        
        # Cancel ping task
        if websocket in self.ping_intervals:
            self.ping_intervals[websocket].cancel()
            del self.ping_intervals[websocket]
            
        logger.info(f"WebSocket disconnected for user {user_id}")
        
    async def send_personal_message(self, message: dict, websocket: WebSocket):
        """Send message to specific WebSocket"""
        try:
            # Sanitize message before sending
            sanitized = sanitize_for_json(message)
            await websocket.send_json(sanitized)
        except Exception as e:
            logger.error(f"Failed to send message: {e}")
            
    async def send_message(self, user_id: str, message: dict):
        """Send message to all connections of a user (alias for broadcast_to_user)"""
        await self.broadcast_to_user(message, user_id)
    
    async def broadcast_to_user(self, message: dict, user_id: str):
        """Broadcast message to all connections of a specific user"""
        if user_id in self.active_connections:
            disconnected = set()

            try:
                from services.autonomy_heartbeat import heartbeat_registry
                heartbeat_registry.mark_ok("realtime")
            except Exception:
                pass
            
            # Track last broadcast event for diagnostics
            self.last_event = {
                "type": message.get("type"),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

            # Sanitize message once before broadcasting
            sanitized = sanitize_for_json(message)
            
            for connection in self.active_connections[user_id]:
                try:
                    await connection.send_json(sanitized)
                except Exception as e:
                    logger.error(f"Broadcast error: {e}")
                    try:
                        from services.autonomy_heartbeat import heartbeat_registry
                        heartbeat_registry.mark_error("realtime", str(e))
                    except Exception:
                        pass
                    disconnected.add(connection)
            
            # Clean up disconnected sockets
            for ws in disconnected:
                await self.disconnect(ws, user_id)
                
    async def broadcast_to_all(self, message: dict):
        """Broadcast message to all connected users"""
        for user_id in list(self.active_connections.keys()):
            await self.broadcast_to_user(message, user_id)
    
    async def broadcast(self, message: dict):
        """Alias for broadcast_to_all() - for backward compatibility"""
        await self.broadcast_to_all(message)
            
    async def _ping_loop(self, websocket: WebSocket):
        """Send periodic pings and wait for pongs to keep connection alive"""
        try:
            while True:
                await asyncio.sleep(self.ping_interval)
                
                # Send ping
                try:
                    await websocket.send_json({
                        "type": "ping",
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    })
                    
                    # Wait for pong (frontend should respond with pong)
                    # If no pong within timeout, connection is stale
                    try:
                        await asyncio.wait_for(
                            self._wait_for_pong(websocket),
                            timeout=self.pong_timeout
                        )
                    except asyncio.TimeoutError:
                        logger.warning("Pong timeout - connection may be stale")
                        # Continue anyway, let disconnect handle cleanup
                        
                except Exception as e:
                    logger.debug(f"Ping send error: {e}")
                    break
                    
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Ping loop error: {e}")
    
    async def _wait_for_pong(self, websocket: WebSocket):
        """Wait for pong message (handled by frontend)"""
        # This is a placeholder - actual pong handling is in the websocket endpoint
        await asyncio.sleep(0.1)

# Global instance (ensure parity with /api/ws)
from websocket_manager_redis import manager  # noqa: E402
