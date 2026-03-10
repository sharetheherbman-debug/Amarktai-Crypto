import asyncio
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from risk_engine import RiskEngine


def test_fixed_fractional_max_notional_from_stop_distance():
    engine = RiskEngine()
    bot = {"stop_loss_pct": 0.01}

    tight = engine._calculate_max_notional_for_risk(
        bot=bot,
        bot_capital=1000.0,
        risk_fraction=0.01,
        entry_price=100.0,
        stop_loss_price=99.5,  # 0.5% stop
    )
    wide = engine._calculate_max_notional_for_risk(
        bot=bot,
        bot_capital=1000.0,
        risk_fraction=0.01,
        entry_price=100.0,
        stop_loss_price=95.0,  # 5% stop
    )

    assert tight == 1000.0  # capped at capital
    assert round(wide, 2) == 200.0


def test_check_trade_risk_rejects_when_fractional_risk_exceeded():
    engine = RiskEngine()
    user_id = "user-1"
    bot = {"id": "bot-1", "user_id": user_id, "current_capital": 1000.0, "stop_loss_pct": 0.01}

    bot_cursor = MagicMock()
    bot_cursor.to_list = AsyncMock(return_value=[bot])
    trades_cursor = MagicMock()
    trades_cursor.to_list = AsyncMock(return_value=[])

    mock_db = MagicMock()
    mock_db.bots_collection.find_one = AsyncMock(return_value=bot)
    mock_db.bots_collection.find = MagicMock(return_value=bot_cursor)
    mock_db.trades_collection.find = MagicMock(return_value=trades_cursor)
    mock_db.users_collection.find_one = AsyncMock(return_value={"risk_profile": "safe"})

    with patch("risk_engine.db", mock_db), \
         patch.object(engine, "_check_daily_loss", new=AsyncMock(return_value=None)):
        allowed, reason = asyncio.run(engine.check_trade_risk(
            user_id=user_id,
            bot_id="bot-1",
            exchange="binance",
            proposed_notional=500.0,
            risk_mode="safe",
            entry_price=100.0,
            stop_loss_price=95.0,  # 5% stop => max_notional ~ R200 at 1% risk
        ))

    assert allowed is False
    assert "fixed-fractional risk cap" in reason
