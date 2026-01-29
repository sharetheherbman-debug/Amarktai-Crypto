"""
Real-Time Event Manager - Ensures ALL dashboard updates happen via WebSocket
"""
import asyncio
from websocket_manager import manager
from logger_config import logger
from typing import Dict, List, Callable
from collections import defaultdict


class RealTimeEventBus:
    """Centralized event bus for real-time updates"""
    
    def __init__(self):
        self.listeners: Dict[str, List[Callable]] = defaultdict(list)
    
    def subscribe(self, event_type: str, callback: Callable):
        """Subscribe to an event type"""
        self.listeners[event_type].append(callback)
        logger.debug(f"Subscribed to event: {event_type}")
    
    def unsubscribe(self, event_type: str, callback: Callable):
        """Unsubscribe from an event type"""
        if callback in self.listeners[event_type]:
            self.listeners[event_type].remove(callback)
            logger.debug(f"Unsubscribed from event: {event_type}")
    
    async def emit(self, event_type: str, data: dict):
        """Emit an event to all subscribers"""
        if event_type in self.listeners:
            for callback in self.listeners[event_type]:
                try:
                    if asyncio.iscoroutinefunction(callback):
                        await callback(data)
                    else:
                        callback(data)
                except Exception as e:
                    logger.error(f"Event callback error ({event_type}): {e}")


# Global event bus
event_bus = RealTimeEventBus()


class RealTimeEvents:
    """Centralized real-time event broadcasting"""
    
    @staticmethod
    async def bot_created(user_id: str, bot_data: dict):
        """Broadcast when bot is created"""
        await manager.send_message(user_id, {
            "type": "bot_created",
            "bot": bot_data,
            "message": f"✅ Bot '{bot_data.get('name')}' created"
        })
        logger.info(f"📡 Real-time: bot_created for user {user_id[:8]}")
    
    @staticmethod
    async def bot_updated(user_id: str, bot_id: str, changes: dict):
        """Broadcast when bot is updated"""
        await manager.send_message(user_id, {
            "type": "bot_updated",
            "bot_id": bot_id,
            "changes": changes,
            "message": "Bot updated"
        })
    
    @staticmethod
    async def bot_deleted(user_id: str, bot_name: str):
        """Broadcast when bot is deleted"""
        await manager.send_message(user_id, {
            "type": "bot_deleted",
            "message": f"🗑️ Bot '{bot_name}' deleted"
        })
    
    @staticmethod
    async def bot_paused(user_id: str, bot_data: dict):
        """Broadcast when bot is paused"""
        await manager.send_message(user_id, {
            "type": "bot_paused",
            "bot": bot_data,
            "message": f"⏸️ Bot '{bot_data.get('name')}' paused"
        })
        logger.info(f"📡 Real-time: bot_paused for user {user_id[:8]}")
    
    @staticmethod
    async def bot_resumed(user_id: str, bot_data: dict):
        """Broadcast when bot is resumed"""
        await manager.send_message(user_id, {
            "type": "bot_resumed",
            "bot": bot_data,
            "message": f"▶️ Bot '{bot_data.get('name')}' resumed"
        })
        logger.info(f"📡 Real-time: bot_resumed for user {user_id[:8]}")
    
    @staticmethod
    async def trade_executed(user_id: str, trade_data: dict):
        """Broadcast when trade executes"""
        await manager.send_message(user_id, {
            "type": "trade_executed",
            "trade": trade_data,
            "message": f"📊 Trade executed: {trade_data.get('pair')}"
        })
    
    @staticmethod
    async def profit_updated(user_id: str, new_profit: float, bot_name: str = None):
        """Broadcast when profit changes"""
        msg = f"💰 Profit updated: R{new_profit:.2f}"
        if bot_name:
            msg = f"💰 {bot_name} profit: R{new_profit:.2f}"
        
        await manager.send_message(user_id, {
            "type": "profit_updated",
            "total_profit": new_profit,
            "bot_name": bot_name,
            "message": msg
        })
    
    @staticmethod
    async def system_mode_changed(user_id: str, mode: str, enabled: bool):
        """Broadcast system mode changes"""
        await manager.send_message(user_id, {
            "type": "system_mode_update",
            "mode": mode,
            "enabled": enabled,
            "message": f"⚙️ {mode} {'enabled' if enabled else 'disabled'}"
        })
    
    @staticmethod
    async def api_key_connected(user_id: str, provider: str, status: str):
        """Broadcast API key connection status"""
        emoji = "✅" if status == "connected" else "❌"
        await manager.send_message(user_id, {
            "type": "api_key_update",
            "provider": provider,
            "status": status,
            "message": f"{emoji} {provider.upper()} {status}"
        })
    
    @staticmethod
    async def autopilot_action(user_id: str, action_type: str, details: dict):
        """Broadcast autopilot actions"""
        await manager.send_message(user_id, {
            "type": "autopilot_action",
            "action_type": action_type,
            "details": details,
            "message": details.get('message', 'Autopilot action executed')
        })
    
    @staticmethod
    async def self_healing_action(user_id: str, bot_name: str, reason: str):
        """Broadcast self-healing actions"""
        await manager.send_message(user_id, {
            "type": "self_healing",
            "bot_name": bot_name,
            "reason": reason,
            "message": f"🛡️ Self-Healing: Paused '{bot_name}' - {reason}"
        })
    
    @staticmethod
    async def bot_promoted(user_id: str, bot_name: str):
        """Broadcast bot promotion to live"""
        await manager.send_message(user_id, {
            "type": "bot_promoted",
            "bot_name": bot_name,
            "message": f"🎉 '{bot_name}' promoted to LIVE trading!"
        })
    
    @staticmethod
    async def force_refresh(user_id: str, reason: str = None):
        """Force complete dashboard refresh"""
        await manager.send_message(user_id, {
            "type": "force_refresh",
            "message": reason or "Dashboard updated"
        })
    
    @staticmethod
    async def countdown_updated(user_id: str, days: int, current_capital: float):
        """Broadcast countdown updates"""
        await manager.send_message(user_id, {
            "type": "countdown_update",
            "days": days,
            "current_capital": current_capital,
            "message": f"📈 {days} days to R1M"
        })
    
    @staticmethod
    async def ai_evolution(user_id: str, action: str, details: dict):
        """Broadcast AI learning/evolution actions"""
        await manager.send_message(user_id, {
            "type": "ai_evolution",
            "action": action,
            "details": details,
            "message": f"🧠 AI Evolution: {action}"
        })
    
    @staticmethod
    async def balance_updated(user_id: str, balance_data: dict):
        """Broadcast wallet balance updates"""
        await manager.send_message(user_id, {
            "type": "balance_updated",
            "balance": balance_data,
            "master_wallet": balance_data.get('master_wallet', {}),
            "exchange_balances": balance_data.get('exchange_balances', {}),
            "message": "💰 Balance updated"
        })
        logger.info(f"📡 Real-time: balance_updated for user {user_id[:8]}")
    
    @staticmethod
    async def wallet_update(user_id: str, wallet_data: dict):
        """Broadcast general wallet updates"""
        await manager.send_message(user_id, {
            "type": "wallet",
            "event": "balance_update",
            "data": wallet_data,
            "message": "💰 Wallet updated"
        })
    
    @staticmethod
    async def training_completed(user_id: str, bot_data: dict):
        """Broadcast when bot completes training"""
        await manager.send_message(user_id, {
            "type": "training_completed",
            "bot": bot_data,
            "message": f"🎓 Bot '{bot_data.get('name')}' training complete - ready for activation"
        })
        logger.info(f"📡 Real-time: training_completed for user {user_id[:8]}")
    
    @staticmethod
    async def training_failed(user_id: str, bot_data: dict):
        """Broadcast when bot training fails"""
        await manager.send_message(user_id, {
            "type": "training_failed",
            "bot": bot_data,
            "message": f"❌ Bot '{bot_data.get('name')}' training failed: {bot_data.get('training_failed_reason')}"
        })
        logger.info(f"📡 Real-time: training_failed for user {user_id[:8]}")
    
    @staticmethod
    async def key_saved(user_id: str, provider: str, display_name: str):
        """Broadcast when API key is saved"""
        await manager.send_message(user_id, {
            "type": "key_saved",
            "provider": provider,
            "display_name": display_name,
            "message": f"🔑 {display_name} API key saved"
        })
        logger.info(f"📡 Real-time: key_saved ({provider}) for user {user_id[:8]}")
    
    @staticmethod
    async def key_tested(user_id: str, provider: str, display_name: str, success: bool, error: str = None):
        """Broadcast when API key is tested"""
        emoji = "✅" if success else "❌"
        message = f"{emoji} {display_name} key test {'passed' if success else 'failed'}"
        if not success and error:
            message += f": {error}"
        
        await manager.send_message(user_id, {
            "type": "key_tested",
            "provider": provider,
            "display_name": display_name,
            "success": success,
            "error": error,
            "message": message
        })
        logger.info(f"📡 Real-time: key_tested ({provider}, {success}) for user {user_id[:8]}")
    
    @staticmethod
    async def key_deleted(user_id: str, provider: str, display_name: str):
        """Broadcast when API key is deleted"""
        await manager.send_message(user_id, {
            "type": "key_deleted",
            "provider": provider,
            "display_name": display_name,
            "message": f"🗑️ {display_name} API key deleted"
        })
        logger.info(f"📡 Real-time: key_deleted ({provider}) for user {user_id[:8]}")
    
    @staticmethod
    async def mode_switched(user_id: str, mode: str, mode_data: dict):
        """Broadcast when system mode is switched"""
        emoji = "📝" if mode == "paper" else "🚀" if mode == "live" else "🤖"
        await manager.send_message(user_id, {
            "type": "mode_switched",
            "mode": mode,
            "mode_data": mode_data,
            "message": f"{emoji} System switched to {mode.upper()} mode"
        })
        logger.info(f"📡 Real-time: mode_switched to {mode} for user {user_id[:8]}")
    
    @staticmethod
    async def bot_status_changed(user_id: str, bot_id: str, status: str, reason: str = None):
        """Broadcast when bot status changes (started/paused/stopped/error)"""
        emoji_map = {
            "active": "▶️",
            "paused": "⏸️",
            "stopped": "⏹️",
            "error": "❌",
            "training": "🎓",
            "quarantined": "🔒"
        }
        emoji = emoji_map.get(status, "🔄")
        message = f"{emoji} Bot status changed to {status.upper()}"
        if reason:
            message += f" - {reason}"
        
        await manager.send_message(user_id, {
            "type": "bot_status_changed",
            "bot_id": bot_id,
            "status": status,
            "reason": reason,
            "message": message
        })
        logger.info(f"📡 Real-time: bot_status_changed ({bot_id[:8]}, {status}) for user {user_id[:8]}")
    
    @staticmethod
    async def bot_quarantined(user_id: str, bot_id: str, reason: str):
        """Broadcast when bot is quarantined for retraining"""
        await manager.send_message(user_id, {
            "type": "bot_quarantined",
            "bot_id": bot_id,
            "reason": reason,
            "message": f"🔒 Bot quarantined for retraining: {reason}"
        })
        logger.info(f"📡 Real-time: bot_quarantined ({bot_id[:8]}) for user {user_id[:8]}")
    
    @staticmethod
    async def training_started(user_id: str, bot_id: str, training_job: dict):
        """Broadcast when training job is created"""
        await manager.send_message(user_id, {
            "type": "training_started",
            "bot_id": bot_id,
            "training_job": training_job,
            "message": f"🎓 Training started for bot"
        })
        logger.info(f"📡 Real-time: training_started ({bot_id[:8]}) for user {user_id[:8]}")
    
    @staticmethod
    async def metrics_updated(user_id: str, metrics: dict):
        """Broadcast metrics updates (P&L, win rate, positions)"""
        await manager.send_message(user_id, {
            "type": "metrics_updated",
            "metrics": metrics,
            "message": "📊 Metrics updated"
        })
        logger.debug(f"📡 Real-time: metrics_updated for user {user_id[:8]}")
    
    @staticmethod
    async def overview_updated(user_id: str, overview: dict):
        """Broadcast overview summary (portfolio value, active bots, etc.)"""
        await manager.send_message(user_id, {
            "type": "overview_updated",
            "overview": overview,
            "message": "📈 Overview updated"
        })
        logger.debug(f"📡 Real-time: overview_updated for user {user_id[:8]}")

# Global instance
rt_events = RealTimeEvents()
