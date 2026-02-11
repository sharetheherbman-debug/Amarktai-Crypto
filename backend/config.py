"""
Production Configuration
All system limits and settings
Reads from environment variables
"""
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# ============================================================================
# ENVIRONMENT VARIABLES (from .env)
# ============================================================================

# Database
MONGO_URL = os.getenv('MONGO_URL', 'mongodb://localhost:27017')
DB_NAME = os.getenv('DB_NAME', 'amarktai_trading')

# Security
JWT_SECRET = os.getenv('JWT_SECRET', 'your-secret-key-change-in-production')
# Encryption key priority: AMARKTAI_FERNET_KEY > FERNET_KEY > ENCRYPTION_KEY
AMARKTAI_FERNET_KEY = os.getenv('AMARKTAI_FERNET_KEY', '')
FERNET_KEY = os.getenv('FERNET_KEY', '')
ENCRYPTION_KEY = os.getenv('ENCRYPTION_KEY', '')  # Required for encrypting API keys
# Use first available key
ACTIVE_ENCRYPTION_KEY = AMARKTAI_FERNET_KEY or FERNET_KEY or ENCRYPTION_KEY

# AI / OpenAI
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY', '')

# Email (SMTP)
SMTP_HOST = os.getenv('SMTP_HOST', 'smtp.gmail.com')
SMTP_PORT = int(os.getenv('SMTP_PORT', '587'))
SMTP_USER = os.getenv('SMTP_USER', '')
SMTP_PASSWORD = os.getenv('SMTP_PASSWORD', '')
FROM_EMAIL = os.getenv('FROM_EMAIL', SMTP_USER)
FROM_NAME = os.getenv('FROM_NAME', 'Amarktai Network')

# Optional Integrations
FETCHAI_API_KEY = os.getenv('FETCHAI_API_KEY', '')
FLOKX_API_KEY = os.getenv('FLOKX_API_KEY', '')

# ============================================================================
# FEATURE FLAGS (Safe defaults for production)
# ============================================================================

# Trading Feature Flags
ENABLE_TRADING = os.getenv('ENABLE_TRADING', 'true').lower() == 'true'  # Enable for paper trading
ENABLE_PAPER_TRADING = os.getenv('ENABLE_PAPER_TRADING', 'true').lower() == 'true'  # Paper trading safe by default
ENABLE_LIVE_TRADING = os.getenv('ENABLE_LIVE_TRADING', 'false').lower() == 'true'  # Live trading OFF by default
ENABLE_AUTOPILOT = os.getenv('ENABLE_AUTOPILOT', 'true').lower() == 'true'  # Autopilot for bot management
ENABLE_BODYGUARD = os.getenv('ENABLE_BODYGUARD', 'true').lower() == 'true'  # AI Bodyguard protection
ENABLE_REALTIME = os.getenv('ENABLE_REALTIME', 'true').lower() == 'true'  # SSE/WS realtime events
ENABLE_SELF_LEARNING = os.getenv('ENABLE_SELF_LEARNING', 'true').lower() == 'true'
ENABLE_SELF_HEALING = os.getenv('ENABLE_SELF_HEALING', 'true').lower() == 'true'
ENABLE_CCXT = os.getenv('ENABLE_CCXT', 'true').lower() == 'true'  # Safe for price data
ENABLE_UAGENTS = os.getenv('ENABLE_UAGENTS', 'false').lower() == 'true'
PAYMENT_AGENT_ENABLED = os.getenv('PAYMENT_AGENT_ENABLED', 'false').lower() == 'true'
ENABLE_REALTIME_TRANSFERS = os.getenv('ENABLE_REALTIME_TRANSFERS', 'false').lower() == 'true'  # Real-time wallet transfers
ENABLE_SCHEDULERS = os.getenv('ENABLE_SCHEDULERS', 'true').lower() == 'true'  # Background jobs

# Live Trading Gate Requirements
# NOTE: PAPER_TRAINING_DAYS is defined below in "Paper → Live promotion criteria" section (line ~117)
REQUIRE_WALLET_FUNDED = os.getenv('REQUIRE_WALLET_FUNDED', 'true').lower() == 'true'  # Must have funded wallet
REQUIRE_API_KEYS_FOR_LIVE = os.getenv('REQUIRE_API_KEYS_FOR_LIVE', 'true').lower() == 'true'  # Must have exchange API keys

# Supported Exchanges for Paper Trading (PRODUCTION)
# Import from canonical source: backend/config/platforms.py
from config.platforms import SUPPORTED_PLATFORMS
PAPER_SUPPORTED_EXCHANGES = set(SUPPORTED_PLATFORMS)  # All 7 exchanges supported for paper trading

# Safe mode: All trading disabled by default
# Enable gradually:
# 1. ENABLE_CCXT=true (price data only)
# 2. ENABLE_PAPER_TRADING=true (paper trading with simulated trades)
# 3. ENABLE_TRADING=true + ENABLE_AUTOPILOT=true for autonomous management
# 4. Configure API keys and enable live trading with ENABLE_LIVE_TRADING=true

# ============================================================================
# SYSTEM CONFIGURATION
# ============================================================================

# Exchange bot limits (researched and safe)
EXCHANGE_BOT_LIMITS = {
    'luno': 5,
    'binance': 10,
    'kucoin': 10,
    'bybit': 10,
    'kraken': 10,
    'bitget': 10,
    'gate': 10
}

# Trading limits - Per exchange (Safety caps per upgrade guide)
# NOTE: These are SAFETY CAPS to protect exchanges and user accounts.
# ACTUAL ENFORCED LIMITS are in exchange_limits.py (50 per bot per day).
# The rate_limiter.py uses exchange_limits.py as the authoritative source.
EXCHANGE_TRADE_LIMITS = {
    'luno': {
        'max_trades_per_bot_per_day': 50,  # Enforced by exchange_limits.py
        'max_trades_per_exchange_per_day': 400,  # Safety cap per upgrade guide
        'min_cooldown_minutes': 15,
        'max_api_calls_per_minute': 60
    },
    'binance': {
        'max_trades_per_bot_per_day': 50,  # Enforced by exchange_limits.py
        'max_trades_per_exchange_per_day': 500,  # Safety cap per upgrade guide
        'min_cooldown_minutes': 10,
        'max_api_calls_per_minute': 1200
    },
    'kucoin': {
        'max_trades_per_bot_per_day': 50,  # Enforced by exchange_limits.py
        'max_trades_per_exchange_per_day': 1000,  # Safety cap per upgrade guide
        'min_cooldown_minutes': 10,
        'max_api_calls_per_minute': 600
    },
    'bybit': {
        'max_trades_per_bot_per_day': 50,  # Enforced by exchange_limits.py
        'max_trades_per_exchange_per_day': 1000,  # Safety cap per upgrade guide
        'min_cooldown_minutes': 10,
        'max_api_calls_per_minute': 600
    },
    'bitget': {
        'max_trades_per_bot_per_day': 50,  # Enforced by exchange_limits.py
        'max_trades_per_exchange_per_day': 800,  # Safety cap per upgrade guide
        'min_cooldown_minutes': 10,
        'max_api_calls_per_minute': 400
    }
}

# Global limits
MAX_TRADES_PER_BOT_PER_DAY = int(os.getenv('MAX_TRADES_PER_BOT_PER_DAY', '1000'))  # Per-bot daily trade cap
MAX_TRADES_PER_USER_PER_DAY = int(os.getenv('MAX_TRADES_PER_USER_PER_DAY', '3000'))  # Total across all bots
MIN_TRADE_PROFIT_THRESHOLD_ZAR = 2.0  # Minimum net profit target (ignore 30c wins)

# Per-exchange trade limits (optional overrides)
LUNO_MAX_TRADES_PER_DAY = int(os.getenv('LUNO_MAX_TRADES_PER_DAY', '20000'))
BINANCE_MAX_TRADES_PER_DAY = int(os.getenv('BINANCE_MAX_TRADES_PER_DAY', '50000'))
KUCOIN_MAX_TRADES_PER_DAY = int(os.getenv('KUCOIN_MAX_TRADES_PER_DAY', '100000'))
BYBIT_MAX_TRADES_PER_DAY = int(os.getenv('BYBIT_MAX_TRADES_PER_DAY', '100000'))
KRAKEN_MAX_TRADES_PER_DAY = int(os.getenv('KRAKEN_MAX_TRADES_PER_DAY', '50000'))
BITGET_MAX_TRADES_PER_DAY = int(os.getenv('BITGET_MAX_TRADES_PER_DAY', '80000'))
GATEIO_MAX_TRADES_PER_DAY = int(os.getenv('GATEIO_MAX_TRADES_PER_DAY', '80000'))

# Map exchange names to their trade limits
EXCHANGE_DAILY_TRADE_LIMITS = {
    'luno': LUNO_MAX_TRADES_PER_DAY,
    'binance': BINANCE_MAX_TRADES_PER_DAY,
    'kucoin': KUCOIN_MAX_TRADES_PER_DAY,
    'bybit': BYBIT_MAX_TRADES_PER_DAY,
    'kraken': KRAKEN_MAX_TRADES_PER_DAY,
    'bitget': BITGET_MAX_TRADES_PER_DAY,
    'gateio': GATEIO_MAX_TRADES_PER_DAY,
    'gate': GATEIO_MAX_TRADES_PER_DAY,  # Alias
}

# Paper → Live promotion criteria
PAPER_TRAINING_DAYS = int(os.getenv('PAPER_TRAINING_DAYS', '7'))  # Must be 7 days minimum
PAPER_STARTING_CAPITAL_ZAR = float(os.getenv('PAPER_STARTING_CAPITAL_ZAR', '30000'))  # Default paper starting capital
MIN_WIN_RATE = 0.52  # 52%
MIN_PROFIT_PERCENT = 0.03  # 3%
MIN_TRADES_FOR_PROMOTION = 25

# Live Training Bay - new/spawned bots must be quarantined for minimum hours before trading
LIVE_MIN_TRAINING_HOURS = int(os.getenv('LIVE_MIN_TRAINING_HOURS', '24'))  # Default 24 hours

# Autopilot settings (configurable via env vars)
# Bot Spawning Logic - SEPARATED THRESHOLDS for clarity
BOT_SPAWN_PROFIT_ZAR = int(os.getenv('BOT_SPAWN_PROFIT_ZAR', '1000'))  # Spawn new bot when profit reaches this
BOT_SPAWN_PROFIT_THRESHOLD_ZAR = BOT_SPAWN_PROFIT_ZAR  # Backward compatibility alias
NEW_BOT_SEED_CAPITAL_ZAR = int(os.getenv('NEW_BOT_SEED_CAPITAL_ZAR', '500'))  # Capital to give new bot
REINVEST_THRESHOLD_ZAR = int(os.getenv('REINVEST_THRESHOLD_ZAR', '300'))  # Lower threshold for more frequent reinvestment
NEW_BOT_CAPITAL = NEW_BOT_SEED_CAPITAL_ZAR  # Backward compatibility alias
MAX_TOTAL_BOTS = int(os.getenv('MAX_TOTAL_BOTS', '65'))  # MUST match MAX_BOTS_GLOBAL in exchange_limits.py (5+10+10+10+10+10+10)
TOP_PERFORMERS_COUNT = int(os.getenv('TOP_PERFORMERS_COUNT', '5'))
EVOLUTION_MUTATION_RATE = float(os.getenv('EVOLUTION_MUTATION_RATE', '0.25'))  # 25% mutation rate for genetic evolution
QUARANTINE_THRESHOLD = float(os.getenv('QUARANTINE_THRESHOLD', '-0.05'))  # -5% performance threshold

# Per-exchange bot spawning configuration
ENABLE_PER_EXCHANGE_BOT_SPAWN = os.getenv('ENABLE_PER_EXCHANGE_BOT_SPAWN', 'true').lower() == 'true'
ENABLE_OVERALL_PROFIT_THRESHOLD = os.getenv('ENABLE_OVERALL_PROFIT_THRESHOLD', 'false').lower() == 'true'
OVERALL_PROFIT_THRESHOLD_ZAR = int(os.getenv('OVERALL_PROFIT_THRESHOLD_ZAR', '5000'))

# AI Models
AI_MODELS = {
    'system_brain': 'gpt-5.1',  # Autopilot, risk, learning
    'trade_decision': 'gpt-4o',  # Per-bot decisions
    'reporting': 'gpt-4',  # Summaries, emails
    'chatops': 'gpt-4o'  # Dashboard chat
}

# Risk settings
STOP_LOSS_SAFE = 0.05  # 5%
STOP_LOSS_BALANCED = 0.10  # 10%
STOP_LOSS_AGGRESSIVE = 0.15  # 15%

# Risk Management - Adjusted for production (more tolerance)
MAX_HOURLY_LOSS_PERCENT = 0.15  # 15% in 1 hour
MAX_DAILY_LOSS_PERCENT = float(os.getenv('MAX_DAILY_LOSS_PERCENT', '0.15'))  # 15% daily loss limit (increased from 10%)
MAX_DRAWDOWN_PERCENT = float(os.getenv('MAX_DRAWDOWN_PERCENT', '0.25'))  # 25% drawdown limit (increased from 20%)
MIN_POSITION_SIZE_PERCENT = 0.02  # 2% minimum per-trade sizing
MAX_POSITION_SIZE_PERCENT = 0.05  # 5% maximum per-trade sizing

# Self-healing configuration
MAX_ERRORS_PER_HOUR = int(os.getenv('MAX_ERRORS_PER_HOUR', '20'))  # Error budget for self-healing

# ============================================================================
# WALLET TRANSFER LIMITS & SECURITY
# ============================================================================

# Withdrawal limits (USD equivalent)
DAILY_WITHDRAWAL_LIMIT_USD = float(os.getenv('DAILY_WITHDRAWAL_LIMIT_USD', '10000'))  # $10k per day default
MONTHLY_WITHDRAWAL_LIMIT_USD = float(os.getenv('MONTHLY_WITHDRAWAL_LIMIT_USD', '100000'))  # $100k per month default
MAX_SINGLE_WITHDRAWAL_USD = float(os.getenv('MAX_SINGLE_WITHDRAWAL_USD', '5000'))  # $5k per transaction default

# Email confirmation for withdrawals
REQUIRE_EMAIL_CONFIRMATION = os.getenv('REQUIRE_EMAIL_CONFIRMATION', 'true').lower() == 'true'
EMAIL_CONFIRMATION_TIMEOUT_HOURS = int(os.getenv('EMAIL_CONFIRMATION_TIMEOUT_HOURS', '24'))  # 24 hour token expiry

# Whitelisted addresses requirement
REQUIRE_WHITELISTED_ADDRESS = os.getenv('REQUIRE_WHITELISTED_ADDRESS', 'true').lower() == 'true'

# Rate limiting for withdrawals
MAX_WITHDRAWAL_ATTEMPTS_PER_HOUR = int(os.getenv('MAX_WITHDRAWAL_ATTEMPTS_PER_HOUR', '5'))  # Prevent spam

# ============================================================================
# WALLET TRANSFER SECURITY & LIMITS (Production-Safe)
# ============================================================================

# 2FA Requirements
REQUIRE_2FA_FOR_WITHDRAWALS = os.getenv('REQUIRE_2FA_FOR_WITHDRAWALS', 'false').lower() == 'true'  # OFF by default, enable for production

# Admin Approval Thresholds (ZAR)
REQUIRE_ADMIN_APPROVAL_ABOVE_ZAR = float(os.getenv('REQUIRE_ADMIN_APPROVAL_ABOVE_ZAR', '100000'))  # R100k default

# Transfer Limits (ZAR)
WALLET_MAX_TRANSFER_ZAR_PER_TX = float(os.getenv('WALLET_MAX_TRANSFER_ZAR_PER_TX', '50000'))  # R50k per transaction
WALLET_MAX_TRANSFER_ZAR_PER_DAY = float(os.getenv('WALLET_MAX_TRANSFER_ZAR_PER_DAY', '200000'))  # R200k per day
WALLET_MAX_TRANSFER_ZAR_PER_MONTH = float(os.getenv('WALLET_MAX_TRANSFER_ZAR_PER_MONTH', '2000000'))  # R2M per month

# Address Whitelisting
REQUIRE_ADDRESS_WHITELIST = os.getenv('REQUIRE_ADDRESS_WHITELIST', 'true').lower() == 'true'  # Require whitelisted addresses

# Reserve Requirements (ZAR) - Working Capital Model
MIN_RESERVE_LUNO_ZAR = float(os.getenv('MIN_RESERVE_LUNO_ZAR', '10000'))  # R10k minimum on Luno (hub)
MIN_RESERVE_PER_EXCHANGE_ZAR = float(os.getenv('MIN_RESERVE_PER_EXCHANGE_ZAR', '5000'))  # R5k minimum per other exchange

# ============================================================================
# DeFi/DEX TRADING SETTINGS
# ============================================================================

# Web3 Provider URLs (Alchemy, Infura, etc.)
ETH_RPC_URL = os.getenv('ETH_RPC_URL', 'https://eth.llamarpc.com')  # Public fallback
BSC_RPC_URL = os.getenv('BSC_RPC_URL', 'https://bsc-dataseed.binance.org')  # Public fallback
POLYGON_RPC_URL = os.getenv('POLYGON_RPC_URL', 'https://polygon-rpc.com')  # Public fallback

# DEX Router Addresses (Uniswap V2 style)
UNISWAP_V2_ROUTER = '0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D'  # Ethereum Mainnet
PANCAKESWAP_ROUTER = '0x10ED43C718714eb63d5aA57B78B54704E256024E'  # BSC Mainnet
QUICKSWAP_ROUTER = '0xa5E0829CaCEd8fFDD4De3c43696c57F7D7A678ff'  # Polygon Mainnet

# DEX Trading Limits
MAX_SLIPPAGE_PERCENT = float(os.getenv('MAX_SLIPPAGE_PERCENT', '5.0'))  # 5% max slippage
MIN_LIQUIDITY_USD = float(os.getenv('MIN_LIQUIDITY_USD', '10000'))  # Minimum liquidity for safety
GAS_LIMIT_SWAP = int(os.getenv('GAS_LIMIT_SWAP', '300000'))  # Gas limit for swaps
GAS_LIMIT_APPROVAL = int(os.getenv('GAS_LIMIT_APPROVAL', '100000'))  # Gas limit for approvals
