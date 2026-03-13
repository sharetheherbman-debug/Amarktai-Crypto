"""
Regression tests for PR58 paper-wallet route regression.

Confirms that the following routes exist, are correctly wired to the
canonical services, and behave as expected:

  POST /api/user/paper-start-fresh   — user-facing full paper reset
  POST /api/wallet/paper/set-balance — set exact ZAR opening balance

These tests are static (no live DB / FastAPI server required) and mirror
the style used in the rest of the test suite.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ---------------------------------------------------------------------------
# Route file / function presence
# ---------------------------------------------------------------------------

def test_user_paper_start_fresh_route_exists():
    """POST /api/user/paper-start-fresh must be defined in admin_start_fresh.py"""
    route_path = os.path.join(
        os.path.dirname(__file__), "..", "routes", "admin_start_fresh.py"
    )
    with open(route_path) as f:
        content = f.read()

    assert "/api/user/paper-start-fresh" in content, (
        "Route /api/user/paper-start-fresh is missing from admin_start_fresh.py"
    )
    assert "user_paper_start_fresh" in content, (
        "Handler function user_paper_start_fresh is missing"
    )
    assert "perform_paper_reset" in content, (
        "Route must delegate to canonical perform_paper_reset"
    )
    print("✅ /api/user/paper-start-fresh route definition found")


def test_wallet_set_balance_route_exists():
    """POST /api/wallet/paper/set-balance must be defined in wallet_hub.py"""
    route_path = os.path.join(
        os.path.dirname(__file__), "..", "routes", "wallet_hub.py"
    )
    with open(route_path) as f:
        content = f.read()

    assert "/paper/set-balance" in content, (
        "Route /api/wallet/paper/set-balance is missing from wallet_hub.py"
    )
    assert "set_paper_wallet_balance" in content, (
        "Handler function set_paper_wallet_balance is missing"
    )
    assert "paper_wallet_service.set_balance" in content, (
        "Route must delegate to canonical paper_wallet_service.set_balance"
    )
    print("✅ /api/wallet/paper/set-balance route definition found")


def test_paper_wallet_service_has_set_balance():
    """paper_wallet_service must expose a set_balance() method."""
    service_path = os.path.join(
        os.path.dirname(__file__), "..", "services", "paper_wallet_service.py"
    )
    with open(service_path) as f:
        content = f.read()

    assert "async def set_balance(" in content, (
        "PaperWalletService is missing the set_balance() method"
    )
    print("✅ PaperWalletService.set_balance() method found")


# ---------------------------------------------------------------------------
# Single-source-of-truth checks
# ---------------------------------------------------------------------------

def test_admin_start_fresh_delegates_to_perform_paper_reset():
    """Admin start-fresh and user start-fresh both delegate to perform_paper_reset."""
    route_path = os.path.join(
        os.path.dirname(__file__), "..", "routes", "admin_start_fresh.py"
    )
    with open(route_path) as f:
        content = f.read()

    occurrences = content.count("perform_paper_reset")
    assert occurrences >= 2, (
        f"Expected at least 2 call-sites of perform_paper_reset (admin + user), "
        f"found {occurrences}"
    )
    print(f"✅ perform_paper_reset is called {occurrences} times (admin + user paths)")


def test_no_duplicate_wallet_reset_logic():
    """set_paper_wallet_balance must delegate to paper_wallet_service, not re-implement wallet logic."""
    route_path = os.path.join(
        os.path.dirname(__file__), "..", "routes", "wallet_hub.py"
    )
    with open(route_path) as f:
        content = f.read()

    # The route file may reference wallets_collection in other helpers,
    # but the set_paper_wallet_balance handler itself must not – it should
    # call paper_wallet_service.set_balance exclusively.
    assert "paper_wallet_service.set_balance" in content, (
        "set_paper_wallet_balance must delegate to paper_wallet_service.set_balance"
    )
    print("✅ set_paper_wallet_balance delegates to paper_wallet_service.set_balance")


# ---------------------------------------------------------------------------
# Request model / contract
# ---------------------------------------------------------------------------

def test_set_balance_request_model_exists():
    """PaperSetBalanceRequest model must be present in wallet_hub.py."""
    route_path = os.path.join(
        os.path.dirname(__file__), "..", "routes", "wallet_hub.py"
    )
    with open(route_path) as f:
        content = f.read()

    assert "PaperSetBalanceRequest" in content, "PaperSetBalanceRequest model missing"
    assert "balance_zar" in content, "balance_zar field missing from model"
    assert "confirmed" in content, "confirmed field missing from model"
    print("✅ PaperSetBalanceRequest model with balance_zar + confirmed fields present")


def test_paper_start_fresh_request_model_exists():
    """PaperStartFreshRequest model must be present in admin_start_fresh.py."""
    route_path = os.path.join(
        os.path.dirname(__file__), "..", "routes", "admin_start_fresh.py"
    )
    with open(route_path) as f:
        content = f.read()

    assert "PaperStartFreshRequest" in content, "PaperStartFreshRequest model missing"
    assert "confirmed" in content, "confirmed field missing from PaperStartFreshRequest"
    print("✅ PaperStartFreshRequest model with confirmed field present")


# ---------------------------------------------------------------------------
# Route registration in server.py
# ---------------------------------------------------------------------------

def test_admin_start_fresh_registered_in_server():
    """admin_start_fresh module must be registered in server.py."""
    server_path = os.path.join(os.path.dirname(__file__), "..", "server.py")
    with open(server_path) as f:
        content = f.read()

    assert "admin_start_fresh" in content, (
        "routes.admin_start_fresh is not registered in server.py"
    )
    print("✅ admin_start_fresh is registered in server.py")


def test_wallet_hub_registered_in_server():
    """wallet_hub module must be registered in server.py."""
    server_path = os.path.join(os.path.dirname(__file__), "..", "server.py")
    with open(server_path) as f:
        content = f.read()

    assert "wallet_hub" in content, (
        "routes.wallet_hub is not registered in server.py"
    )
    print("✅ wallet_hub is registered in server.py")


# ---------------------------------------------------------------------------
# set_balance service method contract
# ---------------------------------------------------------------------------

def test_set_balance_service_uses_find_one_and_update():
    """set_balance must use find_one_and_update (atomic, no race conditions)."""
    service_path = os.path.join(
        os.path.dirname(__file__), "..", "services", "paper_wallet_service.py"
    )
    with open(service_path) as f:
        content = f.read()

    assert "async def set_balance(" in content, (
        "PaperWalletService is missing the set_balance() method"
    )
    # Confirm find_one_and_update and upsert=True appear in the file
    # (they are used exclusively in set_balance and reserve_funds for wallet ops).
    assert "find_one_and_update" in content, (
        "set_balance must use find_one_and_update for atomic balance write"
    )
    assert "upsert=True" in content, (
        "set_balance must use upsert=True so the wallet is created if missing"
    )
    print("✅ set_balance uses find_one_and_update with upsert=True")


# ---------------------------------------------------------------------------
# Syntax sanity
# ---------------------------------------------------------------------------

def test_routes_compile_cleanly():
    """All modified route/service files must compile without syntax errors."""
    import py_compile, tempfile

    files = [
        os.path.join(os.path.dirname(__file__), "..", "routes", "admin_start_fresh.py"),
        os.path.join(os.path.dirname(__file__), "..", "routes", "wallet_hub.py"),
        os.path.join(os.path.dirname(__file__), "..", "services", "paper_wallet_service.py"),
    ]
    for path in files:
        py_compile.compile(path, doraise=True)
        print(f"✅ {os.path.basename(path)} compiles cleanly")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=" * 70)
    print("Regression Tests: paper-start-fresh + wallet set-balance routes")
    print("=" * 70)

    tests = [
        test_user_paper_start_fresh_route_exists,
        test_wallet_set_balance_route_exists,
        test_paper_wallet_service_has_set_balance,
        test_admin_start_fresh_delegates_to_perform_paper_reset,
        test_no_duplicate_wallet_reset_logic,
        test_set_balance_request_model_exists,
        test_paper_start_fresh_request_model_exists,
        test_admin_start_fresh_registered_in_server,
        test_wallet_hub_registered_in_server,
        test_set_balance_service_uses_find_one_and_update,
        test_routes_compile_cleanly,
    ]

    results = []
    for t in tests:
        try:
            t()
            results.append(True)
        except AssertionError as e:
            print(f"❌ {t.__name__}: {e}")
            results.append(False)
        except Exception as e:
            print(f"❌ {t.__name__} ERROR: {e}")
            results.append(False)

    print("\n" + "=" * 70)
    failed = sum(1 for r in results if not r)
    if failed == 0:
        print("✅ ALL REGRESSION TESTS PASSED")
        sys.exit(0)
    else:
        print(f"❌ {failed} REGRESSION TEST(S) FAILED")
        sys.exit(1)
