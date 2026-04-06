"""
Tests for the /api/bots/seed-luno-paper endpoint.

Verifies:
1. Double-seed results in exactly 5 bots (idempotency).
2. Seed when >5 bots exist returns 409 and creates no new bots.
3. After seed, each of the 5 bots has a paper_ledger entry.
4. Paper tick does not emit "No paper wallet found" for seeded bots.
"""

import pytest
from fastapi import HTTPException
from unittest.mock import AsyncMock, MagicMock, patch
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

_GBOT_NAMES = ["Gbot1", "Gbot2", "Gbot3", "Gbot4", "Gbot5"]


def _make_bot(name: str, bot_id: str) -> dict:
    return {
        "id": bot_id,
        "user_id": "test_user",
        "name": name,
        "status": "active",
        "exchange": "luno",
        "trading_mode": "paper",
    }


async def _run_seed(bots_col, ledger_col=None, wallets_col=None, wb_col=None):
    """Call seed_luno_paper_bots with database mocks patched in."""
    from routes.bot_lifecycle import seed_luno_paper_bots
    import services.paper_wallet_ledger as lwm
    import services.paper_wallet_service as pwm

    patches = [
        patch("database.bots_collection", bots_col),
        patch("routes.system_mode.get_system_mode", new_callable=AsyncMock,
              return_value={"liveTrading": False}),
    ]
    if ledger_col is not None:
        patches.append(patch("database.paper_ledger_collection", ledger_col))
    if wallets_col is not None:
        patches.append(patch("database.wallets_collection", wallets_col))
    if wb_col is not None:
        patches.append(patch("database.wallet_balances_collection", wb_col))

    # Reset singleton collections so init_db() picks up the new mocks.
    orig_ledger_col = lwm.paper_wallet_ledger.collection
    orig_wallet_col = pwm.paper_wallet_service.collection
    lwm.paper_wallet_ledger.collection = ledger_col
    pwm.paper_wallet_service.collection = wallets_col

    ctx_managers = [p.__enter__() for p in patches]
    try:
        return await seed_luno_paper_bots(user_id="test_user")
    finally:
        for p, _ in zip(reversed(patches), reversed(ctx_managers)):
            p.__exit__(None, None, None)
        lwm.paper_wallet_ledger.collection = orig_ledger_col
        pwm.paper_wallet_service.collection = orig_wallet_col


def _make_wallet_mocks():
    """Return (ledger_col, wallets_col, wb_col) mocks with standard behaviour."""
    mock_ledger = MagicMock()
    mock_ledger.find_one = AsyncMock(return_value=None)
    mock_ledger.insert_one = AsyncMock(return_value=MagicMock(inserted_id="x"))
    mock_ledger.find_one_and_update = AsyncMock(return_value=None)
    mock_ledger.aggregate = MagicMock(
        return_value=MagicMock(to_list=AsyncMock(return_value=[]))
    )

    mock_wallets = MagicMock()
    mock_wallets.find_one = AsyncMock(
        return_value={"user_id": "test_user", "type": "paper", "balances": {"ZAR": 50000.0}}
    )
    mock_wallets.find_one_and_update = AsyncMock(
        return_value={"balances": {"ZAR": 40000.0}}
    )
    mock_wallets.update_one = AsyncMock()

    mock_wb = MagicMock()
    mock_wb.update_one = AsyncMock()

    return mock_ledger, mock_wallets, mock_wb


# ---------------------------------------------------------------------------
# 1. Idempotency
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_double_seed_creates_exactly_5():
    """Calling seed twice must result in exactly 5 bots; no duplicates."""
    call_count = {"n": 0}
    inserted = []

    async def count_documents(filt):
        return 0 if call_count["n"] == 0 else 5

    async def find_one_bot(filt, projection=None):
        if call_count["n"] == 0:
            return None
        name = filt.get("name")
        match = next((b for b in inserted if b["name"] == name), None)
        if match:
            return {"id": match["id"], "name": match["name"], "status": "active"}
        return None

    async def insert_bot(doc):
        inserted.append(doc)
        return MagicMock(inserted_id="dummy")

    mock_bots = MagicMock()
    mock_bots.count_documents = AsyncMock(side_effect=count_documents)
    mock_bots.find_one = AsyncMock(side_effect=find_one_bot)
    mock_bots.insert_one = AsyncMock(side_effect=insert_bot)

    ledger_col, wallets_col, wb_col = _make_wallet_mocks()

    # First seed
    call_count["n"] = 0
    data1 = await _run_seed(mock_bots, ledger_col, wallets_col, wb_col)
    assert data1["created"] == 5
    assert data1["existing"] == 0
    assert len(inserted) == 5

    # Second seed - all 5 already exist
    call_count["n"] = 1
    data2 = await _run_seed(mock_bots, ledger_col, wallets_col, wb_col)
    assert data2["created"] == 0
    assert data2["existing"] == 5
    # Bot count unchanged
    assert len(inserted) == 5


# ---------------------------------------------------------------------------
# 2. MAX 5 enforcement
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_over_limit_returns_409():
    """If >5 luno paper bots exist, seed must raise HTTP 409."""
    over_limit_bots = [_make_bot(f"Gbot{i}", f"bot-{i}") for i in range(1, 9)]  # 8

    mock_bots = MagicMock()
    mock_bots.count_documents = AsyncMock(return_value=8)
    mock_find_cursor = MagicMock()
    mock_find_cursor.to_list = AsyncMock(return_value=over_limit_bots)
    mock_bots.find = MagicMock(return_value=mock_find_cursor)
    mock_bots.insert_one = AsyncMock()

    with pytest.raises(HTTPException) as exc_info:
        await _run_seed(mock_bots)

    assert exc_info.value.status_code == 409
    detail = exc_info.value.detail
    assert detail.get("count") == 8
    assert "bots" in detail
    # No bot was created
    mock_bots.insert_one.assert_not_called()


@pytest.mark.asyncio
async def test_over_limit_does_not_create_new_bots():
    """Even with >5 bots, the insert_one must never be called."""
    existing = [_make_bot(f"Extra{i}", f"eid-{i}") for i in range(7)]

    mock_bots = MagicMock()
    mock_bots.count_documents = AsyncMock(return_value=7)
    mock_cursor = MagicMock()
    mock_cursor.to_list = AsyncMock(return_value=existing)
    mock_bots.find = MagicMock(return_value=mock_cursor)
    mock_bots.insert_one = AsyncMock()

    with pytest.raises(HTTPException) as exc_info:
        await _run_seed(mock_bots)

    assert exc_info.value.status_code == 409
    mock_bots.insert_one.assert_not_called()


@pytest.mark.asyncio
async def test_exactly_5_returns_all_existing():
    """When exactly 5 bots exist, seed must return them all as 'existing'."""
    existing_bots = [_make_bot(name, f"bid-{i}") for i, name in enumerate(_GBOT_NAMES)]

    async def find_one_bot(filt, projection=None):
        name = filt.get("name")
        match = next((b for b in existing_bots if b["name"] == name), None)
        if match:
            return {"id": match["id"], "name": match["name"], "status": "active"}
        return None

    mock_bots = MagicMock()
    mock_bots.count_documents = AsyncMock(return_value=5)
    mock_bots.find_one = AsyncMock(side_effect=find_one_bot)
    mock_bots.insert_one = AsyncMock()

    _, wallets_col, wb_col = _make_wallet_mocks()

    data = await _run_seed(mock_bots, wallets_col=wallets_col, wb_col=wb_col)

    assert data["created"] == 0
    assert data["existing"] == 5
    mock_bots.insert_one.assert_not_called()


# ---------------------------------------------------------------------------
# 3. Ledger entries created for each new bot
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_ledger_entries_created_for_new_bots():
    """After seed, each of the 5 new bots has a paper_ledger entry."""
    ledger_entries = []

    async def ledger_insert_one(doc):
        ledger_entries.append(doc)
        return MagicMock(inserted_id="dummy")

    mock_bots = MagicMock()
    mock_bots.count_documents = AsyncMock(return_value=0)
    mock_bots.find_one = AsyncMock(return_value=None)
    mock_bots.insert_one = AsyncMock(return_value=MagicMock(inserted_id="x"))

    mock_ledger = MagicMock()
    mock_ledger.find_one = AsyncMock(return_value=None)
    mock_ledger.insert_one = AsyncMock(side_effect=ledger_insert_one)
    mock_ledger.find_one_and_update = AsyncMock(return_value=None)
    mock_ledger.aggregate = MagicMock(
        return_value=MagicMock(to_list=AsyncMock(return_value=[]))
    )

    _, wallets_col, wb_col = _make_wallet_mocks()

    data = await _run_seed(mock_bots, mock_ledger, wallets_col, wb_col)

    assert data["created"] == 5
    assert len(ledger_entries) == 5
    for entry in ledger_entries:
        assert entry.get("user_id") == "test_user"
        assert "bot_id" in entry
        assert entry.get("current_balance", 0) > 0
        assert entry.get("status") == "active"


# ---------------------------------------------------------------------------
# 4. No "No paper wallet found" for seeded bots
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_balance_returns_success_for_seeded_bot():
    """get_balance must succeed (no 'No paper wallet found') when ledger entry exists."""
    import services.paper_wallet_ledger as lwm

    bot_id = "seeded-bot-123"
    ledger_doc = {
        "bot_id": bot_id,
        "user_id": "test_user",
        "current_balance": 10000.0,
        "initial_balance": 10000.0,
        "currency": "ZAR",
        "status": "active",
    }

    mock_col = MagicMock()
    mock_col.find_one = AsyncMock(return_value=ledger_doc)

    ledger = lwm.PaperWalletLedger()
    ledger.collection = mock_col

    success, balance, msg = await ledger.get_balance(bot_id)

    assert success is True, f"Expected success=True but got: {msg}"
    assert balance == 10000.0
    assert "No paper wallet found" not in msg


@pytest.mark.asyncio
async def test_get_balance_missing_ledger_auto_reserves_when_bot_has_capital():
    """When no ledger entry exists but bot has initial_capital, auto-reserve must succeed."""
    import services.paper_wallet_ledger as lwm

    bot_id = "auto-bot-789"
    bot_doc = {"id": bot_id, "user_id": "test_user", "initial_capital": 5000.0,
               "exchange": "luno", "pair": "BTC/ZAR"}
    ledger_entry = {"bot_id": bot_id, "user_id": "test_user",
                    "current_balance": 5000.0, "status": "active"}

    call_count = {"n": 0}

    async def mock_find_one(filt, projection=None):
        call_count["n"] += 1
        return None if call_count["n"] <= 1 else ledger_entry

    mock_col = MagicMock()
    mock_col.find_one = AsyncMock(side_effect=mock_find_one)
    mock_col.insert_one = AsyncMock(return_value=MagicMock(inserted_id="x"))

    mock_bots = MagicMock()
    mock_bots.find_one = AsyncMock(return_value=bot_doc)

    mock_wallets = MagicMock()
    mock_wallets.find_one = AsyncMock(
        return_value={"user_id": "test_user", "type": "paper", "balances": {"ZAR": 5000.0}}
    )
    mock_wallets.find_one_and_update = AsyncMock(
        return_value={"balances": {"ZAR": 0.0}}
    )

    mock_wb = MagicMock()
    mock_wb.update_one = AsyncMock()

    with (
        patch("database.bots_collection", mock_bots),
        patch("database.paper_ledger_collection", mock_col),
        patch("database.wallets_collection", mock_wallets),
        patch("database.wallet_balances_collection", mock_wb),
    ):
        ledger = lwm.PaperWalletLedger()
        ledger.collection = mock_col

        with patch.object(ledger, "reserve_funds", new_callable=AsyncMock) as mock_reserve:
            mock_reserve.return_value = (True, "Reserved")
            success, balance, msg = await ledger.get_balance(bot_id)

    assert success is True
    assert "No paper wallet found" not in msg


