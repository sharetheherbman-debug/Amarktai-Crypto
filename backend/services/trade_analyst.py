"""
Post-trade analyst — generates a short lesson when a trade closes.
"""
import logging
from datetime import datetime, timezone
from typing import Optional

logger = logging.getLogger(__name__)


def generate_lesson(trade: dict) -> str:
    """Generate a simple lesson from a closed trade."""
    pnl = trade.get("pnl") or trade.get("profit_loss") or trade.get("pl") or 0
    symbol = trade.get("symbol") or trade.get("pair", "UNKNOWN")
    side = trade.get("side", "BUY").upper()
    win = float(pnl) >= 0 if pnl is not None else False

    if win:
        return (
            f"{'Long' if side == 'BUY' else 'Short'} on {symbol} closed with gain. "
            f"Entry timing aligned with market trend. Keep following the signal."
        )
    else:
        return (
            f"{'Long' if side == 'BUY' else 'Short'} on {symbol} closed at a loss. "
            f"Market moved against position. Review entry conditions before next trade."
        )


async def record_trade_lesson(user_id: str, bot_id: str, trade: dict):
    """Store lesson and emit an event for the closed trade."""
    try:
        import database as db
        from routes.events import emit_event

        lesson = generate_lesson(trade)
        pnl = trade.get("pnl") or trade.get("profit_loss") or trade.get("pl") or 0
        pnl_str = f"+R{abs(float(pnl)):.2f}" if float(pnl) >= 0 else f"-R{abs(float(pnl)):.2f}"

        # Store lesson in bot's lessons array
        if db.db is not None:
            await db.db.bot_lessons.update_one(
                {"bot_id": bot_id, "user_id": user_id},
                {"$push": {"lessons": {"$each": [{"lesson": lesson, "pnl": pnl, "ts": datetime.now(timezone.utc).isoformat(), "trade_id": str(trade.get("_id", ""))}], "$slice": -10}}},
                upsert=True,
            )

        # Emit event
        message = f"Closed trade {pnl_str} — Lesson: {lesson}"
        await emit_event(user_id, "trade_closed", "info" if float(pnl) >= 0 else "warning", message, meta={"bot_id": bot_id, "pnl": float(pnl)})
    except Exception as e:
        logger.debug(f"Could not record trade lesson: {e}")
