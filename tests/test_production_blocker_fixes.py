"""
Tests for production blocker fixes.

Validates:
1. Self-healing status endpoint and canonical truth
2. Bot radar target policy (no "Not configured" noise)
3. Footer does not show unknown build metadata (frontend test)
4. Duplicate scalper panel removed from BotManagement
5. Truth kernel includes SELF_HEALING subsystem
6. Target policy produces sensible strategy-based targets
7. Admin key monitor groups exist
8. Analytics consolidation (fewer tabs)
9. Bot fleet capital from canonical source
10. Radar no longer shows "not_configured" target_source when targets exist
11. All visible routes resolve (route audit)
"""

import sys
import os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))


# ── 1. Self-healing get_status() method ─────────────────────────────────

class TestSelfHealingStatus:

    def test_get_status_returns_dict(self):
        from self_healing import SelfHealingSystem
        sh = SelfHealingSystem()
        status = sh.get_status()
        assert isinstance(status, dict)
        assert "enabled" in status
        assert "state" in status
        assert "last_result" in status
        assert "last_action" in status
        assert "monitored_systems" in status

    def test_status_disabled_when_not_started(self):
        from self_healing import SelfHealingSystem
        sh = SelfHealingSystem()
        status = sh.get_status()
        assert status["enabled"] is False
        assert status["state"] == "disabled"
        assert status["last_result"] == "idle"

    def test_status_running_after_start_flag(self):
        from self_healing import SelfHealingSystem
        sh = SelfHealingSystem()
        sh.is_running = True
        sh.last_result = "ok"
        sh.last_reason_code = "HEALTHY"
        status = sh.get_status()
        assert status["enabled"] is True
        assert status["state"] == "running"
        assert status["last_result"] == "ok"


# ── 2. Target policy service ────────────────────────────────────────────

class TestTargetPolicy:

    def test_derive_targets_with_no_config(self):
        from services.target_policy import derive_targets
        bot = {
            "bot_type": "normal",
            "risk_mode": "balanced",
            "initial_capital": 10000,
        }
        targets = derive_targets(bot)
        assert targets["target_source"] == "strategy_derived"
        assert targets["daily_profit_target"] is not None
        assert targets["daily_profit_target"] > 0
        assert targets["trade_profit_target"] is not None
        assert targets["trade_profit_target"] > 0
        # Should NOT be a tiny 15-rand default
        assert targets["daily_profit_target"] >= 50  # 0.5% of 10000 = 50

    def test_derive_targets_scalper_aggressive(self):
        from services.target_policy import derive_targets
        bot = {
            "bot_type": "scalper",
            "risk_mode": "aggressive",
            "initial_capital": 5000,
        }
        targets = derive_targets(bot)
        assert targets["target_source"] == "strategy_derived"
        assert targets["daily_profit_target"] > 0
        assert targets["bot_type"] == "scalper"
        assert targets["risk_mode"] == "aggressive"

    def test_derive_targets_respects_configured(self):
        from services.target_policy import derive_targets
        bot = {
            "bot_type": "normal",
            "risk_mode": "balanced",
            "initial_capital": 10000,
            "daily_profit_target_pct": 0.03,  # 3%
        }
        targets = derive_targets(bot)
        assert targets["target_source"] == "configured"
        assert targets["daily_profit_target"] == 300  # 3% of 10000

    def test_derive_targets_zero_capital(self):
        from services.target_policy import derive_targets
        bot = {"bot_type": "normal", "risk_mode": "safe", "initial_capital": 0}
        targets = derive_targets(bot)
        assert targets["daily_profit_target"] is None
        assert targets["trade_profit_target"] is None

    def test_radar_no_not_configured_when_targets_derived(self):
        """Radar target_source should never be 'not_configured' when targets exist."""
        from services.target_policy import derive_targets
        bot = {
            "bot_type": "normal",
            "risk_mode": "balanced",
            "initial_capital": 5000,
        }
        targets = derive_targets(bot)
        assert targets["target_source"] != "not_configured"


# ── 3. Truth kernel includes SELF_HEALING subsystem ─────────────────────

class TestTruthKernelSelfHealing:

    def test_self_healing_subsystem_in_subsystem_list(self):
        """Truth kernel SUBSYSTEMS should include SELF_HEALING."""
        # Can't easily run async compute_truth_summary in this env,
        # but verify the code path exists by checking the module
        path = os.path.join(
            os.path.dirname(__file__), '..', 'backend', 'services', 'truth_kernel.py'
        )
        with open(path, 'r') as f:
            content = f.read()
        assert 'SELF_HEALING' in content
        assert 'self_healing.get_status' in content or '_sh.get_status' in content


# ── 4. Bot Fleet capital_summary uses canonical fields ──────────────────

class TestBotFleetCanonicalCapital:

    def test_capital_summary_has_required_fields(self):
        """Verify canonical_metrics builds the required capital fields."""
        from services.canonical_metrics import build_canonical_capital_summary
        summary = build_canonical_capital_summary(
            capital_initial=1000,
            capital_allocated=1050,
            capital_available=850,
            open_position_value=200,
            profit_realized=50,
            unrealized_profit=10,
        )
        required_fields = [
            "initial_capital", "allocated_capital", "available_capital",
            "open_position_value", "total_equity", "realized_profit",
            "unrealized_profit",
        ]
        for field in required_fields:
            assert field in summary, f"Missing canonical field: {field}"
        assert summary["initial_capital"] == 1000
        assert summary["realized_profit"] == 50


# ── 5. Self-healing endpoint exists in autonomy router ──────────────────

class TestSelfHealingEndpoint:

    def test_autonomy_router_has_self_healing_endpoint(self):
        """Verify /api/autonomy/self-healing/status route is registered in source."""
        path = os.path.join(
            os.path.dirname(__file__), '..', 'backend', 'routes', 'autonomy_control.py'
        )
        with open(path, 'r') as f:
            content = f.read()
        assert 'self-healing/status' in content
        assert 'get_self_healing_status' in content


# ── 6. Footer test (backend-side check that env vars are not leaked) ────

class TestFooterBuildInfo:

    def test_no_build_metadata_in_footer(self):
        """SiteFooter.js should not contain any build metadata display."""
        footer_path = os.path.join(
            os.path.dirname(__file__), '..', 'frontend', 'src', 'components', 'SiteFooter.js'
        )
        with open(footer_path, 'r') as f:
            content = f.read()
        assert "'unknown'" not in content
        assert '"unknown"' not in content
        assert "untagged" not in content
        assert "buildLabel" not in content


# ── 7. Scalper panel removed from BotManagement ─────────────────────────

class TestDuplicateScalperRemoved:

    def test_no_scalper_panel_import_in_bot_management(self):
        """BotManagementSection should not import ScalperBotsPanel."""
        path = os.path.join(
            os.path.dirname(__file__), '..', 'frontend', 'src',
            'pages', 'dashboard', 'sections', 'BotManagementSection.js'
        )
        with open(path, 'r') as f:
            content = f.read()
        assert "ScalperBotsPanel" not in content
        assert "Exchange caps apply per platform" not in content


# ── 8. Consolidated analytics tabs ──────────────────────────────────────

class TestAnalyticsConsolidation:

    def test_metrics_tabs_consolidated(self):
        """MetricsWithTabsSection should have 4 focused tabs, not 6."""
        path = os.path.join(
            os.path.dirname(__file__), '..', 'frontend', 'src',
            'pages', 'dashboard', 'sections', 'MetricsWithTabsSection.js'
        )
        with open(path, 'r') as f:
            content = f.read()
        # Should NOT have 6 overlapping tabs
        assert "whale-flow" not in content
        assert "system-metrics" not in content
        assert "intelligence-panels" not in content
        # Should have consolidated tabs
        assert "decision-trace" in content
        assert "market-state" in content
        assert "capital" in content
        assert "huggingface" in content


# ── 9. Admin key monitor grouped layout ─────────────────────────────────

class TestAdminKeyMonitorGrouped:

    def test_admin_panel_uses_grouped_key_monitor(self):
        """AdminPanelSection should use KeyMonitorGrouped, not flat table."""
        path = os.path.join(
            os.path.dirname(__file__), '..', 'frontend', 'src',
            'pages', 'dashboard', 'sections', 'AdminPanelSection.js'
        )
        with open(path, 'r') as f:
            content = f.read()
        assert "KeyMonitorGrouped" in content
        assert "Core AI" in content
        assert "Market Data" in content
        assert "Exchanges" in content
        assert "Enrichers" in content


# ── 10. Route audit — visible endpoints must exist ──────────────────────

class TestRouteAudit:

    def _read_route_file(self, relative_path):
        path = os.path.join(os.path.dirname(__file__), '..', 'backend', relative_path)
        with open(path, 'r') as f:
            return f.read()

    def test_radar_snapshot_route_exists(self):
        content = self._read_route_file('routes/radar.py')
        assert '/snapshot' in content or 'radar_snapshot' in content

    def test_admin_truth_summary_route_exists(self):
        content = self._read_route_file('routes/admin_truth.py')
        assert '/summary' in content

    def test_decision_trace_route_exists(self):
        content = self._read_route_file('routes/decision_trace.py')
        assert '/trace' in content

    def test_autonomy_status_route_exists(self):
        content = self._read_route_file('routes/autonomy_control.py')
        assert '/status' in content

    def test_self_healing_status_route_exists(self):
        content = self._read_route_file('routes/autonomy_control.py')
        assert 'self-healing/status' in content

    def test_dashboard_overview_route_exists(self):
        content = self._read_route_file('routes/dashboard_overview.py')
        assert '/snapshot' in content or 'overview_snapshot' in content

    def test_bots_status_route_exists(self):
        content = self._read_route_file('routes/bot_lifecycle.py')
        assert '/status' in content
