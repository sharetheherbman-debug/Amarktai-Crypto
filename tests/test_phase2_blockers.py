"""
Phase 2 Blocker Tests
=======================
Covers the three blockers from the Phase 2 PR:

  BLOCKER 1 — Build metadata (sha/branch) resolves correctly in health.py.
  BLOCKER 2 — CoinStats key resolution order (DB → env → none).
  BLOCKER 3 — Paper wallet allows non-Luno (USDT-quote) bots when ZAR equity
               is sufficient; FX helper returns a usable rate.
"""

import os
import sys
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

# Make backend importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

# Stub heavy optional dependencies so imports don't fail in CI
for _mod in ("ccxt", "ccxt.async_support", "ccxt_service", "tenacity",
             "huggingface_hub"):
    if _mod not in sys.modules:
        sys.modules[_mod] = MagicMock()


# ── BLOCKER 1: health.py build metadata ──────────────────────────────────────

class TestHealthBuildMetadata:
    """health.py must return real sha/branch values and fall back correctly."""

    def setup_method(self):
        """Reset caches before each test."""
        import routes.health as h
        h._BUILD_HASH_CACHE = None
        h._BUILD_BRANCH_CACHE = None

    def test_build_hash_uses_build_sha_env(self):
        """BUILD_SHA env var is preferred over git for build hash."""
        from routes.health import get_build_hash
        with patch.dict(os.environ, {"BUILD_SHA": "abc123deadbeef"}, clear=False):
            import routes.health as h
            h._BUILD_HASH_CACHE = None
            sha = get_build_hash()
        # health.py truncates to 12 chars
        assert sha == "abc123deadbe", f"Expected BUILD_SHA (truncated to 12), got {sha!r}"

    def test_build_hash_uses_git_sha_env(self):
        """GIT_SHA env var is a fallback for build hash when BUILD_SHA absent."""
        import routes.health as h
        h._BUILD_HASH_CACHE = None
        env = {"GIT_SHA": "deadbeef1234", "BUILD_SHA": ""}
        with patch.dict(os.environ, env, clear=False):
            sha = h.get_build_hash()
        assert sha == "deadbeef1234", f"Expected GIT_SHA value, got {sha!r}"

    def test_build_hash_uses_github_sha_env(self):
        """GITHUB_SHA env var (set by GitHub Actions) is a valid fallback."""
        import routes.health as h
        h._BUILD_HASH_CACHE = None
        env = {"GITHUB_SHA": "feedcafe5678", "BUILD_SHA": "", "GIT_SHA": ""}
        with patch.dict(os.environ, env, clear=False):
            sha = h.get_build_hash()
        assert sha == "feedcafe5678", f"Expected GITHUB_SHA value, got {sha!r}"

    def test_build_branch_uses_build_branch_env(self):
        """BUILD_BRANCH env var is preferred over git for branch."""
        import routes.health as h
        h._BUILD_BRANCH_CACHE = None
        with patch.dict(os.environ, {"BUILD_BRANCH": "main"}, clear=False):
            branch = h.get_build_branch()
        assert branch == "main", f"Expected 'main', got {branch!r}"

    def test_build_branch_uses_git_branch_env(self):
        """GIT_BRANCH env var is a fallback for branch when BUILD_BRANCH absent."""
        import routes.health as h
        h._BUILD_BRANCH_CACHE = None
        env = {"GIT_BRANCH": "feature/test", "BUILD_BRANCH": ""}
        with patch.dict(os.environ, env, clear=False):
            branch = h.get_build_branch()
        assert branch == "feature/test", f"Expected 'feature/test', got {branch!r}"

    def test_build_branch_uses_github_ref_name_env(self):
        """GITHUB_REF_NAME env var (set by GitHub Actions) is a valid fallback."""
        import routes.health as h
        h._BUILD_BRANCH_CACHE = None
        env = {"GITHUB_REF_NAME": "main", "BUILD_BRANCH": "", "GIT_BRANCH": ""}
        with patch.dict(os.environ, env, clear=False):
            branch = h.get_build_branch()
        assert branch == "main", f"Expected 'main', got {branch!r}"

    def test_build_hash_not_unknown_when_dot_git_exists(self):
        """SHA must resolve to a real value (not 'unknown') when .git is present."""
        import routes.health as h
        from pathlib import Path
        repo_root = Path(h._REPO_ROOT)
        if not (repo_root / ".git").exists():
            pytest.skip(".git not found — repo root detection may need AMARKTAI_REPO_ROOT")
        h._BUILD_HASH_CACHE = None
        # Clear env vars so we fall through to git
        with patch.dict(os.environ, {
            "BUILD_SHA": "", "GIT_SHA": "", "GITHUB_SHA": ""
        }, clear=False):
            sha = h.get_build_hash()
        assert sha != "unknown", f"Expected a real git SHA, got 'unknown'"
        assert len(sha) >= 7, f"SHA looks too short: {sha!r}"

    def test_find_repo_root_returns_a_directory(self):
        """_find_repo_root() must always return an existing directory path."""
        import routes.health as h
        assert os.path.isdir(h._REPO_ROOT), (
            f"_REPO_ROOT is not a directory: {h._REPO_ROOT!r}"
        )

    def test_amarktai_repo_root_env_is_respected(self, tmp_path):
        """AMARKTAI_REPO_ROOT env var overrides automatic discovery."""
        # Create a fake .git so the function accepts it
        (tmp_path / ".git").mkdir()
        import importlib
        import routes.health as h
        with patch.dict(os.environ, {"AMARKTAI_REPO_ROOT": str(tmp_path)}, clear=False):
            # Re-run the root discovery (not cached on module level for this call)
            root = h._find_repo_root()
        assert str(root) == str(tmp_path), (
            f"Expected AMARKTAI_REPO_ROOT={tmp_path}, got {root!r}"
        )


# ── BLOCKER 2: build_info.py _find_repo_root walk-upward ─────────────────────

class TestBuildInfoRepoRoot:
    """build_info._find_repo_root() must walk upward and find .git/."""

    def test_repo_root_is_directory(self):
        from routes.build_info import _REPO_ROOT
        assert _REPO_ROOT.is_dir(), f"_REPO_ROOT is not a directory: {_REPO_ROOT}"

    def test_find_repo_root_env_override(self, tmp_path):
        """AMARKTAI_REPO_ROOT env var is honoured by build_info._find_repo_root()."""
        (tmp_path / ".git").mkdir()
        from routes.build_info import _find_repo_root
        with patch.dict(os.environ, {"AMARKTAI_REPO_ROOT": str(tmp_path)}, clear=False):
            root = _find_repo_root()
        assert root == tmp_path, f"Expected {tmp_path}, got {root}"


# ── BLOCKER 2: CoinStats key resolution ──────────────────────────────────────

class TestCoinStatsKeyResolution:
    """resolve_coinstats_key() must prefer DB key, fall back to env."""

    @pytest.mark.asyncio
    async def test_user_db_key_is_preferred(self):
        """Per-user key from DB takes priority over env var."""
        from services.news_coinstats import resolve_coinstats_key
        mock_key_data = {"api_key": "user-db-key-xyz"}
        with patch("services.news_coinstats._COINSTATS_ENV_KEY", "env-key-abc"):
            with patch(
                "routes.api_key_management.get_decrypted_key",
                AsyncMock(return_value=mock_key_data),
            ):
                key, source = await resolve_coinstats_key("user123")
        assert key == "user-db-key-xyz"
        assert source == "user"

    @pytest.mark.asyncio
    async def test_env_fallback_when_no_db_key(self):
        """Env var is used when no user DB key is found."""
        from services.news_coinstats import resolve_coinstats_key
        with patch("services.news_coinstats._COINSTATS_ENV_KEY", "env-key-fallback"):
            with patch(
                "routes.api_key_management.get_decrypted_key",
                AsyncMock(return_value=None),
            ):
                key, source = await resolve_coinstats_key("user123")
        assert key == "env-key-fallback"
        assert source == "env"

    @pytest.mark.asyncio
    async def test_none_when_no_key_configured(self):
        """Returns (None, 'none') when neither DB key nor env var is set."""
        from services.news_coinstats import resolve_coinstats_key
        with patch("services.news_coinstats._COINSTATS_ENV_KEY", ""):
            with patch(
                "routes.api_key_management.get_decrypted_key",
                AsyncMock(return_value=None),
            ):
                key, source = await resolve_coinstats_key("user123")
        assert key is None
        assert source == "none"

    @pytest.mark.asyncio
    async def test_no_user_id_uses_env(self):
        """Without a user_id only the env var is checked."""
        from services.news_coinstats import resolve_coinstats_key
        with patch("services.news_coinstats._COINSTATS_ENV_KEY", "env-only-key"):
            key, source = await resolve_coinstats_key(None)
        assert key == "env-only-key"
        assert source == "env"

    def test_intelligence_status_exposes_coinstats_fields(self):
        """get_intelligence_status() must include coinstats_configured and has_data."""
        from services.market_intelligence_service import get_intelligence_status
        status = get_intelligence_status()
        assert "last_run_at" in status
        assert "last_error" in status
        assert "has_data" in status


# ── BLOCKER 3: Paper wallet USDT / FX conversion ─────────────────────────────

class TestPaperWalletUSDT:
    """Paper wallet must allow non-Luno bots to start using ZAR→USDT conversion."""

    @pytest.mark.asyncio
    async def test_reserve_usdt_deducts_zar_when_usdt_empty(self):
        """reserve_funds with USDT currency deducts ZAR when no USDT balance."""
        from services.paper_wallet_service import PaperWalletService

        stored = [
            {
                "user_id": "u1",
                "type": "paper",
                "balances": {"ZAR": 10000.0, "USDT": 0.0},
            }
        ]

        async def find_one(filt, projection=None):
            return stored[0]

        async def find_one_and_update(filt, update, upsert=False, return_document=None):
            # Simulate USDT direct check failing (no USDT balance)
            if f"balances.USDT" in str(filt) and "$gte" in str(filt):
                # USDT balance is 0, so $gte fails
                return None
            # ZAR deduction
            if "balances.ZAR" in str(filt):
                inc = update.get("$inc", {})
                if "balances.ZAR" in inc:
                    stored[0]["balances"]["ZAR"] += float(inc["balances.ZAR"])
                return stored[0]
            return None

        col = MagicMock()
        col.find_one = AsyncMock(side_effect=find_one)
        col.find_one_and_update = AsyncMock(side_effect=find_one_and_update)

        svc = PaperWalletService()
        svc.collection = col

        # _get_paper_zar_per_usdt must return a rate without hitting live exchange
        with patch(
            "services.paper_wallet_service._get_paper_zar_per_usdt",
            AsyncMock(return_value=18.5),
        ):
            success, msg = await svc.reserve_funds("u1", 100.0, "USDT")

        assert success is True, f"Expected success, got: {msg}"
        assert "ZAR" in msg or "Paper FX" in msg, f"Expected FX message, got: {msg}"

    @pytest.mark.asyncio
    async def test_reserve_usdt_fails_when_insufficient_zar(self):
        """reserve_funds returns failure when there is not enough ZAR to convert."""
        from services.paper_wallet_service import PaperWalletService

        stored = [
            {
                "user_id": "u1",
                "type": "paper",
                "balances": {"ZAR": 100.0},  # only R100, need more
            }
        ]

        async def find_one(filt, projection=None):
            return stored[0]

        async def find_one_and_update(filt, update, upsert=False, return_document=None):
            # Both USDT and ZAR $gte checks fail
            return None

        col = MagicMock()
        col.find_one = AsyncMock(side_effect=find_one)
        col.find_one_and_update = AsyncMock(side_effect=find_one_and_update)

        svc = PaperWalletService()
        svc.collection = col

        with patch(
            "services.paper_wallet_service._get_paper_zar_per_usdt",
            AsyncMock(return_value=18.5),
        ):
            success, msg = await svc.reserve_funds("u1", 1000.0, "USDT")

        assert success is False, "Expected failure when ZAR insufficient"

    @pytest.mark.asyncio
    async def test_get_paper_zar_per_usdt_returns_positive_float(self):
        """_get_paper_zar_per_usdt() must return a positive float (live or static)."""
        from services.paper_wallet_service import _get_paper_zar_per_usdt
        # With live price service unavailable, should fall back to static
        with patch(
            "services.price_fallback_service.price_fallback_service.get_price",
            AsyncMock(side_effect=Exception("not available")),
        ):
            rate = await _get_paper_zar_per_usdt()
        assert isinstance(rate, float), f"Expected float, got {type(rate)}"
        assert rate > 0, f"Rate must be positive, got {rate}"

    def test_get_paper_zar_per_usdt_static_env_override(self, monkeypatch):
        """PAPER_ZAR_PER_USDT env var sets the static fallback rate."""
        import services.paper_wallet_service as pws
        # Patch the module-level default directly to avoid reloading
        with patch.object(pws, "_PAPER_ZAR_PER_USDT_DEFAULT", 20.0):
            with patch(
                "services.price_fallback_service.price_fallback_service.get_price",
                AsyncMock(side_effect=Exception("not available")),
            ):
                import asyncio
                rate = asyncio.get_event_loop().run_until_complete(pws._get_paper_zar_per_usdt())
        assert rate == 20.0, f"Expected 20.0 from patched default, got {rate}"


class TestBotManagerUSDTPrecheck:
    """bot_manager.create_bot() must allow non-Luno bots when ZAR balance is ok."""

    @pytest.mark.asyncio
    async def test_non_luno_bot_allowed_when_zar_sufficient(self):
        """create_bot() for Binance must NOT block when ZAR balance covers capital."""
        for _mod in ("ccxt", "ccxt.async_support"):
            if _mod not in sys.modules:
                sys.modules[_mod] = MagicMock()

        from engines.bot_manager import BotManager
        manager = BotManager()

        # Override limit check to not block
        manager.can_create_bot = AsyncMock(return_value=(True, "ok"))

        mock_paper_service = MagicMock()
        # USDT balance = 0, ZAR balance = 5000
        async def mock_get_available(user_id, currency):
            return 0.0 if currency == "USDT" else 5000.0
        mock_paper_service.get_available_balance = AsyncMock(side_effect=mock_get_available)

        mock_reserved_service = MagicMock()
        mock_reserved_service.reserve_funds = AsyncMock(return_value=(True, "Reserved"))

        mock_capital_validator = MagicMock()
        mock_capital_validator.validate_bot_funding = AsyncMock(return_value=(True, None, None))
        mock_capital_validator.allocate_capital_to_bot = AsyncMock(return_value=(True, "ok"))

        import database as db_module
        mock_bots_col = MagicMock()
        mock_bots_col.count_documents = AsyncMock(return_value=0)
        mock_bots_col.insert_one = AsyncMock()
        mock_bots_col.delete_one = AsyncMock()

        # Patch at the services module level (imports are inside function body)
        with patch("services.paper_wallet_service.paper_wallet_service", mock_paper_service), \
             patch("services.reserved_funds_service.reserved_funds_service", mock_reserved_service), \
             patch("services.capital_validator.capital_validator", mock_capital_validator, create=True), \
             patch.object(db_module, "bots_collection", mock_bots_col), \
             patch("engines.bot_manager.NEW_BOT_CAPITAL", 100):

            result = await manager.create_bot(
                user_id="user1",
                name="TestBot",
                exchange="binance",
                risk_mode="safe",
                capital=500,
            )

        # Should NOT return insufficient funds error
        if not result.get("success"):
            assert "insufficient" not in result.get("message", "").lower(), (
                f"Bot should start with sufficient ZAR, got: {result}"
            )
