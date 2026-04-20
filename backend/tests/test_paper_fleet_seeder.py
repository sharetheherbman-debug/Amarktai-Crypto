"""
Tests for the canonical paper fleet seeder.

Covers the three required regression tests:

1. test_seed_fleet_respects_exchange_selection
   — If run selection is luno+binance, the seeded fleet contains bots on both exchanges.

2. test_seed_fleet_correct_type_distribution
   — 10 normal / 10 scalper after a 20-bot seed across 2 exchanges.

3. test_seeded_bots_visible_to_user
   — Seeded bots appear in the standard bot-not-deleted query (same filter
     used by /api/bots/status, /api/diagnostics/go-live, /api/radar/snapshot,
     /api/dashboard/overview).

Additional sanity checks:
4. test_seed_fleet_luno_only_when_one_exchange
5. test_seed_fleet_luno_uses_zar_capital
6. test_seed_fleet_binance_uses_usdt_capital
7. test_seed_fleet_correct_canonical_fields
8. test_seed_fleet_no_hardcoded_luno_pair_for_binance
9. test_seed_fleet_single_source_of_truth
"""

import os
import sys
import pytest
import asyncio
from unittest.mock import AsyncMock, patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mock_db(inserted: list):
    """Return a mock db where insert_many appends to *inserted*."""

    async def _insert_many(docs):
        inserted.extend(docs)

    async def _count_documents(query):
        # Return 0 so cap checks always pass (fresh DB state)
        return 0

    mock_coll = MagicMock()
    mock_coll.insert_many = _insert_many
    mock_coll.count_documents = _count_documents

    mock_db = MagicMock()
    mock_db.bots_collection = mock_coll
    return mock_db


def _mock_wallet_service(balance_zar: float = 30000.0):
    """Return a mock paper_wallet_service with a given ZAR balance."""
    svc = MagicMock()
    svc.get_available_balance = AsyncMock(return_value=balance_zar)
    svc.fund = AsyncMock()
    return svc


# ---------------------------------------------------------------------------
# 1. Exchange selection is respected
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_seed_fleet_respects_exchange_selection():
    """Luno+Binance selection → fleet contains bots on both exchanges."""
    inserted = []

    with (
        patch("services.paper_fleet_seeder.db") as mock_db_mod,
        patch("services.paper_fleet_seeder.paper_wallet_service", _mock_wallet_service()),
    ):
        mock_db_mod.bots_collection = _make_mock_db(inserted).bots_collection

        from services.paper_fleet_seeder import seed_paper_fleet
        result = await seed_paper_fleet(
            user_id="user-abc123",
            exchanges=["luno", "binance"],
            normal_per_exchange=5,
            scalper_per_exchange=5,
        )

    assert result["bots_created"] == 20, (
        f"Expected 20 bots created, got {result['bots_created']}"
    )

    exchanges_in_fleet = {bot["exchange"] for bot in inserted}
    assert "luno" in exchanges_in_fleet, "Fleet must contain luno bots"
    assert "binance" in exchanges_in_fleet, "Fleet must contain binance bots"

    luno_bots = [b for b in inserted if b["exchange"] == "luno"]
    binance_bots = [b for b in inserted if b["exchange"] == "binance"]
    assert len(luno_bots) == 10, f"Expected 10 luno bots, got {len(luno_bots)}"
    assert len(binance_bots) == 10, f"Expected 10 binance bots, got {len(binance_bots)}"


# ---------------------------------------------------------------------------
# 2. Normal / scalper type distribution
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_seed_fleet_correct_type_distribution():
    """20-bot fleet across 2 exchanges → 10 normal / 10 scalper."""
    inserted = []

    with (
        patch("services.paper_fleet_seeder.db") as mock_db_mod,
        patch("services.paper_fleet_seeder.paper_wallet_service", _mock_wallet_service()),
    ):
        mock_db_mod.bots_collection = _make_mock_db(inserted).bots_collection

        from services.paper_fleet_seeder import seed_paper_fleet
        result = await seed_paper_fleet(
            user_id="user-type-test",
            exchanges=["luno", "binance"],
            normal_per_exchange=5,
            scalper_per_exchange=5,
        )

    normal_bots = [b for b in inserted if b.get("bot_type") == "normal"]
    scalper_bots = [b for b in inserted if b.get("bot_type") == "scalper"]

    assert len(normal_bots) == 10, (
        f"Expected 10 normal bots, got {len(normal_bots)}"
    )
    assert len(scalper_bots) == 10, (
        f"Expected 10 scalper bots, got {len(scalper_bots)}"
    )

    # Type breakdown reported in result
    assert result["by_exchange"]["luno"]["normal"] == 5
    assert result["by_exchange"]["luno"]["scalper"] == 5
    assert result["by_exchange"]["binance"]["normal"] == 5
    assert result["by_exchange"]["binance"]["scalper"] == 5


# ---------------------------------------------------------------------------
# 3. Seeded bots are visible to user via canonical query
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_seeded_bots_visible_to_user():
    """Seeded bots pass the bot_not_deleted_filter used by /api/bots/status."""
    from services.bot_filters import bot_not_deleted_filter

    inserted = []

    with (
        patch("services.paper_fleet_seeder.db") as mock_db_mod,
        patch("services.paper_fleet_seeder.paper_wallet_service", _mock_wallet_service()),
    ):
        mock_db_mod.bots_collection = _make_mock_db(inserted).bots_collection

        from services.paper_fleet_seeder import seed_paper_fleet
        await seed_paper_fleet(
            user_id="user-visible",
            exchanges=["luno"],
            normal_per_exchange=5,
            scalper_per_exchange=5,
        )

    required_filter = bot_not_deleted_filter()

    for bot in inserted:
        # status must NOT be "deleted" or "marked_for_deletion"
        status = bot.get("status", "")
        assert status not in ("deleted", "marked_for_deletion"), (
            f"Seeded bot has status '{status}' which is excluded by canonical filter"
        )

        # is_deleted must not be True
        assert bot.get("is_deleted") is not True, "Seeded bot must not have is_deleted=True"

        # deleted must not be True
        assert bot.get("deleted") is not True, "Seeded bot must not have deleted=True"

        # deleted_at must not be present
        assert "deleted_at" not in bot, (
            "Seeded bot must not have deleted_at field — it would be filtered out"
        )

        # Must have user_id so ownership queries work
        assert bot.get("user_id") == "user-visible", "Seeded bot must carry the correct user_id"


# ---------------------------------------------------------------------------
# 4. Luno-only fleet when one exchange
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_seed_fleet_luno_only_when_one_exchange():
    """When only luno is in exchanges, no binance bots are created."""
    inserted = []

    with (
        patch("services.paper_fleet_seeder.db") as mock_db_mod,
        patch("services.paper_fleet_seeder.paper_wallet_service", _mock_wallet_service()),
    ):
        mock_db_mod.bots_collection = _make_mock_db(inserted).bots_collection

        from services.paper_fleet_seeder import seed_paper_fleet
        result = await seed_paper_fleet(
            user_id="user-luno-only",
            exchanges=["luno"],
            normal_per_exchange=5,
            scalper_per_exchange=5,
        )

    exchanges = {b["exchange"] for b in inserted}
    assert exchanges == {"luno"}, f"Only luno expected, got: {exchanges}"
    assert result["bots_created"] == 10


# ---------------------------------------------------------------------------
# 5. Luno bots use ZAR capital (no conversion)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_seed_fleet_luno_uses_zar_capital():
    """Luno bots must store quote_currency=ZAR and fx_rate_at_creation=1.0."""
    inserted = []

    with (
        patch("services.paper_fleet_seeder.db") as mock_db_mod,
        patch("services.paper_fleet_seeder.paper_wallet_service", _mock_wallet_service(10000.0)),
    ):
        mock_db_mod.bots_collection = _make_mock_db(inserted).bots_collection

        from services.paper_fleet_seeder import seed_paper_fleet
        await seed_paper_fleet(
            user_id="user-luno-cap",
            exchanges=["luno"],
            normal_per_exchange=5,
            scalper_per_exchange=0,
        )

    luno_bots = [b for b in inserted if b["exchange"] == "luno"]
    assert luno_bots, "Should have luno bots"
    for bot in luno_bots:
        assert bot.get("quote_currency") == "ZAR", (
            f"Luno bot must have quote_currency=ZAR, got {bot.get('quote_currency')}"
        )
        assert bot.get("fx_rate_at_creation") == pytest.approx(1.0), (
            f"Luno bot must have fx_rate_at_creation=1.0, got {bot.get('fx_rate_at_creation')}"
        )
        # initial_capital must equal canonical_base_capital_zar for Luno
        assert bot.get("initial_capital") == pytest.approx(
            bot.get("canonical_base_capital_zar"), rel=1e-4
        ), "Luno initial_capital must equal canonical_base_capital_zar"
        # Default pair for Luno is BTC/ZAR (CCXT-normalised from XBT/ZAR)
        assert bot.get("pair") == "BTC/ZAR", (
            f"Luno default pair must be BTC/ZAR (CCXT-normalised), got {bot.get('pair')}"
        )


# ---------------------------------------------------------------------------
# 6. Binance bots use USDT capital (FX-converted)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_seed_fleet_binance_uses_usdt_capital():
    """Binance bots must store quote_currency=USDT and initial_capital != ZAR base."""
    from services.fx_normalizer import update_fx_rate
    update_fx_rate(19.0, "test")

    inserted = []

    with (
        patch("services.paper_fleet_seeder.db") as mock_db_mod,
        patch("services.paper_fleet_seeder.paper_wallet_service", _mock_wallet_service(19000.0)),
    ):
        mock_db_mod.bots_collection = _make_mock_db(inserted).bots_collection

        from services.paper_fleet_seeder import seed_paper_fleet
        await seed_paper_fleet(
            user_id="user-binance-cap",
            exchanges=["binance"],
            normal_per_exchange=5,
            scalper_per_exchange=0,
            capital_zar_per_bot=1000.0,
        )

    binance_bots = [b for b in inserted if b["exchange"] == "binance"]
    assert binance_bots, "Should have binance bots"
    for bot in binance_bots:
        assert bot.get("quote_currency") == "USDT", (
            f"Binance bot must have quote_currency=USDT, got {bot.get('quote_currency')}"
        )
        # At FX=19, R1000 ZAR → ≈52.63 USDT (definitely not 1000)
        assert bot.get("initial_capital") == pytest.approx(1000.0 / 19.0, rel=1e-3), (
            f"Binance initial_capital should be ≈52.63 USDT at FX 19, "
            f"got {bot.get('initial_capital')}"
        )
        assert bot.get("canonical_base_capital_zar") == pytest.approx(1000.0, rel=1e-3), (
            "canonical_base_capital_zar must always be the ZAR economic base"
        )


# ---------------------------------------------------------------------------
# 7. Canonical fields are always present
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_seed_fleet_correct_canonical_fields():
    """Every seeded bot must carry all canonical capital + identity fields."""
    inserted = []
    required_fields = [
        "id", "user_id", "name", "status", "trading_mode", "exchange",
        "pair", "bot_type", "strategy_preset", "risk_mode",
        "canonical_base_capital_zar", "funding_input_amount",
        "funding_input_currency", "fx_rate_at_creation", "quote_currency",
        "initial_capital", "current_capital", "total_profit", "trades_count",
        "origin", "created_at",
    ]

    with (
        patch("services.paper_fleet_seeder.db") as mock_db_mod,
        patch("services.paper_fleet_seeder.paper_wallet_service", _mock_wallet_service()),
    ):
        mock_db_mod.bots_collection = _make_mock_db(inserted).bots_collection

        from services.paper_fleet_seeder import seed_paper_fleet
        await seed_paper_fleet(
            user_id="user-fields",
            exchanges=["luno", "binance"],
            normal_per_exchange=2,
            scalper_per_exchange=2,
        )

    assert inserted, "Expected bots to be created"
    for bot in inserted:
        for field in required_fields:
            assert field in bot, (
                f"Canonical field '{field}' is missing from seeded bot '{bot.get('name')}'"
            )
        # status must be active
        assert bot["status"] == "active"
        # trading_mode must be paper
        assert bot["trading_mode"] == "paper"


# ---------------------------------------------------------------------------
# 8. No hardcoded Luno pair for Binance bots
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_seed_fleet_no_hardcoded_luno_pair_for_binance():
    """Binance bots must NOT have pair='XBT/ZAR' (a Luno-only pair)."""
    inserted = []

    with (
        patch("services.paper_fleet_seeder.db") as mock_db_mod,
        patch("services.paper_fleet_seeder.paper_wallet_service", _mock_wallet_service()),
    ):
        mock_db_mod.bots_collection = _make_mock_db(inserted).bots_collection

        from services.paper_fleet_seeder import seed_paper_fleet
        await seed_paper_fleet(
            user_id="user-pair-test",
            exchanges=["binance"],
            normal_per_exchange=5,
            scalper_per_exchange=0,
        )

    binance_bots = [b for b in inserted if b["exchange"] == "binance"]
    for bot in binance_bots:
        assert bot.get("pair") != "XBT/ZAR", (
            f"Binance bot has Luno pair 'XBT/ZAR': {bot}"
        )
        assert bot.get("pair") == "BTC/USDT", (
            f"Binance bot default pair should be 'BTC/USDT', got {bot.get('pair')}"
        )


# ---------------------------------------------------------------------------
# 9. Single source of truth — no other module contains inline bot insertion
# ---------------------------------------------------------------------------

def test_seed_fleet_single_source_of_truth():
    """Verify that system.py and admin_start_fresh.py no longer contain
    inline bots_collection.insert_many calls in their seed functions.

    The canonical seed path is now in services/paper_fleet_seeder.py.
    """
    import re
    backend_root = os.path.join(os.path.dirname(__file__), "..")

    files_to_check = [
        os.path.join(backend_root, "routes", "system.py"),
        os.path.join(backend_root, "routes", "admin_start_fresh.py"),
        os.path.join(backend_root, "routes", "bot_lifecycle.py"),
    ]

    # Pattern: inline insert_many inside a function that contains "seed" or "bot"
    # We look for the specific pattern of building a list of bot dicts then inserting —
    # the canonical seeder is the only allowed place for this.
    for path in files_to_check:
        with open(path) as f:
            content = f.read()

        # No inline bot insertion dict with hardcoded "exchange": "luno" in seed paths
        luno_hardcode = re.search(
            r'"exchange":\s*"luno"',
            content,
        )
        # Allow it only in the luno-specific endpoint comment/docstring context,
        # NOT as a dict literal being built for insertion.
        # We check for the specific pattern of a bot-dict literal with hardcoded luno:
        bot_dict_with_luno = re.search(
            r'\{\s*["\']id["\']\s*:.*?["\']exchange["\']\s*:\s*["\']luno["\']',
            content,
            re.DOTALL,
        )
        assert bot_dict_with_luno is None, (
            f"{os.path.basename(path)} still contains an inline bot dict with "
            f"hardcoded exchange='luno'. Use seed_paper_fleet() instead."
        )

    # The canonical seeder file must exist
    seeder_path = os.path.join(backend_root, "services", "paper_fleet_seeder.py")
    assert os.path.exists(seeder_path), "services/paper_fleet_seeder.py must exist"

    with open(seeder_path) as f:
        seeder_content = f.read()

    assert "seed_paper_fleet" in seeder_content, "seed_paper_fleet must be defined in the seeder"
    assert "resolve_capital_for_exchange" in seeder_content, (
        "seeder must use resolve_capital_for_exchange for correct FX conversion"
    )
    assert "get_user_paper_exchanges" not in seeder_content, (
        "seeder must not call get_user_paper_exchanges itself — "
        "callers resolve exchanges before calling seed_paper_fleet"
    )
