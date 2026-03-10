import os
import sys
from datetime import datetime, timezone
import re

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))


def test_radar_targets_not_fabricated_when_unconfigured():
    from routes.radar import _compute_radar_entry

    bot = {
        "id": "bot-a",
        "name": "A",
        "bot_type": "normal",
        "risk_mode": "balanced",
        "current_capital": 1000,
    }
    entry = _compute_radar_entry(bot, None, datetime.now(timezone.utc))
    assert entry["daily_profit_target"] is None
    assert entry["trade_profit_target"] is None
    assert entry["target_source"] == "not_configured"


def test_radar_targets_use_configured_values():
    from routes.radar import _compute_radar_entry

    bot = {
        "id": "bot-b",
        "name": "B",
        "bot_type": "normal",
        "risk_mode": "balanced",
        "current_capital": 1000,
        "daily_profit_target_pct": 0.02,
        "trade_profit_target_pct": 0.01,
    }
    entry = _compute_radar_entry(bot, None, datetime.now(timezone.utc))
    assert entry["daily_profit_target"] == 20.0
    assert entry["trade_profit_target"] == 10.0
    assert entry["target_source"] == "configured"


def test_hold_policy_single_source_scalper_and_normal():
    from services.hold_policy import resolve_hold_policy

    scalper = resolve_hold_policy({"bot_type": "scalper"})
    normal = resolve_hold_policy({"bot_type": "normal", "risk_mode": "balanced"})
    assert scalper["max_hold_seconds"] == 300
    assert normal["max_hold_seconds"] == 3600


def test_radar_and_engine_share_hold_policy_resolver():
    radar_path = os.path.join(os.path.dirname(__file__), "..", "backend", "routes", "radar.py")
    engine_path = os.path.join(os.path.dirname(__file__), "..", "backend", "paper_trading_engine.py")
    with open(radar_path) as f:
        radar_source = f.read()
    with open(engine_path) as f:
        engine_source = f.read()
    assert "from services.hold_policy import resolve_hold_policy" in radar_source
    assert "from services.hold_policy import resolve_hold_policy" in engine_source
    assert "resolve_hold_policy(" in radar_source
    assert "resolve_hold_policy(" in engine_source


def test_overview_uses_canonical_open_position_source():
    path = os.path.join(os.path.dirname(__file__), "..", "backend", "routes", "dashboard_overview.py")
    with open(path) as f:
        source = f.read()
    assert "get_canonical_open_position_count" in source
    assert "positions_collection.count_documents" not in source


def test_countdown_uses_paper_wallet_total_equity_source():
    path = os.path.join(os.path.dirname(__file__), "..", "backend", "server.py")
    with open(path) as f:
        source = f.read()
    assert "get_canonical_paper_wallet_equity" in source
    assert 'capital_source = paper_equity["source"]' in source


def test_scalper_edge_gate_is_stricter():
    path = os.path.join(os.path.dirname(__file__), "..", "backend", "paper_trading_engine.py")
    with open(path) as f:
        source = f.read()
    assert "estimated_cost_pct * 2.25" in source
    assert "edge_required_pct + 0.35" in source
    assert "scalper_conflicting_signals" in source


def test_frontend_bot_metrics_use_canonical_capital_summary():
    path = os.path.join(
        os.path.dirname(__file__),
        "..",
        "frontend",
        "src",
        "pages",
        "dashboard",
        "sections",
        "BotFleetSection.js",
    )
    with open(path) as f:
        source = f.read()
    assert "capital_summary" in source
    assert "Total Equity" in source
    assert "Initial Capital" in source
    assert "Allocated Capital" in source


def test_engine_has_early_exit_reasons_before_timeout_fallback():
    path = os.path.join(os.path.dirname(__file__), "..", "backend", "paper_trading_engine.py")
    with open(path) as f:
        source = f.read()
    assert "scalper_no_progress_exit" in source
    assert "normal_no_progress_exit" in source
    assert "regime_deterioration_exit" in source
    assert "if not close_reason and age_seconds >= max_hold_seconds" in source


def test_frontend_bots_update_refreshes_canonical_status():
    path = os.path.join(
        os.path.dirname(__file__),
        "..",
        "frontend",
        "src",
        "hooks",
        "useDashboardData.js",
    )
    with open(path) as f:
        source = f.read()
    assert re.search(r"realtimeClient\.on\(['\"]bots_update['\"],\s*\(\)\s*=>\s*\{", source)
    assert re.search(r"\bloadBots\(\)\s*;", source)
    assert re.search(r"\[\s*token\s*,\s*loadRecentTrades\s*,\s*loadCountdown\s*,\s*loadMetrics\s*,\s*loadBots\s*\]", source)


def test_frontend_activity_counts_distinguish_runnable_vs_active():
    hook_path = os.path.join(
        os.path.dirname(__file__),
        "..",
        "frontend",
        "src",
        "hooks",
        "useDashboardData.js",
    )
    with open(hook_path) as f:
        source = f.read()
    assert "runnable /" in source
    assert "runnableBots" in source
