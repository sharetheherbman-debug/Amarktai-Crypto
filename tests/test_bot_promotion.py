"""
Tests for Bot Promotion System (Paper to Live)

Tests:
- 7-day paper training requirement
- MIN_TRADES_FOR_PROMOTION requirement (25 trades)
- MIN_WIN_RATE requirement (52%)
- MIN_PROFIT_PERCENT requirement (3%)
- Circuit breaker check before promotion
- API keys validation before promotion
- AUTO_PROMOTE_LIVE flag behavior
- Realtime broadcast on promotion
"""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from bot_lifecycle import BotLifecycleManager


@pytest.fixture
def mock_db():
    """Mock database with collections"""
    db_module = MagicMock()
    
    # Mock collections
    db_module.bots_collection = AsyncMock()
    db_module.trades_collection = AsyncMock()
    db_module.circuit_breaker_state = AsyncMock()
    db_module.api_keys_collection = AsyncMock()
    db_module.system_modes_collection = AsyncMock()
    
    return db_module


@pytest.fixture
def lifecycle_manager():
    """Create lifecycle manager instance"""
    return BotLifecycleManager()


@pytest.fixture
def eligible_bot():
    """Create a bot that meets all promotion criteria"""
    created_at = datetime.now(timezone.utc) - timedelta(days=8)
    
    return {
        "id": "bot_123",
        "user_id": "user_abc",
        "name": "Test Bot",
        "exchange": "binance",
        "trading_mode": "paper",
        "status": "active",
        "origin": "user",
        "created_at": created_at.isoformat(),
        "initial_capital": 1000.0,
        "current_capital": 1035.0,  # 3.5% profit
        "total_profit": 35.0,
        "trades_count": 30
    }


@pytest.fixture
def profitable_trades():
    """Create mock trades with >52% win rate"""
    trades = []
    
    # 16 winning trades (53%)
    for i in range(16):
        trades.append({
            "bot_id": "bot_123",
            "profit_loss": 5.0,
            "new_capital": 1000 + (i + 1) * 5
        })
    
    # 14 losing trades (47%)
    for i in range(14):
        trades.append({
            "bot_id": "bot_123",
            "profit_loss": -3.0,
            "new_capital": 1000 + 16 * 5 - (i + 1) * 3
        })
    
    return trades


@pytest.mark.asyncio
async def test_promotion_requires_7_days(lifecycle_manager, eligible_bot, mock_db, profitable_trades):
    """Test that promotion requires 7 days of paper trading"""
    # Bot created only 5 days ago
    recent_bot = eligible_bot.copy()
    recent_bot["created_at"] = (datetime.now(timezone.utc) - timedelta(days=5)).isoformat()
    
    with patch('bot_lifecycle.db', mock_db):
        mock_db.trades_collection.count_documents = AsyncMock(return_value=30)
        mock_db.trades_collection.find = MagicMock(return_value=AsyncMock(to_list=AsyncMock(return_value=profitable_trades)))
        
        should_promote = await lifecycle_manager._should_promote(recent_bot)
        
        assert should_promote is False


@pytest.mark.asyncio
async def test_promotion_requires_min_trades(lifecycle_manager, eligible_bot, mock_db, profitable_trades):
    """Test that promotion requires at least 25 trades"""
    with patch('bot_lifecycle.db', mock_db):
        # Only 20 trades
        mock_db.trades_collection.count_documents = AsyncMock(return_value=20)
        mock_db.trades_collection.find = MagicMock(return_value=AsyncMock(to_list=AsyncMock(return_value=profitable_trades[:20])))
        
        should_promote = await lifecycle_manager._should_promote(eligible_bot)
        
        assert should_promote is False


@pytest.mark.asyncio
async def test_promotion_requires_min_win_rate(lifecycle_manager, eligible_bot, mock_db):
    """Test that promotion requires at least 52% win rate"""
    # Create trades with only 40% win rate
    low_win_trades = [
        {"bot_id": "bot_123", "profit_loss": 5.0, "new_capital": 1000} for _ in range(12)  # 40% wins
    ] + [
        {"bot_id": "bot_123", "profit_loss": -3.0, "new_capital": 1000} for _ in range(18)  # 60% losses
    ]
    
    with patch('bot_lifecycle.db', mock_db):
        mock_db.trades_collection.count_documents = AsyncMock(return_value=30)
        mock_db.trades_collection.find = MagicMock(return_value=AsyncMock(to_list=AsyncMock(return_value=low_win_trades)))
        
        should_promote = await lifecycle_manager._should_promote(eligible_bot)
        
        assert should_promote is False


@pytest.mark.asyncio
async def test_promotion_requires_min_profit(lifecycle_manager, eligible_bot, mock_db, profitable_trades):
    """Test that promotion requires at least 3% profit"""
    # Bot with only 1% profit
    low_profit_bot = eligible_bot.copy()
    low_profit_bot["current_capital"] = 1010.0  # Only 1% profit
    
    with patch('bot_lifecycle.db', mock_db):
        mock_db.trades_collection.count_documents = AsyncMock(return_value=30)
        mock_db.trades_collection.find = MagicMock(return_value=AsyncMock(to_list=AsyncMock(return_value=profitable_trades)))
        
        should_promote = await lifecycle_manager._should_promote(low_profit_bot)
        
        assert should_promote is False


@pytest.mark.asyncio
async def test_promotion_checks_circuit_breaker(lifecycle_manager, eligible_bot, mock_db, profitable_trades):
    """Test that promotion blocked if circuit breaker tripped"""
    with patch('bot_lifecycle.db', mock_db):
        mock_db.trades_collection.count_documents = AsyncMock(return_value=30)
        mock_db.trades_collection.find = MagicMock(return_value=AsyncMock(to_list=AsyncMock(return_value=profitable_trades)))
        
        # Circuit breaker is tripped
        mock_db.circuit_breaker_state.find_one = AsyncMock(return_value={
            "entity_type": "bot",
            "entity_id": "bot_123",
            "tripped": True,
            "trigger_reason": "Max drawdown exceeded"
        })
        
        should_promote = await lifecycle_manager._should_promote(eligible_bot)
        
        assert should_promote is False


@pytest.mark.asyncio
async def test_promotion_validates_api_keys(lifecycle_manager, eligible_bot, mock_db, profitable_trades):
    """Test that promotion validates API keys when REQUIRE_API_KEYS_FOR_LIVE=true"""
    with patch('bot_lifecycle.db', mock_db):
        mock_db.trades_collection.count_documents = AsyncMock(return_value=30)
        mock_db.trades_collection.find = MagicMock(return_value=AsyncMock(to_list=AsyncMock(return_value=profitable_trades)))
        mock_db.circuit_breaker_state.find_one = AsyncMock(return_value=None)
        
        # No API keys found
        mock_db.api_keys_collection.find_one = AsyncMock(return_value=None)
        
        with patch('bot_lifecycle.config.REQUIRE_API_KEYS_FOR_LIVE', True):
            should_promote = await lifecycle_manager._should_promote(eligible_bot)
            
            assert should_promote is False


@pytest.mark.asyncio
async def test_auto_promote_live_flag_true(lifecycle_manager, eligible_bot, mock_db, profitable_trades):
    """Test AUTO_PROMOTE_LIVE=true automatically promotes eligible bots"""
    with patch('bot_lifecycle.db', mock_db):
        mock_db.bots_collection.find = MagicMock(return_value=AsyncMock(to_list=AsyncMock(return_value=[eligible_bot])))
        mock_db.bots_collection.update_one = AsyncMock()
        mock_db.trades_collection.count_documents = AsyncMock(return_value=30)
        mock_db.trades_collection.find = MagicMock(return_value=AsyncMock(to_list=AsyncMock(return_value=profitable_trades)))
        mock_db.circuit_breaker_state.find_one = AsyncMock(return_value=None)
        mock_db.api_keys_collection.find_one = AsyncMock(return_value={
            "user_id": "user_abc",
            "exchange": "binance",
            "api_key": "key",
            "secret": "secret"
        })
        mock_db.system_modes_collection.find_one = AsyncMock(return_value={
            "user_id": "user_abc",
            "liveTrading": True
        })
        
        with patch('bot_lifecycle.config.AUTO_PROMOTE_LIVE', True):
            with patch('bot_lifecycle.config.ENABLE_LIVE_TRADING', True):
                with patch('bot_lifecycle.config.REQUIRE_API_KEYS_FOR_LIVE', False):
                    result = await lifecycle_manager.check_promotions()
                    
                    assert result["promoted_count"] == 1
                    assert result["eligible_count"] == 1


@pytest.mark.asyncio
async def test_auto_promote_live_flag_false(lifecycle_manager, eligible_bot, mock_db, profitable_trades):
    """Test AUTO_PROMOTE_LIVE=false only marks bots as eligible"""
    with patch('bot_lifecycle.db', mock_db):
        mock_db.bots_collection.find = MagicMock(return_value=AsyncMock(to_list=AsyncMock(return_value=[eligible_bot])))
        mock_db.bots_collection.update_one = AsyncMock()
        mock_db.trades_collection.count_documents = AsyncMock(return_value=30)
        mock_db.trades_collection.find = MagicMock(return_value=AsyncMock(to_list=AsyncMock(return_value=profitable_trades)))
        mock_db.circuit_breaker_state.find_one = AsyncMock(return_value=None)
        mock_db.api_keys_collection.find_one = AsyncMock(return_value={
            "user_id": "user_abc",
            "exchange": "binance",
            "api_key": "key",
            "secret": "secret"
        })
        
        with patch('bot_lifecycle.config.AUTO_PROMOTE_LIVE', False):
            with patch('bot_lifecycle.config.ENABLE_LIVE_TRADING', True):
                with patch('bot_lifecycle.config.REQUIRE_API_KEYS_FOR_LIVE', False):
                    result = await lifecycle_manager.check_promotions()
                    
                    # Should mark as eligible but NOT promote
                    assert result["promoted_count"] == 0
                    assert result["eligible_count"] == 1
                    assert result["auto_promote_enabled"] is False


@pytest.mark.asyncio
async def test_promotion_broadcasts_realtime_event(lifecycle_manager, eligible_bot, mock_db):
    """Test that promotion broadcasts realtime event"""
    with patch('bot_lifecycle.db', mock_db):
        mock_db.bots_collection.update_one = AsyncMock()
        mock_db.system_modes_collection.find_one = AsyncMock(return_value={
            "user_id": "user_abc",
            "liveTrading": True
        })
        
        with patch('bot_lifecycle.realtime_events.manager.send_message', AsyncMock()) as mock_broadcast:
            await lifecycle_manager._promote_bot(eligible_bot)
            
            # Verify broadcast was called
            mock_broadcast.assert_called_once()
            call_args = mock_broadcast.call_args
            assert call_args[0][0] == eligible_bot["user_id"]
            assert call_args[0][1]["type"] == "bot_promoted"


@pytest.mark.asyncio
async def test_promotion_preserves_paper_history(lifecycle_manager, eligible_bot, mock_db):
    """Test that promotion preserves paper performance history"""
    with patch('bot_lifecycle.db', mock_db):
        mock_db.system_modes_collection.find_one = AsyncMock(return_value={
            "user_id": "user_abc",
            "liveTrading": True
        })
        
        update_spy = AsyncMock()
        mock_db.bots_collection.update_one = update_spy
        
        with patch('bot_lifecycle.realtime_events.manager.send_message', AsyncMock()):
            await lifecycle_manager._promote_bot(eligible_bot)
            
            # Check update included paper_performance
            update_call = update_spy.call_args
            set_data = update_call[0][1]["$set"]
            
            assert "paper_performance" in set_data
            assert set_data["paper_performance"]["paper_final_capital"] == eligible_bot["current_capital"]
            assert set_data["trading_mode"] == "live"
            assert set_data["current_capital"] == eligible_bot["initial_capital"]  # Reset for live


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
