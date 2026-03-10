import asyncio
import os
import sys
from unittest.mock import AsyncMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from paper_trading_engine import PaperTradingEngine


def test_exit_profile_defaults_and_overrides():
    profile_scalper = PaperTradingEngine._resolve_exit_profile({"bot_type": "scalper"})
    profile_override = PaperTradingEngine._resolve_exit_profile(
        {"bot_type": "normal", "stop_loss_pct": 0.007},
        {"take_profit_pct": 0.012}
    )

    assert profile_scalper["stop_loss_pct"] <= 0.005
    assert profile_scalper["take_profit_pct"] >= 0.003
    assert profile_override["stop_loss_pct"] == 0.007
    assert profile_override["take_profit_pct"] == 0.012


def test_dynamic_targets_use_atr_when_available():
    engine = PaperTradingEngine()

    with patch("engines.atr_stops.atr_stop_loss.calculate_atr_stop_loss", new=AsyncMock(return_value={
        "stop_loss": 98.0,
        "method": "atr_based",
    })):
        result = asyncio.run(engine._apply_dynamic_exit_targets(
            bot_id="bot-1",
            symbol="BTC/USDT",
            entry_price=100.0,
            stop_loss_pct=0.01,
            take_profit_pct=0.02,
        ))

    assert result["stop_loss_price"] == 98.0
    assert result["take_profit_price"] > 102.0
