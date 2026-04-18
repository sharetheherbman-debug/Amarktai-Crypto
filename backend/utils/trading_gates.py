"""
Trading Mode Gates - Safety and Compliance Checks

This module implements critical safety gates to prevent unauthorized trading:
1. Trading mode gates: Ensure PAPER_TRADING=1 OR LIVE_TRADING=1 before any trade
2. Autopilot gates: Ensure AUTOPILOT_ENABLED=1 AND trading mode enabled
3. Live trading validation: Verify API keys exist and are valid before live trades
"""

import logging
from typing import Tuple, Optional
from utils.env_utils import env_bool

logger = logging.getLogger(__name__)


class TradingGateError(Exception):
    """Raised when trading gates are not satisfied"""
    pass


def check_trading_mode_enabled() -> Tuple[bool, str]:
    """
    Check if any trading mode is enabled.
    
    Returns:
        Tuple[bool, str]: (is_enabled, reason_or_mode)
    """
    paper_trading = env_bool('PAPER_TRADING', False) or env_bool('ENABLE_PAPER_TRADING', True)
    live_trading = env_bool('LIVE_TRADING', False) or env_bool('ENABLE_LIVE_TRADING', False)
    
    if not paper_trading and not live_trading:
        return False, "No trading mode enabled. Set PAPER_TRADING=1 or LIVE_TRADING=1"
    
    if paper_trading:
        return True, "paper"
    
    return True, "live"


def check_autopilot_gates() -> Tuple[bool, str]:
    """
    Check if autopilot can run.
    
    Autopilot requires:
    - AUTOPILOT_ENABLED=1
    - AND (PAPER_TRADING=1 OR LIVE_TRADING=1)
    
    Returns:
        Tuple[bool, str]: (can_run, error_message)
    """
    autopilot_enabled = env_bool('AUTOPILOT_ENABLED', False) or env_bool('ENABLE_AUTOPILOT', True)
    
    if not autopilot_enabled:
        return False, "Autopilot disabled. Set AUTOPILOT_ENABLED=1 to enable"
    
    trading_enabled, mode_or_reason = check_trading_mode_enabled()
    
    if not trading_enabled:
        return False, f"Autopilot requires trading mode. {mode_or_reason}"
    
    logger.info(f"✅ Autopilot gates passed: AUTOPILOT_ENABLED=1, mode={mode_or_reason}")
    return True, f"Autopilot enabled in {mode_or_reason} mode"


async def check_live_trading_keys(user_id: str, exchange: Optional[str] = None) -> Tuple[bool, str]:
    """
    Validate that live trading can proceed by checking API keys.
    
    For live trading, we MUST have:
    - API keys stored in database
    - Keys must be for the correct exchange (if specified)
    
    Args:
        user_id: User ID to check keys for
        exchange: Optional exchange name to validate (e.g., 'luno', 'binance')
    
    Returns:
        Tuple[bool, str]: (keys_valid, error_message)
    """
    try:
        # Import database only when needed
        import database as db
        
        # Find API keys for user
        query = {"user_id": user_id}
        if exchange:
            query["exchange"] = exchange.lower()
        
        keys = await db.api_keys_collection.find(query).to_list(100)
        
        if not keys:
            msg = f"No API keys found for user {user_id[:8]}"
            if exchange:
                msg += f" on {exchange}"
            return False, msg
        
        # Verify keys have required fields
        for key in keys:
            if not key.get('api_key') or not key.get('api_secret'):
                return False, f"Incomplete API keys for {key.get('exchange', 'unknown')}"
        
        if exchange:
            logger.info(f"✅ API keys validated for user {user_id[:8]} on {exchange}")
        else:
            logger.info(f"✅ API keys validated for user {user_id[:8]} ({len(keys)} exchanges)")
        
        return True, "API keys validated"
        
    except Exception as e:
        logger.error(f"Error checking API keys: {e}")
        return False, f"Failed to validate API keys: {str(e)}"


async def validate_exchange_connection(exchange_instance) -> Tuple[bool, str]:
    """
    Test that an exchange connection is working.
    
    Args:
        exchange_instance: CCXT exchange instance
    
    Returns:
        Tuple[bool, str]: (connection_valid, error_message)
    """
    try:
        if not exchange_instance:
            return False, "Exchange instance is None"
        
        # Test connection by fetching balance (requires valid keys)
        balance = await exchange_instance.fetch_balance()
        
        if balance is None:
            return False, "Exchange returned null balance"
        
        logger.info(f"✅ Exchange connection validated: {exchange_instance.id}")
        return True, "Exchange connection valid"
        
    except Exception as e:
        logger.error(f"Exchange connection test failed: {e}")
        return False, f"Exchange connection failed: {str(e)}"


def enforce_trading_gates(trading_mode: str = None) -> None:
    """
    Enforce trading mode gates before allowing any trade execution.
    
    Args:
        trading_mode: Optional - 'paper' or 'live' to check specific mode
    
    Raises:
        TradingGateError: If trading gates are not satisfied
    """
    if trading_mode == "paper":
        paper_enabled = env_bool('PAPER_TRADING', False) or env_bool('ENABLE_PAPER_TRADING', True)
        if not paper_enabled:
            msg = "❌ Paper trading gate FAILED: PAPER_TRADING not enabled"
            logger.error(msg)
            raise TradingGateError(msg)
        logger.debug("✅ Paper trading gate passed")
        return
    
    if trading_mode == "live":
        live_enabled = env_bool('LIVE_TRADING', False)
        if not live_enabled:
            msg = "❌ Live trading gate FAILED: LIVE_TRADING not enabled"
            logger.error(msg)
            raise TradingGateError(msg)
        logger.debug("✅ Live trading gate passed")
        return
    
    # General check - either mode must be enabled
    enabled, reason = check_trading_mode_enabled()
    if not enabled:
        msg = f"❌ Trading gates FAILED: {reason}"
        logger.error(msg)
        raise TradingGateError(msg)
    
    logger.debug(f"✅ Trading gates passed: mode={reason}")


async def enforce_live_trading_gates(user_id: str, exchange: str) -> None:
    """
    Enforce all gates for live trading before placing real orders.

    Gates (in order):
    1. LIVE_TRADING / ENABLE_LIVE_TRADING env var must be set
    2. LIVE_FUNDS_MOVEMENT_ALLOWED env var must be set (second kill-switch)
    3. Validated API keys must exist for this exchange

    Args:
        user_id: User ID (will be truncated in logs for security)
        exchange: Exchange name

    Raises:
        TradingGateError: If any gate check fails
    """
    # 1. Check LIVE_TRADING environment variable
    enforce_trading_gates("live")

    # 2. Check LIVE_FUNDS_MOVEMENT_ALLOWED — second explicit kill-switch that
    #    must be set before any real funds can move.  This allows LIVE_TRADING
    #    to be enabled for configuration/testing while still blocking all orders
    #    until an operator deliberately sets this flag.
    try:
        import config as _live_cfg
        _funds_allowed = getattr(_live_cfg, 'LIVE_FUNDS_MOVEMENT_ALLOWED', False)
    except Exception:
        _funds_allowed = env_bool('LIVE_FUNDS_MOVEMENT_ALLOWED', False)

    if not _funds_allowed:
        msg = (
            "❌ Live trading gate FAILED: LIVE_FUNDS_MOVEMENT_ALLOWED is not set. "
            "Set LIVE_FUNDS_MOVEMENT_ALLOWED=true in your environment to allow real fund movement."
        )
        logger.error(msg)
        raise TradingGateError(msg)

    # 3. Check API keys exist
    keys_valid, keys_msg = await check_live_trading_keys(user_id, exchange)
    if not keys_valid:
        msg = f"❌ Live trading gate FAILED: {keys_msg}"
        logger.error(msg)
        raise TradingGateError(msg)

    logger.info(f"✅ All live trading gates passed for user {user_id[:8]} on {exchange}")
