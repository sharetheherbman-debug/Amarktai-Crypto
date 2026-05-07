import os
import sys

backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, backend_dir)


def test_scheduler_gate_disabled_reason(monkeypatch):
    monkeypatch.setenv("ENABLE_TRADING", "false")
    monkeypatch.setenv("ENABLE_PAPER_TRADING", "false")
    monkeypatch.setenv("ENABLE_LIVE_TRADING", "false")
    from services.system_gate import SystemGateService

    gate = SystemGateService()
    should_run, reason = gate.validate_scheduler_tick()
    assert not should_run
    assert "Trading disabled" in reason


def test_scheduler_gate_enabled_reason(monkeypatch):
    monkeypatch.setenv("ENABLE_TRADING", "true")
    monkeypatch.setenv("ENABLE_PAPER_TRADING", "true")
    monkeypatch.setenv("ENABLE_LIVE_TRADING", "false")
    from services.system_gate import SystemGateService

    gate = SystemGateService()
    should_run, reason = gate.validate_scheduler_tick()
    assert should_run
    assert "Scheduler can proceed" in reason
