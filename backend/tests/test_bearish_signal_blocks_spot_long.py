import os
import sys
import pytest

backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, backend_dir)


@pytest.mark.asyncio
async def test_bearish_signal_blocks_spot_long(monkeypatch):
    from trading_scheduler import trading_scheduler

    class _Regime:
        class _R:
            value = "bear"
        regime = _R()

    class _Detector:
        async def detect_regime(self, *_args, **_kwargs):
            return _Regime()

    import engines.regime_detector as rd
    monkeypatch.setattr(rd, "regime_detector", _Detector())

    bot = {
        "id": "bot_1",
        "user_id": "u1",
        "name": "Spot Bot",
        "exchange": "binance",
        "pair": "BTC/USDT",
        "risk_mode": "safe",
        "current_capital": 1000.0,
        "market_type": "spot",
        "supports_shorting": False,
    }

    result = await trading_scheduler.execute_live_trade(bot)
    assert result["success"] is False
    assert result["skip_reason"] == "bearish_spot_no_short"
    assert result["trade_direction"] == "FLAT"
