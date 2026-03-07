"""
Pass 3 Go-Live Recovery — Operational Hardening Tests

Validates:
- Scheduler observability state
- Trade staggerer duplicate queue prevention
- Heartbeat registry watchdog
- Diagnostic endpoint contracts
- Trading gate integrity

Run with:
  PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest tests/test_pass3_go_live.py -v
"""

import os
import sys
import re
import ast
import pytest

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

# Ensure test-safe environment
os.environ.setdefault("ENVIRONMENT", "testing")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-testing-only")


# =====================================================================
# SCHEDULER OBSERVABILITY
# =====================================================================

class TestSchedulerObservability:
    """Verify trading scheduler has proper observability state."""

    def test_scheduler_has_health_snapshot_method(self):
        from trading_scheduler import TradingScheduler
        sched = TradingScheduler()
        assert hasattr(sched, 'get_health_snapshot')
        snap = sched.get_health_snapshot()
        assert isinstance(snap, dict)

    def test_scheduler_health_snapshot_fields(self):
        from trading_scheduler import TradingScheduler
        sched = TradingScheduler()
        snap = sched.get_health_snapshot()
        required_fields = [
            "scheduler_running",
            "task_alive",
            "last_heartbeat",
            "check_interval_seconds",
            "last_tick_at",
            "last_tick_bots",
            "last_tick_queued",
            "last_tick_executed",
            "last_tick_noop_reason",
            "last_trade_at",
            "last_trade_bot",
            "last_trade_result",
            "total_ticks",
            "total_trades_executed",
            "total_noop_ticks",
            "queue_size",
            "active_trades",
            "timestamp",
        ]
        for field in required_fields:
            assert field in snap, f"Missing field: {field}"

    def test_scheduler_initial_state_not_running(self):
        from trading_scheduler import TradingScheduler
        sched = TradingScheduler()
        snap = sched.get_health_snapshot()
        assert snap["scheduler_running"] is False
        assert snap["task_alive"] is False
        assert snap["total_ticks"] == 0
        assert snap["total_trades_executed"] == 0

    def test_scheduler_tick_counters_are_integers(self):
        from trading_scheduler import TradingScheduler
        sched = TradingScheduler()
        snap = sched.get_health_snapshot()
        assert isinstance(snap["total_ticks"], int)
        assert isinstance(snap["total_trades_executed"], int)
        assert isinstance(snap["total_noop_ticks"], int)
        assert isinstance(snap["last_tick_bots"], int)

    def test_bot_pause_reason_codes_defined(self):
        from trading_scheduler import BotPauseReason
        required = [
            "MODE_DISABLED", "NO_EXCHANGE_KEYS", "RISK_STOP",
            "EMERGENCY_STOP", "BUDGET_EXHAUSTED", "USER_PAUSED",
            "UNSUPPORTED_EXCHANGE", "DAILY_LOSS_LOCK",
        ]
        for code in required:
            assert hasattr(BotPauseReason, code)
            assert isinstance(getattr(BotPauseReason, code), str)


# =====================================================================
# TRADE STAGGERER DEDUP
# =====================================================================

class TestTradeStaggererDedup:
    """Verify trade_staggerer prevents duplicate queue spam."""

    def test_staggerer_has_trade_queue_attribute(self):
        from engines.trade_staggerer import TradeStaggerer
        ts = TradeStaggerer()
        assert hasattr(ts, 'trade_queue')
        assert len(ts.trade_queue) == 0

    def test_staggerer_queue_is_deque(self):
        from engines.trade_staggerer import TradeStaggerer
        from collections import deque
        ts = TradeStaggerer()
        assert isinstance(ts.trade_queue, deque)

    def test_scheduler_dedup_check_in_source(self):
        """The scheduler must check queued_bot_ids before adding to queue."""
        scheduler_path = os.path.join(
            os.path.dirname(__file__), '..', 'backend', 'trading_scheduler.py'
        )
        with open(scheduler_path) as f:
            source = f.read()
        # Must contain dedup logic
        assert 'queued_bot_ids' in source, "Scheduler must check for duplicate bot_ids in queue"
        assert 'if bot_id in queued_bot_ids' in source, "Scheduler must skip bots already in queue"


# =====================================================================
# HEARTBEAT REGISTRY WATCHDOG
# =====================================================================

class TestHeartbeatRegistryWatchdog:
    """Verify heartbeat registry has watchdog/stale detection."""

    def test_registry_has_check_stale_method(self):
        from services.autonomy_heartbeat import AutonomyHeartbeatRegistry
        reg = AutonomyHeartbeatRegistry()
        assert hasattr(reg, 'check_stale')

    def test_check_stale_returns_all_subsystems(self):
        from services.autonomy_heartbeat import AutonomyHeartbeatRegistry, DEFAULT_SUBSYSTEMS
        reg = AutonomyHeartbeatRegistry()
        stale = reg.check_stale()
        for subsystem in DEFAULT_SUBSYSTEMS:
            assert subsystem in stale, f"Missing subsystem: {subsystem}"

    def test_check_stale_fields(self):
        from services.autonomy_heartbeat import AutonomyHeartbeatRegistry
        reg = AutonomyHeartbeatRegistry()
        stale = reg.check_stale()
        for subsystem, info in stale.items():
            assert "alive" in info
            assert "stale_seconds" in info
            assert "threshold" in info

    def test_fresh_heartbeat_is_alive(self):
        from services.autonomy_heartbeat import AutonomyHeartbeatRegistry
        reg = AutonomyHeartbeatRegistry()
        reg.mark_ok("trading_scheduler")
        stale = reg.check_stale()
        assert stale["trading_scheduler"]["alive"] is True
        assert stale["trading_scheduler"]["stale_seconds"] is not None
        assert stale["trading_scheduler"]["stale_seconds"] < 5  # Just marked

    def test_no_heartbeat_is_not_alive(self):
        from services.autonomy_heartbeat import AutonomyHeartbeatRegistry
        reg = AutonomyHeartbeatRegistry()
        stale = reg.check_stale()
        assert stale["trading_scheduler"]["alive"] is False
        assert stale["trading_scheduler"]["stale_seconds"] is None

    def test_daily_loss_reset_in_subsystems(self):
        from services.autonomy_heartbeat import DEFAULT_SUBSYSTEMS
        assert "daily_loss_reset" in DEFAULT_SUBSYSTEMS

    def test_trading_scheduler_in_subsystems(self):
        from services.autonomy_heartbeat import DEFAULT_SUBSYSTEMS
        assert "trading_scheduler" in DEFAULT_SUBSYSTEMS


# =====================================================================
# DIAGNOSTIC ENDPOINT CONTRACTS
# =====================================================================

class TestDiagnosticEndpoints:
    """Verify diagnostic route source code contracts."""

    def test_go_live_endpoint_exists(self):
        diag_path = os.path.join(
            os.path.dirname(__file__), '..', 'backend', 'routes', 'diagnostics.py'
        )
        with open(diag_path) as f:
            source = f.read()
        assert '"/go-live"' in source, "go-live endpoint must exist in diagnostics.py"

    def test_scheduler_health_endpoint_exists(self):
        diag_path = os.path.join(
            os.path.dirname(__file__), '..', 'backend', 'routes', 'diagnostics.py'
        )
        with open(diag_path) as f:
            source = f.read()
        assert '"/scheduler-health"' in source

    def test_reset_proof_endpoint_exists(self):
        diag_path = os.path.join(
            os.path.dirname(__file__), '..', 'backend', 'routes', 'diagnostics.py'
        )
        with open(diag_path) as f:
            source = f.read()
        assert '"/reset-proof"' in source

    def test_paper_activity_endpoint_exists(self):
        diag_path = os.path.join(
            os.path.dirname(__file__), '..', 'backend', 'routes', 'diagnostics.py'
        )
        with open(diag_path) as f:
            source = f.read()
        assert '"/paper-activity"' in source

    def test_go_live_checks_scheduler(self):
        """go-live endpoint must check scheduler health."""
        diag_path = os.path.join(
            os.path.dirname(__file__), '..', 'backend', 'routes', 'diagnostics.py'
        )
        with open(diag_path) as f:
            source = f.read()
        # Find the go_live_diagnostic function
        assert 'get_health_snapshot' in source, "go-live must use scheduler health snapshot"

    def test_go_live_checks_risk(self):
        """go-live endpoint must check risk status."""
        diag_path = os.path.join(
            os.path.dirname(__file__), '..', 'backend', 'routes', 'diagnostics.py'
        )
        with open(diag_path) as f:
            source = f.read()
        assert 'emergency_stop' in source

    def test_risk_summary_endpoint_exists(self):
        """risk_management.py must have /api/risk/summary."""
        risk_path = os.path.join(
            os.path.dirname(__file__), '..', 'backend', 'routes', 'risk_management.py'
        )
        with open(risk_path) as f:
            source = f.read()
        assert '/api/risk/summary' in source


# =====================================================================
# TRADING GATES INTEGRITY
# =====================================================================

class TestTradingGatesIntegrity:
    """Verify risk/training/live gates remain intact."""

    def test_trading_gates_module_exists(self):
        from utils.trading_gates import enforce_live_trading_gates, TradingGateError
        assert callable(enforce_live_trading_gates)

    def test_trading_mode_validator_exists(self):
        from services.trading_mode_validator import trading_mode_validator
        assert hasattr(trading_mode_validator, 'validate_bot_trading_mode')

    def test_risk_lock_service_exists(self):
        from services.risk_lock_service import risk_lock_service
        assert hasattr(risk_lock_service, 'is_locked_today')

    def test_system_gate_exists(self):
        from services.system_gate import system_gate
        assert hasattr(system_gate, 'validate_scheduler_tick')

    def test_live_gate_service_exists(self):
        from services.live_gate_service import live_gate_service
        assert hasattr(live_gate_service, 'can_place_order')

    def test_quarantine_service_exists(self):
        from services.bot_quarantine import quarantine_service
        assert hasattr(quarantine_service, 'quarantine_bot')


# =====================================================================
# RESET / ADMIN INFRASTRUCTURE
# =====================================================================

class TestResetInfrastructure:
    """Verify reset endpoints and orchestration exist."""

    def test_admin_start_fresh_route_exists(self):
        route_path = os.path.join(
            os.path.dirname(__file__), '..', 'backend', 'routes', 'admin_start_fresh.py'
        )
        with open(route_path) as f:
            source = f.read()
        assert 'start-fresh' in source

    def test_admin_start_fresh_clears_paper_wallets(self):
        route_path = os.path.join(
            os.path.dirname(__file__), '..', 'backend', 'routes', 'admin_start_fresh.py'
        )
        with open(route_path) as f:
            source = f.read()
        assert 'paper_wallet' in source.lower() or 'wallet' in source.lower()

    def test_admin_start_fresh_clears_risk_locks(self):
        route_path = os.path.join(
            os.path.dirname(__file__), '..', 'backend', 'routes', 'admin_start_fresh.py'
        )
        with open(route_path) as f:
            source = f.read()
        assert 'risk_lock' in source.lower() or 'daily_loss' in source.lower() or 'emergency_stop' in source.lower()


# =====================================================================
# SOURCE CONSISTENCY
# =====================================================================

class TestSourceConsistency:
    """Verify no /api/api/ double prefix issues, no dead imports."""

    def test_no_double_api_prefix_in_routes(self):
        """Route files must not create /api/api/ paths."""
        routes_dir = os.path.join(
            os.path.dirname(__file__), '..', 'backend', 'routes'
        )
        violations = []
        for fname in os.listdir(routes_dir):
            if not fname.endswith('.py'):
                continue
            fpath = os.path.join(routes_dir, fname)
            with open(fpath) as f:
                for lineno, line in enumerate(f, 1):
                    if '/api/api/' in line and not line.strip().startswith('#'):
                        violations.append(f"{fname}:{lineno}")
        assert len(violations) == 0, f"Double /api/api/ found in: {violations}"

    def test_all_modified_files_parse(self):
        """All key backend files must parse without syntax errors."""
        backend_dir = os.path.join(os.path.dirname(__file__), '..', 'backend')
        files = [
            'trading_scheduler.py',
            'services/autonomy_heartbeat.py',
            'routes/diagnostics.py',
            'engines/trade_staggerer.py',
        ]
        for f in files:
            fpath = os.path.join(backend_dir, f)
            with open(fpath) as fh:
                try:
                    ast.parse(fh.read())
                except SyntaxError as e:
                    pytest.fail(f"Syntax error in {f}: {e}")
