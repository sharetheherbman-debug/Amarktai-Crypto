import os
import sys
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, backend_dir)


@pytest.mark.asyncio
async def test_learning_last_run_diagnostics_reports_last_run():
    import database as db

    try:
        import server
    except ImportError as e:
        pytest.skip(f"Server import skipped due to missing dependency: {e}")

    user_id = "learning_diag_user"
    last_run_doc = {
        "user_id": user_id,
        "completed_at": "2026-05-01T01:30:00+00:00",
        "changes_applied": 3,
        "status": "applied",
        "run_id": "run_1",
        "summary": "Updated bounded strategy parameters",
    }

    mock_learning_runs = MagicMock()
    mock_learning_runs.find_one = AsyncMock(return_value=last_run_doc)

    with patch.object(db, "learning_runs_collection", mock_learning_runs):
        payload = await server.diagnostics_learning_last_run(user_id=user_id)

    assert payload["last_run_ts"] == "2026-05-01T01:30:00+00:00"
    assert payload["bots_updated_count"] == 3
    assert payload["last_run_at"] == "2026-05-01T01:30:00+00:00"
    assert payload["parameters_updated"] == 3
    assert payload["audit_id"] == "run_1"
