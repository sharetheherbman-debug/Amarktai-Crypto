"""
Config package
==============
CANONICAL RUNTIME CONFIG.  Python resolves `import config` to this package
(config/__init__.py), NOT to the standalone config.py file in the parent
directory.  ALL changes to runtime defaults MUST be made here.

config.py (parent) is kept as a thin reference copy for IDE navigation and
legacy tooling only — it is never imported at runtime when this package exists.
"""

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

# Exchange limits (8 canonical exchanges)
EXCHANGE_BOT_LIMITS = {
    'luno': 10,  # 10 total on Luno: 5 normal + 5 scalper
    'binance': 10,
    'kucoin': 10,
    'bybit': 10,
    'kraken': 10,
    'bitget': 10,
    'gate': 10,
    'coinbase': 10,
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
    },
    'coinbase': {
        'max_trades_per_bot_per_day': int(os.getenv('MAX_TRADES_PER_BOT_DAILY_COINBASE', '999999')),
        'min_cooldown_minutes': 15,
        'max_api_calls_per_minute': 30
    },
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
PAPER_PAIR_WHITELIST_ENABLED = os.getenv('PAPER_PAIR_WHITELIST_ENABLED', 'false').lower() == 'true'
PAPER_STALE_EXIT_MINUTES = int(os.getenv('PAPER_STALE_EXIT_MINUTES', '120'))
# Time-exit fires unconditionally at this age regardless of P&L.
# Ensures profitable trades still close for overnight win/loss accounting.
PAPER_MAX_HOLD_MINUTES = int(os.getenv('PAPER_MAX_HOLD_MINUTES', '120'))
# Safety exit fires when a trade is profitable and has been open this long.
# Prevents profitable trades from lingering past half max-hold without a signal.
# Default 60 min; set to 0 to disable.
PAPER_SAFETY_EXIT_MINUTES = int(os.getenv('PAPER_SAFETY_EXIT_MINUTES', '60'))
# Stagnation exit: close if price hasn't moved beyond estimated round-trip cost
# (fees + spread) for this many minutes.  Prevents idle capital.  Default: 7 min.
# (reduced from 10 to exit faster on no movement and reduce stagnation losses).
STAGNATION_EXIT_MINUTES = int(os.getenv('STAGNATION_EXIT_MINUTES', '7'))
# Fee break-even exit: close when the trade has been open at least this long AND
# the unrealised PnL is definitively below -round_trip_cost_pct (the loss already
# exceeds what fees/spread would cost even at breakeven).  Default: 10 min.
FEE_BREAK_EVEN_WINDOW_MINUTES = int(os.getenv('FEE_BREAK_EVEN_WINDOW_MINUTES', '10'))
# Time-decay exit: close when the trade has been open at least this long AND
# the unrealised PnL is still below +round_trip_cost_pct (has not yet generated
# enough profit to cover costs).  Fires after soft_max_hold so it catches trades
# that could not exit at soft due to wide spread.  Default: 20 min.
TIME_DECAY_EXIT_MINUTES = int(os.getenv('TIME_DECAY_EXIT_MINUTES', '20'))
# Stop-loss cooldown: after a stop-loss on a symbol, block that symbol for this
# many minutes before the bot can re-open it.  Longer than the regular cooldown.
# Default: 30 min.
STOP_LOSS_COOLDOWN_MINUTES = int(os.getenv('STOP_LOSS_COOLDOWN_MINUTES', '30'))
# Adaptive entry threshold — losing streak guardrails:
# LOSING_STREAK_THRESHOLD : consecutive stop-losses before confidence bar is raised.
# LOSING_STREAK_SIGNAL_BOOST : extra avg_confidence required per active loss streak.
# E.g. normal threshold = 0.65; after 3 losses, threshold = 0.65 + 0.10 = 0.75.
LOSING_STREAK_THRESHOLD = int(os.getenv('LOSING_STREAK_THRESHOLD', '3'))
LOSING_STREAK_SIGNAL_BOOST = float(os.getenv('LOSING_STREAK_SIGNAL_BOOST', '0.10'))
# Base average-confidence threshold for entry. Raised by LOSING_STREAK_SIGNAL_BOOST
# after a losing streak. Set to 0.45 to require meaningful signal quality before entry;
# avoids low-confidence trades that pass only because the local regime source is available.
BASE_CONFIDENCE_THRESHOLD = float(os.getenv('BASE_CONFIDENCE_THRESHOLD', '0.45'))

# ── Scalper-specific stricter thresholds ────────────────────────────────────
# Scalpers require higher signal quality than normal bots because their profit
# window per trade is smaller (less room to absorb spread + fee costs).
SCALPER_CONFIDENCE_THRESHOLD = float(os.getenv('SCALPER_CONFIDENCE_THRESHOLD', '0.62'))
# Max hold time for scalpers (minutes).  Normal bots use PAPER_MAX_HOLD_MINUTES.
SCALPER_MAX_HOLD_MINUTES = int(os.getenv('SCALPER_MAX_HOLD_MINUTES', '25'))
# Max spread (%) for scalpers.  Normal bots use PAPER_MAX_SPREAD_PCT.
# 0.30% allows realistic ZAR-quoted pair spreads (Luno BTC/ZAR is typically 0.1-0.3%).
# The previous 0.15% was too tight, permanently blocking scalpers on ZAR pairs.
SCALPER_MAX_SPREAD_PCT = float(os.getenv('SCALPER_MAX_SPREAD_PCT', '0.30'))
# Soft max-hold (seconds): close if spread is acceptable; retry otherwise but
# cannot exceed HARD_MAX_HOLD_SECONDS.  Fires AFTER the regular time_exit at
# PAPER_MAX_HOLD_MINUTES as a grace-window for spread-sensitive exits.
# Default: 8100 (135 minutes = 2h 15min).
SOFT_MAX_HOLD_SECONDS = int(os.getenv('SOFT_MAX_HOLD_SECONDS', '8100'))
# Hard max-hold (seconds): force-close unconditionally — even on low confidence.
# Low confidence may block OPENING new trades but must never block CLOSING.
# Fires after SOFT_MAX_HOLD_SECONDS as an absolute last resort.
# Default: 8700 (145 minutes = 2h 25min).
HARD_MAX_HOLD_SECONDS = int(os.getenv('HARD_MAX_HOLD_SECONDS', '8700'))
# Symbol rotation anti-repeat: cooldown window (minutes) before the same symbol
# can be re-selected for a new trade on the same bot.  Default: 15 min.
SYMBOL_COOLDOWN_MINUTES = int(os.getenv('SYMBOL_COOLDOWN_MINUTES', '15'))
# Symbol rotation anti-repeat: last N closed/open symbols tracked per bot.
SYMBOL_COOLDOWN_HISTORY = int(os.getenv('SYMBOL_COOLDOWN_HISTORY', '3'))
# Portfolio guard: max new opens on the same symbol per user in this window (minutes).
PORTFOLIO_GUARD_WINDOW_MINUTES = int(os.getenv('PORTFOLIO_GUARD_WINDOW_MINUTES', '10'))
# Portfolio guard: max concurrent open trades on the same symbol per user.
PORTFOLIO_GUARD_MAX_SAME_SYMBOL = int(os.getenv('PORTFOLIO_GUARD_MAX_SAME_SYMBOL', '1'))
# Training-mode max hold: closes training trades sooner to speed up the learn loop.
# Default 45 min; recorded as close_reason=training_timeout.
TRAINING_MAX_HOLD_MINUTES = int(os.getenv('TRAINING_MAX_HOLD_MINUTES', '45'))
# Number of successfully closed trades required to complete training.
# Default 5; bot auto-graduates once closed_trades_count reaches this value.
TRAINING_TRADES_REQUIRED = int(os.getenv('TRAINING_TRADES_REQUIRED', '5'))

# ── Expectancy / Drawdown guards ────────────────────────────────────────────
# Maximum drawdown (as a fraction of peak equity) before bots stand down.
# When realised drawdown >= MAX_DRAWDOWN_PCT, no new trades are opened.
# Default: 0.10 (10 %).  Set 0 to disable.
MAX_DRAWDOWN_PCT = float(os.getenv('MAX_DRAWDOWN_PCT', '0.10'))
# Minimum estimated expectancy (ZAR per trade) required to open a trade.
# Expectancy = (win_rate * avg_win) - (loss_rate * avg_loss) - round_trip_cost
# 0 means "expectancy must be strictly positive". Set negative to disable.
MIN_EXPECTANCY_ZAR = float(os.getenv('MIN_EXPECTANCY_ZAR', '0'))

# Minimum net edge percentage required AFTER round-trip costs before a trade is entered.
# When ml_is_simulated=True the hard filter uses break-even (expected_move >= cost)
# instead of this threshold so the bot can collect learning data.
# Set to 0.02% (paper-trading learning phase — relaxed for data collection).
MINIMUM_EDGE_PCT = float(os.getenv('MINIMUM_EDGE_PCT', '0.02'))

# ── Safety buffer & regime playbooks ────────────────────────────────────────
# Base safety buffer added on top of fees+spread+slippage in the edge gate.
# Default 0.10 %.  In wide-spread / low-liquidity regimes this is multiplied
# by SAFETY_BUFFER_WIDE_SPREAD_MULTIPLIER so bots are more selective.
SAFETY_BUFFER_PCT = float(os.getenv('SAFETY_BUFFER_PCT', '0.10'))
# Multiplier applied to SAFETY_BUFFER_PCT when spread > PAPER_MAX_SPREAD_PCT * 0.6
# (i.e. spread is "wide but still below the hard cutoff").  Default: 2.0.
SAFETY_BUFFER_WIDE_SPREAD_MULTIPLIER = float(os.getenv('SAFETY_BUFFER_WIDE_SPREAD_MULTIPLIER', '2.0'))

# ── Per-risk-mode adaptive defaults ─────────────────────────────────────────
# Bots use these defaults when no custom bot-level override is set.
# Targets are NOT hard-coded outcomes; they tune behaviour (risk / selectivity
# / frequency) within the drawdown and expectancy guardrails above.
RISK_MODE_CONFIG: dict = {
    "safe": {
        "max_hold_minutes": int(os.getenv('SAFE_MAX_HOLD_MINUTES', '60')),
        "safety_exit_minutes": int(os.getenv('SAFE_SAFETY_EXIT_MINUTES', '30')),
        "take_profit_pct": float(os.getenv('SAFE_TAKE_PROFIT_PCT', '0.015')),
        "stop_loss_pct": float(os.getenv('SAFE_STOP_LOSS_PCT', '0.010')),
        "position_size_pct": float(os.getenv('SAFE_POSITION_SIZE_PCT', '0.20')),
        "min_confidence": float(os.getenv('SAFE_MIN_CONFIDENCE', '0.65')),
        "safety_buffer_pct": float(os.getenv('SAFE_SAFETY_BUFFER_PCT', '0.15')),
        # Adaptive target: aim ~3-4% daily on R1000 initial budget
        "daily_target_pct": float(os.getenv('SAFE_DAILY_TARGET_PCT', '0.03')),
    },
    "balanced": {
        "max_hold_minutes": int(os.getenv('BALANCED_MAX_HOLD_MINUTES', '90')),
        "safety_exit_minutes": int(os.getenv('BALANCED_SAFETY_EXIT_MINUTES', '45')),
        "take_profit_pct": float(os.getenv('BALANCED_TAKE_PROFIT_PCT', '0.025')),
        "stop_loss_pct": float(os.getenv('BALANCED_STOP_LOSS_PCT', '0.015')),
        "position_size_pct": float(os.getenv('BALANCED_POSITION_SIZE_PCT', '0.30')),
        "min_confidence": float(os.getenv('BALANCED_MIN_CONFIDENCE', '0.60')),
        "safety_buffer_pct": float(os.getenv('BALANCED_SAFETY_BUFFER_PCT', '0.10')),
        "daily_target_pct": float(os.getenv('BALANCED_DAILY_TARGET_PCT', '0.05')),
    },
    "aggressive": {
        "max_hold_minutes": int(os.getenv('AGGRESSIVE_MAX_HOLD_MINUTES', '120')),
        "safety_exit_minutes": int(os.getenv('AGGRESSIVE_SAFETY_EXIT_MINUTES', '60')),
        "take_profit_pct": float(os.getenv('AGGRESSIVE_TAKE_PROFIT_PCT', '0.04')),
        "stop_loss_pct": float(os.getenv('AGGRESSIVE_STOP_LOSS_PCT', '0.025')),
        "position_size_pct": float(os.getenv('AGGRESSIVE_POSITION_SIZE_PCT', '0.45')),
        "min_confidence": float(os.getenv('AGGRESSIVE_MIN_CONFIDENCE', '0.55')),
        "safety_buffer_pct": float(os.getenv('AGGRESSIVE_SAFETY_BUFFER_PCT', '0.08')),
        "daily_target_pct": float(os.getenv('AGGRESSIVE_DAILY_TARGET_PCT', '0.08')),
    },
}

# Broad per-exchange pair universe used as a FALLBACK when PAPER_PAIR_WHITELIST_ENABLED=true.
# By default PAPER_PAIR_WHITELIST_ENABLED=false so dynamic exchange discovery is used instead.
# When enabled (e.g. via env var) this list acts as a curated safety universe, not a hard block.
PAPER_PAIR_WHITELIST = {
    "luno": [
        "BTC/ZAR", "ETH/ZAR", "XRP/ZAR", "SOL/ZAR", "USDC/ZAR",
        "LTC/ZAR", "BCH/ZAR", "LINK/ZAR",
    ],
    "binance": [
        "BTC/USDT", "ETH/USDT", "BNB/USDT", "SOL/USDT", "XRP/USDT",
        "ADA/USDT", "DOGE/USDT", "AVAX/USDT", "DOT/USDT", "MATIC/USDT",
        "LTC/USDT", "LINK/USDT", "UNI/USDT", "ATOM/USDT", "FIL/USDT",
        "NEAR/USDT", "APT/USDT", "ARB/USDT", "OP/USDT", "SUI/USDT",
    ],
    "kucoin": [
        "BTC/USDT", "ETH/USDT", "BNB/USDT", "SOL/USDT", "XRP/USDT",
        "ADA/USDT", "DOGE/USDT", "AVAX/USDT", "DOT/USDT", "MATIC/USDT",
        "LTC/USDT", "LINK/USDT", "UNI/USDT", "ATOM/USDT", "NEAR/USDT",
        "APT/USDT", "ARB/USDT", "OP/USDT", "SUI/USDT", "KCS/USDT",
    ],
    "bybit": [
        "BTC/USDT", "ETH/USDT", "BNB/USDT", "SOL/USDT", "XRP/USDT",
        "ADA/USDT", "DOGE/USDT", "AVAX/USDT", "DOT/USDT", "MATIC/USDT",
        "LTC/USDT", "LINK/USDT", "UNI/USDT", "ATOM/USDT", "NEAR/USDT",
        "APT/USDT", "ARB/USDT", "OP/USDT", "SUI/USDT",
    ],
    "kraken": [
        "BTC/USDT", "ETH/USDT", "SOL/USDT", "XRP/USDT", "ADA/USDT",
        "DOGE/USDT", "AVAX/USDT", "DOT/USDT", "MATIC/USDT", "LTC/USDT",
        "LINK/USDT", "UNI/USDT", "ATOM/USDT", "NEAR/USDT",
    ],
    "bitget": [
        "BTC/USDT", "ETH/USDT", "BNB/USDT", "SOL/USDT", "XRP/USDT",
        "ADA/USDT", "DOGE/USDT", "AVAX/USDT", "DOT/USDT", "MATIC/USDT",
        "LTC/USDT", "LINK/USDT", "UNI/USDT", "ATOM/USDT", "NEAR/USDT",
        "APT/USDT", "ARB/USDT", "OP/USDT", "SUI/USDT",
    ],
    "gate": [
        "BTC/USDT", "ETH/USDT", "SOL/USDT", "XRP/USDT", "ADA/USDT",
        "DOGE/USDT", "AVAX/USDT", "DOT/USDT", "MATIC/USDT", "LTC/USDT",
        "LINK/USDT", "UNI/USDT", "ATOM/USDT", "NEAR/USDT", "ARB/USDT",
    ],
    "coinbase": [
        "BTC/USDT", "ETH/USDT", "SOL/USDT", "XRP/USDT", "ADA/USDT",
        "DOGE/USDT", "AVAX/USDT", "DOT/USDT", "MATIC/USDT", "LTC/USDT",
        "LINK/USDT", "UNI/USDT", "ATOM/USDT", "NEAR/USDT", "APT/USDT",
    ],
}
EXCHANGE_DAILY_TRADE_LIMITS = {
    'luno': int(os.getenv('LUNO_MAX_TRADES_PER_DAY', '20000')),
    'binance': int(os.getenv('BINANCE_MAX_TRADES_PER_DAY', '50000')),
    'kucoin': int(os.getenv('KUCOIN_MAX_TRADES_PER_DAY', '100000')),
    'bybit': int(os.getenv('BYBIT_MAX_TRADES_PER_DAY', '100000')),
    'kraken': int(os.getenv('KRAKEN_MAX_TRADES_PER_DAY', '50000')),
    'bitget': int(os.getenv('BITGET_MAX_TRADES_PER_DAY', '80000')),
    'gate': int(os.getenv('GATEIO_MAX_TRADES_PER_DAY', '80000')),
    'coinbase': int(os.getenv('COINBASE_MAX_TRADES_PER_DAY', '40000')),
}

# Autopilot settings (configurable via env vars)
# Bot Spawning Logic - SEPARATED THRESHOLDS for clarity
BOT_SPAWN_PROFIT_THRESHOLD_ZAR = int(os.getenv('BOT_SPAWN_PROFIT_THRESHOLD_ZAR', '1000'))  # Spawn new bot when profit reaches this
AUTO_SPAWN_COOLDOWN_MINUTES = int(os.getenv('AUTO_SPAWN_COOLDOWN_MINUTES', '60'))
AUTO_SPAWN_MAX_PER_DAY = int(os.getenv('AUTO_SPAWN_MAX_PER_DAY', '2'))
NEW_BOT_SEED_CAPITAL_ZAR = int(os.getenv('NEW_BOT_SEED_CAPITAL_ZAR', '200'))  # Capital to give new bot (auto-spawned only)
REINVEST_THRESHOLD_ZAR = int(os.getenv('REINVEST_THRESHOLD_ZAR', '50'))  # Lower threshold for more frequent reinvestment
NEW_BOT_CAPITAL = NEW_BOT_SEED_CAPITAL_ZAR  # Backward compatibility alias
# Minimum starting capital for any manually-created bot (all platforms).
# Auto-spawned (growth-engine) bots are exempt — they use NEW_BOT_SEED_CAPITAL_ZAR.
BOT_MANUAL_MIN_CAPITAL_ZAR = int(os.getenv('BOT_MANUAL_MIN_CAPITAL_ZAR', '1000'))
MAX_TOTAL_BOTS = int(os.getenv('MAX_TOTAL_BOTS', '75'))  # Must equal MAX_BOTS_GLOBAL in exchange_limits.py (currently 75)
TOP_PERFORMERS_COUNT = int(os.getenv('TOP_PERFORMERS_COUNT', '5'))
EVOLUTION_MUTATION_RATE = float(os.getenv('EVOLUTION_MUTATION_RATE', '0.25'))  # 25% mutation
QUARANTINE_THRESHOLD = float(os.getenv('QUARANTINE_THRESHOLD', '-0.05'))  # -5% threshold

# Autopilot growth + reinvest controls
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
NEW_TRADING_BRAIN_V2 = os.getenv('NEW_TRADING_BRAIN_V2', 'true').lower() == 'true'

# Live Trading Gate Requirements
REQUIRE_WALLET_FUNDED = os.getenv('REQUIRE_WALLET_FUNDED', 'true').lower() == 'true'
REQUIRE_API_KEYS_FOR_LIVE = os.getenv('REQUIRE_API_KEYS_FOR_LIVE', 'true').lower() == 'true'
AUTO_PROMOTE_LIVE = os.getenv('AUTO_PROMOTE_LIVE', 'false').lower() == 'true'  # Auto-promote eligible bots from paper to live daily

# Supported Exchanges for Paper Trading
# Import from canonical source: backend/config/platforms.py
from config.platforms import SUPPORTED_PLATFORMS
PAPER_SUPPORTED_EXCHANGES = set(SUPPORTED_PLATFORMS)  # All 8 exchanges supported

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
    'PAPER_SAFETY_EXIT_MINUTES',
    'STAGNATION_EXIT_MINUTES',
    'FEE_BREAK_EVEN_WINDOW_MINUTES',
    'TIME_DECAY_EXIT_MINUTES',
    'STOP_LOSS_COOLDOWN_MINUTES',
    'LOSING_STREAK_THRESHOLD',
    'LOSING_STREAK_SIGNAL_BOOST',
    'BASE_CONFIDENCE_THRESHOLD',
    'SCALPER_CONFIDENCE_THRESHOLD',
    'SCALPER_MAX_HOLD_MINUTES',
    'SCALPER_MAX_SPREAD_PCT',
    'SOFT_MAX_HOLD_SECONDS',
    'HARD_MAX_HOLD_SECONDS',
    'SYMBOL_COOLDOWN_MINUTES',
    'SYMBOL_COOLDOWN_HISTORY',
    'PORTFOLIO_GUARD_WINDOW_MINUTES',
    'PORTFOLIO_GUARD_MAX_SAME_SYMBOL',
    'TRAINING_MAX_HOLD_MINUTES',
    'TRAINING_TRADES_REQUIRED',
    'MAX_DRAWDOWN_PCT',
    'MIN_EXPECTANCY_ZAR',
    'MINIMUM_EDGE_PCT',
    'SAFETY_BUFFER_PCT',
    'SAFETY_BUFFER_WIDE_SPREAD_MULTIPLIER',
    'RISK_MODE_CONFIG',
    'EXCHANGE_DAILY_TRADE_LIMITS',
    'BOT_SPAWN_PROFIT_THRESHOLD_ZAR', 'AUTO_SPAWN_COOLDOWN_MINUTES', 'AUTO_SPAWN_MAX_PER_DAY',
    'NEW_BOT_SEED_CAPITAL_ZAR', 'REINVEST_THRESHOLD_ZAR',
    'NEW_BOT_CAPITAL', 'BOT_MANUAL_MIN_CAPITAL_ZAR', 'MAX_TOTAL_BOTS', 'TOP_PERFORMERS_COUNT',
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
    'NEW_TRADING_BRAIN_V2',
    'AUTOPILOT_PROFIT_MILESTONE_ZAR', 'AUTOPILOT_REINVEST_MIN_ZAR',
    'AUTOPILOT_MAX_BOTS_PER_PLATFORM',
    'REQUIRE_WALLET_FUNDED', 'REQUIRE_API_KEYS_FOR_LIVE', 'AUTO_PROMOTE_LIVE', 'PAPER_SUPPORTED_EXCHANGES'
]
