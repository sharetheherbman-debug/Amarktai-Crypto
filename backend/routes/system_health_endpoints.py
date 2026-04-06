"""
System Health Indicators
Provides real-time system status for dashboard LEDs
"""

from fastapi import APIRouter, HTTPException
from typing import Dict
import logging
import asyncio
from datetime import datetime, timezone
import time

import database as db
from websocket_manager import manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/health", tags=["System Health"])

# Global health metrics
health_metrics = {
    "api": {"status": "unknown", "last_check": None, "response_time": 0},
    "database": {"status": "unknown", "last_check": None, "response_time": 0},
    "websocket": {"status": "unknown", "active_connections": 0, "last_check": None},
    "sse": {"status": "unknown", "active_streams": 0, "last_check": None}
}

@router.get("/indicators")
async def get_health_indicators():
    """Get system health indicators for dashboard LEDs"""
    try:
        start_time = time.time()
        
        # 1. API Health (this endpoint responding = healthy)
        api_health = {
            "status": "healthy",
            "last_check": datetime.now(timezone.utc).isoformat(),
            "response_time": 0  # Will be calculated
        }
        
        # 2. Database Health
        try:
            db_start = time.time()
            await db.client.admin.command('ping')
            db_time = (time.time() - db_start) * 1000  # Convert to ms
            
            db_health = {
                "status": "healthy" if db_time < 100 else "degraded",
                "last_check": datetime.now(timezone.utc).isoformat(),
                "response_time": round(db_time, 2)
            }
        except:
            db_health = {
                "status": "unhealthy",
                "last_check": datetime.now(timezone.utc).isoformat(),
                "response_time": 0
            }
        
        # 3. WebSocket Health
        ws_connections = sum(len(conns) for conns in manager.active_connections.values())
        ws_health = {
            "status": "healthy",
            "active_connections": ws_connections,
            "last_check": datetime.now(timezone.utc).isoformat()
        }
        
        # 4. SSE Health (placeholder - would need actual SSE connection tracking)
        sse_health = {
            "status": "healthy",
            "active_streams": 0,  # Would track actual SSE streams
            "last_check": datetime.now(timezone.utc).isoformat()
        }
        
        # Calculate API response time
        api_time = (time.time() - start_time) * 1000
        api_health["response_time"] = round(api_time, 2)
        
        # Overall RTT (Round Trip Time)
        overall_rtt = round(api_time + db_time, 2) if db_health["status"] != "unhealthy" else 0
        
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "overall_status": "healthy" if all(
                h.get("status") == "healthy" 
                for h in [api_health, db_health, ws_health, sse_health]
            ) else "degraded",
            "overall_rtt": overall_rtt,
            "indicators": {
                "api": api_health,
                "database": db_health,
                "websocket": ws_health,
                "sse": sse_health
            }
        }
        
    except Exception as e:
        logger.error(f"Health indicators error: {e}")
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "overall_status": "unhealthy",
            "overall_rtt": 0,
            "indicators": {
                "api": {"status": "unhealthy", "error": str(e)},
                "database": {"status": "unknown"},
                "websocket": {"status": "unknown"},
                "sse": {"status": "unknown"}
            }
        }

@router.get("/ping")
async def ping():
    """Simple ping endpoint for health checks"""
    return {
        "status": "ok",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


@router.get("/paper-trading")
async def get_paper_trading_status():
    """Get paper trading engine status for monitoring"""
    try:
        from paper_trading_engine import paper_engine
        
        status = paper_engine.get_status()
        
        return {
            "status": "ok",
            "paper_trading": status,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as e:
        logger.error(f"Paper trading status error: {e}")
        return {
            "status": "error",
            "error": str(e),
            "paper_trading": {
                "is_running": False,
                "last_error": str(e)
            },
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

