"""
AI Super Intelligence Chat Router
Real-time AI chat with action confirmation and tool routing
"""

from fastapi import APIRouter, HTTPException, Depends, Body, Query
from fastapi.responses import JSONResponse
import asyncio
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any, Tuple
import logging
import json
import os
from uuid import uuid4
import re

from auth import get_current_user
import database as db
from ai_super_brain import AISuperBrain
from engines.trade_budget_manager import trade_budget_manager
from websocket_manager import manager
from services.bot_runtime_state import bot_runtime_state
from realtime_events import rt_events
from engines.audit_logger import audit_logger

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/ai", tags=["AI Chat"])

ai_brain = AISuperBrain()

# Action confirmation tokens storage (legacy - DB-backed confirmations preferred)
confirmation_tokens = {}
CONFIRMATION_TTL_MINUTES = 15
UUID_PATTERN = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I)

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
        return {"action": "get_overview_snapshot"}
    if "performance" in content_lower and "summary" in content_lower:
        return {"action": "get_performance_summary"}
    if "system status" in content_lower or content_lower.strip() == "status":
        return {"action": "get_system_status"}
    if "risk" in content_lower and "reset" not in content_lower:
        return {"action": "get_risk_status"}
    if "admin tools" in content_lower or "open admin" in content_lower:
        return {"action": "open_admin_tools"}
    if "pause all" in content_lower and "bot" in content_lower:
        return {"action": "pause_all_bots"}
    if "resume all" in content_lower and "bot" in content_lower:
        return {"action": "resume_all_bots"}
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
        return {"action": "pause_autonomy_subsystem", "params": {"subsystem": "autopilot"}} if not enabled else {"action": "resume_autonomy_subsystem", "params": {"subsystem": "autopilot"}}
    if "live" in content_lower and ("switch" in content_lower or "enable" in content_lower):
        return {"action": "set_system_mode", "params": {"mode": "live"}}
    if "paper" in content_lower and ("switch" in content_lower or "enable" in content_lower):
        return {"action": "set_system_mode", "params": {"mode": "paper"}}
    if "transfer" in content_lower or "withdraw" in content_lower:
        return {"action": "transfer_funds"}

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
    """
    Resolve OpenAI API key using canonical priority.
    
    Uses the centralized resolver from services/openai_key_resolver.py
    to ensure consistent behavior across all AI features.
    """
    from services.openai_key_resolver import resolve_openai_key as canonical_resolver
    
    api_key, source = await canonical_resolver(user_id)
    
    # Log the resolution for debugging
    logger.info(f"AI Chat: OpenAI key resolved source={source} for user {user_id[:8] if user_id else 'system'}")
    
    return api_key, source


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
            "error_code": code,
            "message": message,
            "role": "assistant",
            "content": user_message,
            "reply": user_message,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "system_state": system_state,
            "key_source": key_source
        }
    )


def build_action_meta(action: Optional[str], tool_result: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not action:
        return {
            "action_attempted": False,
            "action_name": None,
            "action_result": None,
            "reason": None,
        }
    if not tool_result:
        return {
            "action_attempted": True,
            "action_name": action,
            "action_result": "failed",
            "reason": "Action result unavailable.",
        }
    if tool_result.get("requires_confirmation"):
        reason = tool_result.get("reply") or "Confirmation required."
        return {
            "action_attempted": True,
            "action_name": action,
            "action_result": "blocked",
            "reason": reason,
        }
    result_payload = tool_result.get("result") if isinstance(tool_result.get("result"), dict) else {}
    if isinstance(result_payload, dict) and "success" in result_payload:
        success_flag = result_payload.get("success")
    else:
        success_flag = tool_result.get("success")
    reason = tool_result.get("error") or result_payload.get("error") or result_payload.get("message")
    if success_flag:
        return {
            "action_attempted": True,
            "action_name": action,
            "action_result": "success",
            "reason": None,
        }
    reason_text = reason or "Action failed."
    lowered = reason_text.lower()
    blocked_keywords = ("blocked", "required", "not allowed", "permission", "confirm", "confirmation")
    action_result = "blocked" if any(word in lowered for word in blocked_keywords) else "failed"
    return {
        "action_attempted": True,
        "action_name": action,
        "action_result": action_result,
        "reason": reason_text,
    }


def resolve_action_reply(action: str, tool_result: Optional[Dict[str, Any]]) -> str:
    if not tool_result:
        return f"Action '{action}' failed."
    if tool_result.get("requires_confirmation"):
        return tool_result.get("reply") or "Confirmation required."
    result_payload = tool_result.get("result") if isinstance(tool_result.get("result"), dict) else {}
    reply = tool_result.get("reply") or result_payload.get("message") or tool_result.get("message")
    if isinstance(result_payload, dict) and "success" in result_payload:
        success_flag = result_payload.get("success")
    else:
        success_flag = tool_result.get("success")
    if success_flag:
        return reply or f"✅ {action.replace('_', ' ').title()} completed."
    reason = tool_result.get("error") or result_payload.get("error") or result_payload.get("message")
    if reason:
        return reason
    return reply or f"Action '{action}' failed."


async def generate_degraded_response(user_message: str, user_id: str, system_state: Dict) -> Dict[str, Any]:
    """
    Generate a basic response without OpenAI key by analyzing user intent
    and querying database directly for common information requests.
    
    Args:
        user_message: The user's chat message
        user_id: User ID for potential future personalization
        system_state: Current system state with bots, capital, modes, etc.
    
    Returns:
        Dict with response content, metadata, and degraded_mode flag
    """
    message_lower = user_message.lower()
    
    # Pattern matching for common queries
    response_parts = []
    
    # System status query
    if any(word in message_lower for word in ["status", "overview", "summary", "health", "how are things"]):
        bots_info = system_state.get("bots", {})
        capital_info = system_state.get("capital", {})
        modes = system_state.get("system_modes", {})
        
        response_parts.append("📊 **System Status**")
        response_parts.append(f"• Bots: {bots_info.get('total', 0)} total ({bots_info.get('active', 0)} active, {bots_info.get('paused', 0)} paused)")
        response_parts.append(f"• Capital: ${capital_info.get('total', 0):,.2f}")
        response_parts.append(f"• Total Profit: ${capital_info.get('total_profit', 0):,.2f}")
        response_parts.append(f"• Mode: {'Live Trading' if modes.get('liveTrading') else 'Paper Trading'}")
        response_parts.append(f"• Autopilot: {'Enabled' if modes.get('autopilot') else 'Disabled'}")
    
    # Wallet/balance query
    elif any(word in message_lower for word in ["wallet", "balance", "capital", "money", "funds"]):
        capital_info = system_state.get("capital", {})
        budget_status = system_state.get("budget_status", {})
        
        response_parts.append("💰 **Wallet Summary**")
        response_parts.append(f"• Total Capital: ${capital_info.get('total', 0):,.2f}")
        response_parts.append(f"• Total Profit/Loss: ${capital_info.get('total_profit', 0):,.2f}")
        
        if budget_status:
            response_parts.append("\n**Exchange Budgets:**")
            for exchange, data in budget_status.items():
                if isinstance(data, dict):
                    allocated = data.get('allocated', 0)
                    available = data.get('available', 0)
                    response_parts.append(f"• {exchange.title()}: ${allocated:,.2f} allocated, ${available:,.2f} available")
    
    # Bot query
    elif any(word in message_lower for word in ["bot", "trading bot", "bots"]):
        bots_info = system_state.get("bots", {})
        
        response_parts.append("🤖 **Bot Status**")
        response_parts.append(f"• Total Bots: {bots_info.get('total', 0)}")
        response_parts.append(f"• Active: {bots_info.get('active', 0)}")
        response_parts.append(f"• Paused: {bots_info.get('paused', 0)}")
        response_parts.append(f"• Stopped: {bots_info.get('stopped', 0)}")
    
    # Performance query
    elif any(word in message_lower for word in ["performance", "profit", "loss", "pnl", "trades"]):
        capital_info = system_state.get("capital", {})
        perf_info = system_state.get("recent_performance", {})
        
        response_parts.append("📈 **Performance Summary**")
        response_parts.append(f"• Total Profit/Loss: ${capital_info.get('total_profit', 0):,.2f}")
        response_parts.append(f"• Recent Trades: {perf_info.get('recent_trades_count', 0)}")
        response_parts.append(f"• Recent PnL: ${perf_info.get('recent_pnl', 0):,.2f}")
    
    # Autopilot query
    elif "autopilot" in message_lower:
        modes = system_state.get("system_modes", {})
        autopilot_enabled = modes.get("autopilot", False)
        
        response_parts.append("🚀 **Autopilot Status**")
        response_parts.append(f"• Status: {'✅ Enabled' if autopilot_enabled else '❌ Disabled'}")
        if autopilot_enabled:
            response_parts.append("• Autopilot is actively managing your trading strategies")
        else:
            response_parts.append("• Enable autopilot to allow AI-driven trading decisions")
    
    # Mode query (live/paper)
    elif any(word in message_lower for word in ["mode", "paper", "live", "trading mode"]):
        modes = system_state.get("system_modes", {})
        
        response_parts.append("⚙️ **Trading Mode**")
        if modes.get("liveTrading"):
            response_parts.append("• Mode: 🔴 **LIVE TRADING**")
            response_parts.append("• Real money is being used for trades")
        else:
            response_parts.append("• Mode: 📝 **PAPER TRADING**")
            response_parts.append("• Simulated trading with virtual funds")
    
    # Events query
    elif any(word in message_lower for word in ["event", "alert", "notification", "recent", "latest"]):
        perf_info = system_state.get("recent_performance", {})
        
        response_parts.append("📅 **Recent Events**")
        response_parts.append(f"• Recent Trades: {perf_info.get('recent_trades_count', 0)}")
        response_parts.append("• Check the Dashboard for detailed event history")
    
    # Learning/AI query
    elif any(word in message_lower for word in ["learn", "learning", "ai", "intelligence", "smart"]):
        response_parts.append("🧠 **AI Learning Status**")
        response_parts.append("• Basic system monitoring active")
        response_parts.append("• Advanced AI learning requires OpenAI key")
        response_parts.append("• Add API key in Settings → API Keys for full intelligence")
    
    # Generic/help query
    else:
        response_parts.append("👋 **AI Chat (Basic Mode)**")
        response_parts.append("\nI can help you with:")
        response_parts.append("• System status and overview")
        response_parts.append("• Wallet balance and capital")
        response_parts.append("• Bot status and management")
        response_parts.append("• Performance and trading results")
        response_parts.append("• Autopilot and trading mode info")
        response_parts.append("\nTry asking: 'show status' or 'what's my balance?'")
    
    # Add footer note about OpenAI key
    response_parts.append("\n---")
    response_parts.append("ℹ️ *Advanced intelligence requires OpenAI key - add in Settings → API Keys*")
    
    response_text = "\n".join(response_parts)
    
    return {
        "success": True,
        "role": "assistant",
        "content": response_text,
        "reply": response_text,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "system_state": system_state,
        "key_source": "degraded_mode",
        "degraded_mode": True,
        "action_meta": {
            "action_attempted": False,
            "action_name": None,
            "action_result": None,
            "reason": None
        }
    }


async def create_confirmation_record(
    user_id: str,
    action: str,
    params: Dict[str, Any],
    confirmation_phrase: Optional[str] = None,
    ttl_minutes: Optional[int] = None,
) -> Dict[str, Any]:
    ttl_minutes = ttl_minutes or CONFIRMATION_TTL_MINUTES
    confirmation_id = str(uuid4())
    created_at = datetime.now(timezone.utc)
    expires_at = created_at + timedelta(minutes=ttl_minutes)
    record = {
        "confirmation_id": confirmation_id,
        "user_id": user_id,
        "action": action,
        "params": params,
        "confirmation_phrase": confirmation_phrase,
        "status": "pending",
        "created_at": created_at.isoformat(),
        "expires_at": expires_at.isoformat(),
    }
    if db.chatops_confirmations_collection is not None:
        await db.chatops_confirmations_collection.insert_one(record)
    else:
        confirmation_tokens[confirmation_id] = record
    return record


async def get_confirmation_record(confirmation_id: str, user_id: str) -> Optional[Dict[str, Any]]:
    now = datetime.now(timezone.utc)
    record = None
    if db.chatops_confirmations_collection is not None:
        record = await db.chatops_confirmations_collection.find_one(
            {"confirmation_id": confirmation_id, "user_id": user_id, "status": "pending"},
            {"_id": 0},
        )
    else:
        record = confirmation_tokens.get(confirmation_id)
        if record and record.get("user_id") != user_id:
            record = None

    if not record:
        return None

    expires_at = record.get("expires_at")
    if expires_at:
        try:
            expiry = datetime.fromisoformat(str(expires_at).replace("Z", "+00:00"))
            if expiry < now:
                if db.chatops_confirmations_collection is not None:
                    await db.chatops_confirmations_collection.update_one(
                        {"confirmation_id": confirmation_id},
                        {"$set": {"status": "expired"}},
                    )
                else:
                    confirmation_tokens.pop(confirmation_id, None)
                return None
        except Exception:
            pass

    return record


async def mark_confirmation_used(confirmation_id: str):
    if db.chatops_confirmations_collection is not None:
        await db.chatops_confirmations_collection.update_one(
            {"confirmation_id": confirmation_id},
            {"$set": {"status": "used", "used_at": datetime.now(timezone.utc).isoformat()}},
        )
    else:
        confirmation_tokens.pop(confirmation_id, None)


async def build_ai_status(user_id: str) -> Dict[str, Any]:
    key, key_source = await resolve_openai_key(user_id)
    primary_model = os.getenv("OPENAI_MODEL") or os.getenv("OPENAI_FALLBACK_MODEL") or "gpt-4o-mini"
    memory_status = {"ok": False, "path": None}
    try:
        from ai_memory_manager import memory_manager
        memory_status = {
            "ok": memory_manager.archive_path.exists(),
            "path": str(memory_manager.archive_path),
        }
    except Exception:
        memory_status = {"ok": False, "path": None}

    next_cycle = None
    last_cycle = None
    try:
        from ai_scheduler import ai_scheduler
        last_cycle = ai_scheduler.last_run.isoformat() if ai_scheduler.last_run else None
        now = datetime.now(timezone.utc)
        target_time = datetime.combine(now.date(), datetime.min.time(), tzinfo=timezone.utc).replace(hour=2, minute=0)
        if now >= target_time:
            target_time = target_time + timedelta(days=1)
        next_cycle = target_time.isoformat()
    except Exception:
        pass

    return {
        "key_configured": bool(key),
        "key_source": key_source,
        "model": primary_model,
        "memory_manager": memory_status,
        "last_cycle": last_cycle,
        "next_cycle": next_cycle,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


async def build_grounded_context(user_id: str) -> Dict[str, Any]:
    from routes.system_status import get_system_status
    from routes.system_mode import get_mode
    from services.overview_service import overview_service
    from routes.bot_lifecycle import get_bots_status
    from routes.wallet_endpoints import build_paper_wallet_status_summary
    from routes.autonomy_control import get_autonomy_status
    from routes.learning_jobs import get_learning_status

    tasks = await asyncio.gather(
        get_system_status(user_id),
        get_mode(user_id),
        overview_service.get_snapshot(user_id),
        get_bots_status(user_id),
        build_paper_wallet_status_summary(user_id),
        get_autonomy_status(user_id),
        build_ai_status(user_id),
        get_learning_status(user_id),
        return_exceptions=True,
    )

    def safe(item, fallback=None):
        return fallback if isinstance(item, Exception) else item

    system_status = safe(tasks[0], {})
    system_mode = safe(tasks[1], {})
    overview = safe(tasks[2], {})
    bots_status = safe(tasks[3], {})
    wallet_status = safe(tasks[4], {})
    autonomy_status = safe(tasks[5], {})
    ai_status = safe(tasks[6], {})
    learning_status = safe(tasks[7], {})

    return {
        "system_status": system_status,
        "system_mode": system_mode,
        "overview": overview,
        "bots": bots_status.get("bots") or bots_status.get("data") or bots_status,
        "wallet": wallet_status,
        "autonomy": autonomy_status.get("subsystems") or autonomy_status,
        "ai": ai_status,
        "learning": learning_status,
    }


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
            "recent_pnl": round(sum(t.get('net_pnl', t.get('profit_loss', 0)) for t in recent_trades), 2)
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
                bot = await db.bots_collection.find_one({"id": bot_id, "user_id": user_id}, {"_id": 0})
                if not bot:
                    return {"success": False, "action": "start_bot", "error": "Bot not found", "bot_id": bot_id}
                runtime_before = await bot_runtime_state.ensure_state(bot)
                result = await db.bots_collection.update_one(
                    {"id": bot_id, "user_id": user_id},
                    {"$set": {"status": "active"}}
                )
                await bot_runtime_state.set_state(bot_id, user_id, "active", source="ai")
                verified = await bot_runtime_state.get_state(bot_id)
                await rt_events.bot_state_changed(
                    user_id,
                    bot_id,
                    (runtime_before or {}).get("state", bot.get("status", "unknown")),
                    "active"
                )
                await audit_logger.log_bot_action("started", user_id, bot_id, bot.get("name", "bot"))
                return {
                    "success": result.modified_count > 0,
                    "action": "start_bot",
                    "bot_id": bot_id,
                    "verified_state": verified,
                }
            
            elif action == "pause_bot":
                bot_id = params.get('bot_id')
                reason = params.get('reason', 'AI recommendation')
                bot = await db.bots_collection.find_one({"id": bot_id, "user_id": user_id}, {"_id": 0})
                if not bot:
                    return {"success": False, "action": "pause_bot", "error": "Bot not found", "bot_id": bot_id}
                runtime_before = await bot_runtime_state.ensure_state(bot)
                result = await db.bots_collection.update_one(
                    {"id": bot_id, "user_id": user_id},
                    {"$set": {
                        "status": "paused",
                        "pause_reason": reason,
                        "paused_by_system": True
                    }}
                )
                await bot_runtime_state.set_state(bot_id, user_id, "paused", reason=reason, source="ai")
                verified = await bot_runtime_state.get_state(bot_id)
                await rt_events.bot_state_changed(
                    user_id,
                    bot_id,
                    (runtime_before or {}).get("state", bot.get("status", "unknown")),
                    "paused",
                    reason
                )
                await audit_logger.log_bot_action("paused", user_id, bot_id, bot.get("name", "bot"), {"reason": reason})
                return {
                    "success": result.modified_count > 0,
                    "action": "pause_bot",
                    "bot_id": bot_id,
                    "verified_state": verified,
                }
            
            elif action == "stop_bot":
                bot_id = params.get('bot_id')
                bot = await db.bots_collection.find_one({"id": bot_id, "user_id": user_id}, {"_id": 0})
                if not bot:
                    return {"success": False, "action": "stop_bot", "error": "Bot not found", "bot_id": bot_id}
                runtime_before = await bot_runtime_state.ensure_state(bot)
                result = await db.bots_collection.update_one(
                    {"id": bot_id, "user_id": user_id},
                    {"$set": {"status": "stopped"}}
                )
                await bot_runtime_state.set_state(bot_id, user_id, "stopped", source="ai")
                verified = await bot_runtime_state.get_state(bot_id)
                await rt_events.bot_state_changed(
                    user_id,
                    bot_id,
                    (runtime_before or {}).get("state", bot.get("status", "unknown")),
                    "stopped"
                )
                await audit_logger.log_bot_action("stopped", user_id, bot_id, bot.get("name", "bot"))
                return {
                    "success": result.modified_count > 0,
                    "action": "stop_bot",
                    "bot_id": bot_id,
                    "verified_state": verified,
                }

            elif action == "resume_bot":
                bot_id = params.get('bot_id')
                bot = await db.bots_collection.find_one({"id": bot_id, "user_id": user_id}, {"_id": 0})
                if not bot:
                    return {"success": False, "action": "resume_bot", "error": "Bot not found", "bot_id": bot_id}
                runtime_before = await bot_runtime_state.ensure_state(bot)
                result = await db.bots_collection.update_one(
                    {"id": bot_id, "user_id": user_id},
                    {"$set": {"status": "active"}}
                )
                await bot_runtime_state.set_state(bot_id, user_id, "active", source="ai")
                verified = await bot_runtime_state.get_state(bot_id)
                await rt_events.bot_state_changed(
                    user_id,
                    bot_id,
                    (runtime_before or {}).get("state", bot.get("status", "unknown")),
                    "active"
                )
                await audit_logger.log_bot_action("resumed", user_id, bot_id, bot.get("name", "bot"))
                return {
                    "success": result.modified_count > 0,
                    "action": "resume_bot",
                    "bot_id": bot_id,
                    "verified_state": verified,
                }
            
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
                await rt_events.system_mode_changed(user_id, "emergencyStop", True)
                await audit_logger.log_system_mode_change(user_id, "emergencyStop", True, "AI emergency stop")
                return {"success": True, "action": "emergency_stop"}

            elif action == "toggle_autopilot":
                enabled = bool(params.get("enabled", False))
                await db.system_modes_collection.update_one(
                    {"user_id": user_id},
                    {"$set": {"autopilot": enabled}},
                    upsert=True
                )
                await rt_events.system_mode_changed(user_id, "autopilot", enabled)
                await audit_logger.log_system_mode_change(user_id, "autopilot", enabled, "AI autopilot toggle")
                return {"success": True, "action": "toggle_autopilot", "enabled": enabled}

            elif action == "switch_mode":
                from routes.system_mode import set_system_mode
                mode = params.get("mode")
                if mode not in ["paper", "live", "autopilot"]:
                    return {"success": False, "error": "Invalid mode"}
                await set_system_mode(mode, user_id)
                await rt_events.system_mode_changed(user_id, "mode", True)
                await audit_logger.log_system_mode_change(user_id, "mode", True, f"AI switch to {mode}")
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
                    await rt_events.lock_reset(user_id, "daily_loss")
                except Exception:
                    pass
                await audit_logger.log_event(
                    "risk_lock_reset",
                    user_id,
                    {"lock_type": "daily_loss", "source": "ai"},
                )
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

            elif action == "fetch_status":
                state = await AIActionRouter.get_system_state(user_id)
                return {"success": True, "action": "fetch_status", "data": state}

            elif action == "fetch_overview":
                from services.overview_service import overview_service
                overview = await overview_service.get_snapshot(user_id)
                return {"success": True, "action": "fetch_overview", "data": overview}

            elif action == "fetch_performance":
                summary = await build_recent_summary(user_id)
                return {"success": True, "action": "fetch_performance", "data": summary}

            elif action == "fetch_risk":
                user = await db.users_collection.find_one({"id": user_id}, {"_id": 0})
                return {
                    "success": True,
                    "action": "fetch_risk",
                    "data": {
                        "daily_loss_lock_active": bool((user or {}).get("daily_loss_lock_active", False)),
                        "daily_loss_locked_reason": (user or {}).get("daily_loss_locked_reason"),
                    },
                }

            elif action == "open_admin_tools":
                user = await db.users_collection.find_one({"id": user_id}, {"_id": 0, "is_admin": 1})
                if not user or not user.get("is_admin"):
                    return {"success": False, "action": "open_admin_tools", "error": "Admin access required"}
                return {"success": True, "action": "open_admin_tools", "message": "Admin tools unlocked"}
            
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


MAX_TRANSFER_AMOUNT = float(os.getenv("CHAT_MAX_TRANSFER_AMOUNT", "10000"))


async def _is_admin_user(user_id: str) -> bool:
    user = await db.users_collection.find_one({"id": user_id}, {"_id": 0, "is_admin": 1})
    return bool(user and user.get("is_admin"))


async def _handle_get_system_status(user_id: str, params: Dict[str, Any]) -> Dict[str, Any]:
    from routes.system_status import get_system_status
    data = await get_system_status(user_id)
    return {"success": True, "data": data, "message": "System status retrieved."}


async def _handle_get_system_mode(user_id: str, params: Dict[str, Any]) -> Dict[str, Any]:
    from routes.system_mode import get_mode
    data = await get_mode(user_id)
    return {"success": True, "data": data, "message": "System mode retrieved."}


async def _handle_get_overview_snapshot(user_id: str, params: Dict[str, Any]) -> Dict[str, Any]:
    from services.overview_service import overview_service
    data = await overview_service.get_snapshot(user_id)
    return {"success": True, "data": data, "message": "Overview snapshot retrieved."}


async def _handle_get_performance_summary(user_id: str, params: Dict[str, Any]) -> Dict[str, Any]:
    data = await build_recent_summary(user_id)
    return {"success": True, "data": data, "message": "Performance summary retrieved."}


async def _handle_get_risk_status(user_id: str, params: Dict[str, Any]) -> Dict[str, Any]:
    from routes.risk_management import get_risk_status
    data = await get_risk_status(user_id)
    return {"success": True, "data": data, "message": "Risk status retrieved."}


async def _handle_set_system_mode(user_id: str, params: Dict[str, Any]) -> Dict[str, Any]:
    from routes.system_mode import switch_mode, ModeSwitchRequest
    mode = (params.get("mode") or "").lower()
    if mode not in {"paper", "live", "autopilot"}:
        return {"success": False, "error": "Invalid mode. Use paper, live, or autopilot."}
    confirmation_token = CONFIRM_LIVE_TRADING if mode == "live" else None
    data = await switch_mode(ModeSwitchRequest(mode=mode, confirmation_token=confirmation_token), user_id)
    return {"success": True, "data": data, "message": f"System mode switched to {mode}."}


async def _handle_list_bots(user_id: str, params: Dict[str, Any]) -> Dict[str, Any]:
    from routes.bot_lifecycle import get_bots_status
    data = await get_bots_status(user_id)
    return {"success": True, "data": data, "message": "Bots status retrieved."}


async def _handle_open_admin_tools(user_id: str, params: Dict[str, Any]) -> Dict[str, Any]:
    data = await action_router.execute_action("open_admin_tools", params, user_id)
    return {"success": data.get("success", False), "data": data, "message": data.get("message")}


async def _handle_create_bot(user_id: str, params: Dict[str, Any]) -> Dict[str, Any]:
    from models import BotCreate, BotRiskMode, TradingMode
    from server import create_bot

    exchange = params.get("exchange") or params.get("platform")
    name = params.get("name") or params.get("bot_name")
    risk_mode = params.get("risk_mode") or params.get("mode") or "balanced"
    if not name or not exchange:
        return {"success": False, "error": "Bot name and exchange are required."}

    mode = params.get("trading_mode")
    if mode:
        trading_mode = TradingMode(mode)
    else:
        trading_mode = TradingMode.PAPER

    bot = BotCreate(
        name=name,
        exchange=exchange,
        risk_mode=BotRiskMode(risk_mode),
        trading_mode=trading_mode,
        initial_capital=float(params.get("initial_capital", 0) or 0),
        strategy_preset=params.get("strategy_preset"),
    )
    data = await create_bot(bot, user_id)
    return {"success": True, "data": data, "message": f"Bot '{name}' created."}


async def _handle_pause_bot(user_id: str, params: Dict[str, Any]) -> Dict[str, Any]:
    data = await action_router.execute_action("pause_bot", params, user_id)
    return {"success": data.get("success", False), "data": data, "message": "Bot pause requested."}


async def _handle_resume_bot(user_id: str, params: Dict[str, Any]) -> Dict[str, Any]:
    data = await action_router.execute_action("resume_bot", params, user_id)
    return {"success": data.get("success", False), "data": data, "message": "Bot resume requested."}


async def _handle_stop_bot(user_id: str, params: Dict[str, Any]) -> Dict[str, Any]:
    data = await action_router.execute_action("stop_bot", params, user_id)
    return {"success": data.get("success", False), "data": data, "message": "Bot stop requested."}


async def _handle_pause_all_bots(user_id: str, params: Dict[str, Any]) -> Dict[str, Any]:
    from routes.bot_lifecycle import pause_all_bots
    data = await pause_all_bots(params or {}, user_id)
    return {"success": data.get("success", False), "data": data, "message": data.get("message", "Paused all bots.")}


async def _handle_resume_all_bots(user_id: str, params: Dict[str, Any]) -> Dict[str, Any]:
    from routes.risk_management import resume_all_bots_with_risk_check
    data = await resume_all_bots_with_risk_check(bool(params.get("force", False)), user_id)
    return {"success": True, "data": data, "message": "Resume all bots requested."}


async def _handle_get_wallet_status(user_id: str, params: Dict[str, Any]) -> Dict[str, Any]:
    from services.wallet_summary_service import wallet_summary_service
    data = await wallet_summary_service.get_summary(user_id)
    return {"success": True, "data": data, "message": "Wallet status retrieved."}


async def _handle_transfer_funds(user_id: str, params: Dict[str, Any]) -> Dict[str, Any]:
    from services.transfer_state_machine import TransferStateMachine
    from services.system_mode_service import system_mode_service

    amount = float(params.get("amount", 0) or 0)
    if amount <= 0:
        return {"success": False, "error": "Transfer amount must be greater than zero."}
    if amount > MAX_TRANSFER_AMOUNT:
        return {"success": False, "error": f"Transfer amount exceeds limit of {MAX_TRANSFER_AMOUNT}."}

    mode = await system_mode_service.get_current_mode(user_id)
    if mode != "live":
        return {"success": False, "error": "Transfers are blocked while in paper mode."}

    if not await _is_admin_user(user_id):
        return {"success": False, "error": "Admin privileges required for transfers."}

    transfer_machine = TransferStateMachine()
    result = await transfer_machine.request_transfer(
        user_id=user_id,
        from_exchange=params.get("from_exchange"),
        to_exchange=params.get("to_exchange"),
        currency=params.get("currency"),
        amount=amount,
        idempotency_key=params.get("idempotency_key"),
    )
    return {"success": True, "data": result, "message": "Transfer requested."}


async def _handle_get_autonomy_status(user_id: str, params: Dict[str, Any]) -> Dict[str, Any]:
    from routes.autonomy_control import get_autonomy_status
    data = await get_autonomy_status(user_id)
    return {"success": True, "data": data, "message": "Autonomy status retrieved."}


async def _handle_pause_autonomy(user_id: str, params: Dict[str, Any]) -> Dict[str, Any]:
    from routes.autonomy_control import pause_autonomy, AutonomyControlRequest, CONFIRM_PAUSE
    subsystem = params.get("subsystem") or "all"
    data = await pause_autonomy(AutonomyControlRequest(subsystem=subsystem, confirmation_phrase=CONFIRM_PAUSE), user_id)
    return {"success": True, "data": data, "message": "Autonomy pause requested."}


async def _handle_resume_autonomy(user_id: str, params: Dict[str, Any]) -> Dict[str, Any]:
    from routes.autonomy_control import resume_autonomy, AutonomyControlRequest, CONFIRM_RESUME
    subsystem = params.get("subsystem") or "all"
    data = await resume_autonomy(AutonomyControlRequest(subsystem=subsystem, confirmation_phrase=CONFIRM_RESUME), user_id)
    return {"success": True, "data": data, "message": "Autonomy resume requested."}


async def _handle_run_autonomy_cycle(user_id: str, params: Dict[str, Any]) -> Dict[str, Any]:
    from routes.autonomy_control import run_autonomy_now, AutonomyRunRequest, CONFIRM_RUN
    allow_live = bool(params.get("allow_live", False))
    data = await run_autonomy_now(AutonomyRunRequest(confirmation_phrase=CONFIRM_RUN, allow_live=allow_live), user_id)
    return {"success": True, "data": data, "message": "Autonomy cycle triggered."}


async def _handle_get_bodyguard_status(user_id: str, params: Dict[str, Any]) -> Dict[str, Any]:
    from routes.risk_management import get_risk_status
    data = await get_risk_status(user_id)
    return {"success": True, "data": data.get("bodyguard_lock") if isinstance(data, dict) else data}


async def _handle_set_risk_mode(user_id: str, params: Dict[str, Any]) -> Dict[str, Any]:
    risk_mode = (params.get("risk_mode") or params.get("mode") or "").lower()
    if risk_mode not in {"safe", "balanced", "risky", "aggressive"}:
        return {"success": False, "error": "Risk mode must be safe, balanced, risky, or aggressive."}
    await db.users_collection.update_one(
        {"id": user_id},
        {"$set": {"risk_profile": risk_mode}},
    )
    bot_id = params.get("bot_id")
    if bot_id:
        await db.bots_collection.update_one(
            {"id": bot_id, "user_id": user_id},
            {"$set": {"risk_mode": risk_mode}},
        )
    return {"success": True, "message": f"Risk mode set to {risk_mode}."}


async def _handle_get_learning_status(user_id: str, params: Dict[str, Any]) -> Dict[str, Any]:
    from routes.learning_jobs import get_learning_status
    data = await get_learning_status(user_id)
    return {"success": True, "data": data, "message": "Learning status retrieved."}


async def _handle_enable_learning(user_id: str, params: Dict[str, Any]) -> Dict[str, Any]:
    if os.getenv("ENABLE_LEARNING_LOOP", "false").lower() != "true":
        return {
            "success": False,
            "error": "Learning loop disabled (ENABLE_LEARNING_LOOP=false). Set ENABLE_LEARNING_LOOP=true and retry with admin confirmation."
        }
    if not await _is_admin_user(user_id):
        return {"success": False, "error": "Admin access required to enable learning loop."}
    await learning_loop.start()
    from services.autonomy_state import autonomy_state
    autonomy_state.set_paused("learning_loop", False)
    return {"success": True, "message": "Learning loop enabled."}


async def _handle_disable_learning(user_id: str, params: Dict[str, Any]) -> Dict[str, Any]:
    if not await _is_admin_user(user_id):
        return {"success": False, "error": "Admin access required to disable learning loop."}
    learning_loop.stop()
    from services.autonomy_state import autonomy_state
    autonomy_state.set_paused("learning_loop", True)
    return {"success": True, "message": "Learning loop disabled."}


async def _handle_diagnostics_realtime(user_id: str, params: Dict[str, Any]) -> Dict[str, Any]:
    from routes.diagnostics import get_realtime_status
    data = await get_realtime_status(user_id)
    return {"success": True, "data": data, "message": "Realtime diagnostics retrieved."}


async def _handle_report_last_errors(user_id: str, params: Dict[str, Any]) -> Dict[str, Any]:
    from autopilot_engine import autopilot as autopilot_engine
    from services.autonomy_heartbeat import heartbeat_registry

    heartbeats = heartbeat_registry.snapshot()
    errors = []
    if last_ai_error:
        errors.append({"source": "ai_chat", **last_ai_error})
    if autopilot_engine.last_error:
        errors.append({"source": "autopilot", "message": autopilot_engine.last_error})
    for subsystem, heartbeat in heartbeats.items():
        if heartbeat.get("last_error_message"):
            errors.append({
                "source": subsystem,
                "message": heartbeat.get("last_error_message"),
                "timestamp": heartbeat.get("last_error_at"),
            })
    return {"success": True, "data": errors, "message": "Last error summary retrieved."}


ACTION_REGISTRY = {
    "get_system_status": {
        "description": "Fetch system status and health summary.",
        "params": [],
        "requires_confirmation": False,
        "handler": _handle_get_system_status,
    },
    "get_system_mode": {
        "description": "Fetch current system mode (paper/live/autopilot).",
        "params": [],
        "requires_confirmation": False,
        "handler": _handle_get_system_mode,
    },
    "get_overview_snapshot": {
        "description": "Get overview snapshot metrics.",
        "params": [],
        "requires_confirmation": False,
        "handler": _handle_get_overview_snapshot,
    },
    "get_performance_summary": {
        "description": "Get recent performance summary.",
        "params": [],
        "requires_confirmation": False,
        "handler": _handle_get_performance_summary,
    },
    "get_risk_status": {
        "description": "Get current risk status and locks.",
        "params": [],
        "requires_confirmation": False,
        "handler": _handle_get_risk_status,
    },
    "set_system_mode": {
        "description": "Switch system mode (paper/live/autopilot).",
        "params": ["mode"],
        "requires_confirmation": True,
        "confirmation_phrase": CONFIRM_LIVE_TRADING,
        "handler": _handle_set_system_mode,
    },
    "list_bots": {
        "description": "List bots and status summary.",
        "params": [],
        "requires_confirmation": False,
        "handler": _handle_list_bots,
    },
    "open_admin_tools": {
        "description": "Unlock admin tools for current session.",
        "params": [],
        "requires_confirmation": False,
        "handler": _handle_open_admin_tools,
    },
    "create_bot": {
        "description": "Create a new bot.",
        "params": ["name", "exchange", "risk_mode", "initial_capital"],
        "requires_confirmation": False,
        "handler": _handle_create_bot,
    },
    "pause_bot": {
        "description": "Pause a bot.",
        "params": ["bot_id", "reason"],
        "requires_confirmation": True,
        "handler": _handle_pause_bot,
    },
    "resume_bot": {
        "description": "Resume a bot.",
        "params": ["bot_id"],
        "requires_confirmation": True,
        "handler": _handle_resume_bot,
    },
    "stop_bot": {
        "description": "Stop a bot.",
        "params": ["bot_id"],
        "requires_confirmation": True,
        "handler": _handle_stop_bot,
    },
    "pause_all_bots": {
        "description": "Pause all bots.",
        "params": ["reason"],
        "requires_confirmation": True,
        "handler": _handle_pause_all_bots,
    },
    "resume_all_bots": {
        "description": "Resume all bots with risk checks.",
        "params": ["force"],
        "requires_confirmation": True,
        "handler": _handle_resume_all_bots,
    },
    "get_wallet_status": {
        "description": "Get wallet summary and funding status.",
        "params": [],
        "requires_confirmation": False,
        "handler": _handle_get_wallet_status,
    },
    "transfer_funds": {
        "description": "Request a transfer between exchanges.",
        "params": ["from_exchange", "to_exchange", "currency", "amount"],
        "requires_confirmation": True,
        "confirmation_phrase": CONFIRM_TRANSFER,
        "handler": _handle_transfer_funds,
    },
    "get_autonomy_status": {
        "description": "Get autonomy subsystem status.",
        "params": [],
        "requires_confirmation": False,
        "handler": _handle_get_autonomy_status,
    },
    "pause_autonomy_subsystem": {
        "description": "Pause autonomy subsystem.",
        "params": ["subsystem"],
        "requires_confirmation": True,
        "confirmation_phrase": "CONFIRM AUTONOMY PAUSE",
        "handler": _handle_pause_autonomy,
    },
    "resume_autonomy_subsystem": {
        "description": "Resume autonomy subsystem.",
        "params": ["subsystem"],
        "requires_confirmation": True,
        "confirmation_phrase": "CONFIRM AUTONOMY RESUME",
        "handler": _handle_resume_autonomy,
    },
    "run_autonomy_cycle_now": {
        "description": "Trigger an autonomy cycle immediately.",
        "params": ["allow_live"],
        "requires_confirmation": True,
        "confirmation_phrase": "CONFIRM AUTONOMY RUN",
        "handler": _handle_run_autonomy_cycle,
    },
    "get_bodyguard_status": {
        "description": "Get bodyguard lock status.",
        "params": [],
        "requires_confirmation": False,
        "handler": _handle_get_bodyguard_status,
    },
    "set_risk_mode": {
        "description": "Set user or bot risk mode.",
        "params": ["risk_mode", "bot_id"],
        "requires_confirmation": False,
        "handler": _handle_set_risk_mode,
    },
    "get_learning_status": {
        "description": "Get learning loop status.",
        "params": [],
        "requires_confirmation": False,
        "handler": _handle_get_learning_status,
    },
    "enable_learning_loop": {
        "description": "Enable learning loop scheduler.",
        "params": [],
        "requires_confirmation": True,
        "handler": _handle_enable_learning,
    },
    "disable_learning_loop": {
        "description": "Disable learning loop scheduler.",
        "params": [],
        "requires_confirmation": True,
        "handler": _handle_disable_learning,
    },
    "diagnostics_realtime": {
        "description": "Get realtime diagnostics summary.",
        "params": [],
        "requires_confirmation": False,
        "handler": _handle_diagnostics_realtime,
    },
    "report_last_errors": {
        "description": "Report last known system errors.",
        "params": [],
        "requires_confirmation": False,
        "handler": _handle_report_last_errors,
    },
}


def get_tool_catalog() -> List[Dict[str, Any]]:
    return [
        {
            "name": name,
            "description": tool["description"],
            "params": tool.get("params", []),
            "requires_confirmation": tool.get("requires_confirmation", False),
        }
        for name, tool in ACTION_REGISTRY.items()
    ]


async def execute_tool_action(
    action: str,
    params: Dict[str, Any],
    user_id: str,
    *,
    from_confirmation: bool = False,
) -> Dict[str, Any]:
    tool = ACTION_REGISTRY.get(action)
    if not tool:
        return {"success": False, "error": f"Unknown action: {action}"}

    if tool.get("admin_only") and not await _is_admin_user(user_id):
        return {"success": False, "error": "Admin access required."}

    requires_confirmation = tool.get("requires_confirmation", False)
    confirmation_phrase = tool.get("confirmation_phrase")
    if requires_confirmation and not from_confirmation:
        record = await create_confirmation_record(
            user_id,
            action,
            params,
            confirmation_phrase=confirmation_phrase,
        )
        message = tool.get("confirmation_message") or (
            f"Confirmation required. Reply with confirmation_id {record['confirmation_id']}" +
            (f" and phrase: {record['confirmation_phrase']}" if record.get("confirmation_phrase") else "")
        )
        return {
            "success": False,
            "requires_confirmation": True,
            "confirmation_id": record["confirmation_id"],
            "reply": message,
        }

    try:
        result = await tool["handler"](user_id, params)
        return {"success": True, "result": result, "reply": result.get("message") or "Action completed."}
    except HTTPException as exc:
        return {"success": False, "error": exc.detail}
    except Exception as exc:
        logger.error("Tool action error (%s): %s", action, exc)
        return {"success": False, "error": str(exc)}


def parse_tool_payload(payload: str) -> Tuple[Optional[str], Optional[Dict[str, Any]], Optional[str], Optional[List[Dict[str, Any]]]]:
    candidate = payload.strip()
    if candidate.startswith("```") and candidate.endswith("```"):
        candidate = candidate.strip("`").strip()
    if not (candidate.startswith("{") and candidate.endswith("}")):
        return None, None, None, None
    tool_payload = json.loads(candidate)
    reply = tool_payload.get("reply") or tool_payload.get("response") or tool_payload.get("content")
    if "tool_call" in tool_payload:
        tool_call = tool_payload.get("tool_call") or {}
        return tool_call.get("name") or tool_call.get("action"), tool_call.get("params", {}), reply, None
    if "action" in tool_payload:
        return tool_payload.get("action"), tool_payload.get("params", {}), reply, None
    tool_actions = tool_payload.get("tool_actions") or tool_payload.get("actions")
    if isinstance(tool_actions, list):
        return None, None, reply, tool_actions
    return None, None, reply, None


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
        confirmation_token = message.get('confirmation_token') or message.get('confirmation_id')
        confirmation_phrase = message.get("confirmation_phrase") or ""
        log_only = bool(message.get("log_only"))
        user_tag = user_id[:8] if user_id else "unknown"
        logger.info(
            "AI chat request user=%s message_length=%d request_action=%s",
            user_tag,
            len(content or ""),
            request_action
        )

        if not confirmation_token and content:
            match = UUID_PATTERN.search(content)
            if match:
                confirmation_token = match.group(0)

        if log_only:
            if content:
                await db.chat_messages_collection.insert_one({
                    "user_id": user_id,
                    "role": message.get("role", "user"),
                    "content": content,
                    "metadata": message.get("metadata") or {},
                    "timestamp": datetime.now(timezone.utc).isoformat()
                })
            return {
                "success": True,
                "reply": "Message logged.",
                "logged": True,
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        
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
        grounded_context = await build_grounded_context(user_id)
        
        # Load full chat history for context (last 30 messages)
        chat_history = await db.chat_messages_collection.find(
            {"user_id": user_id},
            {"_id": 0}
        ).sort("timestamp", -1).limit(30).to_list(30)
        chat_history.reverse()

        # Load per-user memory and update with latest 7-day summary
        memory = await get_user_memory(user_id)
        recent_summary = await build_recent_summary(user_id)
        user_doc = await db.users_collection.find_one(
            {"id": user_id},
            {"_id": 0, "risk_profile": 1, "first_name": 1, "last_name": 1, "email": 1, "username": 1}
        )
        risk_profile = (user_doc or {}).get("risk_profile") or memory.get("risk_profile") or "balanced"
        first_name = (user_doc or {}).get("first_name") or ""
        last_name = (user_doc or {}).get("last_name") or ""
        username = (user_doc or {}).get("username") or ""
        email = (user_doc or {}).get("email") or ""
        if first_name and last_name:
            display_name = f"{first_name} {last_name}".strip()
        else:
            display_name = first_name or username or email or "Trader"
        await update_user_memory(user_id, {
            "risk_profile": risk_profile,
            "last_7d_summary": recent_summary
        })
        memory = await get_user_memory(user_id)

        tool_actions: List[Dict[str, Any]] = []
        action_results: List[Dict[str, Any]] = []
        requires_confirmation = False
        confirmation_id = None
        handled_action = False
        action_meta = build_action_meta(None, None)
        action_success = False

        if confirmation_token:
            handled_action = True
            record = await get_confirmation_record(confirmation_token, user_id)
            if record:
                required_phrase = record.get("confirmation_phrase")
                phrase_source = confirmation_phrase or content
                if required_phrase and required_phrase.upper() not in phrase_source.upper():
                    ai_response = f"Please confirm by typing the exact phrase: {required_phrase}."
                    requires_confirmation = True
                    confirmation_id = record.get("confirmation_id")
                    action_meta = build_action_meta(record.get("action"), {"requires_confirmation": True, "reply": ai_response})
                else:
                    tool_actions.append({
                        "action": record["action"],
                        "params": record.get("params", {}),
                        "source": "confirmation"
                    })
                    tool_result = await execute_tool_action(
                        record["action"],
                        record.get("params", {}),
                        user_id,
                        from_confirmation=True,
                    )
                    await mark_confirmation_used(record["confirmation_id"])
                    action_results.append(tool_result.get("result", tool_result))
                    action_meta = build_action_meta(record["action"], tool_result)
                    ai_response = resolve_action_reply(record["action"], tool_result)
                    if action_meta.get("action_result") == "success":
                        action_success = True
                    await log_chatops_action(user_id, record["action"], record.get("params", {}), tool_result)
                    await update_user_memory(user_id, {
                        "last_commands": (memory.get("last_commands", []) + [record["action"]])[-5:]
                    })
                    await manager.send_message(user_id, {
                        "type": "ai_action_executed",
                        "action": record["action"],
                        "result": tool_result
                    })
            else:
                ai_response = "Invalid or expired confirmation token."
        else:
            action_request = detect_action_intent(content, request_action)
            if action_request:
                action = action_request["action"]
                params = action_request.get("params", {}) or {}
                if action == "transfer_funds":
                    params = {**params, **parse_transfer_params(content)}
                if action in ["pause_bot", "resume_bot", "stop_bot"] and not params.get("bot_id"):
                    bot = await find_bot_match(user_id, content)
                    if not bot:
                        ai_response = "Please specify the bot name you want to control."
                        handled_action = True
                    else:
                        params["bot_id"] = bot.get("id")
                if action in ACTION_REGISTRY:
                    handled_action = True
                    tool_actions.append({"action": action, "params": params, "source": "chat"})
                    tool_result = await execute_tool_action(action, params, user_id)
                    action_meta = build_action_meta(action, tool_result)
                    ai_response = resolve_action_reply(action, tool_result)
                    if tool_result.get("requires_confirmation"):
                        requires_confirmation = True
                        confirmation_id = tool_result.get("confirmation_id")
                    else:
                        action_results.append(tool_result.get("result", tool_result))
                        if action_meta.get("action_result") == "success":
                            action_success = True
                    await log_chatops_action(user_id, action, params, tool_result)
                    await update_user_memory(user_id, {
                        "last_commands": (memory.get("last_commands", []) + [action])[-5:]
                    })

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
                    
                    # CRITICAL: Never block if key is missing - use degraded mode instead
                    # The resolver will have already fallen back to system key
                    if not user_api_key:
                        # Use degraded mode - provide basic responses without OpenAI
                        logger.info(f"AI Chat: Using degraded mode (no OpenAI key) for user {user_tag}")
                        degraded_response = await generate_degraded_response(content, user_id, system_state)
                        
                        # Store assistant response in chat history
                        assistant_msg = {
                            "user_id": user_id,
                            "role": "assistant",
                            "content": degraded_response["content"],
                            "timestamp": degraded_response["timestamp"],
                            "key_source": "degraded_mode"
                        }
                        await db.chat_messages_collection.insert_one(assistant_msg)
                        
                        # Send real-time update
                        await manager.send_personal_message(
                            json.dumps({
                                "type": "ai_chat_response",
                                "message": degraded_response["content"],
                                "timestamp": degraded_response["timestamp"],
                                "degraded_mode": True
                            }),
                            user_id
                        )
                        
                        return JSONResponse(content=degraded_response)
                    
                    # Use AsyncOpenAI client (openai>=1.x) with resolved key
                    from openai import AsyncOpenAI
                    
                    try:
                        request_timeout = float(os.getenv("OPENAI_TIMEOUT_SECONDS", "30"))
                    except ValueError:
                        request_timeout = 30.0
                        logger.warning("Invalid OPENAI_TIMEOUT_SECONDS value, defaulting to 30s")
                    
                    # Create client with resolved API key (user or system)
                    client = AsyncOpenAI(api_key=user_api_key, timeout=request_timeout)
                    
                    # Log which key source is being used
                    logger.info(f"AI Chat: Using OpenAI key source={key_source} for user {user_tag}")
                    
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
                    context_payload = json.dumps(grounded_context, default=str)
                    if len(context_payload) > 4000:
                        context_payload = context_payload[:4000] + "..."
                    tool_catalog = get_tool_catalog()
                    tools_payload = json.dumps(tool_catalog, default=str)
                    system_mode_status = grounded_context.get("system_mode") or {}
                    allowed_actions = ", ".join([tool["name"] for tool in tool_catalog])
                    capabilities = [
                        "Answer questions about bots, performance, risk, and system health",
                        "Provide overview snapshot, wallet status, and autonomy status",
                        "Trigger approved actions only when confirmed (see Allowed Actions)"
                    ]

                    # Prepare context for AI
                    context = f"""You are an AI trading assistant for Amarktai Crypto (part of Amarktai Network).

                    User:
                    - Name: {display_name}
                    - Risk Profile: {risk_profile}

                    Current System Status:
                    - Mode: {system_mode_status.get("mode", "unknown")}
                    - Paper Trading: {system_mode_status.get("paperTrading", False)}
                    - Live Trading: {system_mode_status.get("liveTrading", False)}
                    - Autopilot: {system_mode_status.get("autopilot", False)}

                    Capabilities:
                    - {"; ".join(capabilities)}
                    - Allowed Actions: {allowed_actions}

                    Grounded System Context (JSON):
                    {context_payload}

                    User Memory:
                    - Preferences: {memory_preferences}
                    - Last 7-day summary: {recent_summary}
                    - Last commands: {memory_commands}

                    Available Tools (JSON):
                    {tools_payload}

                    User Question: {content}

                    Instructions:
                    - Respond in plain language (no code blocks unless the user asks for code)
                    - Use the grounded system context. Do not guess unknown values.
                    - Never claim an action completed unless the tool reports success.
                    - If an action requires confirmation, ask for confirmation before executing.
                    - If an action is needed, respond with JSON: {{ "action": "<tool_name>", "params": {{...}}, "reply": "<short response>" }}
                    - If multiple actions are needed, respond with JSON: {{ "tool_actions": [{{"action": "...", "params": {{...}}}}], "reply": "<short response>" }}
                    - Explain safety checks and confirmations as needed
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

        # Tool call parsing: allow AI to return structured tool actions (JSON)
        try:
            tool_action, tool_params, tool_reply, tool_action_list = parse_tool_payload(ai_response or "")
            if tool_action:
                tool_actions.append({"action": tool_action, "params": tool_params or {}, "source": "ai"})
                tool_result = await execute_tool_action(tool_action, tool_params or {}, user_id)
                await log_chatops_action(user_id, tool_action, tool_params or {}, tool_result)
                action_meta = build_action_meta(tool_action, tool_result)
                action_reply = resolve_action_reply(tool_action, tool_result)
                if tool_result.get("requires_confirmation"):
                    requires_confirmation = True
                    confirmation_id = tool_result.get("confirmation_id")
                    ai_response = action_reply
                else:
                    action_results.append(tool_result.get("result", tool_result))
                    ai_response = tool_reply if tool_reply and action_meta.get("action_result") == "success" else action_reply
                    if action_meta.get("action_result") == "success":
                        action_success = True
            elif tool_action_list:
                if tool_reply:
                    ai_response = tool_reply
                for action_item in tool_action_list:
                    if not isinstance(action_item, dict):
                        continue
                    action_name = action_item.get("action") or action_item.get("name")
                    action_params = action_item.get("params", {}) or {}
                    if not action_name:
                        continue
                    tool_actions.append({"action": action_name, "params": action_params, "source": "ai"})
                    tool_result = await execute_tool_action(action_name, action_params, user_id)
                    await log_chatops_action(user_id, action_name, action_params, tool_result)
                    action_meta = build_action_meta(action_name, tool_result)
                    if tool_result.get("requires_confirmation") and not requires_confirmation:
                        requires_confirmation = True
                        confirmation_id = tool_result.get("confirmation_id")
                        ai_response = resolve_action_reply(action_name, tool_result)
                    else:
                        action_results.append(tool_result.get("result", tool_result))
                        if action_meta.get("action_result") == "success":
                            action_success = True
                        elif isinstance(ai_response, str):
                            failure_reason = action_meta.get("reason") or "Action failed."
                            ai_response += f" {failure_reason}"
        except Exception as tool_error:
            logger.warning(f"Tool action parsing failed: {tool_error}")

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

        if action_success:
            await rt_events.force_refresh(user_id, reason="AI action completed. Refreshing dashboard.")
        
        return {
            "success": True,
            "role": "assistant",
            "content": ai_response,
            "reply": ai_response,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            **action_meta,
            "actions": tool_actions,
            "tool_actions": tool_actions,
            "action_results": action_results,
            "requires_confirmation": requires_confirmation,
            "confirmation_id": confirmation_id,
            "meta": {
                "key_source": key_source if 'key_source' in locals() else None,
                "model_used": model_used if 'model_used' in locals() else None,
                "system_state": system_state,
                "grounded_context": grounded_context,
                "error": error_code
            }
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


@router.get("/status")
async def get_ai_status(user_id: str = Depends(get_current_user)):
    """Return AI configuration status for the authenticated user."""
    data = await build_ai_status(user_id)
    return {"success": True, **data}


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
