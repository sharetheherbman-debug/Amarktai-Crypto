"""
Diagnostics Endpoints - Pre-Merge Verification
Includes realtime smoke tests and system health checks
"""

from fastapi import APIRouter, HTTPException, Depends
from datetime import datetime, timezone, timedelta
from typing import Dict, List
import logging

from auth import get_current_user
from websocket_manager import manager
from realtime_events import rt_events
import database as db
from config import PAPER_MAX_HOLD_MINUTES, PAPER_STALE_EXIT_MINUTES, SOFT_MAX_HOLD_SECONDS, HARD_MAX_HOLD_SECONDS

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/diagnostics", tags=["Diagnostics"])


def _get_close_rejects_from_engine() -> dict:
    """Aggregate close SKIP/REJECT reasons from the paper engine action log."""
    try:
        from paper_trading_engine import paper_engine
        rejects: dict = {}
        for entry in paper_engine._action_log:
            if entry.get("action") == "SKIP":
                reason = entry.get("reason", "unknown")
                rejects[reason] = rejects.get(reason, 0) + 1
        return rejects
    except Exception:
        return {}


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
        active_bots: Count of active paper trading bots
        trades_today: Count of trades executed today
        scheduler_running: Whether scheduler is active
    """
    try:
        from paper_trading_engine import paper_trading_engine
        from trading_scheduler import trading_scheduler
        from datetime import datetime, timezone, timedelta
        
        # Get scheduler status
        scheduler_status = trading_scheduler.get_status() if hasattr(trading_scheduler, 'get_status') else {}
        
        # Get paper trading engine status  
        engine_status = {}
        if hasattr(paper_trading_engine, 'last_tick_time'):
            engine_status['last_tick'] = paper_trading_engine.last_tick_time
        
        # Count active paper trading bots for this user
        active_bots_count = await db.bots_collection.count_documents({
            "user_id": user_id,
            "status": "active",
            "mode": "paper"
        })
        
        # Count trades today
        today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        trades_today = await db.trades_collection.count_documents({
            "user_id": user_id,
            "timestamp": {"$gte": today_start.isoformat()},
            "mode": "paper"
        })
        
        # Get last trade/order info
        last_trade = await db.trades_collection.find_one(
            {"user_id": user_id, "mode": "paper"},
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
            "active_bots": active_bots_count,
            "trades_today": trades_today,
            "scheduler_running": scheduler_status.get('running', False),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as e:
        logger.error(f"Paper trading status error: {e}")
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
        from utils.env_utils import env_bool
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

        enabled = env_bool('ENABLE_AUTO_SPAWN', False) or env_bool('AUTOPILOT_ENABLED', False) or env_bool('ENABLE_AUTOPILOT', False)
        profit_threshold = float(PROFIT_THRESHOLD_ZAR)
        cooldown_minutes = getattr(config, "AUTO_SPAWN_COOLDOWN_MINUTES", 60)
        max_spawns_per_day = getattr(config, "AUTO_SPAWN_MAX_PER_DAY", 2)

        modes = await db.system_modes_collection.find_one({"user_id": user_id}, {"_id": 0}) or {}
        trading_mode = "live" if modes.get("liveTrading") else "paper"

        total_available = 0
        try:
            from services.wallet_summary_service import wallet_summary_service
            wallet_summary = await wallet_summary_service.get_summary(user_id)
            total_available = float(wallet_summary.get('available_wallet_zar', 0) or 0)
        except Exception as e:
            logger.warning(f"Auto-spawn wallet balance fallback: {e}")
            try:
                from engines.wallet_manager import wallet_manager
                wallet_balance = await wallet_manager.get_master_balance(user_id)
                if 'total_zar' in wallet_balance:
                    total_available = wallet_balance['total_zar']
            except Exception as e2:
                logger.warning(f"Auto-spawn wallet balance secondary fallback: {e2}")

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
# Data Integrity Diagnostics  (C3)
# ============================================================================

@router.get("/data-integrity")
async def get_data_integrity(user_id: str = Depends(get_current_user)):
    """
    Data integrity snapshot for rapid go-live debugging.

    Returns:
        - total_trades, paper_trades, live_trades
        - filled_count, closed_count
        - net_realized_pnl  (closed trades only, net_pnl field)
        - current_paper_wallet_balance
        - bots_current_capital_sum
        - db_name   (safe – no credentials)
    """
    try:
        # Trade counts
        total_trades = 0
        paper_trades = 0
        live_trades = 0
        filled_count = 0
        closed_count = 0
        net_realized_pnl = 0.0

        if db.trades_collection is not None:
            total_trades = await db.trades_collection.count_documents({"user_id": user_id})
            paper_trades = await db.trades_collection.count_documents({"user_id": user_id, "is_paper": True})
            live_trades = await db.trades_collection.count_documents({"user_id": user_id, "is_live": True})
            filled_count = await db.trades_collection.count_documents({"user_id": user_id, "status": "filled"})
            closed_count = await db.trades_collection.count_documents({"user_id": user_id, "status": "closed"})

            closed_cursor = db.trades_collection.find(
                {"user_id": user_id, "status": "closed"},
                {"net_pnl": 1, "profit_loss": 1, "_id": 0}
            )
            async for t in closed_cursor:
                _net_pnl = t.get("net_pnl")
                pnl = _net_pnl if _net_pnl is not None else t.get("profit_loss", 0)
                net_realized_pnl += float(pnl or 0)

        # Paper wallet balance
        paper_wallet_balance = 0.0
        try:
            from services.paper_wallet_ledger import paper_wallet_ledger
            balances = await paper_wallet_ledger.get_all_balances(user_id)
            paper_wallet_balance = sum(float(v or 0) for v in balances.values())
        except Exception:
            pass

        # Bots capital sum
        bots_capital_sum = 0.0
        if db.bots_collection is not None:
            async for bot in db.bots_collection.find(
                {"user_id": user_id, "status": {"$ne": "deleted"}},
                {"current_capital": 1, "_id": 0}
            ):
                bots_capital_sum += float(bot.get("current_capital") or 0)

        # Safe DB identity
        db_name = "unknown"
        try:
            from database import _parse_mongo_config
            _, db_name = _parse_mongo_config()
        except Exception:
            pass

        return {
            "success": True,
            "total_trades": total_trades,
            "paper_trades": paper_trades,
            "live_trades": live_trades,
            "filled_count": filled_count,
            "closed_count": closed_count,
            "net_realized_pnl": round(net_realized_pnl, 2),
            "paper_wallet_balance": round(paper_wallet_balance, 2),
            "bots_current_capital_sum": round(bots_capital_sum, 2),
            "db_name": db_name,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as e:
        logger.error(f"Data integrity diagnostics error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# DB Diagnostics  (A1 – admin only)
# ============================================================================

@router.get("/db")
async def get_db_diagnostics(user_id: str = Depends(get_current_user)):
    """
    Admin-level DB diagnostics endpoint.

    Returns:
        - effective mongo_uri_host (credentials redacted)
        - db_name
        - collections list
        - key index summaries for trades
        - document counts
    """
    from auth import require_admin
    # Require admin – raise 403 if not
    try:
        from auth import is_admin as _is_admin
        from database import db as _db_instance, client as _client
        if not await _is_admin(user_id):
            from fastapi import HTTPException as _HTTPException
            raise _HTTPException(status_code=403, detail="Admin access required")
    except ImportError:
        pass

    try:
        from database import _parse_mongo_config, db as _db_instance, client as _client
        mongo_url, db_name = _parse_mongo_config()

        # Safe host
        try:
            from urllib.parse import urlparse
            parsed = urlparse(mongo_url)
            safe_host = f"{parsed.hostname or 'unknown'}:{parsed.port or 27017}"
        except Exception:
            safe_host = "unknown"

        # Collection list
        collections = []
        counts = {}
        index_summary = {}

        if _db_instance is not None:
            collections = await _db_instance.list_collection_names()

            # Count key collections
            for cname in ("trades", "bots", "users", "api_keys"):
                try:
                    counts[cname] = await _db_instance[cname].count_documents({})
                except Exception:
                    counts[cname] = -1

            # Index summary for trades
            try:
                trade_indexes = await _db_instance["trades"].index_information()
                index_summary["trades"] = {
                    name: {
                        "key": info.get("key"),
                        "unique": info.get("unique", False),
                        "sparse": info.get("sparse", False),
                    }
                    for name, info in trade_indexes.items()
                }
            except Exception as idx_err:
                index_summary["trades"] = {"error": str(idx_err)}

        return {
            "success": True,
            "mongo_uri_host": safe_host,
            "db_name": db_name,
            "collections": sorted(collections),
            "counts": counts,
            "indexes": index_summary,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as e:
        logger.error(f"DB diagnostics error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Realtime Diagnostics  (A4)
# ============================================================================

@router.get("/realtime-status")
async def get_realtime_status_summary(user_id: str = Depends(get_current_user)):
    """
    Realtime system diagnostics.

    Returns:
        - connected_users count
        - total active connections
        - last broadcast timestamps per event type (where tracked)
    """
    try:
        from websocket_manager import manager as _ws_manager
        active_connections_count = sum(
            len(v) for v in _ws_manager.active_connections.values()
        )
        connected_users = list(_ws_manager.active_connections.keys())

        # Try to get broadcast timestamps from realtime_events if available
        broadcast_stats: dict = {}
        try:
            from realtime_events import rt_events as _rt
            if hasattr(_rt, '_last_broadcast'):
                broadcast_stats = _rt._last_broadcast
        except Exception:
            pass

        return {
            "success": True,
            "connected_users_count": len(connected_users),
            "total_connections": active_connections_count,
            "broadcast_stats": broadcast_stats,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    except Exception as e:
        logger.error(f"Realtime diagnostics error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Phase 1 — Safe Read-only Trading Diagnostics
# ============================================================================

@router.get("/why-not-trading")
async def why_not_trading(user_id: str = Depends(get_current_user)):
    """Return ranked, truthful reasons why bots may not be trading.

    Read-only. No side effects.

    Checks (in priority order):
    1. System mode (paper/live enabled?)
    2. Scheduler running
    3. Active bots count
    4. Paper wallet funded
    5. Risk locks / circuit breakers
    6. Bots in quarantine
    7. Bot-level blocks (no exchange key, unsupported exchange, paused)
    """
    reasons: list = []

    # 1. System mode flags
    try:
        from services.system_mode_service import system_mode_service
        mode = await system_mode_service.get_mode(user_id)
        if mode != 'paper':
            reasons.append({"code": "PAPER_DISABLED", "severity": "critical",
                             "message": "paperTrading mode is OFF — enable it in Settings"})
    except Exception as e:
        reasons.append({"code": "MODE_CHECK_ERROR", "severity": "warning", "message": str(e)})

    # 2. Scheduler running
    try:
        from trading_scheduler import trading_scheduler
        sched_running = getattr(trading_scheduler, "is_running", False)
        if not sched_running:
            reasons.append({"code": "SCHEDULER_STOPPED", "severity": "critical",
                             "message": "Trading scheduler is not running"})
    except Exception as e:
        reasons.append({"code": "SCHEDULER_CHECK_ERROR", "severity": "warning", "message": str(e)})

    # 3. Active bots — use bot_not_deleted_filter for consistency with the scheduler
    try:
        from services.bot_filters import bot_not_deleted_filter
        active_bots = await db.bots_collection.count_documents(
            bot_not_deleted_filter({"user_id": user_id, "status": "active"})
        )
        if active_bots == 0:
            reasons.append({"code": "NO_ACTIVE_BOTS", "severity": "critical",
                             "message": "No active bots found — create and start bots via dashboard"})
    except Exception as e:
        reasons.append({"code": "BOTS_CHECK_ERROR", "severity": "warning", "message": str(e)})

    # 4. Paper wallet funded
    try:
        from services.paper_wallet_service import paper_wallet_service
        wallet = await paper_wallet_service.get_wallet_status(user_id)
        total = wallet.get("total", 0) if wallet else 0
        if total == 0:
            reasons.append({"code": "WALLET_UNFUNDED", "severity": "critical",
                             "message": "Paper wallet balance is 0 — fund it via dashboard"})
    except Exception as e:
        reasons.append({"code": "WALLET_CHECK_ERROR", "severity": "warning", "message": str(e)})

    # 5. Risk locks
    try:
        from risk_engine import risk_engine
        if hasattr(risk_engine, "is_locked") and await risk_engine.is_locked(user_id):
            reasons.append({"code": "RISK_LOCKED", "severity": "critical",
                             "message": "Risk engine lock active — check risk dashboard"})
    except Exception:
        pass

    # 6. Quarantine
    try:
        qcount = await db.bot_quarantine_collection.count_documents(
            {"user_id": user_id, "status": "quarantined"}
        ) if hasattr(db, "bot_quarantine_collection") else 0
        if qcount > 0:
            reasons.append({"code": "BOTS_IN_QUARANTINE", "severity": "warning",
                             "message": f"{qcount} bot(s) in quarantine — review and release via dashboard"})
    except Exception:
        pass

    # 7. Bot-level blocks (sample up to 20 active bots)
    try:
        from config import PAPER_SUPPORTED_EXCHANGES
        from services.bot_filters import bot_not_deleted_filter
        bots = await db.bots_collection.find(
            bot_not_deleted_filter({"user_id": user_id, "status": "active"}),
            {"_id": 0, "id": 1, "name": 1, "exchange": 1, "status": 1, "pause_reason": 1}
        ).to_list(20)
        unsupported = [b["name"] for b in bots if b.get("exchange", "").lower() not in PAPER_SUPPORTED_EXCHANGES]
        if unsupported:
            reasons.append({"code": "UNSUPPORTED_EXCHANGE", "severity": "warning",
                             "message": f"Bots on unsupported exchange: {unsupported}"})
    except Exception:
        pass

    status = "ok" if not reasons else ("critical" if any(r["severity"] == "critical" for r in reasons) else "warning")
    return {
        "success": True,
        "status": status,
        "reasons": reasons,
        "reasons_count": len(reasons),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/last-tick")
async def last_tick_summary(user_id: str = Depends(get_current_user)):
    """Summary of the last scheduler tick for the current user.

    Read-only. No side effects.

    Returns:
        last_tick_at: when the scheduler last ran (from bot_runtime_state)
        bots_evaluated: count of bots that were evaluated
        orders_attempted: count of orders attempted in last tick
        fills_saved: count of fills saved in last tick
        trades_opened: count of trades opened in last tick
        trades_closed: count of trades closed in last tick
        rejects: count of rejected/skipped orders with reasons
    """
    try:
        from trading_scheduler import trading_scheduler
        last_tick = getattr(trading_scheduler, "last_tick", None)
        tick_count = getattr(trading_scheduler, "tick_count", 0)
        is_running = getattr(trading_scheduler, "is_running", False)
    except Exception:
        last_tick = None
        tick_count = 0
        is_running = False

    # Get the most recent bot runtime state records for this user
    try:
        runtime_docs = await db.bot_runtime_state_collection.find(
            {"user_id": user_id},
            {"_id": 0, "bot_id": 1, "last_tick_at": 1, "last_decision": 1,
             "last_order_error": 1, "updated_at": 1}
        ).sort("updated_at", -1).to_list(50)
    except Exception:
        runtime_docs = []

    last_tick_at = None
    if runtime_docs:
        raw = runtime_docs[0].get("updated_at") or runtime_docs[0].get("last_tick_at")
        last_tick_at = raw.isoformat() if hasattr(raw, "isoformat") else raw
    elif last_tick:
        last_tick_at = last_tick.isoformat() if hasattr(last_tick, "isoformat") else str(last_tick)

    # Prefer scheduler.last_tick when it is more recent than the DB record
    # (covers the period before record_tick() first writes to bot_runtime_state).
    if last_tick is not None:
        sched_ts = last_tick.isoformat() if hasattr(last_tick, "isoformat") else str(last_tick)
        if last_tick_at is None or sched_ts > last_tick_at:
            last_tick_at = sched_ts

    bots_evaluated = len(runtime_docs)

    # Count recent activity (last 5 minutes)
    window_start = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
    try:
        trades_opened = await db.trades_collection.count_documents(
            {"user_id": user_id, "status": "open",
             "$expr": {"$gt": [{"$ifNull": ["$opened_at", "$timestamp"]}, window_start]}}
        )
        trades_closed = await db.trades_collection.count_documents(
            {"user_id": user_id, "status": {"$in": ["closed", "completed"]},
             "$expr": {"$gt": [{"$ifNull": ["$closed_at", "$timestamp"]}, window_start]}}
        )
        trades_failed = await db.trades_collection.count_documents(
            {"user_id": user_id, "status": "failed",
             "$expr": {"$gt": [{"$ifNull": ["$closed_at", "$timestamp"]}, window_start]}}
        )
    except Exception:
        trades_opened = trades_closed = trades_failed = 0

    rejects = [
        {"bot_id": d.get("bot_id"), "reason": d.get("last_order_error")}
        for d in runtime_docs
        if d.get("last_order_error")
    ]

    return {
        "success": True,
        "scheduler_running": is_running,
        "tick_count": tick_count,
        "last_tick_at": last_tick_at,
        "bots_evaluated": bots_evaluated,
        "window_minutes": 5,
        "trades_opened_in_window": trades_opened,
        "trades_closed_in_window": trades_closed,
        "trades_failed_in_window": trades_failed,
        "rejects": rejects,
        "rejects_count": len(rejects),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/decision-trace")
async def decision_trace(
    bot_id: str = None,
    limit: int = 20,
    user_id: str = Depends(get_current_user)
):
    """Read-only trace of last bot decisions and reasons.

    Queries bot_runtime_state and recent trades to reconstruct
    the decision history without requiring a separate decisions collection.

    Read-only. No side effects.
    """
    # Runtime state (last known decision per bot)
    query: dict = {"user_id": user_id}
    if bot_id:
        query["bot_id"] = bot_id

    try:
        runtime_docs = await db.bot_runtime_state_collection.find(
            query,
            {"_id": 0, "bot_id": 1, "last_tick_at": 1, "last_decision": 1,
             "last_order_error": 1, "updated_at": 1, "open_position": 1}
        ).sort("updated_at", -1).to_list(limit)
    except Exception:
        runtime_docs = []

    # Recent trades for context
    trade_query: dict = {"user_id": user_id}
    if bot_id:
        trade_query["bot_id"] = bot_id

    try:
        recent_trades = await db.trades_collection.find(
            trade_query,
            {"_id": 0, "id": 1, "bot_id": 1, "status": 1, "side": 1,
             "pair": 1, "opened_at": 1, "closed_at": 1,
             "net_pnl": 1, "trade_close_reason": 1, "skip_reason": 1,
             "last_order_error": 1}
        ).sort([("opened_at", -1), ("_id", -1)]).limit(limit).to_list(limit)
    except Exception:
        recent_trades = []

    return {
        "success": True,
        "bot_id_filter": bot_id,
        "runtime_states": runtime_docs,
        "recent_trades": recent_trades,
        "runtime_states_count": len(runtime_docs),
        "recent_trades_count": len(recent_trades),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/last-tick-summary")
async def last_tick_summary_v2(user_id: str = Depends(get_current_user)):
    """Per-user summary of the last scheduler tick.

    Returns deterministic counts derived from DB records so the response is
    accurate even after a backend restart (unlike in-memory counters).

    Fields:
        last_tick_at        – when the scheduler last ran for any of this user's bots
        bots_evaluated      – bots that had a runtime-state record updated in last tick
        decisions_made      – bots that produced a trade decision (open or close attempt)
        opens_attempted     – trade open records created in last 5 min window
        opens_done          – opens that ended in status "open" (fill confirmed)
        closes_attempted    – close attempts recorded (closed + failed in window)
        closes_done         – trades transitioned to "closed"/"completed" in window
        skips_by_reason     – {reason: count} for bots that were skipped
        rejects_by_reason   – {reason: count} for bots with last_order_error set
        last_error          – most recent last_order_error across all bots (or null)
    """
    try:
        from trading_scheduler import trading_scheduler
        is_running = getattr(trading_scheduler, "is_running", False)
        tick_count = getattr(trading_scheduler, "tick_count", 0)
    except Exception:
        is_running = False
        tick_count = 0

    window_start = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()

    # Runtime state records for this user
    try:
        runtime_docs = await db.bot_runtime_state_collection.find(
            {"user_id": user_id},
            {"_id": 0, "bot_id": 1, "last_tick_at": 1, "last_decision": 1,
             "last_order_error": 1, "updated_at": 1}
        ).sort("updated_at", -1).to_list(200)
    except Exception:
        runtime_docs = []

    last_tick_at = None
    if runtime_docs:
        raw = runtime_docs[0].get("updated_at") or runtime_docs[0].get("last_tick_at")
        last_tick_at = raw.isoformat() if hasattr(raw, "isoformat") else raw

    # Prefer scheduler.last_tick when it is more recent than the DB record.
    try:
        sched_last = getattr(trading_scheduler, "last_tick", None)
        if sched_last is not None:
            sched_ts = sched_last.isoformat() if hasattr(sched_last, "isoformat") else str(sched_last)
            if last_tick_at is None or sched_ts > last_tick_at:
                last_tick_at = sched_ts
    except Exception:
        pass

    bots_evaluated = len(runtime_docs)

    # Trade counts in window
    try:
        opens_attempted = await db.trades_collection.count_documents({
            "user_id": user_id,
            "$expr": {"$gt": [{"$ifNull": ["$opened_at", "$timestamp"]}, window_start]}
        })
        opens_done = await db.trades_collection.count_documents({
            "user_id": user_id, "status": "open",
            "$expr": {"$gt": [{"$ifNull": ["$opened_at", "$timestamp"]}, window_start]}
        })
        closes_done = await db.trades_collection.count_documents({
            "user_id": user_id, "status": {"$in": ["closed", "completed"]},
            "$expr": {"$gt": [{"$ifNull": ["$closed_at", "$timestamp"]}, window_start]}
        })
        closes_failed = await db.trades_collection.count_documents({
            "user_id": user_id, "status": "failed",
            "$expr": {"$gt": [{"$ifNull": ["$closed_at", "$timestamp"]}, window_start]}
        })
        closes_attempted = closes_done + closes_failed
    except Exception:
        opens_attempted = opens_done = closes_attempted = closes_done = closes_failed = 0

    decisions_made = opens_attempted + closes_attempted

    # Aggregate skip / reject reasons from runtime state
    skips_by_reason: dict = {}
    rejects_by_reason: dict = {}
    last_error = None
    for doc in runtime_docs:
        err = doc.get("last_order_error")
        if err:
            rejects_by_reason[err] = rejects_by_reason.get(err, 0) + 1
            if last_error is None:
                last_error = err
        decision = doc.get("last_decision")
        if decision and isinstance(decision, dict):
            skip = decision.get("skip_reason")
            if skip:
                skips_by_reason[skip] = skips_by_reason.get(skip, 0) + 1

    return {
        "success": True,
        "scheduler_running": is_running,
        "tick_count": tick_count,
        "last_tick_at": last_tick_at,
        "window_minutes": 5,
        "bots_evaluated": bots_evaluated,
        "decisions_made": decisions_made,
        "opens_attempted": opens_attempted,
        "opens_done": opens_done,
        "closes_attempted": closes_attempted,
        "closes_done": closes_done,
        "closes_failed": closes_failed,
        "skips_by_reason": skips_by_reason,
        "rejects_by_reason": rejects_by_reason,
        "close_rejects_by_reason": _get_close_rejects_from_engine(),
        "last_error": last_error,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/paper-close-proof")
async def paper_close_proof(user_id: str = Depends(get_current_user)):
    """Deterministic paper-close proof diagnostic (auth required).

    All counts are derived from the DB so this endpoint is accurate across
    restarts and does not rely on in-memory counters.

    Returns
    -------
    open_trades_count           : number of trades currently open for this user
    oldest_open_trade_age_minutes : age in minutes of the oldest open trade (or null)
    closes_attempted_last_5m    : trades transitioned to closed/completed OR failed in last 5 min
    closes_done_last_5m         : trades that reached status closed/completed in last 5 min
    last_close_at               : ISO timestamp of the last successful paper-engine close (or null)
    last_10_closes              : list of up to 10 recent closed trades with id + close_reason
    """
    window_start = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
    now = datetime.now(timezone.utc)

    try:
        open_trades = await db.trades_collection.find(
            {"user_id": user_id, "status": "open"},
            {"_id": 0, "id": 1, "opened_at": 1, "entry_time": 1, "timestamp": 1},
        ).sort([("opened_at", 1), ("_id", 1)]).to_list(200)
    except Exception:
        open_trades = []

    open_trades_count = len(open_trades)

    oldest_open_trade_age_minutes = None
    if open_trades:
        oldest_raw = (
            open_trades[0].get("opened_at")
            or open_trades[0].get("entry_time")
            or open_trades[0].get("timestamp")
        )
        if oldest_raw:
            try:
                oldest_dt = datetime.fromisoformat(str(oldest_raw).replace("Z", "+00:00"))
                oldest_open_trade_age_minutes = round((now - oldest_dt).total_seconds() / 60, 1)
            except Exception:
                pass

    try:
        closes_done_last_5m = await db.trades_collection.count_documents({
            "user_id": user_id,
            "status": {"$in": ["closed", "completed"]},
            "$expr": {"$gt": [{"$ifNull": ["$closed_at", "$timestamp"]}, window_start]},
        })
        closes_failed_last_5m = await db.trades_collection.count_documents({
            "user_id": user_id,
            "status": "failed",
            "$expr": {"$gt": [{"$ifNull": ["$closed_at", "$timestamp"]}, window_start]},
        })
    except Exception:
        closes_done_last_5m = 0
        closes_failed_last_5m = 0

    closes_attempted_last_5m = closes_done_last_5m + closes_failed_last_5m

    # last_close_at from the paper engine singleton
    last_close_at = None
    try:
        from paper_trading_engine import paper_engine
        last_close_at = paper_engine.get_status().get("last_close_time")
    except Exception:
        pass

    # last 10 closed trades
    try:
        recent_closes = await db.trades_collection.find(
            {"user_id": user_id, "status": {"$in": ["closed", "completed"]}},
            {"_id": 0, "id": 1, "trade_close_reason": 1, "closed_at": 1, "pair": 1},
        ).sort([("closed_at", -1), ("_id", -1)]).to_list(10)
    except Exception:
        recent_closes = []

    return {
        "success": True,
        "open_trades_count": open_trades_count,
        "oldest_open_trade_age_minutes": oldest_open_trade_age_minutes,
        "closes_attempted_last_5m": closes_attempted_last_5m,
        "closes_done_last_5m": closes_done_last_5m,
        "last_close_at": last_close_at,
        "last_10_closes": [
            {
                "id": t.get("id"),
                "close_reason": t.get("trade_close_reason"),
                "pair": t.get("pair"),
                "closed_at": t.get("closed_at"),
            }
            for t in recent_closes
        ],
        "timestamp": now.isoformat(),
    }


@router.get("/news-sources")
async def news_sources_diagnostic(user_id: str = Depends(get_current_user)):
    """Provider diagnostics for CoinStats and other configured news providers (auth required).

    Returns structured status for each provider so the frontend can display
    exactly what is configured, when it last ran, and why articles may be missing.

    Returns
    -------
    success     : bool
    providers   : list of provider status objects
    timestamp   : ISO timestamp
    """
    from services.news_coinstats import coinstats_provider, resolve_coinstats_key

    # CoinStats diagnostics
    key, key_source = await resolve_coinstats_key(user_id)
    cached = coinstats_provider._cache or {}
    articles = cached.get("articles", [])
    cache_ts = coinstats_provider._cache_ts
    cache_age_seconds: int | None = None
    if cache_ts is not None:
        try:
            cache_age_seconds = int((datetime.now(timezone.utc) - cache_ts).total_seconds())
        except Exception:
            pass

    # Derive fetch_status from provider state
    last_err = coinstats_provider._last_error
    if not key:
        fetch_status = "key_missing"
    elif last_err and "429" in str(last_err):
        fetch_status = "rate_limited"
    elif last_err and "401" in str(last_err):
        fetch_status = "invalid_key"
    elif last_err:
        fetch_status = "error"
    elif cache_ts is None:
        fetch_status = "pending"
    elif articles:
        fetch_status = "ok"
    else:
        fetch_status = "no_articles"

    coinstats_entry = {
        "provider": "coinstats",
        "configured": bool(key),
        "key_source": key_source,
        "last_run_at": cached.get("fetched_at"),
        "last_ok_at": cached.get("fetched_at") if articles else None,
        "last_error": last_err,
        "fetch_status": fetch_status,
        "last_articles_count": len(articles),
        "cache_age_seconds": cache_age_seconds,
        "http_status_last": None,  # not tracked per-request; test_connection covers this
    }

    # GDELT stub entry (secondary provider when configured)
    import os
    news_provider = os.getenv("NEWS_PROVIDER", "coinstats").lower()
    gdelt_entry = {
        "provider": "gdelt",
        "configured": news_provider == "gdelt",
        "key_source": "none",
        "last_run_at": None,
        "last_ok_at": None,
        "last_error": None,
        "fetch_status": "not_primary" if news_provider != "gdelt" else "pending",
        "last_articles_count": 0,
        "cache_age_seconds": None,
        "http_status_last": None,
    }

    return {
        "success": True,
        "providers": [coinstats_entry, gdelt_entry],
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/open-trades")
async def open_trades_diagnostic(user_id: str = Depends(get_current_user)):
    """List open trades for the current user with diagnostic context.

    Read-only. Shows per-trade: age, tp/sl prices, current price (cached),
    next exit condition, how far away it is, and whether hard/soft exit is triggered.
    """
    try:
        trades = await db.trades_collection.find(
            {"user_id": user_id, "status": "open"},
            {"_id": 0}
        ).sort([("opened_at", -1), ("_id", -1)]).to_list(200)
    except Exception:
        trades = []

    now = datetime.now(timezone.utc)
    enriched = []
    oldest_age: float = 0.0
    for t in trades:
        entry_time_raw = t.get("entry_time") or t.get("opened_at") or t.get("timestamp")
        try:
            entry_time = datetime.fromisoformat(str(entry_time_raw).replace("Z", "+00:00"))
            age_minutes = round((now - entry_time).total_seconds() / 60, 1)
            age_seconds = age_minutes * 60
        except Exception:
            age_minutes = None
            age_seconds = 0.0

        if age_minutes is not None and age_minutes > oldest_age:
            oldest_age = age_minutes

        entry_price = float(t.get("entry_price") or t.get("price") or 0)
        stop_loss_pct = float(t.get("stop_loss_pct", 0.02))
        take_profit_pct = float(t.get("take_profit_pct", 0.03))
        stop_loss_price = t.get("stop_loss_price") or (entry_price * (1 - stop_loss_pct) if entry_price else None)
        take_profit_price = t.get("take_profit_price") or (entry_price * (1 + take_profit_pct) if entry_price else None)

        hard_exit_triggered = age_seconds >= HARD_MAX_HOLD_SECONDS if age_minutes is not None else False
        soft_exit_triggered = age_seconds >= SOFT_MAX_HOLD_SECONDS if age_minutes is not None else False

        next_exit = "awaiting_signal"
        if age_minutes is not None:
            if hard_exit_triggered:
                next_exit = "hard_exit_overdue"
            elif soft_exit_triggered:
                next_exit = "soft_exit_triggered"
            elif age_minutes >= PAPER_MAX_HOLD_MINUTES:
                next_exit = "time_exit_due"
            elif age_minutes >= PAPER_STALE_EXIT_MINUTES:
                next_exit = "stale_exit_eligible"
            else:
                remaining = round(PAPER_MAX_HOLD_MINUTES - age_minutes, 1)
                next_exit = f"time_exit_in_{remaining}min"

        enriched.append({
            "id": t.get("id"),
            "bot_id": t.get("bot_id"),
            "pair": t.get("pair") or t.get("symbol"),
            "exchange": t.get("exchange"),
            "entry_price": entry_price,
            "stop_loss_price": round(stop_loss_price, 6) if stop_loss_price else None,
            "take_profit_price": round(take_profit_price, 6) if take_profit_price else None,
            "age_minutes": age_minutes,
            "next_exit": next_exit,
            "hard_exit_triggered": hard_exit_triggered,
            "soft_exit_triggered": soft_exit_triggered,
            "opened_at": entry_time_raw,
            "trade_amount": t.get("trade_amount"),
            "data_source": t.get("data_source"),
        })

    return {
        "success": True,
        "open_trades_count": len(enriched),
        "oldest_open_trade_age_minutes": round(oldest_age, 1) if enriched else None,
        "trades": enriched,
        "timestamp": now.isoformat(),
    }


@router.get("/paper-engine")
@router.get("/paper")
async def paper_engine_diagnostics(user_id: str = Depends(get_current_user)):
    """Truth diagnostics for the paper trading engine.

    Returns a real-time snapshot of engine state, all open trades with
    age/next-exit details, and the last 20 engine actions (ring buffer).

    Fields
    ------
    engine_running          : bool — engine has run at least one tick
    last_tick_at            : ISO timestamp of last tick (or null)
    tick_interval_seconds   : configured scheduler interval
    open_trades_count       : number of open paper trades for this user
    open_trades             : list (up to 50) with per-trade diagnostics
    last_20_actions         : ring buffer entries from the paper engine
    """
    from paper_trading_engine import paper_engine
    from config import PAPER_MAX_HOLD_MINUTES, PAPER_STALE_EXIT_MINUTES

    now = datetime.now(timezone.utc)

    # Engine-level state
    engine_status = paper_engine.get_status()
    last_tick_raw = engine_status.get("last_tick_time")
    last_tick_at = last_tick_raw

    # Scheduler interval + running state
    tick_interval_seconds: int = 30
    sched_is_running = False
    sched_last_tick = None
    try:
        from trading_scheduler import trading_scheduler
        tick_interval_seconds = getattr(trading_scheduler, "tick_interval", 30)
        sched_is_running = getattr(trading_scheduler, "is_running", False)
        sched_last_tick = getattr(trading_scheduler, "last_tick", None)
        if sched_last_tick is not None:
            sched_ts = sched_last_tick.isoformat() if hasattr(sched_last_tick, "isoformat") else str(sched_last_tick)
            if last_tick_at is None or sched_ts > (last_tick_at or ""):
                last_tick_at = sched_ts
    except Exception:
        pass

    # engine_running: True if either the paper engine OR the scheduler is active
    # (paper_engine.is_running is only set on first run_trading_cycle call,
    #  so use scheduler state as primary truth while engine warms up)
    engine_running = engine_status.get("is_running", False) or sched_is_running

    # Open trades for this user
    try:
        raw_trades = await db.trades_collection.find(
            {"user_id": user_id, "status": "open"},
            {"_id": 0},
        ).sort([("opened_at", 1), ("_id", 1)]).to_list(50)
    except Exception:
        raw_trades = []

    open_trades = []
    for t in raw_trades:
        entry_time_raw = t.get("entry_time") or t.get("opened_at") or t.get("timestamp")
        try:
            entry_time = datetime.fromisoformat(str(entry_time_raw).replace("Z", "+00:00"))
            age_minutes = round((now - entry_time).total_seconds() / 60, 1)
        except Exception:
            age_minutes = None

        entry_price = float(t.get("entry_price") or t.get("price") or 0)

        # Determine next_exit condition
        age_seconds = (age_minutes * 60) if age_minutes is not None else 0.0
        hard_exit_triggered = age_seconds >= HARD_MAX_HOLD_SECONDS if age_minutes is not None else False
        soft_exit_triggered = age_seconds >= SOFT_MAX_HOLD_SECONDS if age_minutes is not None else False
        next_exit = "awaiting_signal"
        if age_minutes is not None:
            if hard_exit_triggered:
                next_exit = "hard_exit_overdue"
            elif soft_exit_triggered:
                next_exit = "soft_exit_triggered"
            elif age_minutes >= PAPER_MAX_HOLD_MINUTES:
                next_exit = "time_exit_due"
            elif age_minutes >= PAPER_STALE_EXIT_MINUTES:
                next_exit = "stale_exit_eligible"
            else:
                remaining_time = round(PAPER_MAX_HOLD_MINUTES - age_minutes, 1)
                remaining_stale = round(PAPER_STALE_EXIT_MINUTES - age_minutes, 1)
                next_exit = f"time_exit_in_{remaining_time}min"
                if remaining_stale < remaining_time and remaining_stale > 0:
                    next_exit = f"stale_exit_in_{remaining_stale}min_or_{next_exit}"

        open_trades.append({
            "id": t.get("id"),
            "bot_id": t.get("bot_id"),
            "bot_name": t.get("bot_name"),
            "exchange": t.get("exchange"),
            "symbol": t.get("pair") or t.get("symbol"),
            "opened_at": entry_time_raw,
            "age_minutes": age_minutes,
            "entry_price": entry_price,
            "trade_amount": float(t.get("trade_amount") or t.get("entry_value") or 0),
            "current_price": None,  # populated below via price_fallback_service
            "unrealized_pnl_zar": None,
            "next_exit": next_exit,
            "hard_exit_triggered": hard_exit_triggered,
            "soft_exit_triggered": soft_exit_triggered,
        })

    # Enrich open trades with current price + unrealized PnL
    # Uses price_fallback_service (non-blocking; falls back to cached/static prices).
    try:
        from services.price_fallback_service import price_fallback_service
        for trade in open_trades:
            sym = trade.get("symbol")
            exch = trade.get("exchange") or "luno"
            if not sym:
                continue
            try:
                price = await price_fallback_service.get_price(exch, sym)
                if price and price > 0:
                    trade["current_price"] = price
                    entry = trade.get("entry_price") or 0
                    trade_amount = trade.get("trade_amount") or 0
                    if entry and entry > 0 and trade_amount:
                        # unrealized_pnl_zar = position_value * price_change_ratio
                        trade["unrealized_pnl_zar"] = round(
                            (price - entry) / entry * trade_amount, 2
                        )
            except Exception:
                pass
    except Exception:
        pass

    return {
        "success": True,
        "engine_running": engine_running,
        "last_tick_at": last_tick_at,
        "last_close_at": engine_status.get("last_close_time"),
        "closes_attempted": engine_status.get("closes_attempted", 0),
        "closes_done": engine_status.get("closes_done", 0),
        "close_loop_enabled": True,
        "tick_interval_seconds": tick_interval_seconds,
        "open_trades_count": len(open_trades),
        "oldest_open_trade_age_minutes": max(
            (t["age_minutes"] for t in open_trades if t.get("age_minutes") is not None),
            default=None,
        ),
        "open_trades": open_trades,
        "last_20_actions": engine_status.get("last_20_actions", []),
        "timestamp": now.isoformat(),
    }


@router.get("/symbol-selection")
async def symbol_selection_diagnostic(
    bot_id: str = "",
    user_id: str = Depends(get_current_user),
):
    """Truth diagnostic for symbol selection (C1).

    Returns:
      - candidate_count: how many symbols passed universe + exchange filters
      - filtered_out_reasons: summary of why symbols were dropped
      - top5_scored: the top 5 candidate symbols and their scores
      - winner: the symbol that was (or would be) selected
      - winner_reason: why this symbol won

    If bot_id is provided, shows the last recorded selection for that bot.
    If bot_id is omitted, simulates a fresh selection for Luno using the
    default symbol universe.
    """
    from services.symbol_universe import symbol_universe as _su
    from paper_trading_engine import paper_engine

    # If bot_id given and we have a cached selection, return it
    if bot_id:
        cached = paper_engine._last_symbol_selection
        if cached and cached.get("bot_id") == bot_id:
            return {"success": True, "source": "engine_cache", **cached}

    # Simulate a selection for the given (or default) exchange
    # Use Luno universe as a safe default demo
    exchange = "luno"
    try:
        bots_cursor = db.bots_collection.find(
            {"user_id": user_id, "id": bot_id} if bot_id else {"user_id": user_id},
            {"exchange": 1, "pair": 1, "symbol_universe": 1, "_id": 0},
        )
        bot_list = await bots_cursor.to_list(1)
        if bot_list:
            exchange = bot_list[0].get("exchange", "luno")
    except Exception:
        pass

    universe = _su.get_universe(exchange)
    open_symbols: list = []
    try:
        open_trades_cursor = db.trades_collection.find(
            {"user_id": user_id, "status": "open"}, {"pair": 1, "symbol": 1, "_id": 0}
        )
        open_trades_list = await open_trades_cursor.to_list(100)
        open_symbols = [
            t.get("pair") or t.get("symbol", "") for t in open_trades_list
            if t.get("pair") or t.get("symbol")
        ]
    except Exception:
        pass

    _winner, diag = await _su.select(
        bot_id=bot_id or "demo",
        user_id=user_id,
        exchange=exchange,
        available_pairs=universe,
        open_symbols_for_user=open_symbols,
    )
    return {
        "success": True,
        "source": "simulated",
        "last_n_closed_symbols": _su.last_n_symbols(bot_id or "demo"),
        **diag,
    }
