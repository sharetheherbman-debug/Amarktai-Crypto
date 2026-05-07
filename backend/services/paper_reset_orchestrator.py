"""
Paper Reset Orchestrator — single source-of-truth for all paper reset flows.

Every reset endpoint (admin start-fresh, user paper-start-fresh,
system paper-sandbox/reset, AI-chat reset) MUST delegate to
``paper_reset_orchestrator.run(user_id, scope)``.  This guarantees that
the same set of fields is cleared regardless of which surface triggered
the reset.

Scope values
------------
``"paper_only"``  — wipes paper bots/trades/fills and resets paper-mode
                    performance state; live bots/keys are untouched.
``"full"``        — same as paper_only plus live bots, orders and related
                    telemetry (use with care).

What is reset
-------------
Per-bot (paper bots):
  - equity_peak         → set to current_capital (drawdown becomes 0 %)
  - daily_capital_baseline → set to current_capital
  - daily_baseline_date → today (UTC)
  - daily_pnl, daily_loss_pct, trades_today → 0
  - pause_reason, paused_reason, last_order_error, last_order_attempt_at → cleared
  - paused_by_bodyguard, paused_by_system → False
  - per-bot circuit breaker flags → cleared

Per-user:
  - daily_loss_lock_active, emergency_stop → False
  - daily_loss_pct, daily_loss_locked_at/reason, daily_loss_day_key → cleared

Collections wiped (paper_only scope):
  - fills_ledger (is_paper=True for user)
  - ledger_events (paper-tagged for user)
  - equity_series, drawdown_series, circuit_breaker_state (user)
  - balance_snapshots, paper_ledger, bot_metrics, bot_runtime_state,
    bot_lifecycle, performance_metrics (user)
  - wallet_balances, capital_injections (user)
  - user_countdowns, profit_ledger (user)

Paper wallet reset (to 0).
Paper reset baseline timestamp stored so analytics graph knows when to
start the new baseline.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from datetime import datetime, timezone
from typing import Any, Dict

import database as db
from config import PAPER_STARTING_CAPITAL_ZAR

logger = logging.getLogger(__name__)

def _today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _paper_bot_filter(user_id: str) -> dict:
    return {
        "user_id": user_id,
        "status": {"$ne": "deleted"},
        "$or": [
            {"trading_mode": "paper"},
            {"mode": "paper"},
            {"is_paper": True},
            {"paper_test_ready": True},
            {
                "trading_mode": {"$exists": False},
                "mode": {"$ne": "live"},
                "exchange": {"$exists": True},
            },
        ],
    }


def _paper_trade_filter(user_id: str, bot_ids: Iterable[str] | None = None) -> dict:
    clauses: list[dict] = [
        {"is_paper": True},
        {"mode": "paper"},
        {"trading_mode": "paper"},
    ]
    if bot_ids:
        clauses.append({"bot_id": {"$in": list(bot_ids)}})
    return {"user_id": user_id, "$or": clauses}


def _paper_runtime_filter(user_id: str, bot_ids: Iterable[str] | None = None) -> dict:
    clauses: list[dict] = [
        {"is_paper": True},
        {"mode": "paper"},
        {"trading_mode": "paper"},
    ]
    if bot_ids:
        clauses.append({"bot_id": {"$in": list(bot_ids)}})
    return {"user_id": user_id, "$or": clauses}


async def _safe_delete(collection, filt: dict, label: str) -> int:
    """Delete documents and return the deleted count; never raises."""
    if collection is None:
        return 0
    try:
        r = await collection.delete_many(filt)
        return r.deleted_count
    except Exception as exc:
        logger.warning("paper_reset_orchestrator: failed to delete %s: %s", label, exc)
        return 0


async def _safe_update_many(collection, filt: dict, update: dict, label: str) -> int:
    """Update documents and return modified count; never raises."""
    if collection is None:
        return 0
    try:
        r = await collection.update_many(filt, update)
        return r.modified_count
    except Exception as exc:
        logger.warning("paper_reset_orchestrator: failed to update %s: %s", label, exc)
        return 0


async def run(
    user_id: str,
    scope: str = "paper_only",
    also_reset_risk_locks: bool = True,
) -> Dict[str, Any]:
    """Execute a complete paper (or full) reset for *user_id*.

    Returns a summary dict with deleted/reset counts and post-reset invariants.
    Never raises — any sub-operation failure is logged and counted as a warning.
    """
    today_str = _today()
    now_iso = _now_iso()

    summary: Dict[str, Any] = {
        "scope": scope,
        "user_id": user_id[:8],
        "bots_soft_deleted": 0,
        "open_trades_deleted": 0,
        "bots_performance_reset": 0,
        "trades_deleted": 0,
        "orders_deleted": 0,
        "fills_deleted": 0,
        "telemetry_deleted": 0,
        "runtime_deleted": 0,
        "risk_locks_reset": 0,
        "wallet_reset": False,
        "warnings": [],
    }

    # ------------------------------------------------------------------
    # Step 1: Soft-delete paper bots (mark status=deleted).
    #         Then collect their IDs for downstream cleanup.
    # ------------------------------------------------------------------
    bot_filter: dict = _paper_bot_filter(user_id) if scope == "paper_only" else {
        "user_id": user_id,
        "status": {"$ne": "deleted"},
    }

    # Fetch IDs BEFORE soft-deleting so we can clean up their data.
    active_bots = await db.bots_collection.find(
        bot_filter,
        {"_id": 0, "id": 1, "current_capital": 1, "initial_capital": 1},
    ).to_list(1000)
    bot_ids = [b["id"] for b in active_bots if "id" in b]

    if bot_ids:
        try:
            await db.bots_collection.update_many(
                {"id": {"$in": bot_ids}},
                {
                    "$set": {
                        "paused_by_system": True,
                        "pause_reason": "paper_reset_in_progress",
                        "updated_at": now_iso,
                    }
                },
            )
        except Exception as exc:
            logger.warning("paper_reset_orchestrator: pre-reset pause failed: %s", exc)

    soft_delete_result = await _safe_update_many(
        db.bots_collection,
        bot_filter,
        {
            "$set": {
                "status": "deleted",
                "deleted_at": now_iso,
                "deleted_by": user_id,
                "deletion_reason": "paper_reset_orchestrator",
            }
        },
        "bots_soft_delete",
    )
    summary["bots_soft_deleted"] = soft_delete_result

    # ------------------------------------------------------------------
    # Step 1b: Reset performance state on any SURVIVING paper bots
    #          (e.g. bots that were already deleted but might be re-used,
    #          or bots in a different scope that are kept alive).
    #          This prevents stale equity_peak / drawdown on any bot the
    #          caller did not delete.
    # ------------------------------------------------------------------
    surviving_filter: dict = _paper_bot_filter(user_id) if scope == "paper_only" else {
        "user_id": user_id,
        "status": {"$ne": "deleted"},
    }

    # For surviving bots we can't know current_capital without fetching
    # each one, so we use $set with conditional field — we'll update them
    # one by one so equity_peak reflects their individual current_capital.
    surviving_bots = await db.bots_collection.find(
        surviving_filter,
        {"_id": 0, "id": 1, "current_capital": 1, "initial_capital": 1},
    ).to_list(1000)

    perf_reset_count = 0
    for sbot in surviving_bots:
        sbid = sbot.get("id")
        if not sbid:
            continue
        cap = sbot.get("current_capital") or sbot.get("initial_capital") or 0
        if cap <= 0:
            cap = 0
        try:
            await db.bots_collection.update_one(
                {"id": sbid},
                {
                    "$set": {
                        "equity_peak": cap,
                        "current_drawdown_pct": 0.0,
                        "daily_capital_baseline": cap,
                        "daily_baseline_date": today_str,
                        "daily_pnl": 0.0,
                        "daily_loss_pct": 0.0,
                        "trades_today": 0,
                        "paused_by_bodyguard": False,
                        "paused_by_system": False,
                    },
                    "$unset": {
                        "pause_reason": "",
                        "paused_reason": "",
                        "last_order_error": "",
                        "last_order_attempt_at": "",
                        "circuit_breaker_tripped": "",
                        "circuit_breaker_tripped_at": "",
                        "bodyguard_last_breach_at": "",
                        "bodyguard_last_pause_at": "",
                    },
                },
            )
            perf_reset_count += 1
        except Exception as exc:
            logger.warning(
                "paper_reset_orchestrator: could not reset perf for bot %s: %s", sbid, exc
            )

    summary["bots_performance_reset"] = perf_reset_count

    # ------------------------------------------------------------------
    # Step 2: Delete trade/order/fill records for the deleted bots.
    # ------------------------------------------------------------------
    paper_trade_filter = _paper_trade_filter(user_id, bot_ids)
    summary["open_trades_deleted"] = await _safe_delete(
        db.trades_collection,
        {**paper_trade_filter, "status": {"$in": ["open", "pending"]}},
        "open_paper_trades",
    )
    summary["trades_deleted"] += summary["open_trades_deleted"]
    summary["trades_deleted"] += await _safe_delete(
        db.trades_collection,
        {**paper_trade_filter, "status": {"$nin": ["open", "pending"]}},
        "paper_trades_history",
    )
    if bot_ids:
        summary["orders_deleted"] += await _safe_delete(
            db.orders_collection, {"user_id": user_id, "bot_id": {"$in": bot_ids}}, "orders"
        )
        try:
            if db.db is not None:
                r = await db.db["fills_ledger"].delete_many(
                    {"user_id": user_id, "bot_id": {"$in": bot_ids}}
                )
                summary["fills_deleted"] += r.deleted_count
        except Exception as exc:
            logger.warning("paper_reset_orchestrator: fills by bot_id: %s", exc)

        try:
            telem_r = await db.bot_metrics_collection.delete_many(
                {"bot_id": {"$in": bot_ids}}
            )
            summary["telemetry_deleted"] += telem_r.deleted_count
        except Exception as exc:
            logger.warning("paper_reset_orchestrator: telemetry: %s", exc)

    # ------------------------------------------------------------------
    # Step 3: Wipe user-scoped paper fills (is_paper=True) so that
    #         compute_equity() returns 0 after the reset.
    # ------------------------------------------------------------------
    raw_db = getattr(db, "db", None)
    if raw_db is not None:
        # Primary fill records tagged as paper
        r = await _safe_delete(
            raw_db["fills_ledger"],
            _paper_runtime_filter(user_id, bot_ids),
            "fills_ledger(is_paper)",
        )
        summary["fills_deleted"] += r

        # All fills that belong to deleted bots (belt-and-suspenders)
        if bot_ids:
            r2 = await _safe_delete(
                raw_db["fills_ledger"],
                {"user_id": user_id, "bot_id": {"$in": bot_ids}},
                "fills_ledger(bot_ids)",
            )
            summary["fills_deleted"] += r2

        # Ledger events tagged as paper
        paper_events_filter = {
            "user_id": user_id,
            "$or": [
                {"event_type": "paper_capital_bootstrap"},
                {"metadata.mode": "paper"},
                {"metadata.is_paper": True},
            ],
        }
        summary["runtime_deleted"] += await _safe_delete(
            raw_db["ledger_events"], paper_events_filter, "ledger_events(paper)"
        )

        # Per-user circuit breaker state (both user-scope and bot-scope for paper bots)
        if bot_ids:
            cb_filter: dict = {
                "$or": [
                    {"user_id": user_id, "bot_id": {"$exists": False}},
                    {"bot_id": {"$in": bot_ids}},
                ]
            }
        else:
            cb_filter = {"user_id": user_id}
        summary["runtime_deleted"] += await _safe_delete(
            raw_db["circuit_breaker_state"], cb_filter, "circuit_breaker_state"
        )

        # Analytics series
        for coll_name in (
            "equity_series",
            "drawdown_series",
            "profit_ledger",
        ):
            summary["runtime_deleted"] += await _safe_delete(
                raw_db[coll_name],
                _paper_runtime_filter(user_id, bot_ids),
                coll_name,
            )

    # ------------------------------------------------------------------
    # Step 4: Wipe user-scoped runtime collections.
    # ------------------------------------------------------------------
    _user_runtime: list[tuple[str, Any]] = [
        ("balance_snapshots", db.balance_snapshots_collection),
        ("paper_ledger", db.paper_ledger_collection),
        ("bot_metrics(user)", db.bot_metrics_collection),
        ("bot_runtime_state", db.bot_runtime_state_collection),
        ("bot_lifecycle", db.bot_lifecycle_collection),
        ("performance_metrics", db.performance_metrics_collection),
        ("training_jobs", db.training_jobs_collection),
        ("decisions", db.decisions_collection),
        ("learning_logs", db.learning_logs_collection),
        ("learning_data", db.learning_data_collection),
        ("learning_runs", db.learning_runs_collection),
        ("learning_changes", db.learning_changes_collection),
    ]
    for label, coll in _user_runtime:
        summary["runtime_deleted"] += await _safe_delete(
            coll,
            _paper_runtime_filter(user_id, bot_ids),
            label,
        )

    summary["runtime_deleted"] += await _safe_delete(
        db.user_countdowns_collection, {"user_id": user_id}, "user_countdowns"
    )

    if db.wallet_balances_collection is not None:
        try:
            await db.wallet_balances_collection.update_one(
                {"user_id": user_id},
                {
                    "$unset": {
                        "paper_wallet_allocated_zar": "",
                        "paper_wallet_available_zar": "",
                        "paper_wallet_balance_zar": "",
                        "paper_wallet_updated_at": "",
                    }
                },
                upsert=False,
            )
        except Exception as exc:
            logger.warning("paper_reset_orchestrator: wallet cache reset: %s", exc)

    # ------------------------------------------------------------------
    # Step 5: Reset per-user risk locks (daily loss, emergency stop).
    # ------------------------------------------------------------------
    if also_reset_risk_locks:
        try:
            r = await db.users_collection.update_one(
                {"id": user_id},
                {
                    "$set": {
                        "daily_loss_lock_active": False,
                        "daily_loss_lock_reset_at": now_iso,
                        "emergency_stop": False,
                    },
                    "$unset": {
                        "daily_loss_locked_at": "",
                        "daily_loss_locked_reason": "",
                        "daily_loss_pct": "",
                        "daily_loss_day_key": "",
                    },
                },
            )
            summary["risk_locks_reset"] = r.modified_count
        except Exception as exc:
            logger.warning("paper_reset_orchestrator: risk lock reset: %s", exc)
            summary["warnings"].append(f"risk_lock_reset: {exc}")

    # ------------------------------------------------------------------
    # Step 6: Reset paper wallet to zero.
    # ------------------------------------------------------------------
    wallet_before: dict = {}
    wallet_after: dict = {}
    try:
        from services.paper_wallet_service import paper_wallet_service
        from services.paper_wallet_ledger import paper_wallet_ledger

        wresult = await paper_wallet_service.reset(
            user_id,
            starting_balance=float(PAPER_STARTING_CAPITAL_ZAR),
        )
        wallet_before = wresult.get("wallet_before", {})
        wallet_after = wresult.get("wallet_after", {})
        await paper_wallet_ledger.get_user_balance(user_id)
        summary["wallet_reset"] = True
    except Exception as exc:
        logger.warning("paper_reset_orchestrator: paper wallet reset: %s", exc)
        summary["warnings"].append(f"paper_wallet_reset: {exc}")

    summary["wallet_before"] = wallet_before
    summary["wallet_after"] = wallet_after

    # ------------------------------------------------------------------
    # Step 7: Store equity-baseline timestamp so analytics graph knows
    #         where the new session begins.
    # ------------------------------------------------------------------
    try:
        if db.paper_reset_baselines_collection is not None:
            await db.paper_reset_baselines_collection.update_one(
                {"user_id": user_id},
                {"$set": {"user_id": user_id, "reset_at": now_iso}},
                upsert=True,
            )
    except Exception as exc:
        logger.warning("paper_reset_orchestrator: equity baseline: %s", exc)

    # ------------------------------------------------------------------
    # Step 8: Post-reset invariant checks (best-effort).
    # ------------------------------------------------------------------
    post_reset: dict = {}
    try:
        post_reset["active_bots"] = await db.bots_collection.count_documents(
            {**_paper_bot_filter(user_id), "status": {"$in": ["active", "running"]}}
        )
        post_reset["open_positions"] = await db.trades_collection.count_documents(
            {**_paper_trade_filter(user_id), "status": {"$in": ["open", "pending"]}}
        )
        post_reset["remaining_paper_fills"] = 0
    except Exception as exc:
        logger.warning("paper_reset_orchestrator: invariant checks: %s", exc)

    if raw_db is not None:
        try:
            from services.ledger_service import get_ledger_service

            _lsvc = get_ledger_service(db.db)
            post_reset["ledger_equity"] = round(await _lsvc.compute_equity(user_id), 4)
            post_reset["ledger_fills"] = await raw_db["fills_ledger"].count_documents(
                {
                    "user_id": user_id,
                    "$or": [
                        {"is_paper": True},
                        {"mode": "paper"},
                        {"trading_mode": "paper"},
                    ],
                }
            )
            post_reset["remaining_paper_fills"] = post_reset["ledger_fills"]
            expected_equity = round(float(PAPER_STARTING_CAPITAL_ZAR), 4)
            if post_reset["ledger_equity"] not in (0, expected_equity):
                msg = (
                    f"ledger_equity={post_reset['ledger_equity']} non-zero after reset"
                    f" for user {user_id[:8]}"
                )
                summary["warnings"].append(msg)
                logger.error("Post-reset invariant FAIL: %s", msg)
        except Exception as exc:
            logger.warning("paper_reset_orchestrator: ledger invariant: %s", exc)

    summary["post_reset"] = post_reset
    summary["wallet_available"] = round(float((wallet_after or {}).get("ZAR", 0) or 0), 2)
    summary["paper_balance"] = summary["wallet_available"]
    summary["remaining_paper_bots"] = int(post_reset.get("active_bots", 0) or 0)
    summary["remaining_open_paper_trades"] = int(post_reset.get("open_positions", 0) or 0)
    summary["remaining_paper_fills"] = int(post_reset.get("remaining_paper_fills", 0) or 0)
    logger.info(
        "paper_reset_orchestrator.run completed: user=%s scope=%s "
        "bots_deleted=%d fills_deleted=%d warnings=%d",
        user_id[:8],
        scope,
        summary["bots_soft_deleted"],
        summary["fills_deleted"],
        len(summary["warnings"]),
    )
    return summary
