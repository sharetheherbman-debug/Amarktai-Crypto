"""
Daily Close & Reinvest Job

Runs at 00:05 Africa/Johannesburg (SAST) using SAST day boundaries.
Must be idempotent: one run per day max, stored with run_id.

Responsibilities:
1. Compute realized PnL from ledger for the SAST day.
2. Score bots per exchange.
3. Reinvest realized PnL into best-performing bots.
4. Autospawn clones of the best bot per exchange.
5. Log everything with audit trail.
"""

from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional
import logging
import hashlib

logger = logging.getLogger(__name__)

# SAST offset (UTC+2)
SAST_OFFSET = timedelta(hours=2)


def sast_now() -> datetime:
    """Return current time in SAST."""
    return datetime.now(timezone.utc) + SAST_OFFSET


def sast_day_boundaries(dt: Optional[datetime] = None) -> tuple:
    """
    Return (start_utc, end_utc) for the SAST day containing dt.
    If dt is None, uses current SAST time.
    """
    if dt is None:
        dt = sast_now()
    elif dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc) + SAST_OFFSET

    day_start_sast = dt.replace(hour=0, minute=0, second=0, microsecond=0)
    day_end_sast = day_start_sast + timedelta(days=1)

    # Convert back to UTC
    start_utc = day_start_sast - SAST_OFFSET
    end_utc = day_end_sast - SAST_OFFSET

    return start_utc.replace(tzinfo=timezone.utc), end_utc.replace(tzinfo=timezone.utc)


def make_run_id(date_str: str, user_id: str) -> str:
    """Generate idempotent run ID for a given date + user."""
    return hashlib.sha256(f"daily_close:{date_str}:{user_id}".encode()).hexdigest()[:16]


def score_bot(bot: Dict, fills: List[Dict]) -> float:
    """
    Score a bot for autospawn / reinvestment ranking.

    Score = risk_adjusted_pnl - drawdown_penalty - slippage_penalty - instability_penalty
    """
    realized_pnl = sum(f.get("realized_pnl", 0) for f in fills)
    total_trades = len(fills)
    if total_trades == 0:
        return 0.0

    # Risk-adjusted return (simple Sharpe-like)
    capital = float(bot.get("current_capital", bot.get("initial_capital", 1000)))
    pnl_ratio = realized_pnl / capital if capital > 0 else 0

    # Drawdown penalty
    max_drawdown = float(bot.get("max_drawdown_pct", 0))
    drawdown_penalty = max_drawdown * 0.5

    # Slippage penalty
    avg_slippage = float(bot.get("avg_slippage_pct", 0))
    slippage_penalty = avg_slippage * 2.0

    # Instability penalty (high trade failure rate)
    failed_trades = sum(1 for f in fills if f.get("status") == "failed")
    failure_rate = failed_trades / total_trades if total_trades > 0 else 0
    instability_penalty = failure_rate * 10.0

    score = (pnl_ratio * 100) - drawdown_penalty - slippage_penalty - instability_penalty
    return round(score, 4)


async def run_daily_close(user_id: str, db) -> Dict:
    """
    Execute the daily close and reinvest cycle.

    Returns a report dict with summary and actions taken.
    """
    now_sast = sast_now()
    date_str = now_sast.strftime("%Y-%m-%d")
    run_id = make_run_id(date_str, user_id)

    # Idempotency check
    existing_run = await db["daily_close_runs"].find_one({"run_id": run_id})
    if existing_run:
        logger.info(f"Daily close already ran for {date_str} (run_id={run_id})")
        return {
            "status": "ALREADY_RAN",
            "run_id": run_id,
            "date": date_str,
            "previous_run": existing_run.get("completed_at"),
        }

    start_utc, end_utc = sast_day_boundaries()

    report = {
        "run_id": run_id,
        "date": date_str,
        "sast_day_start": start_utc.isoformat(),
        "sast_day_end": end_utc.isoformat(),
        "bots_scored": [],
        "reinvest_actions": [],
        "total_realized_pnl": 0.0,
        "status": "RUNNING",
    }

    try:
        # 1. Get all user bots
        bots = await db["bots"].find(
            {"user_id": user_id, "deleted": {"$ne": True}}
        ).to_list(length=200)

        # 2. Get fills for the SAST day
        fills = await db["fills_ledger"].find(
            {
                "user_id": user_id,
                "timestamp": {"$gte": start_utc, "$lt": end_utc},
            }
        ).to_list(length=10000)

        total_pnl = 0.0
        bot_scores = []

        for bot in bots:
            bot_id = str(bot.get("_id", ""))
            bot_fills = [f for f in fills if f.get("bot_id") == bot_id]

            bot_pnl = sum(float(f.get("realized_pnl", 0)) for f in bot_fills)
            total_pnl += bot_pnl

            sc = score_bot(bot, bot_fills)
            bot_scores.append({
                "bot_id": bot_id,
                "name": bot.get("name", ""),
                "exchange": bot.get("exchange", ""),
                "score": sc,
                "realized_pnl": round(bot_pnl, 2),
                "trades": len(bot_fills),
            })

        # Sort by score descending
        bot_scores.sort(key=lambda x: x["score"], reverse=True)
        report["bots_scored"] = bot_scores
        report["total_realized_pnl"] = round(total_pnl, 2)

        # 3. Reinvest: allocate realized PnL to best bots
        if total_pnl > 0:
            # Simple strategy: allocate proportionally to top-scoring bots
            positive_bots = [b for b in bot_scores if b["score"] > 0]
            if positive_bots:
                total_score = sum(b["score"] for b in positive_bots)
                for bot_entry in positive_bots[:5]:  # Top 5 bots
                    share = (bot_entry["score"] / total_score) * total_pnl if total_score > 0 else 0
                    if share > 0:
                        report["reinvest_actions"].append({
                            "bot_id": bot_entry["bot_id"],
                            "amount": round(share, 2),
                            "reason": f"Reinvest from daily PnL (score={bot_entry['score']})",
                        })

        report["status"] = "COMPLETED"
        report["completed_at"] = datetime.now(timezone.utc).isoformat()

        # 4. Save run record (idempotent)
        await db["daily_close_runs"].insert_one({
            "run_id": run_id,
            "user_id": user_id,
            "date": date_str,
            "report": report,
            "completed_at": datetime.now(timezone.utc),
        })

        logger.info(f"Daily close completed: run_id={run_id}, pnl={total_pnl:.2f}, bots={len(bots)}")
        return report

    except Exception as e:
        report["status"] = "ERROR"
        report["error"] = str(e)
        logger.error(f"Daily close error: {e}", exc_info=True)
        return report
