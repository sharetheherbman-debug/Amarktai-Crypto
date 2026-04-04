"""
Diagnostics Endpoints - Pre-Merge Verification
Includes realtime smoke tests and system health checks
"""

from fastapi import APIRouter, HTTPException, Depends, Request
from datetime import datetime, timezone, timedelta
from typing import Dict, List
import logging
import os
import subprocess

from auth import get_current_user
from websocket_manager import manager
from realtime_events import rt_events
import database as db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/diagnostics", tags=["Diagnostics"])

# Maximum number of bots fetched in a single diagnostics query.
# Matches the cap used by truth_kernel and bot_lifecycle for consistency.
_MAX_BOTS_QUERY = 500


@router.get("/provider-health")
async def provider_health_snapshot(user_id: str = Depends(get_current_user)):
    """Canonical provider health + live market intelligence snapshot for dashboard panels."""
    try:
        from services.provider_registry import list_providers
        from engines.market_intelligence_engine import market_intelligence_engine

        providers = list_providers()
        keys = await db.api_keys_collection.find(
            {"user_id": user_id},
            {"_id": 0, "provider": 1, "status": 1, "last_tested_at": 1, "last_test_error": 1},
        ).to_list(200)
        key_map = {k.get("provider"): k for k in keys if k.get("provider")}

        health_map = {}
        for provider in providers:
            pid = provider.get("id")
            key_doc = key_map.get(pid, {})
            status = str(key_doc.get("status", "not_configured")).lower()
            configured_by_user = bool(key_doc)
            if status in {"configured_valid", "test_ok"}:
                normalized = "healthy"
                valid_key = True
            elif status in {"configured_untested", "saved_untested", "configured_rate_limited"}:
                normalized = "degraded"
                valid_key = "unknown"
            elif status in {"configured_invalid", "test_failed"}:
                normalized = "down"
                valid_key = False
            else:
                normalized = "unconfigured"
                valid_key = False
            health_map[pid] = {
                "status": normalized,
                # Canonical truth fields
                "configured_by_user": configured_by_user,
                "valid_key": valid_key,
                "using_public_fallback": False,
                "ownership_scope": "user" if configured_by_user else "public",
                "last_tested": key_doc.get("last_tested_at"),
                "last_error": key_doc.get("last_test_error"),
                "type": provider.get("type"),
            }

        try:
            live_health = await market_intelligence_engine.health_check()
            usage = market_intelligence_engine.get_provider_usage() or {}
        except Exception:
            live_health = {}
            usage = {}

        for pid, ok in (live_health or {}).items():
            existing = health_map.get(pid, {"status": "unconfigured", "configured_by_user": False, "valid_key": False, "using_public_fallback": False})
            if existing.get("status") == "unconfigured":
                # Provider is reachable via public/system endpoint but user has NOT configured a key.
                # Mark as public_fallback — do NOT upgrade to "healthy".
                existing["status"] = "public_fallback" if ok else "unconfigured"
                existing["using_public_fallback"] = bool(ok)
                existing["ownership_scope"] = "public"
            elif existing.get("status") in {"healthy", "degraded"} and ok is False:
                existing["status"] = "degraded"
            existing["healthy"] = bool(ok) and existing.get("configured_by_user", False)
            existing["reachable"] = bool(ok)
            existing["usage"] = usage.get(pid, {})
            health_map[pid] = existing

        intelligence = {}
        try:
            intelligence = await market_intelligence_engine.get_intelligence_summary(["BTC", "ETH"])
        except Exception:
            intelligence = {}

        return {
            "provider_health": health_map,
            "intelligence": intelligence,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as exc:
        logger.error("provider_health_snapshot failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/regime-summary")
async def regime_summary(user_id: str = Depends(get_current_user)):
    """Summarize latest bot-visible regime and confidence state."""
    try:
        from utils.bot_state import normalize_bot_state

        bots = await db.bots_collection.find(
            {
                "user_id": user_id,
                "status": {"$nin": ["deleted", "marked_for_deletion"]},
                "deleted": {"$ne": True},
                "is_deleted": {"$ne": True},
                "deleted_at": {"$exists": False},
            },
            {"_id": 0},
        ).to_list(_MAX_BOTS_QUERY)
        if not bots:
            return {}

        summary: Dict[str, Dict] = {}
        for raw in bots:
            bot = normalize_bot_state(raw)
            symbol = str(bot.get("pair") or bot.get("symbol") or "UNKNOWN")
            regime = str(bot.get("market_regime", bot.get("canonical_market_regime", "unknown"))).lower()
            confidence = float(
                bot.get("canonical_regime_confidence", bot.get("regime_confidence", bot.get("confidence_score", 0))) or 0
            )
            bucket = summary.setdefault(symbol, {"regime": regime, "confidence": confidence, "bots": 0})
            bucket["bots"] += 1
            if confidence > float(bucket.get("confidence", 0)):
                bucket["regime"] = regime
                bucket["confidence"] = confidence
        return summary
    except Exception as exc:
        logger.error("regime_summary failed: %s", exc)
        return {}


@router.get("/whale-signals")
async def whale_signals(user_id: str = Depends(get_current_user)):
    """Whale flow signals for dashboard panel with graceful unavailable semantics."""
    try:
        from routes.advanced_trading_endpoints import get_whale_summary

        payload = await get_whale_summary(current_user=user_id)
        data = payload.get("data") or payload.get("summary") or {}
        signals = data.get("signals") if isinstance(data, dict) else []
        if not isinstance(signals, list):
            signals = []
        return {
            "status": payload.get("status", "success"),
            "signals": signals,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as exc:
        logger.warning("whale_signals unavailable: %s", exc)
        return {"status": "unavailable", "signals": [], "timestamp": datetime.now(timezone.utc).isoformat()}


@router.get("/sentiment-summary")
async def sentiment_summary(user_id: str = Depends(get_current_user)):
    """Sentiment summary endpoint used by intelligence panels."""
    try:
        from routes.advanced_trading_endpoints import get_sentiment_summary

        payload = await get_sentiment_summary(current_user=user_id)
        summary = payload.get("summary", {}) if isinstance(payload, dict) else {}
        if isinstance(summary, dict) and summary:
            first = next(iter(summary.values()))
            score = float(first.get("score", 0.5) if isinstance(first, dict) else 0.5)
            return {
                "score": score,
                "label": "Bullish" if score > 0.6 else "Bearish" if score < 0.4 else "Neutral",
                "headlines": [],
            }
    except Exception:
        pass
    return {"score": 0.5, "label": "Unavailable", "headlines": []}


@router.get("/orderbook-summary")
async def orderbook_summary(user_id: str = Depends(get_current_user)):
    """Orderbook-like operational summary based on recorded spread/slippage fields."""
    try:
        recent = await db.trades_collection.find(
            {"user_id": user_id},
            {"_id": 0, "spread_estimate": 1, "slippage_estimate": 1, "type": 1, "side": 1},
        ).sort("timestamp", -1).limit(200).to_list(200)
        if not recent:
            return {"imbalance": 0.0, "spread_pct": 0.0, "walls": []}

        buys = sum(1 for t in recent if str(t.get("side", t.get("type", "")).lower()) in {"buy", "long"})
        sells = sum(1 for t in recent if str(t.get("side", t.get("type", "")).lower()) in {"sell", "short"})
        total = max(1, buys + sells)
        imbalance = (buys - sells) / total
        spreads = [float(t.get("spread_estimate") or 0) for t in recent if t.get("spread_estimate") is not None]
        spread_pct = sum(spreads) / len(spreads) if spreads else 0.0
        return {
            "imbalance": round(float(imbalance), 4),
            "spread_pct": round(float(spread_pct), 4),
            "walls": [],
        }
    except Exception as exc:
        logger.warning("orderbook_summary failed: %s", exc)
        return {"imbalance": 0.0, "spread_pct": 0.0, "walls": []}


@router.get("/capital-efficiency")
async def capital_efficiency(user_id: str = Depends(get_current_user)):
    """Capital efficiency snapshot derived from canonical metrics."""
    try:
        from services.canonical_metrics import get_canonical_metrics_snapshot

        bots = await db.bots_collection.find(
            {
                "user_id": user_id,
                "status": {"$nin": ["deleted", "marked_for_deletion"]},
                "deleted": {"$ne": True},
                "is_deleted": {"$ne": True},
                "deleted_at": {"$exists": False},
            },
            {"_id": 0},
        ).to_list(_MAX_BOTS_QUERY)
        metrics = await get_canonical_metrics_snapshot(user_id, bots=bots)
        summary = metrics.get("summary", {})
        return {
            "capital_utilization_pct": summary.get("capital_utilization_pct", 0),
            "roi_pct": summary.get("roi_pct", 0),
            "profit_realized": summary.get("profit_realized", 0),
            "trade_count": summary.get("trade_count", 0),
        }
    except Exception as exc:
        logger.warning("capital_efficiency failed: %s", exc)
        return {"capital_utilization_pct": 0, "roi_pct": 0, "profit_realized": 0, "trade_count": 0}


@router.get("/genetics-summary")
async def genetics_summary(user_id: str = Depends(get_current_user)):
    """Bot evolution summary for intelligence panel."""
    try:
        bots = await db.bots_collection.find(
            {"user_id": user_id},
            {"_id": 0, "parent_bot_id": 1, "generation": 1, "strategy_preset": 1},
        ).to_list(_MAX_BOTS_QUERY)
        if not bots:
            return {"available": False, "reason": "no_bots"}
        evolved = [b for b in bots if b.get("parent_bot_id")]
        max_generation = max(int(b.get("generation", 1) or 1) for b in bots)
        return {
            "available": True,
            "total_bots": len(bots),
            "evolved_bots": len(evolved),
            "max_generation": max_generation,
        }
    except Exception as exc:
        logger.warning("genetics_summary failed: %s", exc)
        return {"available": False, "reason": str(exc)[:120]}


@router.get("/realtime-smoke")
async def realtime_smoke_test(user_id: str = Depends(get_current_user)):
    """Realtime smoke test - verify events are dispatched successfully
    
    Publishes test events to realtime channels and verifies server-side dispatch.
    Used for pre-merge verification to ensure realtime functionality works.
    
    Returns:
        success: bool - Overall test result
        channels_tested: list - Channels that were tested
        events_sent: int - Number of events sent
        dispatch_results: dict - Per-channel dispatch results
        timestamp: str - Test execution time
    """
    try:
        channels_tested = []
        events_sent = 0
        dispatch_results = {}
        
        # Test 1: Send a test message via WebSocket manager
        try:
            await manager.send_message(user_id, {
                "type": "smoke_test",
                "message": "Realtime smoke test",
                "timestamp": datetime.now(timezone.utc).isoformat()
            })
            channels_tested.append("websocket_manager")
            events_sent += 1
            dispatch_results["websocket_manager"] = {
                "success": True,
                "connections": len(manager.active_connections.get(user_id, []))
            }
        except Exception as e:
            dispatch_results["websocket_manager"] = {
                "success": False,
                "error": str(e)
            }
        
        # Test 2: Send test bot update event
        try:
            test_bot_data = {
                "id": "smoke_test_bot",
                "name": "Smoke Test Bot",
                "status": "active"
            }
            await rt_events.bot_updated(user_id, "smoke_test_bot", {"status": "active"})
            channels_tested.append("bot_updates")
            events_sent += 1
            dispatch_results["bot_updates"] = {"success": True}
        except Exception as e:
            dispatch_results["bot_updates"] = {
                "success": False,
                "error": str(e)
            }
        
        # Test 3: Send test metrics update
        try:
            test_metrics = {
                "total_profit": 0,
                "bot_count": 0,
                "test": True
            }
            await rt_events.metrics_updated(user_id, test_metrics)
            channels_tested.append("metrics_updates")
            events_sent += 1
            dispatch_results["metrics_updates"] = {"success": True}
        except Exception as e:
            dispatch_results["metrics_updates"] = {
                "success": False,
                "error": str(e)
            }
        
        # Test 4: Broadcast test
        try:
            await manager.broadcast({
                "type": "smoke_test_broadcast",
                "message": "Broadcast smoke test"
            })
            channels_tested.append("broadcast")
            events_sent += 1
            dispatch_results["broadcast"] = {"success": True}
        except Exception as e:
            dispatch_results["broadcast"] = {
                "success": False,
                "error": str(e)
            }
        
        # Determine overall success
        all_success = all(r.get("success", False) for r in dispatch_results.values())
        
        return {
            "success": all_success,
            "channels_tested": channels_tested,
            "events_sent": events_sent,
            "dispatch_results": dispatch_results,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "user_id": user_id[:8] + "..."  # Partial user ID for privacy
        }
        
    except Exception as e:
        logger.error(f"Realtime smoke test error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/system-health")
async def system_health_check(user_id: str = Depends(get_current_user)):
    """Comprehensive system health check
    
    Tests database connectivity, critical collections, and service availability.
    """
    try:
        health_status = {
            "database": {},
            "collections": {},
            "services": {},
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
        # Test database connectivity
        try:
            await db.client.admin.command('ping')
            health_status["database"]["connected"] = True
            health_status["database"]["status"] = "healthy"
        except Exception as e:
            health_status["database"]["connected"] = False
            health_status["database"]["status"] = "error"
            health_status["database"]["error"] = str(e)
        
        # Test critical collections
        critical_collections = [
            "users_collection",
            "bots_collection",
            "trades_collection",
            "api_keys_collection",
            "training_jobs_collection"
        ]
        
        for coll_name in critical_collections:
            try:
                coll = getattr(db, coll_name, None)
                if coll is not None:
                    # Try to count documents
                    count = await coll.count_documents({})
                    health_status["collections"][coll_name] = {
                        "available": True,
                        "document_count": count
                    }
                else:
                    health_status["collections"][coll_name] = {
                        "available": False,
                        "error": "Collection not initialized"
                    }
            except Exception as e:
                health_status["collections"][coll_name] = {
                    "available": False,
                    "error": str(e)
                }
        
        # Test WebSocket manager
        try:
            active_connections = sum(len(conns) for conns in manager.active_connections.values())
            health_status["services"]["websocket_manager"] = {
                "available": True,
                "active_connections": active_connections
            }
        except Exception as e:
            health_status["services"]["websocket_manager"] = {
                "available": False,
                "error": str(e)
            }
        
        # Determine overall health
        db_healthy = health_status["database"].get("connected", False)
        all_collections_ok = all(c.get("available", False) for c in health_status["collections"].values())
        
        health_status["overall"] = "healthy" if (db_healthy and all_collections_ok) else "degraded"
        
        return health_status
        
    except Exception as e:
        logger.error(f"System health check error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/autopilot-check")
async def autopilot_functionality_check(user_id: str = Depends(get_current_user)):
    """Autopilot functionality check - verify all autopilot features work correctly
    
    Checks:
    - Autopilot enabled status
    - R1000 profit threshold for bot spawning
    - Bot spawn logic correctness
    - Paper-to-live promotion criteria
    - Capital reinvestment logic
    - Strategy optimization
    
    Returns detailed status of autopilot functionality
    """
    try:
        # Get user autopilot settings
        user = await db.users_collection.find_one({"id": user_id}, {"_id": 0})
        
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        autopilot_checks = {
            "enabled": user.get('autopilot_enabled', False),
            "spawn_threshold": {},
            "bot_limits": {},
            "promotion_criteria": {},
            "reinvestment": {},
            "overall_status": "healthy"
        }
        
        # Check 1: R1000 spawn threshold verification
        try:
            from services.ledger_service import get_ledger_service
            ledger = get_ledger_service(db)
            
            # Get profit calculations
            realized_pnl = await ledger.compute_realized_pnl(user_id)
            fees_paid = await ledger.compute_fees_paid(user_id)
            net_profit = realized_pnl - fees_paid
            reserved = await ledger.compute_reserved_profit(user_id) if hasattr(ledger, 'compute_reserved_profit') else 0
            available_profit = net_profit - reserved
            
            autopilot_checks["spawn_threshold"] = {
                "required_profit": 1000.0,
                "current_net_profit": round(net_profit, 2),
                "available_profit": round(available_profit, 2),
                "reserved_profit": round(reserved, 2),
                "can_spawn": available_profit >= 1000.0,
                "status": "pass" if available_profit >= 1000.0 or available_profit < 100 else "pending"
            }
        except Exception as e:
            autopilot_checks["spawn_threshold"] = {
                "status": "error",
                "error": str(e)
            }
        
        # Check 2: Bot limits enforcement
        try:
            bots = await db.bots_collection.find(
                {"user_id": user_id, "status": {"$nin": ["deleted", "marked_for_deletion"]}},
                {"_id": 0}
            ).to_list(1000)
            
            bot_count = len(bots)
            max_bots = 65
            
            # Count by exchange
            exchange_counts = {}
            EXCHANGE_LIMITS = {
                'luno': 5,
                'binance': 10,
                'kucoin': 10,
                'bybit': 10,
                'kraken': 10,
                'bitget': 10,
                'gate': 10
            }
            
            for bot in bots:
                exchange = bot.get('exchange', '').lower()
                exchange_counts[exchange] = exchange_counts.get(exchange, 0) + 1
            
            autopilot_checks["bot_limits"] = {
                "total_bots": bot_count,
                "max_bots": max_bots,
                "under_limit": bot_count < max_bots,
                "exchange_distribution": exchange_counts,
                "exchange_limits": EXCHANGE_LIMITS,
                "exchange_availability": {
                    exchange: {
                        "current": exchange_counts.get(exchange, 0),
                        "max": limit,
                        "available_slots": limit - exchange_counts.get(exchange, 0)
                    }
                    for exchange, limit in EXCHANGE_LIMITS.items()
                },
                "status": "pass"
            }
        except Exception as e:
            autopilot_checks["bot_limits"] = {
                "status": "error",
                "error": str(e)
            }
        
        # Check 3: Paper-to-live promotion criteria
        try:
            from datetime import timedelta
            seven_days_ago = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
            
            paper_bots = await db.bots_collection.find({
                'user_id': user_id,
                'trading_mode': 'paper',
                'paper_start_date': {'$lte': seven_days_ago},
                'promoted_to_live': False
            }).to_list(1000)
            
            eligible_for_promotion = []
            for bot in paper_bots:
                win_rate = bot.get('win_rate', 0)
                max_drawdown = bot.get('max_drawdown', 100)
                trades_count = bot.get('trades_count', 0)
                
                meets_criteria = (
                    win_rate >= 60 and
                    max_drawdown <= 10 and
                    trades_count >= 20
                )
                
                if meets_criteria:
                    eligible_for_promotion.append({
                        "bot_id": bot['id'],
                        "name": bot.get('name'),
                        "win_rate": win_rate,
                        "max_drawdown": max_drawdown,
                        "trades_count": trades_count
                    })
            
            autopilot_checks["promotion_criteria"] = {
                "criteria": {
                    "min_win_rate": 60,
                    "max_drawdown": 10,
                    "min_trades": 20,
                    "min_days_paper": 7
                },
                "paper_bots_count": len(paper_bots),
                "eligible_for_promotion": len(eligible_for_promotion),
                "eligible_bots": eligible_for_promotion,
                "status": "pass"
            }
        except Exception as e:
            autopilot_checks["promotion_criteria"] = {
                "status": "error",
                "error": str(e)
            }
        
        # Check 4: Reinvestment logic
        try:
            # Check if there's profit to reinvest
            reinvest_available = net_profit > 100 and net_profit < 1000
            
            autopilot_checks["reinvestment"] = {
                "enabled": autopilot_checks["enabled"],
                "min_reinvest_profit": 100.0,
                "current_profit": round(net_profit, 2),
                "reinvest_available": reinvest_available,
                "strategy": "Top performing bots receive additional capital",
                "status": "pass"
            }
        except Exception as e:
            autopilot_checks["reinvestment"] = {
                "status": "error",
                "error": str(e)
            }
        
        # Determine overall status
        all_checks = [
            autopilot_checks["spawn_threshold"].get("status"),
            autopilot_checks["bot_limits"].get("status"),
            autopilot_checks["promotion_criteria"].get("status"),
            autopilot_checks["reinvestment"].get("status")
        ]
        
        if all(status == "pass" for status in all_checks):
            autopilot_checks["overall_status"] = "healthy"
        elif any(status == "error" for status in all_checks):
            autopilot_checks["overall_status"] = "degraded"
        else:
            autopilot_checks["overall_status"] = "pending"
        
        autopilot_checks["timestamp"] = datetime.now(timezone.utc).isoformat()
        
        return autopilot_checks
        
    except Exception as e:
        logger.error(f"Autopilot functionality check error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/autopilot")
async def autopilot_runtime_diagnostics(user_id: str = Depends(get_current_user)):
    """Runtime diagnostics for autopilot scheduler and gating."""
    try:
        from autopilot_engine import autopilot
        from utils.env_utils import env_bool
        from utils.trading_gates import check_autopilot_gates, check_trading_mode_enabled

        gates_ok, gates_reason = check_autopilot_gates()
        trading_ok, trading_reason = check_trading_mode_enabled()

        diagnostics = autopilot.get_diagnostics()
        diagnostics["gating"] = {
            "autopilot_enabled": env_bool("AUTOPILOT_ENABLED", False),
            "trading_enabled": trading_ok,
            "trading_mode": trading_reason if trading_ok else None,
            "gates_ok": gates_ok,
            "reason": gates_reason
        }
        diagnostics["timestamp"] = datetime.now(timezone.utc).isoformat()
        return diagnostics
    except Exception as e:
        logger.error(f"Autopilot diagnostics error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/paper-status")
async def get_paper_trading_status(user_id: str = Depends(get_current_user)):
    """Get paper trading diagnostic status

    Returns:
        last_tick: Last scheduler tick time
        last_decision: Last trading decision made
        last_order_attempt: Last order attempt
        last_fill: Last successful fill
        last_error: Last error encountered
        active_bots: Count of active bots (canonical)
        runnable_bots: Count of bots eligible to trade
        total_bots: Total non-deleted bot count
        trades_today: Count of trades executed today
        scheduler_running: Whether scheduler is active
        scheduler_state: Full scheduler lifecycle truth (queue size, noop reason, blocked count)
    """
    try:
        from paper_trading_engine import paper_trading_engine
        from trading_scheduler import trading_scheduler
        from datetime import datetime, timezone
        from services.canonical import get_canonical_bot_counts, get_canonical_trade_counts

        # Get scheduler status — use the real is_running attribute
        scheduler_running = getattr(trading_scheduler, 'is_running', False)

        # Get paper trading engine status
        engine_status = {}
        if hasattr(paper_trading_engine, 'last_tick_time'):
            engine_status['last_tick'] = paper_trading_engine.last_tick_time

        # Canonical bot counts (same function used by /api/bots/status and /api/overview/snapshot)
        counts = await get_canonical_bot_counts(user_id)

        trade_counts = await get_canonical_trade_counts(user_id)
        trades_today = trade_counts["today"]

        # Get last trade/order info
        last_trade = await db.trades_collection.find_one(
            {"user_id": user_id},
            {"_id": 0},
            sort=[("timestamp", -1)]
        )

        # Get last decision from bot decisions collection if it exists
        last_decision = None
        if hasattr(db, 'bot_decisions_collection'):
            decision_doc = await db.bot_decisions_collection.find_one(
                {"user_id": user_id},
                {"_id": 0, "decision": 1, "reason": 1, "timestamp": 1},
                sort=[("timestamp", -1)]
            )
            if decision_doc:
                last_decision = {
                    "decision": decision_doc.get('decision'),
                    "reason": decision_doc.get('reason'),
                    "timestamp": decision_doc.get('timestamp')
                }

        # Get last error from logs (if available)
        last_error = None
        if hasattr(db, 'error_logs_collection'):
            error_doc = await db.error_logs_collection.find_one(
                {"user_id": user_id, "context": "paper_trading"},
                {"_id": 0, "error": 1, "timestamp": 1},
                sort=[("timestamp", -1)]
            )
            if error_doc:
                last_error = {
                    "error": error_doc.get('error'),
                    "timestamp": error_doc.get('timestamp')
                }

        # Expose canonical scheduler lifecycle truth so the API reflects runtime state.
        # This closes the gap between VPS logs and API-visible diagnostics.
        scheduler_state = trading_scheduler.get_health_snapshot()

        return {
            "success": True,
            "last_tick": engine_status.get('last_tick'),
            "last_decision": last_decision,
            "last_order_attempt": last_trade.get('timestamp') if last_trade else None,
            "last_fill": {
                "timestamp": last_trade.get('timestamp'),
                "pair": last_trade.get('pair'),
                "side": last_trade.get('side'),
                "amount": last_trade.get('amount'),
                "price": last_trade.get('price')
            } if last_trade else None,
            "last_error": last_error,
            "active_bots": counts["active"],
            "runnable_bots": counts["runnable"],
            "total_bots": counts["total"],
            "trades_today": trades_today,
            "scheduler_running": scheduler_running,
            # Canonical scheduler lifecycle truth — queue → execution → persistence
            "scheduler_state": {
                "queue_size": scheduler_state.get("queue_size", 0),
                "queued_bot_ids": scheduler_state.get("queued_bot_ids", []),
                "active_trades": scheduler_state.get("active_trades", 0),
                "last_tick_at": scheduler_state.get("last_tick_at"),
                "last_tick_queued": scheduler_state.get("last_tick_queued", 0),
                "last_tick_processed": scheduler_state.get("last_tick_processed", 0),
                "last_tick_blocked": scheduler_state.get("last_tick_blocked", 0),
                "last_tick_executed": scheduler_state.get("last_tick_executed", 0),
                "last_tick_noop_reason": scheduler_state.get("last_tick_noop_reason"),
                "last_trade_at": scheduler_state.get("last_trade_at"),
                "last_trade_result": scheduler_state.get("last_trade_result"),
                "total_ticks": scheduler_state.get("total_ticks", 0),
                "total_trades_executed": scheduler_state.get("total_trades_executed", 0),
                "total_noop_ticks": scheduler_state.get("total_noop_ticks", 0),
            },
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

    except Exception as e:
        logger.error(f"Paper trading status error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/truth")
async def get_truth_snapshot(user_id: str = Depends(get_current_user)):
    """Canonical truth snapshot — single source of truth for all subsystems.

    Returns per-subsystem PASS/FAIL with evidence fields, contradiction
    detector output, and rule precedence order.  Any mismatch between
    endpoint-derived counts and the canonical values is surfaced in the
    ``contradictions`` array.
    """
    try:
        from services.truth_kernel import compute_truth_summary
        snapshot = await compute_truth_summary(user_id, db.db)
        return snapshot
    except Exception as e:
        logger.error(f"Truth snapshot error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/auto-spawn")
async def get_auto_spawn_status(user_id: str = Depends(get_current_user)):
    """Get auto-spawn diagnostic status
    
    Returns:
        enabled: Whether auto-spawn is enabled
        profit_threshold: Minimum profit required (ZAR)
        current_profit: User's current realized profit (ZAR)
        eligible: Whether user is eligible for spawn
        available_capital: Available capital for spawning
        next_eligibility: When user will be eligible (if not now)
        last_spawn_time: Last spawn timestamp
        spawn_count_today: Spawns today
        reason: Why spawn is blocked (if applicable)
    """
    try:
        import os
        import config
        from rules import SUPPORTED_EXCHANGES, check_bot_cap_limit, get_reason_message, PROFIT_THRESHOLD_ZAR
        from profit_ledger import profit_ledger

        def parse_datetime(value):
            if isinstance(value, datetime):
                return value
            if isinstance(value, str):
                try:
                    return datetime.fromisoformat(value.replace("Z", "+00:00"))
                except ValueError:
                    return None
            return None

        enabled = os.getenv('ENABLE_AUTO_SPAWN', '0') == '1' or os.getenv('AUTOPILOT_ENABLED', '0') == '1'
        profit_threshold = float(PROFIT_THRESHOLD_ZAR)
        cooldown_minutes = getattr(config, "AUTO_SPAWN_COOLDOWN_MINUTES", 60)
        max_spawns_per_day = getattr(config, "AUTO_SPAWN_MAX_PER_DAY", 2)

        modes = await db.system_modes_collection.find_one({"user_id": user_id}, {"_id": 0}) or {}
        trading_mode = "live" if modes.get("liveTrading") else "paper"

        total_available = 0
        try:
            from engines.wallet_manager import wallet_manager
            wallet_balance = await wallet_manager.get_master_balance(user_id)
            if 'total_zar' in wallet_balance:
                total_available = wallet_balance['total_zar']
        except Exception as e:
            logger.warning(f"Auto-spawn wallet balance fallback: {e}")

        bot_capital_requirement = float(os.getenv('BOT_INITIAL_CAPITAL_ZAR', '1000'))
        now = datetime.now(timezone.utc)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

        current_profit_per_exchange = {}
        eligible_per_exchange = {}
        spawn_count_today_per_exchange = {}
        last_spawn_time_per_exchange = {}
        reason_per_exchange = {}

        for exchange in SUPPORTED_EXCHANGES:
            current_profit = await profit_ledger.get_exchange_profit(user_id, exchange, trading_mode)
            current_profit_per_exchange[exchange] = round(current_profit, 2)

            spawn_filter = {
                "user_id": user_id,
                "exchange": exchange,
                "$or": [
                    {"auto_spawned": True},
                    {"spawned_by": {"$in": ["autopilot", "auto_spawn"]}}
                ]
            }
            spawn_count_today = await db.bots_collection.count_documents({
                **spawn_filter,
                "created_at": {"$gte": today_start.isoformat()}
            })
            spawn_count_today_per_exchange[exchange] = spawn_count_today

            last_spawn = await db.bots_collection.find_one(
                spawn_filter,
                {"_id": 0, "created_at": 1, "spawned_at": 1},
                sort=[("created_at", -1)]
            )
            last_spawn_time = None
            if last_spawn:
                last_spawn_time = parse_datetime(last_spawn.get("created_at"))
                if last_spawn_time is None:
                    last_spawn_time = parse_datetime(last_spawn.get("spawned_at"))
            last_spawn_time_per_exchange[exchange] = last_spawn_time.isoformat() if last_spawn_time else None

            eligible = True
            reason = None

            if not enabled:
                eligible = False
                reason = "AUTO_SPAWN_DISABLED"
            else:
                bot_count = await db.bots_collection.count_documents({
                    "user_id": user_id,
                    "exchange": exchange,
                    "status": {"$nin": ["deleted", "quarantined"]}
                })
                can_create, reason_code = check_bot_cap_limit(exchange, bot_count + 1, user_id)
                if not can_create:
                    eligible = False
                    reason = get_reason_message(reason_code)
                elif spawn_count_today >= max_spawns_per_day:
                    eligible = False
                    reason = f"DAILY_SPAWN_CAP_REACHED ({spawn_count_today}/{max_spawns_per_day})"
                elif last_spawn_time:
                    cooldown_until = last_spawn_time + timedelta(minutes=cooldown_minutes)
                    if now < cooldown_until:
                        eligible = False
                        reason = f"SPAWN_COOLDOWN_ACTIVE (until {cooldown_until.isoformat()})"
                if eligible and current_profit < profit_threshold:
                    eligible = False
                    reason = f"PROFIT_TOO_LOW (need {profit_threshold} ZAR, have {current_profit:.2f} ZAR)"
                if eligible and total_available < bot_capital_requirement:
                    eligible = False
                    reason = (
                        f"INSUFFICIENT_CAPITAL (need {bot_capital_requirement} ZAR, have {total_available:.2f} ZAR)"
                    )

            eligible_per_exchange[exchange] = eligible
            reason_per_exchange[exchange] = reason or "ELIGIBLE"

        return {
            "success": True,
            "enabled": enabled,
            "profit_threshold": profit_threshold,
            "trading_mode": trading_mode,
            "cooldown_minutes": cooldown_minutes,
            "max_spawns_per_day": max_spawns_per_day,
            "available_capital": total_available,
            "bot_capital_requirement": bot_capital_requirement,
            "current_profit_per_exchange": current_profit_per_exchange,
            "eligible_per_exchange": eligible_per_exchange,
            "spawn_count_today_per_exchange": spawn_count_today_per_exchange,
            "last_spawn_time_per_exchange": last_spawn_time_per_exchange,
            "reason_per_exchange": reason_per_exchange,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as e:
        logger.error(f"Auto-spawn status error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/realtime")
async def get_realtime_status(user_id: str = Depends(get_current_user)):
    """Get realtime connection diagnostic status
    
    Returns:
        ws_connected: WebSocket connection count for user
        ws_total_connections: Total WS connections
        sse_supported: Whether SSE is supported
        last_event_type: Type of last event sent
        last_event_time: Time of last event
        connection_count: Total active connections
        uptime_seconds: How long realtime system has been up
    """
    try:
        import os
        from websocket_manager import manager
        from realtime_events import rt_events
        
        # Get WebSocket connection info
        user_connections = len(manager.active_connections.get(user_id, []))
        total_connections = sum(len(conns) for conns in manager.active_connections.values())
        
        # Get last event info (if tracking exists)
        last_event = getattr(manager, "last_event", None) or getattr(rt_events, "last_event", None)
        
        # Check SSE support
        sse_supported = hasattr(manager, 'send_sse') or os.path.exists('/api/realtime/events')
        
        return {
            "success": True,
            "ws_connected": user_connections,
            "ws_total_connections": total_connections,
            "sse_supported": sse_supported,
            "last_event_type": last_event.get('type') if last_event else None,
            "last_event_time": last_event.get('timestamp') if last_event else None,
            "connection_count": total_connections,
            "manager_type": type(manager).__name__,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as e:
        logger.error(f"Realtime status error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/websocket")
async def websocket_diagnostics(user_id: str = Depends(get_current_user)):
    """Get WebSocket diagnostics and configuration."""
    try:
        import os
        from utils.env_utils import env_bool

        public_ws = os.getenv("PUBLIC_WS_URL")
        public_api = os.getenv("PUBLIC_API_URL")
        ws_url = public_ws

        if not ws_url and public_api:
            if public_api.startswith("https://"):
                ws_url = public_api.replace("https://", "wss://")
            elif public_api.startswith("http://"):
                ws_url = public_api.replace("http://", "ws://")

        if not ws_url:
            host = os.getenv("HOST", "127.0.0.1")
            port = os.getenv("PORT", "8000")
            ws_url = f"ws://{host}:{port}"

        user_connections = len(manager.active_connections.get(user_id, []))
        total_connections = sum(len(conns) for conns in manager.active_connections.values())
        last_event = getattr(manager, "last_event", None)

        return {
            "success": True,
            "ws_url": f"{ws_url}/api/ws",
            "enabled": env_bool("ENABLE_REALTIME", True),
            "connections": {
                "user": user_connections,
                "total": total_connections
            },
            "last_event_time": last_event.get("timestamp") if last_event else None,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    except Exception as e:
        logger.error(f"WebSocket diagnostics error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/accounting")
async def get_accounting_diagnostics(user_id: str = Depends(get_current_user)):
    """Get accounting diagnostics for trades, counters, and bot reconciliation."""
    try:
        trades = await db.trades_collection.find(
            {"user_id": user_id, "status": "closed"},
            {
                "_id": 0,
                "id": 1,
                "bot_id": 1,
                "timestamp": 1,
                "symbol": 1,
                "exchange": 1,
                "entry_price": 1,
                "exit_price": 1,
                "net_pnl": 1,
                "profit_loss": 1,
                "fee_paid": 1,
                "fee_amount": 1,
                "slippage": 1,
                "trade_close_reason": 1
            }
        ).sort("timestamp", -1).to_list(5000)

        used_profit_loss = False

        def trade_net(trade: Dict) -> float:
            nonlocal used_profit_loss
            net_value = trade.get("net_pnl")
            if net_value is None:
                used_profit_loss = True
                net_value = trade.get("profit_loss", 0)
            return float(net_value or 0)

        total_trades = len(trades)
        win_count = sum(1 for t in trades if trade_net(t) > 0)
        loss_count = sum(1 for t in trades if trade_net(t) < 0)

        if used_profit_loss:
            logger.warning("Accounting diagnostics: trades missing net_pnl, falling back to profit_loss")

        trade_by_bot: Dict[str, list] = {}
        for trade in trades:
            trade_by_bot.setdefault(trade.get("bot_id"), []).append(trade)

        bots = await db.bots_collection.find(
            {"user_id": user_id, "status": {"$ne": "deleted"}},
            {"_id": 0}
        ).to_list(1000)

        reconciliation = []
        for bot in bots:
            bot_id = bot.get("id")
            bot_trades = trade_by_bot.get(bot_id, [])
            bot_realized = sum(trade_net(t) for t in bot_trades)
            bot_wins = sum(1 for t in bot_trades if trade_net(t) > 0)
            bot_losses = sum(1 for t in bot_trades if trade_net(t) < 0)
            initial_capital = float(bot.get("initial_capital", 0) or 0)
            current_capital = float(bot.get("current_capital", 0) or 0)
            expected_equity = initial_capital + bot_realized
            reconciliation.append({
                "bot_id": bot_id,
                "bot_name": bot.get("name"),
                "initial_capital": round(initial_capital, 2),
                "current_capital": round(current_capital, 2),
                "total_profit": round(float(bot.get("total_profit", 0) or 0), 2),
                "realized_pnl": round(bot_realized, 2),
                "expected_equity": round(expected_equity, 2),
                "equity_delta": round(current_capital - expected_equity, 2),
                "trades_count": len(bot_trades),
                "win_count": bot_wins,
                "loss_count": bot_losses
            })

        return {
            "success": True,
            "trades_recent": trades[:20],
            "counters": {
                "trades_count": total_trades,
                "win_count": win_count,
                "loss_count": loss_count
            },
            "reconciliation": reconciliation,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    except Exception as e:
        logger.error(f"Accounting diagnostics error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/wallet-status")
async def get_wallet_status(user_id: str = Depends(get_current_user)):
    """
    Get wallet diagnostics status
    
    Returns:
        - Balance snapshots per exchange
        - Active transfers
        - Reserved funds
        - Recent transfer history
        - Wallet health indicators
    """
    try:
        # Get balance snapshots
        snapshots = await db.db["balances_snapshots"].find(
            {"user_id": user_id},
            {"_id": 0}
        ).sort("timestamp", -1).limit(50).to_list(50)
        
        # Group by exchange and currency
        balances = {}
        for snapshot in snapshots:
            exchange = snapshot.get("exchange")
            currency = snapshot.get("currency")
            balance = snapshot.get("balance", 0)
            
            if exchange not in balances:
                balances[exchange] = {}
            
            if currency not in balances[exchange]:
                balances[exchange][currency] = balance
        
        # Get active transfers
        active_transfers = await db.db["transfer_jobs"].find(
            {
                "user_id": user_id,
                "state": {"$nin": ["confirmed", "failed", "cancelled"]}
            },
            {"_id": 0}
        ).to_list(20)
        
        # Get reserved funds
        reserved_funds = await db.db["reserved_funds"].find(
            {"user_id": user_id},
            {"_id": 0}
        ).to_list(20)
        
        # Get recent transfer history (last 10)
        recent_transfers = await db.db["transfer_jobs"].find(
            {"user_id": user_id},
            {"_id": 0}
        ).sort("created_at", -1).limit(10).to_list(10)
        
        # Calculate health indicators
        total_balance = 0
        for exchange_balances in balances.values():
            for balance in exchange_balances.values():
                total_balance += balance
        
        total_reserved = sum(rf.get("amount", 0) for rf in reserved_funds)
        available = total_balance - total_reserved
        
        return {
            "success": True,
            "balances": balances,
            "active_transfers": len(active_transfers),
            "active_transfer_details": active_transfers,
            "reserved_funds": reserved_funds,
            "recent_transfers": recent_transfers,
            "health": {
                "total_balance": round(total_balance, 2),
                "total_reserved": round(total_reserved, 2),
                "available": round(available, 2),
                "exchanges_with_balance": len(balances)
            },
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as e:
        logger.error(f"Wallet status error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/transfers")
async def get_transfer_diagnostics(user_id: str = Depends(get_current_user)):
    """
    Get transfer system diagnostics
    
    Returns:
        - Transfer queue status
        - Recent transfers with states
        - Transfer state distribution
        - Average processing time
        - Success rate
    """
    try:
        # Get all transfers for user
        all_transfers = await db.db["transfer_jobs"].find(
            {"user_id": user_id},
            {"_id": 0}
        ).sort("created_at", -1).limit(100).to_list(100)
        
        # Calculate statistics
        state_distribution = {}
        processing_times = []
        successful = 0
        failed = 0
        
        for transfer in all_transfers:
            state = transfer.get("state", "unknown")
            state_distribution[state] = state_distribution.get(state, 0) + 1
            
            if state == "confirmed":
                successful += 1
                # Calculate processing time if both timestamps exist
                created = transfer.get("created_at")
                updated = transfer.get("updated_at")
                if created and updated:
                    try:
                        created_dt = datetime.fromisoformat(created.replace('Z', '+00:00'))
                        updated_dt = datetime.fromisoformat(updated.replace('Z', '+00:00'))
                        processing_time = (updated_dt - created_dt).total_seconds()
                        processing_times.append(processing_time)
                    except:
                        pass
            
            elif state == "failed":
                failed += 1
        
        avg_processing_time = sum(processing_times) / len(processing_times) if processing_times else 0
        total = successful + failed
        success_rate = (successful / total * 100) if total > 0 else 0
        
        # Get pending transfers
        pending = await db.db["transfer_jobs"].count_documents({
            "user_id": user_id,
            "state": {"$in": ["requested", "queued", "broadcast"]}
        })
        
        # Get transfers needing approval
        needs_approval = await db.db["transfer_jobs"].count_documents({
            "user_id": user_id,
            "state": "needs_approval"
        })
        
        return {
            "success": True,
            "total_transfers": len(all_transfers),
            "state_distribution": state_distribution,
            "pending_queue": pending,
            "needs_approval": needs_approval,
            "statistics": {
                "successful": successful,
                "failed": failed,
                "success_rate": round(success_rate, 2),
                "avg_processing_time_seconds": round(avg_processing_time, 2)
            },
            "recent_transfers": all_transfers[:10],
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as e:
        logger.error(f"Transfer diagnostics error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/regime")
async def get_market_regime(pair: str = "BTC/USD", exchange: str = "luno"):
    """
    Get current market regime detection
    
    Returns:
        - Current regime (trending, mean-reversion, high-vol, low-vol)
        - Trend direction
        - Volatility level
        - Recommended strategy
        - Confidence score
    """
    try:
        from market_regime import MarketRegimeDetector
        
        detector = MarketRegimeDetector()
        regime = await detector.detect_regime(pair, exchange)
        
        # Add strategy recommendation based on regime
        strategy_map = {
            "trending_up": "momentum_long",
            "trending_down": "momentum_short",
            "sideways": "mean_reversion",
            "high_volatility": "breakout",
            "low_volatility": "range_trading"
        }
        
        recommended_strategy = strategy_map.get(regime.get("regime"), "balanced")
        
        return {
            "success": True,
            "pair": pair,
            "exchange": exchange,
            "regime": regime.get("regime", "unknown"),
            "trend": regime.get("trend", "neutral"),
            "volatility": regime.get("volatility", "normal"),
            "confidence": regime.get("confidence", 0),
            "recommended_strategy": recommended_strategy,
            "cached_for_minutes": 15,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as e:
        logger.error(f"Market regime error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/health-detail")
async def get_health_detail():
    """
    Detailed system health with self-healing status
    
    Returns:
        - Database connectivity
        - Service health (schedulers, engines, etc.)
        - Self-healing status
        - Circuit breaker states
        - Error rates
        - Resource usage
    """
    try:
        # Check database
        db_healthy = False
        try:
            await db.db.command("ping")
            db_healthy = True
        except:
            pass
        
        # Check collections
        collection_status = {}
        required_collections = [
            "users", "bots", "trades", "api_keys",
            "transfer_jobs", "transfers_ledger", "balances_snapshots",
            "reserved_funds", "coordination_locks"
        ]
        
        for coll_name in required_collections:
            try:
                count = await db.db[coll_name].count_documents({})
                collection_status[coll_name] = {"exists": True, "count": count}
            except:
                collection_status[coll_name] = {"exists": False, "count": 0}
        
        # Check self-healing
        self_healing_status = {}
        try:
            from self_healing import self_healing_monitor
            self_healing_status = self_healing_monitor.get_status() if hasattr(self_healing_monitor, 'get_status') else {}
        except:
            self_healing_status = {"error": "self_healing module not available"}
        
        # Check circuit breakers
        circuit_breaker_status = {}
        try:
            # Get circuit breaker states from database
            breakers = await db.db["circuit_breakers"].find({}, {"_id": 0}).to_list(10)
            for breaker in breakers:
                circuit_breaker_status[breaker.get("name", "unknown")] = {
                    "state": breaker.get("state", "unknown"),
                    "last_triggered": breaker.get("last_triggered")
                }
        except:
            circuit_breaker_status = {"error": "circuit_breakers collection not available"}
        
        # Calculate overall health score
        health_score = 0
        if db_healthy:
            health_score += 40
        
        collections_healthy = sum(1 for cs in collection_status.values() if cs.get("exists"))
        health_score += (collections_healthy / len(required_collections)) * 40
        
        if not self_healing_status.get("error"):
            health_score += 10
        
        if not circuit_breaker_status.get("error"):
            health_score += 10
        
        return {
            "success": True,
            "health_score": round(health_score, 1),
            "database": {
                "healthy": db_healthy,
                "collections": collection_status
            },
            "self_healing": self_healing_status,
            "circuit_breakers": circuit_breaker_status,
            "services": {
                "scheduler": "unknown",  # Would check actual scheduler status
                "paper_trading": "unknown",
                "realtime_events": "unknown"
            },
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as e:
        logger.error(f"Health detail error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# WALLET DIAGNOSTICS ENDPOINTS
# ============================================================================
# NOTE: Duplicate /wallet-status and /transfers routes removed (lines 961-1054)
# Canonical versions exist earlier in this file at lines 650 and 733


@router.get("/approvals")
async def get_approvals_diagnostics(user_id: str = Depends(get_current_user)):
    """
    Approval diagnostics - pending/processed approvals
    
    Returns:
    - Pending approvals count
    - Recent approvals/rejections
    - Approval queue health
    """
    try:
        # Check if user is admin
        user = await db.users_collection.find_one({"id": user_id})
        is_admin = user and user.get("role") == "admin"
        
        if not is_admin:
            return {
                "message": "Admin access required for approval diagnostics",
                "is_admin": False
            }
        
        # Get pending approvals
        pending_cursor = db.db["transfer_jobs"].find(
            {"state": "needs_approval"},
            {"_id": 0}
        ).sort("created_at", -1)
        
        pending = await pending_cursor.to_list(100)
        
        # Get recent processed approvals
        processed_cursor = db.db["audit_log"].find(
            {"event": {"$in": ["transfer_approved", "transfer_rejected"]}},
            {"_id": 0}
        ).sort("timestamp", -1).limit(50)
        
        processed = await processed_cursor.to_list(50)
        
        return {
            "pending_count": len(pending),
            "pending_approvals": pending,
            "recent_processed": processed,
            "is_admin": True,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as e:
        logger.error(f"Approvals diagnostics error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/email-status")
async def get_email_status():
    """
    Email service diagnostics
    
    Returns:
    - SMTP configured status
    - Recent email confirmations sent
    - Configuration details (redacted)
    """
    try:
        import config
        
        smtp_configured = bool(config.SMTP_USER and config.SMTP_PASSWORD)
        
        # Get recent email confirmations
        recent_emails_cursor = db.db["email_confirmations"].find(
            {},
            {"_id": 0, "token": 0}  # Exclude sensitive token
        ).sort("created_at", -1).limit(10)
        
        recent_emails = await recent_emails_cursor.to_list(10)
        
        return {
            "smtp_configured": smtp_configured,
            "smtp_host": config.SMTP_HOST if smtp_configured else None,
            "smtp_port": config.SMTP_PORT if smtp_configured else None,
            "from_email": config.FROM_EMAIL if smtp_configured else None,
            "recent_emails_count": len(recent_emails),
            "recent_emails": recent_emails,
            "status": "configured" if smtp_configured else "not_configured",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as e:
        logger.error(f"Email status error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/reserves")
async def get_reserves_diagnostics(user_id: str = Depends(get_current_user)):
    """
    Reserved funds diagnostics - Available vs reserved per exchange
    
    Returns:
    - Reserved funds by exchange and currency
    - Available balance (total - reserved)
    - Bot allocations
    """
    try:
        # Get wallet balances with reserved funds
        balances_cursor = db.wallet_balances_collection.find(
            {"user_id": user_id},
            {"_id": 0}
        )
        
        balances = await balances_cursor.to_list(100)
        
        # Calculate totals per exchange
        exchange_summary = {}
        for bal in balances:
            exchange = bal.get("exchange", "unknown")
            currency = bal.get("currency", "unknown")
            total = float(bal.get("balance", 0))
            reserved = float(bal.get("reserved", 0))
            available = total - reserved
            
            if exchange not in exchange_summary:
                exchange_summary[exchange] = {
                    "currencies": {},
                    "total_value_zar": 0
                }
            
            exchange_summary[exchange]["currencies"][currency] = {
                "total": round(total, 2),
                "reserved": round(reserved, 2),
                "available": round(available, 2),
                "utilization_pct": round((reserved / total * 100) if total > 0 else 0, 1)
            }
        
        # Get active bots to show what's reserved
        active_bots_cursor = db.bots_collection.find(
            {
                "user_id": user_id,
                "state": {"$in": ["running", "waiting"]}
            },
            {"_id": 0, "id": 1, "name": 1, "exchange": 1, "budget": 1}
        )
        
        active_bots = await active_bots_cursor.to_list(100)
        
        return {
            "success": True,
            "exchange_summary": exchange_summary,
            "active_bots": active_bots,
            "total_active_bots": len(active_bots),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as e:
        logger.error(f"Reserves diagnostics error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/transfer-path")
async def transfer_path_diagnostic():
    """
    Diagnostic endpoint to verify which transfer path is active
    
    Checks:
    - Enhanced wallet transfers enabled
    - Transfer state machine availability
    - Legacy wallet_manager blocked status
    - Transfer limits service availability
    - Address whitelist service availability
    
    Returns:
        active_path: 'enhanced' | 'legacy_blocked' | 'unknown'
        enhanced_enabled: bool
        services_available: dict
        config: dict with relevant settings
        production_ready: bool
    """
    try:
        import config
        from services.transfer_state_machine import transfer_state_machine
        from services.transfer_limits_service import transfer_limits_service
        from services.address_whitelist import address_whitelist_service
        
        # Check if enhanced transfers are enabled
        enhanced_enabled = getattr(config, 'ENABLE_WALLET_TRANSFERS_ENHANCED', False) or \
                          getattr(config, 'ENABLE_REALTIME_TRANSFERS', False)
        
        # Check service availability
        services_available = {
            "transfer_state_machine": transfer_state_machine is not None,
            "transfer_limits_service": transfer_limits_service is not None,
            "address_whitelist_service": address_whitelist_service is not None
        }
        
        # Check limit configuration
        limits_configured = {
            "per_tx_limit": getattr(config, 'WALLET_MAX_TRANSFER_ZAR_PER_TX', None),
            "daily_limit": getattr(config, 'WALLET_MAX_TRANSFER_ZAR_PER_DAY', None),
            "monthly_limit": getattr(config, 'WALLET_MAX_TRANSFER_ZAR_PER_MONTH', None)
        }
        
        # Check security settings
        security_config = {
            "require_2fa": getattr(config, 'REQUIRE_2FA_FOR_WITHDRAWALS', False),
            "require_whitelist": getattr(config, 'REQUIRE_ADDRESS_WHITELIST', True),
            "approval_threshold_zar": getattr(config, 'REQUIRE_ADMIN_APPROVAL_ABOVE_ZAR', 100000)
        }
        
        # Determine active path
        if enhanced_enabled and all(services_available.values()):
            active_path = "enhanced"
        elif enhanced_enabled and not all(services_available.values()):
            active_path = "enhanced_partial"
        else:
            active_path = "legacy_blocked"
        
        # Production readiness check
        production_ready = (
            active_path == "enhanced" and
            all(limits_configured.values()) and
            all(v is not None for v in limits_configured.values())
        )
        
        return {
            "success": True,
            "active_path": active_path,
            "enhanced_enabled": enhanced_enabled,
            "services_available": services_available,
            "limits_configured": limits_configured,
            "security_config": security_config,
            "production_ready": production_ready,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "message": (
                "✅ Enhanced transfer path active and production-ready" if production_ready
                else "⚠️ Enhanced transfer path not fully configured" if active_path == "enhanced_partial"
                else "❌ Legacy transfer path (blocked for safety)"
            )
        }
        
    except Exception as e:
        logger.error(f"Transfer path diagnostic error: {e}")
        return {
            "success": False,
            "error": str(e),
            "active_path": "unknown",
            "production_ready": False,
            "message": f"❌ Unable to determine transfer path: {str(e)}"
        }


@router.get("/ws")
async def websocket_diagnostics():
    """WebSocket readiness diagnostics endpoint
    
    Returns WebSocket configuration and health info.
    Used to verify WebSocket endpoint is properly configured before attempting connection.
    
    Returns:
        expected_path: str - The WebSocket endpoint path
        protocol: str - Expected protocol (ws or wss)
        ok: bool - Whether WebSocket is ready
        note: str - Usage instructions
        manager_info: dict - WebSocket manager status
    """
    try:
        # Get WebSocket manager info
        manager_info = {}
        try:
            from websocket_manager import manager
            
            # Check if manager has active_connections attribute
            if hasattr(manager, 'active_connections'):
                connection_count = len(manager.active_connections) if manager.active_connections else 0
            else:
                connection_count = 0
            
            manager_info = {
                "available": True,
                "active_connections": connection_count,
                "type": type(manager).__name__
            }
        except Exception as e:
            logger.warning(f"Could not get WebSocket manager info: {e}")
            manager_info = {
                "available": False,
                "error": str(e)
            }
        
        return {
            "ok": True,
            "expected_path": "/api/ws",
            "protocol": "wss (production) or ws (development)",
            "note": "Use wss://<host>/api/ws?token=<jwt_token> for secure connections",
            "usage": {
                "query_param": "/api/ws?token=<jwt_token>",
                "header": "Authorization: Bearer <jwt_token>",
                "both_supported": True
            },
            "nginx_config": {
                "required": True,
                "location": "/api/ws",
                "upgrade_header": "required",
                "connection_header": "upgrade",
                "timeout": "3600s recommended"
            },
            "manager_info": manager_info,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    except Exception as e:
        logger.error(f"WebSocket diagnostics error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# DATA INTEGRITY ENDPOINT
# ============================================================================

# Tolerance for wallet balance reconciliation (cents)
WALLET_BALANCE_TOLERANCE = 0.01
# Tolerance for bot capital vs wallet reserved reconciliation (R1)
CAPITAL_RECONCILIATION_TOLERANCE = 1.0

@router.get("/data-integrity")
async def data_integrity_check(user_id: str = Depends(get_current_user)):
    """
    GET /api/diagnostics/data-integrity

    Reconciles wallet, bots, trades, and ledger data for the authenticated user.
    Returns per-subsystem pass/fail with details on mismatches.
    """
    now = datetime.now(timezone.utc)
    checks: Dict = {}

    try:
        # 1. Bot count consistency
        all_bots = await db.bots_collection.find(
            {"user_id": user_id, "deleted": {"$ne": True}}
        ).to_list(length=500)

        active_bots = [b for b in all_bots if b.get("status") == "active"]
        paused_bots = [b for b in all_bots if b.get("status") == "paused"]

        checks["bot_counts"] = {
            "status": "PASS",
            "total": len(all_bots),
            "active": len(active_bots),
            "paused": len(paused_bots),
        }

        # 2. Wallet balance check
        wallet_doc = await db.db["paper_wallets"].find_one({"user_id": user_id}) or {}
        wallet_total = float(wallet_doc.get("total", wallet_doc.get("available", 0)))
        wallet_available = float(wallet_doc.get("available", 0))
        wallet_reserved = float(wallet_doc.get("reserved", 0))

        balance_match = abs(wallet_total - (wallet_available + wallet_reserved)) < WALLET_BALANCE_TOLERANCE
        checks["wallet_balance"] = {
            "status": "PASS" if balance_match else "FAIL",
            "total": wallet_total,
            "available": wallet_available,
            "reserved": wallet_reserved,
            "discrepancy": None if balance_match else round(wallet_total - wallet_available - wallet_reserved, 2),
        }

        # 3. Bot capital vs wallet reconciliation
        total_bot_capital = sum(float(b.get("current_capital", 0)) for b in all_bots)
        capital_close = abs(total_bot_capital - wallet_reserved) < CAPITAL_RECONCILIATION_TOLERANCE
        checks["capital_reconciliation"] = {
            "status": "PASS" if capital_close else "WARN",
            "total_bot_capital": round(total_bot_capital, 2),
            "wallet_reserved": round(wallet_reserved, 2),
            "difference": round(total_bot_capital - wallet_reserved, 2),
        }

        # 4. Trade count check
        total_trades = await db.trades_collection.count_documents({"user_id": user_id})
        open_trades = await db.trades_collection.count_documents(
            {"user_id": user_id, "status": {"$in": ["open", "active"]}}
        )
        checks["trades"] = {
            "status": "PASS",
            "total_trades": total_trades,
            "open_trades": open_trades,
        }

        # 5. Ledger fill count
        try:
            fills_count = await db.db["fills_ledger"].count_documents({"user_id": user_id})
        except Exception:
            fills_count = 0
        checks["ledger_fills"] = {
            "status": "PASS" if fills_count >= 0 else "WARN",
            "total_fills": fills_count,
        }

        # Overall status
        failed = [k for k, v in checks.items() if v.get("status") == "FAIL"]
        warned = [k for k, v in checks.items() if v.get("status") == "WARN"]

        return {
            "timestamp": now.isoformat(),
            "user_id": user_id,
            "overall_status": "FAIL" if failed else ("WARN" if warned else "PASS"),
            "failed_checks": failed,
            "warning_checks": warned,
            "checks": checks,
        }
    except Exception as e:
        logger.error(f"Data integrity check error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Data integrity check failed: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# Frontend ↔ Backend Contract Endpoint
# No authentication required – used by smoke tests and the frontend error panel
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/frontend-contract")
async def frontend_contract():
    """Return the expected API contract version and key flags for frontend validation.

    This endpoint is intentionally unauthenticated so it can be:
      - Hit by smoke_test.sh without a token
      - Used by the frontend ErrorBoundary "Copy Diagnostics" flow
      - Polled by monitoring tools
    """
    def get_build_sha() -> str:
        sha = os.environ.get("BUILD_SHA", "")
        if sha:
            return sha
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--short", "HEAD"],
                capture_output=True, text=True, timeout=3
            )
            return result.stdout.strip() if result.returncode == 0 else "unknown"
        except Exception:
            return "unknown"

    return {
        "contract_version": "1",
        "api_version": "3.0.0",
        "build_sha": get_build_sha(),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "expected_endpoints": {
            "auth_login":        "POST /api/auth/login",
            "auth_me":           "GET  /api/auth/me",
            "bots_status":       "GET  /api/bots/status",
            "overview_snapshot": "GET  /api/overview/snapshot",
            "system_mode":       "GET  /api/system/mode",
            "keys_status":       "GET  /api/keys/status",
            "health_ping":       "GET  /api/health/ping",
            "prices_live":       "GET  /api/prices/live",
            "trades_recent":     "GET  /api/trades/recent",
            "wallet_balances":   "GET  /api/wallet/balances",
            "ws_realtime":       "WS  /api/ws",
        },
        "feature_flags": {
            "paper_trading":  True,
            "live_trading":   bool(int(os.environ.get("LIVE_TRADING", "0"))),
            "autopilot":      bool(int(os.environ.get("AUTOPILOT_ENABLED", "0"))),
            "realtime_ws":    True,
            "ai_chat":        bool(os.environ.get("OPENAI_API_KEY", "")),
        },
        "supported_exchanges": [
            "luno", "binance", "kucoin", "bybit", "kraken", "bitget", "gate"
        ],
    }


@router.get("/daily-loss-status")
async def get_daily_loss_status(user_id: str = Depends(get_current_user)):
    """
    Diagnostics: Daily loss lock state for the current user.

    Returns:
      - lock_active: whether the daily loss lock is currently set
      - day_key: the UTC date when the lock was triggered
      - is_stale: True if day_key != today's UTC date (lock will auto-clear)
      - locked_reason: human-readable reason
      - locked_at: timestamp of lock activation
      - today_utc: today's UTC date string (YYYY-MM-DD)
    """
    try:
        from datetime import datetime, timezone
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        user = await db.users_collection.find_one(
            {"id": user_id},
            {
                "_id": 0,
                "daily_loss_lock_active": 1,
                "daily_loss_day_key": 1,
                "daily_loss_locked_at": 1,
                "daily_loss_locked_reason": 1,
                "daily_loss_pct": 1,
                "daily_loss_lock_reset_at": 1,
                "daily_loss_lock_reset_by": 1,
            },
        )
        if not user:
            return {"error": "User not found", "today_utc": today}

        lock_active = bool(user.get("daily_loss_lock_active", False))
        day_key = user.get("daily_loss_day_key", "")
        is_stale = lock_active and (not day_key or day_key != today)

        return {
            "lock_active": lock_active,
            "day_key": day_key or None,
            "is_stale": is_stale,
            "locked_reason": user.get("daily_loss_locked_reason") if lock_active else None,
            "locked_at": user.get("daily_loss_locked_at") if lock_active else None,
            "daily_loss_pct": user.get("daily_loss_pct") if lock_active else None,
            "last_reset_at": user.get("daily_loss_lock_reset_at"),
            "last_reset_by": user.get("daily_loss_lock_reset_by"),
            "today_utc": today,
        }
    except Exception as exc:
        logger.error(f"daily-loss-status error: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))


# =====================================================================
# NEW DIAGNOSTIC ENDPOINTS — Pass 1 Go-Live Recovery
# =====================================================================


@router.get("/scheduler-health")
async def scheduler_health_diagnostic(user_id: str = Depends(get_current_user)):
    """Canonical scheduler-health diagnostic.

    Reports comprehensive scheduler state including tick history,
    last trade info, queue status, and heartbeat.
    """
    try:
        from trading_scheduler import trading_scheduler

        return trading_scheduler.get_health_snapshot()
    except Exception as exc:
        logger.error(f"scheduler-health error: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/reset-proof")
async def reset_proof_diagnostic(user_id: str = Depends(get_current_user)):
    """Canonical reset-proof diagnostic.

    Returns counts for every collection affected by a paper-reset so
    operators can verify that a reset actually cleared the expected data.
    """
    try:
        bots_count = await db.bots_collection.count_documents({
            "user_id": user_id,
            "status": {"$nin": ["deleted"]},
        })

        trades_count = await db.trades_collection.count_documents({
            "user_id": user_id,
        })

        orders_count = await db.orders_collection.count_documents({
            "user_id": user_id,
        })

        fills_count = 0
        if hasattr(db, 'fills_collection'):
            fills_count = await db.fills_collection.count_documents({
                "user_id": user_id,
            })

        paper_wallet_count = 0
        if hasattr(db, 'paper_wallets_collection'):
            paper_wallet_count = await db.paper_wallets_collection.count_documents({
                "user_id": user_id,
            })

        ledger_count = 0
        if hasattr(db, 'ledger_collection'):
            ledger_count = await db.ledger_collection.count_documents({
                "user_id": user_id,
            })

        risk_user = await db.users_collection.find_one(
            {"id": user_id},
            {"_id": 0, "daily_loss_lock_active": 1, "emergency_stop": 1}
        )

        return {
            "user_id_prefix": user_id[:8] + "...",
            "bots_non_deleted": bots_count,
            "trades": trades_count,
            "orders": orders_count,
            "fills": fills_count,
            "paper_wallets": paper_wallet_count,
            "ledger_entries": ledger_count,
            "daily_loss_lock_active": (risk_user or {}).get("daily_loss_lock_active", False),
            "emergency_stop": (risk_user or {}).get("emergency_stop", False),
            "is_clean": (
                bots_count == 0
                and trades_count == 0
                and orders_count == 0
                and fills_count == 0
                and paper_wallet_count == 0
                and ledger_count == 0
            ),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as exc:
        logger.error(f"reset-proof error: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/paper-activity")
async def paper_activity_diagnostic(user_id: str = Depends(get_current_user)):
    """Canonical paper-trading-activity diagnostic.

    Proves whether end-to-end paper trading execution has occurred by
    showing the most recent trade, fill, and decision for the user.
    """
    try:
        from services.canonical import get_canonical_bot_counts, get_canonical_trade_counts

        counts = await get_canonical_bot_counts(user_id)

        trades_today = (await get_canonical_trade_counts(user_id))["today"]

        last_trade = await db.trades_collection.find_one(
            {"user_id": user_id},
            {"_id": 0, "timestamp": 1, "pair": 1, "side": 1, "amount": 1, "price": 1, "bot_id": 1},
            sort=[("timestamp", -1)],
        )

        last_fill = None
        if hasattr(db, 'fills_collection'):
            last_fill = await db.fills_collection.find_one(
                {"user_id": user_id},
                {"_id": 0, "timestamp": 1, "pair": 1, "side": 1},
                sort=[("timestamp", -1)],
            )

        return {
            "active_bots": counts.get("active", 0),
            "total_bots": counts.get("total", 0),
            "trades_today": trades_today,
            "last_trade": last_trade,
            "last_fill": last_fill,
            "execution_proven": trades_today > 0 or last_trade is not None,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as exc:
        logger.error(f"paper-activity error: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/go-live")
async def go_live_diagnostic(user_id: str = Depends(get_current_user)):
    """Consolidated go-live readiness check.

    Evaluates all subsystems needed for a confident go-live decision:
    - scheduler health
    - paper execution proof
    - reset cleanliness
    - risk status
    - heartbeat vitals
    - queue health
    """
    try:
        checks = {}
        blockers = []

        # 1. Scheduler health
        from trading_scheduler import trading_scheduler
        sched = trading_scheduler.get_health_snapshot()
        checks["scheduler"] = {
            "running": sched["scheduler_running"],
            "task_alive": sched["task_alive"],
            "last_tick_at": sched["last_tick_at"],
            "total_ticks": sched["total_ticks"],
            "total_trades_executed": sched["total_trades_executed"],
        }
        if not sched["scheduler_running"]:
            blockers.append("scheduler_not_running")
        if not sched["task_alive"]:
            blockers.append("scheduler_task_dead")

        # 2. Paper execution proof
        from services.canonical import get_canonical_trade_counts
        trades_today = (await get_canonical_trade_counts(user_id))["today"]
        last_trade_doc = await db.trades_collection.find_one(
            {"user_id": user_id},
            sort=[("timestamp", -1)],
            projection={"_id": 0, "timestamp": 1, "pair": 1, "side": 1, "profit_loss": 1},
        )
        checks["execution"] = {
            "trades_today": trades_today,
            "last_trade": last_trade_doc,
            "execution_proven": trades_today > 0 or last_trade_doc is not None,
        }

        # 3. Bot status
        total_bots = await db.bots_collection.count_documents({"user_id": user_id, "status": {"$ne": "deleted"}})
        active_bots = await db.bots_collection.count_documents({"user_id": user_id, "status": "active"})
        checks["bots"] = {"total": total_bots, "active": active_bots}
        if active_bots == 0:
            blockers.append("no_active_bots")

        # 4. Risk status
        try:
            from services.risk_lock_service import risk_lock_service as _rls
            locked, lock_reason = await _rls.is_locked_today(user_id)
        except Exception:
            locked, lock_reason = False, None
        modes = await db.system_modes_collection.find_one({"user_id": user_id}, {"_id": 0})
        emergency_stop = (modes or {}).get("emergencyStop", False)
        checks["risk"] = {
            "daily_loss_locked": locked,
            "lock_reason": lock_reason,
            "emergency_stop": emergency_stop,
        }
        if emergency_stop:
            blockers.append("emergency_stop_active")
        if locked:
            blockers.append("daily_loss_locked")

        # 5. Heartbeat vitals
        try:
            from services.autonomy_heartbeat import heartbeat_registry
            hb = heartbeat_registry.snapshot()
            sched_hb = hb.get("trading_scheduler", {})
            checks["heartbeat"] = {
                "trading_scheduler": sched_hb,
            }
            if sched_hb.get("last_error_at") and not sched_hb.get("last_ok_at"):
                blockers.append("scheduler_heartbeat_error_only")
        except Exception:
            checks["heartbeat"] = {"error": "heartbeat_registry_unavailable"}

        # 6. Queue health
        from engines.trade_staggerer import trade_staggerer as _ts
        queue_status = await _ts.get_queue_status()
        checks["queue"] = queue_status

        ready = len(blockers) == 0
        return {
            "ready": ready,
            "blockers": blockers,
            "checks": checks,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as exc:
        logger.error(f"go-live diagnostic error: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/subsystem-health")
async def get_subsystem_health(user_id: str = Depends(get_current_user)):
    """User-accessible subsystem health summary.

    Returns the live status of every key subsystem so users can immediately
    see what is healthy, degraded, or blocked — and why.  Includes a
    dependency chain so a single failed component's downstream impact is
    visible.

    Unlike /api/admin/truth/summary this endpoint is available to all
    authenticated users, not only admins.
    """
    # database already imported as db at module top
    try:
        now = datetime.now(timezone.utc)

        # ── 1. Scheduler health ────────────────────────────────────────────
        try:
            from trading_scheduler import trading_scheduler
            snap = trading_scheduler.get_health_snapshot()
            last_tick_at = snap.get("last_tick_at")
            lag_s = None
            if last_tick_at:
                try:
                    lt = datetime.fromisoformat(str(last_tick_at).replace("Z", "+00:00"))
                    lag_s = round((now - lt).total_seconds(), 1)
                except Exception:
                    lag_s = None
            sched_healthy = snap.get("running", False) and (lag_s is None or lag_s < 120)
            scheduler_status = {
                "healthy": sched_healthy,
                "status": "healthy" if sched_healthy else "stale",
                "last_tick_at": last_tick_at,
                "lag_seconds": lag_s,
                "total_ticks": snap.get("total_ticks", 0),
                "total_trades": snap.get("total_trades_executed", 0),
                "reason": None if sched_healthy else (
                    "Scheduler not running" if not snap.get("running") else
                    f"No tick in {lag_s}s (stale threshold: 120s)"
                ),
            }
        except Exception as _e:
            scheduler_status = {"healthy": False, "status": "error", "reason": str(_e)}

        # ── 2. WebSocket / realtime ────────────────────────────────────────
        try:
            ws_count = len(manager.active_connections) if hasattr(manager, "active_connections") else 0
            ws_status = {"healthy": True, "status": "healthy", "active_connections": ws_count, "reason": None}
        except Exception as _e:
            ws_status = {"healthy": False, "status": "error", "reason": str(_e)}

        # ── 3. Market intelligence ─────────────────────────────────────────
        try:
            recent_alert = await db.alerts_collection.find_one(
                {"user_id": user_id, "is_simulated": True},
                sort=[("created_at", -1)],
            )
            mi_degraded = recent_alert is not None
            mi_status = {
                "healthy": not mi_degraded,
                "status": "degraded" if mi_degraded else "healthy",
                "reason": (
                    "Recent market intelligence alerts flagged as simulated "
                    "(source unavailable / DNS failure)" if mi_degraded else None
                ),
                "last_simulated_alert": (recent_alert or {}).get("created_at"),
            }
        except Exception as _e:
            mi_status = {"healthy": False, "status": "error", "reason": str(_e)}

        # ── 4. Paper wallet ────────────────────────────────────────────────
        try:
            from services.paper_wallet_service import paper_wallet_service
            wallet = await paper_wallet_service.get_balances(user_id)
            total = wallet.get("total", 0)
            wallet_status = {
                "healthy": True,
                "status": "healthy",
                "total_zar": total,
                "funded": total > 0,
                "reason": None if total > 0 else "Paper wallet is empty — fund via Wallet Hub",
            }
        except Exception as _e:
            wallet_status = {"healthy": False, "status": "error", "reason": str(_e)}

        # ── 5. Exchange readiness ──────────────────────────────────────────
        try:
            # Use canonical exchange list from exchange_adapter (single source of truth)
            from services.exchange_adapter import SUPPORTED_EXCHANGES as _SX
            configured_exchanges = []
            for ex in _SX:
                key_doc = await db.api_keys_collection.find_one(
                    {"user_id": user_id, "provider": ex}
                )
                if key_doc and key_doc.get("api_key"):
                    configured_exchanges.append(ex)
            ex_status = {
                "healthy": len(configured_exchanges) > 0,
                "status": "healthy" if configured_exchanges else "no_keys",
                "configured_exchanges": configured_exchanges,
                "reason": None if configured_exchanges else "No exchange API keys configured",
            }
        except Exception as _e:
            ex_status = {"healthy": False, "status": "error", "reason": str(_e)}

        # ── 6. Risk locks ──────────────────────────────────────────────────
        try:
            from services.risk_lock_service import risk_lock_service
            daily_lock = await risk_lock_service.get_lock_status(user_id)
            from emergency_stop import emergency_stop_service
            es = await emergency_stop_service.get_status(user_id)
            global_disabled = es.get("global_disabled", False)
            daily_locked = daily_lock.get("daily_loss_lock_active", False)
            risk_ok = not global_disabled and not daily_locked
            risk_status = {
                "healthy": risk_ok,
                "status": "healthy" if risk_ok else "locked",
                "global_disabled": global_disabled,
                "daily_loss_lock": daily_locked,
                "reason": (
                    "Emergency/global disable is active" if global_disabled else
                    "Daily loss lock is active" if daily_locked else None
                ),
            }
        except Exception as _e:
            risk_status = {"healthy": False, "status": "error", "reason": str(_e)}

        # ── 7. Live-trading eligibility ────────────────────────────────────
        try:
            from routes.live_trading_gate import check_user_live_eligibility
            eligibility = await check_user_live_eligibility(user_id)
            live_status = {
                "healthy": eligibility.get("eligible", False),
                "status": "eligible" if eligibility.get("eligible") else "not_yet_eligible",
                "eligible": eligibility.get("eligible", False),
                "days_elapsed": (eligibility.get("statistics") or {}).get("days_elapsed"),
                "reasons": eligibility.get("reasons", []),
                "warnings": eligibility.get("warnings", []),
                "reason": (
                    None if eligibility.get("eligible") else
                    "; ".join(eligibility.get("reasons", ["Requirements not met"]))
                ),
            }
        except Exception as _e:
            live_status = {"healthy": False, "status": "error", "reason": str(_e)}

        # ── 8. Learning / training pipeline ────────────────────────────────
        try:
            perf_count = await db.performance_metrics_collection.count_documents(
                {"user_id": user_id}
            )
            training_count = await db.training_jobs_collection.count_documents(
                {"user_id": user_id}
            )
            learning_status = {
                "healthy": True,
                "status": "healthy" if perf_count > 0 else "no_data",
                "performance_metrics_count": perf_count,
                "training_jobs_count": training_count,
                "reason": (
                    None if perf_count > 0 else
                    "No performance metrics yet — will populate as bots trade"
                ),
            }
        except Exception as _e:
            learning_status = {"healthy": False, "status": "error", "reason": str(_e)}

        # ── Aggregate overall health ────────────────────────────────────────
        subsystems = {
            "scheduler": scheduler_status,
            "websocket": ws_status,
            "market_intelligence": mi_status,
            "paper_wallet": wallet_status,
            "exchange_keys": ex_status,
            "risk_locks": risk_status,
            "live_eligibility": live_status,
            "learning_pipeline": learning_status,
        }

        # Determine blocking chain: which failing subsystems block trading
        BLOCKS_TRADING = ("scheduler", "risk_locks")
        BLOCKS_LIVE = ("exchange_keys", "live_eligibility")

        trading_blockers = [
            k for k in BLOCKS_TRADING
            if not subsystems[k].get("healthy", True)
        ]
        live_blockers = [
            k for k in BLOCKS_LIVE
            if not subsystems[k].get("healthy", True)
        ]

        overall_healthy = all(v.get("healthy", True) for v in subsystems.values())

        return {
            "timestamp": now.isoformat(),
            "overall_healthy": overall_healthy,
            "trading_blocked": bool(trading_blockers),
            "trading_blockers": trading_blockers,
            "live_blocked": bool(live_blockers),
            "live_blockers": live_blockers,
            "subsystems": subsystems,
        }

    except Exception as exc:
        logger.error(f"Subsystem health error: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))


# ══════════════════════════════════════════════════════════════════════════════
# Trade quality + meaningful win diagnostics
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/trade-quality")
async def trade_quality_diagnostics(
    user_id: str = Depends(get_current_user),
    days: int = 7,
):
    """
    Canonical trade-quality diagnostics.

    Returns:
        meaningful_win_stats  — qualified_win_count, micro_win_count, loss_count,
                                meaningful_win_rate_pct, gross_win_rate_pct, net_win_rate_pct
        paper_floor_stats     — how many trades had paper_edge_floor_applied=True
        reject_reasons        — top reject reason codes with counts and percentages
        bot_reject_summary    — reject reason breakdown per bot_id
        exchange_reject_summary — reject reason breakdown per exchange
        policy_version        — active policy version
    """
    try:
        from datetime import datetime, timezone, timedelta
        from services.trading_brain_v2.trade_outcome_classifier import (
            classify_trade_outcome,
            build_outcome_counts,
            OUTCOME_LOSS,
            OUTCOME_MICRO_WIN,
            OUTCOME_QUALIFIED_WIN,
        )
        from services.trading_brain_v2.entry_thresholds import POLICY_VERSION

        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

        # ── Closed trades for win stats ──
        trades = await db.trades_collection.find(
            {"user_id": user_id, "status": "closed", "timestamp": {"$gte": cutoff}},
            {"_id": 0, "gross_pnl": 1, "net_pnl": 1, "bot_type": 1, "exchange": 1,
             "current_capital": 1, "notional": 1, "all_in_cost_bps": 1,
             "outcome_class": 1, "paper_edge_floor_applied": 1,
             "decision_reason_code": 1, "bot_id": 1},
        ).to_list(2000)

        # Classify any unclassified trades
        classified = []
        paper_floor_count = 0
        for t in trades:
            if not t.get("outcome_class"):
                result = classify_trade_outcome(
                    gross_pnl=float(t.get("gross_pnl") or 0),
                    net_pnl=float(t.get("net_pnl") or 0),
                    bot_type=t.get("bot_type", "normal"),
                    exchange=t.get("exchange", "luno"),
                    bot_equity=float(t.get("current_capital") or 0),
                    notional=float(t.get("notional") or 0),
                    all_in_cost_bps=float(t.get("all_in_cost_bps") or 25),
                )
                t["outcome_class"] = result["outcome_class"]
            classified.append(t)
            if t.get("paper_edge_floor_applied"):
                paper_floor_count += 1

        outcome_counts = build_outcome_counts(classified)

        # ── Reject reason aggregation ──
        rejected_trades = await db.trades_collection.find(
            {
                "user_id": user_id,
                "status": {"$in": ["rejected", "skipped", "blocked"]},
                "timestamp": {"$gte": cutoff},
            },
            {"_id": 0, "decision_reason_code": 1, "bot_id": 1, "exchange": 1},
        ).to_list(5000)

        reason_counts: dict = {}
        bot_reject: dict = {}
        exchange_reject: dict = {}
        for r in rejected_trades:
            code = str(r.get("decision_reason_code") or "UNKNOWN")
            bot_id = str(r.get("bot_id") or "unknown")
            exchange = str(r.get("exchange") or "unknown")
            reason_counts[code] = reason_counts.get(code, 0) + 1
            bot_reject.setdefault(bot_id, {})
            bot_reject[bot_id][code] = bot_reject[bot_id].get(code, 0) + 1
            exchange_reject.setdefault(exchange, {})
            exchange_reject[exchange][code] = exchange_reject[exchange].get(code, 0) + 1

        total_rejected = len(rejected_trades)
        reject_reasons = [
            {
                "reason_code": code,
                "count": count,
                "pct": round(count / total_rejected * 100, 1) if total_rejected else 0.0,
            }
            for code, count in sorted(reason_counts.items(), key=lambda x: -x[1])
        ]

        return {
            "meaningful_win_stats": outcome_counts,
            "paper_floor_stats": {
                "trades_with_floor": paper_floor_count,
                "total_closed_trades": len(trades),
                "paper_floor_usage_pct": round(paper_floor_count / len(trades) * 100, 1) if trades else 0.0,
            },
            "reject_reasons": reject_reasons,
            "reject_total": total_rejected,
            "bot_reject_summary": bot_reject,
            "exchange_reject_summary": exchange_reject,
            "policy_version": POLICY_VERSION,
            "days_window": days,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as exc:
        logger.error("trade_quality_diagnostics failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/scalper-regime")
async def scalper_regime_diagnostics(
    user_id: str = Depends(get_current_user),
    days: int = 7,
):
    """
    Scalper vs normal-bot regime block diagnostics.

    Returns a breakdown of how many times scalper bots were allowed vs blocked
    per regime, with explicit compatibility reason codes.

    Returns:
        scalper_regime_summary   — regime → {allowed_count, blocked_count, reason_codes}
        normal_regime_summary    — regime → {allowed_count, blocked_count}
        top_scalper_block_reasons — ranked list of scalper block reasons
        active_scalper_regimes   — regimes where scalpers are currently allowed
    """
    try:
        from services.trading_brain_v2.regime_scorer import STRATEGY_REGIME_MAP
        from services.regime_classifier import _STRATEGY_ALLOWED_REGIMES

        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

        # Fetch bot activity snapshots with regime data
        bots = await db.bots_collection.find(
            {
                "user_id": user_id,
                "status": {"$nin": ["deleted", "marked_for_deletion"]},
            },
            {"_id": 0, "id": 1, "bot_type": 1, "market_regime": 1,
             "canonical_market_regime": 1, "regime_confidence": 1,
             "last_decision_reason": 1, "last_entry_reason_code": 1},
        ).to_list(_MAX_BOTS_QUERY)

        scalper_bots = [b for b in bots if str(b.get("bot_type", "")).lower() == "scalper"]
        normal_bots = [b for b in bots if str(b.get("bot_type", "")).lower() != "scalper"]

        def _summarize_bots(bot_list, strategy):
            from services.trading_brain_v2.regime_scorer import RegimeScorerV2
            scorer = RegimeScorerV2()
            regime_summary: dict = {}
            for b in bot_list:
                regime = str(b.get("canonical_market_regime") or b.get("market_regime") or "unknown").lower()
                confidence = float(b.get("regime_confidence") or 0.0)
                elig = scorer.is_eligible(strategy, {"regime_label": regime, "regime_confidence": confidence})
                bucket = regime_summary.setdefault(regime, {
                    "allowed_count": 0, "blocked_count": 0, "reason_codes": {}
                })
                if elig.get("eligible"):
                    bucket["allowed_count"] += 1
                else:
                    bucket["blocked_count"] += 1
                rc = elig.get("compatibility_reason_code", "UNKNOWN")
                bucket["reason_codes"][rc] = bucket["reason_codes"].get(rc, 0) + 1
            return regime_summary

        scalper_summary = _summarize_bots(scalper_bots, "scalper")
        normal_summary = _summarize_bots(normal_bots, "normal")

        # Top scalper block reasons
        all_scalper_reasons: dict = {}
        for data in scalper_summary.values():
            for rc, cnt in data["reason_codes"].items():
                all_scalper_reasons[rc] = all_scalper_reasons.get(rc, 0) + cnt
        top_block_reasons = sorted(
            [{"reason_code": rc, "count": cnt} for rc, cnt in all_scalper_reasons.items()],
            key=lambda x: -x["count"],
        )

        return {
            "scalper_regime_summary": scalper_summary,
            "normal_regime_summary": normal_summary,
            "top_scalper_block_reasons": top_block_reasons,
            "active_scalper_regimes": sorted(STRATEGY_REGIME_MAP.get("scalper", set())),
            "scalper_bot_count": len(scalper_bots),
            "normal_bot_count": len(normal_bots),
            "days_window": days,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as exc:
        logger.error("scalper_regime_diagnostics failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/exit-distribution")
async def exit_distribution_diagnostics(
    user_id: str = Depends(get_current_user),
    days: int = 7,
):
    """
    Hold time and exit reason distribution for closed trades.

    Returns:
        exit_reason_counts      — count per exit reason code
        bot_type_avg_hold_s     — avg hold time in seconds per bot type
        exit_reason_pct         — percentage breakdown of exit reasons
        hold_percentiles        — p25/p50/p75/p90/p99 hold durations
        scalper_exit_breakdown  — exit reasons for scalper bots only
        normal_exit_breakdown   — exit reasons for normal bots only
    """
    try:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

        trades = await db.trades_collection.find(
            {"user_id": user_id, "status": "closed", "timestamp": {"$gte": cutoff}},
            {"_id": 0, "exit_reason": 1, "trade_close_reason": 1, "hold_seconds": 1,
             "hold_time_seconds": 1, "bot_type": 1, "created_at": 1, "closed_at": 1},
        ).to_list(5000)

        if not trades:
            return {
                "exit_reason_counts": {},
                "bot_type_avg_hold_s": {},
                "exit_reason_pct": {},
                "hold_percentiles": {},
                "scalper_exit_breakdown": {},
                "normal_exit_breakdown": {},
                "total_trades": 0,
                "days_window": days,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

        reason_counts: dict = {}
        bot_type_holds: dict = {}
        scalper_exits: dict = {}
        normal_exits: dict = {}
        hold_durations: list = []

        for t in trades:
            reason = str(
                t.get("exit_reason") or t.get("trade_close_reason") or "unknown"
            )
            bot_type = str(t.get("bot_type") or "normal").lower()
            hold_s = float(
                t.get("hold_seconds") or t.get("hold_time_seconds") or 0
            )

            reason_counts[reason] = reason_counts.get(reason, 0) + 1
            bot_type_holds.setdefault(bot_type, []).append(hold_s)
            if hold_s > 0:
                hold_durations.append(hold_s)

            if bot_type == "scalper":
                scalper_exits[reason] = scalper_exits.get(reason, 0) + 1
            else:
                normal_exits[reason] = normal_exits.get(reason, 0) + 1

        total = len(trades)
        exit_reason_pct = {
            r: round(c / total * 100, 1)
            for r, c in reason_counts.items()
        }

        avg_hold = {
            bt: round(sum(hs) / len(hs), 1)
            for bt, hs in bot_type_holds.items()
            if hs
        }

        # Compute percentiles
        percentiles = {}
        if hold_durations:
            sorted_h = sorted(hold_durations)
            n = len(sorted_h)
            for pct, label in [(25, "p25"), (50, "p50"), (75, "p75"), (90, "p90"), (99, "p99")]:
                idx = min(int(n * pct / 100), n - 1)
                percentiles[label] = round(sorted_h[idx], 1)

        return {
            "exit_reason_counts": reason_counts,
            "bot_type_avg_hold_s": avg_hold,
            "exit_reason_pct": exit_reason_pct,
            "hold_percentiles": percentiles,
            "scalper_exit_breakdown": scalper_exits,
            "normal_exit_breakdown": normal_exits,
            "total_trades": total,
            "days_window": days,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as exc:
        logger.error("exit_distribution_diagnostics failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/edge-realization")
async def edge_realization_diagnostics(
    user_id: str = Depends(get_current_user),
    days: int = 7,
):
    """
    Projected vs realized net profit diagnostics.

    Shows how well projected edge (at entry) translates to realized edge (at close).
    This surfaces systematic over-confidence in projected profit, especially when
    paper_edge_floor_applied=True inflated entry projections.

    Returns:
        avg_projected_net_profit     — average projected_net_profit at entry
        avg_realized_net_profit      — average actual net_pnl at close
        avg_implementation_shortfall — projected minus realized (per trade)
        paper_floor_inflation        — avg projected profit for floor-applied vs non-floor trades
        bot_type_shortfall           — shortfall breakdown per bot type
        exchange_shortfall           — shortfall breakdown per exchange
    """
    try:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

        trades = await db.trades_collection.find(
            {"user_id": user_id, "status": "closed", "timestamp": {"$gte": cutoff}},
            {"_id": 0, "projected_net_profit_quote": 1, "net_pnl": 1,
             "paper_edge_floor_applied": 1, "bot_type": 1, "exchange": 1},
        ).to_list(5000)

        if not trades:
            return {
                "avg_projected_net_profit": 0.0,
                "avg_realized_net_profit": 0.0,
                "avg_implementation_shortfall": 0.0,
                "paper_floor_inflation": {},
                "bot_type_shortfall": {},
                "exchange_shortfall": {},
                "total_trades": 0,
                "days_window": days,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

        projected_list: list = []
        realized_list: list = []
        floor_projected: list = []
        no_floor_projected: list = []
        bt_data: dict = {}
        ex_data: dict = {}

        for t in trades:
            proj = float(t.get("projected_net_profit_quote") or 0)
            real = float(t.get("net_pnl") or 0)
            floor_applied = bool(t.get("paper_edge_floor_applied"))
            bot_type = str(t.get("bot_type") or "normal")
            exchange = str(t.get("exchange") or "unknown")

            shortfall = proj - real
            projected_list.append(proj)
            realized_list.append(real)

            if floor_applied:
                floor_projected.append(proj)
            else:
                no_floor_projected.append(proj)

            bt_data.setdefault(bot_type, {"shortfalls": [], "projected": [], "realized": []})
            bt_data[bot_type]["shortfalls"].append(shortfall)
            bt_data[bot_type]["projected"].append(proj)
            bt_data[bot_type]["realized"].append(real)

            ex_data.setdefault(exchange, {"shortfalls": [], "projected": [], "realized": []})
            ex_data[exchange]["shortfalls"].append(shortfall)
            ex_data[exchange]["projected"].append(proj)
            ex_data[exchange]["realized"].append(real)

        def _avg(lst):
            return round(sum(lst) / len(lst), 6) if lst else 0.0

        bot_type_shortfall = {
            bt: {
                "avg_shortfall": _avg(d["shortfalls"]),
                "avg_projected": _avg(d["projected"]),
                "avg_realized": _avg(d["realized"]),
                "count": len(d["shortfalls"]),
            }
            for bt, d in bt_data.items()
        }
        exchange_shortfall = {
            ex: {
                "avg_shortfall": _avg(d["shortfalls"]),
                "avg_projected": _avg(d["projected"]),
                "avg_realized": _avg(d["realized"]),
                "count": len(d["shortfalls"]),
            }
            for ex, d in ex_data.items()
        }

        return {
            "avg_projected_net_profit": _avg(projected_list),
            "avg_realized_net_profit": _avg(realized_list),
            "avg_implementation_shortfall": _avg([p - r for p, r in zip(projected_list, realized_list)]),
            "paper_floor_inflation": {
                "avg_projected_with_floor": _avg(floor_projected),
                "avg_projected_without_floor": _avg(no_floor_projected),
                "floor_trade_count": len(floor_projected),
                "non_floor_trade_count": len(no_floor_projected),
            },
            "bot_type_shortfall": bot_type_shortfall,
            "exchange_shortfall": exchange_shortfall,
            "total_trades": len(trades),
            "days_window": days,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as exc:
        logger.error("edge_realization_diagnostics failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


# ══════════════════════════════════════════════════════════════════════════
# Policy pack diagnostics
# ══════════════════════════════════════════════════════════════════════════

@router.get("/policy-packs")
async def policy_pack_diagnostics(
    user_id: str = Depends(get_current_user),
    days: int = 7,
):
    """
    Policy pack diagnostics endpoint.

    Returns:
        available_packs          — all named packs with their parameters
        pack_summary             — lightweight summary of all packs
        bot_pack_assignments     — {bot_id: pack_name} for all active bots
        pack_scorecard           — per-pack scorecard aggregated from calibration records
        recommended_packs        — daily_evaluator recommendations per bot_type
        policy_pack_version      — POLICY_PACK_VERSION string
    """
    try:
        from services.trading_brain_v2.policy_packs import (
            ALL_PACKS, pack_summary, select_pack_for_bot, POLICY_PACK_VERSION,
        )
        from services.trading_brain_v2.trade_calibration import (
            compute_pack_scorecard, daily_evaluator,
        )
        from utils.bot_state import normalize_bot_state

        # ── Bot pack assignments ──
        bots = await db.bots_collection.find(
            {
                "user_id": user_id,
                "status": {"$nin": ["deleted", "marked_for_deletion"]},
                "deleted": {"$ne": True},
                "is_deleted": {"$ne": True},
            },
            {"_id": 0, "id": 1, "bot_type": 1, "policy_pack_name": 1, "policy_pack": 1},
        ).to_list(_MAX_BOTS_QUERY)

        bot_pack_assignments = {}
        for b in bots:
            bot_id = str(b.get("id") or "unknown")
            pack = select_pack_for_bot(b)
            bot_pack_assignments[bot_id] = {
                "pack_name":    pack["pack_name"],
                "pack_version": pack["pack_version"],
                "bot_type":     str(b.get("bot_type") or "normal"),
                "explicit":     bool(b.get("policy_pack_name") or b.get("policy_pack")),
            }

        # ── Calibration records for scorecard ──
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        cal_records = await db.trades_collection.find(
            {
                "user_id": user_id,
                "status": "closed",
                "calibration_complete": True,
                "timestamp": {"$gte": cutoff},
            },
            {
                "_id": 0,
                "outcome_class": 1, "policy_pack_name": 1,
                "realized_projection_ratio": 1, "hold_seconds": 1,
                "realized_net_profit_quote": 1, "paper_edge_floor_applied": 1,
                "exit_reason_code": 1, "bot_type": 1,
            },
        ).to_list(5000)

        # Group by pack_name for scorecards
        by_pack: dict = {}
        for r in cal_records:
            pn = str(r.get("policy_pack_name") or "unknown")
            by_pack.setdefault(pn, []).append(r)

        pack_scorecards = {
            pn: compute_pack_scorecard(records, pack_name=pn, window_days=days)
            for pn, records in by_pack.items()
        }

        # ── Recommendations per bot type ──
        recommendations: dict = {}
        for bt in ["normal", "scalper", "mean_reversion"]:
            rec = daily_evaluator(pack_scorecards, bot_type=bt, exchange="all")
            recommendations[bt] = {
                "recommended_pack": rec.get("recommended_pack_name"),
                "score":            rec.get("recommended_score"),
                "reasoning":        rec.get("reasoning"),
                "pack_scores":      rec.get("pack_scores", {}),
                "insufficient_packs": rec.get("insufficient_data_packs", []),
            }

        return {
            "available_packs":       list(ALL_PACKS.values()),
            "pack_summary":          pack_summary(),
            "bot_pack_assignments":  bot_pack_assignments,
            "pack_scorecards":       pack_scorecards,
            "recommended_packs":     recommendations,
            "policy_pack_version":   POLICY_PACK_VERSION,
            "calibration_days":      days,
            "timestamp":             datetime.now(timezone.utc).isoformat(),
        }
    except Exception as exc:
        logger.error("policy_pack_diagnostics failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/blockers")
async def get_trade_blockers(request: Request):
    """Return every gate that can block trade execution and its current status."""
    from utils.env_utils import env_bool
    from utils.trading_gates import check_trading_mode_enabled, check_autopilot_gates

    blockers: list[dict] = []

    # 1. Trading gates (any mode enabled)
    trading_ok, trading_reason = check_trading_mode_enabled()
    blockers.append({
        "gate_name": "trading_gates",
        "blocked": not trading_ok,
        "reason_code": "NO_TRADING_MODE" if not trading_ok else "OK",
        "human_readable": trading_reason,
        "required_fix": "Set PAPER_TRADING=1 or LIVE_TRADING=1" if not trading_ok else None,
    })

    # 2. Autopilot
    ap_ok, ap_reason = check_autopilot_gates()
    blockers.append({
        "gate_name": "autopilot",
        "blocked": not ap_ok,
        "reason_code": "AUTOPILOT_DISABLED" if not ap_ok else "OK",
        "human_readable": ap_reason,
        "required_fix": "Set AUTOPILOT_ENABLED=1 and enable a trading mode" if not ap_ok else None,
    })

    # 3. Emergency stop
    emergency = env_bool("EMERGENCY_STOP", False)
    blockers.append({
        "gate_name": "emergency_stop",
        "blocked": emergency,
        "reason_code": "EMERGENCY_STOP_ACTIVE" if emergency else "OK",
        "human_readable": "Emergency stop is ACTIVE — all trading halted" if emergency else "Emergency stop not active",
        "required_fix": "Set EMERGENCY_STOP=0 to resume trading" if emergency else None,
    })

    # 4. Paper trading
    paper_on = env_bool("PAPER_TRADING", False)
    blockers.append({
        "gate_name": "paper_trading",
        "blocked": not paper_on,
        "reason_code": "PAPER_TRADING_OFF" if not paper_on else "OK",
        "human_readable": "Paper trading is disabled" if not paper_on else "Paper trading enabled",
        "required_fix": "Set PAPER_TRADING=1 to enable paper trading" if not paper_on else None,
    })

    # 5. Live trading
    live_on = env_bool("LIVE_TRADING", False)
    blockers.append({
        "gate_name": "live_trading",
        "blocked": not live_on,
        "reason_code": "LIVE_TRADING_OFF" if not live_on else "OK",
        "human_readable": "Live trading is disabled" if not live_on else "Live trading enabled",
        "required_fix": "Set LIVE_TRADING=1 to enable live trading" if not live_on else None,
    })

    # 6. Wallet check (paper wallet service available)
    wallet_ok = True
    wallet_reason = "Paper wallet service available"
    try:
        from services.paper_wallet_service import paper_wallet_service
        await paper_wallet_service.init_db()
    except Exception as exc:
        wallet_ok = False
        wallet_reason = f"Paper wallet unavailable: {exc}"
    blockers.append({
        "gate_name": "wallet",
        "blocked": not wallet_ok,
        "reason_code": "WALLET_UNAVAILABLE" if not wallet_ok else "OK",
        "human_readable": wallet_reason,
        "required_fix": "Check database connectivity and wallet collection" if not wallet_ok else None,
    })

    # 7. Edge gate
    try:
        from config import EDGE_GATE_PAPER, EDGE_GATE_LIVE
    except ImportError:
        EDGE_GATE_PAPER, EDGE_GATE_LIVE = False, False
    edge_active = EDGE_GATE_PAPER or EDGE_GATE_LIVE
    blockers.append({
        "gate_name": "edge_gate",
        "blocked": edge_active,
        "reason_code": "EDGE_GATE_ACTIVE" if edge_active else "OK",
        "human_readable": (
            f"Edge gate active (paper={EDGE_GATE_PAPER}, live={EDGE_GATE_LIVE}) — "
            "low-edge trades will be rejected"
        ) if edge_active else "Edge gate inactive",
        "required_fix": "Set EDGE_GATE_PAPER=false / EDGE_GATE_LIVE=false to relax" if edge_active else None,
    })

    # 8. Confidence gate
    confidence_on = env_bool("CONFIDENCE_GATE", False)
    blockers.append({
        "gate_name": "confidence_gate",
        "blocked": confidence_on,
        "reason_code": "CONFIDENCE_GATE_ACTIVE" if confidence_on else "OK",
        "human_readable": "Confidence gate active — low-confidence signals rejected" if confidence_on else "Confidence gate inactive",
        "required_fix": "Set CONFIDENCE_GATE=0 to disable" if confidence_on else None,
    })

    active_blockers = [b for b in blockers if b["blocked"]]
    return {
        "blockers": blockers,
        "total_gates": len(blockers),
        "active_blockers": len(active_blockers),
        "trading_possible": not any(
            b["blocked"] for b in blockers
            if b["gate_name"] in ("trading_gates", "emergency_stop")
        ),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# ── Policy Performance ────────────────────────────────────────────────────


@router.get("/policy-performance")
async def get_policy_performance(request: Request):
    """Per-pack performance scorecards with outcome classification."""
    try:
        from services.policy_performance_engine import get_pack_performance

        # Extract user_id from query params if present (optional filter)
        user_id = request.query_params.get("user_id")
        result = await get_pack_performance(user_id=user_id)
        return result
    except Exception as exc:
        logger.error("policy-performance error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


# ── Dashboard Truth ───────────────────────────────────────────────────────


@router.get("/dashboard-truth")
async def get_dashboard_truth(request: Request):
    """Canonical dashboard truth: win rates, quality metrics, calibration stats."""
    try:
        from services.trading_brain_v2.trade_outcome_classifier import build_outcome_counts
        from services.trading_brain_v2.trade_calibration import compute_pack_scorecard
        from services.trading_brain_v2.policy_packs import get_default_pack_for_bot_type

        user_id = request.query_params.get("user_id")
        query: dict = {"status": "closed"}
        if user_id:
            query["user_id"] = user_id

        trades = await db.trades_collection.find(
            query, {"_id": 0},
        ).sort("closed_at", -1).to_list(5000)

        # Outcome counts
        trade_quality_metrics = build_outcome_counts(trades)

        # Calibration stats — build lightweight calibration records
        calibration_records = []
        for t in trades:
            projected = float(t.get("projected_net_profit_quote", 0) or 0)
            realized = float(t.get("net_pnl", t.get("profit_loss", 0)) or 0)
            ratio = max(-3.0, min(3.0, realized / projected)) if projected > 0 else None
            calibration_records.append({
                "calibration_complete": True,
                "outcome_class": t.get("outcome_class", "LOSS" if realized <= 0 else "QUALIFIED_WIN"),
                "realized_projection_ratio": ratio,
                "hold_seconds": t.get("hold_seconds"),
                "realized_net_profit_quote": realized,
                "paper_edge_floor_applied": t.get("paper_edge_floor_applied", False),
                "exit_reason_code": t.get("trade_close_reason", "unknown"),
            })

        # Active policy pack (from first active bot, or default)
        active_bot = await db.bots_collection.find_one(
            {"status": {"$in": ["active", "running"]}},
            {"_id": 0, "policy_pack_name": 1, "bot_type": 1},
        )
        if active_bot and active_bot.get("policy_pack_name"):
            policy_pack_in_use = active_bot["policy_pack_name"]
        else:
            bt = (active_bot or {}).get("bot_type", "normal")
            policy_pack_in_use = get_default_pack_for_bot_type(bt)["pack_name"]

        scorecard = compute_pack_scorecard(
            calibration_records, pack_name=policy_pack_in_use,
        )

        return {
            "qualified_win_rate": trade_quality_metrics.get("meaningful_win_rate_pct", 0.0),
            "micro_win_rate": round(
                trade_quality_metrics["micro_win_count"] / trade_quality_metrics["total_trades"] * 100, 2
            ) if trade_quality_metrics["total_trades"] > 0 else 0.0,
            "total_win_rate": trade_quality_metrics.get("net_win_rate_pct", 0.0),
            "policy_pack_in_use": policy_pack_in_use,
            "trade_quality_metrics": trade_quality_metrics,
            "calibration_stats": scorecard,
            "total_closed_trades": len(trades),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as exc:
        logger.error("dashboard-truth error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))


# ── Self-Learning Recommendations ─────────────────────────────────────────


@router.get("/smtp-test")
async def smtp_test(user_id: str = Depends(get_current_user)):
    """
    Live SMTP probe — verifies config, TCP connect, STARTTLS, and login.

    Does NOT send any email.  Returns step-by-step results so ops can
    pinpoint exactly where SMTP breaks (missing config / bad host / bad creds).

    Steps tested
    ------------
    1. config_present  – SMTP_HOST, SMTP_USER, SMTP_PASSWORD all non-empty
    2. tcp_connect     – TCP socket to SMTP_HOST:SMTP_PORT within 10 s
    3. starttls        – EHLO + STARTTLS negotiation
    4. login           – AUTH LOGIN with SMTP_USER / SMTP_PASSWORD
    """
    import smtplib
    import socket
    import config as _cfg

    result: Dict = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "smtp_host": _cfg.SMTP_HOST or None,
        "smtp_port": _cfg.SMTP_PORT,
        "smtp_user": _cfg.SMTP_USER or None,
        "from_email": _cfg.FROM_EMAIL or None,
        "steps": {},
        "overall": "fail",
    }

    steps = result["steps"]

    # ── Step 1: config present ─────────────────────────────────────────────
    config_ok = bool(_cfg.SMTP_HOST and _cfg.SMTP_USER and _cfg.SMTP_PASSWORD)
    steps["config_present"] = {
        "ok": config_ok,
        "detail": (
            "All required SMTP env vars set" if config_ok else
            "One or more of SMTP_HOST / SMTP_USER / SMTP_PASSWORD is blank"
        ),
    }
    if not config_ok:
        result["overall"] = "fail"
        return result

    # ── Step 2: TCP connect ────────────────────────────────────────────────
    tcp_ok = False
    tcp_detail = ""
    try:
        sock = socket.create_connection((_cfg.SMTP_HOST, _cfg.SMTP_PORT), timeout=10)
        sock.close()
        tcp_ok = True
        tcp_detail = f"Connected to {_cfg.SMTP_HOST}:{_cfg.SMTP_PORT}"
    except Exception as exc:
        tcp_detail = f"TCP connect failed: {exc}"
    steps["tcp_connect"] = {"ok": tcp_ok, "detail": tcp_detail}
    if not tcp_ok:
        result["overall"] = "fail"
        return result

    # ── Steps 3 & 4: STARTTLS + login ─────────────────────────────────────
    tls_ok = False
    tls_detail = ""
    login_ok = False
    login_detail = ""
    try:
        with smtplib.SMTP(_cfg.SMTP_HOST, _cfg.SMTP_PORT, timeout=15) as server:
            server.ehlo()
            server.starttls()
            tls_ok = True
            tls_detail = "STARTTLS negotiated"
            try:
                server.login(_cfg.SMTP_USER, _cfg.SMTP_PASSWORD)
                login_ok = True
                login_detail = f"Authenticated as {_cfg.SMTP_USER}"
            except smtplib.SMTPAuthenticationError as exc:
                login_detail = f"AUTH failed: {exc}"
            except Exception as exc:
                login_detail = f"Login error: {exc}"
    except smtplib.SMTPException as exc:
        tls_detail = f"STARTTLS failed: {exc}"
    except Exception as exc:
        tls_detail = f"SMTP error: {exc}"

    steps["starttls"] = {"ok": tls_ok, "detail": tls_detail}
    steps["login"] = {"ok": login_ok, "detail": login_detail}

    all_ok = config_ok and tcp_ok and tls_ok and login_ok
    result["overall"] = "pass" if all_ok else "fail"
    return result


@router.get("/keys-detail")
async def keys_detail(user_id: str = Depends(get_current_user)):
    """
    Per-provider API key diagnostics.

    For each supported provider returns:
      present     – key document exists in DB
      source      – "db" (keys stored in MongoDB) or "env" (legacy)
      decryptable – whether the stored ciphertext can be decrypted
      test_ok     – last stored test result (true / false / null = untested)
      last_tested – ISO timestamp of last test, or null
      last_error  – last test error message, or null

    Covers all 11 providers tracked in the keys.py router.
    """
    PROVIDERS = [
        "luno", "binance", "kucoin", "bybit", "kraken", "bitget", "gate",
        "openai", "coinstats", "huggingface", "coingecko",
    ]

    try:
        from routes.api_key_management import decrypt_api_key
    except Exception:
        decrypt_api_key = None

    out = {}
    for provider in PROVIDERS:
        key_doc = await db.api_keys_collection.find_one(
            {"user_id": user_id, "provider": provider},
            {"_id": 0, "api_key_encrypted": 1, "status": 1,
             "last_tested_at": 1, "last_test_ok": 1, "last_test_error": 1},
        )

        present = bool(key_doc and key_doc.get("api_key_encrypted"))

        decryptable = None  # type: Optional[bool]
        if present and decrypt_api_key is not None:
            try:
                decrypt_api_key(key_doc["api_key_encrypted"])
                decryptable = True
            except Exception:
                decryptable = False

        raw_test = key_doc.get("last_test_ok") if key_doc else None
        # Normalise legacy string values
        if raw_test == "test_ok":
            raw_test = True
        elif raw_test == "test_failed":
            raw_test = False

        out[provider] = {
            "present": present,
            "source": "db" if present else None,
            "decryptable": decryptable,
            "test_ok": raw_test,
            "last_tested": key_doc.get("last_tested_at") if key_doc else None,
            "last_error": key_doc.get("last_test_error") if key_doc else None,
        }

    exchange_providers = ["luno", "binance", "kucoin", "bybit", "kraken", "bitget", "gate"]
    exchanges_present = [p for p in exchange_providers if out[p]["present"]]
    exchanges_valid = [p for p in exchange_providers if out[p].get("test_ok") is True]

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "providers": out,
        "summary": {
            "exchanges_present": exchanges_present,
            "exchanges_valid": exchanges_valid,
            "any_exchange_ready": len(exchanges_present) > 0,
        },
    }


@router.get("/learning-readiness")
async def learning_readiness():
    """
    Learning and retrain readiness — no auth required for smoke tests.

    Returns:
      learning_enabled   – value of ENABLE_LEARNING_LOOP env var
      xgb_model_present  – whether models/xgb_predictor.json exists on disk
      river_dir_present  – whether models/river/ directory exists
      timer_active       – systemd amarktai-retrain.timer is-active
      timer_enabled      – systemd amarktai-retrain.timer is-enabled
      timer_next_run     – next trigger time from systemctl show (or null)
    """
    from pathlib import Path
    import subprocess

    backend_dir = Path(__file__).resolve().parent.parent
    model_dir = backend_dir / "models"
    xgb_path = model_dir / "xgb_predictor.json"
    river_dir = model_dir / "river"

    learning_enabled = os.getenv("ENABLE_LEARNING_LOOP", "false").lower() == "true"
    xgb_present = xgb_path.exists()
    river_present = river_dir.is_dir()

    def _systemctl(args: list) -> str:
        try:
            r = subprocess.run(
                ["systemctl"] + args,
                capture_output=True, text=True, timeout=5
            )
            return r.stdout.strip()
        except Exception:
            return "unknown"

    timer_active = _systemctl(["is-active", "amarktai-retrain.timer"])
    timer_enabled = _systemctl(["is-enabled", "amarktai-retrain.timer"])

    timer_next_run = None  # type: Optional[str]
    try:
        raw = _systemctl(["show", "amarktai-retrain.timer", "--property=NextElapseUSecRealtime"])
        if "=" in raw:
            timer_next_run = raw.split("=", 1)[1].strip() or None
    except Exception:
        pass

    overall_ready = (
        xgb_present
        and river_present
        and timer_active == "active"
        and timer_enabled == "enabled"
    )

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "learning_enabled": learning_enabled,
        "xgb_model_present": xgb_present,
        "xgb_model_path": str(xgb_path),
        "river_dir_present": river_present,
        "river_dir_path": str(river_dir),
        "timer_active": timer_active,
        "timer_enabled": timer_enabled,
        "timer_next_run": timer_next_run,
        "overall_ready": overall_ready,
        "notes": {
            "xgb_missing": (
                None if xgb_present else
                "Normal on fresh install — XGBoost trains at 02:00 UTC once "
                "ENABLE_LEARNING_LOOP=true and ≥50 closed trades exist."
            ),
            "timer_inactive": (
                None if timer_active == "active" else
                "Run: sudo systemctl enable --now amarktai-retrain.timer"
            ),
        },
    }


@router.get("/self-learning")
async def get_self_learning_recommendations(request: Request):
    """Self-learning pack recommendations using daily_evaluator."""
    try:
        from services.trading_brain_v2.trade_calibration import (
            compute_pack_scorecard,
            daily_evaluator,
        )
        from services.trading_brain_v2.policy_packs import ALL_PACKS

        user_id = request.query_params.get("user_id")
        bot_type = request.query_params.get("bot_type", "normal")
        exchange = request.query_params.get("exchange", "")

        query: dict = {"status": "closed"}
        if user_id:
            query["user_id"] = user_id

        trades = await db.trades_collection.find(
            query, {"_id": 0},
        ).sort("closed_at", -1).to_list(5000)

        # Group by pack and build scorecards
        pack_trades: Dict[str, list] = {}
        for t in trades:
            pack_name = t.get("policy_pack_name") or t.get("policy_pack") or "balanced"
            pack_trades.setdefault(pack_name, []).append(t)

        scorecards: Dict[str, dict] = {}
        for pack_name, pack_list in pack_trades.items():
            records = []
            for t in pack_list:
                projected = float(t.get("projected_net_profit_quote", 0) or 0)
                realized = float(t.get("net_pnl", t.get("profit_loss", 0)) or 0)
                ratio = max(-3.0, min(3.0, realized / projected)) if projected > 0 else None
                records.append({
                    "calibration_complete": True,
                    "outcome_class": t.get("outcome_class", "LOSS" if realized <= 0 else "QUALIFIED_WIN"),
                    "realized_projection_ratio": ratio,
                    "hold_seconds": t.get("hold_seconds"),
                    "realized_net_profit_quote": realized,
                    "paper_edge_floor_applied": t.get("paper_edge_floor_applied", False),
                    "exit_reason_code": t.get("trade_close_reason", "unknown"),
                })
            scorecards[pack_name] = compute_pack_scorecard(records, pack_name=pack_name)

        recommendation = daily_evaluator(
            scorecards,
            bot_type=bot_type,
            exchange=exchange,
        )

        return {
            "recommendation": recommendation,
            "scorecards": scorecards,
            "bot_type": bot_type,
            "exchange": exchange,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as exc:
        logger.error("self-learning error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))
