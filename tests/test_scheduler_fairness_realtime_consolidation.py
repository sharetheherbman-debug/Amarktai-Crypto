from pathlib import Path
import asyncio
import os
import sys
from unittest.mock import AsyncMock, patch


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, os.path.join(ROOT, "backend"))


def _read(rel_path: str) -> str:
    return (ROOT / rel_path).read_text(encoding="utf-8")


def test_scheduler_uses_round_robin_queue_rotation():
    src = _read("backend/trading_scheduler.py")
    assert "self._queue_rotation_offset = 0" in src
    assert "def _fair_queue_order" in src
    assert "for bot in self._fair_queue_order(active_bots):" in src


def test_trade_staggerer_avoids_back_to_back_same_bot_when_queued():
    src = _read("backend/engines/trade_staggerer.py")
    assert "self.last_dispatched_bot_id" in src
    assert "deferred_same_bot" in src
    assert "bot_id == self.last_dispatched_bot_id" in src


def test_realtime_events_no_duplicate_key_methods_and_single_system_mode_event():
    src = _read("backend/realtime_events.py")
    assert src.count("def key_saved(") == 1
    assert src.count("def key_tested(") == 1
    assert '"type": "system_mode_update"' not in src
    assert '"type": "system_mode_changed"' in src


def test_system_mode_changed_emits_single_message_runtime():
    from realtime_events import RealTimeEvents

    with patch("realtime_events.manager.send_message", new=AsyncMock()) as send_message:
        asyncio.run(RealTimeEvents.system_mode_changed("user-1", "autopilot", True))
        assert send_message.await_count == 1


def test_dashboard_state_and_data_consolidate_trade_refresh_variants():
    state_src = _read("frontend/src/hooks/useDashboardState.js")
    data_src = _read("frontend/src/hooks/useDashboardData.js")

    assert "case 'trade_inserted':" in state_src
    assert "case 'system_mode_changed':" in state_src
    assert "refreshCanonicalTradeTruth();" in state_src

    assert "const refreshTradeTruth = () => {" in data_src
    assert "realtimeClient.on('trade_inserted'" in data_src
    assert "realtimeClient.on('trades_update', refreshTradeTruth)" in data_src
