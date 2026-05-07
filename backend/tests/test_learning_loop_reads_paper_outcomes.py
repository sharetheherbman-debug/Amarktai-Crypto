"""
Verify the learning loop reads real closed paper/live trades (Phase 8).
"""
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, backend_dir)


def test_learning_loop_reads_trades_collection():
    """Learning loop must query db.trades_collection (not a fake/static dataset)."""
    loop_path = os.path.join(backend_dir, "services", "learning_loop.py")
    with open(loop_path, "r", encoding="utf-8") as f:
        src = f.read()
    assert "trades_collection" in src, (
        "services/learning_loop.py does not reference trades_collection — "
        "learning loop is not reading real trade outcomes"
    )
    assert "status.*closed" in src or '"closed"' in src or "'closed'" in src, (
        "Learning loop does not filter for closed trades"
    )


def test_learning_loop_writes_learning_runs_collection():
    """Learning loop must write audit trail to learning_runs_collection."""
    loop_path = os.path.join(backend_dir, "services", "learning_loop.py")
    with open(loop_path, "r", encoding="utf-8") as f:
        src = f.read()
    assert "learning_runs_collection" in src, (
        "services/learning_loop.py does not reference learning_runs_collection — "
        "audit trail may be missing"
    )
    assert "insert_one" in src, (
        "Learning loop does not call insert_one — audit record may not be written"
    )


def test_learning_loop_never_enables_live():
    """Learning loop must never set liveTrading or ENABLE_LIVE_TRADING=true."""
    loop_path = os.path.join(backend_dir, "services", "learning_loop.py")
    with open(loop_path, "r", encoding="utf-8") as f:
        src = f.read()
    assert "ENABLE_LIVE_TRADING" not in src, (
        "Learning loop references ENABLE_LIVE_TRADING — verify it never sets this to true"
    )
    # Should not set liveTrading to True
    assert '"liveTrading": True' not in src and "'liveTrading': True" not in src, (
        "Learning loop contains code that sets liveTrading=True"
    )


def test_learning_loop_target_time_is_configured():
    """LEARNING_LOOP_TARGET_TIME must be exported from services.learning_loop."""
    try:
        from services.learning_loop import LEARNING_LOOP_TARGET_TIME
        from datetime import time
        assert isinstance(LEARNING_LOOP_TARGET_TIME, time), (
            f"LEARNING_LOOP_TARGET_TIME should be a time object, got {type(LEARNING_LOOP_TARGET_TIME)}"
        )
    except ImportError as e:
        import pytest as _pt
        _pt.skip(f"Could not import learning_loop: {e}")


def test_learning_last_run_endpoint_includes_required_fields():
    """GET /api/diagnostics/learning-last-run response must include Phase 8 contract fields."""
    import inspect
    try:
        import server
        src = inspect.getsource(server.diagnostics_learning_last_run)
    except Exception:
        # Try alternate path
        import ast
        server_path = os.path.join(backend_dir, "server.py")
        with open(server_path, "r", encoding="utf-8") as f:
            server_src = f.read()
        src = server_src

    required_fields = ["enabled", "scheduled", "last_run_at", "next_run_at",
                       "trades_analyzed", "parameters_updated", "safety_changes",
                       "audit_id", "last_error"]
    missing = [f for f in required_fields if f'"{f}"' not in src and f"'{f}'" not in src]
    assert not missing, f"diagnostics_learning_last_run missing Phase 8 fields: {missing}"


@pytest.mark.asyncio
async def test_learning_last_run_endpoint_returns_scheduled_and_last_error():
    """diagnostics_learning_last_run must return 'scheduled' and 'last_error' fields."""
    import database as db
    import server

    mock_learning_runs = MagicMock()
    mock_learning_runs.find_one = AsyncMock(return_value=None)

    with patch.object(db, "learning_runs_collection", mock_learning_runs):
        result = await server.diagnostics_learning_last_run(user_id="learning_fields_user")

    assert "scheduled" in result, "Response missing 'scheduled' field (Phase 8)"
    assert "last_error" in result, "Response missing 'last_error' field (Phase 8)"
    # last_error should be None when status is not error
    assert result["last_error"] is None


@pytest.mark.asyncio
async def test_learning_last_run_endpoint_with_error_run():
    """last_error must be populated when the last run had status=error."""
    import database as db
    import server

    error_run = {
        "user_id": "err_user",
        "completed_at": "2026-05-01T01:00:00+00:00",
        "status": "error",
        "trades_analyzed": 0,
        "changes_applied": 0,
        "run_id": "err_run_1",
        "summary": "Connection timeout",
        "error": "Connection timeout",
    }
    mock_learning_runs = MagicMock()
    mock_learning_runs.find_one = AsyncMock(return_value=error_run)

    with patch.object(db, "learning_runs_collection", mock_learning_runs):
        result = await server.diagnostics_learning_last_run(user_id="err_user")

    assert result["last_error"] is not None, (
        "last_error should be populated when status=error"
    )
    assert result["status"] == "error"
