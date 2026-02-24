"""
Tests for Order Pipeline Production-Ready Features

Tests:
- Per-exchange daily caps (Luno 150, others 750)
- Per-bot cooldown (15s between orders)
- Rolling window cap (30 orders / 10 min)
- Rate limit backoff with exponential retry
- Spam pattern detection
- SignalEngine integration in Gate B
- Rejection logging + realtime broadcast
"""

import pytest
import asyncio
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from services.order_pipeline import OrderPipeline
from services.signal_engine import SignalEngine


@pytest.fixture
def mock_db():
    """Mock database with collections.

    Returns the same mock instance each time a collection is accessed by key so
    that test setup via ``mock_db["bot_cooldowns"] = ...`` is visible to the
    OrderPipeline that stored the reference at construction time.
    """
    _collections = {
        "pending_orders": AsyncMock(),
        "circuit_breaker_state": AsyncMock(),
        "bot_cooldowns": AsyncMock(),
        "rolling_windows": AsyncMock(),
        "spam_scores": AsyncMock(),
        "bots": AsyncMock(),
        "trades": AsyncMock(),
    }
    # Ensure default AsyncMock returns resolve to 0/None for count/find operations
    _collections["bot_cooldowns"].find_one = AsyncMock(return_value=None)
    _collections["rolling_windows"].count_documents = AsyncMock(return_value=0)
    _collections["bots"].count_documents = AsyncMock(return_value=1)
    _collections["circuit_breaker_state"].find_one = AsyncMock(return_value=None)
    _collections["pending_orders"].find_one = AsyncMock(return_value=None)
    _collections["pending_orders"].count_documents = AsyncMock(return_value=0)
    _collections["spam_scores"].find_one = AsyncMock(return_value=None)
    _collections["spam_scores"].update_one = AsyncMock()

    db = MagicMock()
    db.__getitem__ = lambda _, key: _collections.get(key, AsyncMock())
    db.__setitem__ = lambda _, key, val: _collections.__setitem__(key, val)

    return db


@pytest.fixture
def mock_ledger():
    """Mock ledger service"""
    ledger = AsyncMock()
    ledger.get_trade_count = AsyncMock(return_value=0)
    ledger.append_event = AsyncMock()
    ledger.compute_drawdown = AsyncMock(return_value=(0.05, 0.05))
    ledger.compute_daily_pnl = AsyncMock(return_value=100.0)
    ledger.compute_equity = AsyncMock(return_value=10000.0)
    ledger.get_consecutive_losses = AsyncMock(return_value=0)
    ledger.get_error_rate = AsyncMock(return_value=0)
    ledger.get_recent_trades = AsyncMock(return_value=[])
    return ledger


@pytest.fixture
def mock_signal_engine():
    """Mock signal engine"""
    from services.signal_engine import SignalOutput
    
    signal = SignalOutput(
        expected_edge_bps=50.0,
        confidence=0.8,
        regime='stable_uptrend',
        risk_score=0.3,
        suggested_order_type='limit',
        suggested_size_multiplier=1.0,
        rationale="Strong signal",
        diagnostics={}
    )
    
    engine = AsyncMock()
    engine.get_signal = AsyncMock(return_value=signal)
    return engine


@pytest.fixture
def order_pipeline(mock_db, mock_ledger, mock_signal_engine):
    """Create order pipeline instance"""
    config = {
        # Luno: 150/day, Others: 750/day
        "LUNO_BOT_DAILY_CAP": 150,
        "BINANCE_BOT_DAILY_CAP": 750,
        "BOT_COOLDOWN_SECONDS": 15,
        "ROLLING_WINDOW_CAP": 30,
        "ROLLING_WINDOW_MINUTES": 10,
        # Low threshold so spam detection test triggers: 25 cancels adds +10 pts to spam score
        # (cancel_count > 20 → score += 10; score 10 >= MAX_SPAM_SCORE 5 → detected)
        "MAX_SPAM_SCORE": 5,
    }
    
    return OrderPipeline(
        db=mock_db,
        ledger_service=mock_ledger,
        config=config,
        signal_engine=mock_signal_engine,
        realtime_broadcaster=AsyncMock()
    )


@pytest.mark.asyncio
async def test_per_exchange_daily_caps_luno(order_pipeline, mock_ledger):
    """Test that Luno has 150 trades/day cap per bot"""
    # Mock bot has already made 150 trades today
    mock_ledger.get_trade_count = AsyncMock(return_value=150)
    
    result = await order_pipeline.submit_order(
        user_id="test_user",
        bot_id="test_bot",
        exchange="luno",
        symbol="BTC/ZAR",
        side="buy",
        amount=0.001,
        order_type="limit",
        price=900000,
        is_paper=True
    )
    
    assert result["success"] is False
    assert result["gate_failed"] == "trade_limiter"
    assert "150" in result["rejection_reason"]
    assert "luno" in result["rejection_reason"].lower()


@pytest.mark.asyncio
async def test_per_exchange_daily_caps_binance(order_pipeline, mock_ledger):
    """Test that Binance has 750 trades/day cap per bot"""
    # Mock bot has already made 750 trades today
    mock_ledger.get_trade_count = AsyncMock(return_value=750)
    
    result = await order_pipeline.submit_order(
        user_id="test_user",
        bot_id="test_bot",
        exchange="binance",
        symbol="BTC/USDT",
        side="buy",
        amount=0.001,
        order_type="limit",
        price=50000,
        is_paper=True
    )
    
    assert result["success"] is False
    assert result["gate_failed"] == "trade_limiter"
    assert "750" in result["rejection_reason"]


@pytest.mark.asyncio
async def test_bot_cooldown_15_seconds(order_pipeline, mock_db, mock_ledger):
    """Test that bot cooldown enforces 15s between orders"""
    # Mock that last order was 10 seconds ago — patch directly on the shared mock instance
    last_order_time = datetime.now(timezone.utc) - timedelta(seconds=10)
    mock_db["bot_cooldowns"].find_one = AsyncMock(return_value={
        "bot_id": "test_bot",
        "created_at": last_order_time
    })
    mock_ledger.get_trade_count = AsyncMock(return_value=0)
    
    result = await order_pipeline.submit_order(
        user_id="test_user",
        bot_id="test_bot",
        exchange="binance",
        symbol="BTC/USDT",
        side="buy",
        amount=0.001,
        order_type="limit",
        price=50000,
        is_paper=True
    )
    
    assert result["success"] is False
    assert result["gate_failed"] == "trade_limiter"
    assert "cooldown" in result["rejection_reason"].lower()
    assert "15" in result["rejection_reason"]


@pytest.mark.asyncio
async def test_rolling_window_cap_30_orders(order_pipeline, mock_db, mock_ledger):
    """Test rolling window enforces 30 orders per 10 minutes"""
    # Patch directly on the shared mock instances (replacing the whole collection
    # would not affect self.rolling_windows which was captured at init time)
    mock_db["rolling_windows"].count_documents = AsyncMock(return_value=30)
    # bot_cooldowns.find_one already returns None by default from fixture
    mock_ledger.get_trade_count = AsyncMock(return_value=0)
    
    result = await order_pipeline.submit_order(
        user_id="test_user",
        bot_id="test_bot",
        exchange="binance",
        symbol="BTC/USDT",
        side="buy",
        amount=0.001,
        order_type="limit",
        price=50000,
        is_paper=True
    )
    
    assert result["success"] is False
    assert result["gate_failed"] == "trade_limiter"
    assert "rolling window" in result["rejection_reason"].lower()
    assert "30" in result["rejection_reason"]


@pytest.mark.asyncio
async def test_rate_limit_exponential_backoff(order_pipeline):
    """Test rate limit backoff calculation"""
    # First error
    backoff1 = await order_pipeline.handle_rate_limit_error(
        user_id="test_user",
        exchange="binance",
        error_type="429"
    )
    
    assert backoff1 > 0
    assert backoff1 >= order_pipeline.rate_limit_base_backoff
    
    # Second error (should have higher backoff)
    backoff2 = await order_pipeline.handle_rate_limit_error(
        user_id="test_user",
        exchange="binance",
        error_type="429"
    )
    
    assert backoff2 > backoff1
    
    # Third error (should be even higher)
    backoff3 = await order_pipeline.handle_rate_limit_error(
        user_id="test_user",
        exchange="binance",
        error_type="429"
    )
    
    assert backoff3 > backoff2
    assert backoff3 <= order_pipeline.rate_limit_max_backoff


@pytest.mark.asyncio
async def test_signal_engine_integration_gate_b(order_pipeline, mock_signal_engine, mock_ledger):
    """Test that Gate B uses SignalEngine for expected edge"""
    # Setup: no rate limit issues
    mock_ledger.get_trade_count = AsyncMock(return_value=0)
    
    # Mock collections to bypass other gates
    order_pipeline.db["bot_cooldowns"].find_one = AsyncMock(return_value=None)
    order_pipeline.db["rolling_windows"].count_documents = AsyncMock(return_value=0)
    order_pipeline.db["bots"].count_documents = AsyncMock(return_value=1)
    order_pipeline.db["pending_orders"].find_one = AsyncMock(return_value=None)
    order_pipeline.db["circuit_breaker_state"].find_one = AsyncMock(return_value=None)
    
    result = await order_pipeline.submit_order(
        user_id="test_user",
        bot_id="test_bot",
        exchange="binance",
        symbol="BTC/USDT",
        side="buy",
        amount=0.001,
        order_type="limit",
        price=50000,
        is_paper=True
    )
    
    # Verify signal engine was called
    mock_signal_engine.get_signal.assert_called_once()
    
    # Check execution summary includes signal data
    if result["success"]:
        assert "expected_edge_bps" in result["execution_summary"]
        assert result["execution_summary"]["expected_edge_bps"] == 50.0
        assert "confidence" in result["execution_summary"]


@pytest.mark.asyncio
async def test_spam_pattern_detection_excessive_cancels(order_pipeline, mock_db):
    """Test spam detection for excessive order cancels"""
    # Mock excessive cancels (>20 in 1 hour) — patch on existing shared instance
    mock_db["pending_orders"].count_documents = AsyncMock(return_value=25)
    mock_db["spam_scores"].find_one = AsyncMock(return_value=None)
    mock_db["spam_scores"].update_one = AsyncMock()

    # Check spam patterns
    result = await order_pipeline._check_spam_patterns(
        user_id="test_user",
        bot_id="test_bot",
        exchange="binance",
        symbol="BTC/USDT",
        amount=0.001
    )
    
    # Should detect spam
    assert result["passed"] is False
    assert "spam" in result["reason"].lower()


@pytest.mark.asyncio
async def test_rejection_broadcast_to_realtime(order_pipeline, mock_ledger):
    """Test that rejections are broadcast to realtime events"""
    # Mock rejection due to daily cap
    mock_ledger.get_trade_count = AsyncMock(return_value=150)
    
    result = await order_pipeline.submit_order(
        user_id="test_user",
        bot_id="test_bot",
        exchange="luno",
        symbol="BTC/ZAR",
        side="buy",
        amount=0.001,
        order_type="limit",
        price=900000,
        is_paper=True
    )
    
    assert result["success"] is False
    
    # Verify realtime broadcast was called
    assert order_pipeline.realtime_broadcaster.broadcast.called


@pytest.mark.asyncio
async def test_user_scaling_caps_with_bot_count(order_pipeline, mock_db, mock_ledger):
    """Test that user cap scales with bot count but respects hard cap"""
    # Mock 10 bots on Luno for user
    mock_db["bots"].count_documents = AsyncMock(return_value=10)
    mock_db["bot_cooldowns"].find_one = AsyncMock(return_value=None)
    mock_db["rolling_windows"].count_documents = AsyncMock(return_value=0)
    
    # User cap = min(3000, 10 * 150) = 1500
    # Mock user has made 1500 trades today
    async def mock_get_trade_count(**kwargs):
        if "bot_id" in kwargs:
            return 0  # Bot OK
        else:
            return 1500  # User at cap
    
    mock_ledger.get_trade_count = mock_get_trade_count
    
    result = await order_pipeline.submit_order(
        user_id="test_user",
        bot_id="test_bot",
        exchange="luno",
        symbol="BTC/ZAR",
        side="buy",
        amount=0.001,
        order_type="limit",
        price=900000,
        is_paper=True
    )
    
    assert result["success"] is False
    assert result["gate_failed"] == "trade_limiter"
    assert "1500" in result["rejection_reason"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
