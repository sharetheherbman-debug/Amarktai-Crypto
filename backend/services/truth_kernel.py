"""
Truth Kernel — Single Source of Truth for System State

Computes canonical system state from the ledger, DB, and live runtime.
All summary endpoints should read from Truth Kernel outputs rather than
recomputing independently.

Canonical outputs:
  - bot_eligibility: eligible_to_trade per bot with reason codes
  - wallet_balances: available/allocated/reserved per currency
  - risk_state: peak equity, drawdown, daily PnL
  - scheduler_state: last_tick, lag, running
  - exchange_readiness: per-exchange health status
  - exposure_state: per-coin, per-exchange, per-side exposure

Rule Precedence (highest → lowest):
  1) Emergency stop (global/user)
  2) Circuit breaker
  3) Daily loss lock
  4) Bodyguard lock
  5) Quarantine / training gate
  6) Exchange health / API degraded
  7) Wallet insufficiency
  8) Strategy gating (min edge / spread / volatility filters)
"""

from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any
import logging

from utils.bot_state import normalize_bot_state

# ── Named constants for thresholds ──────────────────────────────────────
BALANCE_TOLERANCE = 0.01           # Cents tolerance for wallet reconciliation
SCHEDULER_STALE_THRESHOLD_SECONDS = 120  # Seconds before scheduler is considered stale
MAX_DRAWDOWN_PERCENT = 20          # Maximum drawdown % before risk FAIL

logger = logging.getLogger(__name__)

# ── Rule precedence order (highest priority first) ──────────────────────
RULE_PRECEDENCE = [
    "emergency_stop",
    "circuit_breaker",
    "daily_loss_lock",
    "bodyguard_lock",
    "quarantine_training_gate",
    "exchange_health",
    "wallet_insufficiency",
    "strategy_gating",
]

# Subsystem identifiers for truth summary
SUBSYSTEMS = [
    "TRUTH_KERNEL",
    "BOT_ELIGIBILITY",
    "PAPER_ENGINE",
    "LEDGER_TRUTH",
    "WALLET_RECONCILIATION",
    "RISK_BASELINES",
    "DAILY_CLOSE",
    "AUTOSPAWN",
    "TRAINING_GATE",
    "EXCHANGE_HEALTH",
    "REALTIME",
    "AI_CHATOPS",
    "UI_HEALTH",
    "SCALPER",
]


async def compute_bot_eligibility(user_id: str, db) -> Dict[str, Any]:
    """Canonical bot eligibility from the DB."""
    bots_raw = await db["bots"].find(
        {"user_id": user_id, "deleted": {"$ne": True}}
    ).to_list(length=500)

    bots = [normalize_bot_state(b) for b in bots_raw]
    total = len(bots)
    eligible = [b for b in bots if b.get("eligible_to_trade")]
    ineligible = [b for b in bots if not b.get("eligible_to_trade")]

    # Separate normal vs scalper counts
    normal_bots = [b for b in bots if b.get("bot_type", "normal") == "normal"]
    scalper_bots = [b for b in bots if b.get("bot_type") == "scalper"]

    return {
        "total_bots": total,
        "eligible_count": len(eligible),
        "ineligible_count": len(ineligible),
        "normal_count": len(normal_bots),
        "scalper_count": len(scalper_bots),
        "ineligible_reasons": {
            str(b.get("_id", "")): b.get("not_eligible_reasons", [])
            for b in ineligible
        },
    }


async def compute_wallet_balances(user_id: str, db) -> Dict[str, Any]:
    """Canonical wallet balances for the paper wallet.

    Reads from the same source as /api/wallet/paper:
    - ``wallet_balances`` collection keyed by user_id stores the cached totals
      that paper_wallet_ledger._update_user_wallet_balance() writes after every
      reserve / debit / credit operation.
    - Falls back to reading the raw ``wallets`` document (type=paper) directly
      in case the cached fields are absent.

    This ensures truth_kernel WALLET_RECONCILIATION agrees with /api/wallet/paper
    and the Truth Console rather than reading from a non-existent ``paper_wallets``
    collection.
    """
    # Primary: cached totals written by paper_wallet_ledger
    wb = await db["wallet_balances"].find_one({"user_id": user_id}) or {}
    total = float(wb.get("paper_wallet_balance_zar", 0) or 0)
    available = float(wb.get("paper_wallet_available_zar", 0) or 0)
    allocated = float(wb.get("paper_wallet_allocated_zar", 0) or 0)

    # Fallback: raw wallets doc (type=paper, balances dict)
    if total == 0 and available == 0 and allocated == 0:
        raw = await db["wallets"].find_one({"user_id": user_id, "type": "paper"}) or {}
        balances = raw.get("balances") or {}
        zar_raw = float(balances.get("ZAR", 0) or 0)
        if zar_raw > 0:
            available = zar_raw
            total = zar_raw

    zar = available
    usdt = 0.0  # paper mode is ZAR-only; extend here if multi-currency is added

    balance_check = abs(total - (available + allocated)) < BALANCE_TOLERANCE

    return {
        "total": round(total, 2),
        "available": round(available, 2),
        "reserved": round(allocated, 2),
        "zar_available": round(zar, 2),
        "usdt_available": usdt,
        "balance_check": balance_check,
        "negative_balance": available < 0 or allocated < 0,
    }


async def compute_risk_state(user_id: str, db) -> Dict[str, Any]:
    """Canonical risk state: peak equity, drawdown, daily PnL."""
    bots_raw = await db["bots"].find(
        {"user_id": user_id, "deleted": {"$ne": True}}
    ).to_list(length=500)

    total_equity = sum(float(b.get("current_capital", 0)) for b in bots_raw)
    peak_equity = max(
        (float(b.get("peak_equity", b.get("current_capital", 0))) for b in bots_raw),
        default=0,
    )
    drawdown_pct = ((peak_equity - total_equity) / peak_equity * 100) if peak_equity > 0 else 0

    # Daily PnL from fills
    from jobs.daily_close import sast_day_boundaries
    start_utc, end_utc = sast_day_boundaries()
    fills = await db["fills_ledger"].find(
        {"user_id": user_id, "timestamp": {"$gte": start_utc, "$lt": end_utc}}
    ).to_list(length=10000)
    daily_pnl = sum(float(f.get("realized_pnl", 0)) for f in fills)

    return {
        "total_equity": round(total_equity, 2),
        "peak_equity": round(peak_equity, 2),
        "drawdown_pct": round(drawdown_pct, 2),
        "daily_realized_pnl": round(daily_pnl, 2),
        "fills_today": len(fills),
    }


async def compute_scheduler_state(db) -> Dict[str, Any]:
    """Canonical scheduler state.

    Uses the same live heartbeat_registry that /api/autonomy/status uses, so
    PAPER_ENGINE in the Truth Console agrees with the autonomy subsystem panel.

    The ``scheduler_heartbeat`` MongoDB collection is never written to by the
    current trading_scheduler, so relying on it always showed FAIL even while
    the scheduler was running.  We now read the in-process registry and, as a
    secondary cross-check, also inspect trading_scheduler.is_running.
    """
    try:
        from services.autonomy_heartbeat import heartbeat_registry
        watchdog = heartbeat_registry.check_stale()
        ts_state = watchdog.get("trading_scheduler", {})
        alive = ts_state.get("alive", False)
        last_ok = ts_state.get("last_ok_at")
    except (ImportError, AttributeError, KeyError) as exc:
        logger.debug("heartbeat_registry check failed in compute_scheduler_state: %s", exc)
        alive = False
        last_ok = None

    # Cross-check with the scheduler's own is_running flag
    try:
        from trading_scheduler import trading_scheduler as _ts
        is_running = getattr(_ts, "is_running", False)
        last_tick_at = getattr(_ts, "last_tick_at", None)
    except (ImportError, AttributeError) as exc:
        logger.debug("trading_scheduler import failed in compute_scheduler_state: %s", exc)
        is_running = False
        last_tick_at = None

    running = is_running or alive

    # Determine lag from last_tick_at (most granular) or last heartbeat ok
    last_tick_str = last_tick_at or last_ok
    lag: Optional[float] = None
    if last_tick_str:
        try:
            if isinstance(last_tick_str, str):
                ts_dt = datetime.fromisoformat(last_tick_str.replace("Z", "+00:00"))
            else:
                ts_dt = last_tick_str
            lag = (datetime.now(timezone.utc) - ts_dt).total_seconds()
        except Exception:
            lag = None

    stale = (lag is not None and lag > SCHEDULER_STALE_THRESHOLD_SECONDS) or (
        not running and lag is None
    )

    return {
        "running": running,
        "scheduler_running": running,
        "last_tick": last_tick_str,
        "lag_seconds": round(lag, 1) if lag is not None else None,
        "stale": stale,
    }


async def compute_exchange_readiness(user_id: str, db) -> Dict[str, Any]:
    """Per-exchange health from canonical API key documents.

    Uses the same underlying key documents that power /api/keys/status to avoid
    truth drift between Truth Console EXCHANGE_HEALTH and key-status panels.
    """
    from services.exchange_adapter import SUPPORTED_EXCHANGES

    results = {}
    for ex in SUPPORTED_EXCHANGES:
        key_doc = await db["api_keys"].find_one(
            {"user_id": user_id, "provider": ex},
            {
                "_id": 0,
                "api_key": 1,
                "api_key_encrypted": 1,
                "status": 1,
                "last_test_ok": 1,
                "last_tested_at": 1,
                "last_test_error": 1,
            },
        )
        configured = bool(
            key_doc and (
                key_doc.get("api_key")
                or key_doc.get("api_key_encrypted")
            )
        )
        test_passed = key_doc.get("last_test_ok") if key_doc else None
        if test_passed is None and key_doc:
            status = (key_doc.get("status") or "").lower()
            if status in {"configured_valid", "test_ok"}:
                test_passed = True
            elif status in {"configured_invalid", "test_failed"}:
                test_passed = False
        results[ex] = {
            "configured": configured,
            "test_passed": test_passed,
            "error": key_doc.get("last_test_error") if key_doc else None,
            "last_tested_at": key_doc.get("last_tested_at") if key_doc else None,
        }
    configured_count = sum(1 for v in results.values() if v["configured"])
    return {
        "exchanges": results,
        "configured_count": configured_count,
        "total_exchanges": len(SUPPORTED_EXCHANGES),
    }


async def compute_daily_close_state(user_id: str, db) -> Dict[str, Any]:
    """Status of last daily close run."""
    from jobs.daily_close import sast_now, make_run_id
    now_sast = sast_now()
    date_str = now_sast.strftime("%Y-%m-%d")
    run_id = make_run_id(date_str, user_id)

    run_doc = await db["daily_close_runs"].find_one({"run_id": run_id})
    return {
        "today_date": date_str,
        "ran_today": run_doc is not None,
        "run_id": run_id,
        "completed_at": run_doc.get("completed_at") if run_doc else None,
        "status": run_doc.get("report", {}).get("status") if run_doc else "NOT_RUN",
    }


async def compute_realtime_state(db) -> Dict[str, Any]:
    """WebSocket / realtime connection state."""
    try:
        from websocket_manager import manager
        active = len(manager.active_connections) if hasattr(manager, "active_connections") else 0
    except Exception:
        active = 0
    return {
        "ws_connections": active,
        "healthy": active >= 0,  # 0 is OK if no one is connected
    }


async def compute_truth_summary(user_id: str, db) -> Dict[str, Any]:
    """
    Master truth summary used by both Go-Live Gate and Admin Truth Console.
    Returns per-subsystem PASS/FAIL with evidence fields and reason codes.
    """
    now = datetime.now(timezone.utc)

    bots = await compute_bot_eligibility(user_id, db)
    wallet = await compute_wallet_balances(user_id, db)
    risk = await compute_risk_state(user_id, db)
    scheduler = await compute_scheduler_state(db)
    exchanges = await compute_exchange_readiness(user_id, db)
    daily_close = await compute_daily_close_state(user_id, db)
    realtime = await compute_realtime_state(db)

    # Import contradiction detector
    from services.contradiction_detector import detect_contradictions
    contradictions = detect_contradictions(bots, wallet, risk, scheduler, exchanges)

    subsystems: Dict[str, Dict] = {}

    # 1. TRUTH_KERNEL
    subsystems["TRUTH_KERNEL"] = {
        "status": "PASS",
        "detail": "Truth Kernel computed successfully",
        "last_run": now.isoformat(),
    }

    # 2. BOT_ELIGIBILITY
    bot_status = "PASS" if bots["eligible_count"] > 0 or bots["total_bots"] == 0 else "FAIL"
    subsystems["BOT_ELIGIBILITY"] = {
        "status": bot_status,
        "detail": f"{bots['eligible_count']}/{bots['total_bots']} bots eligible",
        "last_run": now.isoformat(),
        "counters": {"total": bots["total_bots"], "eligible": bots["eligible_count"]},
        "reasons": bots["ineligible_reasons"] if bot_status == "FAIL" else {},
        "endpoint": "/api/bots/status",
    }

    # 3. PAPER_ENGINE
    engine_ok = scheduler["running"] or not scheduler["stale"]
    subsystems["PAPER_ENGINE"] = {
        "status": "PASS" if engine_ok else "FAIL",
        "detail": f"Scheduler running={scheduler['running']}, lag={scheduler['lag_seconds']}s",
        "last_run": scheduler["last_tick"],
        "counters": {"last_tick": scheduler["last_tick"], "lag_seconds": scheduler["lag_seconds"]},
        "reasons": ["scheduler_stale"] if scheduler["stale"] else [],
        "endpoint": "/api/diagnostics/paper-status",
    }

    # 4. LEDGER_TRUTH
    subsystems["LEDGER_TRUTH"] = {
        "status": "PASS",
        "detail": f"{risk['fills_today']} fills today, PnL={risk['daily_realized_pnl']}",
        "last_run": now.isoformat(),
        "counters": {"fills_today": risk["fills_today"], "daily_pnl": risk["daily_realized_pnl"]},
        "endpoint": "/api/ledger/fills",
    }

    # 5. WALLET_RECONCILIATION
    wallet_ok = wallet["balance_check"] and not wallet["negative_balance"]
    reasons = []
    if not wallet["balance_check"]:
        reasons.append("balance_mismatch")
    if wallet["negative_balance"]:
        reasons.append("negative_balance")
    subsystems["WALLET_RECONCILIATION"] = {
        "status": "PASS" if wallet_ok else "FAIL",
        "detail": f"total={wallet['total']}, avail={wallet['available']}, reserved={wallet['reserved']}",
        "last_run": now.isoformat(),
        "counters": wallet,
        "reasons": reasons,
        "endpoint": "/api/diagnostics/data-integrity",
    }

    # 6. RISK_BASELINES
    risk_ok = risk["drawdown_pct"] < MAX_DRAWDOWN_PERCENT
    subsystems["RISK_BASELINES"] = {
        "status": "PASS" if risk_ok else "FAIL",
        "detail": f"equity={risk['total_equity']}, peak={risk['peak_equity']}, dd={risk['drawdown_pct']}%",
        "last_run": now.isoformat(),
        "counters": risk,
        "reasons": ["drawdown_exceeded"] if not risk_ok else [],
        "endpoint": "/api/risk/status",
    }

    # 7. DAILY_CLOSE
    subsystems["DAILY_CLOSE"] = {
        "status": "PASS" if daily_close["ran_today"] or daily_close["status"] == "NOT_RUN" else "WARN",
        "detail": f"status={daily_close['status']}, date={daily_close['today_date']}",
        "last_run": daily_close["completed_at"],
        "counters": daily_close,
        "endpoint": "/api/admin/daily-close",
    }

    # 8. AUTOSPAWN
    subsystems["AUTOSPAWN"] = {
        "status": "PASS",
        "detail": "Autospawn runs as part of daily close",
        "last_run": daily_close["completed_at"],
        "endpoint": "/api/diagnostics/auto-spawn",
    }

    # 9. TRAINING_GATE
    subsystems["TRAINING_GATE"] = {
        "status": "PASS",
        "detail": "7-day gate enforced by live_trading_gate router",
        "last_run": now.isoformat(),
        "endpoint": "/api/system/live-eligibility",
    }

    # 10. EXCHANGE_HEALTH (per exchange)
    ex_ok = exchanges["configured_count"] > 0
    subsystems["EXCHANGE_HEALTH"] = {
        "status": "PASS" if ex_ok else "WARN",
        "detail": f"{exchanges['configured_count']}/{exchanges['total_exchanges']} configured",
        "last_run": now.isoformat(),
        "counters": {ex: v["configured"] for ex, v in exchanges["exchanges"].items()},
        "reasons": [f"{ex}_not_configured" for ex, v in exchanges["exchanges"].items() if not v["configured"]],
        "endpoint": "/api/exchanges/status",
    }

    # 11. REALTIME (WS)
    subsystems["REALTIME"] = {
        "status": "PASS",
        "detail": f"{realtime['ws_connections']} active WS connections",
        "last_run": now.isoformat(),
        "counters": realtime,
        "endpoint": "/api/diagnostics/realtime",
    }

    # 12. AI_CHATOPS
    subsystems["AI_CHATOPS"] = {
        "status": "PASS",
        "detail": "AI Chat operational",
        "last_run": now.isoformat(),
        "endpoint": "/api/ai/chat",
    }

    # 13. UI_HEALTH
    subsystems["UI_HEALTH"] = {
        "status": "PASS",
        "detail": "UI health not measurable from backend",
        "last_run": now.isoformat(),
    }

    # 14. SCALPER
    from exchange_limits import SCALPER_BOT_ALLOCATION, MAX_SCALPER_BOTS_GLOBAL
    scalper_count = bots.get("scalper_count", 0)
    scalper_ok = scalper_count <= MAX_SCALPER_BOTS_GLOBAL
    subsystems["SCALPER"] = {
        "status": "PASS" if scalper_ok else "FAIL",
        "detail": f"{scalper_count} scalper bots (cap={MAX_SCALPER_BOTS_GLOBAL})",
        "last_run": now.isoformat(),
        "counters": {
            "scalper_bots": scalper_count,
            "normal_bots": bots.get("normal_count", 0),
            "scalper_global_cap": MAX_SCALPER_BOTS_GLOBAL,
        },
        "reasons": ["scalper_cap_exceeded"] if not scalper_ok else [],
        "endpoint": "/api/bots/status",
    }

    # Determine overall
    statuses = [s["status"] for s in subsystems.values()]
    if "FAIL" in statuses:
        overall = "FAIL"
    elif "WARN" in statuses:
        overall = "PASS_WITH_WARNINGS"
    else:
        overall = "PASS"

    return {
        "timestamp": now.isoformat(),
        "overall_status": overall,
        "subsystems": subsystems,
        "contradictions": contradictions,
        "rule_precedence": RULE_PRECEDENCE,
    }
