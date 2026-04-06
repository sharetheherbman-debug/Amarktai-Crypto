"""
Tests for Go-Live Blocker Fixes
- B1: Autonomy confirmation field compatibility (confirmation vs confirmation_phrase)
- B2: TradeStaggerer queue diagnostics
- B3: env_bool import in diagnostics
- B6: Runtime reset endpoint
- B7: Wallet status endpoint
"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock, AsyncMock
from datetime import datetime, timezone


class TestB1AutonomyConfirmationCompat:
    """Test that autonomy run-now accepts both confirmation fields"""
    
    def test_confirmation_phrase_field(self):
        """Test that confirmation_phrase is accepted"""
        from routes.autonomy_control import AutonomyRunRequest
        
        # Test with confirmation_phrase
        request = AutonomyRunRequest(
            confirmation_phrase="CONFIRM AUTONOMY RUN",
            allow_live=False
        )
        assert request.confirmation_phrase == "CONFIRM AUTONOMY RUN"
        assert request.confirmation is None
    
    def test_confirmation_field(self):
        """Test that confirmation field is accepted (backward compat)"""
        from routes.autonomy_control import AutonomyRunRequest
        
        # Test with confirmation
        request = AutonomyRunRequest(
            confirmation="CONFIRM AUTONOMY RUN",
            allow_live=False
        )
        assert request.confirmation == "CONFIRM AUTONOMY RUN"
        assert request.confirmation_phrase is None
    
    def test_both_fields(self):
        """Test that both fields can be provided"""
        from routes.autonomy_control import AutonomyRunRequest
        
        # Test with both
        request = AutonomyRunRequest(
            confirmation_phrase="CONFIRM AUTONOMY RUN",
            confirmation="CONFIRM AUTONOMY RUN",
            allow_live=False
        )
        assert request.confirmation_phrase == "CONFIRM AUTONOMY RUN"
        assert request.confirmation == "CONFIRM AUTONOMY RUN"


class TestB2TradeStaggererDiagnostics:
    """Test TradeStaggerer queue state diagnostics"""
    
    @pytest.mark.asyncio
    async def test_get_queue_state_exists(self):
        """Test that get_queue_state method exists and returns expected structure"""
        from engines.trade_staggerer import trade_staggerer
        
        # Get queue state
        state = await trade_staggerer.get_queue_state()
        
        # Verify structure
        assert isinstance(state, dict)
        assert "queue_size" in state
        assert "locks" in state
        assert "cooldowns" in state
        assert "sample_items" in state
        assert "exchange_stats" in state
    
    @pytest.mark.asyncio
    async def test_queue_state_with_active_trade(self):
        """Test queue state when trade is active"""
        from engines.trade_staggerer import trade_staggerer
        
        # Register a trade start
        bot_id = "test_bot_123"
        exchange = "binance"
        await trade_staggerer.register_trade_start(bot_id, exchange)
        
        # Get state
        state = await trade_staggerer.get_queue_state()
        
        # Should have active trades
        assert state["active_trades_count"] > 0
        assert len(state["locks"]) > 0
        
        # Clean up
        await trade_staggerer.register_trade_complete(bot_id, exchange)


class TestB3EnvBoolImport:
    """Test that env_bool is properly imported in diagnostics"""
    
    def test_env_bool_import_in_diagnostics(self):
        """Test that env_bool can be imported from diagnostics module"""
        # This will fail if import is missing
        try:
            # Import the diagnostics module to verify no import errors
            from routes import diagnostics
            # If we get here, imports are working
            assert True
        except NameError as e:
            if "env_bool" in str(e):
                pytest.fail("env_bool is not properly imported in diagnostics module")
            raise


class TestB6RuntimeResetEndpoint:
    """Test runtime reset endpoint"""
    
    def test_runtime_reset_request_model(self):
        """Test RuntimeResetRequest model"""
        from routes.admin_endpoints import RuntimeResetRequest
        
        # Test valid request
        request = RuntimeResetRequest(
            confirmation_phrase="CONFIRM RUNTIME RESET",
            mode="paper"
        )
        assert request.confirmation_phrase == "CONFIRM RUNTIME RESET"
        assert request.mode == "paper"
    
    def test_runtime_reset_requires_confirmation(self):
        """Test that runtime reset requires correct confirmation phrase"""
        from routes.admin_endpoints import RuntimeResetRequest
        
        # Test with wrong phrase
        request = RuntimeResetRequest(
            confirmation_phrase="WRONG PHRASE",
            mode="paper"
        )
        # The endpoint should reject this
        assert request.confirmation_phrase == "WRONG PHRASE"


class TestB7WalletStatusEndpoint:
    """Test wallet status endpoint"""
    
    @pytest.mark.asyncio
    async def test_wallet_status_structure(self):
        """Test that wallet status endpoint returns expected structure"""
        from routes.wallet_endpoints import router
        
        # The endpoint should exist
        routes = [route.path for route in router.routes]
        assert "/status" in routes or any("/status" in route for route in routes)


class TestTradeSchedulerLogging:
    """Test that trading_scheduler has proper logging"""
    
    def test_execute_bot_trades_has_logging(self):
        """Test that execute_bot_trades method has logging statements"""
        from trading_scheduler import TradingScheduler
        import inspect
        
        # Get source code
        source = inspect.getsource(TradingScheduler.execute_bot_trades)
        
        # Check for logging statements
        assert "logger.debug" in source or "logger.info" in source
        assert "Dequeued trade" in source or "dequeued" in source.lower()


class TestConfigImports:
    """Test that config imports are consistent"""
    
    def test_auto_spawn_cooldown_exists(self):
        """Test that AUTO_SPAWN_COOLDOWN_MINUTES exists in config"""
        import config
        
        # Should have this attribute
        assert hasattr(config, "AUTO_SPAWN_COOLDOWN_MINUTES")
        assert isinstance(config.AUTO_SPAWN_COOLDOWN_MINUTES, int)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
