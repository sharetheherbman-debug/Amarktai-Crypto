"""
Production Truth Fixes — Unit Tests
====================================

Tests that validate the production-truth fixes introduced to address:

1. Hardcoded fake fallback prices removed from paper_trading_engine — trades must
   be blocked (not executed with fake prices) when real market data is unavailable.
2. Paper wallet reset goes to ZERO (not 30000 seed) so the dashboard reflects a
   true clean state immediately after reset.
3. No fake placeholder chart labels in the frontend fallback state.
4. mode label no longer says "simulated for demonstration purposes".

Run with:
  ENVIRONMENT=testing JWT_SECRET=test-jwt-secret-for-testing-only \
  PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest tests/test_production_truth_fixes.py -v
"""

import os
import sys
import inspect
import asyncio
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

os.environ.setdefault("ENVIRONMENT", "testing")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-testing-only")


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# ---------------------------------------------------------------------------
# 1. Paper Trading Engine — No fake fallback prices
# ---------------------------------------------------------------------------

class TestNoFakeFallbackPrices:
    """Paper trading engine must NOT use hardcoded fake prices as a final fallback."""

    def test_get_real_price_source_no_hardcoded_btc(self):
        """get_real_price must not contain BTC=50000 hardcoded fallback."""
        from paper_trading_engine import PaperTradingEngine
        source = inspect.getsource(PaperTradingEngine.get_real_price)
        assert "50000" not in source, (
            "Hardcoded BTC fallback price (50000.0) was found in get_real_price. "
            "Remove it — fake prices must never drive paper trading decisions."
        )
        assert "3000.0" not in source, (
            "Hardcoded ETH fallback price (3000.0) was found in get_real_price."
        )

    def test_get_real_price_returns_none_when_unavailable(self):
        """get_real_price must return None (not a fake price) when market data is unavailable."""
        from unittest.mock import AsyncMock, patch, MagicMock
        from paper_trading_engine import PaperTradingEngine

        engine = PaperTradingEngine()
        engine.price_cache = {}  # Empty cache
        # All exchange objects are None — simulating no connectivity
        engine.luno_exchange = None
        engine.binance_exchange = None
        engine.kucoin_exchange = None
        engine.bybit_exchange = None
        engine.bitget_exchange = None

        result = _run(engine.get_real_price("BTC/ZAR", "luno"))
        assert result is None, (
            f"get_real_price must return None when market data is unavailable, got {result!r}"
        )

    def test_get_market_snapshot_returns_unavailable_when_no_data(self):
        """get_market_snapshot must return source='unavailable' and mid=None when no price."""
        from unittest.mock import AsyncMock
        from paper_trading_engine import PaperTradingEngine

        engine = PaperTradingEngine()
        engine.price_cache = {}
        engine.luno_exchange = None
        engine.binance_exchange = None
        engine.kucoin_exchange = None
        engine.bybit_exchange = None
        engine.bitget_exchange = None

        snapshot = _run(engine.get_market_snapshot("BTC/ZAR", "luno"))
        assert snapshot["source"] == "unavailable", (
            f"Expected source='unavailable', got {snapshot['source']!r}"
        )
        assert snapshot["mid"] is None, (
            f"Expected mid=None (market unavailable), got {snapshot['mid']!r}"
        )

    def test_execute_smart_trade_blocked_on_unavailable_market(self):
        """execute_smart_trade must return success=False when market snapshot is unavailable."""
        from unittest.mock import AsyncMock, patch, MagicMock
        from paper_trading_engine import PaperTradingEngine

        engine = PaperTradingEngine()
        engine.price_cache = {}
        engine.luno_exchange = None
        engine.binance_exchange = None
        engine.kucoin_exchange = None
        engine.bybit_exchange = None
        engine.bitget_exchange = None

        # Stub get_market_snapshot to return unavailable
        async def fake_snapshot(symbol, exchange="luno"):
            return {
                "bid": None, "ask": None, "mid": None,
                "spread": 0.0, "spread_bps": 0.0,
                "source": "unavailable", "timestamp": "2024-01-01T00:00:00Z"
            }

        engine.get_market_snapshot = fake_snapshot
        engine.get_available_pairs = AsyncMock(return_value=["BTC/ZAR"])

        bot_data = {
            "id": "bot_test",
            "user_id": "u1",
            "name": "TestBot",
            "exchange": "luno",
            "pair": "BTC/ZAR",
            "initial_capital": 1000,
            "current_capital": 1000,
            "trading_mode": "paper",
            "risk_mode": "safe",
        }

        with patch("paper_trading_engine.enforce_trading_gates"):
            result = _run(engine.execute_smart_trade("bot_test", bot_data))

        assert result.get("success") is False, (
            "Trade must be blocked when market data is unavailable"
        )
        assert result.get("skip_reason") == "market_data_unavailable" or \
               "unavailable" in (result.get("error") or "").lower(), (
            f"Expected market_data_unavailable skip reason, got: {result}"
        )

    def test_mode_label_not_simulated(self):
        """get_mode_label must not describe paper mode as 'simulated for demonstration'."""
        from paper_trading_engine import PaperTradingEngine
        engine = PaperTradingEngine()
        label_info = engine.get_mode_label()
        desc = label_info.get("description", "")
        assert "simulated for demonstration" not in desc.lower(), (
            f"Mode label must not say 'simulated for demonstration'. Got: {desc!r}"
        )
        # Mode should be 'paper', not 'demo'
        assert label_info.get("mode") != "demo", (
            "Mode must not be 'demo' — use 'paper' or 'verified'"
        )

    def test_no_fallback_source_in_snapshot_code(self):
        """get_market_snapshot default source must not be 'fallback' — use 'unavailable'."""
        from paper_trading_engine import PaperTradingEngine
        source = inspect.getsource(PaperTradingEngine.get_market_snapshot)
        # The default source initialisation must be 'unavailable', not 'fallback'.
        assert 'source = "fallback"' not in source and "source = 'fallback'" not in source, (
            "get_market_snapshot must not initialise source as 'fallback'; "
            "use 'unavailable' so callers can block fake-price trades explicitly."
        )


# ---------------------------------------------------------------------------
# 2. Paper Wallet Reset — Must go to ZERO
# ---------------------------------------------------------------------------

class TestPaperWalletResetToZero:
    """Paper wallet reset must set all balances to zero (true clean reset)."""

    def test_reset_function_does_not_seed_with_starting_capital(self):
        """reset() must NOT set ZAR to PAPER_STARTING_CAPITAL_ZAR."""
        import inspect
        from services.paper_wallet_service import PaperWalletService

        source = inspect.getsource(PaperWalletService.reset)
        # The reset function must NOT seed balances with starting capital
        assert '"balances.ZAR": float(PAPER_STARTING_CAPITAL_ZAR)' not in source, (
            "reset() must not seed the wallet with PAPER_STARTING_CAPITAL_ZAR — "
            "paper reset must return the wallet to a true zero state."
        )

    def test_reset_returns_zero_total(self):
        """reset() must return total=0 (empty wallet) after a true clean reset."""
        from unittest.mock import AsyncMock, MagicMock, patch
        from pymongo import ReturnDocument
        from services.paper_wallet_service import PaperWalletService

        service = PaperWalletService()

        # Simulate existing wallet with ZAR and BTC balances
        existing_doc = {
            "user_id": "u1",
            "type": "paper",
            "balances": {"ZAR": 30000.0, "BTC": 0.05},
        }
        # After reset, the document should have zero/empty balances
        reset_doc = {
            "user_id": "u1",
            "type": "paper",
            "balances": {},
        }

        mock_col = MagicMock()
        mock_col.find_one = AsyncMock(return_value=existing_doc)
        mock_col.find_one_and_update = AsyncMock(return_value=reset_doc)
        service.collection = mock_col

        result = _run(service.reset("u1"))

        assert result["total"] == 0, (
            f"Paper wallet reset must return total=0, got {result['total']}"
        )
        assert result["balances"] == {} or result["balances"] == {"ZAR": 0.0}, (
            f"Paper wallet reset must return empty or zero balances, got {result['balances']}"
        )

    def test_reset_source_sets_balances_to_empty(self):
        """reset() source must set balances to an empty dict (not 30000)."""
        import inspect
        from services.paper_wallet_service import PaperWalletService
        source = inspect.getsource(PaperWalletService.reset)
        # The update must set balances to {} (empty dict), not to a seeded amount
        assert '"balances": {}' in source or "'balances': {}" in source, (
            "reset() must set balances to {} (empty dict) for a true clean reset"
        )


# ---------------------------------------------------------------------------
# 3. Frontend — No fake placeholder chart labels
# ---------------------------------------------------------------------------

class TestNoFakePlaceholderChartData:
    """Frontend loadProfitData must not substitute fake day labels on error."""

    def test_no_mon_tue_placeholder_labels_in_dashboard_state(self):
        """useDashboardState.js must not have 'Mon', 'Tue' placeholder day labels in fallback."""
        path = os.path.join(
            os.path.dirname(__file__), "..", "frontend", "src",
            "hooks", "useDashboardState.js"
        )
        with open(path) as f:
            content = f.read()
        # The 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun' fake label array
        # must not appear in the loadProfitData error handler
        placeholder_block = "'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'"
        assert placeholder_block not in content, (
            "Fake placeholder day labels ('Mon', 'Tue', ...) must be removed from "
            "loadProfitData error fallback — charts must show real data only."
        )


# ---------------------------------------------------------------------------
# 4. Paper reset WebSocket handler in frontend
# ---------------------------------------------------------------------------

class TestPaperResetWebSocketHandler:
    """Frontend must have an explicit paper_reset WebSocket message handler."""

    def test_paper_reset_case_exists_in_dashboard_state(self):
        """useDashboardState.js must handle the 'paper_reset' WebSocket message."""
        path = os.path.join(
            os.path.dirname(__file__), "..", "frontend", "src",
            "hooks", "useDashboardState.js"
        )
        with open(path) as f:
            content = f.read()
        assert "case 'paper_reset':" in content, (
            "useDashboardState.js must have an explicit 'paper_reset' WebSocket message handler "
            "to clear client state immediately when the backend completes a paper reset."
        )

    def test_paper_reset_handler_clears_balances(self):
        """paper_reset handler must clear wallet balances to zero."""
        path = os.path.join(
            os.path.dirname(__file__), "..", "frontend", "src",
            "hooks", "useDashboardState.js"
        )
        with open(path) as f:
            content = f.read()
        # After case 'paper_reset': there should be a setBalances call with zeros
        paper_reset_idx = content.index("case 'paper_reset':")
        force_refresh_idx = content.index("case 'force_refresh':")
        handler_block = content[paper_reset_idx:force_refresh_idx]
        assert "setBalances" in handler_block, (
            "paper_reset WebSocket handler must call setBalances to reset wallet to zero"
        )


# ---------------------------------------------------------------------------
# 5. Bot update endpoint — live-trading gate validation
# ---------------------------------------------------------------------------

class TestBotUpdateEndpoint:
    """PUT /api/bots/{bot_id} must validate live-trading gates."""

    def test_update_bot_route_exists_in_server(self):
        """PUT /bots/{bot_id} must be registered in server.py api_router."""
        path = os.path.join(os.path.dirname(__file__), "..", "backend", "server.py")
        with open(path) as f:
            content = f.read()
        assert '@api_router.put("/bots/{bot_id}")' in content or \
               "@api_router.put('/bots/{bot_id}')" in content, (
            "server.py must register PUT /bots/{bot_id} so the frontend "
            "handleToggleBotMode function (PUT /api/bots/{botId}) works."
        )

    def test_update_bot_blocks_live_mode_when_env_disabled(self):
        """Bot update in server.py must refuse trading_mode=live when LIVE_TRADING env var is not set."""
        path = os.path.join(os.path.dirname(__file__), "..", "backend", "server.py")
        with open(path) as f:
            content = f.read()
        assert "LIVE_TRADING" in content, (
            "server.py update_bot must check the LIVE_TRADING env var before allowing mode=live"
        )

    def test_update_bot_blocks_live_without_user_eligibility(self):
        """Bot update must check user live_allowed flag before permitting mode=live."""
        path = os.path.join(os.path.dirname(__file__), "..", "backend", "server.py")
        with open(path) as f:
            content = f.read()
        assert "live_allowed" in content, (
            "server.py update_bot must verify user.live_allowed before trading_mode='live'"
        )

    def test_no_duplicate_update_bot_in_bot_lifecycle(self):
        """bot_lifecycle.py must NOT define its own PUT /{bot_id} (prevents collision)."""
        import inspect
        from routes.bot_lifecycle import router
        routes_with_methods = [
            (r.methods, r.path) for r in router.routes if hasattr(r, 'methods')
        ]
        put_bare = [
            (m, p) for m, p in routes_with_methods
            if p == '/{bot_id}' and 'PUT' in (m or [])
        ]
        assert not put_bare, (
            "bot_lifecycle.py must NOT register PUT /{bot_id} — the canonical "
            "update_bot lives in server.py. Duplicate routes cause a server collision."
        )


# ---------------------------------------------------------------------------
# 6. Auto-start paper learning on bot creation
# ---------------------------------------------------------------------------

class TestPaperLearningAutoStart:
    """Bot creation must auto-start the paper learning period."""

    def test_server_py_auto_starts_paper_learning(self):
        """server.py bot creation flow must auto-start paper learning period."""
        path = os.path.join(os.path.dirname(__file__), "..", "backend", "server.py")
        with open(path) as f:
            content = f.read()
        assert "paper_learning_start_ts" in content, (
            "server.py bot creation must auto-set paper_learning_start_ts so users "
            "are automatically enrolled in the 7-day evaluation window."
        )

    def test_scalper_seed_auto_starts_paper_learning(self):
        """Scalper seed endpoint must also auto-start paper learning."""
        path = os.path.join(os.path.dirname(__file__), "..", "backend", "routes", "scalper.py")
        with open(path) as f:
            content = f.read()
        assert "paper_learning_start_ts" in content, (
            "routes/scalper.py scalper_seed must auto-set paper_learning_start_ts"
        )


# ---------------------------------------------------------------------------
# 7. Subsystem health endpoint registered
# ---------------------------------------------------------------------------

class TestSubsystemHealthEndpoint:
    """The /api/diagnostics/subsystem-health endpoint must exist."""

    def test_subsystem_health_route_exists(self):
        """diagnostics.py must have a /subsystem-health GET route."""
        import inspect
        from routes.diagnostics import router
        paths = [r.path for r in router.routes if hasattr(r, 'path')]
        assert (
            "/api/diagnostics/subsystem-health" in paths or
            "/subsystem-health" in paths
        ), (
            "/subsystem-health must be registered in diagnostics.py "
            "so all users can see which subsystems are healthy/blocked. "
            f"Current paths ending in health: {[p for p in paths if 'health' in p]}"
        )

    def test_subsystem_health_returns_trading_blockers(self):
        """subsystem-health source must include 'trading_blocked' in its response."""
        path = os.path.join(os.path.dirname(__file__), "..", "backend", "routes", "diagnostics.py")
        with open(path) as f:
            content = f.read()
        assert "trading_blocked" in content, (
            "subsystem-health must return 'trading_blocked' so frontend can show "
            "whether trading is currently blocked and why."
        )


# ---------------------------------------------------------------------------
# 8. Growth Engine section — disabled reason visibility
# ---------------------------------------------------------------------------

class TestGrowthEngineSectionBlockers:
    """GrowthEngineSection.js must show disabled reasons clearly."""

    def _read_section(self):
        path = os.path.join(
            os.path.dirname(__file__), "..", "frontend", "src",
            "pages", "dashboard", "sections", "GrowthEngineSection.js"
        )
        with open(path) as f:
            return f.read()

    def test_reason_labels_map_exists(self):
        """GrowthEngineSection must have a human-readable REASON_LABELS map."""
        content = self._read_section()
        assert "REASON_LABELS" in content, (
            "GrowthEngineSection.js must have a REASON_LABELS map so backend reason "
            "codes like AUTOPILOT_GROWTH_DISABLED are shown as human-readable text."
        )

    def test_disabled_panel_shown_when_engine_off(self):
        """GrowthEngineSection must render a DisabledPanel when the engine is off."""
        content = self._read_section()
        assert "DisabledPanel" in content, (
            "GrowthEngineSection.js must render a DisabledPanel component when "
            "growthEnabled is false, showing the user why it is disabled."
        )

    def test_blocked_reasons_surfaced_per_platform(self):
        """Each PlatformGrowthCard must show blocked_reasons from backend."""
        content = self._read_section()
        assert "blocked_reasons" in content, (
            "GrowthEngineSection.js must read blocked_reasons from each platform's "
            "status and display them so the user knows what is blocking the engine."
        )
