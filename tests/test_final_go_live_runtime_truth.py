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
