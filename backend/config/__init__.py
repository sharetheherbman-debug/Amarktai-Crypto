"""
Config package
Re-exports constants from ../config.py for backward compatibility with imports like:
    from config import PAPER_TRAINING_DAYS

CANONICAL ENV VARIABLE NAMES (Pass 1 Go-Live Recovery):
  Trading gates:  PAPER_TRADING (1/0), LIVE_TRADING (1/0), AUTOPILOT_ENABLED (1/0)
  Legacy aliases: ENABLE_PAPER_TRADING, ENABLE_LIVE_TRADING, ENABLE_AUTOPILOT
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

# ---------------------------------------------------------------------------
# Helper — import from canonical source utils/env_utils.py
# ---------------------------------------------------------------------------
try:
    from utils.env_utils import env_bool as _env_bool
except ImportError:
    # Fallback if utils not importable (e.g. standalone config import)
    def _env_bool(name: str, default: bool = False) -> bool:
        value = os.getenv(name)
        if value is None:
            return default
        return value.strip().lower() in {'1', 'true', 'yes', 'y', 'on'}

# ---------------------------------------------------------------------------
# CANONICAL trading-gate variables  (1 / 0 style via _env_bool)
# ---------------------------------------------------------------------------
PAPER_TRADING = _env_bool('PAPER_TRADING', False) or _env_bool('ENABLE_PAPER_TRADING', False)
LIVE_TRADING = _env_bool('LIVE_TRADING', False) or _env_bool('ENABLE_LIVE_TRADING', False)
# AUTOPILOT_ENABLED defaults to True so that users who enable autopilot in the UI
# are not silently blocked by a missing env var.
# Explicit override: set AUTOPILOT_ENABLED=0 or AUTOPILOT_ENABLED=false to disable globally.
# Precedence: AUTOPILOT_ENABLED (canonical) → ENABLE_AUTOPILOT (legacy) → default True
_autopilot_env = os.getenv('AUTOPILOT_ENABLED')
_autopilot_legacy = os.getenv('ENABLE_AUTOPILOT')
if _autopilot_env is not None:
    AUTOPILOT_ENABLED = _autopilot_env.strip().lower() in {'1', 'true', 'yes', 'y', 'on'}
elif _autopilot_legacy is not None:
    AUTOPILOT_ENABLED = _autopilot_legacy.strip().lower() in {'1', 'true', 'yes', 'y', 'on'}
else:
    AUTOPILOT_ENABLED = True  # Default: enabled when not explicitly set

# Backward-compatible aliases
ENABLE_PAPER_TRADING = PAPER_TRADING
ENABLE_LIVE_TRADING = LIVE_TRADING
ENABLE_AUTOPILOT = AUTOPILOT_ENABLED

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
        'max_trades_per_bot_per_day': 120,
        'min_cooldown_minutes': 10,
        'max_api_calls_per_minute': 500
    },
    'bitget': {
        'max_trades_per_bot_per_day': 120,
        'min_cooldown_minutes': 10,
        'max_api_calls_per_minute': 400
    },
    'gate': {
        'max_trades_per_bot_per_day': 120,
        'min_cooldown_minutes': 10,
        'max_api_calls_per_minute': 400
    }
}

# Global limits
MAX_TRADES_PER_BOT_PER_DAY = int(os.getenv('MAX_TRADES_PER_BOT_PER_DAY', '1000'))  # Per-bot daily trade cap
MAX_TRADES_PER_USER_PER_DAY = 3000
MIN_TRADE_PROFIT_THRESHOLD_ZAR = 2.0

# Paper trading anti-churn protections
EDGE_BUFFER_PCT = float(os.getenv('EDGE_BUFFER_PCT', '0.15'))  # 0.15% buffer
EDGE_GATE_PAPER = os.getenv('EDGE_GATE_PAPER', 'true').lower() == 'true'
EDGE_GATE_LIVE = os.getenv('EDGE_GATE_LIVE', 'false').lower() == 'true'
PAPER_MAX_SPREAD_PCT = float(os.getenv('PAPER_MAX_SPREAD_PCT', '0.35'))  # 0.35% max spread
PAPER_MIN_ORDERBOOK_NOTIONAL = float(os.getenv('PAPER_MIN_ORDERBOOK_NOTIONAL', '50000'))  # ZAR/USDT
PAPER_PAIR_WHITELIST_ENABLED = os.getenv('PAPER_PAIR_WHITELIST_ENABLED', 'true').lower() == 'true'
PAPER_STALE_EXIT_MINUTES = int(os.getenv('PAPER_STALE_EXIT_MINUTES', '120'))

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
NEW_BOT_SEED_CAPITAL_ZAR = int(os.getenv('NEW_BOT_SEED_CAPITAL_ZAR', '500'))  # Capital to give new bot
REINVEST_THRESHOLD_ZAR = int(os.getenv('REINVEST_THRESHOLD_ZAR', '300'))  # Lower threshold
NEW_BOT_CAPITAL = NEW_BOT_SEED_CAPITAL_ZAR  # Backward compatibility alias
MAX_TOTAL_BOTS = int(os.getenv('MAX_TOTAL_BOTS', '65'))  # Total bots across all 7 exchanges
TOP_PERFORMERS_COUNT = int(os.getenv('TOP_PERFORMERS_COUNT', '5'))
EVOLUTION_MUTATION_RATE = float(os.getenv('EVOLUTION_MUTATION_RATE', '0.25'))  # 25% mutation
QUARANTINE_THRESHOLD = float(os.getenv('QUARANTINE_THRESHOLD', '-0.05'))  # -5% threshold

# Autopilot growth + reinvest controls
# Default: enabled — can be disabled via env var ENABLE_AUTOPILOT_GROWTH=false
ENABLE_AUTOPILOT_GROWTH = os.getenv('ENABLE_AUTOPILOT_GROWTH', 'true').lower() == 'true'
ENABLE_AUTOPILOT_REINVEST = os.getenv('ENABLE_AUTOPILOT_REINVEST', 'true').lower() == 'true'
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

# Feature flags — ENABLE_PAPER_TRADING, ENABLE_LIVE_TRADING, ENABLE_AUTOPILOT
# already resolved above as canonical aliases.
ENABLE_TRADING = os.getenv('ENABLE_TRADING', 'true').lower() == 'true'  # Enable for paper trading
ENABLE_BODYGUARD = os.getenv('ENABLE_BODYGUARD', 'true').lower() == 'true'  # AI protection
ENABLE_REALTIME = os.getenv('ENABLE_REALTIME', 'true').lower() == 'true'  # SSE/WS events
ENABLE_SELF_LEARNING = os.getenv('ENABLE_SELF_LEARNING', 'true').lower() == 'true'
ENABLE_SELF_HEALING = os.getenv('ENABLE_SELF_HEALING', 'true').lower() == 'true'
ENABLE_CCXT = os.getenv('ENABLE_CCXT', 'true').lower() == 'true'
ENABLE_UAGENTS = os.getenv('ENABLE_UAGENTS', 'false').lower() == 'true'
PAYMENT_AGENT_ENABLED = os.getenv('PAYMENT_AGENT_ENABLED', 'false').lower() == 'true'
ENABLE_REALTIME_TRANSFERS = os.getenv('ENABLE_REALTIME_TRANSFERS', 'false').lower() == 'true'  # Real-time wallet transfers
ENABLE_SCHEDULERS = os.getenv('ENABLE_SCHEDULERS', 'true').lower() == 'true'  # Background jobs

# Trading Brain V2 – economics-first engine redesign
NEW_TRADING_BRAIN_V2 = os.getenv('NEW_TRADING_BRAIN_V2', 'false').lower() == 'true'

# Live Trading Gate Requirements
REQUIRE_WALLET_FUNDED = os.getenv('REQUIRE_WALLET_FUNDED', 'true').lower() == 'true'
REQUIRE_API_KEYS_FOR_LIVE = os.getenv('REQUIRE_API_KEYS_FOR_LIVE', 'true').lower() == 'true'

# Supported Exchanges for Paper Trading
# Import from canonical source: backend/config/platforms.py
from config.platforms import SUPPORTED_PLATFORMS
PAPER_SUPPORTED_EXCHANGES = set(SUPPORTED_PLATFORMS)  # All 7 exchanges supported

__all__ = [
    'PAPER_TRAINING_DAYS', 'PAPER_STARTING_CAPITAL_ZAR', 'MIN_WIN_RATE', 'MIN_PROFIT_PERCENT', 'MIN_TRADES_FOR_PROMOTION',
    'EXCHANGE_BOT_LIMITS', 'EXCHANGE_TRADE_LIMITS',
    'MAX_TRADES_PER_BOT_PER_DAY', 'MAX_TRADES_PER_USER_PER_DAY', 'MIN_TRADE_PROFIT_THRESHOLD_ZAR',
    'EDGE_BUFFER_PCT', 'EDGE_GATE_PAPER', 'EDGE_GATE_LIVE', 'PAPER_MAX_SPREAD_PCT',
    'PAPER_MIN_ORDERBOOK_NOTIONAL', 'PAPER_PAIR_WHITELIST', 'PAPER_PAIR_WHITELIST_ENABLED',
    'PAPER_STALE_EXIT_MINUTES',
    'EXCHANGE_DAILY_TRADE_LIMITS',
    'BOT_SPAWN_PROFIT_THRESHOLD_ZAR', 'NEW_BOT_SEED_CAPITAL_ZAR', 'REINVEST_THRESHOLD_ZAR',
    'NEW_BOT_CAPITAL', 'MAX_TOTAL_BOTS', 'TOP_PERFORMERS_COUNT',
    'EVOLUTION_MUTATION_RATE', 'QUARANTINE_THRESHOLD',
    'AI_MODELS',
    'STOP_LOSS_SAFE', 'STOP_LOSS_BALANCED', 'STOP_LOSS_AGGRESSIVE',
    'MAX_HOURLY_LOSS_PERCENT', 'MAX_DAILY_LOSS_PERCENT', 'MAX_DRAWDOWN_PERCENT',
    'MIN_POSITION_SIZE_PERCENT', 'MAX_POSITION_SIZE_PERCENT', 'MAX_ERRORS_PER_HOUR',
    # Canonical trading gate names
    'PAPER_TRADING', 'LIVE_TRADING', 'AUTOPILOT_ENABLED',
    # Legacy aliases (resolve to same values)
    'ENABLE_TRADING', 'ENABLE_PAPER_TRADING', 'ENABLE_LIVE_TRADING', 'ENABLE_AUTOPILOT',
    'ENABLE_BODYGUARD', 'ENABLE_REALTIME', 'ENABLE_REALTIME_TRANSFERS', 'ENABLE_SCHEDULERS',
    'ENABLE_SELF_LEARNING', 'ENABLE_SELF_HEALING',
    'ENABLE_CCXT', 'ENABLE_UAGENTS', 'PAYMENT_AGENT_ENABLED',
    'ENABLE_AUTOPILOT_GROWTH', 'ENABLE_AUTOPILOT_REINVEST',
    'AUTOPILOT_PROFIT_MILESTONE_ZAR', 'AUTOPILOT_REINVEST_MIN_ZAR',
    'AUTOPILOT_MAX_BOTS_PER_PLATFORM',
    'REQUIRE_WALLET_FUNDED', 'REQUIRE_API_KEYS_FOR_LIVE', 'PAPER_SUPPORTED_EXCHANGES',
    'NEW_TRADING_BRAIN_V2',
]
