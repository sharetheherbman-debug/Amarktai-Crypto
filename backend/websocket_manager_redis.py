"""
WebSocket Manager with Redis Pub/Sub Support
Handles realtime communication with graceful degradation
Supports multi-worker deployments via Redis broadcast
"""

import asyncio
import copy
import json
import logging
from typing import Dict, Set, Optional, Any
from datetime import datetime, timezone
import os

from bson import ObjectId, Decimal128, Binary
from bson.timestamp import Timestamp

from fastapi import WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)


def sanitize_for_json(obj: Any) -> Any:
    """
    Recursively sanitize data for JSON serialization.
    Converts ObjectId to str and datetime to timezone-aware ISO string.
    """
    if isinstance(obj, ObjectId):
        return str(obj)
    if isinstance(obj, Decimal128):
        return float(obj.to_decimal())
    if isinstance(obj, Timestamp):
        return datetime.fromtimestamp(obj.time, tz=timezone.utc).isoformat()
    if isinstance(obj, (bytes, bytearray, Binary)):
        return obj.hex()
    if isinstance(obj, datetime):
        if obj.tzinfo is None:
            obj = obj.replace(tzinfo=timezone.utc)
        return obj.isoformat()
    if isinstance(obj, dict):
        return {k: sanitize_for_json(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [sanitize_for_json(item) for item in obj]
    if isinstance(obj, (str, int, float, bool, type(None))):
        return obj
    return str(obj)


class ConnectionManager:
    """Manages WebSocket connections with Redis pub/sub support"""
    
    def __init__(self):
        # Local connections (in-memory for single worker)
        self.active_connections: Dict[str, Set[WebSocket]] = {}
        
        # Redis support for multi-worker
        self.redis_client = None
        self.redis_pubsub = None
        self.redis_enabled = False
        self.redis_listener_task = None
        
        # Message sequence tracking for reconnect/replay
        self.message_sequence = 0
        self.message_history: Dict[str, list] = {}  # user_id -> last N messages
        self.history_limit = 50
        # Last broadcast metadata for diagnostics (/api/diagnostics/realtime)
        self.last_event: Optional[dict] = None
        
    async def init_redis(self):
        """Initialize Redis connection for pub/sub"""
        try:
            redis_url = os.getenv('REDIS_URL', os.getenv('REDIS_HOST'))
            redis_flag = os.getenv('REDIS_ENABLED', 'true').lower() == 'true'

            if not redis_flag:
                logger.info("Redis disabled via REDIS_ENABLED=false")
                return
            if not redis_url:
                logger.info("Redis not configured, using in-memory realtime only")
                return
            
            import redis.asyncio as aioredis
            
            self.redis_client = await aioredis.from_url(
                redis_url,
                encoding="utf-8",
                decode_responses=True
            )
            
            # Test connection
            await self.redis_client.ping()
            
            # Setup pubsub
            self.redis_pubsub = self.redis_client.pubsub()
            await self.redis_pubsub.subscribe('amarktai:broadcast')
            
            # Start listener
            self.redis_listener_task = asyncio.create_task(self._redis_listener())
            
            self.redis_enabled = True
            logger.info("✅ Redis pub/sub initialized for realtime broadcast")
            
        except ImportError:
            logger.warning("redis package not installed, realtime limited to single worker")
        except Exception as e:
            logger.warning(f"Redis connection failed, using in-memory only: {e}")
            self.redis_enabled = False
    
    async def _redis_listener(self):
        """Listen for Redis pub/sub messages and broadcast locally"""
        try:
            while True:
                message = await self.redis_pubsub.get_message(ignore_subscribe_messages=True)
                if message and message['type'] == 'message':
                    data = json.loads(message['data'])
                    user_id = data.get('user_id')
                    payload = data.get('payload')
                    
                    if user_id and payload:
                        # Broadcast to local connections for this user
                        await self._send_to_local_connections(user_id, payload)
                        
                await asyncio.sleep(0.01)  # Small delay to prevent tight loop
                
        except asyncio.CancelledError:
            logger.info("Redis listener stopped")
        except Exception as e:
            logger.error(f"Redis listener error: {e}")
    
    async def connect(self, websocket: WebSocket, user_id: str, last_event_id: Optional[int] = None):
        """Connect a WebSocket client
        
        Args:
            websocket: WebSocket connection
            user_id: User ID
            last_event_id: Optional last event ID for replay
        """
        await websocket.accept()
        
        # Add to active connections
        if user_id not in self.active_connections:
            self.active_connections[user_id] = set()
        self.active_connections[user_id].add(websocket)
        
        logger.info(f"WebSocket connected for user {user_id[:8]}")
        
        # Send connection confirmation with sequence
        await self._send_to_websocket(websocket, {
            "type": "connection_established",
            "user_id": user_id,
            "current_sequence": self.message_sequence,
            "redis_enabled": self.redis_enabled,
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
        
        # Replay missed messages if requested
        if last_event_id is not None:
            await self._replay_messages(websocket, user_id, last_event_id)
    
    def disconnect(self, websocket: WebSocket, user_id: str):
        """Disconnect a WebSocket client
        
        Args:
            websocket: WebSocket connection
            user_id: User ID
        """
        if user_id in self.active_connections:
            self.active_connections[user_id].discard(websocket)
            if not self.active_connections[user_id]:
                del self.active_connections[user_id]
        
        logger.info(f"WebSocket disconnected for user {user_id[:8]}")
    
    async def send_message(self, user_id: str, message: dict):
        """Send message to all connections for a user
        
        Broadcasts via Redis if enabled, otherwise sends to local connections only
        
        Args:
            user_id: User ID
            message: Message dict to send
        """
        message = copy.deepcopy(message)
        self.message_sequence += 1
        message['sequence'] = self.message_sequence
        message['timestamp'] = message.get('timestamp', datetime.now(timezone.utc).isoformat())
        sanitized = sanitize_for_json(message)
        self.last_event = {
            "type": sanitized.get("type"),
            "timestamp": sanitized.get("timestamp")
        }
        
        # Store in history for replay
        if user_id not in self.message_history:
            self.message_history[user_id] = []
        self.message_history[user_id].append(sanitized)
        
        # Trim history
        if len(self.message_history[user_id]) > self.history_limit:
            self.message_history[user_id] = self.message_history[user_id][-self.history_limit:]
        
        # Broadcast via Redis if enabled
        if self.redis_enabled and self.redis_client:
            try:
                await self.redis_client.publish(
                    'amarktai:broadcast',
                    json.dumps({
                        'user_id': user_id,
                        'payload': sanitized
                    })
                )
                # Redis will broadcast back to us via listener
                return
            except Exception as e:
                logger.error(f"Redis publish failed, falling back to local: {e}")
        
        # Fallback to local connections
        await self._send_to_local_connections(user_id, sanitized)

    async def broadcast_to_user(self, message: dict, user_id: str):
        """Backward compatible alias for send_message."""
        await self.send_message(user_id, message)

    async def broadcast(self, message: dict):
        """Backward compatible alias for broadcast_all."""
        await self.broadcast_all(message)
    
    async def _send_to_local_connections(self, user_id: str, message: dict):
        """Send message to local WebSocket connections
        
        Args:
            user_id: User ID
            message: Message dict
        """
        if user_id not in self.active_connections:
            return
        
        disconnected = set()
        
        for connection in self.active_connections[user_id]:
            try:
                await self._send_to_websocket(connection, message)
            except Exception as e:
                logger.error(f"Send failed, marking for disconnect: {e}")
                disconnected.add(connection)
        
        # Clean up disconnected
        for connection in disconnected:
            self.active_connections[user_id].discard(connection)
    
    async def _send_to_websocket(self, websocket: WebSocket, message: dict):
        """Send message to a single WebSocket
        
        Args:
            websocket: WebSocket connection
            message: Message dict
        """
        await websocket.send_json(message)
    
    async def _replay_messages(self, websocket: WebSocket, user_id: str, last_event_id: int):
        """Replay missed messages since last_event_id
        
        Args:
            websocket: WebSocket connection
            user_id: User ID
            last_event_id: Last sequence ID client received
        """
        if user_id not in self.message_history:
            return
        
        # Find messages after last_event_id
        missed_messages = [
            msg for msg in self.message_history[user_id]
            if msg.get('sequence', 0) > last_event_id
        ]
        
        if missed_messages:
            logger.info(f"Replaying {len(missed_messages)} messages for user {user_id[:8]}")
            for msg in missed_messages:
                try:
                    await self._send_to_websocket(websocket, msg)
                except Exception as e:
                    logger.error(f"Replay failed: {e}")
                    break
    
    async def broadcast_all(self, message: dict):
        """Broadcast message to all connected users
        
        Args:
            message: Message dict
        """
        for user_id in list(self.active_connections.keys()):
            await self.send_message(user_id, message)
    
    async def close(self):
        """Close all connections and cleanup"""
        # Cancel Redis listener
        if self.redis_listener_task:
            self.redis_listener_task.cancel()
            try:
                await self.redis_listener_task
            except asyncio.CancelledError:
                pass
        
        # Close Redis connection
        if self.redis_pubsub:
            await self.redis_pubsub.unsubscribe('amarktai:broadcast')
            await self.redis_pubsub.close()
        
        if self.redis_client:
            await self.redis_client.close()
        
        # Close all WebSocket connections
        for user_id, connections in list(self.active_connections.items()):
            for connection in list(connections):
                try:
                    await connection.close()
                except:
                    pass
        
        self.active_connections.clear()
        logger.info("WebSocket manager closed")
    
    def get_status(self) -> dict:
        """Get realtime status for preflight
        
        Returns:
            Status dict with connection info
        """
        return {
            "enabled": True,
            "redis_enabled": self.redis_enabled,
            "transport": "websocket",
            "active_users": len(self.active_connections),
            "total_connections": sum(len(conns) for conns in self.active_connections.values()),
            "message_sequence": self.message_sequence,
            "status": "ok" if self.redis_enabled else "degraded",
            "message": "Multi-worker support active" if self.redis_enabled else "Single-worker mode (realtime degraded)"
        }


# Global singleton
manager = ConnectionManager()
