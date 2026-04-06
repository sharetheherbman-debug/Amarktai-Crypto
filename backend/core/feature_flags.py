"""
Feature Flags Service - Unified Trading Mode & Feature Control

This module provides a single source of truth for all feature flags with:
1. Backward-compatible env var aliases
2. Precedence rules: ENV = hard limits, DB/system mode = user control
3. Clear reasoning for effective settings

Usage:
    from core.feature_flags import get_effective_flags
    
    flags = await get_effective_flags(user_id)
    if flags['enable_paper_trading']:
        # Paper trading is allowed
        pass
"""

import logging
from typing import Dict, Optional
from utils.env_utils import env_bool
import database as db

logger = logging.getLogger(__name__)


def get_env_flags() -> Dict[str, bool]:
    """
    Get all environment-level feature flags with backward compatibility.
    
    Canonical flags are:
    - ENABLE_TRADING: Master switch for all trading
    - ENABLE_PAPER_TRADING: Paper trading mode
    - ENABLE_LIVE_TRADING: Live trading mode
    - ENABLE_AUTOPILOT: Autonomous bot management
    
    Backward-compatible aliases:
    - PAPER_TRADING → ENABLE_PAPER_TRADING
    - LIVE_TRADING → ENABLE_LIVE_TRADING
    - AUTOPILOT_ENABLED → ENABLE_AUTOPILOT
    
    Returns:
        Dict with canonical flag names and boolean values
    """
    # Master trading switch
    enable_trading = env_bool('ENABLE_TRADING', False)
    
    # Paper trading: Check canonical ENABLE_PAPER_TRADING; also honour legacy PAPER_TRADING.
    # Both default to True so paper is user-controllable via system mode unless an env var
    # is explicitly set to false/0/no to hard-disable.  AND ensures either variable alone
    # can hard-disable (e.g. PAPER_TRADING=false in a legacy deployment).
    enable_paper_trading = (
        env_bool('ENABLE_PAPER_TRADING', True) and
        env_bool('PAPER_TRADING', True)
    )
    
    # Live trading: Check both ENABLE_LIVE_TRADING and legacy LIVE_TRADING
    enable_live_trading = (
        env_bool('ENABLE_LIVE_TRADING', False) or 
        env_bool('LIVE_TRADING', False)
    )
    
    # Autopilot: Check both ENABLE_AUTOPILOT and legacy AUTOPILOT_ENABLED
    enable_autopilot = (
        env_bool('ENABLE_AUTOPILOT', False) or 
        env_bool('AUTOPILOT_ENABLED', False)
    )
    
    return {
        'enable_trading': enable_trading,
        'enable_paper_trading': enable_paper_trading,
        'enable_live_trading': enable_live_trading,
        'enable_autopilot': enable_autopilot,
    }


async def get_system_mode_flags(user_id: str) -> Dict[str, bool]:
    """
    Get user's system mode flags from database.
    These represent user preferences within environment hard limits.
    
    Args:
        user_id: User ID
        
    Returns:
        Dict with system mode flags
    """
    try:
        # Get user's system mode document
        mode_doc = await db.system_modes_collection.find_one(
            {"user_id": user_id}, 
            {"_id": 0}
        )
        
        if not mode_doc:
            # Return safe defaults
            return {
                'paper_trading': True,
                'live_trading': False,
                'autopilot': False,
            }
        
        return {
            'paper_trading': mode_doc.get('paperTrading', False),
            'live_trading': mode_doc.get('liveTrading', False),
            'autopilot': mode_doc.get('autopilot', False),
        }
    except Exception as e:
        logger.error(f"Error fetching system mode flags for user {user_id[:8]}: {e}")
        # Return safe defaults on error
        return {
            'paper_trading': True,
            'live_trading': False,
            'autopilot': False,
        }


async def get_effective_flags(user_id: str) -> Dict:
    """
    Get effective feature flags considering both environment and user preferences.
    
    Precedence rule:
    - ENV flags are hard safety limits (if env disables, cannot be enabled by user)
    - DB/system mode is user control within env hard limits
    - Effective flag = ENV flag AND system mode flag
    
    Args:
        user_id: User ID
        
    Returns:
        {
            'enable_trading': bool,
            'enable_paper_trading': bool,
            'enable_live_trading': bool,
            'enable_autopilot': bool,
            'effective_mode': 'paper' | 'live' | 'autopilot' | 'disabled',
            'reasons': {
                'paper_trading': str,
                'live_trading': str,
                'autopilot': str,
            }
        }
    """
    # Get environment hard limits
    env_flags = get_env_flags()
    
    # Get user's system mode preferences
    system_mode = await get_system_mode_flags(user_id)
    
    # Calculate effective flags with precedence rules
    reasons = {}
    
    # Paper trading: ENV must enable AND system mode must enable
    enable_paper_trading = env_flags['enable_paper_trading'] and system_mode['paper_trading']
    if not env_flags['enable_paper_trading']:
        reasons['paper_trading'] = "Disabled in environment (ENV hard limit)"
    elif not system_mode['paper_trading']:
        reasons['paper_trading'] = "Disabled in system mode (user preference)"
    else:
        reasons['paper_trading'] = "Enabled"
    
    # Live trading: ENV must enable AND system mode must enable
    enable_live_trading = env_flags['enable_live_trading'] and system_mode['live_trading']
    if not env_flags['enable_live_trading']:
        reasons['live_trading'] = "Disabled in environment (ENV hard limit)"
    elif not system_mode['live_trading']:
        reasons['live_trading'] = "Disabled in system mode (user preference)"
    else:
        reasons['live_trading'] = "Enabled"
    
    # Autopilot: ENV must enable AND system mode must enable AND trading must be enabled
    enable_autopilot = (
        env_flags['enable_autopilot'] and 
        system_mode['autopilot'] and
        (enable_paper_trading or enable_live_trading)
    )
    if not env_flags['enable_autopilot']:
        reasons['autopilot'] = "Disabled in environment (ENV hard limit)"
    elif not system_mode['autopilot']:
        reasons['autopilot'] = "Disabled in system mode (user preference)"
    elif not (enable_paper_trading or enable_live_trading):
        reasons['autopilot'] = "No trading mode enabled"
    else:
        reasons['autopilot'] = "Enabled"
    
    # Determine effective mode
    effective_mode = "disabled"
    if enable_autopilot:
        effective_mode = "autopilot"
    elif enable_live_trading:
        effective_mode = "live"
    elif enable_paper_trading:
        effective_mode = "paper"
    
    return {
        'enable_trading': env_flags['enable_trading'],
        'enable_paper_trading': enable_paper_trading,
        'enable_live_trading': enable_live_trading,
        'enable_autopilot': enable_autopilot,
        'effective_mode': effective_mode,
        'reasons': reasons,
        # Also include raw env and system mode for debugging
        'env_flags': env_flags,
        'system_mode': system_mode,
    }


async def can_resume_bot(bot: Dict, user_id: str) -> tuple[bool, Optional[str]]:
    """
    Check if a bot can be resumed based on effective feature flags.
    
    Args:
        bot: Bot document with trading_mode field
        user_id: User ID
        
    Returns:
        (can_resume, reason_if_blocked)
    """
    flags = await get_effective_flags(user_id)
    trading_mode = bot.get('trading_mode', 'paper')
    
    if trading_mode == 'paper':
        if not flags['enable_paper_trading']:
            return False, flags['reasons']['paper_trading']
    elif trading_mode == 'live':
        if not flags['enable_live_trading']:
            return False, flags['reasons']['live_trading']
    else:
        return False, f"Unknown trading mode: {trading_mode}"
    
    return True, None
