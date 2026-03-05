"""System routes for basic ping and status endpoints.

This module defines a minimal router that exposes system‑wide ping endpoints.  Having a
dedicated file ensures that the server can mount `/api/system/ping` without
conflicting with other route prefixes and satisfies health checks used by
deployment scripts.
"""

from fastapi import APIRouter, Depends, HTTPException, Body
from datetime import datetime, timezone
from typing import Dict
import config
import logging
import os

from auth import get_current_user
import database as db

logger = logging.getLogger(__name__)

# Prefix ensures final paths begin with /api/system when mounted without an
# additional prefix.
router = APIRouter(prefix="/api/system", tags=["System"])


@router.get("/ping")
async def system_ping() -> dict:
    """Return a simple heartbeat response for system health checks."""
    return {
        "status": "ok",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/platforms")
async def get_platforms() -> dict:
    """Return list of all enabled trading platforms/exchanges.
    
    Returns platform names, enabled status, and bot limits.
    Frontend should use this to populate platform selectors.
    NOW RETURNS ALL 7 PLATFORMS: Luno, Binance, KuCoin, Bybit, Kraken, Bitget, Gate
    """
    try:
        # Import canonical platform registry
        from config.platforms import get_all_platforms, SUPPORTED_PLATFORMS
        
        # Get all platform configs from canonical source
        platform_configs = get_all_platforms()
        
        platforms = []
        for platform_config in platform_configs:
            platforms.append({
                "id": platform_config["id"],
                "name": platform_config["name"],
                "display_name": platform_config["display_name"],
                "enabled": platform_config["enabled"],
                "bot_limit": platform_config["max_bots"],
                "supports_paper": platform_config["supports_paper"],
                "supports_live": platform_config["supports_live"],
                "icon": platform_config.get("icon", ""),
                "color": platform_config.get("color", ""),
                "region": platform_config.get("region", "")
            })
        
        return {
            "platforms": platforms,
            "total_count": len(platforms),
            "default": "all",  # Default filter value
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    except Exception as e:
        # Never crash - return safe defaults with ALL 7 platforms
        logger.error(f"Error in get_platforms: {e}")
        return {
            "platforms": [
                {"id": "luno", "name": "Luno", "display_name": "Luno", "enabled": True, "bot_limit": 5, "supports_paper": True, "supports_live": True},
                {"id": "binance", "name": "Binance", "display_name": "Binance", "enabled": True, "bot_limit": 10, "supports_paper": True, "supports_live": True},
                {"id": "kucoin", "name": "KuCoin", "display_name": "KuCoin", "enabled": True, "bot_limit": 10, "supports_paper": True, "supports_live": True},
                {"id": "bybit", "name": "Bybit", "display_name": "Bybit", "enabled": True, "bot_limit": 10, "supports_paper": True, "supports_live": True},
                {"id": "kraken", "name": "Kraken", "display_name": "Kraken", "enabled": True, "bot_limit": 10, "supports_paper": True, "supports_live": True},
                {"id": "bitget", "name": "Bitget", "display_name": "Bitget", "enabled": True, "bot_limit": 10, "supports_paper": True, "supports_live": True},
                {"id": "gate", "name": "Gate.io", "display_name": "Gate.io", "enabled": True, "bot_limit": 10, "supports_paper": True, "supports_live": True}
            ],
            "total_count": 7,
            "default": "all",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }


@router.get("/gates")
async def get_system_gates() -> dict:
    """Get current state of all system gates (feature flags).
    
    This endpoint shows the live state of all trading gates and explains why they are
    enabled or disabled. Used for go-live readiness checks and troubleshooting.
    
    Dynamically discovers all ENABLE_* flags from config module.
    
    Returns:
        gates: Dict of gate names to their current state (True/False)
        reasons: Dict of gate names to explanation strings
        safe_to_trade: Boolean indicating if trading is safe to enable
        warnings: List of warnings about disabled gates
    """
    try:
        # Dynamically discover all ENABLE_* attributes from config
        gates = {}
        for attr_name in dir(config):
            if attr_name.startswith('ENABLE_'):
                gates[attr_name] = getattr(config, attr_name, False)
        
        # Explain each gate's status
        reasons = {}
        warnings = []
        
        # ENABLE_TRADING
        if gates["ENABLE_TRADING"]:
            reasons["ENABLE_TRADING"] = "Trading system is enabled (required for both paper and live)"
        else:
            reasons["ENABLE_TRADING"] = "Trading system is DISABLED - no trading possible"
            warnings.append("ENABLE_TRADING is OFF - trading is completely disabled")
        
        # ENABLE_PAPER_TRADING
        if gates["ENABLE_PAPER_TRADING"]:
            reasons["ENABLE_PAPER_TRADING"] = "Paper trading is enabled (simulated trades)"
        else:
            reasons["ENABLE_PAPER_TRADING"] = "Paper trading is DISABLED"
            warnings.append("ENABLE_PAPER_TRADING is OFF - cannot test strategies")
        
        # ENABLE_LIVE_TRADING
        if gates["ENABLE_LIVE_TRADING"]:
            reasons["ENABLE_LIVE_TRADING"] = "Live trading is ENABLED - real money at risk"
            warnings.append("⚠️ LIVE TRADING IS ACTIVE - using real funds")
        else:
            reasons["ENABLE_LIVE_TRADING"] = "Live trading is disabled (safe default)"
        
        # ENABLE_AUTOPILOT
        if gates["ENABLE_AUTOPILOT"]:
            reasons["ENABLE_AUTOPILOT"] = "Autopilot is enabled (autonomous bot management)"
        else:
            reasons["ENABLE_AUTOPILOT"] = "Autopilot is disabled (manual bot management only)"
        
        # ENABLE_SCHEDULERS
        if gates["ENABLE_SCHEDULERS"]:
            reasons["ENABLE_SCHEDULERS"] = "Background schedulers are enabled"
        else:
            reasons["ENABLE_SCHEDULERS"] = "Background schedulers are DISABLED"
            warnings.append("ENABLE_SCHEDULERS is OFF - no automated tasks will run")
        
        # ENABLE_BODYGUARD
        if gates["ENABLE_BODYGUARD"]:
            reasons["ENABLE_BODYGUARD"] = "AI Bodyguard is enabled (extra safety checks)"
        else:
            reasons["ENABLE_BODYGUARD"] = "AI Bodyguard is disabled"
        
        # ENABLE_REALTIME
        if gates["ENABLE_REALTIME"]:
            reasons["ENABLE_REALTIME"] = "Real-time events (SSE/WebSocket) are enabled"
        else:
            reasons["ENABLE_REALTIME"] = "Real-time events are disabled"
        
        # ENABLE_CCXT
        if gates["ENABLE_CCXT"]:
            reasons["ENABLE_CCXT"] = "CCXT exchange integration is enabled"
        else:
            reasons["ENABLE_CCXT"] = "CCXT is DISABLED - cannot fetch prices or trade"
            warnings.append("ENABLE_CCXT is OFF - exchange integration disabled")
        
        # Determine if safe to trade
        safe_to_trade_paper = (
            gates["ENABLE_TRADING"] and 
            gates["ENABLE_PAPER_TRADING"] and 
            gates["ENABLE_CCXT"]
        )
        
        safe_to_trade_live = (
            gates["ENABLE_TRADING"] and 
            gates["ENABLE_LIVE_TRADING"] and 
            gates["ENABLE_CCXT"]
        )
        
        # Build recommended actions
        recommended_actions = []
        if not safe_to_trade_paper:
            recommended_actions.append("Enable ENABLE_TRADING, ENABLE_PAPER_TRADING, and ENABLE_CCXT for paper trading")
        if not safe_to_trade_live and gates["ENABLE_LIVE_TRADING"]:
            recommended_actions.append("⚠️ Live trading is ON but prerequisites may not be met")
        
        return {
            "gates": gates,
            "reasons": reasons,
            "safe_to_trade_paper": safe_to_trade_paper,
            "safe_to_trade_live": safe_to_trade_live,
            "warnings": warnings,
            "recommended_actions": recommended_actions,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error in get_system_gates: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get system gates: {str(e)}")


# REMOVED: Duplicate of live_trading_gate.py endpoint GET /api/system/live-eligibility
# Use live_trading_gate.py instead


# REMOVED: Duplicate of emergency_stop_endpoints.py endpoint GET /api/system/emergency-stop/status  
# Use emergency_stop_endpoints.py instead


# REMOVED: Duplicate GET /api/system/status - canonical version in routes/system_status.py
# This duplicate route causes collision. Use system_status.py instead.

# @router.get("/status")
# async def system_status(user_id: str = Depends(get_current_user)) -> dict:
#     """REMOVED - See system_status.py for canonical implementation"""
#     pass


# REMOVED: Duplicate GET /api/system/mode - canonical version in routes/system_mode.py  
# This duplicate route causes collision. Use system_mode.py instead.

# @router.get("/mode")
# async def get_system_mode(user_id: str = Depends(get_current_user)) -> dict:
#     """REMOVED - See system_mode.py for canonical implementation"""
#     pass


# REMOVED: Duplicate POST /api/system/mode - canonical version in routes/system_mode.py
# This duplicate route causes collision. Use system_mode.py /mode/switch instead.

# @router.post("/mode")
# async def set_system_mode(payload: Dict = Body(...), user_id: str = Depends(get_current_user)) -> dict:
#     """REMOVED - See system_mode.py for canonical implementation"""
#     pass


@router.post("/paper-reset")
async def paper_reset(
    data: dict = {},
    user_id: str = Depends(get_current_user),
):
    """POST /api/system/paper-reset (admin-only)

    Orchestrated reset for paper trading mode.
    Requires confirmation phrase: RESET_PAPER_TRADING

    Resets:
    - Daily loss lock
    - Bodyguard locks
    - Circuit breaker (scoped)
    - Paper wallet baseline + ledger fills for daily PnL

    Broadcasts realtime 'reset_complete' event.
    """
    import database as db_mod
    from auth import is_admin

    admin = await is_admin(user_id)
    if not admin:
        raise HTTPException(status_code=403, detail="Admin access required")

    confirmation = data.get("confirmation", "")
    if confirmation != "RESET_PAPER_TRADING":
        raise HTTPException(
            status_code=400,
            detail="Confirmation phrase required: RESET_PAPER_TRADING"
        )

    results = {}
    now = datetime.now(timezone.utc)

    # 1. Reset daily loss lock
    try:
        await db_mod.db["risk_locks"].update_many(
            {"user_id": user_id, "lock_type": "daily_loss"},
            {"$set": {"active": False, "reset_at": now.isoformat(), "reset_by": "paper-reset"}}
        )
        results["daily_loss_lock"] = "reset"
    except Exception as e:
        results["daily_loss_lock"] = f"error: {str(e)[:80]}"

    # 2. Reset bodyguard locks
    try:
        await db_mod.bots_collection.update_many(
            {"user_id": user_id, "status": {"$in": ["bodyguard_paused", "quarantined"]}},
            {"$set": {"status": "active", "bodyguard_reset_at": now.isoformat()}}
        )
        results["bodyguard_locks"] = "reset"
    except Exception as e:
        results["bodyguard_locks"] = f"error: {str(e)[:80]}"

    # 3. Reset circuit breaker
    try:
        await db_mod.db["circuit_breaker"].update_many(
            {"user_id": user_id},
            {"$set": {"tripped": False, "reset_at": now.isoformat()}}
        )
        results["circuit_breaker"] = "reset"
    except Exception as e:
        results["circuit_breaker"] = f"error: {str(e)[:80]}"

    # 4. Reset paper wallet baseline
    try:
        await db_mod.db["paper_wallets"].update_many(
            {"user_id": user_id},
            {"$set": {"daily_pnl_baseline_reset_at": now.isoformat()}}
        )
        results["paper_wallet_baseline"] = "reset"
    except Exception as e:
        results["paper_wallet_baseline"] = f"error: {str(e)[:80]}"

    # 5. Broadcast reset event
    try:
        from realtime_events import rt_events
        await rt_events.emit(user_id, "reset_complete", {
            "type": "paper_reset",
            "timestamp": now.isoformat(),
            "results": results,
        })
        results["broadcast"] = "sent"
    except Exception as e:
        results["broadcast"] = f"skipped: {str(e)[:80]}"

    logger.info(f"Paper reset completed for user {user_id}: {results}")

    return {
        "success": True,
        "message": "Paper trading reset complete",
        "results": results,
        "timestamp": now.isoformat(),
    }
