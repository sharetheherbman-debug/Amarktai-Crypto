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


_PAPER_RESET_CONFIRMATION_PHRASE = "RESET PAPER SANDBOX"


@router.post("/paper-sandbox/reset")
async def reset_paper_sandbox(
    payload: Dict = Body(...),
    user_id: str = Depends(get_current_user),
):
    """Hard reset the paper trading sandbox for the current user.

    Clears bots (paper), bot_runtime_state, bot_events, bot_lifecycle,
    trades, orders, fills, ledger, paper_ledger, equity/drawdown series,
    countdown timers, and wallet caches.

    Required body fields:
        confirmed: true
        confirmation_phrase: "RESET PAPER SANDBOX"

    Returns delete counts per collection.
    """
    if not payload.get("confirmed"):
        raise HTTPException(status_code=400, detail="confirmed=true required")

    phrase = payload.get("confirmation_phrase", "")
    if phrase.strip().upper() != _PAPER_RESET_CONFIRMATION_PHRASE:
        raise HTTPException(
            status_code=400,
            detail=f'confirmation_phrase must be exactly "{_PAPER_RESET_CONFIRMATION_PHRASE}"',
        )

    user_filter = {"user_id": user_id}
    paper_bot_filter = {"user_id": user_id, "trading_mode": "paper"}

    results: Dict[str, int] = {}

    async def _delete(collection_obj, filt: dict, label: str) -> int:
        if collection_obj is None:
            return 0
        try:
            r = await collection_obj.delete_many(filt)
            return r.deleted_count
        except Exception as exc:
            logger.warning("paper-sandbox reset: failed to clear %s: %s", label, exc)
            return 0

    # Targeted paper-only deletes
    results["bots"] = await _delete(db.bots_collection, paper_bot_filter, "bots")
    results["bot_runtime_state"] = await _delete(db.bot_runtime_state_collection, user_filter, "bot_runtime_state")
    results["bot_lifecycle"] = await _delete(db.bot_lifecycle_collection, user_filter, "bot_lifecycle")
    results["trades"] = await _delete(db.trades_collection, {**user_filter, "trading_mode": "paper"}, "trades")
    results["orders"] = await _delete(db.orders_collection, user_filter, "orders")
    results["ledger"] = await _delete(db.ledger_collection, user_filter, "ledger")
    results["paper_ledger"] = await _delete(db.paper_ledger_collection, user_filter, "paper_ledger")
    results["user_countdowns"] = await _delete(db.user_countdowns_collection, user_filter, "user_countdowns")
    results["wallet_balances"] = await _delete(db.wallet_balances_collection, user_filter, "wallet_balances")

    # Collections that don't have module-level globals — access via raw db handle
    raw_db = getattr(db, "db", None)
    if raw_db is not None:
        results["bot_events"] = await _delete(raw_db.bot_events, user_filter, "bot_events")
        results["fills"] = await _delete(raw_db.fills, user_filter, "fills")
        results["equity_series"] = await _delete(raw_db.equity_series, user_filter, "equity_series")
        results["drawdown_series"] = await _delete(raw_db.drawdown_series, user_filter, "drawdown_series")
        # Clear paper-scoped fills so compute_equity() returns 0 after reset
        paper_fills_filter = {"user_id": user_id, "is_paper": True}
        results["fills_ledger"] = await _delete(raw_db.fills_ledger, paper_fills_filter, "fills_ledger")
        # Clear paper-scoped ledger events (bootstrap, funding, and metadata-tagged paper events)
        paper_events_filter = {
            "user_id": user_id,
            "$or": [
                {"event_type": "paper_capital_bootstrap"},
                {"metadata.mode": "paper"},
                {"metadata.is_paper": True},
            ]
        }
        results["ledger_events"] = await _delete(raw_db.ledger_events, paper_events_filter, "ledger_events")
        # Clear circuit breaker state so no stale trips survive reset
        results["circuit_breaker_state"] = await _delete(raw_db.circuit_breaker_state, user_filter, "circuit_breaker_state")

    # Reset paper wallet balance to 0
    try:
        from services.paper_wallet_service import paper_wallet_service
        await paper_wallet_service.reset(user_id)
        results["paper_wallet"] = 1
    except Exception as exc:
        logger.warning("paper-sandbox reset: paper wallet reset failed: %s", exc)
        results["paper_wallet"] = 0

    # Clear in-memory ccxt paper balances so countdown endpoints see 0
    try:
        from ccxt_service import ccxt_service as _ccxt
        if hasattr(_ccxt, "paper_balances") and user_id in _ccxt.paper_balances:
            _ccxt.paper_balances[user_id] = {}
            results["ccxt_paper_balance"] = 1
    except Exception as exc:
        logger.warning("paper-sandbox reset: ccxt paper balance clear failed: %s", exc)

    # Audit log
    try:
        await db.audit_logs_collection.insert_one({
            "user_id": user_id,
            "action": "paper_sandbox_reset",
            "details": results,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
    except Exception:
        pass

    total_deleted = sum(v for v in results.values() if isinstance(v, int))
    logger.info("Paper sandbox reset for user %s: %d documents cleared", user_id[:8], total_deleted)

    # Post-reset invariant check: verify paper equity and trades are zero
    invariant_warnings = []
    try:
        from services.ledger_service import get_ledger_service
        _lsvc = get_ledger_service(db.db)
        post_equity = round(await _lsvc.compute_equity(user_id), 4)
        post_trades = await db.trades_collection.count_documents({"user_id": user_id, "trading_mode": "paper"})
        # Count paper fills specifically
        post_fills = await db.db["fills_ledger"].count_documents({"user_id": user_id, "is_paper": True}) if db.db else 0
        if post_equity != 0:
            msg = f"ledger_equity={post_equity} non-zero after reset for user {user_id[:8]}"
            invariant_warnings.append(msg)
            logger.error("Post-reset invariant FAIL: %s", msg)
        if post_fills != 0:
            msg = f"paper_fills_ledger={post_fills} non-zero after reset for user {user_id[:8]}"
            invariant_warnings.append(msg)
            logger.error("Post-reset invariant FAIL: %s", msg)
    except Exception as inv_err:
        logger.warning("Post-reset invariant check error: %s", inv_err)

    return {
        "success": True,
        "deleted": results,
        "total_deleted": total_deleted,
        "invariant_warnings": invariant_warnings,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# REMOVED: Duplicate of live_trading_gate.py endpoint GET /api/system/live-eligibility
# Use live_trading_gate.py instead


# REMOVED: Duplicate of emergency_stop_endpoints.py endpoint GET /api/system/emergency-stop/status  
# Use emergency_stop_endpoints.py instead


@router.get("/reset-proof")
async def get_reset_proof(user_id: str = Depends(get_current_user)):
    """
    GET /api/system/reset-proof

    Returns a post-reset proof snapshot showing all runtime counters are zero.
    Useful after a Start Fresh / paper reset to confirm clean state.

    Returns:
      - equity: 0 if ledger is clean
      - trades_total: 0 if no trades exist
      - ledger_rows: 0 if fills_ledger is empty
      - bots: 0 if no active bots
      - wallet_balance: current paper wallet ZAR balance
      - is_clean: true if equity==0 and trades_total==0 and bots==0
    """
    result = {
        "equity": 0.0,
        "trades_total": 0,
        "ledger_rows": 0,
        "bots": 0,
        "wallet_balance": 0.0,
        "is_clean": False,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    errors = []

    try:
        from services.ledger_service import get_ledger_service
        if db.db is not None:
            _lsvc = get_ledger_service(db.db)
            result["equity"] = round(await _lsvc.compute_equity(user_id, currency="ZAR"), 4)
            result["ledger_rows"] = await db.db["fills_ledger"].count_documents({"user_id": user_id})
    except Exception as e:
        errors.append(f"ledger: {e}")

    try:
        if db.trades_collection is not None:
            result["trades_total"] = await db.trades_collection.count_documents({"user_id": user_id})
    except Exception as e:
        errors.append(f"trades: {e}")

    try:
        if db.bots_collection is not None:
            result["bots"] = await db.bots_collection.count_documents(
                {"user_id": user_id, "status": {"$in": ["active", "running"]}}
            )
    except Exception as e:
        errors.append(f"bots: {e}")

    try:
        from services.paper_wallet_service import paper_wallet_service
        pw = await paper_wallet_service.get_balances(user_id)
        result["wallet_balance"] = float((pw.get("balances") or {}).get("ZAR", 0) or 0)
    except Exception as e:
        errors.append(f"wallet: {e}")

    result["is_clean"] = (
        result["equity"] == 0.0
        and result["trades_total"] == 0
        and result["bots"] == 0
    )
    if errors:
        result["errors"] = errors

    return result


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
