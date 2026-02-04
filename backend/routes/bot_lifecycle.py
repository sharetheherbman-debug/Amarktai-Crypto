"""
Bot Lifecycle Management Router
Handles pause, resume, cooldown periods, and bot lifecycle operations
"""

from fastapi import APIRouter, HTTPException, Depends
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict
import logging
import os

from auth import get_current_user
import database as db
from websocket_manager import manager
from realtime_events import rt_events
from services.bot_quarantine import quarantine_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/bots", tags=["Bot Lifecycle"])


@router.get("/status")
async def get_bots_status(user_id: str = Depends(get_current_user)):
    """Get bot status list with states for bot management
    
    Returns all bots with detailed status including training states
    
    Args:
        user_id: Current user ID (from auth)
        
    Returns:
        List of bots with id, exchange, state, paused_reason, etc.
    """
    try:
        bots = await db.bots_collection.find({"user_id": user_id, "status": {"$ne": "deleted"}}, {"_id": 0}).to_list(1000)
        
        # Enrich each bot with detailed state
        enriched_bots = []
        for bot in bots:
            status = bot.get('status', 'unknown')
            
            # Map status to standard states
            if status == 'active':
                state = 'active'
            elif status == 'paused':
                # Check if ready to activate (paused_ready)
                if bot.get('training_complete') and bot.get('paused_by_user'):
                    state = 'paused_ready'
                else:
                    state = 'paused'
            elif status == 'stopped':
                state = 'stopped'
            elif status == 'training' or bot.get('training_in_progress'):
                state = 'training'
            elif status == 'training_failed' or bot.get('training_failed'):
                state = 'training_failed'
            else:
                state = status
            
            enriched_bot = {
                "id": bot.get('id'),
                "name": bot.get('name'),
                "exchange": bot.get('exchange', 'unknown'),
                "state": state,
                "status": status,  # Keep original for compatibility
                "paused_reason": bot.get('paused_reason') or bot.get('pause_reason'),  # Canonical field (support legacy)
                "paused_by_user": bot.get('paused_by_user', False),
                "paused_by_system": bot.get('paused_by_system', False),
                "quarantine_reason": bot.get('quarantine_reason'),
                "quarantine_until": bot.get('quarantine_until'),
                "training_state": bot.get('training_state'),
                "trading_mode": bot.get('trading_mode', 'paper'),
                "risk_mode": bot.get('risk_mode', 'balanced'),
                "current_capital": bot.get('current_capital', 0),
                "total_profit": bot.get('total_profit', 0),
                "trades_count": bot.get('trades_count', 0),
                "training_complete": bot.get('training_complete', False),
                "training_failed_reason": bot.get('training_failed_reason'),
                "created_at": bot.get('created_at'),
                "started_at": bot.get('started_at'),
                "paused_at": bot.get('paused_at'),
                "stopped_at": bot.get('stopped_at')
            }
            enriched_bots.append(enriched_bot)
        
        # Count by exchange to ensure all 7 are represented
        exchange_counts = {}
        all_exchanges = ['luno', 'binance', 'kucoin', 'bybit', 'kraken', 'bitget', 'gate']
        for exchange in all_exchanges:
            exchange_counts[exchange] = len([b for b in enriched_bots if b.get('exchange') == exchange])
        
        return {
            "success": True,
            "bots": enriched_bots,
            "total": len(enriched_bots),
            "exchange_counts": exchange_counts,
            "all_exchanges": all_exchanges
        }
        
    except Exception as e:
        logger.error(f"Get bots status error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{bot_id}/start")
async def start_bot(bot_id: str, user_id: str = Depends(get_current_user)):
    """Start a bot's trading activity
    
    Args:
        bot_id: Bot ID to start
        user_id: Current user ID (from auth)
        
    Returns:
        Updated bot status
    """
    try:
        # Verify bot belongs to user
        bot = await db.bots_collection.find_one({"id": bot_id, "user_id": user_id}, {"_id": 0})
        if not bot:
            raise HTTPException(status_code=404, detail="Bot not found")
        
        # Check if already active
        if bot.get('status') == 'active':
            return {
                "success": False,
                "message": f"Bot '{bot['name']}' is already active",
                "bot": bot
            }
        
        # PREFLIGHT VALIDATION: Check requirements before starting bot
        trading_mode = bot.get('trading_mode', 'paper')
        
        # 1. Check wallet balance is available
        current_capital = bot.get('current_capital', 0)
        initial_capital = bot.get('initial_capital', 0)
        if current_capital <= 0 and initial_capital <= 0:
            raise HTTPException(
                status_code=400, 
                detail=f"Cannot start bot '{bot['name']}': No wallet balance available. Please allocate capital to this bot."
            )
        
        # 2. Check trading mode is enabled (Paper or Live)
        # Validate that the bot's trading mode (paper/live) is enabled in environment config
        # This prevents starting bots in modes that are disabled system-wide
        paper_trading_enabled = os.getenv('PAPER_TRADING', '0') == '1'
        live_trading_enabled = os.getenv('LIVE_TRADING', '0') == '1'
        
        if trading_mode == 'paper' and not paper_trading_enabled:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot start bot '{bot['name']}': Paper trading is disabled. Set PAPER_TRADING=1 in environment."
            )
        elif trading_mode == 'live' and not live_trading_enabled:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot start bot '{bot['name']}': Live trading is disabled. Set LIVE_TRADING=1 in environment."
            )
        elif not paper_trading_enabled and not live_trading_enabled:
            raise HTTPException(
                status_code=400,
                detail="Cannot start bot: Both paper and live trading are disabled. Enable at least one trading mode."
            )
        
        # 3. Check ledger collection is accessible
        try:
            # Verify ledger collection exists and is accessible
            await db.ledger_collection.find_one({}, {"_id": 1})
        except Exception as e:
            logger.error(f"Ledger collection check failed: {e}")
            raise HTTPException(
                status_code=500,
                detail=f"Cannot start bot '{bot['name']}': Ledger collection is not accessible. Please contact admin."
            )
        
        # Start the bot
        started_at = datetime.now(timezone.utc).isoformat()
        
        await db.bots_collection.update_one(
            {"id": bot_id},
            {
                "$set": {
                    "status": "active",
                    "started_at": started_at
                },
                "$unset": {
                    "stopped_at": "",
                    "paused_at": "",
                    "pause_reason": "",
                    "paused_by_user": "",
                    "paused_by_system": "",
                    "stop_reason": ""
                }
            }
        )
        
        # Get updated bot
        updated_bot = await db.bots_collection.find_one({"id": bot_id}, {"_id": 0})
        
        # Send real-time notifications
        await rt_events.bot_resumed(user_id, updated_bot)
        
        # Also broadcast overview and platform stats updates
        from services.realtime_service import realtime_service
        await realtime_service.broadcast_overview_update(user_id, f"Bot started: {bot['name']}")
        await realtime_service.broadcast_platform_stats_update(user_id, bot.get('exchange'))
        
        logger.info(f"✅ Bot {bot['name']} started by user {user_id[:8]}")
        
        return {
            "success": True,
            "message": f"Bot '{bot['name']}' started successfully",
            "bot": updated_bot
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Start bot error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{bot_id}/stop")
async def stop_bot(bot_id: str, data: Optional[Dict] = None, user_id: str = Depends(get_current_user)):
    """Stop a bot's trading activity permanently
    
    Args:
        bot_id: Bot ID to stop
        data: Optional data with reason for stop
        user_id: Current user ID (from auth)
        
    Returns:
        Updated bot status
    """
    try:
        # Verify bot belongs to user
        bot = await db.bots_collection.find_one({"id": bot_id, "user_id": user_id}, {"_id": 0})
        if not bot:
            raise HTTPException(status_code=404, detail="Bot not found")
        
        # Check if already stopped
        if bot.get('status') == 'stopped':
            return {
                "success": False,
                "message": f"Bot '{bot['name']}' is already stopped",
                "bot": bot
            }
        
        # Stop the bot
        if data is None:
            data = {}
        reason = data.get('reason', 'Manual stop by user')
        stopped_at = datetime.now(timezone.utc).isoformat()
        
        await db.bots_collection.update_one(
            {"id": bot_id},
            {
                "$set": {
                    "status": "stopped",
                    "stopped_at": stopped_at,
                    "stop_reason": reason
                }
            }
        )
        
        # Get updated bot
        updated_bot = await db.bots_collection.find_one({"id": bot_id}, {"_id": 0})
        
        # Send real-time notifications
        await manager.send_message(user_id, {
            "type": "bot_stopped",
            "bot": updated_bot,
            "message": f"⏹️ Bot '{bot['name']}' stopped"
        })
        
        # Also broadcast overview and platform stats updates
        from services.realtime_service import realtime_service
        await realtime_service.broadcast_overview_update(user_id, f"Bot stopped: {bot['name']}")
        await realtime_service.broadcast_platform_stats_update(user_id, bot.get('exchange'))
        
        logger.info(f"✅ Bot {bot['name']} stopped by user {user_id[:8]}")
        
        return {
            "success": True,
            "message": f"Bot '{bot['name']}' stopped successfully",
            "bot": updated_bot
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Stop bot error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{bot_id}/pause")
@router.put("/{bot_id}/pause")
async def pause_bot(bot_id: str, data: Optional[Dict] = None, user_id: str = Depends(get_current_user)):
    """Pause a bot's trading activity
    
    Accepts both POST and PUT methods for compatibility with frontend
    
    Args:
        bot_id: Bot ID to pause
        data: Optional data with reason for pause
        user_id: Current user ID (from auth)
        
    Returns:
        Updated bot status
    """
    try:
        # Verify bot belongs to user
        bot = await db.bots_collection.find_one({"id": bot_id, "user_id": user_id}, {"_id": 0})
        if not bot:
            raise HTTPException(status_code=404, detail="Bot not found")
        
        # Check if already paused
        if bot.get('status') == 'paused':
            return {
                "success": False,
                "message": f"Bot '{bot['name']}' is already paused",
                "bot": bot
            }
        
        # Pause the bot
        if data is None:
            data = {}
        reason = data.get('reason', 'Manual pause by user')
        paused_at = datetime.now(timezone.utc).isoformat()
        
        await db.bots_collection.update_one(
            {"id": bot_id},
            {
                "$set": {
                    "status": "paused",
                    "paused_at": paused_at,
                    "pause_reason": reason,
                    "paused_by_user": True
                }
            }
        )
        
        # Place bot in quarantine for auto-retraining (only if not manually paused)
        # Manual pauses get lower priority quarantine
        try:
            if not data or not data.get('manual'):
                await quarantine_service.quarantine_bot(bot_id, reason)
        except Exception as e:
            logger.warning(f"Failed to quarantine bot: {e}")
        
        # Get updated bot
        updated_bot = await db.bots_collection.find_one({"id": bot_id}, {"_id": 0})
        
        # Send real-time notifications
        await rt_events.bot_paused(user_id, updated_bot)
        
        # Also broadcast overview and platform stats updates
        from services.realtime_service import realtime_service
        await realtime_service.broadcast_overview_update(user_id, f"Bot paused: {bot['name']}")
        await realtime_service.broadcast_platform_stats_update(user_id, bot.get('exchange'))
        
        logger.info(f"✅ Bot {bot['name']} paused by user {user_id[:8]}")
        
        return {
            "success": True,
            "message": f"Bot '{bot['name']}' paused successfully",
            "bot": updated_bot
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Pause bot error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{bot_id}/resume")
@router.put("/{bot_id}/resume")
@router.post("/{bot_id}/unpause")
@router.put("/{bot_id}/unpause")
async def resume_bot(bot_id: str, user_id: str = Depends(get_current_user)):
    """Resume a paused bot's trading activity (also /unpause alias)
    
    Accepts both POST and PUT methods for compatibility with frontend
    
    Args:
        bot_id: Bot ID to resume
        user_id: Current user ID (from auth)
        
    Returns:
        Updated bot status
    """
    try:
        # Verify bot belongs to user
        bot = await db.bots_collection.find_one({"id": bot_id, "user_id": user_id}, {"_id": 0})
        if not bot:
            raise HTTPException(status_code=404, detail="Bot not found")
        
        # Check if currently paused
        if bot.get('status') != 'paused':
            return {
                "success": False,
                "message": f"Bot '{bot['name']}' is not paused (status: {bot.get('status', 'unknown')})",
                "bot": bot
            }
        
        # Resume the bot
        resumed_at = datetime.now(timezone.utc).isoformat()
        
        await db.bots_collection.update_one(
            {"id": bot_id},
            {
                "$set": {
                    "status": "active",
                    "resumed_at": resumed_at
                },
                "$unset": {
                    "paused_at": "",
                    "pause_reason": "",
                    "paused_by_user": "",
                    "paused_by_system": ""
                }
            }
        )
        
        # Get updated bot
        updated_bot = await db.bots_collection.find_one({"id": bot_id}, {"_id": 0})
        
        # Send real-time notification
        await rt_events.bot_resumed(user_id, updated_bot)
        
        logger.info(f"✅ Bot {bot['name']} resumed by user {user_id[:8]}")
        
        return {
            "success": True,
            "message": f"Bot '{bot['name']}' resumed successfully",
            "bot": updated_bot
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Resume bot error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{bot_id}/cooldown")
async def set_bot_cooldown(
    bot_id: str, 
    data: dict,
    user_id: str = Depends(get_current_user)
):
    """Set custom cooldown period for a bot
    
    Args:
        bot_id: Bot ID
        data: {"cooldown_minutes": int} - Cooldown period in minutes
        user_id: Current user ID (from auth)
        
    Returns:
        Updated bot with cooldown settings
    """
    try:
        # Verify bot belongs to user
        bot = await db.bots_collection.find_one({"id": bot_id, "user_id": user_id}, {"_id": 0})
        if not bot:
            raise HTTPException(status_code=404, detail="Bot not found")
        
        # Validate cooldown period
        cooldown_minutes = data.get('cooldown_minutes')
        if not cooldown_minutes or not isinstance(cooldown_minutes, (int, float)):
            raise HTTPException(status_code=400, detail="Invalid cooldown_minutes value")
        
        # Validate range (5 minutes to 120 minutes)
        if cooldown_minutes < 5 or cooldown_minutes > 120:
            raise HTTPException(
                status_code=400, 
                detail="Cooldown period must be between 5 and 120 minutes"
            )
        
        # Update bot cooldown
        await db.bots_collection.update_one(
            {"id": bot_id},
            {
                "$set": {
                    "custom_cooldown_minutes": cooldown_minutes,
                    "cooldown_updated_at": datetime.now(timezone.utc).isoformat()
                }
            }
        )
        
        # Get updated bot
        updated_bot = await db.bots_collection.find_one({"id": bot_id}, {"_id": 0})
        
        logger.info(f"✅ Bot {bot['name']} cooldown set to {cooldown_minutes} minutes")
        
        return {
            "success": True,
            "message": f"Cooldown set to {cooldown_minutes} minutes for '{bot['name']}'",
            "bot": updated_bot,
            "cooldown_minutes": cooldown_minutes
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Set cooldown error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{bot_id}/status")
async def get_bot_detailed_status(bot_id: str, user_id: str = Depends(get_current_user)):
    """Get detailed status information for a bot
    
    Args:
        bot_id: Bot ID
        user_id: Current user ID (from auth)
        
    Returns:
        Comprehensive bot status including cooldown info, recent trades, etc.
    """
    try:
        # Verify bot belongs to user
        bot = await db.bots_collection.find_one({"id": bot_id, "user_id": user_id}, {"_id": 0})
        if not bot:
            raise HTTPException(status_code=404, detail="Bot not found")
        
        # Calculate cooldown status
        last_trade_time = bot.get('last_trade_time')
        custom_cooldown = bot.get('custom_cooldown_minutes', 15)  # Default 15 minutes
        cooldown_remaining = 0
        can_trade_at = None
        
        if last_trade_time:
            if isinstance(last_trade_time, str):
                last_trade_dt = datetime.fromisoformat(last_trade_time.replace('Z', '+00:00'))
            else:
                last_trade_dt = last_trade_time
            
            next_trade_allowed = last_trade_dt + timedelta(minutes=custom_cooldown)
            now = datetime.now(timezone.utc)
            
            if now < next_trade_allowed:
                cooldown_remaining = int((next_trade_allowed - now).total_seconds() / 60)
                can_trade_at = next_trade_allowed.isoformat()
        
        # Get recent trades (last 10)
        recent_trades = await db.trades_collection.find(
            {"bot_id": bot_id},
            {"_id": 0}
        ).sort("timestamp", -1).limit(10).to_list(10)
        
        # Calculate daily stats
        today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        trades_today = await db.trades_collection.count_documents({
            "bot_id": bot_id,
            "timestamp": {"$gte": today_start.isoformat()}
        })
        
        # Calculate profit today
        today_trades = await db.trades_collection.find(
            {
                "bot_id": bot_id,
                "timestamp": {"$gte": today_start.isoformat()}
            },
            {"_id": 0}
        ).to_list(1000)
        
        profit_today = sum(t.get('profit_loss', 0) for t in today_trades)
        
        return {
            "bot": bot,
            "status": {
                "current_status": bot.get('status', 'unknown'),
                "is_active": bot.get('status') == 'active',
                "is_paused": bot.get('status') == 'paused',
                "pause_reason": bot.get('pause_reason'),
                "paused_at": bot.get('paused_at'),
                "paused_by_system": bot.get('paused_by_system', False)
            },
            "cooldown": {
                "custom_cooldown_minutes": custom_cooldown,
                "remaining_minutes": cooldown_remaining,
                "can_trade_now": cooldown_remaining == 0 and bot.get('status') == 'active',
                "next_trade_at": can_trade_at
            },
            "performance": {
                "total_trades": bot.get('trades_count', 0),
                "trades_today": trades_today,
                "total_profit": bot.get('total_profit', 0),
                "profit_today": round(profit_today, 2),
                "current_capital": bot.get('current_capital', 0),
                "win_rate": bot.get('win_rate', 0)
            },
            "recent_trades": recent_trades[:5]  # Last 5 trades
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get bot status error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/pause-all")
async def pause_all_bots(data: Optional[Dict] = None, user_id: str = Depends(get_current_user)):
    """Pause all active bots for a user
    
    Args:
        data: Optional data with reason for pause
        user_id: Current user ID (from auth)
        
    Returns:
        Summary of paused bots
    """
    try:
        if data is None:
            data = {}
        reason = data.get('reason', 'Bulk pause by user')
        paused_at = datetime.now(timezone.utc).isoformat()
        
        # Pause all active bots
        result = await db.bots_collection.update_many(
            {"user_id": user_id, "status": "active"},
            {
                "$set": {
                    "status": "paused",
                    "paused_at": paused_at,
                    "pause_reason": reason,
                    "paused_by_user": True
                }
            }
        )
        
        # Send real-time notification
        await rt_events.force_refresh(user_id, f"Paused {result.modified_count} bots")
        
        logger.info(f"✅ Paused {result.modified_count} bots for user {user_id[:8]}")
        
        return {
            "success": True,
            "message": f"Paused {result.modified_count} bot(s)",
            "paused_count": result.modified_count
        }
        
    except Exception as e:
        logger.error(f"Pause all bots error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{bot_id}/trading-enabled")
@router.post("/{bot_id}/trading-enabled")
async def toggle_bot_trading(bot_id: str, data: Dict, user_id: str = Depends(get_current_user)):
    """Enable or disable trading for a specific bot
    
    This allows users to toggle trading on/off without pausing the bot.
    The bot remains active but won't execute trades when trading_enabled=False.
    
    Args:
        bot_id: Bot ID to toggle
        data: {"enabled": true/false}
        user_id: Current user ID (from auth)
        
    Returns:
        Updated bot status
    """
    try:
        # Verify bot belongs to user
        bot = await db.bots_collection.find_one({"id": bot_id, "user_id": user_id}, {"_id": 0})
        if not bot:
            raise HTTPException(status_code=404, detail="Bot not found")
        
        enabled = data.get('enabled', True)
        
        # Update trading_enabled flag
        await db.bots_collection.update_one(
            {"id": bot_id},
            {
                "$set": {
                    "trading_enabled": enabled,
                    "trading_enabled_updated_at": datetime.now(timezone.utc).isoformat(),
                    "trading_enabled_by_user": True
                }
            }
        )
        
        # Get updated bot
        updated_bot = await db.bots_collection.find_one({"id": bot_id}, {"_id": 0})
        
        # Log audit trail
        from engines.audit_logger import audit_logger
        await audit_logger.log_action(
            user_id=user_id,
            action="bot_trading_toggled",
            details={
                "bot_id": bot_id,
                "bot_name": bot.get('name'),
                "enabled": enabled
            }
        )
        
        # Send real-time notification
        await rt_events.force_refresh(user_id, f"Bot {bot.get('name')} trading {'enabled' if enabled else 'disabled'}")
        
        status_text = "enabled" if enabled else "disabled"
        logger.info(f"✅ Bot {bot['name']} trading {status_text} by user {user_id[:8]}")
        
        return {
            "success": True,
            "message": f"Bot '{bot['name']}' trading {status_text}",
            "bot": updated_bot
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Toggle bot trading error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{bot_id}")
async def delete_bot(
    bot_id: str,
    user_id: str = Depends(get_current_user)
):
    """Delete a bot permanently
    
    Soft-deletes the bot by setting status to 'deleted' rather than removing from DB.
    This preserves historical data for analytics while removing bot from active use.
    Broadcasts realtime events for immediate UI update.
    
    Args:
        bot_id: Bot ID to delete
        user_id: Current user ID (from auth)
        
    Returns:
        Success response with deletion confirmation
    """
    try:
        # Get bot and verify ownership
        bot = await db.bots_collection.find_one(
            {"id": bot_id, "user_id": user_id},
            {"_id": 0}
        )
        
        if not bot:
            raise HTTPException(
                status_code=404,
                detail=f"Bot {bot_id} not found or access denied"
            )
        
        bot_name = bot.get('name', 'Unknown')
        
        # Soft delete: mark as deleted but keep in DB for history
        await db.bots_collection.update_one(
            {"id": bot_id},
            {
                "$set": {
                    "status": "deleted",
                    "deleted_at": datetime.now(timezone.utc).isoformat(),
                    "deleted_by": user_id
                }
            }
        )
        
        # Broadcast realtime events
        from services.realtime_service import realtime_service
        
        # Bot deleted event
        await rt_events.bot_deleted(user_id, bot_name)
        
        # Update overview, profits, and platform stats
        await realtime_service.broadcast_overview_update(user_id, f"Bot deleted: {bot_name}")
        await realtime_service.broadcast_profits_update(user_id, f"Bot deleted: {bot_name}")
        
        # Update platform stats for the bot's exchange
        exchange = bot.get('exchange')
        if exchange:
            await realtime_service.broadcast_platform_stats_update(user_id, exchange)
        
        logger.info(f"Bot {bot_id} ({bot_name}) deleted by user {user_id[:8]}")
        
        return {
            "success": True,
            "message": f"Bot '{bot_name}' deleted successfully",
            "bot_id": bot_id,
            "bot_name": bot_name
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Delete bot error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{bot_id}/diagnostics")
async def get_bot_diagnostics(bot_id: str, user_id: str = Depends(get_current_user)):
    """Get detailed diagnostics for why a bot is or isn't trading
    
    Returns comprehensive diagnostic information including:
    - Trading gates status (paper/live/autopilot/emergency)
    - Rate limiting and daily budget status
    - Bodyguard metrics and pause reasons
    - API key status and permissions
    - Last trade time and next eligible action
    - Win rate and profitability metrics
    
    Args:
        bot_id: Bot ID to diagnose
        user_id: Current user ID (from auth)
        
    Returns:
        Detailed diagnostic information explaining bot trading status
    """
    try:
        # Get bot
        bot = await db.bots_collection.find_one({"id": bot_id, "user_id": user_id}, {"_id": 0})
        if not bot:
            raise HTTPException(status_code=404, detail="Bot not found")
        
        # Check if deleted
        if bot.get('status') == 'deleted':
            raise HTTPException(status_code=404, detail="Bot has been deleted")
        
        # Get user for system gates
        user = await db.users_collection.find_one({"id": user_id}, {"_id": 0})
        
        diagnostics = {
            "bot_id": bot_id,
            "bot_name": bot.get('name'),
            "exchange": bot.get('exchange'),
            "status": bot.get('status'),
            "can_trade": False,
            "reasons": [],
            "gates": {},
            "limits": {},
            "bodyguard": {},
            "api_keys": {},
            "recent_activity": {}
        }
        
        # Check trading gates
        trading_mode = bot.get('trading_mode', 'paper')
        system_mode = user.get('system_mode') if user else 'testing'
        emergency_stop = user.get('emergency_stop', False) if user else False
        
        diagnostics['gates'] = {
            "trading_mode": trading_mode,
            "system_mode": system_mode,
            "emergency_stop": emergency_stop,
            "autopilot_enabled": user.get('autopilot_enabled', True) if user else True
        }
        
        # Status checks
        if bot.get('status') != 'active':
            diagnostics['reasons'].append(f"Bot status is '{bot.get('status')}', not 'active'")
        
        if emergency_stop:
            diagnostics['reasons'].append("Emergency stop is enabled")
        
        if bot.get('paused_by_bodyguard'):
            diagnostics['reasons'].append(f"Paused by bodyguard: {bot.get('pause_reason', 'Unknown reason')}")
        
        if bot.get('paused_by_system'):
            diagnostics['reasons'].append(f"Paused by system: {bot.get('pause_reason', 'Unknown reason')}")
        
        # Check trade limits
        exchange = bot.get('exchange', 'binance')
        from engines.trade_budget_manager import trade_budget_manager
        
        daily_budget = await trade_budget_manager.calculate_bot_daily_budget(bot_id, exchange)
        remaining = await trade_budget_manager.get_bot_remaining_budget(bot_id, exchange)
        can_trade_budget, budget_reason = await trade_budget_manager.can_execute_trade(bot_id, exchange)
        
        diagnostics['limits'] = {
            "daily_budget": daily_budget,
            "remaining_today": remaining,
            "can_trade": can_trade_budget,
            "reason": budget_reason
        }
        
        if not can_trade_budget:
            diagnostics['reasons'].append(f"Trade limit: {budget_reason}")
        
        # Check bodyguard metrics
        from services.bodyguard_service import bodyguard_service
        bodyguard_status = await bodyguard_service.get_bot_drawdown_status(bot_id)
        
        if bodyguard_status:
            diagnostics['bodyguard'] = bodyguard_status
            
            if bodyguard_status.get('paused_by_bodyguard'):
                diagnostics['reasons'].append(f"Bodyguard paused: {bodyguard_status.get('pause_reason', 'Drawdown exceeded')}")
        
        # Check API keys
        api_key = await db.api_keys_collection.find_one({
            "user_id": user_id,
            "provider": exchange
        }, {"_id": 0})
        
        diagnostics['api_keys'] = {
            "has_keys": api_key is not None,
            "connected": api_key.get('connected', False) if api_key else False,
            "provider": exchange
        }
        
        if trading_mode == 'live' and not api_key:
            diagnostics['reasons'].append(f"No API keys configured for {exchange}")
        
        # Recent activity
        last_trade_time = bot.get('last_trade_time') or bot.get('last_trade')
        diagnostics['recent_activity'] = {
            "last_trade_time": last_trade_time,
            "trades_count": bot.get('trades_count', 0),
            "current_capital": bot.get('current_capital', 0),
            "total_profit": bot.get('total_profit', 0),
            "win_rate": bot.get('win_rate', 0)
        }
        
        # Determine if bot can trade
        diagnostics['can_trade'] = (
            bot.get('status') == 'active' and
            not emergency_stop and
            not bot.get('paused_by_bodyguard') and
            not bot.get('paused_by_system') and
            can_trade_budget
        )
        
        if diagnostics['can_trade']:
            diagnostics['reasons'] = ["Bot is ready to trade"]
        
        diagnostics['timestamp'] = datetime.now(timezone.utc).isoformat()
        
        return diagnostics
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get bot diagnostics error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/diagnostics")
async def get_all_bots_diagnostics(user_id: str = Depends(get_current_user)):
    """Get diagnostics for all user bots (bulk endpoint)
    
    Returns summary diagnostics for all non-deleted bots
    
    Args:
        user_id: Current user ID (from auth)
        
    Returns:
        List of bot diagnostics with trading readiness status
    """
    try:
        # Get all non-deleted bots
        bots = await db.bots_collection.find(
            {
                "user_id": user_id,
                "status": {"$nin": ["deleted", "marked_for_deletion"]}
            },
            {"_id": 0}
        ).to_list(1000)
        
        diagnostics_list = []
        
        for bot in bots:
            bot_id = bot['id']
            exchange = bot.get('exchange', 'binance')
            
            # Quick diagnostic check
            from engines.trade_budget_manager import trade_budget_manager
            remaining = await trade_budget_manager.get_bot_remaining_budget(bot_id, exchange)
            can_trade_budget, budget_reason = await trade_budget_manager.can_execute_trade(bot_id, exchange)
            
            can_trade = (
                bot.get('status') == 'active' and
                not bot.get('paused_by_bodyguard') and
                not bot.get('paused_by_system') and
                can_trade_budget
            )
            
            # Build reason summary
            reasons = []
            if bot.get('status') != 'active':
                reasons.append(f"Status: {bot.get('status')}")
            if bot.get('paused_by_bodyguard'):
                reasons.append("Bodyguard pause")
            if not can_trade_budget:
                reasons.append("Budget limit")
            
            diagnostics_list.append({
                "bot_id": bot_id,
                "bot_name": bot.get('name'),
                "exchange": exchange,
                "status": bot.get('status'),
                "can_trade": can_trade,
                "reasons": reasons if reasons else ["Ready to trade"],
                "remaining_budget": remaining,
                "trades_count": bot.get('trades_count', 0),
                "win_rate": bot.get('win_rate', 0),
                "total_profit": bot.get('total_profit', 0)
            })
        
        # Summary statistics
        can_trade_count = len([d for d in diagnostics_list if d['can_trade']])
        paused_count = len([d for d in diagnostics_list if 'pause' in str(d['reasons']).lower()])
        budget_limited_count = len([d for d in diagnostics_list if 'budget' in str(d['reasons']).lower()])
        
        return {
            "diagnostics": diagnostics_list,
            "summary": {
                "total_bots": len(diagnostics_list),
                "can_trade": can_trade_count,
                "paused": paused_count,
                "budget_limited": budget_limited_count
            },
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as e:
        logger.error(f"Get all bots diagnostics error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
