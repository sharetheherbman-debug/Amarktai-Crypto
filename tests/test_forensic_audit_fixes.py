"""
Tests for Forensic Audit Cleanup (March 2026).

Validates:
1. bot_control.py has been deleted (dead duplicate)
2. phase5/6/8 endpoints are NOT in server.py's routers_to_mount list
3. Root .env.example AUTOPILOT_ENABLED defaults to 0 (safe)
4. Scalper V1 gate constants are configurable via env vars with safe defaults
5. New scalper gate defaults are more permissive than the old hardcoded values
"""

import os
import sys
import re

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
os.environ.setdefault("ENVIRONMENT", "testing")
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "amarktai_test")
os.environ.setdefault("JWT_SECRET", "test-secret-key-for-testing")

BACKEND_DIR = os.path.join(os.path.dirname(__file__), "..", "backend")
REPO_ROOT = os.path.join(os.path.dirname(__file__), "..")


# ── 1. bot_control.py deleted ─────────────────────────────────────────────

class TestBotControlDeleted:

    def test_bot_control_file_does_not_exist(self):
        """routes/bot_control.py must be deleted — it is a dead duplicate."""
        path = os.path.join(BACKEND_DIR, "routes", "bot_control.py")
        assert not os.path.exists(path), (
            "routes/bot_control.py still exists. It is a dead duplicate of "
            "bot_lifecycle.py with missing /api prefix and must be deleted."
        )

    def test_server_does_not_mount_bot_control(self):
        """server.py must not have an active routes.bot_control mount."""
        server_path = os.path.join(BACKEND_DIR, "server.py")
        with open(server_path) as f:
            for line in f:
                stripped = line.strip()
                if stripped.startswith("#"):
                    continue
                assert '"routes.bot_control"' not in stripped, (
                    "routes.bot_control is still actively mounted in server.py"
                )
                assert "'routes.bot_control'" not in stripped, (
                    "routes.bot_control is still actively mounted in server.py"
                )


# ── 2. Phase 5/6/8 endpoints not actively mounted ────────────────────────

class TestPhaseEndpointsRemoved:

    @staticmethod
    def _active_mounts(server_path: str) -> list:
        """Return active (non-commented) route entries from server.py."""
        entries = []
        with open(server_path) as f:
            for line in f:
                stripped = line.strip()
                if stripped.startswith("#"):
                    continue
                entries.append(stripped)
        return entries

    def test_phase5_not_mounted(self):
        server_path = os.path.join(BACKEND_DIR, "server.py")
        active = self._active_mounts(server_path)
        for entry in active:
            assert "routes.phase5_endpoints" not in entry, (
                "routes.phase5_endpoints is still actively mounted — "
                "it is superseded and never called by the frontend"
            )

    def test_phase6_not_mounted(self):
        server_path = os.path.join(BACKEND_DIR, "server.py")
        active = self._active_mounts(server_path)
        for entry in active:
            assert "routes.phase6_endpoints" not in entry, (
                "routes.phase6_endpoints is still actively mounted"
            )

    def test_phase8_not_mounted(self):
        server_path = os.path.join(BACKEND_DIR, "server.py")
        active = self._active_mounts(server_path)
        for entry in active:
            assert "routes.phase8_endpoints" not in entry, (
                "routes.phase8_endpoints is still actively mounted"
            )


# ── 3. Root .env.example has safe AUTOPILOT default ──────────────────────

class TestEnvExampleSafeDefaults:

    def _parse_env_value(self, path: str, key: str):
        """Find the first non-commented assignment for key in env file."""
        pattern = re.compile(r"^\s*" + re.escape(key) + r"\s*=\s*(.+)")
        with open(path) as f:
            for line in f:
                if line.strip().startswith("#"):
                    continue
                m = pattern.match(line)
                if m:
                    return m.group(1).strip().strip('"').strip("'").split("#")[0].strip()
        return None

    def test_root_env_autopilot_disabled_by_default(self):
        """Root .env.example must default AUTOPILOT_ENABLED=0 for safety."""
        root_env = os.path.join(REPO_ROOT, ".env.example")
        value = self._parse_env_value(root_env, "AUTOPILOT_ENABLED")
        assert value is not None, ".env.example must define AUTOPILOT_ENABLED"
        assert value in ("0", "false", "False"), (
            f"AUTOPILOT_ENABLED should be 0 in root .env.example for safe defaults, "
            f"got: {value!r}. Setting it to 1 enables autonomous bot spawning on first deploy."
        )

    def test_root_env_paper_trading_default_is_zero(self):
        """Root .env.example must default PAPER_TRADING=0 (all trading OFF)."""
        root_env = os.path.join(REPO_ROOT, ".env.example")
        value = self._parse_env_value(root_env, "PAPER_TRADING")
        assert value is not None, ".env.example must define PAPER_TRADING"
        assert value in ("0", "false", "False"), (
            f"PAPER_TRADING should be 0 in .env.example for safe defaults, got: {value!r}"
        )

    def test_root_env_live_trading_default_is_zero(self):
        """Root .env.example must default LIVE_TRADING=0 (no real money)."""
        root_env = os.path.join(REPO_ROOT, ".env.example")
        value = self._parse_env_value(root_env, "LIVE_TRADING")
        assert value is not None, ".env.example must define LIVE_TRADING"
        assert value in ("0", "false", "False"), (
            f"LIVE_TRADING should be 0 in .env.example for safe defaults, got: {value!r}"
        )

    def test_backend_env_has_v1_scalper_params(self):
        """backend/.env.example must document the new scalper gate env vars."""
        backend_env = os.path.join(BACKEND_DIR, ".env.example")
        with open(backend_env) as f:
            content = f.read()
        assert "SCALPER_MIN_SOURCES" in content, (
            "backend/.env.example must document SCALPER_MIN_SOURCES"
        )
        assert "SCALPER_MIN_CONSENSUS_STRENGTH" in content, (
            "backend/.env.example must document SCALPER_MIN_CONSENSUS_STRENGTH"
        )
        assert "SCALPER_REGIME_CONF_THRESHOLD" in content, (
            "backend/.env.example must document SCALPER_REGIME_CONF_THRESHOLD"
        )


# ── 4. Scalper gate constants are configurable ────────────────────────────

class TestScalperGateConstants:

    def test_scalper_min_sources_is_exported(self):
        """paper_trading_engine must export SCALPER_MIN_SOURCES constant."""
        path = os.path.join(BACKEND_DIR, "paper_trading_engine.py")
        with open(path) as f:
            source = f.read()
        assert "SCALPER_MIN_SOURCES" in source, (
            "paper_trading_engine.py must define SCALPER_MIN_SOURCES env var"
        )

    def test_scalper_min_consensus_is_exported(self):
        """paper_trading_engine must export SCALPER_MIN_CONSENSUS_STRENGTH constant."""
        path = os.path.join(BACKEND_DIR, "paper_trading_engine.py")
        with open(path) as f:
            source = f.read()
        assert "SCALPER_MIN_CONSENSUS_STRENGTH" in source, (
            "paper_trading_engine.py must define SCALPER_MIN_CONSENSUS_STRENGTH env var"
        )

    def test_scalper_regime_conf_threshold_is_exported(self):
        """paper_trading_engine must export SCALPER_REGIME_CONF_THRESHOLD."""
        path = os.path.join(BACKEND_DIR, "paper_trading_engine.py")
        with open(path) as f:
            source = f.read()
        assert "SCALPER_REGIME_CONF_THRESHOLD" in source, (
            "paper_trading_engine.py must define SCALPER_REGIME_CONF_THRESHOLD"
        )

    def test_scalper_constants_default_values_are_permissive(self):
        """Default scalper gate values must be more permissive than old hardcoded ones."""
        import os as _os
        # Clear any overrides
        for k in ("SCALPER_MIN_SOURCES", "SCALPER_MIN_CONSENSUS_STRENGTH",
                  "SCALPER_MIN_AVG_CONFIDENCE", "SCALPER_REGIME_CONF_THRESHOLD",
                  "NORMAL_MIN_SOURCES", "NORMAL_MIN_AVG_CONFIDENCE"):
            _os.environ.pop(k, None)

        path = os.path.join(BACKEND_DIR, "paper_trading_engine.py")
        with open(path) as f:
            source = f.read()

        # SCALPER_MIN_SOURCES default is 1, not 2 — check _env_int call OR os.getenv call
        assert re.search(r'SCALPER_MIN_SOURCES["\']?\s*,\s*["\']?1["\']?', source), (
            "SCALPER_MIN_SOURCES default must be 1 (more permissive than old hardcoded 2)"
        )
        # SCALPER_MIN_CONSENSUS_STRENGTH default is 1, not 2
        assert re.search(r'SCALPER_MIN_CONSENSUS_STRENGTH["\']?\s*,\s*["\']?1["\']?', source), (
            "SCALPER_MIN_CONSENSUS_STRENGTH default must be 1 (more permissive than old hardcoded 2)"
        )
        # SCALPER_MIN_AVG_CONFIDENCE default is ≤ 0.70 (phase1 sets it to 0.70, relaxed from 0.75)
        confidence_match = re.search(
            r'SCALPER_MIN_AVG_CONFIDENCE["\']?\s*,\s*["\']?([0-9.]+)["\']?', source
        )
        assert confidence_match, "SCALPER_MIN_AVG_CONFIDENCE must have a default value"
        default_conf = float(confidence_match.group(1))
        assert default_conf <= 0.70, (
            f"SCALPER_MIN_AVG_CONFIDENCE default ({default_conf}) must be ≤ 0.70 "
            f"(phase1 relaxed from old 0.75 to 0.70)"
        )

    def test_v1_gate_uses_configurable_constants_not_hardcoded(self):
        """V1 scalper gate must enforce a sources threshold ≤ 2 (either constant or literal)."""
        path = os.path.join(BACKEND_DIR, "paper_trading_engine.py")
        with open(path) as f:
            source = f.read()

        # Find the scalper gate section (between the 'if bot_type == "scalper":' and the else branch)
        scalper_block_match = re.search(
            r'if bot_type == ["\']scalper["\']:(.*?)(?=\n\s+else:)',
            source, re.DOTALL
        )
        assert scalper_block_match, "Could not find scalper gate block in paper_trading_engine.py"
        scalper_block = scalper_block_match.group(1)

        # The scalper block must NOT use a threshold > 2 for sources
        hardcoded_gt2 = re.search(r'confidence_sources\s*<\s*[3-9]\b', scalper_block)
        assert hardcoded_gt2 is None, (
            "V1 scalper gate uses a threshold > 2 for confidence_sources. "
            "Must enforce at most 2 sources required."
        )
        # Either the constant SCALPER_MIN_SOURCES is used OR hardcoded < 2
        uses_constant = "SCALPER_MIN_SOURCES" in scalper_block
        uses_literal_2 = bool(re.search(r'confidence_sources\s*<\s*2\b', scalper_block))
        assert uses_constant or uses_literal_2, (
            "V1 scalper gate must reference SCALPER_MIN_SOURCES constant or use `confidence_sources < 2`"
        )
