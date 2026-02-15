"""
Tests for Trading Mode Gating and Paper Funds Enforcement
Phase 4A, 4B, 4C implementation tests
"""

import pytest
import asyncio
import os
from services.paper_wallet_ledger import paper_wallet_ledger
from services.trading_mode_validator import trading_mode_validator
import database as db


class TestPaperWalletLedger:
    """Test paper wallet ledger functionality"""
    
    @pytest.mark.asyncio
    async def test_reserve_funds_success(self):
        """Test successful funds reservation"""
        user_id = "test_user_001"
        bot_id = "test_bot_001"
        amount = 1000.0
        
        success, msg = await paper_wallet_ledger.reserve_funds(user_id, bot_id, amount)
        assert success is True
        assert "Reserved" in msg
        
        # Cleanup
        await paper_wallet_ledger.release_funds(bot_id)
    
    @pytest.mark.asyncio
    async def test_reserve_funds_invalid_amount(self):
        """Test reservation with invalid amount"""
        user_id = "test_user_002"
        bot_id = "test_bot_002"
        amount = 0.0
        
        success, msg = await paper_wallet_ledger.reserve_funds(user_id, bot_id, amount)
        assert success is False
        assert "Invalid amount" in msg
    
    @pytest.mark.asyncio
    async def test_get_balance(self):
        """Test getting wallet balance"""
        user_id = "test_user_003"
        bot_id = "test_bot_003"
        amount = 2000.0
        
        # Reserve funds first
        await paper_wallet_ledger.reserve_funds(user_id, bot_id, amount)
        
        # Get balance
        success, balance, msg = await paper_wallet_ledger.get_balance(bot_id)
        assert success is True
        assert balance == amount
        
        # Cleanup
        await paper_wallet_ledger.release_funds(bot_id)
    
    @pytest.mark.asyncio
    async def test_can_trade_sufficient_funds(self):
        """Test can_trade with sufficient funds"""
        user_id = "test_user_004"
        bot_id = "test_bot_004"
        amount = 1000.0
        
        # Reserve funds
        await paper_wallet_ledger.reserve_funds(user_id, bot_id, amount)
        
        # Check if can trade
        can_trade, msg = await paper_wallet_ledger.can_trade(bot_id, 500.0)
        assert can_trade is True
        
        # Cleanup
        await paper_wallet_ledger.release_funds(bot_id)
    
    @pytest.mark.asyncio
    async def test_can_trade_insufficient_funds(self):
        """Test can_trade with insufficient funds"""
        user_id = "test_user_005"
        bot_id = "test_bot_005"
        amount = 500.0
        
        # Reserve funds
        await paper_wallet_ledger.reserve_funds(user_id, bot_id, amount)
        
        # Check if can trade with more than available
        can_trade, msg = await paper_wallet_ledger.can_trade(bot_id, 1000.0)
        assert can_trade is False
        assert "Insufficient" in msg
        
        # Cleanup
        await paper_wallet_ledger.release_funds(bot_id)
    
    @pytest.mark.asyncio
    async def test_debit_funds(self):
        """Test debiting funds from wallet"""
        user_id = "test_user_006"
        bot_id = "test_bot_006"
        initial_amount = 1000.0
        debit_amount = 300.0
        
        # Reserve funds
        await paper_wallet_ledger.reserve_funds(user_id, bot_id, initial_amount)
        
        # Debit funds
        success, msg = await paper_wallet_ledger.debit(bot_id, debit_amount, "test trade")
        assert success is True
        
        # Check new balance
        success, balance, msg = await paper_wallet_ledger.get_balance(bot_id)
        assert balance == initial_amount - debit_amount
        
        # Cleanup
        await paper_wallet_ledger.release_funds(bot_id)
    
    @pytest.mark.asyncio
    async def test_credit_funds(self):
        """Test crediting funds to wallet"""
        user_id = "test_user_007"
        bot_id = "test_bot_007"
        initial_amount = 1000.0
        credit_amount = 200.0
        
        # Reserve funds
        await paper_wallet_ledger.reserve_funds(user_id, bot_id, initial_amount)
        
        # Credit funds
        success, msg = await paper_wallet_ledger.credit(bot_id, credit_amount, "trade profit")
        assert success is True
        
        # Check new balance
        success, balance, msg = await paper_wallet_ledger.get_balance(bot_id)
        assert balance == initial_amount + credit_amount
        
        # Cleanup
        await paper_wallet_ledger.release_funds(bot_id)
    
    @pytest.mark.asyncio
    async def test_debit_insufficient_funds(self):
        """Test debit fails with insufficient funds"""
        user_id = "test_user_008"
        bot_id = "test_bot_008"
        initial_amount = 500.0
        debit_amount = 1000.0
        
        # Reserve funds
        await paper_wallet_ledger.reserve_funds(user_id, bot_id, initial_amount)
        
        # Try to debit more than available
        success, msg = await paper_wallet_ledger.debit(bot_id, debit_amount, "test trade")
        assert success is False
        assert "Insufficient" in msg
        
        # Cleanup
        await paper_wallet_ledger.release_funds(bot_id)


class TestTradingModeValidator:
    """Test trading mode validation"""
    
    @pytest.mark.asyncio
    async def test_validate_paper_trading(self):
        """Test paper trading validation"""
        # Mock bot data
        bot_data = {
            "id": "test_bot_paper_001",
            "user_id": "test_user_paper_001",
            "trading_mode": "paper",
            "name": "Test Paper Bot"
        }
        
        os.environ['PAPER_TRADING'] = '1'

        # Mock system mode (autopilot enabled)
        await db.system_modes_collection.insert_one({
            "user_id": bot_data["user_id"],
            "autopilot": True,
            "paperTrading": True,
            "emergencyStop": False
        })
        
        can_trade, mode, reason = await trading_mode_validator.validate_paper_trading(bot_data)
        assert can_trade is True
        assert mode == "paper"
        
        # Cleanup
        await db.system_modes_collection.delete_one({"user_id": bot_data["user_id"]})
        os.environ.pop('PAPER_TRADING', None)
    
    @pytest.mark.asyncio
    async def test_validate_paper_trading_emergency_stop(self):
        """Test paper trading blocked by emergency stop"""
        bot_data = {
            "id": "test_bot_paper_002",
            "user_id": "test_user_paper_002",
            "trading_mode": "paper",
            "name": "Test Paper Bot 2"
        }
        
        os.environ['PAPER_TRADING'] = '1'

        # Mock system mode with emergency stop
        await db.system_modes_collection.insert_one({
            "user_id": bot_data["user_id"],
            "autopilot": True,
            "paperTrading": True,
            "emergencyStop": True
        })
        
        can_trade, mode, reason = await trading_mode_validator.validate_paper_trading(bot_data)
        assert can_trade is False
        assert "Emergency stop" in reason
        
        # Cleanup
        await db.system_modes_collection.delete_one({"user_id": bot_data["user_id"]})
        os.environ.pop('PAPER_TRADING', None)
    
    @pytest.mark.asyncio
    async def test_validate_live_trading_no_api_keys(self):
        """Test live trading blocked without API keys"""
        bot_data = {
            "id": "test_bot_live_001",
            "user_id": "test_user_live_001",
            "trading_mode": "live",
            "exchange": "binance",
            "name": "Test Live Bot"
        }
        
        os.environ['LIVE_TRADING'] = '1'

        # Mock system mode (live enabled)
        await db.system_modes_collection.insert_one({
            "user_id": bot_data["user_id"],
            "autopilot": True,
            "liveTrading": True,
            "emergencyStop": False
        })
        
        can_trade, mode, reason = await trading_mode_validator.validate_live_trading(bot_data)
        assert can_trade is False
        assert "No API keys" in reason or "API keys" in reason
        
        # Cleanup
        await db.system_modes_collection.delete_one({"user_id": bot_data["user_id"]})
        os.environ.pop('LIVE_TRADING', None)
    
    @pytest.mark.asyncio
    async def test_validate_global_trading_gates_both_disabled(self):
        """Test global gates with both modes disabled"""
        import os
        
        # Temporarily set environment variables
        os.environ['PAPER_TRADING'] = '0'
        os.environ['LIVE_TRADING'] = '0'
        
        trading_allowed, reason = await trading_mode_validator.validate_global_trading_gates()
        assert trading_allowed is False
        assert "No trading mode enabled" in reason
        
        # Reset environment variables
        os.environ.pop('PAPER_TRADING', None)
        os.environ.pop('LIVE_TRADING', None)
    
    @pytest.mark.asyncio
    async def test_validate_bot_trading_mode(self):
        """Test bot trading mode validation"""
        bot_id = "test_bot_mode_001"
        
        # Create mock bot in database
        await db.bots_collection.insert_one({
            "id": bot_id,
            "user_id": "test_user_mode_001",
            "trading_mode": "paper",
            "name": "Test Mode Bot",
            "status": "active"
        })
        
        os.environ['PAPER_TRADING'] = '1'

        # Mock system mode
        await db.system_modes_collection.insert_one({
            "user_id": "test_user_mode_001",
            "autopilot": True,
            "paperTrading": True,
            "emergencyStop": False
        })
        
        can_trade, mode, reason = await trading_mode_validator.validate_bot_trading_mode(bot_id)
        assert can_trade is True
        assert mode == "paper"
        
        # Cleanup
        await db.bots_collection.delete_one({"id": bot_id})
        await db.system_modes_collection.delete_one({"user_id": "test_user_mode_001"})
        os.environ.pop('PAPER_TRADING', None)

    @pytest.mark.asyncio
    async def test_paper_mode_allowed_when_live_disabled(self):
        """Paper mode allowed even if live trading is disabled for user."""
        bot_data = {
            "id": "test_bot_paper_override_001",
            "user_id": "test_user_paper_override_001",
            "trading_mode": "live",
            "exchange": "binance",
            "name": "Paper Override Bot"
        }

        os.environ['PAPER_TRADING'] = '1'

        await db.system_modes_collection.insert_one({
            "user_id": bot_data["user_id"],
            "autopilot": True,
            "paperTrading": True,
            "liveTrading": False,
            "emergencyStop": False
        })

        can_trade, mode, reason = await trading_mode_validator.validate_bot_trading_mode(
            bot_data["id"], bot_data
        )
        assert can_trade is True
        assert mode == "paper"

        await db.system_modes_collection.delete_one({"user_id": bot_data["user_id"]})
        os.environ.pop('PAPER_TRADING', None)

    @pytest.mark.asyncio
    async def test_live_mode_blocked_without_user_flag(self):
        """Live mode should be blocked when user liveTrading is false."""
        bot_data = {
            "id": "test_bot_live_block_001",
            "user_id": "test_user_live_block_001",
            "trading_mode": "live",
            "exchange": "binance",
            "name": "Live Block Bot"
        }

        os.environ['LIVE_TRADING'] = '1'

        await db.system_modes_collection.insert_one({
            "user_id": bot_data["user_id"],
            "autopilot": True,
            "paperTrading": False,
            "liveTrading": False,
            "emergencyStop": False
        })

        can_trade, mode, reason = await trading_mode_validator.validate_bot_trading_mode(
            bot_data["id"], bot_data
        )
        assert can_trade is False
        assert mode == "live"
        assert "Live trading not enabled for user" in reason

        await db.system_modes_collection.delete_one({"user_id": bot_data["user_id"]})
        os.environ.pop('LIVE_TRADING', None)

    @pytest.mark.asyncio
    async def test_live_mode_blocked_by_env_gate(self):
        """Live mode should be blocked when LIVE_TRADING env gate is disabled."""
        bot_data = {
            "id": "test_bot_live_env_001",
            "user_id": "test_user_live_env_001",
            "trading_mode": "live",
            "exchange": "binance",
            "name": "Live Env Bot"
        }

        os.environ.pop('LIVE_TRADING', None)
        os.environ.pop('ENABLE_LIVE_TRADING', None)

        await db.system_modes_collection.insert_one({
            "user_id": bot_data["user_id"],
            "autopilot": True,
            "paperTrading": False,
            "liveTrading": True,
            "emergencyStop": False
        })

        can_trade, mode, reason = await trading_mode_validator.validate_bot_trading_mode(
            bot_data["id"], bot_data
        )
        assert can_trade is False
        assert mode == "live"
        assert "Live trading not enabled globally" in reason

        await db.system_modes_collection.delete_one({"user_id": bot_data["user_id"]})


class TestIntegration:
    """Integration tests for Phase 4A-4C"""
    
    @pytest.mark.asyncio
    async def test_bot_creation_reserves_paper_funds(self):
        """Test that bot creation reserves paper funds"""
        from engines.bot_manager import bot_manager
        
        user_id = "test_user_integration_001"
        bot_name = "Integration Test Bot"
        exchange = "binance"
        capital = 1000.0
        
        # Create bot
        result = await bot_manager.create_bot(
            user_id=user_id,
            name=bot_name,
            exchange=exchange,
            risk_mode='safe',
            capital=capital
        )
        
        if result.get('success'):
            bot_id = result['bot']['id']
            
            # Check paper wallet has reserved funds
            success, balance, msg = await paper_wallet_ledger.get_balance(bot_id)
            assert success is True
            assert balance == capital
            
            # Cleanup
            await bot_manager.delete_bot(user_id, bot_id=bot_id)
    
    @pytest.mark.asyncio
    async def test_bot_creation_requires_positive_capital(self):
        """Test that bot creation requires capital > 0"""
        from engines.bot_manager import bot_manager
        
        user_id = "test_user_integration_002"
        bot_name = "Zero Capital Bot"
        exchange = "binance"
        capital = 0.0
        
        # Try to create bot with zero capital
        result = await bot_manager.create_bot(
            user_id=user_id,
            name=bot_name,
            exchange=exchange,
            risk_mode='safe',
            capital=capital
        )
        
        assert result.get('success') is False
        assert "initial_capital > 0" in result.get('message', '')


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
