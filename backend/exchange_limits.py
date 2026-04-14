"""Exchange rate limits and caps for safe trading"""

"""
Exchange Rate Limits - Production Requirements

REQUIREMENTS PER EXCHANGE (NORMAL BOTS):
- Luno: 10 bots max total (5 normal + 5 scalper), 400 trades/bot/day, 2,000 total/day
- Binance: 10 bots max, 500 trades/bot/day, 5,000 total/day
- KuCoin: 10 bots max, 1,000 trades/bot/day, 10,000 total/day
- Bybit: 10 bots max, 800 trades/bot/day, 8,000 total/day
- Kraken: 10 bots max, 800 trades/bot/day, 8,000 total/day
- Bitget: 10 bots max, 800 trades/bot/day, 8,000 total/day
- Gate.io: 10 bots max, 800 trades/bot/day, 8,000 total/day
- Coinbase: 10 bots max, 600 trades/bot/day, 6,000 total/day

GLOBAL LIMIT (NORMAL): 75 bots total across all 8 exchanges (5+5 luno + 10×7)

SCALPER BOTS (SEPARATE CATEGORY):
- Luno: max 5 scalper bots (in addition to 5 normal = 10 total on Luno)
- All other exchanges: max 10 scalper bots each
- Scalpers are tracked independently from normal bots.
- Scalper caps do NOT affect normal bot caps.

GLOBAL LIMIT (SCALPER): 75 scalper bots total across all 8 exchanges (5 + 10×7)

These limits ensure:
- Safe operation within exchange API limits
- Realistic paper trading that mirrors live constraints
- Proper throttling and rate limiting
"""

import os

# ── Normal bot limits ───────────────────────────────────────────────────
MAX_BOTS_GLOBAL = 75  # Normal bots only: 5 (luno) + 10*7 (others) = 75

BOT_ALLOCATION = {
    "luno": 5,
    "binance": 10,
    "kucoin": 10,
    "bybit": 10,
    "kraken": 10,
    "bitget": 10,
    "gate": 10,
    "coinbase": 10,
}

# ── Scalper bot limits (separate category) ──────────────────────────────
MAX_SCALPER_BOTS_GLOBAL = 75  # 5 (luno) + 10*7 (others) = 75

SCALPER_BOT_ALLOCATION = {
    "luno": 5,
    "binance": 10,
    "kucoin": 10,
    "bybit": 10,
    "kraken": 10,
    "bitget": 10,
    "gate": 10,
    "coinbase": 10,
}

# ── Scalper EV gating thresholds ────────────────────────────────────────
SCALPER_EV_MIN_BPS = 10           # Minimum expected value in basis points
SCALPER_SPREAD_MAX_BPS = 50       # Maximum spread allowed (basis points)
SCALPER_DEPTH_MIN_QUOTE = 100     # Minimum order book depth in quote currency
SCALPER_MAX_HOLD_SECONDS = 300    # 5 minutes default max hold
SCALPER_STAGNATION_SECONDS = 120  # Exit if no price movement in 2 min
SCALPER_ORDERS_PER_MIN = 10       # Max orders per minute per bot
SCALPER_CANCELS_PER_MIN = 5       # Max cancels per minute per bot
SCALPER_COOLDOWN_SECONDS = int(os.getenv("SCALPER_COOLDOWN_SECONDS", "30"))  # Cooldown between trades per bot

# ── Forced exit reason codes ────────────────────────────────────────────
EXIT_REASON_TIME = "TIME_EXIT"
EXIT_REASON_STAGNATION = "STAGNATION_EXIT"
EXIT_REASON_STOP = "STOP_EXIT"
EXIT_REASON_TARGET = "TARGET_EXIT"
EXIT_REASON_TRAIL = "TRAIL_EXIT"
EXIT_REASON_RISK = "RISK_EXIT"

EXCHANGE_LIMITS = {
    "luno": {
        "max_bots": 5,
        "trades_per_bot_day": 400,
        "total_trades_day": 2000,  # 5 bots × 400
        "max_orders_per_day": 2000,  # Alias for total_trades_day
        "max_orders_per_bot_per_day": 400,  # Alias for trades_per_bot_day
        "max_orders_per_minute": 60,
        "max_orders_per_10_seconds": 10,
        "fee_maker": 0.002,  # 0.2%
        "fee_taker": 0.0025,  # 0.25%
    },
    "binance": {
        "max_bots": 10,
        "trades_per_bot_day": 500,
        "total_trades_day": 5000,  # 10 bots × 500
        "max_orders_per_day": 5000,  # Alias for total_trades_day
        "max_orders_per_bot_per_day": 500,  # Alias for trades_per_bot_day
        "max_orders_per_minute": 60,
        "max_orders_per_10_seconds": 10,
        "fee_maker": 0.001,  # 0.1%
        "fee_taker": 0.001,  # 0.1%
    },
    "kucoin": {
        "max_bots": 10,
        "trades_per_bot_day": 1000,
        "total_trades_day": 10000,  # 10 bots × 1,000
        "max_orders_per_day": 10000,  # Alias for total_trades_day
        "max_orders_per_bot_per_day": 1000,  # Alias for trades_per_bot_day
        "max_orders_per_minute": 60,
        "max_orders_per_10_seconds": 10,
        "fee_maker": 0.001,  # 0.1%
        "fee_taker": 0.001,  # 0.1%
    },
    "bybit": {
        "max_bots": 10,
        "trades_per_bot_day": 800,
        "total_trades_day": 8000,  # 10 bots × 800
        "max_orders_per_day": 8000,  # Alias for total_trades_day
        "max_orders_per_bot_per_day": 800,  # Alias for trades_per_bot_day
        "max_orders_per_minute": 60,
        "max_orders_per_10_seconds": 10,
        "fee_maker": 0.001,  # 0.1%
        "fee_taker": 0.001,  # 0.1%
    },
    "bitget": {
        "max_bots": 10,
        "trades_per_bot_day": 800,
        "total_trades_day": 8000,  # 10 bots × 800
        "max_orders_per_day": 8000,  # Alias for total_trades_day
        "max_orders_per_bot_per_day": 800,  # Alias for trades_per_bot_day
        "max_orders_per_minute": 60,
        "max_orders_per_10_seconds": 10,
        "fee_maker": 0.001,  # 0.1%
        "fee_taker": 0.001,  # 0.1%
    },
    "kraken": {
        "max_bots": 10,
        "trades_per_bot_day": 800,
        "total_trades_day": 8000,  # 10 bots × 800
        "max_orders_per_day": 8000,  # Alias for total_trades_day
        "max_orders_per_bot_per_day": 800,  # Alias for trades_per_bot_day
        "max_orders_per_minute": 60,
        "max_orders_per_10_seconds": 10,
        "fee_maker": 0.0016,  # 0.16%
        "fee_taker": 0.0026,  # 0.26%
    },
    "gate": {
        "max_bots": 10,
        "trades_per_bot_day": 800,
        "total_trades_day": 8000,  # 10 bots × 800
        "max_orders_per_day": 8000,  # Alias for total_trades_day
        "max_orders_per_bot_per_day": 800,  # Alias for trades_per_bot_day
        "max_orders_per_minute": 60,
        "max_orders_per_10_seconds": 10,
        "fee_maker": 0.002,  # 0.2%
        "fee_taker": 0.002,  # 0.2%
    },
    "coinbase": {
        "max_bots": 10,
        "trades_per_bot_day": 600,
        "total_trades_day": 6000,  # 10 bots × 600
        "max_orders_per_day": 6000,  # Alias for total_trades_day
        "max_orders_per_bot_per_day": 600,  # Alias for trades_per_bot_day
        "max_orders_per_minute": 30,
        "max_orders_per_10_seconds": 5,
        "fee_maker": 0.004,  # 0.4%
        "fee_taker": 0.006,  # 0.6%
    },
}

def get_exchange_limits(exchange: str) -> dict:
    """Get limits for an exchange with safe defaults"""
    limits = EXCHANGE_LIMITS.get(exchange.lower(), EXCHANGE_LIMITS["luno"])
    
    # Ensure all required keys exist with safe defaults
    defaults = {
        "max_orders_per_day": 2000,
        "max_orders_per_bot_per_day": 400,
        "max_orders_per_minute": 60,
        "max_orders_per_10_seconds": 10,
        "fee_maker": 0.001,
        "fee_taker": 0.001,
    }
    
    # Merge defaults with existing limits (existing values take precedence)
    return {**defaults, **limits}

def get_fee_rate(exchange: str, order_type: str = "taker") -> float:
    """Get fee rate for exchange"""
    limits = get_exchange_limits(exchange)
    return limits.get(f"fee_{order_type}", 0.0025)


def get_scalper_cap(exchange: str) -> int:
    """Get max scalper bots for an exchange."""
    return SCALPER_BOT_ALLOCATION.get(exchange.lower(), 2)


def get_normal_cap(exchange: str) -> int:
    """Get max normal bots for an exchange."""
    return BOT_ALLOCATION.get(exchange.lower(), 5)


def compute_scalper_ev(
    win_rate: float,
    tp_pct: float,
    sl_pct: float,
    entry_fee_pct: float,
    exit_fee_pct: float,
    spread_pct: float,
    slippage_pct: float,
) -> float:
    """
    Compute expected value for a scalper trade.

    EV = p*(tp - cost_rt) - (1-p)*(sl + cost_rt)
    where cost_rt = entry_fee + exit_fee + spread + slippage
    Returns EV in percentage of capital.
    """
    cost_rt = entry_fee_pct + exit_fee_pct + spread_pct + slippage_pct
    ev = win_rate * (tp_pct - cost_rt) - (1 - win_rate) * (sl_pct + cost_rt)
    return round(ev, 6)
