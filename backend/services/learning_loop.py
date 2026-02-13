"""
Nightly Learning Loop Scheduler (guarded by ENABLE_LEARNING_LOOP).
Performs bounded parameter reweighting and stores audit data.
"""

import asyncio
import logging
import os
from datetime import datetime, timezone, timedelta, time
from typing import Dict, List, Optional
from uuid import uuid4

import database as db

logger = logging.getLogger(__name__)


class LearningLoop:
    def __init__(self):
        self.is_running = False
        self.last_run = None
        self._task: Optional[asyncio.Task] = None

    async def start(self):
        if self._task:
            return
        self.is_running = True
        self._task = asyncio.create_task(self._schedule_loop())
        logger.info("📚 Learning loop scheduler started")

    def stop(self):
        self.is_running = False
        if self._task:
            self._task.cancel()
            self._task = None
        logger.info("📚 Learning loop scheduler stopped")

    async def _schedule_loop(self):
        while self.is_running:
            now = datetime.now(timezone.utc)
            target_time = time(1, 30)  # 01:30 UTC by default
            target_datetime = datetime.combine(now.date(), target_time).replace(tzinfo=timezone.utc)
            if now.time() >= target_time:
                target_datetime = target_datetime + timedelta(days=1)
            sleep_seconds = (target_datetime - now).total_seconds()
            logger.info("📚 Next learning loop in %.1f hours", sleep_seconds / 3600)
            await asyncio.sleep(sleep_seconds)
            await self.run_nightly_learning()

    async def run_nightly_learning(self, dry_run: bool = False):
        if not os.getenv("ENABLE_LEARNING_LOOP", "false").lower() == "true":
            logger.info("📚 Learning loop disabled (ENABLE_LEARNING_LOOP=false)")
            return
        try:
            from services.autonomy_state import autonomy_state
            if autonomy_state.is_paused("learning_loop"):
                logger.info("📚 Learning loop paused by autonomy controls")
                return
        except Exception:
            pass

        try:
            users = await db.users_collection.find({}, {"_id": 0, "id": 1}).to_list(2000)
            for user in users:
                await self._run_for_user(user.get("id"), dry_run=dry_run)
            self.last_run = datetime.now(timezone.utc)
            logger.info("📚 Learning loop complete")
            try:
                from services.autonomy_heartbeat import heartbeat_registry
                heartbeat_registry.mark_ok("learning_loop")
            except Exception:
                pass
        except Exception as e:
            logger.error(f"Learning loop error: {e}")
            try:
                from services.autonomy_heartbeat import heartbeat_registry
                heartbeat_registry.mark_error("learning_loop", str(e))
            except Exception:
                pass

    async def _run_for_user(self, user_id: str, dry_run: bool = False):
        if not user_id:
            return

        window_end = datetime.now(timezone.utc)
        run_id = str(uuid4())
        trade_limit = max(int(os.getenv("LEARNING_TRADE_LIMIT", "200")), 50)

        trades = await db.trades_collection.find(
            {"user_id": user_id, "status": "closed"},
            {"_id": 0, "profit_loss": 1, "net_pnl": 1, "gross_pnl": 1, "fees_total": 1, "slippage_cost": 1, "timestamp": 1}
        ).sort("timestamp", -1).limit(trade_limit).to_list(trade_limit)

        window_start = window_end - timedelta(days=1)
        if trades:
            try:
                window_start = datetime.fromisoformat(str(trades[-1].get("timestamp")).replace("Z", "+00:00"))
            except Exception:
                window_start = window_end - timedelta(days=1)

        total_trades = len(trades)
        wins = [t.get("net_pnl", t.get("profit_loss", 0)) for t in trades if t.get("net_pnl", t.get("profit_loss", 0)) > 0]
        losses = [t.get("net_pnl", t.get("profit_loss", 0)) for t in trades if t.get("net_pnl", t.get("profit_loss", 0)) < 0]
        net_pnl = sum(t.get("net_pnl", t.get("profit_loss", 0)) for t in trades)
        win_rate = (len(wins) / total_trades * 100) if total_trades else 0.0
        avg_win = sum(wins) / len(wins) if wins else 0.0
        avg_loss = sum(losses) / len(losses) if losses else 0.0
        profit_factor = (sum(wins) / abs(sum(losses))) if losses else float("inf")
        fees_total = sum(t.get("fees_total", 0) for t in trades)
        slippage_total = sum(t.get("slippage_cost", 0) for t in trades)
        drawdown_current = None
        drawdown_max = None
        try:
            from services.ledger_service import get_ledger_service
            ledger = get_ledger_service(db.db)
            current_dd, max_dd = await ledger.compute_drawdown(user_id)
            drawdown_current = round(current_dd * 100, 2)
            drawdown_max = round(max_dd * 100, 2)
        except Exception:
            pass

        metrics_doc = {
            "run_id": run_id,
            "user_id": user_id,
            "window_start": window_start.isoformat(),
            "window_end": window_end.isoformat(),
            "total_trades": total_trades,
            "wins": len(wins),
            "losses": len(losses),
            "net_pnl": round(net_pnl, 2),
            "win_rate": round(win_rate, 2),
            "avg_win": round(avg_win, 2),
            "avg_loss": round(avg_loss, 2),
            "profit_factor": round(profit_factor, 2) if profit_factor != float("inf") else None,
            "fees_total": round(fees_total, 2),
            "slippage_total": round(slippage_total, 2),
            "drawdown_current": drawdown_current,
            "drawdown_max": drawdown_max,
            "timestamp": window_end.isoformat()
        }

        await db.learning_metrics_collection.insert_one(metrics_doc)

        min_trades_required = max(int(os.getenv("LEARNING_MIN_TRADES", "50")), 50)
        if total_trades < min_trades_required:
            run_doc = {
                "run_id": run_id,
                "user_id": user_id,
                "started_at": window_start.isoformat(),
                "completed_at": window_end.isoformat(),
                "status": "insufficient_data",
                "trades_analyzed": total_trades,
                "changes_applied": 0,
                "rolled_back": False,
                "summary": f"Insufficient trades ({total_trades}/{min_trades_required}) for learning updates.",
                "metrics": metrics_doc,
                "dry_run": dry_run
            }
            await db.learning_runs_collection.insert_one(run_doc)
            return

        config_doc = await db.system_config_collection.find_one({"user_id": user_id}, {"_id": 0})
        learning_params = (config_doc or {}).get("learning_params", {})
        current_strategy_version_id = (config_doc or {}).get("strategy_version_id")

        trade_size = float(learning_params.get("trade_size_multiplier", 1.0))
        cooldown = float(learning_params.get("cooldown_multiplier", 1.0))
        stop_loss = float(learning_params.get("stop_loss_pct", 0.02))
        previous_params = {
            "trade_size_multiplier": trade_size,
            "cooldown_multiplier": cooldown,
            "stop_loss_pct": stop_loss
        }

        max_risk = float(os.getenv("LEARNING_MAX_RISK_MULTIPLIER", "1.1"))
        min_risk = float(os.getenv("LEARNING_MIN_RISK_MULTIPLIER", "0.8"))
        max_change_pct = float(os.getenv("LEARNING_MAX_CHANGE_PCT", "0.10"))

        changes: List[Dict] = []

        def clamp(value: float, min_value: float, max_value: float) -> float:
            return max(min_value, min(value, max_value))

        if total_trades >= 5:
            if win_rate < 50 or net_pnl < 0 or profit_factor < 1:
                new_trade_size = clamp(trade_size * (1 - max_change_pct), min_risk, max_risk)
                if new_trade_size != trade_size:
                    changes.append({
                        "parameter": "trade_size_multiplier",
                        "old": trade_size,
                        "new": new_trade_size,
                        "reason": "Recent performance below target",
                        "expected_impact": "Reduce exposure to stabilize results"
                    })
                    trade_size = new_trade_size

                new_cooldown = clamp(cooldown * (1 + max_change_pct), 0.8, 1.5)
                if new_cooldown != cooldown:
                    changes.append({
                        "parameter": "cooldown_multiplier",
                        "old": cooldown,
                        "new": new_cooldown,
                        "reason": "Slow down trade cadence after losses",
                        "expected_impact": "Fewer low-quality entries"
                    })
                    cooldown = new_cooldown

                new_stop = clamp(stop_loss * (1 + max_change_pct), 0.01, 0.05)
                if new_stop != stop_loss:
                    changes.append({
                        "parameter": "stop_loss_pct",
                        "old": stop_loss,
                        "new": new_stop,
                        "reason": "Tighter risk control after drawdown",
                        "expected_impact": "Cap downside per trade"
                    })
                    stop_loss = new_stop
            elif win_rate > 55 and net_pnl > 0 and profit_factor > 1.1:
                new_trade_size = clamp(trade_size * (1 + max_change_pct), min_risk, max_risk)
                if new_trade_size != trade_size:
                    changes.append({
                        "parameter": "trade_size_multiplier",
                        "old": trade_size,
                        "new": new_trade_size,
                        "reason": "Strong recent performance",
                        "expected_impact": "Slightly increase position sizing"
                    })
                    trade_size = new_trade_size

        last_run = await db.learning_runs_collection.find_one(
            {"user_id": user_id},
            {"_id": 0, "metrics": 1, "applied_params": 1, "strategy_version_id": 1},
            sort=[("completed_at", -1)]
        )
        last_net_pnl = last_run.get("metrics", {}).get("net_pnl") if last_run else None
        last_strategy_version = last_run.get("strategy_version_id") if last_run else None
        try:
            rollback_threshold = float(os.getenv("LEARNING_ROLLBACK_THRESHOLD", "0.9"))
        except ValueError:
            rollback_threshold = 0.9
        rollback = last_net_pnl is not None and net_pnl < last_net_pnl * rollback_threshold

        improvement_ok = net_pnl >= 0 and win_rate >= 50 and (profit_factor >= 1.05 or profit_factor == float("inf"))
        if last_net_pnl is not None:
            improvement_ok = improvement_ok and net_pnl >= last_net_pnl * 1.01

        sanity_check = {
            "net_pnl": round(net_pnl, 2),
            "win_rate": round(win_rate, 2),
            "profit_factor": round(profit_factor, 2) if profit_factor != float("inf") else None,
            "passes": improvement_ok
        }

        summary_lines = []
        if changes:
            summary_lines.append(f"Adjusted {len(changes)} parameters after {total_trades} trades.")
        else:
            summary_lines.append("No parameter changes required today.")
        if rollback:
            summary_lines.append("Rollback triggered due to degraded performance.")
        if total_trades < 5:
            summary_lines.append("Insufficient trades for major adjustments.")

        applied_params = {
            "trade_size_multiplier": trade_size,
            "cooldown_multiplier": cooldown,
            "stop_loss_pct": stop_loss
        }

        if rollback:
            if not dry_run:
                await db.system_config_collection.update_one(
                    {"user_id": user_id},
                    {"$set": {
                        "learning_params": previous_params,
                        "strategy_version_id": last_strategy_version or current_strategy_version_id
                    }},
                    upsert=True
                )
            applied_params = previous_params
        elif changes and improvement_ok and not dry_run:
            await db.system_config_collection.update_one(
                {"user_id": user_id},
                {"$set": {
                    "learning_params": {
                        "trade_size_multiplier": trade_size,
                        "cooldown_multiplier": cooldown,
                        "stop_loss_pct": stop_loss,
                        "updated_at": window_end.isoformat()
                    }
                }},
                upsert=True
            )
        elif changes and not improvement_ok:
            summary_lines.append("Sanity check failed; skipped parameter updates.")

        for change in changes:
            await db.learning_changes_collection.insert_one({
                "run_id": run_id,
                "user_id": user_id,
                "parameter": change["parameter"],
                "old_value": change["old"],
                "new_value": change["new"],
                "delta": round(change["new"] - change["old"], 4),
                "reason": change["reason"],
                "expected_impact": change["expected_impact"],
                "timestamp": window_end.isoformat()
            })

        strategy_version_id = current_strategy_version_id
        previous_version_id = current_strategy_version_id or last_strategy_version
        if not rollback and changes and improvement_ok and not dry_run and db.strategy_versions_collection is not None:
            strategy_version_id = str(uuid4())
            await db.strategy_versions_collection.insert_one({
                "version_id": strategy_version_id,
                "user_id": user_id,
                "created_at": window_end.isoformat(),
                "params_json": applied_params,
                "created_by": "learning_loop",
                "reason": "nightly_learning_update",
                "metrics": metrics_doc
            })
            await db.system_config_collection.update_one(
                {"user_id": user_id},
                {"$set": {"strategy_version_id": strategy_version_id}},
                upsert=True
            )

        if rollback and previous_version_id:
            strategy_version_id = previous_version_id

        if strategy_version_id and not dry_run and db.bot_strategy_assignments_collection is not None:
            bots = await db.bots_collection.find({"user_id": user_id, "status": {"$ne": "deleted"}}, {"_id": 0, "id": 1}).to_list(1000)
            for bot in bots:
                await db.bot_strategy_assignments_collection.insert_one({
                    "bot_id": bot.get("id"),
                    "user_id": user_id,
                    "strategy_version_id": strategy_version_id,
                    "assigned_at": window_end.isoformat()
                })
            await db.bots_collection.update_many(
                {"user_id": user_id, "status": {"$ne": "deleted"}},
                {"$set": {"strategy_version_id": strategy_version_id}}
            )

        report_letter = (
            "Learning summary:\n"
            f"- Trades analyzed: {total_trades}\n"
            f"- Win rate: {win_rate:.1f}%\n"
            f"- Net PnL: R{net_pnl:.2f}\n"
        )
        if changes:
            report_letter += f"- Changes: {len(changes)} parameter adjustments\n"
        if rollback:
            report_letter += "- Rollback applied due to performance drop\n"

        run_doc = {
            "run_id": run_id,
            "user_id": user_id,
            "started_at": window_start.isoformat(),
            "completed_at": window_end.isoformat(),
            "status": "rolled_back" if rollback else "applied" if changes and improvement_ok and not dry_run else "skipped",
            "trades_analyzed": total_trades,
            "changes_applied": len(changes) if changes and improvement_ok else 0,
            "rolled_back": rollback,
            "summary": " ".join(summary_lines),
            "metrics": metrics_doc,
            "previous_params": previous_params,
            "applied_params": applied_params,
            "strategy_version_id": strategy_version_id,
            "previous_strategy_version_id": previous_version_id,
            "sanity_check": sanity_check,
            "report": {
                "letter": report_letter,
                "changes": changes,
                "metrics": metrics_doc
            },
            "dry_run": dry_run
        }
        await db.learning_runs_collection.insert_one(run_doc)

        if db.action_audit_log_collection is not None:
            try:
                await db.action_audit_log_collection.insert_one({
                    "user_id": user_id,
                    "actor": "learning_loop",
                    "action": "learning_run_completed",
                    "payload": {
                        "run_id": run_id,
                        "strategy_version_id": strategy_version_id,
                        "rolled_back": rollback,
                        "dry_run": dry_run
                    },
                    "result": run_doc,
                    "timestamp": window_end.isoformat()
                })
            except Exception:
                pass

        try:
            from realtime_events import rt_events
            await rt_events.learning_run_completed(user_id, {
                "run_id": run_id,
                "status": run_doc.get("status"),
                "summary": run_doc.get("summary"),
                "strategy_version_id": strategy_version_id
            })
        except Exception:
            pass


learning_loop = LearningLoop()
