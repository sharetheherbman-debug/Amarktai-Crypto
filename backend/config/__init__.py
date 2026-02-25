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

# Email (SMTP) – must mirror backend/config.py
SMTP_HOST = os.getenv('SMTP_HOST', 'smtp.gmail.com')
SMTP_PORT = int(os.getenv('SMTP_PORT', '587'))
SMTP_USER = os.getenv('SMTP_USER', '')
SMTP_PASSWORD = os.getenv('SMTP_PASSWORD', '')
FROM_EMAIL = os.getenv('FROM_EMAIL', SMTP_USER)
FROM_NAME = os.getenv('FROM_NAME', 'Amarktai Network')
EMAIL_CONFIRMATION_TIMEOUT_HOURS = int(os.getenv('EMAIL_CONFIRMATION_TIMEOUT_HOURS', '24'))
REQUIRE_EMAIL_CONFIRMATION = os.getenv('REQUIRE_EMAIL_CONFIRMATION', 'true').lower() == 'true'

# Paper -> Live promotion criteria (most commonly imported)
PAPER_TRAINING_DAYS = int(os.getenv('PAPER_TRAINING_DAYS', '7'))  # Must be 7 days minimum
PAPER_STARTING_CAPITAL_ZAR = float(os.getenv('PAPER_STARTING_CAPITAL_ZAR', '30000'))  # Default paper starting capital
MIN_WIN_RATE = 0.52  # 52%
MIN_PROFIT_PERCENT = 0.03  # 3%
MIN_TRADES_FOR_PROMOTION = 25

# Exchange limits (7 canonical exchanges)
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
        'max_trades_per_bot_per_day': int(os.getenv('MAX_TRADES_PER_BOT_DAILY_LUNO', '999999')),
        'min_cooldown_minutes': 15,
        'max_api_calls_per_minute': 60
    },
    'binance': {
        'max_trades_per_bot_per_day': int(os.getenv('MAX_TRADES_PER_BOT_DAILY_BINANCE', '999999')),
        'min_cooldown_minutes': 10,
        'max_api_calls_per_minute': 1200
    },
    'kucoin': {
        'max_trades_per_bot_per_day': int(os.getenv('MAX_TRADES_PER_BOT_DAILY_KUCOIN', '999999')),
        'min_cooldown_minutes': 10,
        'max_api_calls_per_minute': 600
    },
    'bybit': {
        'max_trades_per_bot_per_day': int(os.getenv('MAX_TRADES_PER_BOT_DAILY_BYBIT', '999999')),
        'min_cooldown_minutes': 10,
        'max_api_calls_per_minute': 600
    },
    'kraken': {
        'max_trades_per_bot_per_day': int(os.getenv('MAX_TRADES_PER_BOT_DAILY_KRAKEN', '999999')),
        'min_cooldown_minutes': 10,
        'max_api_calls_per_minute': 500
    },
    'bitget': {
        'max_trades_per_bot_per_day': int(os.getenv('MAX_TRADES_PER_BOT_DAILY_BITGET', '999999')),
        'min_cooldown_minutes': 10,
        'max_api_calls_per_minute': 400
    },
    'gate': {
        'max_trades_per_bot_per_day': int(os.getenv('MAX_TRADES_PER_BOT_DAILY_GATE', '999999')),
        'min_cooldown_minutes': 10,
        'max_api_calls_per_minute': 400
    }
}

# Global limits — no artificial per-bot/user daily cap. Risk locks (Bodyguard, daily loss) remain.
MAX_TRADES_PER_BOT_PER_DAY = int(os.getenv('MAX_TRADES_PER_BOT_PER_DAY', '999999'))
MAX_TRADES_PER_USER_PER_DAY = int(os.getenv('MAX_TRADES_PER_USER_PER_DAY', '999999'))
MIN_TRADE_PROFIT_THRESHOLD_ZAR = 2.0

# Paper trading anti-churn protections
EDGE_BUFFER_PCT = float(os.getenv('EDGE_BUFFER_PCT', '0.15'))  # 0.15% buffer
EDGE_GATE_PAPER = os.getenv('EDGE_GATE_PAPER', 'true').lower() == 'true'
EDGE_GATE_LIVE = os.getenv('EDGE_GATE_LIVE', 'false').lower() == 'true'
PAPER_MAX_SPREAD_PCT = float(os.getenv('PAPER_MAX_SPREAD_PCT', '0.35'))  # 0.35% max spread
PAPER_MIN_ORDERBOOK_NOTIONAL = float(os.getenv('PAPER_MIN_ORDERBOOK_NOTIONAL', '50000'))  # ZAR/USDT
PAPER_PAIR_WHITELIST_ENABLED = os.getenv('PAPER_PAIR_WHITELIST_ENABLED', 'true').lower() == 'true'
PAPER_STALE_EXIT_MINUTES = int(os.getenv('PAPER_STALE_EXIT_MINUTES', '120'))
# Time-exit fires unconditionally at this age regardless of P&L.
# Ensures profitable trades still close for overnight win/loss accounting.
PAPER_MAX_HOLD_MINUTES = int(os.getenv('PAPER_MAX_HOLD_MINUTES', '120'))

# Default paper trading pair whitelist (can be overridden per bot)
PAPER_PAIR_WHITELIST = {
    "luno": ["BTC/ZAR", "ETH/ZAR", "XRP/ZAR"],
    "binance": ["BTC/USDT", "ETH/USDT", "XRP/USDT"],
    "kucoin": ["BTC/USDT", "ETH/USDT", "XRP/USDT"],
    "bybit": ["BTC/USDT", "ETH/USDT", "XRP/USDT"],
    "kraken": ["BTC/USDT", "ETH/USDT", "XRP/USDT"],
    "bitget": ["BTC/USDT", "ETH/USDT", "XRP/USDT"],
    "gate": ["BTC/USDT", "ETH/USDT", "XRP/USDT"]
}
EXCHANGE_DAILY_TRADE_LIMITS = {
    'luno': int(os.getenv('LUNO_MAX_TRADES_PER_DAY', '20000')),
    'binance': int(os.getenv('BINANCE_MAX_TRADES_PER_DAY', '50000')),
    'kucoin': int(os.getenv('KUCOIN_MAX_TRADES_PER_DAY', '100000')),
    'bybit': int(os.getenv('BYBIT_MAX_TRADES_PER_DAY', '100000')),
    'kraken': int(os.getenv('KRAKEN_MAX_TRADES_PER_DAY', '50000')),
    'bitget': int(os.getenv('BITGET_MAX_TRADES_PER_DAY', '80000')),
    'gate': int(os.getenv('GATEIO_MAX_TRADES_PER_DAY', '80000'))
}

# Autopilot settings (configurable via env vars)
# Bot Spawning Logic - SEPARATED THRESHOLDS for clarity
BOT_SPAWN_PROFIT_THRESHOLD_ZAR = int(os.getenv('BOT_SPAWN_PROFIT_THRESHOLD_ZAR', '1000'))  # Spawn new bot when profit reaches this
AUTO_SPAWN_COOLDOWN_MINUTES = int(os.getenv('AUTO_SPAWN_COOLDOWN_MINUTES', '60'))
AUTO_SPAWN_MAX_PER_DAY = int(os.getenv('AUTO_SPAWN_MAX_PER_DAY', '2'))
NEW_BOT_SEED_CAPITAL_ZAR = int(os.getenv('NEW_BOT_SEED_CAPITAL_ZAR', '500'))  # Capital to give new bot
REINVEST_THRESHOLD_ZAR = int(os.getenv('REINVEST_THRESHOLD_ZAR', '300'))  # Lower threshold
NEW_BOT_CAPITAL = NEW_BOT_SEED_CAPITAL_ZAR  # Backward compatibility alias
MAX_TOTAL_BOTS = int(os.getenv('MAX_TOTAL_BOTS', '65'))  # Total bots across all 7 exchanges
TOP_PERFORMERS_COUNT = int(os.getenv('TOP_PERFORMERS_COUNT', '5'))
EVOLUTION_MUTATION_RATE = float(os.getenv('EVOLUTION_MUTATION_RATE', '0.25'))  # 25% mutation
QUARANTINE_THRESHOLD = float(os.getenv('QUARANTINE_THRESHOLD', '-0.05'))  # -5% threshold

# Autopilot growth + reinvest controls
ENABLE_AUTOPILOT_GROWTH = os.getenv('ENABLE_AUTOPILOT_GROWTH', 'false').lower() == 'true'
ENABLE_AUTOPILOT_REINVEST = os.getenv('ENABLE_AUTOPILOT_REINVEST', 'false').lower() == 'true'
AUTOPILOT_PROFIT_MILESTONE_ZAR = float(os.getenv('AUTOPILOT_PROFIT_MILESTONE_ZAR', '1000'))
AUTOPILOT_REINVEST_MIN_ZAR = float(os.getenv('AUTOPILOT_REINVEST_MIN_ZAR', '100'))
AUTOPILOT_MAX_BOTS_PER_PLATFORM = int(os.getenv('AUTOPILOT_MAX_BOTS_PER_PLATFORM', '0'))

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
AUTO_PROMOTE_LIVE = os.getenv('AUTO_PROMOTE_LIVE', 'false').lower() == 'true'  # Auto-promote eligible bots from paper to live daily

# Supported Exchanges for Paper Trading
# Import from canonical source: backend/config/platforms.py
from config.platforms import SUPPORTED_PLATFORMS
PAPER_SUPPORTED_EXCHANGES = set(SUPPORTED_PLATFORMS)  # All 7 exchanges supported

__all__ = [
    'SMTP_HOST', 'SMTP_PORT', 'SMTP_USER', 'SMTP_PASSWORD', 'FROM_EMAIL', 'FROM_NAME',
    'EMAIL_CONFIRMATION_TIMEOUT_HOURS', 'REQUIRE_EMAIL_CONFIRMATION',
    'PAPER_TRAINING_DAYS', 'PAPER_STARTING_CAPITAL_ZAR', 'MIN_WIN_RATE', 'MIN_PROFIT_PERCENT', 'MIN_TRADES_FOR_PROMOTION',
    'EXCHANGE_BOT_LIMITS', 'EXCHANGE_TRADE_LIMITS',
    'MAX_TRADES_PER_BOT_PER_DAY', 'MAX_TRADES_PER_USER_PER_DAY', 'MIN_TRADE_PROFIT_THRESHOLD_ZAR',
    'EDGE_BUFFER_PCT', 'EDGE_GATE_PAPER', 'EDGE_GATE_LIVE', 'PAPER_MAX_SPREAD_PCT',
    'PAPER_MIN_ORDERBOOK_NOTIONAL', 'PAPER_PAIR_WHITELIST', 'PAPER_PAIR_WHITELIST_ENABLED',
    'PAPER_STALE_EXIT_MINUTES',
    'PAPER_MAX_HOLD_MINUTES',
    'EXCHANGE_DAILY_TRADE_LIMITS',
    'BOT_SPAWN_PROFIT_THRESHOLD_ZAR', 'AUTO_SPAWN_COOLDOWN_MINUTES', 'AUTO_SPAWN_MAX_PER_DAY',
    'NEW_BOT_SEED_CAPITAL_ZAR', 'REINVEST_THRESHOLD_ZAR',
    'NEW_BOT_CAPITAL', 'MAX_TOTAL_BOTS', 'TOP_PERFORMERS_COUNT',
    'EVOLUTION_MUTATION_RATE', 'QUARANTINE_THRESHOLD',
    'AI_MODELS',
    'STOP_LOSS_SAFE', 'STOP_LOSS_BALANCED', 'STOP_LOSS_AGGRESSIVE',
    'MAX_HOURLY_LOSS_PERCENT', 'MAX_DAILY_LOSS_PERCENT', 'MAX_DRAWDOWN_PERCENT',
    'MIN_POSITION_SIZE_PERCENT', 'MAX_POSITION_SIZE_PERCENT', 'MAX_ERRORS_PER_HOUR',
    'ENABLE_TRADING', 'ENABLE_PAPER_TRADING', 'ENABLE_LIVE_TRADING', 'ENABLE_AUTOPILOT',
    'ENABLE_BODYGUARD', 'ENABLE_REALTIME', 'ENABLE_REALTIME_TRANSFERS', 'ENABLE_SCHEDULERS',
    'ENABLE_SELF_LEARNING', 'ENABLE_SELF_HEALING',
    'ENABLE_CCXT', 'ENABLE_UAGENTS', 'PAYMENT_AGENT_ENABLED',
    'ENABLE_AUTOPILOT_GROWTH', 'ENABLE_AUTOPILOT_REINVEST',
    'AUTOPILOT_PROFIT_MILESTONE_ZAR', 'AUTOPILOT_REINVEST_MIN_ZAR',
    'AUTOPILOT_MAX_BOTS_PER_PLATFORM',
    'REQUIRE_WALLET_FUNDED', 'REQUIRE_API_KEYS_FOR_LIVE', 'AUTO_PROMOTE_LIVE', 'PAPER_SUPPORTED_EXCHANGES'
]
