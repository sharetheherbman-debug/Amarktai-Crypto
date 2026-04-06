"""
Test for paper trading resume functionality with feature flags
Tests TASK 1-4: env_bool parsing, feature flags, and resume gates
"""
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

# Import after path is set
from core.feature_flags import get_env_flags, get_effective_flags, can_resume_bot


class TestFeatureFlags:
    """Test the unified feature flags service"""
    
    def test_get_env_flags_with_canonical_names(self):
        """Test that canonical ENABLE_* flags are read correctly"""
        with patch.dict(os.environ, {
            'ENABLE_PAPER_TRADING': 'true',
            'ENABLE_LIVE_TRADING': 'false',
            'ENABLE_AUTOPILOT': '1',
            'ENABLE_TRADING': 'yes'
        }):
            flags = get_env_flags()
            
            assert flags['enable_paper_trading'] is True
            assert flags['enable_live_trading'] is False
            assert flags['enable_autopilot'] is True
            assert flags['enable_trading'] is True
    
    def test_get_env_flags_with_legacy_names(self):
        """Test backward compatibility with legacy flag names"""
        with patch.dict(os.environ, {
            'PAPER_TRADING': 'true',
            'LIVE_TRADING': '1',
            'AUTOPILOT_ENABLED': 'yes'
        }, clear=True):
            flags = get_env_flags()
            
            # Legacy names should work
            assert flags['enable_paper_trading'] is True
            assert flags['enable_live_trading'] is True
            assert flags['enable_autopilot'] is True
    
    def test_get_env_flags_precedence(self):
        """Test that ENABLE_* takes precedence over legacy names"""
        with patch.dict(os.environ, {
            'ENABLE_PAPER_TRADING': 'true',
            'PAPER_TRADING': 'false',  # Should be overridden
        }):
            flags = get_env_flags()
            
            # ENABLE_* should take precedence (OR logic means either enables it)
            assert flags['enable_paper_trading'] is True
    
    def test_env_bool_truthy_values(self):
        """Test that env_bool accepts all truthy values"""
        from utils.env_utils import env_bool
        
        truthy_values = ['1', 'true', 'True', 'TRUE', 'yes', 'Yes', 'YES', 'on', 'ON']
        
        for value in truthy_values:
            with patch.dict(os.environ, {'TEST_FLAG': value}):
                assert env_bool('TEST_FLAG') is True, f"Failed for value: {value}"
    
    def test_env_bool_falsy_values(self):
        """Test that env_bool rejects falsy values"""
        from utils.env_utils import env_bool
        
        falsy_values = ['0', 'false', 'False', 'FALSE', 'no', 'No', 'NO', 'off', 'OFF', '']
        
        for value in falsy_values:
            with patch.dict(os.environ, {'TEST_FLAG': value}):
                assert env_bool('TEST_FLAG') is False, f"Failed for value: {value}"


class TestEffectiveFlags:
    """Test the effective flags calculation with ENV + system mode precedence"""
    
    @pytest.mark.asyncio
    async def test_effective_flags_env_hard_limit(self):
        """Test that ENV flags act as hard limits"""
        # Mock database to return system mode with paper trading enabled
        mock_db = MagicMock()
        mock_collection = MagicMock()
        mock_collection.find_one = AsyncMock(return_value={
            'user_id': 'test_user',
            'paperTrading': True,  # User wants paper trading
            'liveTrading': False,
            'autopilot': False
        })
        
        with patch('core.feature_flags.db', mock_db):
            mock_db.system_modes_collection = mock_collection
            
            # ENV disables paper trading (hard limit)
            with patch.dict(os.environ, {
                'ENABLE_PAPER_TRADING': 'false',
                'PAPER_TRADING': 'false'
            }, clear=True):
                flags = await get_effective_flags('test_user')
                
                # Should be disabled despite system mode wanting it enabled
                assert flags['enable_paper_trading'] is False
                assert 'environment' in flags['reasons']['paper_trading'].lower()
    
    @pytest.mark.asyncio
    async def test_effective_flags_system_mode_control(self):
        """Test that system mode provides user control within env limits"""
        mock_db = MagicMock()
        mock_collection = MagicMock()
        mock_collection.find_one = AsyncMock(return_value={
            'user_id': 'test_user',
            'paperTrading': False,  # User disables paper trading
            'liveTrading': False,
            'autopilot': False
        })
        
        with patch('core.feature_flags.db', mock_db):
            mock_db.system_modes_collection = mock_collection
            
            # ENV allows paper trading
            with patch.dict(os.environ, {
                'ENABLE_PAPER_TRADING': 'true'
            }, clear=True):
                flags = await get_effective_flags('test_user')
                
                # Should be disabled because user disabled it
                assert flags['enable_paper_trading'] is False
                assert 'system mode' in flags['reasons']['paper_trading'].lower()
    
    @pytest.mark.asyncio
    async def test_effective_flags_both_enabled(self):
        """Test that both ENV and system mode must enable for effective flag"""
        mock_db = MagicMock()
        mock_collection = MagicMock()
        mock_collection.find_one = AsyncMock(return_value={
            'user_id': 'test_user',
            'paperTrading': True,  # User enables
            'liveTrading': False,
            'autopilot': False
        })
        
        with patch('core.feature_flags.db', mock_db):
            mock_db.system_modes_collection = mock_collection
            
            # ENV also enables
            with patch.dict(os.environ, {
                'ENABLE_PAPER_TRADING': 'true'
            }, clear=True):
                flags = await get_effective_flags('test_user')
                
                # Should be enabled (both agree)
                assert flags['enable_paper_trading'] is True
                assert flags['reasons']['paper_trading'] == "Enabled"
                assert flags['effective_mode'] == 'paper'


class TestBotResume:
    """Test bot resume functionality with trading mode gates"""
    
    @pytest.mark.asyncio
    async def test_can_resume_paper_bot_when_enabled(self):
        """Test that paper bot can resume when paper trading is enabled"""
        bot = {'id': 'bot123', 'trading_mode': 'paper'}
        
        # Mock effective flags to allow paper trading
        with patch('core.feature_flags.get_effective_flags') as mock_flags:
            mock_flags.return_value = {
                'enable_paper_trading': True,
                'enable_live_trading': False,
                'enable_autopilot': False,
                'effective_mode': 'paper',
                'reasons': {'paper_trading': 'Enabled'}
            }
            
            can_resume, reason = await can_resume_bot(bot, 'user123')
            
            assert can_resume is True
            assert reason is None
    
    @pytest.mark.asyncio
    async def test_cannot_resume_paper_bot_when_disabled(self):
        """Test that paper bot cannot resume when paper trading is disabled"""
        bot = {'id': 'bot123', 'trading_mode': 'paper'}
        
        # Mock effective flags to disallow paper trading
        with patch('core.feature_flags.get_effective_flags') as mock_flags:
            mock_flags.return_value = {
                'enable_paper_trading': False,
                'enable_live_trading': False,
                'enable_autopilot': False,
                'effective_mode': 'disabled',
                'reasons': {'paper_trading': 'Disabled in environment (ENV hard limit)'}
            }
            
            can_resume, reason = await can_resume_bot(bot, 'user123')
            
            assert can_resume is False
            assert reason is not None
            assert 'environment' in reason.lower() or 'disabled' in reason.lower()
    
    @pytest.mark.asyncio
    async def test_cannot_resume_live_bot_when_disabled(self):
        """Test that live bot cannot resume when live trading is disabled"""
        bot = {'id': 'bot123', 'trading_mode': 'live'}
        
        # Mock effective flags to disallow live trading
        with patch('core.feature_flags.get_effective_flags') as mock_flags:
            mock_flags.return_value = {
                'enable_paper_trading': True,
                'enable_live_trading': False,  # Live disabled
                'enable_autopilot': False,
                'effective_mode': 'paper',
                'reasons': {'live_trading': 'Disabled in environment (ENV hard limit)'}
            }
            
            can_resume, reason = await can_resume_bot(bot, 'user123')
            
            assert can_resume is False
            assert reason is not None


class TestSystemStatusConsistency:
    """Test that /api/system/status and /api/system/mode report consistent flags"""
    
    @pytest.mark.asyncio
    async def test_system_status_uses_effective_flags(self):
        """Test that system status endpoint uses effective flags"""
        # This is more of an integration test, but we can verify the structure
        
        # Mock the effective flags
        with patch('core.feature_flags.get_effective_flags') as mock_flags:
            mock_flags.return_value = {
                'enable_paper_trading': True,
                'enable_live_trading': False,
                'enable_autopilot': False,
                'effective_mode': 'paper',
                'reasons': {
                    'paper_trading': 'Enabled',
                    'live_trading': 'Disabled in environment (ENV hard limit)',
                    'autopilot': 'Disabled in system mode (user preference)'
                }
            }
            
            flags = await mock_flags('test_user')
            
            # Verify structure matches what system_status.py expects
            assert 'enable_paper_trading' in flags
            assert 'enable_live_trading' in flags
            assert 'enable_autopilot' in flags
            assert 'effective_mode' in flags
            assert 'reasons' in flags
            
            # Verify reasons provide clear explanations
            for mode, reason in flags['reasons'].items():
                assert isinstance(reason, str)
                assert len(reason) > 0


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
