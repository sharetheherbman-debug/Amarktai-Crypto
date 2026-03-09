"""
Source-level regression checks for remaining go-live blocker fixes.
"""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def test_coindesk_is_canonical_market_data_primary():
    registry = _read("backend/services/provider_registry.py")
    assert '"coindesk": ProviderDefinition(' in registry
    assert registry.index('"coindesk": ProviderDefinition(') < registry.index('"cryptocompare": ProviderDefinition(')

    engine = _read("backend/engines/market_intelligence_engine.py")
    assert 'self._priority = priority or ["coindesk", "cryptocompare", "coingecko", "coinranking"]' in engine


def test_build_ping_exposes_provenance_metadata():
    health = _read("backend/routes/health.py")
    assert "def get_build_metadata()" in health
    assert '"build": get_build_metadata()' in health
    assert '"build_hash": get_build_hash()' in health


def test_admin_key_monitor_endpoint_exists_and_is_admin_scoped():
    admin = _read("backend/routes/admin_endpoints.py")
    assert '@router.get("/key-monitor")' in admin
    assert "Depends(require_admin)" in admin
    assert "fallback_priority" in admin
    assert "estimated_call_usage" in admin


def test_queue_drift_cleanup_hooks_wired():
    staggerer = _read("backend/engines/trade_staggerer.py")
    assert "async def purge_orphaned_queue" in staggerer
    assert "async def clear_bot" in staggerer
    assert "async def clear_user" in staggerer

    scheduler = _read("backend/trading_scheduler.py")
    assert "await trade_staggerer.purge_orphaned_queue(active_bot_ids)" in scheduler

    server = _read("backend/server.py")
    assert "await trade_staggerer.purge_orphaned_queue()" in server

    lifecycle = _read("backend/routes/bot_lifecycle.py")
    assert "await trade_staggerer.clear_bot(bot_id)" in lifecycle

    mode = _read("backend/routes/system_mode.py")
    assert "await trade_staggerer.clear_user(user_id)" in mode


def test_growth_and_spawn_block_reasons_include_required_available_reserved():
    growth_service = _read("backend/services/autopilot_growth.py")
    assert '"min_capital_required"' in growth_service
    assert '"available_capital"' in growth_service
    assert '"reserved_capital"' in growth_service
    assert '"shortfall_capital"' in growth_service
    assert '"block_reason_details"' in growth_service

    spawner = _read("backend/engines/bot_spawner.py")
    assert '"min_required"' in spawner
    assert '"available"' in spawner
    assert '"reserved"' in spawner
    assert '"shortfall"' in spawner


def test_admin_ui_wires_key_monitor():
    hook = _read("frontend/src/hooks/useDashboardState.js")
    assert "const [adminKeyMonitor, setAdminKeyMonitor]" in hook
    assert "const loadAdminKeyMonitor = useCallback" in hook
    assert "axios.get(`${API}/admin/key-monitor`" in hook

    dashboard = _read("frontend/src/pages/Dashboard.js")
    assert "adminKeyMonitor={adminKeyMonitor}" in dashboard

    section = _read("frontend/src/pages/dashboard/sections/AdminPanelSection.js")
    assert "API Key Monitor (Admin)" in section
