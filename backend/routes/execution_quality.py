"""
Execution Quality Monitor Endpoints
Track latency, reject rate, slippage for trade execution
"""

from fastapi import APIRouter, HTTPException, Depends
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional
import logging

from auth import get_current_user
import database as db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/execution-quality", tags=["Execution Quality"])


@router.get("/status")
async def get_execution_quality_status(
    user_id: str = Depends(get_current_user),
    timeframe: str = "1h"
):
    """
    Get execution quality metrics
    
    Tracks:
    - Latency (p50, p95)
    - Reject rate
    - Slippage (basis points)
    - Order fill rate
    
    Actions taken on poor quality:
    - Reduce position size
    - Widen cooldowns
    - Pause bots
    
    Args:
        timeframe: "1h", "24h", "7d"
    
    Returns:
        Execution quality metrics and status
    """
    try:
        # Calculate timeframe
        timeframe_map = {
            "1h": timedelta(hours=1),
            "24h": timedelta(days=1),
            "7d": timedelta(days=7)
        }
        
        delta = timeframe_map.get(timeframe, timedelta(hours=1))
        cutoff = datetime.now(timezone.utc) - delta
        
        # Get execution records from trades
        executions = await db.trades_collection.find({
            "user_id": user_id,
            "timestamp": {"$gte": cutoff.isoformat()}
        }, {
            "_id": 0,
            "latency_ms": 1,
            "slippage_bps": 1,
            "rejected": 1,
            "filled": 1,
            "timestamp": 1
        }).to_list(1000)
        
        if not executions:
            return {
                "success": True,
                "message": "No executions in timeframe",
                "timeframe": timeframe,
                "metrics": {
                    "latency_p50_ms": 0,
                    "latency_p95_ms": 0,
                    "reject_rate": 0,
                    "slippage_avg_bps": 0,
                    "fill_rate": 0
                },
                "quality_score": 100,
                "status": "healthy",
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        
        # Calculate metrics
        latencies = [e.get("latency_ms", 0) for e in executions if e.get("latency_ms")]
        slippages = [e.get("slippage_bps", 0) for e in executions if e.get("slippage_bps")]
        
        rejected_count = sum(1 for e in executions if e.get("rejected"))
        filled_count = sum(1 for e in executions if e.get("filled"))
        total_count = len(executions)
        
        # Calculate percentiles
        latencies.sort()
        p50_idx = int(len(latencies) * 0.5) if latencies else 0
        p95_idx = int(len(latencies) * 0.95) if latencies else 0
        
        latency_p50 = latencies[p50_idx] if latencies and p50_idx < len(latencies) else 0
        latency_p95 = latencies[p95_idx] if latencies and p95_idx < len(latencies) else 0
        
        reject_rate = (rejected_count / total_count * 100) if total_count > 0 else 0
        fill_rate = (filled_count / total_count * 100) if total_count > 0 else 0
        slippage_avg = sum(slippages) / len(slippages) if slippages else 0
        
        # Calculate quality score (0-100)
        quality_score = 100
        
        # Deduct for high latency
        if latency_p95 > 1000:  # >1s
            quality_score -= 30
        elif latency_p95 > 500:  # >500ms
            quality_score -= 15
        
        # Deduct for high reject rate
        if reject_rate > 10:
            quality_score -= 30
        elif reject_rate > 5:
            quality_score -= 15
        
        # Deduct for high slippage
        if slippage_avg > 20:  # >20 bps
            quality_score -= 20
        elif slippage_avg > 10:  # >10 bps
            quality_score -= 10
        
        # Deduct for low fill rate
        if fill_rate < 80:
            quality_score -= 20
        
        # Determine status
        if quality_score >= 85:
            status = "healthy"
            actions = []
        elif quality_score >= 70:
            status = "degraded"
            actions = ["reducing_position_size", "widening_cooldowns"]
        else:
            status = "poor"
            actions = ["pausing_bots", "reducing_position_size", "widening_cooldowns"]
        
        # Get action history
        action_history = await db.db["execution_quality_actions"].find({
            "user_id": user_id,
            "timestamp": {"$gte": cutoff.isoformat()}
        }, {"_id": 0}).sort("timestamp", -1).limit(10).to_list(10)
        
        return {
            "success": True,
            "timeframe": timeframe,
            "metrics": {
                "latency_p50_ms": round(latency_p50, 2),
                "latency_p95_ms": round(latency_p95, 2),
                "reject_rate": round(reject_rate, 2),
                "slippage_avg_bps": round(slippage_avg, 2),
                "fill_rate": round(fill_rate, 2),
                "executions_analyzed": total_count
            },
            "quality_score": quality_score,
            "status": status,
            "active_actions": actions,
            "action_history": action_history,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as e:
        logger.error(f"Execution quality status error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/history")
async def get_execution_quality_history(
    user_id: str = Depends(get_current_user),
    hours: int = 24
):
    """
    Get execution quality history over time
    
    Returns time-series data for charting
    """
    try:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=hours)
        
        # Get hourly aggregated metrics
        # (In production, would use aggregation pipeline)
        executions = await db.trades_collection.find({
            "user_id": user_id,
            "timestamp": {"$gte": cutoff.isoformat()}
        }, {
            "_id": 0,
            "timestamp": 1,
            "latency_ms": 1,
            "slippage_bps": 1,
            "rejected": 1
        }).to_list(10000)
        
        # Group by hour
        hourly_data = {}
        for execution in executions:
            timestamp = execution.get("timestamp", "")
            if not timestamp:
                continue
            
            # Round to hour
            try:
                dt = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
                hour_key = dt.replace(minute=0, second=0, microsecond=0).isoformat()
                
                if hour_key not in hourly_data:
                    hourly_data[hour_key] = {
                        "latencies": [],
                        "slippages": [],
                        "rejects": 0,
                        "total": 0
                    }
                
                hourly_data[hour_key]["total"] += 1
                
                if execution.get("latency_ms"):
                    hourly_data[hour_key]["latencies"].append(execution["latency_ms"])
                
                if execution.get("slippage_bps"):
                    hourly_data[hour_key]["slippages"].append(execution["slippage_bps"])
                
                if execution.get("rejected"):
                    hourly_data[hour_key]["rejects"] += 1
            except:
                continue
        
        # Calculate aggregates per hour
        history = []
        for hour_key, data in sorted(hourly_data.items()):
            avg_latency = sum(data["latencies"]) / len(data["latencies"]) if data["latencies"] else 0
            avg_slippage = sum(data["slippages"]) / len(data["slippages"]) if data["slippages"] else 0
            reject_rate = (data["rejects"] / data["total"] * 100) if data["total"] > 0 else 0
            
            history.append({
                "timestamp": hour_key,
                "avg_latency_ms": round(avg_latency, 2),
                "avg_slippage_bps": round(avg_slippage, 2),
                "reject_rate": round(reject_rate, 2),
                "executions": data["total"]
            })
        
        return {
            "success": True,
            "hours": hours,
            "data_points": len(history),
            "history": history,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as e:
        logger.error(f"Execution quality history error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
