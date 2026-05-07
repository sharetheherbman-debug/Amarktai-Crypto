"""
Verify that freshly seeded paper bots are eligible for the scheduler
(no paused_by_system, correct lifecycle state, valid pairs).
"""
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, backend_dir)


async def _run_seed(user_id: str = "scheduler_seed_user") -> tuple:
    """Run _seed_standard_paper_bots with mocked DB and return (payload, inserted_docs)."""
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
    mock_wallets.find_one = AsyncMock(return_value={
        "user_id": user_id, "type": "paper", "balances": {"ZAR": 30000.0}
    })
    mock_wallets.find_one_and_update = AsyncMock(return_value={"balances": {"ZAR": 24000.0}})
    mock_wallets.update_one = AsyncMock()

    with patch("database.bots_collection", mock_bots), patch(
        "routes.system_mode.get_system_mode",
        new=AsyncMock(return_value={"liveTrading": False}),
    ), patch("database.paper_ledger_collection", mock_ledger), patch(
        "database.wallets_collection", mock_wallets
    ), patch("database.wallet_balances_collection", MagicMock(update_one=AsyncMock())):
        old_ledger = ledger_mod.paper_wallet_ledger.collection
        old_wallet = wallet_mod.paper_wallet_service.collection
        ledger_mod.paper_wallet_ledger.collection = mock_ledger
        wallet_mod.paper_wallet_service.collection = mock_wallets
        try:
            payload = await _seed_standard_paper_bots(user_id=user_id)
        finally:
            ledger_mod.paper_wallet_ledger.collection = old_ledger
            wallet_mod.paper_wallet_service.collection = old_wallet

    return payload, inserted_docs


@pytest.mark.asyncio
async def test_seeded_bots_have_correct_lifecycle_state():
    """Seeded bots must have lifecycle_state=active and status=active."""
    payload, inserted_docs = await _run_seed()

    assert payload["success"] is True
    assert inserted_docs, "No bots were inserted"

    for doc in inserted_docs:
        assert doc.get("lifecycle_state") == "active", (
            f"Bot {doc.get('name')} has lifecycle_state={doc.get('lifecycle_state')!r}, expected 'active'"
        )
        assert doc.get("status") == "active", (
            f"Bot {doc.get('name')} has status={doc.get('status')!r}, expected 'active'"
        )


@pytest.mark.asyncio
async def test_seeded_bots_not_paused():
    """Seeded bots must not be paused (paused=False, paused_by_user/system absent)."""
    _, inserted_docs = await _run_seed()

    assert inserted_docs, "No bots were inserted"
    for doc in inserted_docs:
        assert not doc.get("paused"), f"Bot {doc.get('name')} is paused"
        assert not doc.get("paused_by_user"), f"Bot {doc.get('name')} paused_by_user=True"
        assert not doc.get("paused_by_system"), f"Bot {doc.get('name')} paused_by_system=True"


@pytest.mark.asyncio
async def test_seeded_bots_training_complete_and_ready():
    """Seeded bots must have training_complete=True and paper_test_ready=True."""
    _, inserted_docs = await _run_seed()

    assert inserted_docs, "No bots were inserted"
    for doc in inserted_docs:
        assert doc.get("training_complete") is True, (
            f"Bot {doc.get('name')} training_complete is not True"
        )
        assert doc.get("paper_test_ready") is True, (
            f"Bot {doc.get('name')} paper_test_ready is not True"
        )


@pytest.mark.asyncio
async def test_seeded_bots_have_no_last_order_error():
    """Freshly seeded bots must have last_order_error=None (no stale errors)."""
    _, inserted_docs = await _run_seed()

    assert inserted_docs, "No bots were inserted"
    for doc in inserted_docs:
        assert doc.get("last_order_error") is None, (
            f"Bot {doc.get('name')} has stale last_order_error={doc.get('last_order_error')!r}"
        )


@pytest.mark.asyncio
async def test_seeded_bots_trading_mode_is_paper():
    """Seeded bots must have trading_mode=paper."""
    _, inserted_docs = await _run_seed()

    assert inserted_docs, "No bots were inserted"
    for doc in inserted_docs:
        assert doc.get("trading_mode") == "paper", (
            f"Bot {doc.get('name')} trading_mode={doc.get('trading_mode')!r}, expected 'paper'"
        )


@pytest.mark.asyncio
async def test_seeded_bots_have_capital_allocated():
    """Seeded bots must have current_capital > 0."""
    _, inserted_docs = await _run_seed()

    assert inserted_docs, "No bots were inserted"
    for doc in inserted_docs:
        assert (doc.get("current_capital") or 0) > 0, (
            f"Bot {doc.get('name')} has no capital allocated"
        )
