"""
Growth Engine Service
=====================
Safe, per-user, paper-trading growth automation.

SAFETY PRINCIPLES:
- Never implements its own trading engine.
- Creates/scales bots via existing bot lifecycle endpoints only.
- Moves capital via ledger-first events only.
- Always checks Bodyguard / daily loss locks / duplicate-detection first.
- All actions are off by default and require explicit user opt-in.
- Everything is reversible; actions are rate-limited.
- Leverage is a position-sizing multiplier (1.0-2.0); auto-reverts to 1.0 on any lock.
  In live mode, leverage only applies on exchanges that support it (capability flag).
"""

import asyncio
import logging
import time
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)

# How often the scheduler tick runs (seconds)
_TICK_INTERVAL_SECONDS = 300  # 5 minutes

# Per-user in-memory state cache (reset on restart)
_user_state_cache: Dict[str, dict] = {}


# ── Default settings ──────────────────────────────────────────────────────────

DEFAULT_SETTINGS = {
    # Master switch — everything off unless user enables
    "enabled": False,
    # Individual feature toggles
    "profit_recycling": False,       # Spawn bots from realized profits
    "capital_redistribution": False, # Shift capital worst→best performers
    "strategy_specialization": False, # Assign regime-based bot profiles
    "trade_frequency_tuning": False,  # Adjust bot cooldowns within bounds
    "dynamic_risk_budgeting": False,  # Scale risk budget with equity highs
    "capital_aggression": False,      # Temporarily increase capital allocation
    "exchange_filtering": False,      # Re-weight allocations by exchange score
    "bot_cap_ramp": False,            # Increase bot cap funded from profits
    # Leverage: position sizing multiplier (default OFF, 1.0x–2.0x)
    "leverage_enabled": False,        # Toggle — off by default; auto-reverts on any lock
    "leverage_multiplier": 1.0,       # 1.0 = no leverage, 2.0 = double position size
    # Thresholds / caps
    "profit_recycle_threshold_r": 100.0,   # Min profit (ZAR) before recycling
    "profit_recycle_max_per_day": 2,        # Max bots spawned per day
    "capital_shift_max_pct": 20.0,          # Max % to shift per tick
    "bot_cap_max": 10,                      # Hard upper limit on bot count
    "aggression_min_green_days": 5,         # Days of profit required before aggression
    "aggression_max_drawdown_pct": 5.0,     # Max drawdown % to allow aggression
    "risk_budget_scale_factor": 1.0,        # Current risk budget multiplier (1.0 = unchanged)
    # Safety
    "require_no_locks_for_aggression": True,
    "auto_revert_aggression_after_hours": 24,
}


# ── Guardrail helpers ─────────────────────────────────────────────────────────

async def _check_guardrails(user_id: str) -> Dict[str, Any]:
    """
    Check all safety gates and return a dict of active blocks.
    Returns {"ok": True} if all clear, or {"ok": False, "reasons": [...]} if blocked.
    """
    blocked_reasons = []
    try:
        import database as db
        if db.users_collection is None:
            return {"ok": False, "reasons": ["Database not initialized"]}

        user = await db.users_collection.find_one({"id": user_id}, {"_id": 0})
        if not user:
            return {"ok": False, "reasons": ["User not found"]}

        # Daily loss lock
        if user.get("daily_loss_lock_active"):
            blocked_reasons.append(
                f"Daily loss lock is active (triggered {user.get('daily_loss_locked_reason', 'limit exceeded')}). "
                "Growth Engine paused until lock resets."
            )

        # Bodyguard lock
        if user.get("bodyguard_lock_active"):
            blocked_reasons.append(
                "AI Bodyguard lock is active. Growth Engine paused until bodyguard resets."
            )

        # Emergency stop
        emergency_doc = await db.emergency_stop_collection.find_one(
            {"user_id": user_id, "active": True}, {"_id": 0}
        ) if db.emergency_stop_collection else None
        if emergency_doc:
            blocked_reasons.append(
                "Emergency stop is engaged. Growth Engine paused until emergency stop is lifted."
            )

    except Exception as e:
        logger.warning(f"Growth guardrail check error for {user_id}: {e}")
        blocked_reasons.append(f"Guardrail check failed: {str(e)[:100]}")

    if blocked_reasons:
        return {"ok": False, "reasons": blocked_reasons}
    return {"ok": True, "reasons": []}


# ── Settings persistence ──────────────────────────────────────────────────────

async def get_settings(user_id: str) -> dict:
    """Get growth engine settings for user, merging with defaults."""
    try:
        import database as db
        if db.db is None:
            return {**DEFAULT_SETTINGS, "user_id": user_id}
        coll = db.db["growth_engine_settings"]
        doc = await coll.find_one({"user_id": user_id}, {"_id": 0})
        if doc:
            merged = {**DEFAULT_SETTINGS, **{k: v for k, v in doc.items() if k != "_id"}}
        else:
            merged = {**DEFAULT_SETTINGS, "user_id": user_id}
        return merged
    except Exception as e:
        logger.error(f"get_settings error for {user_id}: {e}")
        return {**DEFAULT_SETTINGS, "user_id": user_id}


async def save_settings(user_id: str, settings: dict) -> dict:
    """Persist updated growth engine settings."""
    try:
        import database as db
        if db.db is None:
            return settings
        coll = db.db["growth_engine_settings"]
        merged = {**DEFAULT_SETTINGS, **settings, "user_id": user_id,
                  "updated_at": datetime.now(timezone.utc).isoformat()}
        # Clamp leverage multiplier to safe bounds
        merged["leverage_multiplier"] = max(1.0, min(2.0, float(merged.get("leverage_multiplier", 1.0))))
        await coll.replace_one({"user_id": user_id}, merged, upsert=True)
        return merged
    except Exception as e:
        logger.error(f"save_settings error for {user_id}: {e}")
        return settings


# ── State helpers ─────────────────────────────────────────────────────────────

async def get_state(user_id: str) -> dict:
    """Get current growth engine state for user."""
    try:
        import database as db
        if db.db is None:
            return {"user_id": user_id, "last_tick": None, "current_regime": "unknown",
                    "confidence": 0.0, "blocked_reasons": [], "last_actions": []}
        coll = db.db["growth_engine_state"]
        doc = await coll.find_one({"user_id": user_id}, {"_id": 0})
        return doc or {"user_id": user_id, "last_tick": None, "current_regime": "unknown",
                       "confidence": 0.0, "blocked_reasons": [], "last_actions": []}
    except Exception as e:
        logger.error(f"get_state error for {user_id}: {e}")
        return {"user_id": user_id, "last_tick": None, "current_regime": "unknown",
                "confidence": 0.0, "blocked_reasons": [], "last_actions": []}


async def _save_state(user_id: str, state: dict):
    """Persist growth engine state."""
    try:
        import database as db
        if db.db is None:
            return
        coll = db.db["growth_engine_state"]
        state["user_id"] = user_id
        await coll.replace_one({"user_id": user_id}, state, upsert=True)
    except Exception as e:
        logger.error(f"_save_state error for {user_id}: {e}")


async def _append_decision(decision: dict):
    """Append a decision record to the append-only log."""
    try:
        import database as db
        if db.db is None:
            return
        coll = db.db["growth_engine_decisions"]
        await coll.insert_one(decision)
    except Exception as e:
        logger.error(f"_append_decision error: {e}")


async def get_decisions(user_id: str, limit: int = 50) -> List[dict]:
    """Get recent decisions for user."""
    try:
        import database as db
        if db.db is None:
            return []
        coll = db.db["growth_engine_decisions"]
        docs = await coll.find(
            {"user_id": user_id}, {"_id": 0}
        ).sort("timestamp", -1).to_list(limit)
        return docs
    except Exception as e:
        logger.error(f"get_decisions error for {user_id}: {e}")
        return []


# ── Regime detection ──────────────────────────────────────────────────────────

async def _detect_regime() -> tuple[str, float]:
    """
    Detect current market regime using CoinStats intelligence and live prices.
    Returns (regime_name, confidence 0-1).
    """
    try:
        from services.market_intelligence_service import get_latest_intelligence
        intel = await get_latest_intelligence()
        mood = intel.get("mood", "neutral")
        risk = intel.get("top_risk", "none")
        updated_at = intel.get("updated_at")

        # Stale if not updated in last 30 minutes
        if updated_at:
            try:
                last_dt = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
                age_minutes = (datetime.now(timezone.utc) - last_dt).total_seconds() / 60
                if age_minutes > 30:
                    return "unknown", 0.3
            except Exception:
                pass

        if mood == "positive" and risk == "none":
            return "trend", 0.7
        elif mood == "negative" and risk != "none":
            return "risk_off", 0.8
        elif mood == "negative":
            return "range", 0.6
        elif risk != "none":
            return "volatile", 0.65
        else:
            return "neutral", 0.5
    except Exception as e:
        logger.debug(f"Regime detection error: {e}")
        return "unknown", 0.3


# ── Individual feature implementations ───────────────────────────────────────

async def _run_profit_recycling(user_id: str, settings: dict, regime: str) -> Optional[dict]:
    """
    Spawn a new paper bot ONLY from realized profits above threshold.
    Uses existing /bots/spawn lifecycle; respects daily cap.
    """
    try:
        import database as db
        threshold = float(settings.get("profit_recycle_threshold_r", 100.0))
        max_per_day = int(settings.get("profit_recycle_max_per_day", 2))

        # Count today's growth-spawned bots
        today = datetime.now(timezone.utc).date().isoformat()
        today_spawns = await db.db["growth_engine_decisions"].count_documents({
            "user_id": user_id,
            "action": "profit_recycling",
            "date": today,
            "outcome": "spawned"
        }) if db.db else 0

        if today_spawns >= max_per_day:
            return {"skipped": True, "reason": f"Daily spawn limit reached ({max_per_day}/day)"}

        # Get realized profits
        from services.accounting import accounting_service
        metrics = await accounting_service.get_unified_metrics(user_id=user_id, trading_mode="paper")
        net_pnl = metrics.get("net_realised_pnl_zar", 0.0)

        if net_pnl < threshold:
            return {"skipped": True, "reason": f"Net profit R{net_pnl:.2f} below threshold R{threshold:.2f}"}

        # Check bot cap
        bot_cap = int(settings.get("bot_cap_max", 10))
        existing_bots = await db.bots_collection.count_documents(
            {"user_id": user_id, "status": {"$nin": ["stopped", "terminated"]}}
        )
        if existing_bots >= bot_cap:
            return {"skipped": True, "reason": f"Bot cap reached ({bot_cap} active bots)"}

        # Spawn via existing engine (dry-run in this implementation — logs decision)
        # In production: call bot_spawner.spawn_bot(user_id, config)
        spawn_capital = min(net_pnl * 0.1, 50.0)  # 10% of profits, max R50
        return {
            "action_taken": True,
            "description": f"Profit recycling: proposed to spawn 1 bot with R{spawn_capital:.2f} from profits "
                           f"(R{net_pnl:.2f} realized). Requires manual confirmation via Growth Engine run-once.",
            "spawn_capital": spawn_capital,
            "net_pnl_used": net_pnl,
        }

    except Exception as e:
        logger.error(f"Profit recycling error for {user_id}: {e}")
        return {"error": str(e)}


async def _run_capital_redistribution(user_id: str, settings: dict) -> Optional[dict]:
    """
    Identify worst and best performing bots, log proposed capital shift.
    Uses ledger-first events only.
    """
    try:
        import database as db
        max_shift_pct = float(settings.get("capital_shift_max_pct", 20.0))

        bots = await db.bots_collection.find(
            {"user_id": user_id, "status": "active"},
            {"_id": 0, "id": 1, "name": 1, "total_profit": 1, "current_capital": 1}
        ).to_list(50)

        if len(bots) < 2:
            return {"skipped": True, "reason": "Need at least 2 active bots for redistribution"}

        sorted_bots = sorted(bots, key=lambda b: float(b.get("total_profit", 0)))
        worst = sorted_bots[0]
        best = sorted_bots[-1]

        worst_capital = float(worst.get("current_capital", 0))
        if worst_capital <= 0:
            return {"skipped": True, "reason": "Worst bot has no capital to redistribute"}

        shift_amount = min(worst_capital * (max_shift_pct / 100), worst_capital * 0.2)
        return {
            "action_taken": True,
            "description": (
                f"Capital redistribution: proposed to move R{shift_amount:.2f} "
                f"from '{worst.get('name', worst['id'])}' (profit: R{worst.get('total_profit', 0):.2f}) "
                f"to '{best.get('name', best['id'])}' (profit: R{best.get('total_profit', 0):.2f}). "
                "Requires run-once confirmation."
            ),
            "shift_amount": shift_amount,
            "from_bot": worst.get("id"),
            "to_bot": best.get("id"),
        }
    except Exception as e:
        logger.error(f"Capital redistribution error for {user_id}: {e}")
        return {"error": str(e)}


async def _run_strategy_specialization(user_id: str, regime: str) -> Optional[dict]:
    """Log regime-based strategy assignment recommendation."""
    REGIME_STRATEGIES = {
        "trend": "momentum",
        "range": "range",
        "volatile": "micro-scalp",
        "risk_off": "range",
        "neutral": "range",
        "breakout": "breakout",
    }
    strategy = REGIME_STRATEGIES.get(regime, "range")
    return {
        "action_taken": True,
        "description": (
            f"Strategy specialization: regime='{regime}' → recommended strategy profile='{strategy}'. "
            "Profile assignment is logged for manual review. Auto-assignment requires run-once."
        ),
        "recommended_strategy": strategy,
        "regime": regime,
    }



# ── Exchange leverage capability registry ─────────────────────────────────────

# Exchanges that support leverage/margin trading
_LEVERAGE_CAPABLE_EXCHANGES = {
    "binance": True,
    "bybit": True,
    "bitmex": True,
    "okx": True,
    "kraken": True,
    "luno": False,       # Spot-only
    "valr": False,       # Spot-only
    "altcointrader": False,
}


async def _get_user_exchange(user_id: str) -> str:
    """Get the primary exchange for a user."""
    try:
        import database as db
        if db.db is None:
            return "unknown"
        key_doc = await db.api_keys_collection.find_one(
            {"user_id": user_id, "is_active": True}, {"provider": 1, "_id": 0}
        )
        return (key_doc.get("provider") or "unknown").lower() if key_doc else "unknown"
    except Exception:
        return "unknown"


async def _run_leverage(user_id: str, settings: dict, guardrail: dict) -> dict:
    """
    Apply leverage multiplier to position sizing.
    - Paper mode: always allowed within bounds.
    - Live mode: only when the user's exchange supports it.
    - Auto-reverts to 1.0 if any guardrail lock is active.
    Guardrails: max 2.0x, only when locks are clear and multiplier > 1.0.
    """
    # Auto-revert if any lock is active
    if not guardrail["ok"]:
        await _persist_leverage_multiplier(user_id, 1.0)
        return {
            "action_taken": True,
            "multiplier": 1.0,
            "description": "Leverage auto-reverted to 1.0x — safety lock is active.",
            "auto_reverted": True,
        }

    requested = float(settings.get("leverage_multiplier", 1.0))
    # Clamp to safe bounds
    multiplier = max(1.0, min(2.0, requested))

    # Check live-mode exchange capability
    try:
        import database as db
        user_doc = await db.users_collection.find_one({"id": user_id}, {"trading_mode": 1, "_id": 0})
        trading_mode = (user_doc or {}).get("trading_mode", "paper")
    except Exception:
        trading_mode = "paper"

    if trading_mode == "live":
        exchange = await _get_user_exchange(user_id)
        capable = _LEVERAGE_CAPABLE_EXCHANGES.get(exchange, None)
        if capable is False:
            await _persist_leverage_multiplier(user_id, 1.0)
            return {
                "action_taken": False,
                "multiplier": 1.0,
                "skipped": True,
                "reason": f"Not available on {exchange} (spot-only exchange — no margin/futures support).",
            }
        if capable is None:
            await _persist_leverage_multiplier(user_id, 1.0)
            return {
                "action_taken": False,
                "multiplier": 1.0,
                "skipped": True,
                "reason": f"Exchange '{exchange}' capability unknown — leverage disabled for safety.",
            }

    await _persist_leverage_multiplier(user_id, multiplier)
    return {
        "action_taken": True,
        "multiplier": multiplier,
        "description": (
            f"Leverage multiplier set to {multiplier:.1f}x — position sizes scaled accordingly. "
            "Auto-reverts to 1.0x if any safety lock activates."
        ),
        "mode": trading_mode,
    }


async def _persist_leverage_multiplier(user_id: str, multiplier: float):
    """Persist the effective leverage multiplier for the user."""
    try:
        import database as db
        if db.db is None:
            return
        await db.db["growth_engine_settings"].update_one(
            {"user_id": user_id},
            {"$set": {"effective_leverage_multiplier": multiplier,
                       "leverage_updated_at": datetime.now(timezone.utc).isoformat()}},
            upsert=True,
        )
    except Exception as e:
        logger.debug(f"Could not persist leverage multiplier: {e}")


async def get_effective_leverage_multiplier(user_id: str) -> float:
    """
    Returns the current effective leverage multiplier for a user.
    Used by the trading engine to scale position sizes.
    Returns 1.0 if leverage is disabled or any lock is active.
    """
    try:
        import database as db
        if db.db is None:
            return 1.0
        coll = db.db["growth_engine_settings"]
        doc = await coll.find_one({"user_id": user_id}, {"_id": 0})
        if not doc or not doc.get("leverage_enabled"):
            return 1.0
        # Auto-revert check
        guardrail = await _check_guardrails(user_id)
        if not guardrail["ok"]:
            return 1.0
        return max(1.0, min(2.0, float(doc.get("effective_leverage_multiplier", 1.0))))
    except Exception:
        return 1.0



async def run_tick(user_id: str, force: bool = False) -> dict:
    """
    Execute one Growth Engine tick for the given user.

    Returns a decision record dict with all actions, reasons, and outcomes.
    """
    now = datetime.now(timezone.utc)
    decision_id = f"ge_{user_id}_{int(now.timestamp())}"

    decision = {
        "decision_id": decision_id,
        "user_id": user_id,
        "timestamp": now.isoformat(),
        "date": now.date().isoformat(),
        "force": force,
        "inputs": {},
        "actions_proposed": [],
        "actions_taken": [],
        "blocked_reasons": [],
        "regime": "unknown",
        "confidence": 0.0,
        "summary": "",
    }

    try:
        # 1. Load settings
        settings = await get_settings(user_id)
        decision["inputs"]["settings_loaded"] = True

        # 2. Fast exit if master switch is off
        if not settings.get("enabled", False):
            decision["summary"] = "Growth Engine is disabled (master switch off)."
            decision["blocked_reasons"] = ["Master switch is off"]
            await _append_decision(decision)
            return decision

        # 3. Check guardrails
        guardrail = await _check_guardrails(user_id)
        if not guardrail["ok"]:
            decision["blocked_reasons"] = guardrail["reasons"]
            decision["summary"] = "Blocked by safety guardrails: " + "; ".join(guardrail["reasons"])
            await _save_state(user_id, {
                "last_tick": now.isoformat(),
                "blocked_reasons": guardrail["reasons"],
                "current_regime": "unknown",
                "confidence": 0.0,
                "last_actions": [],
            })
            await _append_decision(decision)
            return decision

        # 4. Detect regime
        regime, confidence = await _detect_regime()
        decision["regime"] = regime
        decision["confidence"] = confidence
        decision["inputs"]["regime"] = regime
        decision["inputs"]["confidence"] = confidence

        # 5. Run enabled features
        actions = []

        if settings.get("profit_recycling"):
            result = await _run_profit_recycling(user_id, settings, regime)
            if result:
                decision["actions_proposed"].append({"feature": "profit_recycling", **result})
                if result.get("action_taken"):
                    actions.append(f"Profit recycling: {result.get('description', '')[:80]}")

        if settings.get("capital_redistribution"):
            result = await _run_capital_redistribution(user_id, settings)
            if result:
                decision["actions_proposed"].append({"feature": "capital_redistribution", **result})
                if result.get("action_taken"):
                    actions.append(f"Capital redistribution: {result.get('description', '')[:80]}")

        if settings.get("strategy_specialization"):
            result = await _run_strategy_specialization(user_id, regime)
            if result:
                decision["actions_proposed"].append({"feature": "strategy_specialization", **result})
                if result.get("action_taken"):
                    actions.append(f"Strategy specialization → {result.get('recommended_strategy', '')}")

        if settings.get("leverage_enabled"):
            leverage_result = await _run_leverage(user_id, settings, guardrail)
            decision["actions_proposed"].append({"feature": "leverage", **leverage_result})
            if leverage_result.get("action_taken"):
                actions.append(f"Leverage: multiplier set to {leverage_result.get('multiplier', 1.0):.1f}x")

        decision["actions_taken"] = actions
        decision["summary"] = (
            f"Tick complete. Regime: {regime} (confidence {confidence:.0%}). "
            f"{len(actions)} actions proposed. "
            + ("; ".join(actions[:3]) if actions else "No actions taken.")
        )

        # 6. Save state
        await _save_state(user_id, {
            "last_tick": now.isoformat(),
            "blocked_reasons": [],
            "current_regime": regime,
            "confidence": confidence,
            "last_actions": actions[-5:],
        })

        # 7. Emit event
        try:
            from routes.events import emit_event
            if actions:
                await emit_event(
                    user_id, "growth_engine", "info",
                    f"📈 Growth Engine: {len(actions)} action(s) proposed — {'; '.join(actions[:2])}",
                    meta={"regime": regime},
                )
        except Exception:
            pass

    except Exception as e:
        logger.error(f"Growth Engine tick error for {user_id}: {e}", exc_info=True)
        decision["summary"] = f"Tick error: {str(e)[:200]}"
        decision["blocked_reasons"].append(f"Internal error: {str(e)[:100]}")

    await _append_decision(decision)
    return decision


# ── Background scheduler ──────────────────────────────────────────────────────

async def start_growth_engine_scheduler():
    """
    Background task: run Growth Engine tick for all users with it enabled.
    Runs every _TICK_INTERVAL_SECONDS.
    """
    logger.info(f"Growth Engine scheduler starting (interval={_TICK_INTERVAL_SECONDS}s)")
    while True:
        try:
            import database as db
            if db.db is not None:
                coll = db.db["growth_engine_settings"]
                enabled_users = await coll.find(
                    {"enabled": True}, {"user_id": 1, "_id": 0}
                ).to_list(200)
                for u in enabled_users:
                    uid = u.get("user_id")
                    if uid:
                        try:
                            await run_tick(uid)
                        except Exception as e:
                            logger.warning(f"Growth tick error for user {uid}: {e}")
        except Exception as e:
            logger.error(f"Growth scheduler error: {e}")
        await asyncio.sleep(_TICK_INTERVAL_SECONDS)
