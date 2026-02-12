"""
Realtime Broadcaster
Periodically publishes dashboard updates to WebSocket clients.
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Dict, List

import database as db
from websocket_manager import manager
from services.overview_service import OverviewService
from routes.prices import get_live_prices

logger = logging.getLogger(__name__)


class RealtimeBroadcaster:
    def __init__(self):
        self._task: asyncio.Task | None = None
        self._running = False
        self.interval_seconds = float(
            __import__("os").getenv("REALTIME_BROADCAST_INTERVAL", "5")
        )
        self.overview_service = OverviewService()

    async def start(self):
        if self._task:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop())
        logger.info("📡 Realtime broadcaster started (interval=%ss)", self.interval_seconds)

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()
            self._task = None
        logger.info("📡 Realtime broadcaster stopped")

    async def _loop(self):
        while self._running:
            try:
                await self.broadcast_updates()
            except Exception as e:
                logger.error(f"Realtime broadcast error: {e}")
            await asyncio.sleep(self.interval_seconds)

    async def broadcast_updates(self):
        user_ids = list(manager.active_connections.keys())
        if not user_ids:
            return

        timestamp = datetime.now(timezone.utc).isoformat()

        for user_id in user_ids:
            try:
                await self._broadcast_for_user(user_id, timestamp)
            except Exception as e:
                logger.debug(f"Realtime broadcast skipped for {user_id[:8]}: {e}")

    async def _broadcast_for_user(self, user_id: str, timestamp: str):
        await manager.send_message(user_id, {
            "type": "heartbeat",
            "timestamp": timestamp,
            "source": "realtime_broadcaster"
        })

        prices = await get_live_prices(user_id)
        overview = await self.overview_service.get_snapshot(user_id)
        bots = await db.bots_collection.find(
            {"user_id": user_id, "status": {"$ne": "deleted"}},
            {"_id": 0, "id": 1, "name": 1, "status": 1, "trading_mode": 1, "exchange": 1}
        ).to_list(200)
        trades = await db.trades_collection.find(
            {"user_id": user_id},
            {"_id": 0}
        ).sort("timestamp", -1).limit(5).to_list(5)

        await manager.send_message(user_id, {
            "type": "prices_update",
            "data": {"prices": prices},
            "payload": {"prices": prices},
            "timestamp": timestamp
        })

        await manager.send_message(user_id, {
            "type": "overview_update",
            "data": {"overview": overview},
            "payload": {"overview": overview},
            "timestamp": timestamp
        })

        await manager.send_message(user_id, {
            "type": "bots_update",
            "data": {
                "bots": bots,
                "counts": {
                    "total": len(bots),
                    "active": len([b for b in bots if b.get("status") == "active"]),
                    "paused": len([b for b in bots if b.get("status") == "paused"])
                }
            },
            "payload": {
                "bots": bots
            },
            "timestamp": timestamp
        })

        await manager.send_message(user_id, {
            "type": "trades_update",
            "data": {
                "trades": trades,
                "summary": {
                    "count": len(trades),
                    "last_trade_at": trades[0].get("timestamp") if trades else None
                }
            },
            "payload": {"trades": trades},
            "timestamp": timestamp
        })


realtime_broadcaster = RealtimeBroadcaster()
