"""
Tests for Phase 1 deliverables:
  - Position lifecycle model
  - Exchange adapter
  - Daily close job
  - Radar snapshot computation
  - Bot state canonicalization
  - Data integrity endpoint structure
"""

import sys
import os
import pytest
from datetime import datetime, timezone, timedelta

# Ensure backend is on the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))


# ============================================================================
# Position Lifecycle Tests
# ============================================================================

class TestPositionLifecycle:
    """Tests for services/position_lifecycle.py"""

    def test_compute_position_limits_buy(self):
        from services.position_lifecycle import compute_position_limits
        limits = compute_position_limits(entry_price=100.0, side="buy", risk_mode="balanced")
        assert limits["take_profit"] > 100.0, "TP should be above entry for buy"
        assert limits["stop_loss"] < 100.0, "SL should be below entry for buy"
        assert limits["max_hold_seconds"] == 3 * 3600, "Balanced = 3 hours"
        assert "trailing_activation_price" in limits
        assert "trailing_distance_pct" in limits

    def test_compute_position_limits_sell(self):
        from services.position_lifecycle import compute_position_limits
        limits = compute_position_limits(entry_price=100.0, side="sell", risk_mode="balanced")
        assert limits["take_profit"] < 100.0, "TP should be below entry for sell"
        assert limits["stop_loss"] > 100.0, "SL should be above entry for sell"

    def test_compute_position_limits_safe_mode(self):
        from services.position_lifecycle import compute_position_limits
        limits = compute_position_limits(entry_price=50000.0, side="buy", risk_mode="safe")
        assert limits["max_hold_seconds"] == 6 * 3600, "Safe = 6 hours"

    def test_compute_position_limits_aggressive_mode(self):
        from services.position_lifecycle import compute_position_limits
        limits = compute_position_limits(entry_price=50000.0, side="buy", risk_mode="aggressive")
        assert limits["max_hold_seconds"] == 90 * 60, "Aggressive = 90 minutes"

    def test_compute_position_limits_unknown_mode_defaults_to_balanced(self):
        from services.position_lifecycle import compute_position_limits
        limits = compute_position_limits(entry_price=100.0, side="buy", risk_mode="unknown")
        assert limits["max_hold_seconds"] == 3 * 3600

    def test_check_position_exit_time(self):
        from services.position_lifecycle import check_position_exit, TIME_EXIT
        opened = datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        now = datetime(2025, 1, 1, 4, 0, 0, tzinfo=timezone.utc)  # 4 hours later
        should_exit, code, text = check_position_exit(
            side="buy", entry_price=100.0, current_price=101.0,
            opened_at=opened, risk_mode="balanced", now=now,
        )
        assert should_exit is True
        assert code == TIME_EXIT

    def test_check_position_exit_target(self):
        from services.position_lifecycle import check_position_exit, TARGET_EXIT
        opened = datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        now = datetime(2025, 1, 1, 0, 30, 0, tzinfo=timezone.utc)
        should_exit, code, text = check_position_exit(
            side="buy", entry_price=100.0, current_price=110.0,
            opened_at=opened, risk_mode="balanced", tp=105.0, now=now,
        )
        assert should_exit is True
        assert code == TARGET_EXIT

    def test_check_position_exit_stop_loss(self):
        from services.position_lifecycle import check_position_exit, STOP_EXIT
        opened = datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        now = datetime(2025, 1, 1, 0, 30, 0, tzinfo=timezone.utc)
        should_exit, code, text = check_position_exit(
            side="buy", entry_price=100.0, current_price=90.0,
            opened_at=opened, risk_mode="balanced", sl=95.0, now=now,
        )
        assert should_exit is True
        assert code == STOP_EXIT

    def test_check_position_exit_trailing(self):
        from services.position_lifecycle import check_position_exit, TRAIL_EXIT
        opened = datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        now = datetime(2025, 1, 1, 0, 30, 0, tzinfo=timezone.utc)
        should_exit, code, text = check_position_exit(
            side="buy", entry_price=100.0, current_price=99.0,
            opened_at=opened, risk_mode="balanced",
            trailing_stop=99.5, now=now,
        )
        assert should_exit is True
        assert code == TRAIL_EXIT

    def test_check_position_exit_risk(self):
        from services.position_lifecycle import check_position_exit, RISK_EXIT
        opened = datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        now = datetime(2025, 1, 1, 0, 30, 0, tzinfo=timezone.utc)
        should_exit, code, text = check_position_exit(
            side="buy", entry_price=100.0, current_price=90.0,
            opened_at=opened, risk_mode="balanced",
            capital=1000.0, qty=10, now=now,
        )
        assert should_exit is True
        assert code == RISK_EXIT

    def test_check_position_no_exit(self):
        from services.position_lifecycle import check_position_exit
        opened = datetime(2025, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        now = datetime(2025, 1, 1, 0, 30, 0, tzinfo=timezone.utc)
        should_exit, code, text = check_position_exit(
            side="buy", entry_price=100.0, current_price=100.5,
            opened_at=opened, risk_mode="balanced",
            tp=105.0, sl=95.0, now=now,
        )
        assert should_exit is False
        assert code is None

    def test_compute_trailing_stop_buy(self):
        from services.position_lifecycle import compute_trailing_stop
        ts = compute_trailing_stop("buy", current_price=105.0, highest_price=110.0, lowest_price=100.0)
        assert ts is not None
        assert ts < 110.0

    def test_compute_trailing_stop_sell(self):
        from services.position_lifecycle import compute_trailing_stop
        ts = compute_trailing_stop("sell", current_price=95.0, highest_price=110.0, lowest_price=90.0)
        assert ts is not None
        assert ts > 90.0

    def test_reason_codes_are_strings(self):
        from services.position_lifecycle import (
            TIME_EXIT, STAGNATION_EXIT, RISK_EXIT,
            TARGET_EXIT, STOP_EXIT, TRAIL_EXIT,
        )
        for code in [TIME_EXIT, STAGNATION_EXIT, RISK_EXIT, TARGET_EXIT, STOP_EXIT, TRAIL_EXIT]:
            assert isinstance(code, str)
            assert len(code) > 0


# ============================================================================
# Exchange Adapter Tests
# ============================================================================

class TestExchangeAdapter:
    """Tests for services/exchange_adapter.py"""

    def test_supported_exchanges_count(self):
        from services.exchange_adapter import SUPPORTED_EXCHANGES
        assert len(SUPPORTED_EXCHANGES) == 7

    def test_all_seven_exchanges_listed(self):
        from services.exchange_adapter import SUPPORTED_EXCHANGES
        expected = {"luno", "binance", "kucoin", "bybit", "kraken", "bitget", "gate"}
        assert set(SUPPORTED_EXCHANGES) == expected

    def test_is_supported(self):
        from services.exchange_adapter import exchange_adapter
        assert exchange_adapter.is_supported("luno")
        assert exchange_adapter.is_supported("Binance")
        assert not exchange_adapter.is_supported("coinbase")

    def test_default_quote_luno_is_zar(self):
        from services.exchange_adapter import exchange_adapter
        assert exchange_adapter.get_default_quote("luno") == "ZAR"

    def test_default_quote_others_are_usdt(self):
        from services.exchange_adapter import exchange_adapter
        for ex in ["binance", "kucoin", "bybit", "kraken", "bitget", "gate"]:
            assert exchange_adapter.get_default_quote(ex) == "USDT", f"{ex} should default to USDT"

    def test_default_pairs_exist(self):
        from services.exchange_adapter import exchange_adapter
        for ex in ["luno", "binance", "kucoin", "bybit", "kraken", "bitget", "gate"]:
            pairs = exchange_adapter.get_default_pairs(ex)
            assert len(pairs) >= 2, f"{ex} should have at least 2 default pairs"

    def test_fee_rates_exist(self):
        from services.exchange_adapter import exchange_adapter
        for ex in ["luno", "binance", "kucoin", "bybit", "kraken", "bitget", "gate"]:
            fees = exchange_adapter.get_fee_rates(ex)
            assert "maker" in fees
            assert "taker" in fees
            assert fees["taker"] >= 0

    def test_simulate_fill_buy(self):
        from services.exchange_adapter import exchange_adapter
        fill = exchange_adapter.simulate_fill("binance", "buy", 50000.0, 0.001)
        assert fill["simulated"] is True
        assert fill["fill_price"] >= 50000.0  # Buy price includes slippage up
        assert fill["fee"] > 0

    def test_simulate_fill_sell(self):
        from services.exchange_adapter import exchange_adapter
        fill = exchange_adapter.simulate_fill("binance", "sell", 50000.0, 0.001)
        assert fill["fill_price"] <= 50000.0  # Sell price includes slippage down

    def test_simulate_fill_different_exchanges(self):
        from services.exchange_adapter import exchange_adapter
        for ex in ["luno", "binance", "kucoin", "bybit", "kraken", "bitget", "gate"]:
            fill = exchange_adapter.simulate_fill(ex, "buy", 100.0, 1.0)
            assert fill["exchange"] == ex
            assert fill["fee"] >= 0


# ============================================================================
# Daily Close Job Tests
# ============================================================================

class TestDailyClose:
    """Tests for jobs/daily_close.py"""

    def test_sast_now_offset(self):
        from jobs.daily_close import sast_now, SAST_OFFSET
        utc_now = datetime.now(timezone.utc)
        sast = sast_now()
        diff = (sast - utc_now).total_seconds()
        # Should be approximately 2 hours (7200 seconds)
        assert abs(diff - 7200) < 5, "SAST should be UTC+2"

    def test_sast_day_boundaries(self):
        from jobs.daily_close import sast_day_boundaries
        start, end = sast_day_boundaries()
        assert start < end
        diff = (end - start).total_seconds()
        assert diff == 86400, "Day should be exactly 24 hours"

    def test_make_run_id_deterministic(self):
        from jobs.daily_close import make_run_id
        id1 = make_run_id("2025-01-01", "user123")
        id2 = make_run_id("2025-01-01", "user123")
        assert id1 == id2, "Same inputs should produce same run_id"

    def test_make_run_id_different_dates(self):
        from jobs.daily_close import make_run_id
        id1 = make_run_id("2025-01-01", "user123")
        id2 = make_run_id("2025-01-02", "user123")
        assert id1 != id2, "Different dates should produce different run_ids"

    def test_score_bot_empty_fills(self):
        from jobs.daily_close import score_bot
        score = score_bot({"current_capital": 1000}, [])
        assert score == 0.0

    def test_score_bot_positive(self):
        from jobs.daily_close import score_bot
        fills = [
            {"realized_pnl": 10, "status": "filled"},
            {"realized_pnl": 5, "status": "filled"},
        ]
        score = score_bot({"current_capital": 1000}, fills)
        assert score > 0, "Profitable bot should have positive score"

    def test_score_bot_negative(self):
        from jobs.daily_close import score_bot
        fills = [
            {"realized_pnl": -50, "status": "filled"},
        ]
        score = score_bot({"current_capital": 1000, "max_drawdown_pct": 10}, fills)
        assert score < 0, "Losing bot with drawdown should have negative score"


# ============================================================================
# Bot State Canonicalization Tests
# ============================================================================

class TestBotStateCanonicalization:
    """Tests for utils/bot_state.py"""

    def test_normalize_active_bot(self):
        from utils.bot_state import normalize_bot_state
        bot = {"status": "active", "trading_mode": "paper"}
        result = normalize_bot_state(bot)
        assert result["active"] is True
        assert result["eligible_to_trade"] is True
        assert result["lifecycle_stage"] == "active"
        assert result["not_eligible_reasons"] == []

    def test_normalize_paused_bot(self):
        from utils.bot_state import normalize_bot_state
        bot = {"status": "paused", "trading_mode": "paper"}
        result = normalize_bot_state(bot)
        assert result["paused"] is True
        assert result["active"] is False
        assert result["eligible_to_trade"] is False
        assert "bot_paused" in result["not_eligible_reasons"]

    def test_normalize_deleted_bot(self):
        from utils.bot_state import normalize_bot_state
        bot = {"status": "deleted"}
        result = normalize_bot_state(bot)
        assert result["deleted"] is True
        assert result["eligible_to_trade"] is False

    def test_normalize_no_trading_mode(self):
        from utils.bot_state import normalize_bot_state
        bot = {"status": "active"}
        result = normalize_bot_state(bot)
        assert result["eligible_to_trade"] is False
        assert "no_trading_mode" in result["not_eligible_reasons"]

    def test_normalize_quarantined_bot(self):
        from utils.bot_state import normalize_bot_state
        bot = {"status": "active", "trading_mode": "paper", "quarantine_until": "2025-12-31"}
        result = normalize_bot_state(bot)
        assert result["eligible_to_trade"] is False
        assert "bot_quarantined" in result["not_eligible_reasons"]

    def test_normalize_circuit_breaker(self):
        from utils.bot_state import normalize_bot_state
        bot = {"status": "active", "trading_mode": "paper", "circuit_breaker_active": True}
        result = normalize_bot_state(bot)
        assert result["eligible_to_trade"] is False
        assert "circuit_breaker_active" in result["not_eligible_reasons"]

    def test_is_active_bot_true(self):
        from utils.bot_state import is_active_bot
        assert is_active_bot({"status": "active", "trading_mode": "paper"}) is True

    def test_is_active_bot_false(self):
        from utils.bot_state import is_active_bot
        assert is_active_bot({"status": "paused"}) is False


# ============================================================================
# Radar Snapshot Computation Tests
# ============================================================================

class TestRadarComputation:
    """Tests for routes/radar.py _compute_radar_entry"""

    @pytest.fixture(autouse=True)
    def _check_fastapi(self):
        try:
            from routes.radar import _compute_radar_entry  # noqa: F401
        except ImportError:
            pytest.skip("fastapi or other route dependencies not installed")

    def test_radar_entry_no_trade(self):
        from routes.radar import _compute_radar_entry
        now = datetime.now(timezone.utc)
        bot = {
            "_id": "bot123",
            "name": "TestBot",
            "exchange": "binance",
            "pair": "BTC/USDT",
            "current_capital": 1000,
            "risk_mode": "balanced",
        }
        entry = _compute_radar_entry(bot, None, now)
        assert entry["bot_id"] == "bot123"
        assert entry["side"] is None
        assert entry["next_action"] == "WAIT"
        assert entry["next_action_reason_code"] == "NO_POSITION"
        assert entry["daily_profit_target"] > 0
        assert entry["max_hold_seconds"] == 3 * 3600

    def test_radar_entry_with_trade(self):
        from routes.radar import _compute_radar_entry
        now = datetime.now(timezone.utc)
        bot = {
            "_id": "bot456",
            "name": "TestBot2",
            "exchange": "luno",
            "pair": "BTC/ZAR",
            "current_capital": 1000,
            "risk_mode": "safe",
        }
        trade = {
            "side": "buy",
            "entry_price": 50000.0,
            "current_price": 50100.0,
            "take_profit": 51000.0,
            "stop_loss": 49000.0,
            "quantity": 0.001,
            "opened_at": (now - timedelta(minutes=30)).isoformat(),
        }
        entry = _compute_radar_entry(bot, trade, now)
        assert entry["side"] == "buy"
        assert entry["entry_price"] == 50000.0
        assert entry["current_price"] == 50100.0
        assert entry["target_price"] == 51000.0
        assert entry["stop_price"] == 49000.0
        assert entry["remaining_hold_seconds"] is not None
        assert entry["remaining_hold_seconds"] > 0
        assert entry["next_action"] in ["HOLD", "WARN_EXIT", "FORCE_EXIT", "TARGET_EXIT", "STOP_EXIT", "TRAIL_EXIT"]

    def test_radar_entry_time_expired(self):
        from routes.radar import _compute_radar_entry
        now = datetime.now(timezone.utc)
        bot = {
            "_id": "bot789",
            "exchange": "binance",
            "pair": "BTC/USDT",
            "current_capital": 1000,
            "risk_mode": "aggressive",
        }
        # 2 hours ago, aggressive mode has 90min max hold
        trade = {
            "side": "buy",
            "entry_price": 50000.0,
            "current_price": 50100.0,
            "quantity": 0.001,
            "opened_at": (now - timedelta(hours=2)).isoformat(),
        }
        entry = _compute_radar_entry(bot, trade, now)
        assert entry["next_action"] == "FORCE_EXIT"
        assert entry["next_action_reason_code"] == "TIME_EXIT"
        assert entry["remaining_hold_seconds"] == 0

    def test_radar_entry_safe_mode_max_hold(self):
        from routes.radar import _compute_radar_entry
        now = datetime.now(timezone.utc)
        bot = {"_id": "bot_safe", "exchange": "luno", "pair": "BTC/ZAR",
               "current_capital": 1000, "risk_mode": "safe"}
        entry = _compute_radar_entry(bot, None, now)
        assert entry["max_hold_seconds"] == 6 * 3600


# ============================================================================
# Evidence Pack Script Tests
# ============================================================================

class TestEvidencePack:
    """Verify evidence pack script exists and is executable."""

    def test_script_exists(self):
        script_path = os.path.join(
            os.path.dirname(__file__), '..', 'scripts', 'evidence_pack.sh'
        )
        assert os.path.exists(script_path), "evidence_pack.sh should exist"

    def test_script_is_executable(self):
        script_path = os.path.join(
            os.path.dirname(__file__), '..', 'scripts', 'evidence_pack.sh'
        )
        assert os.access(script_path, os.X_OK), "evidence_pack.sh should be executable"

    def test_evidence_dir_exists(self):
        evidence_dir = os.path.join(
            os.path.dirname(__file__), '..', 'docs', 'evidence'
        )
        assert os.path.isdir(evidence_dir), "docs/evidence/ directory should exist"
