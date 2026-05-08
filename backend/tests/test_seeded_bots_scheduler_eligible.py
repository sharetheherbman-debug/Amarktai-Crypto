import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


@pytest.mark.asyncio
async def test_seeded_bots_scheduler_eligible_field_exists():
    import database as db
    from routes.diagnostics import paper_execution_proof

    user_id = "eligible_seed_user"
    mock_bots = MagicMock()
    mock_bots.find = MagicMock(return_value=MagicMock(to_list=AsyncMock(return_value=[])))
    mock_trades = MagicMock()
    mock_trades.count_documents = AsyncMock(return_value=0)
    mock_trades.find = MagicMock(return_value=MagicMock(sort=MagicMock(return_value=MagicMock(to_list=AsyncMock(return_value=[])))))

    with patch.object(db, "bots_collection", mock_bots), patch.object(db, "trades_collection", mock_trades):
        result = await paper_execution_proof(user_id=user_id)

    assert "eligible_bots_count" in result
    assert isinstance(result["eligible_bots_count"], int)

