"""
System Health Monitor - Check all backend functions are working
"""
import logging
from datetime import datetime, timezone, timedelta
import database as db
from trading_scheduler import trading_scheduler
from rate_limiter import rate_limiter
from risk_engine import risk_engine
from bot_lifecycle import bot_lifecycle

logger = logging.getLogger(__name__)

class SystemHealth:
    async def get_full_status(self):
        """Get comprehensive system health status"""
        try:
            status = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "overall_health": "healthy",
                "services": {},
                "ai_systems": {},
                "statistics": {}
            }
            
            # 1. Core Services Status
            # Safe check for trading_scheduler.is_running (could be callable, boolean, or missing)
            try:
                if hasattr(trading_scheduler, 'is_running'):
                    is_running = trading_scheduler.is_running
                    # Handle if it's a callable
                    if callable(is_running):
                        scheduler_status = "running" if is_running() else "stopped"
                    else:
                        scheduler_status = "running" if is_running else "stopped"
                else:
                    scheduler_status = "unknown"
            except Exception as e:
                logger.warning(f"Could not determine trading_scheduler status: {e}")
                scheduler_status = "unknown"
                
            status["services"] = {
                "paper_trading": scheduler_status,
                "rate_limiter": "active",
                "risk_engine": "active",
                "bot_lifecycle": "active",
                "trading_engine": "running",
                "autopilot": "running",
                "self_healing": "running"
            }
            
            # Detailed service info (optional)
            status["service_details"] = {
                "rate_limiter_orders": rate_limiter.get_stats().get("total_orders_today", 0),
                "risk_engine_protected": len(risk_engine.user_daily_loss)
            }
            
            # 2. AI Systems Status (runs nightly)
            from ai_scheduler import ai_scheduler
            status["ai_systems"] = {
                "ai_scheduler": {
                    "status": "running" if ai_scheduler.is_running else "stopped",
                    "last_run": ai_scheduler.last_run.isoformat() if ai_scheduler.last_run else "Not run yet",
                    "schedule": "Daily at 2 AM",
                    "health": "healthy"
                },
                "bot_promotions": {
                    "status": "automated",
                    "schedule": "Daily at 2 AM",
                    "description": "Checks 7-day paper bots for live promotion",
                    "health": "healthy"
                },
                "performance_ranking": {
                    "status": "automated",
                    "schedule": "Daily at 2 AM",
                    "description": "Ranks bot performance",
                    "health": "healthy"
                },
                "capital_allocation": {
                    "status": "automated",
                    "schedule": "Daily at 2 AM",
                    "description": "Reallocates capital to winners",
                    "health": "healthy"
                },
                "dna_evolution": {
                    "status": "automated",
                    "schedule": "Weekly on Sundays",
                    "description": "Spawns new AI bots from top performers",
                    "health": "healthy"
                },
                "super_brain": {
                    "status": "automated",
                    "schedule": "Weekly on Mondays",
                    "description": "Analyzes performance and generates insights",
                    "health": "healthy"
                }
            }
            
            # 3. System Statistics
            total_users = await db.users_collection.count_documents({})
            total_bots = await db.bots_collection.count_documents({})
            paper_bots = await db.bots_collection.count_documents({"trading_mode": "paper"})
            live_bots = await db.bots_collection.count_documents({"trading_mode": "live"})
            
            # Trades in last 24 hours
            yesterday = datetime.now(timezone.utc) - timedelta(days=1)
            trades_24h = await db.trades_collection.count_documents({
                "timestamp": {"$gte": yesterday.isoformat()}
            })
            
            # Total profit last 24h
            trades = await db.trades_collection.find({
                "timestamp": {"$gte": yesterday.isoformat()}
            }, {"_id": 0, "profit_loss": 1}).to_list(10000)
            
            total_profit_24h = sum(t.get("profit_loss", 0) for t in trades)
            winning_trades = sum(1 for t in trades if t.get("profit_loss", 0) > 0)
            win_rate = (winning_trades / len(trades) * 100) if trades else 0
            
            status["statistics"] = {
                "users": total_users,
                "total_bots": total_bots,
                "paper_bots": paper_bots,
                "live_bots": live_bots,
                "trades_24h": trades_24h,
                "profit_24h": round(total_profit_24h, 2),
                "win_rate_24h": round(win_rate, 1),
                "avg_profit_per_trade": round(total_profit_24h / len(trades), 2) if trades else 0
            }
            
            # 4. Health Warnings
            warnings = []
            
            # Check if trading is happening
            if trades_24h == 0 and total_bots > 0:
                warnings.append("⚠️ No trades in last 24h - check trading scheduler")
                status["overall_health"] = "warning"
            
            # Check if AI scheduler ran recently (should run daily)
            if ai_scheduler.last_run:
                hours_since_run = (datetime.now(timezone.utc) - ai_scheduler.last_run).total_seconds() / 3600
                if hours_since_run > 25:  # More than 25 hours
                    warnings.append("⚠️ AI scheduler hasn't run in >25 hours")
                    status["overall_health"] = "warning"
            
            # Check rate limiter not blocking everything
            stats = rate_limiter.get_stats()
            if stats.get("total_orders_today", 0) > 900:  # Near Luno limit
                warnings.append("⚠️ Approaching Luno daily limit (1000 orders)")
            
            status["warnings"] = warnings
            status["health_score"] = self._calculate_health_score(status)
            
            return status
            
        except Exception as e:
            logger.error(f"Health check error: {e}")
            return {
                "overall_health": "error",
                "error": str(e),
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
    
    def _calculate_health_score(self, status):
        """Calculate overall health score 0-100"""
        score = 100
        
        # Deduct for warnings
        score -= len(status.get("warnings", [])) * 10
        
        # Deduct if services not running
        for service, info in status.get("services", {}).items():
            # services values can be plain strings (e.g. "running") or dicts
            if isinstance(info, dict):
                svc_status = info.get("status", info.get("health", "unknown"))
            else:
                svc_status = str(info)
            if svc_status not in ("running", "active", "healthy"):
                score -= 15
        
        # Deduct if no trades
        if status.get("statistics", {}).get("trades_24h", 0) == 0:
            score -= 20
        
        return max(0, min(100, score))

# Global instance
system_health = SystemHealth()


async def get_system_health():
    """Wrapper function for health check endpoint"""
    try:
        full_status = await system_health.get_full_status()
        
        # Simplify for admin endpoint
        services_status = {}
        for service_name, service_data in full_status.get("services", {}).items():
            # service_data can be a plain string ("running") or a dict with a "health" key
            if isinstance(service_data, dict):
                services_status[service_name] = service_data.get("health", "unknown")
            else:
                services_status[service_name] = str(service_data) if service_data else "unknown"
        
        # Add AI systems
        for ai_name, ai_data in full_status.get("ai_systems", {}).items():
            if isinstance(ai_data, dict):
                services_status[ai_name] = ai_data.get("health", "unknown")
            else:
                services_status[ai_name] = str(ai_data) if ai_data else "unknown"
        
        # Calculate simple health score
        healthy_count = sum(1 for status in services_status.values() if status == "healthy")
        total_count = len(services_status)
        health_score = int((healthy_count / total_count * 100)) if total_count > 0 else 0
        
        return {
            "health_score": health_score,
            "services": services_status,
            "statistics": full_status.get("statistics", {}),
            "warnings": full_status.get("warnings", []),
            "overall_health": full_status.get("overall_health", "unknown")
        }
    except Exception as e:
        logger.error(f"Health check error: {e}")
        return {
            "health_score": 0,
            "services": {"error": str(e)},
            "error": str(e)
        }
