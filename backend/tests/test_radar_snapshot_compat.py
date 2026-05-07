import os
import sys
import pytest
from unittest.mock import AsyncMock

backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, backend_dir)


@pytest.mark.asyncio
async def test_radar_snapshot_compat_shape(monkeypatch):
    from routes.dashboard_overview import get_radar_snapshot
    from services.overview_service import overview_service

    monkeypatch.setattr(
        overview_service,
        "get_snapshot",
        AsyncMock(
            return_value={
                "market_mood": "neutral",
                "market_regime": "sideways",
                "sentiment_score": 0.5,
                "prices": {"BTC/ZAR": 1000000},
                "bots_active": 2,
                "paper_bots_active": 2,
                "live_bots_active": 0,
                "open_positions": 1,
                "trades_today": 3,
                "win_rate": 66.6,
                "total_profit": 100.0,
                "paper_wallet_total": 1000.0,
                "paper_wallet_allocated": 200.0,
            }
        ),
    )

    result = await get_radar_snapshot(user_id="radar_user")
    assert result["success"] is True
    assert "market" in result
    assert "trades" in result
    assert "wallet" in result
    assert result["source"] == "overview_service"
