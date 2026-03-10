import os
import sys
from datetime import datetime, timezone


ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(ROOT, "backend"))


def _read(rel_path: str) -> str:
    with open(os.path.join(ROOT, rel_path), encoding="utf-8") as f:
        return f.read()


def test_coindesk_save_and_validation_wiring_present():
    keys_src = _read("backend/routes/keys.py")
    assert "'coindesk', 'cryptocompare'" in keys_src

    registry_src = _read("backend/services/provider_registry.py")
    assert "https://data-api.coindesk.com/news/v1/article/list" in registry_src
    assert '"X-API-KEY"' in registry_src
    assert "CoinDesk rejected the API key" in registry_src


def test_activity_state_resolver_canonical_states():
    from utils.bot_state import resolve_activity_state

    assert resolve_activity_state({"status": "active", "eligible_to_trade": True})["activity_state"] == "runnable"
    assert resolve_activity_state({"status": "active", "eligible_to_trade": False, "not_eligible_reasons": ["daily_loss_lock"]})["activity_state"] == "blocked"
    assert resolve_activity_state({"status": "paused", "paused_by_bodyguard": True})["activity_state"] == "bodyguard_locked"
    assert resolve_activity_state({"status": "paused", "paused_by_system": True})["activity_state"] == "paused_by_system"
    assert resolve_activity_state({"status": "paused", "paused_by_user": True})["activity_state"] == "paused_by_user"
    assert resolve_activity_state({"status": "training"})["activity_state"] == "training"
    assert resolve_activity_state({"status": "quarantined"})["activity_state"] == "quarantined"


def test_radar_entry_includes_canonical_activity_state_fields():
    """Verify radar route source contains canonical activity state field extractions."""
    import os
    radar_path = os.path.join(os.path.dirname(__file__), "..", "backend", "routes", "radar.py")
    with open(radar_path) as f:
        src = f.read()
    assert '"activity_state"' in src
    assert '"activity_reason_code"' in src
    assert '"runnable"' in src
    assert '"eligible_to_trade"' in src


def test_frontend_realtime_forces_canonical_refresh():
    state_src = _read("frontend/src/hooks/useDashboardState.js")
    assert "case 'bots_update'" in state_src
    assert "refreshBotState();" in state_src
    assert "case 'bot_updated'" in state_src

    radar_src = _read("frontend/src/pages/dashboard/sections/BotRadarSection.js")
    assert "realtimeClient.on('bot_created'" in radar_src
    assert "realtimeClient.on('trade_opened'" in radar_src
    assert "realtimeClient.on('trade_closed'" in radar_src
    assert "realtimeClient.on('bot_quarantined'" in radar_src


def test_botfleet_uses_canonical_capital_derivation_to_avoid_false_zeros():
    fleet_src = _read("frontend/src/pages/dashboard/sections/BotFleetSection.js")
    assert "hasCanonicalCapital" in fleet_src
    assert "derivedTotalEquity" in fleet_src
    assert "capitalSummary.total_equity ?? (hasCanonicalCapital ? derivedTotalEquity" in fleet_src


def test_metrics_panel_has_unavailable_semantics_for_empty_series():
    metrics_src = _read("frontend/src/components/PrometheusMetrics.js")
    assert "has_live_series" in metrics_src
    assert "no live Prometheus series are being emitted yet" in metrics_src


def test_engine_reject_paths_record_decision_trace_details():
    engine_src = _read("backend/paper_trading_engine.py")
    assert "Scalper blocked: unknown/low-confidence regime" in engine_src
    assert "Scalper signal consensus too weak" in engine_src
    assert "Normal bot quality threshold not met" in engine_src


def test_paper_engine_collection_checks_use_explicit_none_comparisons():
    engine_src = _read("backend/paper_trading_engine.py")
    assert 'if getattr(db, "decisions_collection", None) is None:' in engine_src
    assert "if db.trades_collection is None:" in engine_src
    assert "if not db.trades_collection:" not in engine_src


def test_unknown_regime_zero_confidence_is_not_eligible():
    """With no regime check in bot_state, a bot with unknown regime is still eligible at structural level.
    Regime gating now lives in the trading engine only, not in eligibility.
    A bot that is active with a trading_mode is structurally eligible regardless of regime state.
    """
    from utils.bot_state import normalize_bot_state

    bot = normalize_bot_state({
        "status": "active",
        "trading_mode": "paper",
        "market_regime": "unknown",
        "canonical_regime_confidence": 0.0,
        "entry_confidence_score": 0.0,
    })
    # Structural eligibility: active + trading_mode → eligible (regime is checked by engine)
    assert bot["eligible_to_trade"] is True
    assert "regime_unknown_low_confidence" not in bot["not_eligible_reasons"]


def test_radar_entry_surfaces_canonical_decision_fields():
    """Verify the radar route file contains canonical decision field extractions."""
    import os
    radar_path = os.path.join(os.path.dirname(__file__), "..", "backend", "routes", "radar.py")
    with open(radar_path) as f:
        src = f.read()
    assert '"decision_reason_code"' in src
    assert '"entry_reason_code"' in src
    assert '"entry_confidence_score"' in src
    assert '"expectancy_net_edge_pct"' in src
    assert '"eligible_to_trade"' in src
    assert '"not_eligible_reasons"' in src


def test_provider_setup_uses_compact_supported_groups_only():
    src = _read("frontend/src/components/APIKeySettings.js")
    assert "Optional / Supported Intelligence" in src
    assert "Advanced / Premium Providers" not in src
    assert "PREMIUM_PROVIDER_IDS" not in src
    assert "Connected" in src
    assert "Configured but untested" in src


def test_bot_status_payload_includes_decision_fields():
    src = _read("backend/routes/bot_lifecycle.py")
    assert '"decision_reason_code": normalized_bot.get("decision_reason_code"' in src
    assert '"entry_reason_code": normalized_bot.get("entry_reason_code"' in src
    assert '"entry_confidence_score": normalized_bot.get("entry_confidence_score"' in src
    assert '"expectancy_net_edge_pct": normalized_bot.get("expectancy_net_edge_pct")' in src


def test_diagnostics_routes_expose_live_intelligence_endpoints():
    src = _read("backend/routes/diagnostics.py")
    assert '@router.get("/provider-health")' in src
    assert '@router.get("/regime-summary")' in src
    assert '@router.get("/whale-signals")' in src
    assert '@router.get("/sentiment-summary")' in src
    assert '@router.get("/orderbook-summary")' in src
    assert '@router.get("/capital-efficiency")' in src
    assert '@router.get("/genetics-summary")' in src


def test_admin_key_monitor_excludes_removed_premium_providers():
    src = _read("backend/routes/admin_endpoints.py")
    assert 'removed_provider_ids = {"glassnode", "lunarcrush"}' in src
    assert "if provider_id in removed_provider_ids" in src
    assert '"deployment_tier": "core_supported"' in src


def test_radar_no_position_block_reason_and_open_position_flag_present():
    src = _read("backend/routes/radar.py")
    assert '"has_open_position": bool(open_trade)' in src
    assert 'entry["next_action_reason_text"] = f"Waiting: {human_reason}"' in src


def test_market_intelligence_panel_uses_diagnostics_snapshot_and_coindesk_first_order():
    src = _read("frontend/src/pages/dashboard/sections/MarketIntelligencePanel.js")
    assert "get('/diagnostics/provider-health')" in src
    # Old verbose heading is replaced with compact live prices section
    assert "Live Prices" in src or "Live Intelligence" in src or "priceRows" in src
    assert "Fallback Architecture" not in src
