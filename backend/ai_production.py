"""
AI Production Handler - Complete Command System
Implements all critical AI commands for full system control
"""

import asyncio
from datetime import datetime, timezone, timedelta
import database as db
from engines.bot_manager import bot_manager
from engines.trade_limiter import trade_limiter
from logger_config import logger
from openai import AsyncOpenAI
import os
import json


class AIProductionHandler:
    def __init__(self):
        # System fallback key (only used if user doesn't have a key)
        self.system_api_key = os.environ.get('OPENAI_API_KEY')
        self.system_client = AsyncOpenAI(api_key=self.system_api_key) if self.system_api_key else None
    
    async def get_openai_client(self, user_id: str) -> tuple[AsyncOpenAI, str]:
        """Get OpenAI client for user - prefers per-user key, falls back to system key
        
        Returns:
            Tuple of (client, key_source) where key_source is 'user', 'system', or 'none'
        """
        try:
            # Try to get user's OpenAI key
            from services.keys_service import keys_service
            user_key_data = await keys_service.get_user_api_key(user_id, 'openai', decrypt=True)
            
            if user_key_data and user_key_data.get('api_key'):
                # Check if key is tested and valid
                status = user_key_data.get('status', '')
                if status == 'test_ok':
                    # Use per-user key
                    user_api_key = user_key_data['api_key']
                    client = AsyncOpenAI(api_key=user_api_key)
                    logger.info(f"Using per-user OpenAI key for user {user_id[:8]}")
                    return client, 'user'
                else:
                    logger.warning(f"User {user_id[:8]} has OpenAI key but status is {status}, falling back to system key")
            
            # Fall back to system key
            if self.system_client:
                logger.info(f"Using system OpenAI key for user {user_id[:8]} (no user key configured)")
                return self.system_client, 'system'
            else:
                logger.error(f"No OpenAI key available for user {user_id[:8]} (no user key and no system key)")
                return None, 'none'
                
        except Exception as e:
            logger.error(f"Error getting OpenAI client for user {user_id[:8]}: {e}")
            # Fall back to system key on error
            if self.system_client:
                return self.system_client, 'system'
            return None, 'none'
        
    async def get_system_context(self, user_id: str) -> dict:
        """Get complete system state"""
        try:
            # Get user
            user = await db.users_collection.find_one({"id": user_id}, {"_id": 0})
            
            # Get all bots
            bots = await db.bots_collection.find({"user_id": user_id}, {"_id": 0}).to_list(100)
            active_bots = [b for b in bots if b.get('status') == 'active']
            
            # Calculate metrics
            total_capital = sum(b.get('current_capital', 0) for b in active_bots)
            total_initial = sum(b.get('initial_capital', 0) for b in active_bots)
            total_profit = total_capital - total_initial
            
            # Get modes
            modes = await db.system_modes_collection.find_one({"user_id": user_id}, {"_id": 0}) or {}
            
            # Get recent trades
            trades = await db.trades_collection.find(
                {"user_id": user_id},
                {"_id": 0}
            ).sort("timestamp", -1).limit(10).to_list(10)
            
            # Get API keys
            api_keys = await db.api_keys_collection.find(
                {"user_id": user_id},
                {"_id": 0, "provider": 1, "connected": 1}
            ).to_list(10)
            
            return {
                "user": user,
                "bots": {
                    "all": bots,
                    "active": active_bots,
                    "total_count": len(bots),
                    "active_count": len(active_bots)
                },
                "financials": {
                    "total_capital": total_capital,
                    "total_initial": total_initial,
                    "total_profit": total_profit,
                    "roi_percent": (total_profit / total_initial * 100) if total_initial > 0 else 0
                },
                "modes": modes,
                "recent_trades": trades,
                "api_keys": {k['provider']: k.get('connected', False) for k in api_keys}
            }
        except Exception as e:
            logger.error(f"Get system context error: {e}")
            return {}
    
    async def execute_command(self, user_id: str, command: str, params: dict) -> dict:
        """Execute AI command"""
        try:
            # BOT CREATION
            if command == "create_bot":
                name = params.get('name', f'Bot-{datetime.now().strftime("%H%M")}')
                exchange = params.get('exchange', 'luno')
                risk_mode = params.get('risk_mode', 'safe')
                capital = params.get('capital', 1000)
                
                result = await bot_manager.create_bot(user_id, name, exchange, risk_mode, capital)
                
                # Send WebSocket
                if result['success']:
                    from websocket_manager import manager
                    await manager.send_message(user_id, {
                        "type": "bot_created",
                        "bot": result.get('bot')
                    })
                
                return result
            
            # DELETE BOT
            elif command == "delete_bot":
                bot_name = params.get('name') or params.get('bot_name')
                result = await bot_manager.delete_bot(user_id, bot_name=bot_name)
                
                if result['success']:
                    from websocket_manager import manager
                    await manager.send_message(user_id, {"type": "force_refresh"})
                
                return result
            
            # PAUSE BOT
            elif command == "pause_bot":
                bot_name = params.get('name') or params.get('bot_name')
                bot = await db.bots_collection.find_one({"user_id": user_id, "name": bot_name}, {"_id": 0})
                if bot:
                    result = await bot_manager.update_bot_status(user_id, bot['id'], 'paused')
                    if result['success']:
                        from websocket_manager import manager
                        await manager.send_message(user_id, {"type": "force_refresh"})
                    return result
                return {"success": False, "message": "❌ Bot not found"}
            
            # RESUME BOT
            elif command == "resume_bot":
                bot_name = params.get('name') or params.get('bot_name')
                bot = await db.bots_collection.find_one({"user_id": user_id, "name": bot_name}, {"_id": 0})
                if bot:
                    result = await bot_manager.update_bot_status(user_id, bot['id'], 'active')
                    if result['success']:
                        from websocket_manager import manager
                        await manager.send_message(user_id, {"type": "force_refresh"})
                    return result
                return {"success": False, "message": "❌ Bot not found"}
            
            # PAUSE ALL
            elif command == "pause_all":
                result = await db.bots_collection.update_many(
                    {"user_id": user_id, "status": "active"},
                    {"$set": {"status": "paused"}}
                )
                from websocket_manager import manager
                await manager.send_message(user_id, {"type": "force_refresh"})
                return {"success": True, "message": f"✅ Paused {result.modified_count} bots"}
            
            # RESUME ALL
            elif command == "resume_all":
                result = await db.bots_collection.update_many(
                    {"user_id": user_id, "status": "paused"},
                    {"$set": {"status": "active"}}
                )
                from websocket_manager import manager
                await manager.send_message(user_id, {"type": "force_refresh"})
                return {"success": True, "message": f"✅ Resumed {result.modified_count} bots"}
            
            # DELETE ALL BOTS (complete removal, not pause)
            elif command == "delete_all_bots":
                result = await db.bots_collection.delete_many({"user_id": user_id})
                from websocket_manager import manager
                await manager.send_message(user_id, {"type": "force_refresh"})
                return {"success": True, "message": f"🗑️ Deleted {result.deleted_count} bots permanently"}
            
            # TOGGLE AUTOPILOT
            elif command == "toggle_autopilot":
                enabled = params.get('enabled', True)
                await db.system_modes_collection.update_one(
                    {"user_id": user_id},
                    {"$set": {"autopilot": enabled}},
                    upsert=True
                )
                from websocket_manager import manager
                await manager.send_message(user_id, {"type": "system_mode_update"})
                return {"success": True, "message": f"✅ Autopilot {'ON' if enabled else 'OFF'}"}
            
            # TOGGLE PAPER TRADING
            elif command == "toggle_paper":
                enabled = params.get('enabled', True)
                await db.system_modes_collection.update_one(
                    {"user_id": user_id},
                    {"$set": {"paperTrading": enabled}},
                    upsert=True
                )
                from websocket_manager import manager
                await manager.send_message(user_id, {"type": "system_mode_update"})
                return {"success": True, "message": f"✅ Paper Trading {'ON' if enabled else 'OFF'}"}
            
            # TOGGLE LIVE TRADING
            elif command == "toggle_live":
                enabled = params.get('enabled', True)
                await db.system_modes_collection.update_one(
                    {"user_id": user_id},
                    {"$set": {"liveTrading": enabled}},
                    upsert=True
                )
                from websocket_manager import manager
                await manager.send_message(user_id, {"type": "system_mode_update"})
                return {"success": True, "message": f"✅ Live Trading {'ON' if enabled else 'OFF'}"}
            
            # EMERGENCY STOP
            elif command == "emergency_stop":
                # Pause all bots
                await db.bots_collection.update_many(
                    {"user_id": user_id},
                    {"$set": {"status": "paused"}}
                )
                # Disable all modes
                await db.system_modes_collection.update_one(
                    {"user_id": user_id},
                    {"$set": {
                        "emergencyStop": True,
                        "autopilot": False,
                        "paperTrading": False,
                        "liveTrading": False
                    }},
                    upsert=True
                )
                from websocket_manager import manager
                await manager.send_message(user_id, {"type": "force_refresh"})
                return {"success": True, "message": "🚨 EMERGENCY STOP - All bots paused, trading disabled"}
            
            # RESUME FROM EMERGENCY
            elif command == "resume_trading":
                await db.system_modes_collection.update_one(
                    {"user_id": user_id},
                    {"$set": {
                        "emergencyStop": False,
                        "paperTrading": True
                    }},
                    upsert=True
                )
                from websocket_manager import manager
                await manager.send_message(user_id, {"type": "force_refresh"})
                return {"success": True, "message": "✅ Trading resumed - Paper mode enabled"}
            
            # SPAWN BOTS (AI-controlled bot creation)
            elif command == "spawn_bots":
                count = int(params.get('count', 1))
                from engines.bot_spawner import bot_spawner
                
                if count == 1:
                    result = await bot_spawner.spawn_single_bot_smart(user_id)
                    if result.get('success'):
                        return {"success": True, "message": f"🤖 Spawned {result['bot']['name']} on {result['bot']['exchange']}"}
                    else:
                        return {"success": False, "message": f"❌ Spawn failed: {result.get('error')}"}
                else:
                    # Spawn multiple or spawn to target
                    result = await bot_spawner.auto_spawn_to_target(user_id)
                    return {"success": True, "message": f"🤖 Spawned {result['spawned_count']} bots (Total: {result['total_bots']}/45)"}
            
            # CHECK WALLET STATUS
            elif command == "wallet_status":
                from engines.wallet_manager import wallet_manager
                balance = await wallet_manager.get_master_balance(user_id)
                if "error" in balance:
                    return {"success": False, "message": f"❌ {balance['error']}"}
                
                msg = "💰 WALLET STATUS (Luno Master)\n"
                msg += f"• ZAR: R{balance.get('zar', 0):,.2f}\n"
                msg += f"• BTC: {balance.get('btc', 0):.8f}\n"
                msg += f"• Total (ZAR): R{balance.get('total_zar', 0):,.2f}"
                return {"success": True, "message": msg}
            
            # REBALANCE TO TOP 5
            elif command == "rebalance_profits":
                # Get top 5 performers
                bots = await db.bots_collection.find({"user_id": user_id}, {"_id": 0}).to_list(100)
                sorted_bots = sorted(bots, key=lambda b: b.get('total_profit', 0), reverse=True)
                top_5_ids = [b['id'] for b in sorted_bots[:5]]
                
                from engines.wallet_manager import wallet_manager
                result = await wallet_manager.rebalance_funds(user_id, top_5_ids)
                
                if result.get('success'):
                    return {"success": True, "message": f"💰 Rebalanced R{result['total_profit']:.2f} to top 5 bots (R{result['per_bot']:.2f} each)"}
                else:
                    return {"success": False, "message": result.get('message', 'Rebalance failed')}
            
            # CHECK PROMOTION STATUS
            elif command == "check_promotions":
                from engines.auto_promotion_manager import auto_promotion_manager
                result = await auto_promotion_manager.check_all_bots_for_promotion(user_id)
                
                if result.get('promoted', 0) > 0:
                    msg = f"🎉 Promoted {result['promoted']} bots to live!"
                else:
                    msg = f"📊 Checked {result.get('checked', 0)} bots - none ready for promotion yet"
                
                return {"success": True, "message": msg}
            
            # RESET SYSTEM (complete wipe - everything back to zero)
            elif command == "reset_system":
                confirm = params.get('confirm', '').lower()
                if confirm != 'yes':
                    return {"success": False, "message": "⚠️ DANGER: This resets EVERYTHING to zero. Say: 'reset system confirm yes'"}
                
                # Reset ALL bot data to initial state
                bots = await db.bots_collection.find({"user_id": user_id}, {"_id": 0}).to_list(100)
                for bot in bots:
                    await db.bots_collection.update_one(
                        {"id": bot['id']},
                        {"$set": {
                            "current_capital": bot.get('initial_capital', 1000),
                            "total_profit": 0,
                            "total_injections": 0,
                            "trades_count": 0,
                            "win_count": 0,
                            "loss_count": 0,
                            "daily_trade_count": 0,
                            "last_trade": None,
                            "last_trade_time": None,
                            "first_trade_at": None,
                            "last_trade_at": None
                        }}
                    )
                
                # Delete ALL user data (trades, logs, EVERYTHING)
                import database as db
                await db.trades_collection.delete_many({"user_id": user_id})
                await db.learning_logs_collection.delete_many({"user_id": user_id})
                await db.learning_data_collection.delete_many({"user_id": user_id})
                await db.autopilot_actions_collection.delete_many({"user_id": user_id})
                await db.rogue_detections_collection.delete_many({"user_id": user_id})
                await db.alerts_collection.delete_many({"user_id": user_id})
                await db.chat_messages_collection.delete_many({"user_id": user_id})
                
                # Delete capital injections history
                import database as db
                await db.capital_injections.delete_many({"user_id": user_id})
                
                logger.info(f"🔄 COMPLETE RESET executed for user {user_id[:8]} - ALL data deleted")
                
                # Delete audit logs (optional - keep for compliance)
                # await db.audit_logs.delete_many({"user_id": user_id})
                
                # Reset system modes (keep paper trading on)
                await db.system_modes_collection.update_one(
                    {"user_id": user_id},
                    {"$set": {
                        "paperTrading": True,
                        "liveTrading": False,
                        "autopilot": False,
                        "emergencyStop": False
                    }},
                    upsert=True
                )
                
                # Send refresh
                from websocket_manager import manager
                await manager.send_message(user_id, {"type": "force_refresh"})
                
                return {"success": True, "message": "🔄 COMPLETE RESET! All profits, trades, graphs, learning data → ZERO. Fresh start!"}
            
            else:
                return {"success": False, "message": f"❌ Unknown command: {command}"}
        
        except Exception as e:
            logger.error(f"Execute command error: {e}")
            return {"success": False, "message": f"❌ Error: {str(e)}"}
    
    async def get_ai_response(self, user_id: str, message: str) -> str:
        """Get AI response with command execution"""
        try:
            # Get system context
            context = await self.get_system_context(user_id)
            
            # Current time
            now = datetime.now(timezone.utc)
            current_time = now.strftime("%A, %B %d, %Y at %I:%M:%S %p UTC")
            
            # Build system prompt
            bots_summary = f"{context['bots']['active_count']} active out of {context['bots']['total_count']} total"
            modes = context['modes']
            financials = context['financials']
            
            system_prompt = f"""You are Amarktai AI - 150% Full Dashboard Controller.

TIME: {current_time}

SYSTEM STATUS:
• Bots: {bots_summary}
• Capital: R{financials['total_capital']:,.2f}
• Profit: R{financials['total_profit']:,.2f} ({financials['roi_percent']:.2f}%)
• Autopilot: {'ON' if modes.get('autopilot') else 'OFF'}
• Paper: {'ON' if modes.get('paperTrading') else 'OFF'}
• Live: {'ON' if modes.get('liveTrading') else 'OFF'}

YOUR ROLE: You have COMPLETE control of this trading system. Execute ANY user request related to bots, trading, analysis, or system management.

COMMANDS (respond with ACTION:command|params|MESSAGE:text):

BOT CONTROL:
• create_bot|name:Name|exchange:luno|risk_mode:safe|capital:1000
• delete_bot|name:BotName
• delete_all_bots (REMOVES ALL BOTS permanently)
• pause_bot|name:BotName / pause_all
• resume_bot|name:BotName / resume_all
• rename_bot|old_name:Old|new_name:New

SYSTEM CONTROL:
• toggle_autopilot|enabled:true/false
• toggle_paper|enabled:true/false
• toggle_live|enabled:true/false (DANGEROUS!)
• emergency_stop (stops EVERYTHING)
• resume_trading
• reset_system|confirm:yes (WIPES ALL DATA - profits, trades, graphs, learning → ZERO)

ANALYSIS:
• analyze_performance / top_performers|limit:5 / bottom_performers|limit:5
• learning_analysis (trigger AI learning)

RULES:
1. For ANY user request: understand intent, map to command, execute
2. Info questions (time, profit, status): answer directly (no ACTION:)
3. "show/hide admin": just acknowledge (frontend handles password)
4. Be proactive - if user wants something, make it happen!

EXAMPLES:
"delete everything" → ACTION:delete_all_bots|MESSAGE:Deleting all bots
"wipe the system" → ACTION:reset_system|confirm:yes|MESSAGE:Complete system reset
"make a Zeus bot" → ACTION:create_bot|name:Zeus|MESSAGE:Creating Zeus"""

            # Call AI with multi-model routing
            from ai_models_router import ai_models_router
            
            # Use ChatOps brain for dashboard commands
            response_text = await ai_models_router.chatops_response(message, system_prompt, user_id)
            
            # Check for ACTION
            if response_text.strip().startswith('ACTION:'):
                parts = response_text.strip().split('|')
                command = parts[0].replace('ACTION:', '').strip()
                
                params = {}
                ai_message = ""
                
                for part in parts[1:]:
                    if ':' in part:
                        key, val = part.split(':', 1)
                        key = key.strip()
                        val = val.strip()
                        
                        if key == 'MESSAGE':
                            ai_message = val
                        elif key == 'enabled':
                            params[key] = val.lower() == 'true'
                        elif key in ['capital']:
                            params[key] = float(val)
                        else:
                            params[key] = val
                
                # Execute command
                result = await self.execute_command(user_id, command, params)
                
                if result['success']:
                    return f"{ai_message}\n\n{result['message']}" if ai_message else result['message']
                return result['message']
            
            return response_text
        
        except Exception as e:
            logger.error(f"AI response error: {e}")
            return f"❌ AI Error: {str(e)}"


ai_production = AIProductionHandler()
