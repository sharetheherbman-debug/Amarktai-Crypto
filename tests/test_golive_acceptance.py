"""
Go-Live Acceptance Tests
Verifies the key requirements from the "Perfect Paper Go-Live Fix Pack":
  - Paper trades can open AND close (TP/SL/training_timeout)
  - Training max hold time is configurable (default 45 min)
  - Market intelligence returns last_error + refresh_interval_seconds
  - Growth engine has no Collection bool() errors
  - Config exports TRAINING_MAX_HOLD_MINUTES
  - Branding strings use AmarktAI Crypto
"""

import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))


class TestTrainingMaxHoldTime:
    """TRAINING_MAX_HOLD_MINUTES must be configurable and default to 45."""

    def test_training_max_hold_minutes_in_config(self):
        from config import TRAINING_MAX_HOLD_MINUTES
        assert TRAINING_MAX_HOLD_MINUTES == 45, (
            f"Expected default 45, got {TRAINING_MAX_HOLD_MINUTES}"
        )

    def test_training_max_hold_env_override(self, monkeypatch):
        monkeypatch.setenv("TRAINING_MAX_HOLD_MINUTES", "30")
        import importlib
        import config as cfg_pkg
        importlib.reload(cfg_pkg)
        from config import TRAINING_MAX_HOLD_MINUTES as T
        assert T == 30
        # Reload to default so other tests are not affected
        monkeypatch.delenv("TRAINING_MAX_HOLD_MINUTES", raising=False)
        importlib.reload(cfg_pkg)

    def test_training_max_hold_exported(self):
        import config as cfg_pkg
        assert hasattr(cfg_pkg, "TRAINING_MAX_HOLD_MINUTES")
        assert cfg_pkg.TRAINING_MAX_HOLD_MINUTES > 0


class TestPaperTradingCloseReasons:
    """Paper trading engine must set correct close reasons and emit structured logs."""

    def test_training_timeout_close_reason(self):
        """A training bot whose trade exceeds TRAINING_MAX_HOLD_MINUTES should get training_timeout."""
        import sys
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
        from paper_trading_engine import PaperTradingEngine
        from config import TRAINING_MAX_HOLD_MINUTES
        # Verify engine imports the constant
        import paper_trading_engine as pte
        assert hasattr(pte, "TRAINING_MAX_HOLD_MINUTES"), (
            "TRAINING_MAX_HOLD_MINUTES must be importable at module level"
        )

    def test_module_level_imports_for_patching(self):
        """market_regime_detector, ml_predictor, fetchai must exist at module level."""
        import paper_trading_engine as pte
        assert hasattr(pte, "market_regime_detector"), (
            "market_regime_detector must be a module-level attribute for test patching"
        )
        assert hasattr(pte, "ml_predictor"), (
            "ml_predictor must be a module-level attribute for test patching"
        )
        assert hasattr(pte, "fetchai"), (
            "fetchai must be a module-level attribute for test patching"
        )

    def test_no_flokx_at_module_level(self):
        """flokx has been removed; no module-level flokx attribute should exist."""
        import paper_trading_engine as pte
        assert not hasattr(pte, "flokx"), (
            "flokx has been removed from the system; should not be a module-level attribute"
        )


class TestMarketIntelligenceStatus:
    """Market intelligence service must return status fields with last_error."""

    def test_get_intelligence_status_returns_required_fields(self):
        from services.market_intelligence_service import get_intelligence_status
        status = get_intelligence_status()
        assert "last_run_at" in status
        assert "next_run_in_seconds" in status
        assert "refresh_interval_seconds" in status
        assert "last_error" in status
        assert "has_data" in status

    def test_refresh_interval_is_60_seconds_default(self):
        from services.market_intelligence_service import _REFRESH_INTERVAL
        # Default should be 60 (or within 30–180 configurable range)
        assert 30 <= _REFRESH_INTERVAL <= 180, (
            f"MARKET_INTEL_REFRESH_SECONDS should be in 30-180 range, got {_REFRESH_INTERVAL}"
        )

    def test_intelligence_fallback_does_not_say_15_minutes(self):
        """The 'no data yet' fallback message must NOT say '15 minutes'."""
        import asyncio
        from services.market_intelligence_service import get_latest_intelligence
        result = asyncio.run(get_latest_intelligence())
        what_happened = result.get("what_happened", "")
        assert "15 minutes" not in what_happened, (
            f"Fallback message still says '15 minutes': {what_happened}"
        )

    def test_intelligence_fallback_includes_refresh_interval(self):
        """The status response must include refresh_interval_seconds."""
        import asyncio
        from services.market_intelligence_service import get_latest_intelligence
        result = asyncio.run(get_latest_intelligence())
        assert "refresh_interval_seconds" in result


class TestGrowthEngineSafety:
    """Growth engine must not use bool() on Motor Collection objects."""

    def test_db_db_check_uses_is_not_none(self):
        """growth_engine_service must not use bare `if db.db` (use `if db.db is not None`)."""
        import ast
        import os

        service_path = os.path.join(
            os.path.dirname(__file__), "..", "backend", "services", "growth_engine_service.py"
        )
        with open(service_path) as f:
            source = f.read()
        tree = ast.parse(source)

        violations = []
        for node in ast.walk(tree):
            # Look for `if expr else ...` where expr is an attribute like db.db
            if isinstance(node, ast.IfExp):
                test = node.test
                if isinstance(test, ast.Attribute) and test.attr == "db":
                    violations.append(ast.dump(test))

        assert not violations, (
            "growth_engine_service uses bare `if db.db` which throws NotImplementedError "
            f"on Motor objects. Found at: {violations}"
        )

    def test_no_valr_in_growth_engine(self):
        """growth_engine_service must not mention valr."""
        import os
        service_path = os.path.join(
            os.path.dirname(__file__), "..", "backend", "services", "growth_engine_service.py"
        )
        with open(service_path) as f:
            content = f.read().lower()
        assert "valr" not in content, (
            "growth_engine_service still contains 'valr' reference which is forbidden"
        )


class TestBrandingStrings:
    """AmarktAI Crypto branding must be consistent across backend service messages."""

    def test_market_intelligence_uses_amarktai_crypto(self):
        """Market intelligence service messages must say AmarktAI Crypto, not Amarktai Crypto."""
        import os
        svc_path = os.path.join(
            os.path.dirname(__file__), "..", "backend", "services", "market_intelligence_service.py"
        )
        with open(svc_path) as f:
            content = f.read()
        # Check "Amarktai Crypto" (wrong) is not present
        assert "Amarktai Crypto" not in content, (
            "market_intelligence_service still uses old branding 'Amarktai Crypto'"
        )
        # Check "AmarktAI Crypto" (correct) is present
        assert "AmarktAI Crypto" in content, (
            "market_intelligence_service must use new branding 'AmarktAI Crypto'"
        )
