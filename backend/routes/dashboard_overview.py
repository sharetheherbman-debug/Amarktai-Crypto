"""
Dashboard Overview Endpoint - Consolidated Stats

Provides a single endpoint for all dashboard overview metrics:
- Total profit, daily/weekly/monthly profit
- Bot counts (active/paused/training)
- System mode flags
- Bodyguard status
- Last trade info
"""

from fastapi import APIRouter, HTTPException, Depends
from datetime import datetime, timezone, timedelta
import logging
from typing import Dict, Optional

from auth import get_current_user
import database as db

logger = logging.getLogger(__name__)
router = APIRouter()

OVERVIEW_SNAPSHOT_KEYS = [
    "systemMode",
    "activeBots",
    "openPositions",
    "totalProfit",
    "winRate",
    "todaysTrades",
    "riskLevel",
    "lastRebalance",
    "nextReinvest",
]


def _safe_int(value, default=0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _safe_float(value, default=0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


@router.get("/api/dashboard/overview")
async def get_dashboard_overview(user_id: str = Depends(get_current_user)):
    """
    Get consolidated dashboard overview stats
    
    Returns:
        - total_profit: Overall profit across all bots
        - daily_profit: Profit today
        - weekly_profit: Profit this week
        - monthly_profit: Profit this month
        - active_bots: Count of active bots
        - paused_bots: Count of paused bots
        - training_bots: Count of bots in training
        - total_bots: Total bot count
        - last_trade_time: Timestamp of most recent trade
        - system_mode: paper_trading/live_trading/autonomous flags
        - bodyguard_status: Daily loss lock status
        - total_trades: Total number of trades
        - win_rate: Percentage of winning trades
    """
    try:
        # Get all user's bots (exclude deleted)
        bots = await db.bots_collection.find({
            "user_id": user_id,
            "status": {"$ne": "deleted"},
            "deleted_at": {"$exists": False}
        }, {"_id": 0}).to_list(1000)
        
        # Calculate bot counts
        active_bots = sum(1 for b in bots if b.get("status") == "active")
        paused_bots = sum(1 for b in bots if b.get("status") == "paused")
        training_bots = sum(1 for b in bots if b.get("status") in ["training", "quarantined"])
        total_bots = len(bots)
        
        # Calculate total profit from bots
        total_profit = sum(b.get("total_profit", 0) for b in bots)
        
        # Get user info for system modes
        user = await db.users_collection.find_one({"id": user_id}, {"_id": 0})
        
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        # System modes
        system_mode = {
            "paper_trading": user.get("system_mode") == "testing" or user.get("system_mode") == "paper",
            "live_trading": user.get("system_mode") == "live_trading",
            "autonomous": user.get("autopilot_enabled", False)
        }
        
        # Bodyguard/risk lock status
        bodyguard_status = {
            "locked": user.get("daily_loss_lock_active", False),
            "reason": user.get("daily_loss_locked_reason"),
            "locked_at": user.get("daily_loss_locked_at"),
            "loss_pct": user.get("daily_loss_pct")
        }
        
        # Calculate time-based profits from trades
        now = datetime.now(timezone.utc)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        week_start = now - timedelta(days=7)
        month_start = now - timedelta(days=30)
        
        # Get trades for time calculations
        bot_ids = [b["id"] for b in bots]
        
        if bot_ids:
            # Today's profit
            daily_trades = await db.trades_collection.find({
                "bot_id": {"$in": bot_ids},
                "timestamp": {"$gte": today_start.isoformat()},
                "status": "closed"
            }, {"_id": 0, "net_pnl": 1, "profit_loss": 1}).to_list(10000)
            daily_profit = sum(t.get("net_pnl", t.get("profit_loss", 0)) for t in daily_trades)
            
            # Weekly profit
            weekly_trades = await db.trades_collection.find({
                "bot_id": {"$in": bot_ids},
                "timestamp": {"$gte": week_start.isoformat()},
                "status": "closed"
            }, {"_id": 0, "net_pnl": 1, "profit_loss": 1}).to_list(10000)
            weekly_profit = sum(t.get("net_pnl", t.get("profit_loss", 0)) for t in weekly_trades)
            
            # Monthly profit
            monthly_trades = await db.trades_collection.find({
                "bot_id": {"$in": bot_ids},
                "timestamp": {"$gte": month_start.isoformat()},
                "status": "closed"
            }, {"_id": 0, "net_pnl": 1, "profit_loss": 1}).to_list(10000)
            monthly_profit = sum(t.get("net_pnl", t.get("profit_loss", 0)) for t in monthly_trades)
            
            # Total trades and win rate
            all_trades = await db.trades_collection.find({
                "bot_id": {"$in": bot_ids},
                "status": "closed"
            }, {"_id": 0, "net_pnl": 1, "profit_loss": 1}).to_list(10000)
            
            total_trades = len(all_trades)
            winning_trades = sum(1 for t in all_trades if t.get("net_pnl", t.get("profit_loss", 0)) > 0)
            win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
            
            # Last trade time
            last_trade = await db.trades_collection.find_one(
                {"bot_id": {"$in": bot_ids}},
                {"_id": 0, "timestamp": 1},
                sort=[("timestamp", -1)]
            )
            last_trade_time = last_trade.get("timestamp") if last_trade else None
        else:
            # No bots
            daily_profit = 0
            weekly_profit = 0
            monthly_profit = 0
            total_trades = 0
            win_rate = 0
            last_trade_time = None
        
        return {
            "success": True,
            "total_profit": round(total_profit, 2),
            "daily_profit": round(daily_profit, 2),
            "weekly_profit": round(weekly_profit, 2),
            "monthly_profit": round(monthly_profit, 2),
            "active_bots": active_bots,
            "paused_bots": paused_bots,
            "training_bots": training_bots,
            "total_bots": total_bots,
            "total_trades": total_trades,
            "win_rate": round(win_rate, 1),
            "last_trade_time": last_trade_time,
            "system_mode": system_mode,
            "bodyguard_status": bodyguard_status,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Dashboard overview error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/overview/snapshot")
async def get_overview_snapshot(user_id: str = Depends(get_current_user)):
    """
    Enhanced overview snapshot - SINGLE SOURCE OF TRUTH for all dashboard metrics
    
    Returns comprehensive snapshot including:
    - Profit metrics (total, today, gross, net)
    - Fee metrics (total fees, today fees)
    - Trade metrics (count, win rate)
    - Bot metrics (active, paused, training, quarantine)
    - Capital metrics (equity, required capital by platform)
    - Market prices (BTC/ZAR, ETH/ZAR, XRP/ZAR with source and % change)
    - Daily loss lock state
    - Trading mode flags
    
    ALL dashboard tiles must use this endpoint. No duplicated calculations.
    """
    try:
        from services.overview_service import overview_service
        
        # Get complete snapshot from centralized service
        snapshot = await overview_service.get_snapshot(user_id)
        user_doc = await db.users_collection.find_one(
            {"id": user_id},
            {"_id": 0, "risk_profile": 1}
        )
        risk_level = (user_doc or {}).get("risk_profile") or "balanced"

        mode_flags = snapshot.get("trading_mode_flags") or {}
        if mode_flags.get("live_trading"):
            system_mode = "live"
        elif mode_flags.get("autopilot"):
            system_mode = "autopilot"
        else:
            system_mode = "paper"

        open_positions = 0
        if db.positions_collection is not None:
            try:
                open_positions = await db.positions_collection.count_documents({
                    "user_id": user_id,
                    "status": {"$ne": "closed"}
                })
            except Exception:
                open_positions = await db.positions_collection.count_documents({"user_id": user_id})

        normalized_snapshot = {
            "systemMode": system_mode,
            "activeBots": _safe_int(snapshot.get("bots_active", 0)),
            "openPositions": _safe_int(open_positions),
            "totalProfit": round(_safe_float(snapshot.get("total_profit", 0)), 2),
            "winRate": round(_safe_float(snapshot.get("win_rate", 0)), 2),
            "todaysTrades": _safe_int(snapshot.get("trades_today", 0)),
            "riskLevel": risk_level.replace("_", " ").title(),
            "lastRebalance": snapshot.get("last_rebalance") or "Not available",
            "nextReinvest": snapshot.get("next_reinvest") or "Not available",
        }

        return {
            **normalized_snapshot
        }
        
    except Exception as e:
        logger.error(f"Overview snapshot error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/dashboard/snapshot")
async def get_dashboard_snapshot(user_id: str = Depends(get_current_user)):
    """
    GET /api/dashboard/snapshot — SINGLE SOURCE OF TRUTH for all dashboard panels.

    Aggregates all subsystems into one authenticated response:
      - server_time
      - system_mode
      - bots_summary (counts, per-mode capital)
      - wallet_summary (paper + live balances, deficit)
      - trades_summary (open, closed, win/loss, last trade)
      - market_intel (mood, headline, fetch_status, block_reason, last_updated)
      - intelligence_status (running, last_run_at, next_run_in_seconds)
      - growth_status (enabled, blocked, regime, last_tick)
      - countdown (ready, progress, equity)

    Every section includes a `_as_of` timestamp.
    """
    now_iso = datetime.now(timezone.utc).isoformat()
    result: Dict = {"server_time": now_iso}

    # ── System mode ────────────────────────────────────────────────────────────
    try:
        from services.system_mode_service import system_mode_service
        mode = await system_mode_service.get_current_mode(user_id)
    except Exception:
        mode = "paper"
    result["system_mode"] = mode

    # ── Bots summary ──────────────────────────────────────────────────────────
    try:
        bots_active = bots_training = bots_paused = 0
        paper_bot_count = paper_bot_capital = live_bot_count = live_bot_capital = 0.0
        if db.bots_collection is not None:
            bots = await db.bots_collection.find(
                {"user_id": user_id, "status": {"$nin": ["deleted", "terminated"]}},
                {"_id": 0, "status": 1, "trading_mode": 1, "current_capital": 1, "initial_capital": 1, "training_complete": 1}
            ).to_list(500)
            for b in bots:
                s = b.get("status", "")
                tc = b.get("training_complete", True)
                cap = float(b.get("current_capital") or b.get("initial_capital") or 0)
                if s in ("active", "running"):
                    if not tc:
                        bots_training += 1
                    else:
                        bots_active += 1
                elif s == "paused":
                    bots_paused += 1
                bm = b.get("trading_mode", "paper")
                if s in ("active", "running"):
                    if bm == "live":
                        live_bot_count += 1
                        live_bot_capital += cap
                    else:
                        paper_bot_count += 1
                        paper_bot_capital += cap
        result["bots_summary"] = {
            "active": bots_active,
            "training": bots_training,
            "paused": bots_paused,
            "total": bots_active + bots_training + bots_paused,
            "paper_bots": {"count": int(paper_bot_count), "capital": round(paper_bot_capital, 2)},
            "live_bots": {"count": int(live_bot_count), "capital": round(live_bot_capital, 2)},
            "_as_of": now_iso,
        }
    except Exception as e:
        logger.warning(f"Dashboard snapshot: bots_summary error: {e}")
        result["bots_summary"] = {"active": 0, "training": 0, "paused": 0, "total": 0, "_error": str(e), "_as_of": now_iso}

    # ── Wallet summary ────────────────────────────────────────────────────────
    try:
        from services.paper_wallet_service import paper_wallet_service
        pw = await paper_wallet_service.get_balances(user_id)
        paper_available = float((pw.get("balances") or {}).get("ZAR", 0) or 0)
        result["wallet_summary"] = {
            "mode": mode,
            "paper": {"available": round(paper_available, 2), "currency": "ZAR"},
            "paper_bots_capital": round(result.get("bots_summary", {}).get("paper_bots", {}).get("capital", 0), 2),
            "live_bots_capital": round(result.get("bots_summary", {}).get("live_bots", {}).get("capital", 0), 2),
            "deficit": 0.0 if mode == "paper" else None,
            "_as_of": now_iso,
        }
    except Exception as e:
        logger.warning(f"Dashboard snapshot: wallet_summary error: {e}")
        result["wallet_summary"] = {"mode": mode, "_error": str(e), "_as_of": now_iso}

    # ── Trades summary ────────────────────────────────────────────────────────
    try:
        open_count = closed_count = wins = total = 0
        last_trade_at = None
        if db.trades_collection is not None:
            open_count = await db.trades_collection.count_documents({"user_id": user_id, "status": "open"})
            closed_docs = await db.trades_collection.find(
                {"user_id": user_id, "status": {"$in": ["closed", "completed"]}},
                {"_id": 0, "profit": 1, "closed_at": 1}
            ).sort("closed_at", -1).to_list(200)
            closed_count = len(closed_docs)
            wins = sum(1 for t in closed_docs if float(t.get("profit", 0) or 0) > 0)
            if closed_docs:
                last_trade_at = closed_docs[0].get("closed_at")
        result["trades_summary"] = {
            "open": open_count,
            "closed": closed_count,
            "wins": wins,
            "losses": max(0, closed_count - wins),
            "win_rate": round(wins / closed_count * 100, 1) if closed_count > 0 else 0,
            "last_trade_at": last_trade_at,
            "_as_of": now_iso,
        }
    except Exception as e:
        logger.warning(f"Dashboard snapshot: trades_summary error: {e}")
        result["trades_summary"] = {"open": 0, "closed": 0, "_error": str(e), "_as_of": now_iso}

    # ── Market intelligence ───────────────────────────────────────────────────
    try:
        from services.market_intelligence_service import get_latest_intelligence, _REFRESH_INTERVAL, _last_brief
        intel = await get_latest_intelligence()
        last_run_at = intel.get("updated_at")
        next_run_in = None
        if last_run_at:
            try:
                from datetime import timezone as _tz
                last_dt = datetime.fromisoformat(last_run_at.replace("Z", "+00:00"))
                elapsed = (datetime.now(timezone.utc) - last_dt).total_seconds()
                next_run_in = max(0, int(_REFRESH_INTERVAL - elapsed))
            except Exception:
                pass
        result["market_intel"] = {
            "mood": intel.get("mood", "neutral"),
            "headline": intel.get("what_happened", ""),
            "why_it_matters": intel.get("why_it_matters", ""),
            "what_amarktai_is_doing": intel.get("what_amarktai_is_doing", ""),
            "top_risk": intel.get("top_risk", "none"),
            "confidence": intel.get("confidence", ""),
            "source": intel.get("source", "CoinStats"),
            "fetch_status": intel.get("fetch_status", "ok" if last_run_at else "pending"),
            "block_reason": intel.get("block_reason"),
            "last_updated": last_run_at,
            "_as_of": now_iso,
        }
        result["intelligence_status"] = {
            "running": True,
            "last_run_at": last_run_at,
            "next_run_in_seconds": next_run_in,
            "refresh_interval_seconds": _REFRESH_INTERVAL,
        }
    except Exception as e:
        logger.warning(f"Dashboard snapshot: market_intel error: {e}")
        result["market_intel"] = {"mood": "neutral", "fetch_status": "error", "block_reason": str(e), "_as_of": now_iso}
        result["intelligence_status"] = {"running": False, "_error": str(e), "_as_of": now_iso}

    # ── Growth engine status ──────────────────────────────────────────────────
    try:
        from services.growth_engine_service import get_settings, get_state, _check_guardrails
        ge_settings = await get_settings(user_id)
        ge_state = await get_state(user_id)
        guardrail = await _check_guardrails(user_id)
        result["growth_status"] = {
            "enabled": ge_settings.get("enabled", False),
            "blocked": not guardrail.get("ok", True),
            "blocked_reasons": guardrail.get("reasons", []),
            "guardrails": {
                "status": guardrail.get("status", "ok"),
                "checks": guardrail.get("checks", {}),
            },
            "current_regime": ge_state.get("current_regime", "neutral"),
            "confidence": ge_state.get("confidence", 0.0),
            "last_tick": ge_state.get("last_tick"),
            "_as_of": now_iso,
        }
    except Exception as e:
        logger.warning(f"Dashboard snapshot: growth_status error: {e}")
        result["growth_status"] = {"enabled": False, "_error": str(e), "_as_of": now_iso}

    # ── Countdown ─────────────────────────────────────────────────────────────
    try:
        countdown_data = {}
        if db.db is not None:
            coll = db.db.get_collection("countdowns") if hasattr(db.db, "get_collection") else None
            if coll is not None:
                cd = await coll.find_one({"user_id": user_id}, {"_id": 0})
                if cd:
                    countdown_data = {
                        "ready": cd.get("ready", False),
                        "progress": cd.get("progress", 0),
                        "equity": cd.get("equity", 0),
                    }
        result["countdown"] = {**countdown_data, "_as_of": now_iso}
    except Exception as e:
        logger.warning(f"Dashboard snapshot: countdown error: {e}")
        result["countdown"] = {"_error": str(e), "_as_of": now_iso}

    return result
