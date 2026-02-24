"""
Realtime Service - Wrapper for consistent real-time event broadcasting
Ensures all state changes broadcast appropriate websocket events
"""

import logging
from typing import Optional, Dict, List

import database as db
from realtime_events import rt_events
from websocket_manager import manager

logger = logging.getLogger(__name__)


class RealtimeService:
    """Centralized service for broadcasting realtime updates"""
    
    async def broadcast_bot_action(
        self, 
        user_id: str, 
        action: str, 
        bot_data: Dict
    ):
        """Broadcast bot lifecycle action
        
        Args:
            user_id: User ID
            action: Action type (created, updated, paused, resumed, stopped, deleted)
            bot_data: Bot data dict
        """
        try:
            bot_name = bot_data.get('name', 'Unknown')
            
            if action == 'created':
                await rt_events.bot_created(user_id, bot_data)
            elif action == 'updated':
                await rt_events.bot_updated(user_id, bot_data.get('id'), bot_data)
            elif action == 'paused':
                await rt_events.bot_paused(user_id, bot_data)
            elif action == 'resumed':
                await rt_events.bot_resumed(user_id, bot_data)
            elif action == 'stopped':
                await manager.send_message(user_id, {
                    "type": "bot_stopped",
                    "bot": bot_data,
                    "message": f"🛑 Bot '{bot_name}' stopped"
                })
            elif action == 'deleted':
                await rt_events.bot_deleted(user_id, bot_name)
            
            # Always broadcast overview update after bot action
            await self.broadcast_overview_update(user_id, f"Bot {action}: {bot_name}")
            await self.broadcast_bots_update(user_id, action, bot_data)
            
        except Exception as e:
            logger.error(f"Error broadcasting bot action '{action}': {e}")
    
    async def broadcast_overview_update(self, user_id: str, reason: Optional[str] = None):
        """Broadcast overview metrics update
        
        Args:
            user_id: User ID
            reason: Optional reason for update
        """
        try:
            message = "Overview updated"
            if reason:
                message = f"Overview updated: {reason}"

            await manager.send_message(user_id, {
                "type": "overview_updated",
                "message": message
            })

            from services.overview_service import OverviewService
            overview_service = OverviewService()
            overview = await overview_service.get_snapshot(user_id)

            await manager.send_message(user_id, {
                "type": "overview_update",
                "data": {"overview": overview, "reason": reason},
                "payload": {"overview": overview, "reason": reason}
            })

        except Exception as e:
            logger.error(f"Error broadcasting overview update: {e}")

    async def broadcast_prices_update(self, user_id: str):
        """Broadcast latest market prices."""
        try:
            from routes.prices import get_live_prices
            prices = await get_live_prices(user_id)
            await manager.send_message(user_id, {
                "type": "prices_update",
                "data": {"prices": prices},
                "payload": {"prices": prices}
            })
        except Exception as e:
            logger.error(f"Error broadcasting prices update: {e}")

    async def broadcast_bots_update(self, user_id: str, action: str, bot_data: Dict):
        """Broadcast bot status changes."""
        try:
            await manager.send_message(user_id, {
                "type": "bots_update",
                "data": {
                    "action": action,
                    "bot": bot_data,
                    "status": bot_data.get("status")
                },
                "payload": {
                    "action": action,
                    "bot": bot_data,
                    "status": bot_data.get("status")
                }
            })
        except Exception as e:
            logger.error(f"Error broadcasting bots update: {e}")

    async def broadcast_trades_update(self, user_id: str, trade_data: Dict):
        """Broadcast latest trade summary."""
        try:
            await manager.send_message(user_id, {
                "type": "trades_update",
                "data": {"trade": trade_data},
                "payload": {"trade": trade_data}
            })
        except Exception as e:
            logger.error(f"Error broadcasting trades update: {e}")

    async def broadcast_countdown_update(self, user_id: str):
        """Broadcast countdown status update.

        Calls ``get_countdown_status`` directly (bypassing FastAPI DI) so the
        ``target`` parameter must be passed as a plain float – otherwise the
        default value is a FastAPI ``Query`` descriptor object, which causes
        ``TypeError: unsupported operand type(s) for -: 'Query' and 'float'``.
        """
        try:
            from routes.ledger_endpoints import get_countdown_status
            countdown = await get_countdown_status(
                target=1_000_000.0,
                current_user=user_id,
                db=db.db,
            )
            await manager.send_message(user_id, {
                "type": "analytics_update",
                "data": {"countdown": countdown},
                "payload": {"countdown": countdown}
            })
        except Exception as e:
            logger.error(f"Error broadcasting countdown update: {e}")
            # Degrade gracefully: send an offline/unknown status so the
            # frontend does not lose its countdown widget entirely.
            try:
                await manager.send_message(user_id, {
                    "type": "analytics_update",
                    "data": {"countdown": {"ready": False, "status": "unknown", "error": str(e)}},
                    "payload": {"countdown": {"ready": False, "status": "unknown"}},
                })
            except Exception:
                pass
    
    async def broadcast_profits_update(self, user_id: str, reason: Optional[str] = None):
        """Broadcast profits/PnL update
        
        Args:
            user_id: User ID
            reason: Optional reason for update
        """
        try:
            message = "Profits updated"
            if reason:
                message = f"Profits updated: {reason}"
            
            await manager.send_message(user_id, {
                "type": "profits_updated",
                "message": message
            })
            
        except Exception as e:
            logger.error(f"Error broadcasting profits update: {e}")
    
    async def broadcast_platform_stats_update(
        self, 
        user_id: str, 
        platform: Optional[str] = None
    ):
        """Broadcast platform statistics update
        
        Args:
            user_id: User ID
            platform: Optional specific platform that changed
        """
        try:
            message = "Platform stats updated"
            if platform:
                message = f"Platform stats updated: {platform}"
            
            await manager.send_message(user_id, {
                "type": "platform_stats_updated",
                "platform": platform,
                "message": message
            })
            
        except Exception as e:
            logger.error(f"Error broadcasting platform stats update: {e}")
    
    async def broadcast_trade_execution(self, user_id: str, trade_data: Dict):
        """Broadcast trade execution
        
        Args:
            user_id: User ID
            trade_data: Trade data dict
        """
        try:
            await rt_events.trade_executed(user_id, trade_data)
            
            # Also update profits and overview
            await self.broadcast_profits_update(user_id, "New trade executed")
            await self.broadcast_overview_update(user_id, "Trade executed")
            await self.broadcast_trades_update(user_id, trade_data)
            await self.broadcast_countdown_update(user_id)
            
        except Exception as e:
            logger.error(f"Error broadcasting trade execution: {e}")
    
    async def broadcast_api_key_update(
        self, 
        user_id: str, 
        provider: str, 
        status: str
    ):
        """Broadcast API key status update
        
        Args:
            user_id: User ID
            provider: Provider name (openai, luno, binance, etc.)
            status: Status (connected, disconnected, test_failed, etc.)
        """
        try:
            await rt_events.api_key_connected(user_id, provider, status)
            
        except Exception as e:
            logger.error(f"Error broadcasting API key update: {e}")
    
    async def broadcast_system_mode_change(
        self, 
        user_id: str, 
        mode: str, 
        enabled: bool
    ):
        """Broadcast system mode change
        
        Args:
            user_id: User ID
            mode: Mode name (paperTrading, liveTrading, etc.)
            enabled: Whether mode is enabled
        """
        try:
            await rt_events.system_mode_changed(user_id, mode, enabled)
            
        except Exception as e:
            logger.error(f"Error broadcasting system mode change: {e}")
    
    async def broadcast_user_storage_update(
        self, 
        user_id: str, 
        storage_key: str
    ):
        """Broadcast user storage/settings update
        
        Args:
            user_id: User ID
            storage_key: Storage key that changed
        """
        try:
            await manager.send_message(user_id, {
                "type": "user_storage_updated",
                "storage_key": storage_key,
                "message": f"Settings updated: {storage_key}"
            })
            
        except Exception as e:
            logger.error(f"Error broadcasting user storage update: {e}")
    
    async def broadcast_alert(
        self, 
        user_id: str, 
        severity: str, 
        message: str,
        alert_data: Optional[Dict] = None
    ):
        """Broadcast system alert
        
        Args:
            user_id: User ID
            severity: Alert severity (info, warning, error, critical)
            message: Alert message
            alert_data: Optional additional alert data
        """
        try:
            await manager.send_message(user_id, {
                "type": "alert",
                "severity": severity,
                "message": message,
                "data": alert_data or {}
            })
            
        except Exception as e:
            logger.error(f"Error broadcasting alert: {e}")
    
    async def broadcast_batch_update(
        self, 
        user_id: str, 
        updates: List[str]
    ):
        """Broadcast multiple update types at once
        
        Args:
            user_id: User ID
            updates: List of update types to broadcast
        """
        try:
            for update_type in updates:
                if update_type == 'overview':
                    await self.broadcast_overview_update(user_id)
                elif update_type == 'profits':
                    await self.broadcast_profits_update(user_id)
                elif update_type == 'platform_stats':
                    await self.broadcast_platform_stats_update(user_id)
                    
        except Exception as e:
            logger.error(f"Error broadcasting batch updates: {e}")
    
    async def broadcast_emergency_stop(self, user_id: str, enabled: bool):
        """Broadcast emergency stop status change
        
        Args:
            user_id: User ID
            enabled: Whether emergency stop is enabled
        """
        try:
            await manager.send_message(user_id, {
                "type": "emergency_stop",
                "enabled": enabled,
                "message": f"🚨 Emergency stop {'activated' if enabled else 'deactivated'}"
            })
            
            # Also broadcast system mode update
            await self.broadcast_system_mode_change(user_id, "emergency_stop", enabled)
            
        except Exception as e:
            logger.error(f"Error broadcasting emergency stop: {e}")


# Global singleton instance
realtime_service = RealtimeService()
