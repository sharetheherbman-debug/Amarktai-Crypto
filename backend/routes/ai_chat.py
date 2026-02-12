"""
AI Super Intelligence Chat Router
Real-time AI chat with action confirmation and tool routing
"""

from fastapi import APIRouter, HTTPException, Depends, Body, Query
from fastapi.responses import JSONResponse
import asyncio
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any
import logging
import json
import os

from auth import get_current_user
import database as db
from ai_super_brain import AISuperBrain
from engines.trade_budget_manager import trade_budget_manager
from websocket_manager import manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/ai", tags=["AI Chat"])

ai_brain = AISuperBrain()

# Action confirmation tokens storage (in production, use Redis)
confirmation_tokens = {}

ALLOW_ENV_OPENAI_KEY = os.getenv("ALLOW_ENV_OPENAI_KEY", "false").lower() == "true"
last_ai_error: Optional[Dict] = None

CONFIRM_RESET_RISK = "RESET RISK LOCKS"
CONFIRM_LIVE_TRADING = "CONFIRM LIVE TRADING"
CONFIRM_AUTOPILOT = "CONFIRM AUTOPILOT"
CONFIRM_TRANSFER = "CONFIRM TRANSFER"


def wants_code_response(content: str) -> bool:
    content_lower = content.lower()
    return any(keyword in content_lower for keyword in ["code", "snippet", "script", "example code"])


async def get_user_memory(user_id: str) -> Dict[str, Any]:
    memory = await db.user_memory_collection.find_one({"user_id": user_id}, {"_id": 0})
    return memory or {}


async def update_user_memory(user_id: str, updates: Dict[str, Any]):
    now = datetime.now(timezone.utc).isoformat()
    await db.user_memory_collection.update_one(
        {"user_id": user_id},
        {"$set": {**updates, "updated_at": now}, "$setOnInsert": {"user_id": user_id, "created_at": now}},
        upsert=True
    )


async def log_chatops_action(user_id: str, action: str, params: Dict[str, Any], result: Dict[str, Any]):
    await db.chatops_actions_collection.insert_one({
        "user_id": user_id,
        "action": action,
        "params": params,
        "result": result,
        "timestamp": datetime.now(timezone.utc).isoformat()
    })


async def build_recent_summary(user_id: str) -> Dict[str, Any]:
    window_start = datetime.now(timezone.utc) - timedelta(days=7)
    trades = await db.trades_collection.find(
        {"user_id": user_id, "timestamp": {"$gte": window_start.isoformat()}},
        {"_id": 0, "net_pnl": 1, "profit_loss": 1}
    ).to_list(10000)
    total = len(trades)
    wins = sum(1 for t in trades if t.get("net_pnl", t.get("profit_loss", 0)) > 0)
    losses = sum(1 for t in trades if t.get("net_pnl", t.get("profit_loss", 0)) < 0)
    pnl = sum(t.get("net_pnl", t.get("profit_loss", 0)) for t in trades)
    return {
        "trades": total,
        "wins": wins,
        "losses": losses,
        "net_pnl": round(pnl, 2),
        "window_start": window_start.isoformat()
    }


async def find_bot_match(user_id: str, content: str) -> Optional[Dict[str, Any]]:
    bots = await db.bots_collection.find(
        {"user_id": user_id, "status": {"$ne": "deleted"}},
        {"_id": 0, "id": 1, "name": 1, "status": 1, "trading_mode": 1}
    ).to_list(200)
    content_lower = content.lower()
    for bot in bots:
        bot_name = (bot.get("name") or "").lower()
        if bot_name and bot_name in content_lower:
            return bot
    return bots[0] if len(bots) == 1 else None


def detect_action_intent(content: str, request_action: bool) -> Optional[Dict[str, Any]]:
    content_lower = content.lower()
    commandish = request_action or content_lower.startswith(
        ("start", "resume", "pause", "stop", "switch", "toggle", "reset", "transfer", "withdraw", "overview", "status", "risk")
    )

    if not commandish:
        return None

    if "overview" in content_lower:
        return {"action": "fetch_overview"}
    if "system status" in content_lower or content_lower.strip() == "status":
        return {"action": "fetch_status"}
    if "risk" in content_lower and "reset" not in content_lower:
        return {"action": "fetch_risk"}
    if "pause" in content_lower and "bot" in content_lower:
        return {"action": "pause_bot"}
    if ("resume" in content_lower or "start" in content_lower) and "bot" in content_lower:
        return {"action": "resume_bot"}
    if "stop" in content_lower and "bot" in content_lower:
        return {"action": "stop_bot"}
    if "reset" in content_lower and "risk" in content_lower:
        return {"action": "reset_risk_locks"}
    if "autopilot" in content_lower:
        enabled = "disable" not in content_lower
        return {"action": "toggle_autopilot", "params": {"enabled": enabled}}
    if "live" in content_lower and ("switch" in content_lower or "enable" in content_lower):
        return {"action": "switch_mode", "params": {"mode": "live"}}
    if "paper" in content_lower and ("switch" in content_lower or "enable" in content_lower):
        return {"action": "switch_mode", "params": {"mode": "paper"}}
    if "transfer" in content_lower or "withdraw" in content_lower:
        return {"action": "wallet_transfer"}

    return None


def parse_transfer_params(content: str) -> Dict[str, Any]:
    supported = ["luno", "binance", "kucoin", "bybit", "kraken", "bitget", "gate"]
    content_lower = content.lower()
    params: Dict[str, Any] = {}

    for exchange in supported:
        if f"from {exchange}" in content_lower:
            params["from_exchange"] = exchange
        if f"to {exchange}" in content_lower:
            params["to_exchange"] = exchange

    import re
    amount_match = re.search(r"(\d+(?:\.\d+)?)\s*(zar|usdt|btc|eth|xrp)", content_lower)
    if amount_match:
        params["amount"] = float(amount_match.group(1))
        params["currency"] = amount_match.group(2).upper()

    return params


async def resolve_openai_key(user_id: str) -> tuple[Optional[str], str]:
    """Resolve OpenAI API key using canonical priority."""
    from routes.api_key_management import get_decrypted_key

    key_data = await get_decrypted_key(user_id, "openai")
    if key_data and key_data.get("api_key"):
        return key_data.get("api_key"), "user"

    if ALLOW_ENV_OPENAI_KEY:
        env_key = os.getenv("OPENAI_API_KEY")
        if env_key:
            return env_key, "env"

    return None, "none"


def record_ai_error(code: str, message: str) -> None:
    global last_ai_error
    last_ai_error = {
        "code": code,
        "message": message,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def build_ai_error_response(
    *,
    status_code: int,
    code: str,
    message: str,
    user_message: str,
    system_state: Optional[Dict] = None,
    key_source: Optional[str] = None
) -> JSONResponse:
    record_ai_error(code, message)
    return JSONResponse(
        status_code=status_code,
        content={
            "success": False,
            "error": message,
            "code": code,
            "role": "assistant",
            "content": user_message,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "system_state": system_state,
            "key_source": key_source
        }
    )


class AIActionRouter:
    """Routes AI actions to appropriate system functions"""
    
    @staticmethod
    async def get_system_state(user_id: str) -> Dict:
        """Get comprehensive system state for AI context"""
        # Get bots
        bots = await db.bots_collection.find(
            {"user_id": user_id},
            {"_id": 0}
        ).to_list(1000)
        
        # Get system modes
        modes = await db.system_modes_collection.find_one(
            {"user_id": user_id},
            {"_id": 0}
        )
        
        # Get recent trades
        recent_trades = await db.trades_collection.find(
            {"user_id": user_id},
            {"_id": 0}
        ).sort("timestamp", -1).limit(10).to_list(10)
        
        # Get wallet summary
        total_capital = sum(bot.get('current_capital', 0) for bot in bots)
        total_profit = sum(bot.get('total_profit', 0) for bot in bots)
        
        # Get budget status
        budget_status = await trade_budget_manager.get_all_exchanges_budget_report()
        
        return {
            "bots": {
                "total": len(bots),
                "active": len([b for b in bots if b.get('status') == 'active']),
                "paused": len([b for b in bots if b.get('status') == 'paused']),
                "stopped": len([b for b in bots if b.get('status') == 'stopped'])
            },
            "capital": {
                "total": round(total_capital, 2),
                "total_profit": round(total_profit, 2)
            },
            "recent_performance": {
                "recent_trades_count": len(recent_trades),
                "recent_pnl": round(sum(t.get('profit_loss', 0) for t in recent_trades), 2)
            },
            "system_modes": modes or {},
            "budget_status": budget_status,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    
    @staticmethod
    async def execute_action(action: str, params: Dict, user_id: str) -> Dict:
        """Execute an AI-requested action with appropriate permissions"""
        try:
            if action == "start_bot":
                bot_id = params.get('bot_id')
                result = await db.bots_collection.update_one(
                    {"id": bot_id, "user_id": user_id},
                    {"$set": {"status": "active"}}
                )
                return {"success": result.modified_count > 0, "action": "start_bot", "bot_id": bot_id}
            
            elif action == "pause_bot":
                bot_id = params.get('bot_id')
                reason = params.get('reason', 'AI recommendation')
                result = await db.bots_collection.update_one(
                    {"id": bot_id, "user_id": user_id},
                    {"$set": {
                        "status": "paused",
                        "pause_reason": reason,
                        "paused_by_system": True
                    }}
                )
                return {"success": result.modified_count > 0, "action": "pause_bot", "bot_id": bot_id}
            
            elif action == "stop_bot":
                bot_id = params.get('bot_id')
                result = await db.bots_collection.update_one(
                    {"id": bot_id, "user_id": user_id},
                    {"$set": {"status": "stopped"}}
                )
                return {"success": result.modified_count > 0, "action": "stop_bot", "bot_id": bot_id}

            elif action == "resume_bot":
                bot_id = params.get('bot_id')
                result = await db.bots_collection.update_one(
                    {"id": bot_id, "user_id": user_id},
                    {"$set": {"status": "active"}}
                )
                return {"success": result.modified_count > 0, "action": "resume_bot", "bot_id": bot_id}
            
            elif action == "emergency_stop":
                result = await db.system_modes_collection.update_one(
                    {"user_id": user_id},
                    {"$set": {"emergencyStop": True}},
                    upsert=True
                )
                # Pause all bots
                await db.bots_collection.update_many(
                    {"user_id": user_id, "status": "active"},
                    {"$set": {
                        "status": "paused",
                        "pause_reason": "Emergency stop activated by AI",
                        "paused_by_system": True
                    }}
                )
                return {"success": True, "action": "emergency_stop"}

            elif action == "toggle_autopilot":
                enabled = bool(params.get("enabled", False))
                await db.system_modes_collection.update_one(
                    {"user_id": user_id},
                    {"$set": {"autopilot": enabled}},
                    upsert=True
                )
                return {"success": True, "action": "toggle_autopilot", "enabled": enabled}

            elif action == "switch_mode":
                from routes.system_mode import set_system_mode
                mode = params.get("mode")
                if mode not in ["paper", "live", "autopilot"]:
                    return {"success": False, "error": "Invalid mode"}
                await set_system_mode(mode, user_id)
                return {"success": True, "action": "switch_mode", "mode": mode}

            elif action == "reset_risk_locks":
                await db.users_collection.update_one(
                    {"id": user_id},
                    {
                        "$set": {
                            "daily_loss_lock_active": False,
                            "daily_loss_lock_reset_at": datetime.now(timezone.utc).isoformat(),
                            "daily_loss_lock_reset_by": user_id
                        },
                        "$unset": {
                            "daily_loss_locked_at": "",
                            "daily_loss_locked_reason": "",
                            "daily_loss_pct": "",
                            "daily_loss_day_key": ""
                        }
                    }
                )
                try:
                    from realtime_events import rt_events
                    await rt_events.lock_reset(user_id, "daily_loss")
                except Exception:
                    pass
                return {"success": True, "action": "reset_risk_locks"}

            elif action == "wallet_transfer":
                from services.transfer_state_machine import TransferStateMachine
                transfer_machine = TransferStateMachine()
                result = await transfer_machine.request_transfer(
                    user_id=user_id,
                    from_exchange=params.get("from_exchange"),
                    to_exchange=params.get("to_exchange"),
                    currency=params.get("currency"),
                    amount=float(params.get("amount", 0)),
                    idempotency_key=params.get("idempotency_key")
                )
                return {"success": True, "action": "wallet_transfer", "result": result}
            
            elif action == "get_limits":
                limits = await trade_budget_manager.get_all_exchanges_budget_report()
                return {"success": True, "action": "get_limits", "data": limits}
            
            elif action == "get_performance_graph":
                # Return data for graphs
                from routes.analytics_api import get_pnl_timeseries
                # This would need to be called differently, but showing the concept
                return {"success": True, "action": "get_performance_graph", "info": "Use /api/analytics/pnl_timeseries"}
            
            else:
                return {"success": False, "error": f"Unknown action: {action}"}
        
        except Exception as e:
            logger.error(f"Action execution failed: {e}")
            return {"success": False, "error": str(e)}


action_router = AIActionRouter()


@router.post("/chat")
async def ai_chat(
    message: Dict = Body(...),
    user_id: str = Depends(get_current_user)
):
    """AI chat endpoint with action routing and confirmation
    
    Body:
        {
            "content": "user message",
            "request_action": false,  # if true, AI can propose actions
            "confirmation_token": null  # for confirming dangerous actions
        }
    """
    try:
        content = message.get('message') or message.get('content', '')
        request_action = message.get('request_action', False)
        confirmation_token = message.get('confirmation_token')
        user_tag = user_id[:8] if user_id else "unknown"
        logger.info(
            "AI chat request user=%s message_length=%d request_action=%s",
            user_tag,
            len(content or ""),
            request_action
        )
        
        # Content filter: Block admin-related queries
        content_lower = content.lower()
        
        # Admin panel trigger - password gate (TASK E)
        admin_trigger_phrases = [
            'show admin',
            'admin panel',
            'admin access',
            'admin login',
            'unlock admin',
            'admin unlock'
        ]
        
        if any(phrase in content_lower for phrase in admin_trigger_phrases):
            # Return admin panel trigger with password requirement
            admin_response = {
                "role": "assistant",
                "content": "🔐 Admin Panel Access\n\nTo access the admin panel, please enter the admin password.\n\nIf you've forgotten your password, contact the system administrator.",
                "action": "show_admin_panel",
                "requires_password": True,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            
            # Save assistant message
            await db.chat_messages_collection.insert_one({
                "user_id": user_id,
                **admin_response
            })
            
            admin_response["success"] = True
            return admin_response
        
        # Block admin credential/password requests
        blocked_phrases = [
            'admin password',
            'admin credentials',
            'what is admin',
            'give me admin'
        ]
        
        if any(phrase in content_lower for phrase in blocked_phrases):
            # Return filtered response
            filtered_response = {
                "role": "assistant",
                "content": "⚠️ I cannot help with admin passwords or credentials. Admin features require secure authentication. Please contact support if you need assistance.",
                "filtered": True,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
            
            # Save filtered assistant message
            await db.chat_messages_collection.insert_one({
                "user_id": user_id,
                **filtered_response
            })
            
            filtered_response["success"] = True
            return filtered_response
        
        # Save user message
        user_msg = {
            "user_id": user_id,
            "role": "user",
            "content": content,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        await db.chat_messages_collection.insert_one(user_msg)
        
        # Get system state for AI context
        system_state = await action_router.get_system_state(user_id)
        
        # Load full chat history for context (last 30 messages)
        chat_history = await db.chat_messages_collection.find(
            {"user_id": user_id},
            {"_id": 0}
        ).sort("timestamp", -1).limit(30).to_list(30)
        chat_history.reverse()

        # Load per-user memory and update with latest 7-day summary
        memory = await get_user_memory(user_id)
        recent_summary = await build_recent_summary(user_id)
        user_doc = await db.users_collection.find_one({"id": user_id}, {"_id": 0, "risk_profile": 1})
        risk_profile = (user_doc or {}).get("risk_profile") or memory.get("risk_profile") or "balanced"
        await update_user_memory(user_id, {
            "risk_profile": risk_profile,
            "last_7d_summary": recent_summary
        })
        memory = await get_user_memory(user_id)
        
        # Check if this is a confirmation for a dangerous action
        if confirmation_token and confirmation_token in confirmation_tokens:
            action_data = confirmation_tokens[confirmation_token]
            confirmation_phrase = message.get("confirmation_phrase") or ""
            phrase_source = confirmation_phrase or content
            
            # Verify it's for this user
            if action_data['user_id'] == user_id:
                required_phrase = action_data.get("confirmation_phrase")
                if required_phrase and required_phrase.upper() not in phrase_source.upper():
                    ai_response = (
                        f"Please confirm by typing the exact phrase: {required_phrase}. "
                        f"Then resend your confirmation token."
                    )
                else:
                    # Execute the confirmed action
                    result = await action_router.execute_action(
                        action_data['action'],
                        action_data['params'],
                        user_id
                    )
                    
                    # Remove token
                    del confirmation_tokens[confirmation_token]
                    
                    ai_response = f"Confirmed. Action executed: {action_data['action']}."
                    
                    await log_chatops_action(user_id, action_data['action'], action_data['params'], result)
                    await update_user_memory(user_id, {
                        "last_commands": (memory.get("last_commands", []) + [action_data['action']])[-5:]
                    })
                    
                    # Send WebSocket notification
                    await manager.send_message(user_id, {
                        "type": "ai_action_executed",
                        "action": action_data['action'],
                        "result": result
                    })
            else:
                ai_response = "Invalid confirmation token or unauthorized."
        else:
            handled_action = False
            action_request = detect_action_intent(content, request_action)
            if action_request:
                action = action_request["action"]
                params = action_request.get("params", {})
                handled_action = True

                if action in ["pause_bot", "resume_bot", "stop_bot"]:
                    bot = await find_bot_match(user_id, content)
                    if not bot:
                        ai_response = "Please specify the bot name you want to control."
                    else:
                        params["bot_id"] = bot.get("id")
                        is_paper = bot.get("trading_mode", "paper") == "paper"
                        requires_confirmation = (action == "stop_bot") or not is_paper
                        if requires_confirmation:
                            import uuid
                            token = str(uuid.uuid4())
                            confirmation_tokens[token] = {
                                "user_id": user_id,
                                "action": action,
                                "params": params,
                                "created_at": datetime.now(timezone.utc).isoformat()
                            }
                            await log_chatops_action(
                                user_id,
                                action,
                                params,
                                {"status": "confirmation_required", "token": token}
                            )
                            ai_response = (
                                f"This action affects {'live' if not is_paper else 'paper'} trading and needs confirmation. "
                                f"Reply with confirmation token: {token}"
                            )
                        else:
                            result = await action_router.execute_action(action, params, user_id)
                            await log_chatops_action(user_id, action, params, result)
                            await update_user_memory(user_id, {
                                "last_commands": (memory.get("last_commands", []) + [action])[-5:]
                            })
                            ai_response = f"Done. {action.replace('_', ' ')} executed for bot {bot.get('name')}."

                elif action in ["fetch_overview", "fetch_status", "fetch_risk"]:
                    if action == "fetch_overview":
                        from services.overview_service import OverviewService
                        overview = await OverviewService().get_snapshot(user_id)
                        ai_response = (
                            f"Overview: Profit R{overview.get('total_profit', 0):.2f}, "
                            f"Active bots {overview.get('bots_active', 0)}, "
                            f"Win rate {overview.get('win_rate', 0):.2f}%."
                        )
                        result = {"overview": overview}
                    elif action == "fetch_status":
                        from routes.system_status import get_system_status
                        status = await get_system_status(user_id)
                        ai_response = (
                            f"System status: DB {'connected' if status['database']['connected'] else 'degraded'}, "
                            f"active bots {status['trading_activity']['active_bots']}."
                        )
                        result = {"status": status}
                    else:
                        from routes.risk_management import get_risk_status
                        risk = await get_risk_status(user_id)
                        ai_response = (
                            f"Risk status: daily loss lock "
                            f"{'active' if risk['daily_loss_lock']['active'] else 'clear'}, "
                            f"emergency stop {'active' if risk['emergency_stop']['active'] else 'clear'}."
                        )
                        result = {"risk": risk}

                    await log_chatops_action(user_id, action, params, result)
                    await update_user_memory(user_id, {
                        "last_commands": (memory.get("last_commands", []) + [action])[-5:]
                    })

                elif action == "reset_risk_locks":
                    user_doc = await db.users_collection.find_one({"id": user_id}, {"_id": 0, "is_admin": 1})
                    if not user_doc or not user_doc.get("is_admin", False):
                        ai_response = "Resetting risk locks requires admin privileges."
                    else:
                        import uuid
                        token = str(uuid.uuid4())
                        confirmation_tokens[token] = {
                            "user_id": user_id,
                            "action": action,
                            "params": params,
                            "confirmation_phrase": CONFIRM_RESET_RISK,
                            "created_at": datetime.now(timezone.utc).isoformat()
                        }
                        await log_chatops_action(
                            user_id,
                            action,
                            params,
                            {"status": "confirmation_required", "token": token}
                        )
                        ai_response = (
                            f"This requires confirmation. Reply with token {token} and phrase: {CONFIRM_RESET_RISK}."
                        )

                elif action == "toggle_autopilot":
                    import uuid
                    token = str(uuid.uuid4())
                    confirmation_tokens[token] = {
                        "user_id": user_id,
                        "action": action,
                        "params": params,
                        "confirmation_phrase": CONFIRM_AUTOPILOT,
                        "created_at": datetime.now(timezone.utc).isoformat()
                    }
                    await log_chatops_action(
                        user_id,
                        action,
                        params,
                        {"status": "confirmation_required", "token": token}
                    )
                    ai_response = (
                        f"Autopilot change needs confirmation. Reply with token {token} and phrase: {CONFIRM_AUTOPILOT}."
                    )

                elif action == "switch_mode":
                    mode = params.get("mode")
                    if mode == "live":
                        from routes.system_mode import live_trading_enabled, check_luno_balance
                        if not live_trading_enabled():
                            ai_response = "Live trading is disabled by configuration."
                        else:
                            has_balance, balance = await check_luno_balance(user_id)
                            if not has_balance:
                                ai_response = f"Live trading requires funded Luno wallet (current: R{balance:.2f})."
                            else:
                                import uuid
                                token = str(uuid.uuid4())
                                confirmation_tokens[token] = {
                                    "user_id": user_id,
                                    "action": action,
                                    "params": params,
                                    "confirmation_phrase": CONFIRM_LIVE_TRADING,
                                    "created_at": datetime.now(timezone.utc).isoformat()
                                }
                                await log_chatops_action(
                                    user_id,
                                    action,
                                    params,
                                    {"status": "confirmation_required", "token": token}
                                )
                                ai_response = (
                                    f"Switching to live trading needs confirmation. "
                                    f"Reply with token {token} and phrase: {CONFIRM_LIVE_TRADING}."
                                )
                    else:
                        result = await action_router.execute_action(action, params, user_id)
                        await log_chatops_action(user_id, action, params, result)
                        await update_user_memory(user_id, {
                            "last_commands": (memory.get("last_commands", []) + [action])[-5:]
                        })
                        ai_response = "System switched to paper trading."

                elif action == "wallet_transfer":
                    params = {**params, **parse_transfer_params(content)}
                    missing = [key for key in ["from_exchange", "to_exchange", "amount", "currency"] if not params.get(key)]
                    if missing:
                        ai_response = f"Please specify transfer details: {', '.join(missing)}."
                    else:
                        params["idempotency_key"] = params.get("idempotency_key") or f"chatops-{datetime.now(timezone.utc).timestamp()}"
                        import uuid
                        token = str(uuid.uuid4())
                        confirmation_tokens[token] = {
                            "user_id": user_id,
                            "action": action,
                            "params": params,
                            "confirmation_phrase": CONFIRM_TRANSFER,
                            "created_at": datetime.now(timezone.utc).isoformat()
                        }
                        await log_chatops_action(
                            user_id,
                            action,
                            params,
                            {"status": "confirmation_required", "token": token}
                        )
                        ai_response = (
                            "Transfers require confirmation and may need admin approval. "
                            f"Reply with token {token} and phrase: {CONFIRM_TRANSFER}."
                        )

            if not handled_action:
                # Generate AI response with OpenAI - CANONICAL KEY RETRIEVAL + MODEL FALLBACK
                error_code = None
                try:
                    user_api_key, key_source = await resolve_openai_key(user_id)
                    logger.info(
                        "AI chat key lookup user=%s provider=openai found=%s source=%s",
                        user_tag,
                        bool(user_api_key),
                        key_source
                    )
                    
                    if not user_api_key:
                        return build_ai_error_response(
                            status_code=409,
                            code="no_api_key",
                            message="OpenAI key not configured",
                            user_message="❌ OpenAI key not configured. Please save your OpenAI API key in Settings → API Keys.",
                            system_state=system_state,
                            key_source="none"
                        )
                    
                    # Use AsyncOpenAI client (openai>=1.x) with user's key
                    from openai import AsyncOpenAI
                    
                    try:
                        request_timeout = float(os.getenv("OPENAI_TIMEOUT_SECONDS", "30"))
                    except ValueError:
                        request_timeout = 30.0
                        logger.warning("Invalid OPENAI_TIMEOUT_SECONDS value, defaulting to 30s")
                    
                    # Create client with user's API key
                    client = AsyncOpenAI(api_key=user_api_key, timeout=request_timeout)
                    
                    # MODEL FALLBACK - Same as keys/test
                    fallback_models = []
                    primary_model = os.getenv("OPENAI_MODEL")
                    if primary_model:
                        fallback_models.append(primary_model)
                    fallback_env = os.getenv("OPENAI_FALLBACK_MODEL")
                    if fallback_env and fallback_env not in fallback_models:
                        fallback_models.append(fallback_env)
                    
                    # Safe ordered allowlist (prefer cheap models for chat)
                    allowlist = ["gpt-4o-mini", "gpt-4.1-mini", "gpt-4o", "gpt-3.5-turbo"]
                    for m in allowlist:
                        if m not in fallback_models:
                            fallback_models.append(m)
                    if not fallback_models:
                        return build_ai_error_response(
                            status_code=500,
                            code="model_not_set",
                            message="No OpenAI model configured",
                            user_message="❌ AI model not configured. Set OPENAI_MODEL in environment.",
                            system_state=system_state,
                            key_source=key_source
                        )
                    
                    memory_preferences = memory.get("preferences", {})
                    memory_commands = memory.get("last_commands", [])
                    
                    # Prepare context for AI
                    context = f"""You are an AI trading assistant for the Amarktai Network.
                    
Current System State:
- Total Bots: {system_state['bots']['total']} (Active: {system_state['bots']['active']}, Paused: {system_state['bots']['paused']})
- Total Capital: R{system_state['capital']['total']}
- Total Profit: R{system_state['capital']['total_profit']}
- Recent Performance: {system_state['recent_performance']['recent_trades_count']} trades, R{system_state['recent_performance']['recent_pnl']} PnL

User Memory:
- Preferences: {memory_preferences}
- Risk Profile: {risk_profile}
- Last 7-day summary: {recent_summary}
- Last commands: {memory_commands}

User Question: {content}

Instructions:
- Respond in plain language (no code blocks unless the user asks for code)
- Be helpful and explain the system state clearly
- If user asks for an action, describe the safety checks
- Provide concise next steps
- Use conversation history for context to maintain continuity
"""
                    
                    # Build messages with history for context
                    ai_messages = [{"role": "system", "content": context}]
                    
                    # Add recent chat history for context
                    for hist_msg in chat_history[-10:]:  # Last 10 messages
                        ai_messages.append({
                            "role": hist_msg.get("role"),
                            "content": hist_msg.get("content")
                        })
                    
                    # Add current user message
                    ai_messages.append({"role": "user", "content": content})
                    
                    # Try each model in fallback order
                    model_used = None
                    ai_response = None
                    
                    for test_model in fallback_models:
                        try:
                            logger.info(
                                "AI chat OpenAI call user=%s model=%s",
                                user_tag,
                                test_model
                            )
                            response = await asyncio.wait_for(
                                client.chat.completions.create(
                                    model=test_model,
                                    messages=ai_messages,
                                    max_tokens=500,
                                    temperature=0.7
                                ),
                                timeout=request_timeout
                            )
                            ai_response = response.choices[0].message.content if response.choices else ""
                            model_used = test_model
                            logger.info(
                                "AI chat response user=%s model=%s response_length=%d",
                                user_tag,
                                model_used,
                                len(ai_response or "")
                            )
                            break  # Success!
                        except Exception as model_error:
                            error_str = str(model_error)
                            # Try next model on 403/404
                            if "404" in error_str or "model_not_found" in error_str.lower() or "403" in error_str or "forbidden" in error_str.lower():
                                logger.info(f"AI chat model {test_model} unavailable, trying next")
                                continue
                            if "401" in error_str or "invalid_api_key" in error_str.lower():
                                error_code = "invalid_key"
                                raise model_error
                            if "429" in error_str:
                                error_code = "upstream_429"
                                raise model_error
                            raise model_error
                    
                    if not ai_response or not ai_response.strip():
                        # All models failed
                        return build_ai_error_response(
                            status_code=502,
                            code="all_models_failed",
                            message="All configured OpenAI models failed",
                            user_message="❌ AI models unavailable. Please check your OpenAI API key permissions.",
                            system_state=system_state,
                            key_source=key_source
                        )
                    
                    # Success - add metadata
                    logger.info(f"AI chat used model: {model_used}, key_source: {key_source}")
                
                except Exception as e:
                    logger.error(f"OpenAI API error: {e}")
                    error_str = str(e)
                    if error_code is None:
                        if "401" in error_str or "invalid_api_key" in error_str.lower():
                            error_code = "invalid_key"
                        elif "429" in error_str:
                            error_code = "upstream_429"
                        elif "timeout" in error_str.lower():
                            error_code = "timeout"
                        else:
                            error_code = "upstream_error"
                    if error_code == "invalid_key":
                        user_message = "❌ OpenAI authentication failed. Please re-save your OpenAI key."
                        status_code = 400
                    elif error_code == "upstream_429":
                        user_message = "❌ OpenAI rate limit reached. Please wait and try again."
                        status_code = 429
                    elif error_code == "timeout":
                        user_message = "❌ OpenAI request timed out. Please try again."
                        status_code = 504
                    else:
                        user_message = "❌ OpenAI request failed. Please try again."
                        status_code = 502
                    return build_ai_error_response(
                        status_code=status_code,
                        code=error_code,
                        message=error_str,
                        user_message=user_message,
                        system_state=system_state,
                        key_source=key_source
                    )
        
        if ai_response and not wants_code_response(content):
            stripped = ai_response.strip()
            if stripped.startswith("```") and stripped.endswith("```"):
                ai_response = stripped.strip("`").strip()

        # Save AI response
        ai_msg = {
            "user_id": user_id,
            "role": "assistant",
            "content": ai_response,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        await db.chat_messages_collection.insert_one(ai_msg)
        
        # Send real-time update
        await manager.send_message(user_id, {
            "type": "ai_chat_message",
            "message": ai_response
        })
        
        return {
            "success": True,
            "role": "assistant",
            "content": ai_response,
            "key_source": key_source if 'key_source' in locals() else None,
            "model_used": model_used if 'model_used' in locals() else None,
            "error": error_code,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "system_state": system_state
        }
    
    except Exception as e:
        logger.error(f"AI chat error: {e}")
        return build_ai_error_response(
            status_code=500,
            code="internal_error",
            message=str(e),
            user_message="❌ AI service encountered an unexpected error.",
            system_state=None
        )


@router.get("/chat/history")
async def get_chat_history(
    days: int = Query(30, ge=1, le=365, description="Number of days of history to retrieve"),
    limit: int = Query(100, ge=1, le=500, description="Maximum number of messages to return"),
    user_id: str = Depends(get_current_user)
):
    """Get chat history for authenticated user only
    
    Returns messages ordered newest-last (chronological order).
    Only returns messages for the authenticated user (namespaced by user_id).
    
    Args:
        days: Number of days of history (default 30, max 365)
        limit: Maximum messages to return (default 100, max 500)
        user_id: Authenticated user ID (from JWT token)
    
    Returns:
        messages: List of chat messages (chronological order)
        count: Number of messages returned
    """
    try:
        # Calculate cutoff date
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)
        
        # Query messages for this user only, within date range
        messages = await db.chat_messages_collection.find(
            {
                "user_id": user_id,
                "timestamp": {"$gte": cutoff_date.isoformat()}
            },
            {"_id": 0}
        ).sort("timestamp", -1).limit(limit).to_list(limit)
        
        # Reverse to get chronological order (newest-last)
        messages.reverse()
        
        return {
            "messages": messages,
            "count": len(messages),
            "days": days,
            "limit": limit,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    
    except Exception as e:
        logger.error(f"Get chat history error: {e}")
        # Return empty state instead of error to avoid frontend crashes
        return {
            "messages": [],
            "count": 0,
            "days": days,
            "limit": limit,
            "error": "Failed to load chat history",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }


@router.post("/chat/clear")
async def clear_chat_history_post(user_id: str = Depends(get_current_user)):
    """Clear chat history for authenticated user (POST endpoint for UI compatibility)
    
    Clears all chat messages for the authenticated user only.
    Returns success even if no messages found (idempotent operation).
    """
    try:
        result = await db.chat_messages_collection.delete_many({"user_id": user_id})
        
        logger.info(f"✅ Cleared {result.deleted_count} chat messages for user {user_id[:8]}")
        
        return {
            "success": True,
            "deleted_count": result.deleted_count,
            "message": f"Cleared {result.deleted_count} messages",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    
    except Exception as e:
        logger.error(f"Clear chat history error: {e}")
        raise HTTPException(status_code=500, detail="Failed to clear chat history")


@router.delete("/chat/history")
async def clear_chat_history(user_id: str = Depends(get_current_user)):
    """Clear chat history for authenticated user (DELETE endpoint for backward compatibility)
    
    Clears all chat messages for the authenticated user only.
    Returns success even if no messages found (idempotent operation).
    """
    try:
        result = await db.chat_messages_collection.delete_many({"user_id": user_id})
        
        logger.info(f"✅ Cleared {result.deleted_count} chat messages for user {user_id[:8]}")
        
        return {
            "success": True,
            "deleted_count": result.deleted_count,
            "message": f"Cleared {result.deleted_count} messages",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    
    except Exception as e:
        logger.error(f"Clear chat history error: {e}")
        raise HTTPException(status_code=500, detail="Failed to clear chat history")


@router.post("/chat/greeting")
async def get_daily_greeting(user_id: str = Depends(get_current_user)):
    """Generate daily greeting with performance report on fresh session
    
    This endpoint:
    - Checks if user already received greeting today
    - Uses full chat history for context
    - Generates personalized greeting with daily report
    - Includes portfolio status and bot performance
    """
    try:
        # Get user info
        user = await db.users_collection.find_one({"id": user_id}, {"_id": 0})
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        user_name = user.get("name", "User")
        
        # Check last greeting timestamp
        last_greeting = await db.chat_sessions_collection.find_one(
            {"user_id": user_id},
            {"_id": 0}
        )
        
        now = datetime.now(timezone.utc)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        
        # If already greeted today, return recent messages instead
        if last_greeting:
            last_greeting_time = datetime.fromisoformat(last_greeting.get("last_greeting_at", ""))
            if last_greeting_time >= today_start:
                # Already greeted today - return recent messages
                messages = await db.chat_messages_collection.find(
                    {"user_id": user_id},
                    {"_id": 0}
                ).sort("timestamp", -1).limit(10).to_list(10)
                messages.reverse()
                
                return {
                    "already_greeted": True,
                    "messages": messages,
                    "timestamp": now.isoformat()
                }
        
        # Get system state for context
        system_state = await action_router.get_system_state(user_id)
        
        # Get yesterday's performance from daily_report service
        try:
            from routes.daily_report import daily_report_service
            
            # Get yesterday's date range
            yesterday_start = (now - timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
            yesterday_end = yesterday_start + timedelta(days=1)
            
            # Get yesterday's trades
            trades = await db.trades_collection.find({
                "user_id": user_id,
                "created_at": {
                    "$gte": yesterday_start.isoformat(),
                    "$lt": yesterday_end.isoformat()
                }
            }).to_list(1000)
            
            total_trades = len(trades)
            winning_trades = len([t for t in trades if t.get("realized_profit", 0) > 0])
            net_profit = sum(t.get("realized_profit", 0) for t in trades) - sum(t.get("fees", 0) for t in trades)
            win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
            
            daily_summary = f"""Yesterday's Performance:
- Trades: {total_trades}
- Win Rate: {win_rate:.1f}%
- Net Profit: R{net_profit:.2f}
"""
        except Exception as e:
            logger.warning(f"Could not fetch yesterday's performance: {e}")
            daily_summary = "Performance data unavailable for yesterday."
        
        # Load full chat history for context (last 50 messages)
        history = await db.chat_messages_collection.find(
            {"user_id": user_id},
            {"_id": 0}
        ).sort("timestamp", -1).limit(50).to_list(50)
        history.reverse()
        
        # Get API key for OpenAI
        try:
            user_api_key, key_source = await resolve_openai_key(user_id)
            
            if not user_api_key:
                record_ai_error("no_api_key", "OpenAI API key not configured")
                return {
                    "role": "assistant",
                    "content": f"Good morning, {user_name}! 👋\n\nI'm your AI trading assistant, but I need an OpenAI API key to provide intelligent insights. Please save your API key in Settings → API Keys.\n\n{daily_summary}\n\nCurrent System:\n- Total Bots: {system_state['bots']['total']} (Active: {system_state['bots']['active']})\n- Total Capital: R{system_state['capital']['total']:.2f}\n- Total Profit: R{system_state['capital']['total_profit']:.2f}",
                    "timestamp": now.isoformat(),
                    "is_greeting": True,
                    "error": "no_api_key",
                    "key_source": key_source
                }
            
            # Generate greeting with OpenAI
            from openai import AsyncOpenAI
            
            client = AsyncOpenAI(api_key=user_api_key)
            
            # Prepare context
            context = f"""You are the AI assistant for Amarktai Network trading system. 

Generate a warm, personalized daily greeting for {user_name}. This is their first session today.

Include:
1. Friendly greeting with user's name
2. Yesterday's performance summary
3. Current portfolio status
4. Any notable alerts or recommendations
5. Encouragement and positive tone

System State:
- Total Bots: {system_state['bots']['total']} (Active: {system_state['bots']['active']}, Paused: {system_state['bots']['paused']})
- Total Capital: R{system_state['capital']['total']:.2f}
- Total Profit: R{system_state['capital']['total_profit']:.2f}

{daily_summary}

Keep it conversational, under 150 words. Use emojis sparingly."""
            
            # Try models with fallback
            fallback_models = ["gpt-4o-mini", "gpt-4.1-mini", "gpt-4o", "gpt-3.5-turbo"]
            greeting_content = None
            
            for model in fallback_models:
                try:
                    response = await client.chat.completions.create(
                        model=model,
                        messages=[
                            {"role": "system", "content": context},
                            {"role": "user", "content": f"Generate a daily greeting for {user_name}"}
                        ],
                        max_tokens=300,
                        temperature=0.8
                    )
                    greeting_content = response.choices[0].message.content
                    break
                except Exception as model_error:
                    if "404" in str(model_error) or "403" in str(model_error):
                        continue
                    else:
                        raise model_error
            
            if not greeting_content:
                # Fallback to simple greeting
                greeting_content = f"Good morning, {user_name}! 👋\n\n{daily_summary}\n\nYour system is running with {system_state['bots']['active']} active bots. How can I help you today?"
        
        except Exception as e:
            logger.error(f"OpenAI greeting generation error: {e}")
            error_str = str(e)
            if "401" in error_str or "invalid_api_key" in error_str.lower():
                record_ai_error("invalid_key", error_str)
            elif "429" in error_str:
                record_ai_error("upstream_429", error_str)
            else:
                record_ai_error("upstream_error", error_str)
            # Fallback greeting
            greeting_content = f"Good morning, {user_name}! 👋\n\n{daily_summary}\n\nCurrent System:\n- Total Bots: {system_state['bots']['total']} (Active: {system_state['bots']['active']})\n- Total Capital: R{system_state['capital']['total']:.2f}\n- Total Profit: R{system_state['capital']['total_profit']:.2f}\n\nHow can I assist you today?"
        
        # Save greeting message
        greeting_msg = {
            "user_id": user_id,
            "role": "assistant",
            "content": greeting_content,
            "timestamp": now.isoformat(),
            "is_greeting": True
        }
        await db.chat_messages_collection.insert_one(greeting_msg)
        
        # Update session record
        await db.chat_sessions_collection.update_one(
            {"user_id": user_id},
            {
                "$set": {
                    "last_greeting_at": now.isoformat(),
                    "last_session_start": now.isoformat()
                }
            },
            upsert=True
        )
        
        return {
            "role": "assistant",
            "content": greeting_content,
            "timestamp": now.isoformat(),
            "is_greeting": True,
            "system_state": system_state
        }
    
    except Exception as e:
        logger.error(f"Daily greeting error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/health")
async def ai_health(user_id: str = Depends(get_current_user)):
    """AI health check for current user."""
    try:
        key, key_source = await resolve_openai_key(user_id)
        primary_model = os.getenv("OPENAI_MODEL")
        fallback_model = os.getenv("OPENAI_FALLBACK_MODEL")
        model = primary_model or fallback_model or "gpt-4o-mini"
        return {
            "key_present": bool(key),
            "key_source": key_source if key else "none",
            "model": model,
            "last_error": last_ai_error
        }
    except Exception as e:
        logger.error(f"AI health error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/action/execute")
async def execute_ai_action(
    action_data: Dict = Body(...),
    user_id: str = Depends(get_current_user)
):
    """Execute an AI action directly (for frontend buttons)
    
    Body:
        {
            "action": "start_bot" | "pause_bot" | "stop_bot" | "emergency_stop" | "get_limits",
            "params": {"bot_id": "...", ...},
            "require_2fa": false  # if true, requires 2FA code
        }
    """
    try:
        action = action_data.get('action')
        params = action_data.get('params', {})
        require_2fa = action_data.get('require_2fa', False)
        
        # Check if 2FA is required
        if require_2fa:
            user = await db.users_collection.find_one({"id": user_id}, {"_id": 0})
            if user and user.get('two_factor_enabled'):
                otp_code = action_data.get('otp_code')
                if not otp_code:
                    return {
                        "success": False,
                        "error": "2FA code required",
                        "require_2fa": True
                    }
                
                # Verify 2FA
                import pyotp
                totp = pyotp.TOTP(user.get('two_factor_secret'))
                if not totp.verify(otp_code, valid_window=1):
                    return {
                        "success": False,
                        "error": "Invalid 2FA code"
                    }
        
        # Execute action
        result = await action_router.execute_action(action, params, user_id)
        
        # Log action
        logger.info(f"User {user_id[:8]} executed AI action: {action}")
        
        return result
    
    except Exception as e:
        logger.error(f"Execute AI action error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
