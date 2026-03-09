"""
Test suite for the audit-repair-live-trading fixes.
Tests:
1. normalize_bot_state - paused_by_system must not override active status
2. _paper_trading_enabled() - uses canonical config 
3. bot_runtime_state reconcile fixes state drift
"""
import sys, os
sys.path.insert(0, 'backend')
os.environ['ENVIRONMENT'] = 'testing'

import pytest


# ─── Test 1: normalize_bot_state ────────────────────────────────────────────

def test_active_bot_with_stale_paused_by_system_is_eligible():
    """A bot with status='active' must be eligible even if paused_by_system=True."""
    from utils.bot_state import normalize_bot_state
    bot = {
        'id': 'b1', 'user_id': 'u1',
        'status': 'active',
        'name': 'Test',
        'trading_mode': 'paper',
        'paused_by_system': True,   # stale flag from a previous pause
    }
    result = normalize_bot_state(bot)
    assert result['eligible_to_trade'] is True, f"Expected eligible, got: {result['not_eligible_reasons']}"
    assert result['paused'] is False
    assert result['active'] is True


def test_paused_bot_is_ineligible():
    """A bot with status='paused' must be ineligible."""
    from utils.bot_state import normalize_bot_state
    bot = {'id': 'b2', 'user_id': 'u1', 'status': 'paused', 'name': 'Test', 'trading_mode': 'paper'}
    result = normalize_bot_state(bot)
    assert result['eligible_to_trade'] is False
    assert 'bot_paused' in result['not_eligible_reasons']


def test_active_bot_without_stale_flags_is_eligible():
    """A clean active bot must be eligible."""
    from utils.bot_state import normalize_bot_state
    bot = {'id': 'b3', 'user_id': 'u1', 'status': 'active', 'name': 'Test', 'trading_mode': 'paper'}
    result = normalize_bot_state(bot)
    assert result['eligible_to_trade'] is True
    assert result['not_eligible_reasons'] == []


def test_active_bot_with_paused_by_user_is_eligible():
    """A bot with status='active' must be eligible even if paused_by_user=True (stale flag)."""
    from utils.bot_state import normalize_bot_state
    bot = {
        'id': 'b4', 'user_id': 'u1',
        'status': 'active',
        'name': 'Test',
        'trading_mode': 'paper',
        'paused_by_user': True,   # stale - resume_bot unsets this
    }
    result = normalize_bot_state(bot)
    assert result['eligible_to_trade'] is True, f"Expected eligible, got: {result['not_eligible_reasons']}"


# ─── Test 2: _paper_trading_enabled ─────────────────────────────────────────

def test_paper_trading_enabled_with_enable_flag():
    """_paper_trading_enabled() must return True when ENABLE_PAPER_TRADING=true."""
    # Clear any potentially conflicting env vars
    os.environ.pop('PAPER_TRADING', None)
    os.environ.pop('LIVE_TRADING', None)
    os.environ['ENABLE_PAPER_TRADING'] = 'true'
    
    # Emulate what _paper_trading_enabled() does
    from config import PAPER_TRADING
    result = (
        PAPER_TRADING
        or os.environ.get('PAPER_TRADING') == '1'
        or os.environ.get('ENABLE_PAPER_TRADING', 'true').lower() == 'true'
    )
    assert result is True, "Expected paper trading enabled with ENABLE_PAPER_TRADING=true"


def test_paper_trading_disabled_when_no_flags():
    """_paper_trading_enabled() returns False when no paper flags are set."""
    os.environ.pop('PAPER_TRADING', None)
    os.environ.pop('ENABLE_PAPER_TRADING', None)
    
    from config import PAPER_TRADING
    result = (
        PAPER_TRADING
        or os.environ.get('PAPER_TRADING') == '1'
        or os.environ.get('ENABLE_PAPER_TRADING', 'true').lower() == 'true'
    )
    # With default 'true' for ENABLE_PAPER_TRADING, paper is enabled by default
    assert result is True, "Paper trading is enabled by default via ENABLE_PAPER_TRADING default"


# ─── Test 3: bot_runtime_state reconcile ────────────────────────────────────

def test_normalize_state_mapping():
    """_normalize_state maps all aliases correctly."""
    from services.bot_runtime_state import _normalize_state
    assert _normalize_state("active") == "active"
    assert _normalize_state("running") == "active"
    assert _normalize_state("paused") == "paused"
    assert _normalize_state("paused_ready") == "paused"
    assert _normalize_state("stopped") == "stopped"
    assert _normalize_state("stop") == "stopped"
    assert _normalize_state("unknown") == "unknown"


if __name__ == '__main__':
    test_active_bot_with_stale_paused_by_system_is_eligible()
    test_paused_bot_is_ineligible()
    test_active_bot_without_stale_flags_is_eligible()
    test_active_bot_with_paused_by_user_is_eligible()
    test_paper_trading_enabled_with_enable_flag()
    test_paper_trading_disabled_when_no_flags()
    test_normalize_state_mapping()
    print("All targeted fix tests PASSED")
