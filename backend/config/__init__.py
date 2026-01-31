"""
Config package
Re-exports constants from ../config.py for backward compatibility with imports like:
    from config import PAPER_TRAINING_DAYS
"""

# These constants are duplicated here to avoid circular import issues
# The canonical source is ../config.py
# When backend/config.py is updated, these should be kept in sync

import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # dotenv not available, use environment variables directly

# Paper -> Live promotion criteria (most commonly imported)
PAPER_TRAINING_DAYS = int(os.getenv('PAPER_TRAINING_DAYS', '7'))  # Must be 7 days minimum
MIN_WIN_RATE = 0.52  # 52%
MIN_PROFIT_PERCENT = 0.03  # 3%
MIN_TRADES_FOR_PROMOTION = 25

# Exchange limits
EXCHANGE_BOT_LIMITS = {
    'luno': 5,
    'binance': 10,
    'kucoin': 10,
    'bybit': 10,
    'kraken': 10,
    'bitget': 10,
    'gate': 10
}

EXCHANGE_TRADE_LIMITS = {
    'luno': {
        'max_trades_per_bot_per_day': 75,
        'min_cooldown_minutes': 15,
        'max_api_calls_per_minute': 60
    },
    'binance': {
        'max_trades_per_bot_per_day': 150,
        'min_cooldown_minutes': 10,
        'max_api_calls_per_minute': 1200
    },
    'kucoin': {
        'max_trades_per_bot_per_day': 150,
        'min_cooldown_minutes': 10,
        'max_api_calls_per_minute': 600
    },
    'bybit': {
        'max_trades_per_bot_per_day': 150,
        'min_cooldown_minutes': 10,
        'max_api_calls_per_minute': 600
    },
    'kraken': {
        'max_trades_per_bot_per_day': 100,
        'min_cooldown_minutes': 12,
        'max_api_calls_per_minute': 120
    },
    'bitget': {
        'max_trades_per_bot_per_day': 120,
        'min_cooldown_minutes': 10,
        'max_api_calls_per_minute': 400
    },
    'gate': {
        'max_trades_per_bot_per_day': 130,
        'min_cooldown_minutes': 10,
        'max_api_calls_per_minute': 500
    }
}

# Global limits
MAX_TRADES_PER_USER_PER_DAY = 3000
MIN_TRADE_PROFIT_THRESHOLD_ZAR = 2.0

# Autopilot settings (configurable via env vars)
REINVEST_THRESHOLD_ZAR = int(os.getenv('REINVEST_THRESHOLD_ZAR', '300'))  # Lower threshold
NEW_BOT_CAPITAL = int(os.getenv('NEW_BOT_CAPITAL', '500'))  # Lower capital requirement
MAX_TOTAL_BOTS = int(os.getenv('MAX_TOTAL_BOTS', '65'))  # Total bots across all exchanges
TOP_PERFORMERS_COUNT = int(os.getenv('TOP_PERFORMERS_COUNT', '5'))
EVOLUTION_MUTATION_RATE = float(os.getenv('EVOLUTION_MUTATION_RATE', '0.25'))  # 25% mutation
QUARANTINE_THRESHOLD = float(os.getenv('QUARANTINE_THRESHOLD', '-0.05'))  # -5% threshold

# Risk settings
STOP_LOSS_SAFE = 0.05
STOP_LOSS_BALANCED = 0.10
STOP_LOSS_AGGRESSIVE = 0.15

# Risk Management - Adjusted for production
MAX_HOURLY_LOSS_PERCENT = 0.15
MAX_DAILY_LOSS_PERCENT = float(os.getenv('MAX_DAILY_LOSS_PERCENT', '0.15'))  # 15% daily loss limit
MAX_DRAWDOWN_PERCENT = float(os.getenv('MAX_DRAWDOWN_PERCENT', '0.25'))  # 25% drawdown limit
MIN_POSITION_SIZE_PERCENT = 0.02  # 2% minimum per-trade
MAX_POSITION_SIZE_PERCENT = 0.05  # 5% maximum per-trade

# Self-healing configuration
MAX_ERRORS_PER_HOUR = int(os.getenv('MAX_ERRORS_PER_HOUR', '20'))  # Error budget

# AI Models
AI_MODELS = {
    'system_brain': 'gpt-5.1',
    'trade_decision': 'gpt-4o',
    'reporting': 'gpt-4',
    'chatops': 'gpt-4o'
}

# Feature flags
ENABLE_TRADING = os.getenv('ENABLE_TRADING', 'true').lower() == 'true'  # Enable for paper trading
ENABLE_PAPER_TRADING = os.getenv('ENABLE_PAPER_TRADING', 'true').lower() == 'true'  # Paper trading safe
ENABLE_LIVE_TRADING = os.getenv('ENABLE_LIVE_TRADING', 'false').lower() == 'true'  # Live OFF by default
ENABLE_AUTOPILOT = os.getenv('ENABLE_AUTOPILOT', 'true').lower() == 'true'  # Autonomous management
ENABLE_BODYGUARD = os.getenv('ENABLE_BODYGUARD', 'true').lower() == 'true'  # AI protection
ENABLE_REALTIME = os.getenv('ENABLE_REALTIME', 'true').lower() == 'true'  # SSE/WS events
ENABLE_SELF_LEARNING = os.getenv('ENABLE_SELF_LEARNING', 'true').lower() == 'true'
ENABLE_SELF_HEALING = os.getenv('ENABLE_SELF_HEALING', 'true').lower() == 'true'
ENABLE_CCXT = os.getenv('ENABLE_CCXT', 'true').lower() == 'true'
ENABLE_UAGENTS = os.getenv('ENABLE_UAGENTS', 'false').lower() == 'true'
PAYMENT_AGENT_ENABLED = os.getenv('PAYMENT_AGENT_ENABLED', 'false').lower() == 'true'
ENABLE_REALTIME_TRANSFERS = os.getenv('ENABLE_REALTIME_TRANSFERS', 'false').lower() == 'true'  # Real-time wallet transfers
ENABLE_SCHEDULERS = os.getenv('ENABLE_SCHEDULERS', 'true').lower() == 'true'  # Background jobs

# Live Trading Gate Requirements
REQUIRE_WALLET_FUNDED = os.getenv('REQUIRE_WALLET_FUNDED', 'true').lower() == 'true'
REQUIRE_API_KEYS_FOR_LIVE = os.getenv('REQUIRE_API_KEYS_FOR_LIVE', 'true').lower() == 'true'

# Supported Exchanges for Paper Trading
PAPER_SUPPORTED_EXCHANGES = {'luno', 'binance', 'kucoin'}

__all__ = [
    'PAPER_TRAINING_DAYS', 'MIN_WIN_RATE', 'MIN_PROFIT_PERCENT', 'MIN_TRADES_FOR_PROMOTION',
    'EXCHANGE_BOT_LIMITS', 'EXCHANGE_TRADE_LIMITS',
    'MAX_TRADES_PER_USER_PER_DAY', 'MIN_TRADE_PROFIT_THRESHOLD_ZAR',
    'REINVEST_THRESHOLD_ZAR', 'NEW_BOT_CAPITAL', 'MAX_TOTAL_BOTS', 'TOP_PERFORMERS_COUNT',
    'EVOLUTION_MUTATION_RATE', 'QUARANTINE_THRESHOLD',
    'AI_MODELS',
    'STOP_LOSS_SAFE', 'STOP_LOSS_BALANCED', 'STOP_LOSS_AGGRESSIVE',
    'MAX_HOURLY_LOSS_PERCENT', 'MAX_DAILY_LOSS_PERCENT', 'MAX_DRAWDOWN_PERCENT',
    'MIN_POSITION_SIZE_PERCENT', 'MAX_POSITION_SIZE_PERCENT', 'MAX_ERRORS_PER_HOUR',
    'ENABLE_TRADING', 'ENABLE_PAPER_TRADING', 'ENABLE_LIVE_TRADING', 'ENABLE_AUTOPILOT',
    'ENABLE_BODYGUARD', 'ENABLE_REALTIME', 'ENABLE_REALTIME_TRANSFERS', 'ENABLE_SCHEDULERS',
    'ENABLE_SELF_LEARNING', 'ENABLE_SELF_HEALING',
    'ENABLE_CCXT', 'ENABLE_UAGENTS', 'PAYMENT_AGENT_ENABLED',
    'REQUIRE_WALLET_FUNDED', 'REQUIRE_API_KEYS_FOR_LIVE', 'PAPER_SUPPORTED_EXCHANGES'
]
