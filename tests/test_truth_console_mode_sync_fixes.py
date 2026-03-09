"""
Regression checks for go-live truth sync fixes.

These are lightweight source-level checks so they stay stable in constrained
CI environments without requiring full service dependencies.
"""

import os


REPO_ROOT = os.path.join(os.path.dirname(__file__), "..")


def _read(rel_path: str) -> str:
    with open(os.path.join(REPO_ROOT, rel_path), "r", encoding="utf-8") as f:
        return f.read()


def test_truth_kernel_exchange_health_uses_canonical_key_fields():
    src = _read("backend/services/truth_kernel.py")
    assert "api_key_encrypted" in src
    assert "last_test_error" in src
    assert "configured_valid" in src


def test_dashboard_overview_uses_system_mode_canonical_source():
    src = _read("backend/routes/dashboard_overview.py")
    assert "from routes.system_mode import get_system_mode" in src
    assert "canonical_mode = await get_system_mode(user_id)" in src
    assert '"autopilot": bool(canonical_mode.get("autopilot", False))' in src


def test_auth_me_exposes_canonical_mode_fields():
    src = _read("backend/routes/auth.py")
    assert 'sanitized_user["trading_mode"] = trading_mode' in src
    assert 'sanitized_user["autonomy"] = autopilot' in src
    assert 'sanitized_user["paperTrading"] = paper_trading' in src


def test_truth_console_has_market_data_key_bucket():
    src = _read("frontend/src/pages/dashboard/sections/TruthConsoleSection.js")
    assert "MARKET_DATA_IDS" in src
    assert "marketData" in src
    assert "📈 Market Data Keys" in src
