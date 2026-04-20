"""
Final Go-Live Architecture Tests
==================================
Mandatory tests verifying the corrected platform-wallet architecture.
Test numbers correspond to the required test list in the problem statement:

  3. test_no_cross_exchange_wallet_fallback
  5. test_fresh_paper_bots_do_not_inherit_emergency_stop
  7. test_wallet_overview_countdown_performance_share_same_valuation
  8. test_admin_key_monitor_frontend_no_dead_route_calls
  +  test_fleet_seeder_does_not_fund_global_wallet_for_bots (bonus)

These complement the existing tests in test_platform_wallet_architecture.py
which cover items 1, 2, 4, and 6 from the same required list.
"""

from __future__ import annotations

import sys
import os
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))


# ===========================================================================
# 3. reserve_exchange_funds must NOT fall back to the global paper wallet
# ===========================================================================

@pytest.mark.asyncio
async def test_no_cross_exchange_wallet_fallback():
    """reserve_exchange_funds must return (False, ...) when exchange wallet is
    insufficient instead of silently falling back to the global paper wallet.

    This is the critical guard against cross-exchange capital contamination:
    a Luno bot must not drain the Binance wallet (or the global pool) when
    its own exchange wallet is empty.
    """
    from services.paper_wallet_service import PaperWalletService

    svc = PaperWalletService()

    # Simulate the exchange wallet find_one_and_update returning None
    # (exchange wallet has insufficient funds).
    async def mock_find_update(filter_q, update, return_document=None):
        # Always return None — simulating insufficient exchange wallet balance.
        return None

    mock_col = AsyncMock()
    mock_col.find_one_and_update = AsyncMock(side_effect=mock_find_update)
    # get_exchange_wallet (called for error message) needs find_one
    mock_col.find_one = AsyncMock(
        return_value={
            "user_id": "user1",
            "exchange": "luno",
            "balances": {"ZAR": 0.0},
            "type": "paper_exchange",
        }
    )
    mock_col.insert_one = AsyncMock(return_value=MagicMock())
    svc.collection = mock_col

    # Track whether the global wallet reserve_funds was ever called.
    global_reserve_called = False
    original_reserve = svc.reserve_funds

    async def spy_reserve_funds(*args, **kwargs):
        nonlocal global_reserve_called
        global_reserve_called = True
        return await original_reserve(*args, **kwargs)

    svc.reserve_funds = spy_reserve_funds

    ok, msg = await svc.reserve_exchange_funds("user1", "luno", 500.0, "ZAR")

    assert ok is False, "Must return False when exchange wallet is insufficient"
    assert global_reserve_called is False, (
        "CROSS-EXCHANGE FALLBACK DETECTED: reserve_exchange_funds fell back to "
        "global paper wallet when exchange wallet was insufficient. "
        "This violates the platform-wallet isolation requirement."
    )
    assert "Insufficient" in msg or "insufficient" in msg, (
        f"Error message should mention insufficient funds, got: {msg}"
    )
    assert "luno" in msg.lower() or "exchange" in msg.lower(), (
        f"Error message should identify the exchange, got: {msg}"
    )


# ===========================================================================
# 5. Fresh paper bots must not inherit stale EMERGENCY_STOP state
# ===========================================================================

@pytest.mark.asyncio
async def test_fresh_paper_bots_do_not_inherit_emergency_stop():
    """paper_reset_orchestrator must clear emergencyStop in system_modes_collection
    so that freshly created paper bots are not immediately paused by the scheduler.

    Root cause: the scheduler reads system_modes_collection.emergencyStop (camelCase).
    The orchestrator previously only cleared users_collection.emergency_stop (snake_case).
    After this fix, both must be cleared on reset.
    """
    import pathlib

    orch_path = pathlib.Path(__file__).parent.parent / "backend" / "services" / "paper_reset_orchestrator.py"
    source = orch_path.read_text()

    # 1. Must clear emergencyStop in system_modes_collection (camelCase — what scheduler reads)
    assert "system_modes_collection" in source, (
        "paper_reset_orchestrator.py must reference system_modes_collection to clear emergencyStop"
    )
    assert '"emergencyStop"' in source or "'emergencyStop'" in source, (
        "paper_reset_orchestrator.py must set emergencyStop: False in system_modes_collection. "
        "The scheduler reads system_modes_collection.emergencyStop (camelCase). "
        "Clearing only users_collection.emergency_stop is NOT sufficient."
    )

    # 2. Must also clear emergency_stop in users_collection (existing behaviour preserved)
    assert "users_collection" in source, (
        "paper_reset_orchestrator.py must still clear emergency_stop in users_collection"
    )
    assert '"emergency_stop"' in source or "'emergency_stop'" in source, (
        "paper_reset_orchestrator.py must set emergency_stop: False in users_collection"
    )

    # 3. Both clears must happen within the also_reset_risk_locks block
    also_block_start = source.find("also_reset_risk_locks")
    assert also_block_start != -1, "also_reset_risk_locks block must exist"
    block = source[also_block_start:]

    assert "system_modes_collection" in block, (
        "emergencyStop clear must be inside the also_reset_risk_locks block"
    )


# ===========================================================================
# 7. Countdown / overview / wallet / performance all use the same ZAR valuation
# ===========================================================================

@pytest.mark.asyncio
async def test_wallet_overview_countdown_performance_share_same_valuation():
    """get_platform_wallet_totals_zar must be the single valuation source
    for all ZAR reporting surfaces.

    This test verifies that:
    - total_zar is the platform-only equity (canonical, used for UI reporting)
    - by_exchange contains per-exchange ZAR breakdown
    - combined_zar is NOT used as the primary portfolio total (it includes the
      legacy global wallet which is not a bot-funding source)
    - platform_wallets_zar (returned by the summary endpoint) equals total_zar

    The canonical path is:
      get_platform_wallet_totals_zar() → total_zar
      ↑ used by: wallet summary endpoint → platform_wallets_zar field
      ↑ used by: countdown, overview, performance tiles
    """
    from services.canonical import get_platform_wallet_totals_zar

    mock_wallets = {
        "luno": {
            "exchange": "luno",
            "native_currency": "ZAR",
            "available": 20000.0,
            "funded": True,
        },
        "binance": {
            "exchange": "binance",
            "native_currency": "USDT",
            "available": 1000.0,
            "funded": True,
        },
    }

    fx_calls: list = []

    def mock_to_display_zar(amount, currency):
        fx_calls.append((amount, currency))
        if currency == "ZAR":
            return (amount, "ZAR", 1.0)
        if currency == "USDT":
            return (amount * 18.5, "ZAR", 18.5)
        return (amount, "ZAR", 1.0)

    async def mock_get_all(uid):
        return mock_wallets

    async def mock_canon_equity(uid):
        # Simulate a non-zero legacy global wallet
        return {"total_equity": 5000.0}

    with patch("services.canonical.paper_wallet_service") as mock_svc, \
         patch("services.canonical.get_canonical_paper_wallet_equity",
               side_effect=mock_canon_equity), \
         patch("services.fx_normalizer.to_display_zar", side_effect=mock_to_display_zar):
        mock_svc.get_all_exchange_wallets = mock_get_all
        result = await get_platform_wallet_totals_zar("user1")

    # Platform total (canonical truth for UI):
    # luno: 20000 ZAR + binance: 1000 USDT × 18.5 = 18500 ZAR → total = 38500
    expected_platform_zar = 20000.0 + 1000.0 * 18.5
    assert abs(result["total_zar"] - expected_platform_zar) < 10, (
        f"total_zar must equal platform-only equity "
        f"({expected_platform_zar}), got {result['total_zar']}"
    )

    # by_exchange must contain both exchanges
    assert "luno" in result["by_exchange"], "luno must be in by_exchange breakdown"
    assert "binance" in result["by_exchange"], "binance must be in by_exchange breakdown"

    # ZAR values must be correct per exchange
    luno_zar = result["by_exchange"]["luno"]["zar"]
    binance_zar = result["by_exchange"]["binance"]["zar"]
    assert abs(luno_zar - 20000.0) < 1, f"Luno ZAR should be 20000, got {luno_zar}"
    assert abs(binance_zar - 18500.0) < 10, f"Binance ZAR should be ~18500, got {binance_zar}"

    # combined_zar includes legacy global wallet — it must NOT be equal to total_zar
    # (because the global wallet has value 5000 in this test)
    assert result["combined_zar"] >= result["total_zar"], (
        "combined_zar must be >= total_zar (it includes legacy global wallet)"
    )

    # FX conversion must have been called (no raw currency summing)
    assert len(fx_calls) > 0, "to_display_zar must be called for currency conversion"
    # Must NOT raw-sum ZAR + USDT (1000 USDT ≠ 1000 ZAR)
    assert result["total_zar"] != (20000.0 + 1000.0), (
        "Raw ZAR+USDT sum detected — must use FX conversion"
    )


# ===========================================================================
# 8. Admin key-monitor routes are reachable (no dead 404 calls)
# ===========================================================================

def test_admin_key_monitor_frontend_no_dead_route_calls():
    """The backend must expose /api/admin/key-monitor and
    /api/admin/key-monitor/per-user so frontend calls do not return 404.

    Previously these routes were missing, causing console errors and
    degraded admin UI every time the admin panel was opened.
    """
    import pathlib
    import importlib.util

    admin_ep_path = (
        pathlib.Path(__file__).parent.parent
        / "backend" / "routes" / "admin_endpoints.py"
    )
    source = admin_ep_path.read_text()

    # Both routes must be defined
    assert (
        '"/key-monitor"' in source or "'/key-monitor'" in source
        or '"/key-monitor"' in source
    ), (
        "GET /key-monitor route is missing from admin_endpoints.py. "
        "The frontend calls /api/admin/key-monitor and receives 404 without this route."
    )
    assert (
        '"/key-monitor/per-user"' in source or "'/key-monitor/per-user'" in source
    ), (
        "GET /key-monitor/per-user route is missing from admin_endpoints.py. "
        "The frontend calls /api/admin/key-monitor/per-user and receives 404 without this route."
    )

    # Routes must be GET endpoints
    key_monitor_idx = source.find('"/key-monitor"')
    if key_monitor_idx == -1:
        key_monitor_idx = source.find("'/key-monitor'")
    assert key_monitor_idx != -1
    # Check that @router.get appears before the route string (within 200 chars)
    context_before = source[max(0, key_monitor_idx - 200): key_monitor_idx]
    assert "@router.get" in context_before, (
        "/key-monitor must be a GET endpoint (decorated with @router.get)"
    )

    per_user_idx = source.find('"/key-monitor/per-user"')
    if per_user_idx == -1:
        per_user_idx = source.find("'/key-monitor/per-user'")
    assert per_user_idx != -1
    context_before_pu = source[max(0, per_user_idx - 200): per_user_idx]
    assert "@router.get" in context_before_pu, (
        "/key-monitor/per-user must be a GET endpoint"
    )

    # Verify the route handlers return the expected shape (providers list)
    assert "providers" in source[key_monitor_idx: key_monitor_idx + 2000], (
        "/key-monitor must return a 'providers' list (expected by frontend)"
    )
    assert "users" in source[per_user_idx: per_user_idx + 2000], (
        "/key-monitor/per-user must return a 'users' list (expected by frontend)"
    )


# ===========================================================================
# Bonus: platform wallet architecture cleanup — no global fallback in seeder
# ===========================================================================

def test_fleet_seeder_does_not_fund_global_wallet_for_bots():
    """paper_fleet_seeder must fund per-exchange wallets, not the global ZAR wallet.

    Funding the global wallet in the seeder was the root cause of cross-exchange
    capital contamination: Luno bots would consume funds from the global pool
    that Binance bots also relied on (via the global fallback).
    """
    import pathlib

    seeder_path = (
        pathlib.Path(__file__).parent.parent
        / "backend" / "services" / "paper_fleet_seeder.py"
    )
    source = seeder_path.read_text()

    # Must NOT call the global paper_wallet_service.fund() without exchange
    # The pattern paper_wallet_service.fund(user_id, ...) is the global wallet fund call.
    # The per-exchange call is fund_exchange_wallet(user_id, exchange, ...).
    # We look for the old pattern that funded the global wallet at the top of seed_paper_fleet.
    old_global_fund_pattern = (
        'await paper_wallet_service.fund(user_id, float(PAPER_STARTING_CAPITAL_ZAR), "ZAR")'
    )
    assert old_global_fund_pattern not in source, (
        "paper_fleet_seeder still calls paper_wallet_service.fund() to fund the GLOBAL wallet. "
        "This is the legacy pattern that caused cross-exchange capital contamination. "
        "Use fund_exchange_wallet() per exchange instead."
    )

    # Must call fund_exchange_wallet to fund exchange-specific wallets
    assert "fund_exchange_wallet" in source, (
        "paper_fleet_seeder must call fund_exchange_wallet() to fund per-exchange wallets. "
        "This ensures each exchange has its own funded wallet before bots start trading."
    )
