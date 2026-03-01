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
        assert "/summary" in routes


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
        content = open(path).read()
        assert '/api/admin/truth/summary' in content, "Should fetch from truth summary endpoint"
        assert 'TruthConsoleSection' in content, "Should export TruthConsoleSection"
        assert 'contradictions' in content, "Should display contradictions"
        assert 'subsystems' in content, "Should display subsystems"
        assert 'rule_precedence' in content, "Should display rule precedence"
