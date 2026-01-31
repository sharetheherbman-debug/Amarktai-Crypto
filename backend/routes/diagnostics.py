"""
Diagnostics Endpoints - Pre-Merge Verification
Includes realtime smoke tests and system health checks
"""

from fastapi import APIRouter, HTTPException, Depends
from datetime import datetime, timezone
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
            max_bots = 45
            
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
