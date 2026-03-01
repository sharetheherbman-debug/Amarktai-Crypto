"""
Tests for Truth Kernel, Contradiction Detector, and Admin Truth Console.

Tests the central truth computation module, contradiction detection,
and AI Chat truth check command integration.
"""

import sys
import os
import pytest

# Ensure backend is on the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))


# ============================================================================
# Contradiction Detector Tests
# ============================================================================

class TestContradictionDetector:
    """Tests for services/contradiction_detector.py"""

    def test_no_contradictions_clean_state(self):
        from services.contradiction_detector import detect_contradictions
        bots = {"total_bots": 2, "eligible_count": 2, "ineligible_count": 0, "ineligible_reasons": {}}
        wallet = {"total": 1000, "available": 500, "reserved": 500, "balance_check": True, "negative_balance": False}
        risk = {"total_equity": 1000, "peak_equity": 1000, "drawdown_pct": 0, "daily_realized_pnl": 0, "fills_today": 0}
        scheduler = {"running": True, "last_tick": "2025-01-01T00:00:00+00:00", "lag_seconds": 5, "stale": False}
        exchanges = {"exchanges": {"binance": {"configured": True}}, "configured_count": 1, "total_exchanges": 7}

        contradictions = detect_contradictions(bots, wallet, risk, scheduler, exchanges)
        assert len(contradictions) == 0, f"Expected no contradictions, got: {contradictions}"

    def test_eligible_bots_no_tick(self):
        from services.contradiction_detector import detect_contradictions
        bots = {"total_bots": 2, "eligible_count": 2, "ineligible_count": 0, "ineligible_reasons": {}}
        wallet = {"total": 1000, "available": 500, "reserved": 500, "balance_check": True, "negative_balance": False}
        risk = {"total_equity": 1000, "peak_equity": 1000, "drawdown_pct": 0, "daily_realized_pnl": 0, "fills_today": 0}
        scheduler = {"running": False, "last_tick": None, "lag_seconds": 999, "stale": True}
        exchanges = {"exchanges": {}, "configured_count": 0, "total_exchanges": 7}

        contradictions = detect_contradictions(bots, wallet, risk, scheduler, exchanges)
        ids = [c["id"] for c in contradictions]
        assert "ELIGIBLE_BOTS_NO_TICK" in ids

    def test_allocated_exceeds_total(self):
        from services.contradiction_detector import detect_contradictions
        bots = {"total_bots": 0, "eligible_count": 0, "ineligible_count": 0, "ineligible_reasons": {}}
        wallet = {"total": 500, "available": 100, "reserved": 600, "balance_check": False, "negative_balance": False}
        risk = {"total_equity": 0, "peak_equity": 0, "drawdown_pct": 0, "daily_realized_pnl": 0, "fills_today": 0}
        scheduler = {"running": False, "last_tick": None, "lag_seconds": None, "stale": True}
        exchanges = {"exchanges": {}, "configured_count": 0, "total_exchanges": 7}

        contradictions = detect_contradictions(bots, wallet, risk, scheduler, exchanges)
        ids = [c["id"] for c in contradictions]
        assert "ALLOCATED_EXCEEDS_TOTAL" in ids

    def test_negative_balance(self):
        from services.contradiction_detector import detect_contradictions
        bots = {"total_bots": 0, "eligible_count": 0, "ineligible_count": 0, "ineligible_reasons": {}}
        wallet = {"total": 100, "available": -10, "reserved": 110, "balance_check": True, "negative_balance": True}
        risk = {"total_equity": 0, "peak_equity": 0, "drawdown_pct": 0, "daily_realized_pnl": 0, "fills_today": 0}
        scheduler = {"running": False, "last_tick": None, "lag_seconds": None, "stale": True}
        exchanges = {"exchanges": {}, "configured_count": 0, "total_exchanges": 7}

        contradictions = detect_contradictions(bots, wallet, risk, scheduler, exchanges)
        ids = [c["id"] for c in contradictions]
        assert "NEGATIVE_BALANCE" in ids

    def test_equity_peak_mismatch(self):
        from services.contradiction_detector import detect_contradictions
        bots = {"total_bots": 2, "eligible_count": 0, "ineligible_count": 2, "ineligible_reasons": {"bot1": ["paused"]}}
        wallet = {"total": 1000, "available": 500, "reserved": 500, "balance_check": True, "negative_balance": False}
        risk = {"total_equity": 0, "peak_equity": 5000, "drawdown_pct": 100, "daily_realized_pnl": 0, "fills_today": 0}
        scheduler = {"running": False, "last_tick": None, "lag_seconds": None, "stale": True}
        exchanges = {"exchanges": {}, "configured_count": 0, "total_exchanges": 7}

        contradictions = detect_contradictions(bots, wallet, risk, scheduler, exchanges)
        ids = [c["id"] for c in contradictions]
        assert "EQUITY_PEAK_MISMATCH" in ids

    def test_drawdown_no_lock(self):
        from services.contradiction_detector import detect_contradictions
        bots = {"total_bots": 2, "eligible_count": 2, "ineligible_count": 0, "ineligible_reasons": {}}
        wallet = {"total": 1000, "available": 500, "reserved": 500, "balance_check": True, "negative_balance": False}
        risk = {"total_equity": 700, "peak_equity": 1000, "drawdown_pct": 30, "daily_realized_pnl": -300, "fills_today": 5}
        scheduler = {"running": True, "last_tick": "2025-01-01T00:00:00+00:00", "lag_seconds": 5, "stale": False}
        exchanges = {"exchanges": {}, "configured_count": 0, "total_exchanges": 7}

        contradictions = detect_contradictions(bots, wallet, risk, scheduler, exchanges)
        ids = [c["id"] for c in contradictions]
        assert "DRAWDOWN_NO_LOCK" in ids

    def test_scheduler_running_but_stale(self):
        from services.contradiction_detector import detect_contradictions
        bots = {"total_bots": 0, "eligible_count": 0, "ineligible_count": 0, "ineligible_reasons": {}}
        wallet = {"total": 1000, "available": 500, "reserved": 500, "balance_check": True, "negative_balance": False}
        risk = {"total_equity": 0, "peak_equity": 0, "drawdown_pct": 0, "daily_realized_pnl": 0, "fills_today": 0}
        scheduler = {"running": True, "last_tick": "2025-01-01T00:00:00+00:00", "lag_seconds": 300, "stale": True}
        exchanges = {"exchanges": {}, "configured_count": 0, "total_exchanges": 7}

        contradictions = detect_contradictions(bots, wallet, risk, scheduler, exchanges)
        ids = [c["id"] for c in contradictions]
        assert "SCHEDULER_RUNNING_BUT_STALE" in ids

    def test_balance_mismatch(self):
        from services.contradiction_detector import detect_contradictions
        bots = {"total_bots": 0, "eligible_count": 0, "ineligible_count": 0, "ineligible_reasons": {}}
        wallet = {"total": 1000, "available": 600, "reserved": 500, "balance_check": False, "negative_balance": False}
        risk = {"total_equity": 0, "peak_equity": 0, "drawdown_pct": 0, "daily_realized_pnl": 0, "fills_today": 0}
        scheduler = {"running": False, "last_tick": None, "lag_seconds": None, "stale": True}
        exchanges = {"exchanges": {}, "configured_count": 0, "total_exchanges": 7}

        contradictions = detect_contradictions(bots, wallet, risk, scheduler, exchanges)
        ids = [c["id"] for c in contradictions]
        assert "BALANCE_MISMATCH" in ids

    def test_severity_levels_are_valid(self):
        from services.contradiction_detector import SEVERITY_CRITICAL, SEVERITY_WARNING, SEVERITY_INFO
        assert SEVERITY_CRITICAL == "critical"
        assert SEVERITY_WARNING == "warning"
        assert SEVERITY_INFO == "info"


# ============================================================================
# Truth Kernel Tests (structure + imports)
# ============================================================================

class TestTruthKernel:
    """Tests for services/truth_kernel.py"""

    def test_truth_kernel_imports(self):
        from services.truth_kernel import (
            RULE_PRECEDENCE,
            SUBSYSTEMS,
            compute_bot_eligibility,
            compute_wallet_balances,
            compute_risk_state,
            compute_scheduler_state,
            compute_exchange_readiness,
            compute_daily_close_state,
            compute_realtime_state,
            compute_truth_summary,
        )
        # All imports must succeed
        assert callable(compute_truth_summary)

    def test_rule_precedence_order(self):
        from services.truth_kernel import RULE_PRECEDENCE
        assert len(RULE_PRECEDENCE) == 8
        assert RULE_PRECEDENCE[0] == "emergency_stop"
        assert RULE_PRECEDENCE[1] == "circuit_breaker"
        assert RULE_PRECEDENCE[2] == "daily_loss_lock"
        assert RULE_PRECEDENCE[-1] == "strategy_gating"

    def test_subsystems_complete(self):
        from services.truth_kernel import SUBSYSTEMS
        expected = [
            "TRUTH_KERNEL", "BOT_ELIGIBILITY", "PAPER_ENGINE",
            "LEDGER_TRUTH", "WALLET_RECONCILIATION", "RISK_BASELINES",
            "DAILY_CLOSE", "AUTOSPAWN", "TRAINING_GATE",
            "EXCHANGE_HEALTH", "REALTIME", "AI_CHATOPS", "UI_HEALTH",
            "SCALPER",
        ]
        assert SUBSYSTEMS == expected

    def test_rule_precedence_has_emergency_first(self):
        from services.truth_kernel import RULE_PRECEDENCE
        assert RULE_PRECEDENCE[0] == "emergency_stop"

    def test_rule_precedence_has_strategy_last(self):
        from services.truth_kernel import RULE_PRECEDENCE
        assert RULE_PRECEDENCE[-1] == "strategy_gating"


# ============================================================================
# Admin Truth Router Tests
# ============================================================================

class TestAdminTruthRouter:
    """Tests for routes/admin_truth.py"""

    @pytest.fixture(autouse=True)
    def _check_fastapi(self):
        try:
            from routes.admin_truth import router  # noqa: F401
        except ImportError:
            pytest.skip("fastapi or other route dependencies not installed")

    def test_router_prefix(self):
        from routes.admin_truth import router
        assert router.prefix == "/api/admin/truth"

    def test_router_has_summary_endpoint(self):
        from routes.admin_truth import router
        routes = [r.path for r in router.routes]
        # In newer Starlette versions route paths include the router prefix
        assert any(p.endswith("/summary") for p in routes)


# ============================================================================
# AI Chat Truth Check Integration Tests
# ============================================================================

class TestAIChatTruthCheck:
    """Tests for truth check command in ai_chat.py"""

    @pytest.fixture(autouse=True)
    def _check_imports(self):
        try:
            from routes.ai_chat import detect_action_intent  # noqa: F401
        except ImportError:
            pytest.skip("AI chat dependencies not installed")

    def test_truth_check_detected(self):
        from routes.ai_chat import detect_action_intent
        result = detect_action_intent("truth check", True)
        assert result is not None
        assert result["action"] == "truth_check"
        assert result["params"]["verbose"] is False

    def test_truth_check_verbose_detected(self):
        from routes.ai_chat import detect_action_intent
        result = detect_action_intent("truth check verbose", True)
        assert result is not None
        assert result["action"] == "truth_check"
        assert result["params"]["verbose"] is True

    def test_truth_check_in_action_registry(self):
        from routes.ai_chat import ACTION_REGISTRY
        assert "truth_check" in ACTION_REGISTRY
        assert ACTION_REGISTRY["truth_check"]["requires_confirmation"] is False

    def test_truth_check_handler_exists(self):
        from routes.ai_chat import ACTION_REGISTRY
        handler = ACTION_REGISTRY["truth_check"]["handler"]
        assert callable(handler)


# ============================================================================
# Frontend Component File Tests
# ============================================================================

class TestFrontendTruthConsole:
    """Verify frontend Truth Console component exists."""

    def test_component_file_exists(self):
        path = os.path.join(
            os.path.dirname(__file__), '..', 'frontend', 'src', 'pages',
            'dashboard', 'sections', 'TruthConsoleSection.js'
        )
        assert os.path.exists(path), "TruthConsoleSection.js should exist"

    def test_css_file_exists(self):
        path = os.path.join(
            os.path.dirname(__file__), '..', 'frontend', 'src', 'styles',
            'truth-console.css'
        )
        assert os.path.exists(path), "truth-console.css should exist"

    def test_component_has_key_elements(self):
        path = os.path.join(
            os.path.dirname(__file__), '..', 'frontend', 'src', 'pages',
            'dashboard', 'sections', 'TruthConsoleSection.js'
        )
        with open(path) as f:
            content = f.read()
        assert '/api/admin/truth/summary' in content, "Should fetch from truth summary endpoint"
        assert 'TruthConsoleSection' in content, "Should export TruthConsoleSection"
        assert 'contradictions' in content, "Should display contradictions"
        assert 'subsystems' in content, "Should display subsystems"
        assert 'rule_precedence' in content, "Should display rule precedence"


# ============================================================================
# Scalper Model + Exchange Limits Tests
# ============================================================================

class TestScalperModels:
    """Tests for scalper bot type, profit routing, and exchange limits."""

    @pytest.fixture(autouse=True)
    def _check_pydantic(self):
        try:
            from models import BotType  # noqa: F401
        except ImportError:
            pytest.skip("pydantic or other model dependencies not installed")

    def test_bot_type_enum_exists(self):
        from models import BotType
        assert BotType.NORMAL == "normal"
        assert BotType.SCALPER == "scalper"

    def test_scalper_profit_routing_enum(self):
        from models import ScalperProfitRouting
        assert ScalperProfitRouting.SCALPER_GROWTH == "SCALPER_GROWTH"
        assert ScalperProfitRouting.RETURN_TO_MAIN == "RETURN_TO_MAIN"

    def test_bot_create_has_bot_type(self):
        from models import BotCreate
        assert 'bot_type' in BotCreate.model_fields

    def test_bot_model_has_bot_type(self):
        from models import Bot
        assert 'bot_type' in Bot.model_fields
        assert 'profit_routing' in Bot.model_fields


class TestScalperExchangeLimits:
    """Tests for scalper exchange caps and EV gating."""

    def test_scalper_bot_allocation_exists(self):
        from exchange_limits import SCALPER_BOT_ALLOCATION, MAX_SCALPER_BOTS_GLOBAL
        assert SCALPER_BOT_ALLOCATION["luno"] == 2
        assert SCALPER_BOT_ALLOCATION["binance"] == 5
        assert SCALPER_BOT_ALLOCATION["kucoin"] == 5
        assert MAX_SCALPER_BOTS_GLOBAL == 32

    def test_normal_caps_unchanged(self):
        from exchange_limits import BOT_ALLOCATION, MAX_BOTS_GLOBAL
        assert BOT_ALLOCATION["luno"] == 5
        assert BOT_ALLOCATION["binance"] == 10
        assert MAX_BOTS_GLOBAL == 65

    def test_scalper_caps_independent(self):
        from exchange_limits import BOT_ALLOCATION, SCALPER_BOT_ALLOCATION
        # Scalper caps must be independent and <= normal caps
        for ex in SCALPER_BOT_ALLOCATION:
            assert ex in BOT_ALLOCATION, f"Scalper exchange {ex} not in normal allocation"
            assert SCALPER_BOT_ALLOCATION[ex] <= BOT_ALLOCATION[ex], f"Scalper cap > normal for {ex}"

    def test_get_scalper_cap(self):
        from exchange_limits import get_scalper_cap
        assert get_scalper_cap("luno") == 2
        assert get_scalper_cap("binance") == 5
        assert get_scalper_cap("unknown") == 2  # default

    def test_get_normal_cap(self):
        from exchange_limits import get_normal_cap
        assert get_normal_cap("luno") == 5
        assert get_normal_cap("binance") == 10

    def test_compute_scalper_ev_positive(self):
        from exchange_limits import compute_scalper_ev
        # High win rate, decent TP/SL, low costs = positive EV
        ev = compute_scalper_ev(
            win_rate=0.6,
            tp_pct=0.01,
            sl_pct=0.005,
            entry_fee_pct=0.001,
            exit_fee_pct=0.001,
            spread_pct=0.0005,
            slippage_pct=0.0003,
        )
        assert ev > 0, f"Expected positive EV, got {ev}"

    def test_compute_scalper_ev_negative(self):
        from exchange_limits import compute_scalper_ev
        # Low win rate, high costs = negative EV
        ev = compute_scalper_ev(
            win_rate=0.3,
            tp_pct=0.005,
            sl_pct=0.01,
            entry_fee_pct=0.002,
            exit_fee_pct=0.002,
            spread_pct=0.002,
            slippage_pct=0.001,
        )
        assert ev < 0, f"Expected negative EV, got {ev}"

    def test_exit_reason_codes_defined(self):
        from exchange_limits import (
            EXIT_REASON_TIME,
            EXIT_REASON_STAGNATION,
            EXIT_REASON_STOP,
            EXIT_REASON_TARGET,
            EXIT_REASON_TRAIL,
            EXIT_REASON_RISK,
        )
        assert EXIT_REASON_TIME == "TIME_EXIT"
        assert EXIT_REASON_STAGNATION == "STAGNATION_EXIT"
        assert EXIT_REASON_STOP == "STOP_EXIT"
        assert EXIT_REASON_TARGET == "TARGET_EXIT"
        assert EXIT_REASON_TRAIL == "TRAIL_EXIT"
        assert EXIT_REASON_RISK == "RISK_EXIT"

    def test_scalper_throttle_constants_defined(self):
        from exchange_limits import (
            SCALPER_ORDERS_PER_MIN,
            SCALPER_CANCELS_PER_MIN,
            SCALPER_COOLDOWN_SECONDS,
            SCALPER_MAX_HOLD_SECONDS,
            SCALPER_STAGNATION_SECONDS,
            SCALPER_EV_MIN_BPS,
            SCALPER_SPREAD_MAX_BPS,
        )
        assert SCALPER_ORDERS_PER_MIN > 0
        assert SCALPER_CANCELS_PER_MIN > 0
        assert SCALPER_COOLDOWN_SECONDS > 0
        assert SCALPER_MAX_HOLD_SECONDS > 0
        assert SCALPER_STAGNATION_SECONDS > 0
        assert SCALPER_EV_MIN_BPS > 0
        assert SCALPER_SPREAD_MAX_BPS > 0


# ============================================================================
# Go-Live Diagnostics Truth Integration
# ============================================================================

class TestGoLiveTruthIntegration:
    """Tests that go-live diagnostics uses Truth Kernel."""

    def test_go_live_imports_truth_kernel(self):
        """Verify server.py references truth kernel in go-live handler."""
        import os
        server_path = os.path.join(
            os.path.dirname(__file__), '..', 'backend', 'server.py'
        )
        with open(server_path) as f:
            content = f.read()
        assert 'compute_truth_summary' in content, \
            "go-live should use compute_truth_summary from truth kernel"
        assert 'contradictions' in content, \
            "go-live should include contradictions from truth kernel"

    def test_scalper_router_exists(self):
        """Verify scalper router file exists."""
        import os
        path = os.path.join(
            os.path.dirname(__file__), '..', 'backend', 'routes', 'scalper.py'
        )
        assert os.path.exists(path), "scalper.py router should exist"

    def test_scalper_router_mounted(self):
        """Verify scalper router is in server.py routers_to_mount."""
        import os
        server_path = os.path.join(
            os.path.dirname(__file__), '..', 'backend', 'server.py'
        )
        with open(server_path) as f:
            content = f.read()
        assert 'routes.scalper' in content, "scalper router should be mounted"

    def test_radar_includes_bot_type(self):
        """Verify radar.py returns bot_type field."""
        import os
        radar_path = os.path.join(
            os.path.dirname(__file__), '..', 'backend', 'routes', 'radar.py'
        )
        with open(radar_path) as f:
            content = f.read()
        assert 'bot_type' in content, "radar should include bot_type field"


# ============================================================================
# AI Chat Scalper Commands Tests
# ============================================================================

class TestAIChatScalperCommands:
    """Tests for scalper-related AI chat commands."""

    def test_ai_chat_detects_create_scalper(self):
        """AI chat should detect 'create scalper bot' intent."""
        import os
        chat_path = os.path.join(
            os.path.dirname(__file__), '..', 'backend', 'routes', 'ai_chat.py'
        )
        with open(chat_path) as f:
            content = f.read()
        assert 'create_scalper_bot' in content, "AI chat should support create_scalper_bot action"
        assert 'scalper_summary' in content, "AI chat should support scalper_summary action"
        assert 'scalper_caps' in content, "AI chat should support scalper_caps action"
        assert 'set_scalper_routing' in content, "AI chat should support set_scalper_routing action"
        assert 'explain_not_trading' in content, "AI chat should support explain_not_trading action"

    def test_ai_chat_scalper_handlers_registered(self):
        """Verify scalper action handlers are in ACTION_REGISTRY."""
        import os
        chat_path = os.path.join(
            os.path.dirname(__file__), '..', 'backend', 'routes', 'ai_chat.py'
        )
        with open(chat_path) as f:
            content = f.read()
        # Handlers should be defined as functions
        assert '_handle_create_scalper_bot' in content
        assert '_handle_scalper_summary' in content
        assert '_handle_scalper_caps' in content
        assert '_handle_set_scalper_routing' in content
        assert '_handle_explain_not_trading' in content

    def test_ai_chat_scalper_routing_requires_confirmation(self):
        """Set scalper routing should require confirmation."""
        import os
        chat_path = os.path.join(
            os.path.dirname(__file__), '..', 'backend', 'routes', 'ai_chat.py'
        )
        with open(chat_path) as f:
            content = f.read()
        # set_scalper_routing should have requires_confirmation: True
        assert '"requires_confirmation": True' in content or "'requires_confirmation': True" in content


# ============================================================================
# Frontend Scalper Panel Tests
# ============================================================================

class TestFrontendScalperPanel:
    """Tests for ScalperBotsPanel frontend component."""

    def test_scalper_panel_file_exists(self):
        import os
        path = os.path.join(
            os.path.dirname(__file__), '..', 'frontend', 'src', 'pages',
            'dashboard', 'sections', 'ScalperBotsPanel.js'
        )
        assert os.path.exists(path), "ScalperBotsPanel.js should exist"

    def test_scalper_panel_fetches_caps(self):
        import os
        path = os.path.join(
            os.path.dirname(__file__), '..', 'frontend', 'src', 'pages',
            'dashboard', 'sections', 'ScalperBotsPanel.js'
        )
        with open(path) as f:
            content = f.read()
        assert '/api/scalper/caps' in content, "Should fetch from scalper caps endpoint"
        assert '/api/scalper/summary' in content, "Should fetch from scalper summary endpoint"

    def test_scalper_panel_shows_routing(self):
        import os
        path = os.path.join(
            os.path.dirname(__file__), '..', 'frontend', 'src', 'pages',
            'dashboard', 'sections', 'ScalperBotsPanel.js'
        )
        with open(path) as f:
            content = f.read()
        assert 'SCALPER_GROWTH' in content, "Should show SCALPER_GROWTH routing"
        assert 'RETURN_TO_MAIN' in content, "Should show RETURN_TO_MAIN routing"

    def test_scalper_css_exists(self):
        import os
        path = os.path.join(
            os.path.dirname(__file__), '..', 'frontend', 'src', 'styles',
            'scalper-panel.css'
        )
        assert os.path.exists(path), "scalper-panel.css should exist"

    def test_bot_management_imports_scalper(self):
        import os
        path = os.path.join(
            os.path.dirname(__file__), '..', 'frontend', 'src', 'pages',
            'dashboard', 'sections', 'BotManagementSection.js'
        )
        with open(path) as f:
            content = f.read()
        assert 'ScalperBotsPanel' in content, "BotManagement should import ScalperBotsPanel"
        assert 'scalper' in content.lower(), "BotManagement should reference scalper tab"

    def test_dashboard_imports_scalper_css(self):
        import os
        path = os.path.join(
            os.path.dirname(__file__), '..', 'frontend', 'src', 'pages',
            'Dashboard.js'
        )
        with open(path) as f:
            content = f.read()
        assert 'scalper-panel.css' in content, "Dashboard should import scalper-panel.css"
