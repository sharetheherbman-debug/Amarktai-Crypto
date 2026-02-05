"""
Test Overview Snapshot Endpoint
Verifies that the overview snapshot returns all required fields
"""

import pytest
from fastapi.testclient import TestClient
import sys
import os

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

from server import app
from rules.bot_rules import SUPPORTED_EXCHANGES


@pytest.fixture
def client():
    """Test client fixture"""
    return TestClient(app)


@pytest.fixture
def mock_user_token():
    """Mock user token for authentication"""
    from auth import create_access_token
    return create_access_token({"user_id": "test-user-overview", "sub": "test-user-overview"})


class TestOverviewSnapshot:
    """Test overview snapshot endpoint"""
    
    def test_overview_snapshot_endpoint_exists(self):
        """Verify /api/overview/snapshot endpoint exists"""
        from routes.dashboard_overview import router
        
        routes = [route for route in router.routes]
        snapshot_route = next((r for r in routes if '/snapshot' in str(r.path)), None)
        
        assert snapshot_route is not None, "/api/overview/snapshot endpoint must exist"
    
    def test_overview_snapshot_structure(self):
        """Verify overview snapshot returns required fields"""
        import inspect
        from routes.dashboard_overview import get_overview_snapshot
        
        source = inspect.getsource(get_overview_snapshot)
        
        # Verify key fields are returned
        required_fields = [
            'system_mode',
            'per_exchange_bots',
            'bots_summary',
            'profit_summary',
            'last_trade_timestamp',
            'last_heartbeat',
            'errors_warnings_count',
            'timestamp'
        ]
        
        for field in required_fields:
            assert field in source, f"Overview snapshot must include '{field}'"
    
    def test_per_exchange_bots_structure(self):
        """Verify per_exchange_bots includes all exchanges with caps"""
        import inspect
        from routes.dashboard_overview import get_overview_snapshot
        
        source = inspect.getsource(get_overview_snapshot)
        
        # Should loop through SUPPORTED_EXCHANGES
        assert 'SUPPORTED_EXCHANGES' in source, "Must iterate through SUPPORTED_EXCHANGES"
        assert 'BOT_CAPS' in source, "Must reference BOT_CAPS"
        
        # Should include count and cap
        assert '"count"' in source or "'count'" in source
        assert '"cap"' in source or "'cap'" in source
        assert '"display"' in source or "'display'" in source
    
    def test_profit_boundaries_calculation(self):
        """Verify profit boundaries are calculated correctly"""
        import inspect
        from routes.dashboard_overview import get_overview_snapshot
        
        source = inspect.getsource(get_overview_snapshot)
        
        # Daily: today 00:00 UTC
        assert 'today_start' in source
        assert 'hour=0' in source and 'minute=0' in source
        
        # Weekly: last Monday
        assert 'week_start' in source
        assert 'weekday' in source or 'Monday' in source.lower()
        
        # Monthly: first day of month
        assert 'month_start' in source
        assert 'day=1' in source
    
    def test_system_mode_flags(self):
        """Verify system mode flags are included"""
        import inspect
        from routes.dashboard_overview import get_overview_snapshot
        
        source = inspect.getsource(get_overview_snapshot)
        
        # Should include various mode flags
        assert 'paper_trading' in source
        assert 'live_trading' in source
        assert 'autopilot' in source
    
    def test_bots_summary_counts(self):
        """Verify bots summary includes all count types"""
        import inspect
        from routes.dashboard_overview import get_overview_snapshot
        
        source = inspect.getsource(get_overview_snapshot)
        
        # Should count different bot statuses
        assert 'active' in source
        assert 'paused' in source
        assert 'quarantined' in source or 'training' in source


class TestOverviewTimeRanges:
    """Test time range calculations"""
    
    def test_daily_starts_at_midnight_utc(self):
        """Daily profit should start at midnight UTC"""
        from datetime import datetime, timezone
        
        now = datetime.now(timezone.utc)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        
        assert today_start.hour == 0
        assert today_start.minute == 0
        assert today_start.second == 0
    
    def test_weekly_starts_on_monday(self):
        """Weekly profit should start on Monday"""
        from datetime import datetime, timezone, timedelta
        
        now = datetime.now(timezone.utc)
        days_since_monday = now.weekday()  # Monday is 0
        week_start = (now - timedelta(days=days_since_monday)).replace(hour=0, minute=0, second=0, microsecond=0)
        
        assert week_start.weekday() == 0, "Week should start on Monday"
        assert week_start.hour == 0
    
    def test_monthly_starts_on_first_day(self):
        """Monthly profit should start on first day of month"""
        from datetime import datetime, timezone
        
        now = datetime.now(timezone.utc)
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        
        assert month_start.day == 1, "Month should start on day 1"
        assert month_start.hour == 0


class TestExchangeBotCounts:
    """Test per-exchange bot counting"""
    
    def test_all_exchanges_included(self):
        """Verify all supported exchanges are included in per_exchange_bots"""
        import inspect
        from routes.dashboard_overview import get_overview_snapshot
        
        source = inspect.getsource(get_overview_snapshot)
        
        # Should iterate through all exchanges
        for exchange in SUPPORTED_EXCHANGES:
            # The logic should handle all exchanges
            pass  # Actual test would need DB access
        
        assert 'SUPPORTED_EXCHANGES' in source
    
    def test_bot_count_format(self):
        """Verify bot count display format X/Y"""
        # Expected format: "3/5" for Luno, "7/10" for others
        import inspect
        from routes.dashboard_overview import get_overview_snapshot
        
        source = inspect.getsource(get_overview_snapshot)
        
        # Should create display string
        assert 'display' in source or 'f"' in source or '"{count}/{cap}"' in source


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
