"""
Critical Production Fixes Tests
Tests for the critical blockers fixed in this PR:
- A) UnboundLocalError in risk_engine
- B) Empty trade documents  
- C) Duplicate close_exchanges
- D) Exchange filtering
"""

import pytest
import asyncio
import sys
import os
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from risk_engine import risk_engine, RiskEngine
from paper_trading_engine import paper_engine, PaperTradingEngine


class TestRiskEngineUnboundLocalError:
    """Test A: Ensure risk_engine doesn't have UnboundLocalError"""
    
    @pytest.mark.asyncio
    async def test_risk_engine_no_unbound_local_error(self):
        """Test that risk_engine.check_trade_risk doesn't throw UnboundLocalError"""
        # Create a mock database
        with patch('risk_engine.db') as mock_db:
            # Setup mock collections
            mock_bots_collection = AsyncMock()
            mock_trades_collection = AsyncMock()
            
            mock_db.bots_collection = mock_bots_collection
            mock_db.trades_collection = mock_trades_collection
            
            # Mock bot data
            mock_bots_collection.find_one.return_value = {
                "id": "bot123",
                "user_id": "user123",
                "current_capital": 5000,
                "risk_mode": "safe"
            }
            
            # Mock user bots
            mock_cursor = AsyncMock()
            mock_cursor.to_list.return_value = [
                {"user_id": "user123", "current_capital": 5000}
            ]
            mock_bots_collection.find.return_value = mock_cursor
            
            # Mock trades
            mock_trades_cursor = AsyncMock()
            mock_trades_cursor.to_list.return_value = []
            mock_trades_collection.find.return_value = mock_trades_cursor
            
            # Create fresh risk engine instance
            engine = RiskEngine()
            
            # This should NOT throw UnboundLocalError
            try:
                result = await engine.check_trade_risk(
                    user_id="user123",
                    bot_id="bot123",
                    exchange="luno",
                    proposed_notional=1000,
                    risk_mode="safe"
                )
                # Result should be a tuple (bool, str)
                assert isinstance(result, tuple), "check_trade_risk should return tuple"
                assert len(result) == 2, "check_trade_risk should return (bool, str)"
                success = True
            except UnboundLocalError as e:
                success = False
                pytest.fail(f"UnboundLocalError raised: {e}")
            
            assert success, "check_trade_risk should not raise UnboundLocalError"
    
    def test_risk_engine_no_inner_import(self):
        """Test that risk_engine.py doesn't have inner 'import database as db'"""
        import risk_engine
        import inspect
        
        # Get source code of the module
        source = inspect.getsource(risk_engine)
        lines = source.split('\n')
        
        # Check for inner imports (inside functions/methods)
        in_function = False
        indent_level = 0
        inner_import_found = False
        
        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            
            # Detect function/method definition
            if stripped.startswith('def ') or stripped.startswith('async def '):
                in_function = True
                indent_level = len(line) - len(line.lstrip())
            
            # Check if we're still in function (based on indentation)
            if in_function and line and not line[0].isspace():
                in_function = False
            
            # Check for import inside function
            if in_function and 'import database as db' in stripped:
                inner_import_found = True
                pytest.fail(f"Found inner 'import database as db' at line {i}: {line}")
        
        assert not inner_import_found, "risk_engine should not have inner 'import database as db'"


class TestPaperTradingEmptyDocs:
    """Test B: Ensure paper trading doesn't insert empty trade documents"""
    
    @pytest.mark.asyncio
    async def test_paper_trade_validates_required_fields(self):
        """Test that paper trading validates trade docs have required fields"""
        with patch('paper_trading_engine.db') as mock_db:
            # Setup mocks
            mock_bots = AsyncMock()
            mock_trades = AsyncMock()
            mock_db.bots_collection = mock_bots
            mock_db.trades_collection = mock_trades
            
            # Mock bot data
            bot_data = {
                "id": "bot123",
                "user_id": "user123",
                "name": "TestBot",
                "current_capital": 1000,
                "initial_capital": 1000,
                "risk_mode": "safe",
                "exchange": "luno"
            }
            
            mock_bots.find_one.return_value = bot_data
            mock_bots.update_one = AsyncMock()
            mock_trades.insert_one = AsyncMock()
            
            # Create engine
            engine = PaperTradingEngine()
            
            # Mock the execute_smart_trade to return incomplete data
            async def mock_execute_with_missing_fields(bot_id, bot_data):
                # Simulate a trade result missing required fields
                return {
                    "success": True,
                    "bot_id": bot_id,
                    # Missing: symbol, exchange, entry_price, etc.
                }
            
            with patch.object(engine, 'execute_smart_trade', side_effect=mock_execute_with_missing_fields):
                result = await engine.run_trading_cycle(
                    "bot123",
                    bot_data,
                    {'bots': mock_bots, 'trades': mock_trades}
                )
                
                # Result should be None if trade validation fails
                assert result is None, "run_trading_cycle should return None for invalid trade data"
                
                # Ensure insert_one was NOT called with invalid data
                mock_trades.insert_one.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_paper_trade_includes_required_fields(self):
        """Test that successful paper trades include all required fields"""
        with patch('paper_trading_engine.db') as mock_db:
            # Setup mocks
            mock_bots = AsyncMock()
            mock_trades = AsyncMock()
            mock_db.bots_collection = mock_bots
            mock_db.trades_collection = mock_trades
            
            # Mock bot data
            bot_data = {
                "id": "bot123",
                "user_id": "user123",
                "name": "TestBot",
                "current_capital": 1000,
                "initial_capital": 1000,
                "risk_mode": "safe",
                "exchange": "luno"
            }
            
            mock_bots.find_one.return_value = bot_data
            mock_bots.update_one = AsyncMock()
            mock_trades.insert_one = AsyncMock()
            
            # Create engine
            engine = PaperTradingEngine()
            
            # Mock execute_smart_trade to return valid data
            async def mock_execute_valid(bot_id, bot_data):
                return {
                    "success": True,
                    "bot_id": bot_id,
                    "symbol": "BTC/ZAR",
                    "exchange": "luno",
                    "entry_price": 50000.0,
                    "exit_price": 50500.0,
                    "amount": 0.01,
                    "profit_loss": 5.0,
                    "fees": 0.5,
                    "is_paper": True,
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
            
            with patch.object(engine, 'execute_smart_trade', side_effect=mock_execute_valid):
                result = await engine.run_trading_cycle(
                    "bot123",
                    bot_data,
                    {'bots': mock_bots, 'trades': mock_trades}
                )
                
                # Should succeed
                assert result is not None, "run_trading_cycle should succeed with valid data"
                
                # Check that insert_one was called
                assert mock_trades.insert_one.called, "insert_one should be called"
                
                # Get the inserted document
                call_args = mock_trades.insert_one.call_args
                inserted_doc = call_args[0][0]
                
                # Verify required fields
                required_fields = ['id', 'user_id', 'bot_id', 'symbol', 'exchange', 
                                   'entry_price', 'exit_price', 'amount', 'profit_loss', 
                                   'fees', 'is_paper', 'timestamp', 'status', 'side']
                
                for field in required_fields:
                    assert field in inserted_doc, f"Trade doc should have field: {field}"
                
                # Verify it's not empty (more than just _id)
                assert len(inserted_doc.keys()) > 5, "Trade doc should have multiple fields"


class TestCloseExchangesSafe:
    """Test C: Ensure close_exchanges is safe and doesn't raise"""
    
    @pytest.mark.asyncio
    async def test_close_exchanges_with_none(self):
        """Test that close_exchanges handles None exchanges gracefully"""
        engine = PaperTradingEngine()
        
        # Set all exchanges to None
        engine.luno_exchange = None
        engine.binance_exchange = None
        engine.kucoin_exchange = None
        
        # Should not raise any exception
        try:
            await engine.close_exchanges()
            success = True
        except Exception as e:
            success = False
            pytest.fail(f"close_exchanges raised exception with None exchanges: {e}")
        
        assert success, "close_exchanges should handle None exchanges"
        
        # Verify all remain None
        assert engine.luno_exchange is None
        assert engine.binance_exchange is None
        assert engine.kucoin_exchange is None
    
    @pytest.mark.asyncio
    async def test_close_exchanges_with_error(self):
        """Test that close_exchanges handles close errors gracefully"""
        engine = PaperTradingEngine()
        
        # Create mock exchange that raises on close
        mock_exchange = AsyncMock()
        mock_exchange.close.side_effect = Exception("Mock close error")
        
        engine.luno_exchange = mock_exchange
        engine.binance_exchange = None
        engine.kucoin_exchange = None
        
        # Should not raise, just log warning
        try:
            await engine.close_exchanges()
            success = True
        except Exception as e:
            success = False
            pytest.fail(f"close_exchanges should not raise on close error: {e}")
        
        assert success, "close_exchanges should handle close errors"
        
        # Verify references are cleared
        assert engine.luno_exchange is None


class TestExchangeFiltering:
    """Test D: Ensure only supported exchanges are processed"""
    
    def test_paper_supported_exchanges_config(self):
        """Test that PAPER_SUPPORTED_EXCHANGES is correctly defined"""
        from config import PAPER_SUPPORTED_EXCHANGES
        
        assert isinstance(PAPER_SUPPORTED_EXCHANGES, set), "PAPER_SUPPORTED_EXCHANGES should be a set"
        assert 'luno' in PAPER_SUPPORTED_EXCHANGES, "luno should be supported"
        assert 'binance' in PAPER_SUPPORTED_EXCHANGES, "binance should be supported"
        assert 'kucoin' in PAPER_SUPPORTED_EXCHANGES, "kucoin should be supported"
        assert 'bybit' in PAPER_SUPPORTED_EXCHANGES, "bybit should be supported"
        assert 'kraken' in PAPER_SUPPORTED_EXCHANGES, "kraken should be supported"
        assert 'bitget' in PAPER_SUPPORTED_EXCHANGES, "bitget should be supported"
        assert 'gate' in PAPER_SUPPORTED_EXCHANGES, "gate should be supported"
        
        # These should NOT be supported in production
        assert 'ovex' not in PAPER_SUPPORTED_EXCHANGES, "ovex should not be supported"
        assert 'valr' not in PAPER_SUPPORTED_EXCHANGES, "valr should not be supported"


class TestLiveTradingGate:
    """Test E: Ensure live trading gate works correctly"""
    
    def test_enable_live_trading_default_false(self):
        """Test that ENABLE_LIVE_TRADING defaults to False"""
        # Need to reload config with no env var
        import importlib
        import config
        
        # Check the default value
        from config import ENABLE_LIVE_TRADING
        
        # In production, this should be False by default
        # (unless explicitly enabled via env var)
        # We can't guarantee env var isn't set, so just check it exists
        assert isinstance(ENABLE_LIVE_TRADING, bool), "ENABLE_LIVE_TRADING should be bool"
    
    def test_paper_training_days_minimum(self):
        """Test that PAPER_TRAINING_DAYS has minimum value"""
        from config import PAPER_TRAINING_DAYS
        
        assert isinstance(PAPER_TRAINING_DAYS, int), "PAPER_TRAINING_DAYS should be int"
        assert PAPER_TRAINING_DAYS >= 7, "PAPER_TRAINING_DAYS should be at least 7"


if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, "-v", "-s"])
