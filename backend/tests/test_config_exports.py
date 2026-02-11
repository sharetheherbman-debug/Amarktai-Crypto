"""Tests for config export availability and router imports."""

import importlib
import sys
from pathlib import Path

backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))


def test_config_exports_paper_starting_capital():
    from config import PAPER_STARTING_CAPITAL_ZAR

    assert isinstance(PAPER_STARTING_CAPITAL_ZAR, float)


def test_wallet_and_admin_routes_importable():
    importlib.import_module("routes.wallet_hub")
    importlib.import_module("routes.admin_endpoints")
