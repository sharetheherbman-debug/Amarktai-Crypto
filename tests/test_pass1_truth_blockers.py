"""
Pass 1 Go-Live Recovery — Truth Blocker Tests

Validates that active contradictions identified in the forensic,
gap-finding, and frontend audits have been resolved.

Run with:
  PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest tests/test_pass1_truth_blockers.py -v
"""

import os
import sys
import re
import pytest

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

# Ensure test-safe environment
os.environ.setdefault("ENVIRONMENT", "testing")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-testing-only")


# =====================================================================
# ENV VARIABLE NAME CONSISTENCY
# =====================================================================

class TestEnvVariableConsistency:
    """
    Canonical env variable names are:
      PAPER_TRADING, LIVE_TRADING, AUTOPILOT_ENABLED  (1/0 via env_bool)
    config package must resolve these (including legacy ENABLE_* aliases).
    """

    def test_config_exports_canonical_paper_trading(self):
        """config package must export PAPER_TRADING as a bool."""
        from config import PAPER_TRADING
        assert isinstance(PAPER_TRADING, bool)

    def test_config_exports_canonical_live_trading(self):
        from config import LIVE_TRADING
        assert isinstance(LIVE_TRADING, bool)

    def test_config_exports_canonical_autopilot_enabled(self):
        from config import AUTOPILOT_ENABLED
        assert isinstance(AUTOPILOT_ENABLED, bool)

    def test_config_backward_compat_aliases(self):
        """Legacy ENABLE_* names must resolve to the same value as canonical names."""
        from config import (
            PAPER_TRADING, LIVE_TRADING, AUTOPILOT_ENABLED,
            ENABLE_PAPER_TRADING, ENABLE_LIVE_TRADING, ENABLE_AUTOPILOT,
        )
        assert ENABLE_PAPER_TRADING == PAPER_TRADING
        assert ENABLE_LIVE_TRADING == LIVE_TRADING
        assert ENABLE_AUTOPILOT == AUTOPILOT_ENABLED

    def test_trading_gates_uses_canonical_names(self):
        """utils/trading_gates.py must read PAPER_TRADING and LIVE_TRADING."""
        gates_path = os.path.join(
            os.path.dirname(__file__), '..', 'backend', 'utils', 'trading_gates.py'
        )
        source = open(gates_path).read()
        assert "PAPER_TRADING" in source
        assert "LIVE_TRADING" in source

    def test_env_example_has_canonical_names(self):
        """backend/.env.example must define the canonical variable names."""
        env_path = os.path.join(
            os.path.dirname(__file__), '..', 'backend', '.env.example'
        )
        content = open(env_path).read()
        assert re.search(r'^PAPER_TRADING=', content, re.MULTILINE), \
            "PAPER_TRADING not found in backend/.env.example"
        assert re.search(r'^LIVE_TRADING=', content, re.MULTILINE), \
            "LIVE_TRADING not found in backend/.env.example"
        assert re.search(r'^AUTOPILOT_ENABLED=', content, re.MULTILINE), \
            "AUTOPILOT_ENABLED not found in backend/.env.example"

    def test_env_example_no_duplicate_live_trading(self):
        """backend/.env.example must NOT have a separate ENABLE_LIVE_TRADING line."""
        env_path = os.path.join(
            os.path.dirname(__file__), '..', 'backend', '.env.example'
        )
        content = open(env_path).read()
        matches = re.findall(r'^ENABLE_LIVE_TRADING=', content, re.MULTILINE)
        assert len(matches) == 0, \
            "ENABLE_LIVE_TRADING should not be in backend/.env.example (use LIVE_TRADING)"


# =====================================================================
# KEYS SERVICE PROVIDER COVERAGE (file-level inspection)
# =====================================================================

class TestKeysServiceProviders:
    """keys_service.SUPPORTED_PROVIDERS must cover all 11 providers."""

    EXPECTED_EXCHANGES = {'luno', 'binance', 'kucoin', 'bybit', 'bitget', 'kraken', 'gate'}
    EXPECTED_AI = {'openai', 'fetchai', 'coinstats', 'huggingface'}

    def _get_providers_from_source(self):
        """Parse SUPPORTED_PROVIDERS from source to avoid heavy imports."""
        path = os.path.join(
            os.path.dirname(__file__), '..', 'backend', 'services', 'keys_service.py'
        )
        content = open(path).read()
        # Find the SUPPORTED_PROVIDERS list literal
        match = re.search(
            r'SUPPORTED_PROVIDERS\s*=\s*\[(.*?)\]', content, re.DOTALL
        )
        assert match, "SUPPORTED_PROVIDERS not found in keys_service.py"
        providers_str = match.group(1)
        # Extract quoted strings
        providers = re.findall(r"'([^']+)'", providers_str)
        return set(providers)

    def test_keys_service_has_all_exchanges(self):
        providers = self._get_providers_from_source()
        missing = self.EXPECTED_EXCHANGES - providers
        assert len(missing) == 0, f"Missing exchange providers: {missing}"

    def test_keys_service_has_all_ai(self):
        providers = self._get_providers_from_source()
        missing = self.EXPECTED_AI - providers
        assert len(missing) == 0, f"Missing AI providers: {missing}"

    def test_keys_service_total_count(self):
        providers = self._get_providers_from_source()
        assert len(providers) == 11, \
            f"Expected 11 providers, got {len(providers)}: {providers}"


# =====================================================================
# SCHEDULER DIAGNOSTIC CORRECTNESS
# =====================================================================

class TestSchedulerDiagnostic:
    """Scheduler diagnostic must read is_running, not .running."""

    def test_trading_scheduler_has_is_running_in_source(self):
        """trading_scheduler.py must define self.is_running attribute."""
        path = os.path.join(
            os.path.dirname(__file__), '..', 'backend', 'trading_scheduler.py'
        )
        content = open(path).read()
        assert 'self.is_running' in content, \
            "TradingScheduler must have self.is_running attribute"

    def test_diagnostics_reads_is_running(self):
        """diagnostics.py paper-status must NOT use .get('running')."""
        diag_path = os.path.join(
            os.path.dirname(__file__), '..', 'backend', 'routes', 'diagnostics.py'
        )
        content = open(diag_path).read()
        # Should NOT have the old pattern
        assert "scheduler_status.get('running'" not in content, \
            "diagnostics.py still uses scheduler_status.get('running') — should use is_running"


# =====================================================================
# RESET ORCHESTRATION
# =====================================================================

class TestResetOrchestration:
    """admin_start_fresh must reset paper wallets and ledger entries."""

    def test_admin_start_fresh_resets_paper_wallet(self):
        """admin_start_fresh.py must contain paper wallet reset logic."""
        path = os.path.join(
            os.path.dirname(__file__), '..', 'backend', 'routes', 'admin_start_fresh.py'
        )
        content = open(path).read()
        assert 'paper_wallet' in content.lower(), \
            "admin_start_fresh.py must reset paper wallets"

    def test_admin_start_fresh_resets_ledger(self):
        """admin_start_fresh.py must contain ledger reset logic."""
        path = os.path.join(
            os.path.dirname(__file__), '..', 'backend', 'routes', 'admin_start_fresh.py'
        )
        content = open(path).read()
        assert 'ledger' in content.lower(), \
            "admin_start_fresh.py must reset ledger entries"


# =====================================================================
# JWT STARTUP VALIDATION (file-level inspection)
# =====================================================================

class TestJWTStartupValidation:
    """auth.py must refuse to start with placeholder JWT_SECRET."""

    def test_auth_has_validate_jwt_secret_function(self):
        """auth.py must define validate_jwt_secret."""
        path = os.path.join(
            os.path.dirname(__file__), '..', 'backend', 'auth.py'
        )
        content = open(path).read()
        assert 'def validate_jwt_secret' in content, \
            "auth.py must define validate_jwt_secret()"

    def test_auth_rejects_default_placeholders(self):
        """auth.py must list unsafe default JWT secrets."""
        path = os.path.join(
            os.path.dirname(__file__), '..', 'backend', 'auth.py'
        )
        content = open(path).read()
        assert 'your-secret-key' in content, \
            "auth.py must list 'your-secret-key' as unsafe"
        assert 'change-me' in content or 'changeme' in content, \
            "auth.py must list 'changeme' variants as unsafe"

    def test_auth_raises_runtime_error(self):
        """auth.py validate_jwt_secret must raise RuntimeError."""
        path = os.path.join(
            os.path.dirname(__file__), '..', 'backend', 'auth.py'
        )
        content = open(path).read()
        assert 'RuntimeError' in content, \
            "validate_jwt_secret must raise RuntimeError for unsafe secrets"


# =====================================================================
# BOT CONTROL ROUTE UNMOUNTED
# =====================================================================

class TestBotControlUnmounted:
    """bot_control.py must NOT be mounted (bot_lifecycle.py is canonical)."""

    def test_bot_control_not_in_router_list(self):
        """server.py router list must not include bot_control."""
        server_path = os.path.join(
            os.path.dirname(__file__), '..', 'backend', 'server.py'
        )
        content = open(server_path).read()
        # Look for active (uncommented) bot_control mount line
        for line in content.split('\n'):
            stripped = line.strip()
            if stripped.startswith('#'):
                continue
            if '"routes.bot_control"' in stripped or "'routes.bot_control'" in stripped:
                pytest.fail(
                    "routes.bot_control is still actively mounted in server.py. "
                    "It must be removed/commented — bot_lifecycle.py is canonical."
                )


# =====================================================================
# REPO TRUTH CONSISTENCY
# =====================================================================

class TestRepoTruth:
    """REPO_TRUTH.md must reflect canonical service name and paths."""

    def test_repo_truth_service_name(self):
        """REPO_TRUTH.md must reference amarktai-api.service."""
        path = os.path.join(
            os.path.dirname(__file__), '..', 'docs', 'REPO_TRUTH.md'
        )
        content = open(path).read()
        assert 'amarktai-api.service' in content, \
            "REPO_TRUTH.md must reference amarktai-api.service (not amarktai-backend.service)"

    def test_repo_truth_no_stale_service_name(self):
        """REPO_TRUTH.md must NOT reference stale amarktai-backend.service."""
        path = os.path.join(
            os.path.dirname(__file__), '..', 'docs', 'REPO_TRUTH.md'
        )
        content = open(path).read()
        assert 'amarktai-backend.service' not in content, \
            "REPO_TRUTH.md still references stale amarktai-backend.service"


# =====================================================================
# NEW DIAGNOSTIC ENDPOINTS EXIST
# =====================================================================

class TestDiagnosticEndpoints:
    """New diagnostic endpoints must be defined in diagnostics.py."""

    def _get_diagnostics_source(self):
        path = os.path.join(
            os.path.dirname(__file__), '..', 'backend', 'routes', 'diagnostics.py'
        )
        return open(path).read()

    def test_scheduler_health_endpoint_exists(self):
        src = self._get_diagnostics_source()
        assert '/scheduler-health' in src, \
            "Missing /api/diagnostics/scheduler-health endpoint"

    def test_reset_proof_endpoint_exists(self):
        src = self._get_diagnostics_source()
        assert '/reset-proof' in src, \
            "Missing /api/diagnostics/reset-proof endpoint"

    def test_paper_activity_endpoint_exists(self):
        src = self._get_diagnostics_source()
        assert '/paper-activity' in src, \
            "Missing /api/diagnostics/paper-activity endpoint"

    def test_risk_summary_endpoint_exists(self):
        """risk_management.py must have /api/risk/summary."""
        path = os.path.join(
            os.path.dirname(__file__), '..', 'backend', 'routes', 'risk_management.py'
        )
        content = open(path).read()
        assert '/api/risk/summary' in content, \
            "Missing /api/risk/summary endpoint"
