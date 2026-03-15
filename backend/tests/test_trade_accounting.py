import pytest
import sys
from pathlib import Path

backend_path = Path(__file__).parent.parent
sys.path.insert(0, str(backend_path))

from utils.trade_utils import calculate_trade_pnl, classify_trade_outcome


def test_trade_pnl_winning_trade():
    result = calculate_trade_pnl(entry_value=1000, exit_value=1100, fees=2, slippage=1)
    assert result["gross_profit"] == pytest.approx(100)
    assert result["net_profit"] == pytest.approx(97)
    # With context: net_profit=97 on 1000 notional (9.7% ROI) → QUALIFIED_WIN
    outcome = classify_trade_outcome(
        result["net_profit"],
        gross_profit=result["gross_profit"],
        notional=1000.0,
        venue="binance",
        strategy="normal",
        bot_equity=1000.0,
        fees=2.0,
        slippage=1.0,
    )
    assert outcome["win_count"] == 1
    assert outcome["qualified_win_count"] == 1
    assert outcome["loss_count"] == 0
    assert outcome["net_green_count"] == 1


def test_trade_pnl_losing_trade():
    result = calculate_trade_pnl(entry_value=1000, exit_value=900, fees=2, slippage=1)
    assert result["gross_profit"] == pytest.approx(-100)
    assert result["net_profit"] == pytest.approx(-103)
    outcome = classify_trade_outcome(result["net_profit"])
    assert outcome["win_count"] == 0
    assert outcome["loss_count"] == 1


def test_trade_pnl_flat_trade():
    result = calculate_trade_pnl(entry_value=1000, exit_value=1000, fees=0, slippage=0)
    assert result["gross_profit"] == pytest.approx(0)
    assert result["net_profit"] == pytest.approx(0)
    outcome = classify_trade_outcome(result["net_profit"])
    # net_pnl=0: not a win, and flat trades don't increment loss_count either
    assert outcome["win_count"] == 0
    assert outcome["qualified_win_count"] == 0
    assert outcome["net_green_count"] == 0
    assert outcome["loss_count"] == 0  # flat trades excluded from loss counter


def test_trade_pnl_fee_only_loss():
    result = calculate_trade_pnl(entry_value=1000, exit_value=1000, fees=5, slippage=0)
    assert result["gross_profit"] == pytest.approx(0)
    assert result["net_profit"] == pytest.approx(-5)
    outcome = classify_trade_outcome(result["net_profit"])
    assert outcome["win_count"] == 0
    assert outcome["loss_count"] == 1


def test_trade_pnl_partial_close_win():
    result = calculate_trade_pnl(entry_value=500, exit_value=525, fees=1, slippage=0.5)
    assert result["gross_profit"] == pytest.approx(25)
    assert result["net_profit"] == pytest.approx(23.5)
    # With context: net_profit=23.5 on 500 notional (4.7% ROI) → QUALIFIED_WIN
    outcome = classify_trade_outcome(
        result["net_profit"],
        gross_profit=result["gross_profit"],
        notional=500.0,
        venue="binance",
        strategy="normal",
        bot_equity=500.0,
        fees=1.0,
        slippage=0.5,
    )
    assert outcome["win_count"] == 1
    assert outcome["qualified_win_count"] == 1
    assert outcome["loss_count"] == 0
