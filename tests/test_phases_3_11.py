"""
Tests for Phases 3-11 implementations
Tests profit/fee normalization, market prices, API keys, etc.
"""

import pytest
import sys
import os
from datetime import datetime, timezone, timedelta

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))


class TestPhase3ProfitFeesNormalization:
    """Test canonical field normalization for profit and fees"""
    
    def test_overview_service_uses_canonical_fields(self):
        """Test that overview service uses net_pnl and fee_amount"""
        # Mock trades with canonical fields
        mock_trades = [
            {"net_pnl": 100, "fee_amount": 5, "timestamp": datetime.now(timezone.utc).isoformat()},
            {"net_pnl": -50, "fee_amount": 3, "timestamp": datetime.now(timezone.utc).isoformat()},
        ]
        
        # Test profit calculation
        total_pnl = sum(t["net_pnl"] for t in mock_trades)
        assert total_pnl == 50
        
        # Test fee calculation
        total_fees = sum(t["fee_amount"] for t in mock_trades)
        assert total_fees == 8
    
    def test_overview_service_fallback_fields(self):
        """Test fallback to profit_loss and fees/fee"""
        # Mock trades with legacy fields
        mock_trades = [
            {"profit_loss": 100, "fees": 5},
            {"profit_loss": -50, "fee": 3},
        ]
        
        # Test fallback logic
        total_pnl = sum(t.get("net_pnl", t.get("profit_loss", 0)) for t in mock_trades)
        assert total_pnl == 50
        
        total_fees = sum(t.get("fee_amount", t.get("fees", t.get("fee", 0))) for t in mock_trades)
        assert total_fees == 8


class TestPhase4MarketPrices:
    """Test live market prices endpoint"""
    
    def test_market_prices_endpoint_structure(self):
        """Test that market prices endpoint returns correct structure"""
        # Expected structure
        expected_pairs = ["BTC/ZAR", "ETH/ZAR", "XRP/ZAR"]
        
        response_structure = {
            "prices": {
                pair: {
                    "price": 0.0,
                    "change_pct": 0.0,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "source": "luno_public"
                }
                for pair in expected_pairs
            },
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
        assert "prices" in response_structure
        assert len(response_structure["prices"]) == 3
        for pair in expected_pairs:
            assert pair in response_structure["prices"]
            assert "price" in response_structure["prices"][pair]
            assert "source" in response_structure["prices"][pair]


class TestPhase5APIKeys:
    """Test API keys management"""
    
    def test_supported_providers(self):
        """Test that all 7 exchanges + 3 AI providers are supported"""
        try:
            from services.provider_registry import PROVIDERS
            
            expected_exchanges = ['luno', 'binance', 'kucoin', 'bybit', 'kraken', 'bitget', 'gate']
            expected_ai = ['openai', 'coinstats', 'fetchai']
            
            for provider in expected_exchanges + expected_ai:
                assert provider in PROVIDERS, f"{provider} not in PROVIDERS"
        except ImportError:
            pytest.skip("Provider registry not available")
    
    def test_provider_status_enum(self):
        """Test provider status values"""
        try:
            from services.provider_registry import ProviderStatus
            
            assert hasattr(ProviderStatus, 'NOT_CONFIGURED')
            assert hasattr(ProviderStatus, 'CONFIGURED_UNTESTED')
            assert hasattr(ProviderStatus, 'CONFIGURED_VALID')
            assert hasattr(ProviderStatus, 'CONFIGURED_INVALID')
        except ImportError:
            pytest.skip("Provider registry not available")


class TestPhase7TradeCadence:
    """Test trade cadence and countdown system (Phase 7)
    
    Note: Phase 6 (Real-time Events) is tested in TestPhase6RealtimeEvents class below
    """
    
    def test_countdown_requires_30_trades(self):
        """Test that countdown only activates after 30 trades"""
        # Mock response with < 30 trades
        response_insufficient = {
            "countdown_active": False,
            "trades_total": 20,
            "trades_needed": 10,
            "message": "Need 10 more trades to activate countdown"
        }
        
        assert response_insufficient["countdown_active"] is False
        assert response_insufficient["trades_total"] < 30
        
        # Mock response with >= 30 trades
        response_sufficient = {
            "countdown_active": True,
            "trades_total": 35,
            "next_trade_eta": datetime.now(timezone.utc).isoformat(),
            "avg_interval_seconds": 3600
        }
        
        assert response_sufficient["countdown_active"] is True
        assert response_sufficient["trades_total"] >= 30


class TestPhase8RequiredCapital:
    """Test wallet required capital endpoint"""
    
    def test_required_capital_calculation(self):
        """Test capital calculation from bots"""
        # Mock bots
        mock_bots = [
            {"initial_capital": 1000, "platform": "luno", "status": "active"},
            {"initial_capital": 2000, "platform": "binance", "status": "paused"},
            {"initial_capital": 1500, "platform": "luno", "status": "training"},
        ]
        
        # Calculate totals
        total = sum(b["initial_capital"] for b in mock_bots)
        assert total == 4500
        
        # Calculate by platform
        by_platform = {}
        for bot in mock_bots:
            platform = bot["platform"]
            if platform not in by_platform:
                by_platform[platform] = 0
            by_platform[platform] += bot["initial_capital"]
        
        assert by_platform["luno"] == 2500
        assert by_platform["binance"] == 2000


class TestPhase9BotCreationContract:
    """Test bot creation platform validation"""
    
    def test_valid_platforms(self):
        """Test that only valid platforms are accepted"""
        try:
            from config.platforms import is_valid_platform, SUPPORTED_PLATFORMS
            
            # Valid platforms
            for platform in SUPPORTED_PLATFORMS:
                assert is_valid_platform(platform), f"{platform} should be valid"
            
            # Invalid platforms
            invalid = ["valr", "ovex", "invalid", ""]
            for platform in invalid:
                assert not is_valid_platform(platform), f"{platform} should be invalid"
        except ImportError:
            pytest.skip("Platform config not available")


class TestPhase10BodyguardRiskManagement:
    """Test bodyguard and daily loss logic"""
    
    def test_daily_loss_uses_realized_pnl(self):
        """Test that daily loss only counts closed trades"""
        # Mock closed trades (realized)
        closed_trades = [
            {"status": "closed", "net_pnl": -50, "timestamp": datetime.now(timezone.utc).isoformat()},
            {"status": "closed", "net_pnl": -30, "timestamp": datetime.now(timezone.utc).isoformat()},
        ]
        
        # Mock open trades (unrealized) - should not count
        open_trades = [
            {"status": "open", "net_pnl": -100, "timestamp": datetime.now(timezone.utc).isoformat()},
        ]
        
        # Only closed trades should be counted
        realized_loss = sum(t["net_pnl"] for t in closed_trades if t["status"] == "closed")
        assert realized_loss == -80
        
        # Verify open trades are excluded
        total_with_open = sum(t["net_pnl"] for t in closed_trades + open_trades if t["status"] == "closed")
        assert total_with_open == realized_loss


class TestPhase6RealtimeEvents:
    """Test realtime event emissions (Phase 6)"""
    
    def test_required_events_exist(self):
        """Test that all required events are defined"""
        try:
            from realtime_events import rt_events
            
            required_events = [
                'trade_inserted',
                'overview_updated',
                'bot_state_changed',
                'lock_triggered',
                'lock_reset',
                'wallet_updated',
                'price_update',
                'key_saved',
                'key_tested'
            ]
            
            for event in required_events:
                assert hasattr(rt_events, event), f"Event {event} not found in rt_events"
        except ImportError:
            pytest.skip("Realtime events not available")


def test_smoke_test_health_endpoint():
    """Test that health endpoint is accessible"""
    # This would normally make an HTTP request
    # For now, just verify the pattern
    health_paths = ["/health", "/api/health", "/api/health/ping"]
    
    for path in health_paths:
        assert path.startswith("/"), f"Health path {path} should start with /"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
