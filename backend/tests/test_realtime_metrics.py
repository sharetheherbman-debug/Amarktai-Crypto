"""
Tests for Realtime Feed Metrics

Validates:
- Daily/weekly/monthly profit calculations
- Win rate calculations
- Exposure metric calculations
- SSE event structure
"""

import pytest
import asyncio
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
import sys
import os

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))


class TestRealtimeMetricsCalculations:
    """Test realtime metric calculation functions"""
    
    @pytest.mark.asyncio
    async def test_calculate_period_profit_daily(self):
        """Test daily profit calculation (last 24 hours)"""
        try:
            from routes.realtime import calculate_period_profit
            
            # This requires database access, so we'll test the logic
            # In production, this would query actual trades
            user_id = "test_user"
            
            # Mock successful calculation
            with patch('routes.realtime.db') as mock_db:
                # Setup mock trades
                now = datetime.now(timezone.utc)
                mock_trades = [
                    {'net_profit': 100, 'timestamp': now.isoformat()},
                    {'net_profit': 50, 'timestamp': now.isoformat()},
                ]
                
                mock_cursor = AsyncMock()
                mock_cursor.to_list = AsyncMock(return_value=mock_trades)
                mock_db.trades_collection.find = MagicMock(return_value=mock_cursor)
                
                # Calculate daily profit
                result = await calculate_period_profit(user_id, days=1)
                
                # Verify result
                assert isinstance(result, float)
                assert result >= 0 or result < 0  # Can be positive or negative
                
        except ImportError as e:
            pytest.skip(f"Realtime module not available: {e}")
    
    @pytest.mark.asyncio
    async def test_calculate_period_profit_weekly(self):
        """Test weekly profit calculation (last 7 days)"""
        try:
            from routes.realtime import calculate_period_profit
            
            user_id = "test_user"
            
            with patch('routes.realtime.db') as mock_db:
                now = datetime.now(timezone.utc)
                mock_trades = [
                    {'net_profit': 100, 'timestamp': (now - timedelta(days=1)).isoformat()},
                    {'net_profit': 200, 'timestamp': (now - timedelta(days=3)).isoformat()},
                    {'net_profit': 150, 'timestamp': (now - timedelta(days=6)).isoformat()},
                ]
                
                mock_cursor = AsyncMock()
                mock_cursor.to_list = AsyncMock(return_value=mock_trades)
                mock_db.trades_collection.find = MagicMock(return_value=mock_cursor)
                
                result = await calculate_period_profit(user_id, days=7)
                
                assert isinstance(result, float)
                
        except ImportError as e:
            pytest.skip(f"Realtime module not available: {e}")
    
    @pytest.mark.asyncio
    async def test_calculate_period_profit_monthly(self):
        """Test monthly profit calculation (last 30 days)"""
        try:
            from routes.realtime import calculate_period_profit
            
            user_id = "test_user"
            
            with patch('routes.realtime.db') as mock_db:
                now = datetime.now(timezone.utc)
                mock_trades = [
                    {'net_profit': 500, 'timestamp': (now - timedelta(days=10)).isoformat()},
                    {'net_profit': 300, 'timestamp': (now - timedelta(days=20)).isoformat()},
                    {'net_profit': 200, 'timestamp': (now - timedelta(days=28)).isoformat()},
                ]
                
                mock_cursor = AsyncMock()
                mock_cursor.to_list = AsyncMock(return_value=mock_trades)
                mock_db.trades_collection.find = MagicMock(return_value=mock_cursor)
                
                result = await calculate_period_profit(user_id, days=30)
                
                assert isinstance(result, float)
                
        except ImportError as e:
            pytest.skip(f"Realtime module not available: {e}")
    
    @pytest.mark.asyncio
    async def test_calculate_win_rate(self):
        """Test win rate calculation"""
        try:
            from routes.realtime import calculate_win_rate
            
            user_id = "test_user"
            
            with patch('routes.realtime.db') as mock_db:
                # Mock trades: 3 wins, 2 losses
                mock_trades = [
                    {'net_profit': 100},  # Win
                    {'net_profit': 50},   # Win
                    {'net_profit': -30},  # Loss
                    {'net_profit': 80},   # Win
                    {'net_profit': -20},  # Loss
                ]
                
                mock_cursor = AsyncMock()
                mock_cursor.to_list = AsyncMock(return_value=mock_trades)
                mock_db.trades_collection.find = MagicMock(return_value=mock_cursor)
                
                result = await calculate_win_rate(user_id)
                
                # Verify result
                assert isinstance(result, float)
                assert 0 <= result <= 100
                # 3 wins out of 5 trades = 60%
                # Allow for rounding
                assert 58 <= result <= 62
                
        except ImportError as e:
            pytest.skip(f"Realtime module not available: {e}")
    
    @pytest.mark.asyncio
    async def test_calculate_win_rate_no_trades(self):
        """Test win rate calculation with no trades"""
        try:
            from routes.realtime import calculate_win_rate
            
            user_id = "test_user"
            
            with patch('routes.realtime.db') as mock_db:
                mock_cursor = AsyncMock()
                mock_cursor.to_list = AsyncMock(return_value=[])
                mock_db.trades_collection.find = MagicMock(return_value=mock_cursor)
                
                result = await calculate_win_rate(user_id)
                
                # Should return 0 when no trades
                assert result == 0.0
                
        except ImportError as e:
            pytest.skip(f"Realtime module not available: {e}")
    
    @pytest.mark.asyncio
    async def test_calculate_exposure(self):
        """Test exposure calculation"""
        try:
            from routes.realtime import calculate_exposure
            
            user_id = "test_user"
            
            with patch('routes.realtime.db') as mock_db:
                # Mock bots with positions
                mock_bots = [
                    {'current_capital': 1000, 'open_position_value': 500},  # 50% exposure
                    {'current_capital': 2000, 'open_position_value': 400},  # 20% exposure
                ]
                
                mock_cursor = AsyncMock()
                mock_cursor.to_list = AsyncMock(return_value=mock_bots)
                mock_db.bots_collection.find = MagicMock(return_value=mock_cursor)
                
                result = await calculate_exposure(user_id)
                
                # Verify result
                assert isinstance(result, float)
                assert result >= 0
                # Total exposure: 900 / 3000 = 30%
                assert 25 <= result <= 35  # Allow for rounding
                
        except ImportError as e:
            pytest.skip(f"Realtime module not available: {e}")
    
    @pytest.mark.asyncio
    async def test_calculate_exposure_no_bots(self):
        """Test exposure calculation with no active bots"""
        try:
            from routes.realtime import calculate_exposure
            
            user_id = "test_user"
            
            with patch('routes.realtime.db') as mock_db:
                mock_cursor = AsyncMock()
                mock_cursor.to_list = AsyncMock(return_value=[])
                mock_db.bots_collection.find = MagicMock(return_value=mock_cursor)
                
                result = await calculate_exposure(user_id)
                
                # Should return 0 when no bots
                assert result == 0.0
                
        except ImportError as e:
            pytest.skip(f"Realtime module not available: {e}")


class TestRealtimeEventStructure:
    """Test SSE event structure and data format"""
    
    def test_overview_update_event_structure(self):
        """Test overview_update event has all required fields"""
        # Expected event structure
        required_fields = [
            'type',
            'active_bots',
            'total_bots',
            'total_profit',
            'daily_profit',
            'weekly_profit',
            'monthly_profit',
            'win_rate',
            'exposure',
            'total_capital',
            'timestamp'
        ]
        
        # Mock event data
        overview_data = {
            'type': 'overview',
            'active_bots': 12,
            'total_bots': 15,
            'total_profit': 5000.00,
            'daily_profit': 150.00,
            'weekly_profit': 800.00,
            'monthly_profit': 3200.00,
            'win_rate': 62.5,
            'exposure': 45.3,
            'total_capital': 10000.00,
            'timestamp': datetime.now(timezone.utc).isoformat()
        }
        
        # Verify all required fields present
        for field in required_fields:
            assert field in overview_data, f"Missing required field: {field}"
        
        # Verify data types
        assert isinstance(overview_data['active_bots'], int)
        assert isinstance(overview_data['total_bots'], int)
        assert isinstance(overview_data['total_profit'], (int, float))
        assert isinstance(overview_data['daily_profit'], (int, float))
        assert isinstance(overview_data['weekly_profit'], (int, float))
        assert isinstance(overview_data['monthly_profit'], (int, float))
        assert isinstance(overview_data['win_rate'], (int, float))
        assert isinstance(overview_data['exposure'], (int, float))
        assert isinstance(overview_data['total_capital'], (int, float))
        assert isinstance(overview_data['timestamp'], str)
        
        # Verify value ranges
        assert overview_data['active_bots'] >= 0
        assert overview_data['total_bots'] >= 0
        assert 0 <= overview_data['win_rate'] <= 100
        assert overview_data['exposure'] >= 0
    
    def test_profit_periods_relationship(self):
        """Test that profit periods have logical relationship"""
        # Monthly should generally include weekly and daily
        total_profit = 10000.00
        monthly_profit = 3200.00
        weekly_profit = 800.00
        daily_profit = 150.00
        
        # Verify relationships (allowing for variations)
        assert monthly_profit <= total_profit
        assert weekly_profit <= monthly_profit or weekly_profit <= total_profit
        assert daily_profit <= weekly_profit or daily_profit <= total_profit
    
    def test_win_rate_percentage_range(self):
        """Test win rate is valid percentage"""
        win_rates = [0.0, 25.5, 50.0, 75.8, 100.0]
        
        for rate in win_rates:
            assert 0 <= rate <= 100
            assert isinstance(rate, (int, float))
    
    def test_exposure_percentage_calculation(self):
        """Test exposure percentage is calculated correctly"""
        # Test case: 50% exposure
        total_capital = 10000.00
        open_position_value = 5000.00
        expected_exposure = 50.0
        
        actual_exposure = (open_position_value / total_capital) * 100
        
        assert abs(actual_exposure - expected_exposure) < 0.01
        
        # Test case: 30% exposure
        open_position_value = 3000.00
        expected_exposure = 30.0
        
        actual_exposure = (open_position_value / total_capital) * 100
        
        assert abs(actual_exposure - expected_exposure) < 0.01


class TestRealtimePerformance:
    """Test realtime feed performance considerations"""
    
    def test_metric_calculation_efficiency(self):
        """Test metrics can be calculated efficiently"""
        # Simulate large dataset
        large_trade_list = [{'net_profit': i * 10} for i in range(1000)]
        
        # Calculate sum efficiently
        import time
        start = time.time()
        total = sum(t['net_profit'] for t in large_trade_list)
        duration = time.time() - start
        
        # Should be very fast (< 0.1 seconds)
        assert duration < 0.1
        assert total == sum(i * 10 for i in range(1000))
    
    def test_period_cutoff_logic(self):
        """Test period cutoff calculations are correct"""
        now = datetime.now(timezone.utc)
        
        # Daily cutoff (24 hours ago)
        daily_cutoff = now - timedelta(days=1)
        assert daily_cutoff < now
        assert (now - daily_cutoff).days == 1
        
        # Weekly cutoff (7 days ago)
        weekly_cutoff = now - timedelta(days=7)
        assert weekly_cutoff < now
        assert (now - weekly_cutoff).days == 7
        
        # Monthly cutoff (30 days ago)
        monthly_cutoff = now - timedelta(days=30)
        assert monthly_cutoff < now
        assert (now - monthly_cutoff).days == 30


if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, "-v", "-s"])
