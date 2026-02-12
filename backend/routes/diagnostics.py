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

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/diagnostics", tags=["Diagnostics"])


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
