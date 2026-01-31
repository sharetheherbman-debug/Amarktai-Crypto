"""Exchange rate limits and caps for safe trading"""

"""
Exchange Rate Limits - Production Requirements

REQUIREMENTS PER EXCHANGE:
- Luno: 5 bots max, 400 trades/bot/day, 2,000 total/day
- Binance: 10 bots max, 500 trades/bot/day, 5,000 total/day  
- KuCoin: 10 bots max, 1,000 trades/bot/day, 10,000 total/day
- Bybit: 10 bots max, 800 trades/bot/day, 8,000 total/day
- Kraken: 10 bots max, 600 trades/bot/day, 6,000 total/day
- Bitget: 10 bots max, 800 trades/bot/day, 8,000 total/day
- Gate.io: 10 bots max, 1,000 trades/bot/day, 10,000 total/day

GLOBAL LIMIT: 65 bots total across all exchanges

These limits ensure:
- Safe operation within exchange API limits
- Realistic paper trading that mirrors live constraints
- Proper throttling and rate limiting
"""

# GLOBAL LIMIT: 65 bots total across all exchanges
MAX_BOTS_GLOBAL = 65

# Bot allocation per exchange
BOT_ALLOCATION = {
    "luno": 5,
    "binance": 10,
    "kucoin": 10,
    "bybit": 10,
    "kraken": 10,
    "bitget": 10,
    "gate": 10
}

EXCHANGE_LIMITS = {
    "luno": {
        "max_bots": 5,
        "trades_per_bot_day": 400,
        "total_trades_day": 2000,  # 5 bots × 400
        "max_orders_per_minute": 60,
        "max_orders_per_10_seconds": 10,
        "fee_maker": 0.002,  # 0.2%
        "fee_taker": 0.0025,  # 0.25%
    },
    "binance": {
        "max_bots": 10,
        "trades_per_bot_day": 500,
        "total_trades_day": 5000,  # 10 bots × 500
        "max_orders_per_minute": 60,
        "max_orders_per_10_seconds": 10,
        "fee_maker": 0.001,  # 0.1%
        "fee_taker": 0.001,  # 0.1%
    },
    "kucoin": {
        "max_bots": 10,
        "trades_per_bot_day": 1000,
        "total_trades_day": 10000,  # 10 bots × 1,000
        "max_orders_per_minute": 60,
        "max_orders_per_10_seconds": 10,
        "fee_maker": 0.001,  # 0.1%
        "fee_taker": 0.001,  # 0.1%
    },
    "bybit": {
        "max_bots": 10,
        "trades_per_bot_day": 800,
        "total_trades_day": 8000,  # 10 bots × 800
        "max_orders_per_minute": 60,
        "max_orders_per_10_seconds": 10,
        "fee_maker": 0.001,  # 0.1%
        "fee_taker": 0.001,  # 0.1%
    },
    "kraken": {
        "max_bots": 10,
        "trades_per_bot_day": 600,
        "total_trades_day": 6000,  # 10 bots × 600
        "max_orders_per_minute": 60,
        "max_orders_per_10_seconds": 10,
        "fee_maker": 0.0016,  # 0.16%
        "fee_taker": 0.0026,  # 0.26%
    },
    "bitget": {
        "max_bots": 10,
        "trades_per_bot_day": 800,
        "total_trades_day": 8000,  # 10 bots × 800
        "max_orders_per_minute": 60,
        "max_orders_per_10_seconds": 10,
        "fee_maker": 0.001,  # 0.1%
        "fee_taker": 0.001,  # 0.1%
    },
    "gate": {
        "max_bots": 10,
        "trades_per_bot_day": 1000,
        "total_trades_day": 10000,  # 10 bots × 1,000
        "max_orders_per_minute": 60,
        "max_orders_per_10_seconds": 10,
        "fee_maker": 0.002,  # 0.2%
        "fee_taker": 0.002,  # 0.2%
    },
}

def get_exchange_limits(exchange: str) -> dict:
    """Get limits for an exchange"""
    return EXCHANGE_LIMITS.get(exchange.lower(), EXCHANGE_LIMITS["luno"])

def get_fee_rate(exchange: str, order_type: str = "taker") -> float:
    """Get fee rate for exchange"""
    limits = get_exchange_limits(exchange)
    return limits.get(f"fee_{order_type}", 0.0025)
