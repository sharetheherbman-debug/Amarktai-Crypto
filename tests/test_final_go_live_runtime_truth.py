"""
Final runtime truth guards for paper-trading go-live.
"""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def test_capital_validator_uses_bot_allocations_as_canonical():
    src = _read("backend/services/capital_validator.py")
    assert "def _bot_allocated_value" in src
    assert '"allocated_capital" in bot_doc' in src
    assert "allocated_balance = round(total_bot_capital, 2)" in src
    assert '"allocated_balance": allocated_balance' in src
    assert 'db.users_collection.update_one(' in src


def test_countdown_uses_closed_trades_not_fills():
    src = _read("backend/server.py")
    assert 'db.trades_collection.count_documents' in src
    assert '"status": "closed"' in src
    assert '"trade_count_source": "closed_trades_documents"' in src

    ledger_src = _read("backend/routes/ledger_endpoints.py")
    assert 'db["trades"].count_documents' in ledger_src
    assert '"status": "closed"' in ledger_src


def test_countdown_uses_canonical_capital_source_priority():
    src = _read("backend/server.py")
    assert 'capital_source = "ledger_equity_zar"' in src
    assert 'capital_source = "bots_current_capital_sum"' in src
    assert 'capital_source = "wallet_snapshot"' in src


def test_paper_engine_close_path_keeps_trade_currency_consistent():
    src = _read("backend/paper_trading_engine.py")
    assert "def _resolve_quote_currency" in src
    assert "open_trade.get(\"fee_currency\")" in src
    assert "trade_result.get(\"fee_currency\")" in src


def test_bot_validator_enforces_scalper_and_normal_caps():
    src = _read("backend/validators/bot_validator.py")
    assert "SCALPER_GLOBAL_CAP_REACHED" in src
    assert "SCALPER_EXCHANGE_CAP_REACHED" in src
    assert "NORMAL_EXCHANGE_CAP_REACHED" in src


def test_dashboard_realtime_trade_events_refresh_canonical_trade_truth():
    src = _read("frontend/src/hooks/useDashboardState.js")
    assert "case 'trade_executed'" in src
    assert "case 'trade_opened'" in src
    assert "case 'trade_closed'" in src
    assert "case 'analytics_update'" in src
    assert "loadRecentTrades();" in src


def test_dashboard_data_hook_handles_trade_event_variants():
    src = _read("frontend/src/hooks/useDashboardData.js")
    assert "realtimeClient.on('trade_executed'" in src
    assert "realtimeClient.on('trade_opened'" in src
    assert "realtimeClient.on('trade_closed'" in src
    assert "realtimeClient.on('analytics_update'" in src
    assert "loadRecentTrades();" in src


def test_countdown_daily_roi_uses_canonical_trade_pnl_fields():
    src = _read("backend/routes/user_countdowns.py")
    assert 'trade.get("net_pnl")' in src
    assert 'trade.get("profit_loss", 0)' in src
    assert 't.get("realized_profit", 0)' not in src


def test_scheduler_uses_single_canonical_trade_websocket_emit_path():
    src = _read("backend/trading_scheduler.py")
    assert "Legacy WebSocket update" not in src
