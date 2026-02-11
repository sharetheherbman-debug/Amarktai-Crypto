"""Tests for config export availability and router imports."""

import importlib
import os
import sys
from pathlib import Path

backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))


def test_config_exports_paper_starting_capital():
    from config import PAPER_STARTING_CAPITAL_ZAR

    expected = float(os.getenv("PAPER_STARTING_CAPITAL_ZAR", "30000"))
    assert isinstance(PAPER_STARTING_CAPITAL_ZAR, float)
    assert PAPER_STARTING_CAPITAL_ZAR == expected


def test_wallet_and_admin_routes_importable():
    wallet_module = importlib.import_module("routes.wallet_hub")
    admin_module = importlib.import_module("routes.admin_endpoints")

    assert getattr(wallet_module, "router", None) is not None
    assert getattr(admin_module, "router", None) is not None
