import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, backend_dir)


@pytest.mark.asyncio
async def test_seeded_paper_bots_start_ready_without_pair_not_allowed():
    from config import PAPER_PAIR_WHITELIST
    from routes.bot_lifecycle import _seed_standard_paper_bots
    import services.paper_wallet_ledger as ledger_mod
    import services.paper_wallet_service as wallet_mod

    inserted_docs = []
    mock_bots = MagicMock()
    mock_bots.count_documents = AsyncMock(return_value=0)
    mock_bots.find_one = AsyncMock(return_value=None)
    mock_bots.insert_one = AsyncMock(side_effect=lambda doc: inserted_docs.append(doc) or MagicMock())

    mock_ledger = MagicMock()
    mock_ledger.find_one = AsyncMock(return_value=None)
    mock_ledger.insert_one = AsyncMock(return_value=MagicMock())
    mock_ledger.find_one_and_update = AsyncMock(return_value=None)
    mock_ledger.aggregate = MagicMock(return_value=MagicMock(to_list=AsyncMock(return_value=[])))

    mock_wallets = MagicMock()
    mock_wallets.find_one = AsyncMock(return_value={"user_id": "pair_seed_user", "type": "paper", "balances": {"ZAR": 30000.0}})
    mock_wallets.find_one_and_update = AsyncMock(return_value={"balances": {"ZAR": 24000.0}})
    mock_wallets.update_one = AsyncMock()

    with patch("database.bots_collection", mock_bots), patch(
        "routes.system_mode.get_system_mode", new=AsyncMock(return_value={"liveTrading": False})
    ), patch("database.paper_ledger_collection", mock_ledger), patch(
        "database.wallets_collection", mock_wallets
    ), patch("database.wallet_balances_collection", MagicMock(update_one=AsyncMock())):
        old_ledger = ledger_mod.paper_wallet_ledger.collection
        old_wallet = wallet_mod.paper_wallet_service.collection
        ledger_mod.paper_wallet_ledger.collection = mock_ledger
        wallet_mod.paper_wallet_service.collection = mock_wallets
        try:
            await _seed_standard_paper_bots(user_id="pair_seed_user")
        finally:
            ledger_mod.paper_wallet_ledger.collection = old_ledger
            wallet_mod.paper_wallet_service.collection = old_wallet

    allowed_pairs = set(PAPER_PAIR_WHITELIST["luno"])
    assert inserted_docs
    for doc in inserted_docs:
        assert doc["pair"] in allowed_pairs
        assert doc["last_order_error"] is None
        assert doc["training_complete"] is True
        assert doc["paper_test_ready"] is True
