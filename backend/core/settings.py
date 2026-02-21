"""
ONE TRUTH Configuration Module
Single source of truth for all system settings, limits, and feature flags.
All modules MUST import from this module only.
"""

import os
from typing import Dict, List, Optional, Set
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


# ============================================================================
# SUPPORTED EXCHANGES - EXACTLY 7 PLATFORMS (IMMUTABLE)
# ============================================================================
SUPPORTED_EXCHANGES: List[str] = [
    'luno',
    'binance', 
    'kucoin',
    'bybit',
    'kraken',
    'bitget',
    'gate'
]

# Frozen set for fast lookup
SUPPORTED_EXCHANGES_SET: Set[str] = frozenset(SUPPORTED_EXCHANGES)


class ExchangeLimits:
    """Exchange-specific rate limits and trading constraints"""
    
    # Bot allocation per exchange
    BOT_ALLOCATION: Dict[str, int] = {
        "luno": 5,
        "binance": 10,
        "kucoin": 10,
        "bybit": 10,
        "kraken": 10,
        "bitget": 10,
        "gate": 10
    }
    
    # Total global bot limit
    MAX_BOTS_GLOBAL: int = 65  # Sum of all allocations
    
    # Per-exchange trading limits
    EXCHANGE_LIMITS: Dict[str, Dict] = {
        "luno": {
            "max_bots": 5,
            "trades_per_bot_day": 400,
            "total_trades_day": 2000,
            "max_orders_per_day": 2000,
            "max_orders_per_bot_per_day": 400,
            "max_orders_per_minute": 60,
            "max_orders_per_10_seconds": 10,
            "fee_maker": 0.002,
            "fee_taker": 0.0025,
        },
        "binance": {
            "max_bots": 10,
            "trades_per_bot_day": 500,
            "total_trades_day": 5000,
            "max_orders_per_day": 5000,
            "max_orders_per_bot_per_day": 500,
            "max_orders_per_minute": 60,
            "max_orders_per_10_seconds": 10,
            "fee_maker": 0.001,
            "fee_taker": 0.001,
        },
        "kucoin": {
            "max_bots": 10,
            "trades_per_bot_day": 1000,
            "total_trades_day": 10000,
            "max_orders_per_day": 10000,
            "max_orders_per_bot_per_day": 1000,
            "max_orders_per_minute": 60,
            "max_orders_per_10_seconds": 10,
            "fee_maker": 0.001,
            "fee_taker": 0.001,
        },
        "bybit": {
            "max_bots": 10,
            "trades_per_bot_day": 800,
            "total_trades_day": 8000,
            "max_orders_per_day": 8000,
            "max_orders_per_bot_per_day": 800,
            "max_orders_per_minute": 60,
            "max_orders_per_10_seconds": 10,
            "fee_maker": 0.001,
            "fee_taker": 0.001,
        },
        "bitget": {
            "max_bots": 10,
            "trades_per_bot_day": 800,
            "total_trades_day": 8000,
            "max_orders_per_day": 8000,
            "max_orders_per_bot_per_day": 800,
            "max_orders_per_minute": 60,
            "max_orders_per_10_seconds": 10,
            "fee_maker": 0.001,
            "fee_taker": 0.001,
        },
        "kraken": {
            "max_bots": 10,
            "trades_per_bot_day": 800,
            "total_trades_day": 8000,
            "max_orders_per_day": 8000,
            "max_orders_per_bot_per_day": 800,
            "max_orders_per_minute": 60,
            "max_orders_per_10_seconds": 10,
            "fee_maker": 0.0016,
            "fee_taker": 0.0026,
        },
        "gate": {
            "max_bots": 10,
            "trades_per_bot_day": 800,
            "total_trades_day": 8000,
            "max_orders_per_day": 8000,
            "max_orders_per_bot_per_day": 800,
            "max_orders_per_minute": 60,
            "max_orders_per_10_seconds": 10,
            "fee_maker": 0.002,
            "fee_taker": 0.002,
        },
    }
    
    @classmethod
    def get_limits(cls, exchange: str) -> Dict:
        """Get limits for exchange with safe defaults"""
        exchange = exchange.lower()
        if exchange not in cls.EXCHANGE_LIMITS:
            # Return conservative defaults for unknown exchange
            return {
                "max_orders_per_day": 2000,
                "max_orders_per_bot_per_day": 400,
                "max_orders_per_minute": 60,
                "max_orders_per_10_seconds": 10,
                "fee_maker": 0.001,
                "fee_taker": 0.001,
            }
        return cls.EXCHANGE_LIMITS[exchange]
    
    @classmethod
    def get_fee_rate(cls, exchange: str, order_type: str = "taker") -> float:
        """Get fee rate for exchange"""
        limits = cls.get_limits(exchange)
        return limits.get(f"fee_{order_type}", 0.0025)


class FeatureFlags:
    """Feature flags controlling system behavior"""
    
    # Trading Feature Flags
    ENABLE_TRADING: bool = os.getenv('ENABLE_TRADING', 'true').lower() == 'true'
    ENABLE_PAPER_TRADING: bool = os.getenv('ENABLE_PAPER_TRADING', 'true').lower() == 'true'
    ENABLE_LIVE_TRADING: bool = os.getenv('ENABLE_LIVE_TRADING', 'false').lower() == 'true'
    ENABLE_AUTOPILOT: bool = os.getenv('ENABLE_AUTOPILOT', 'true').lower() == 'true'
    
    # System Features
    ENABLE_BODYGUARD: bool = os.getenv('ENABLE_BODYGUARD', 'true').lower() == 'true'
    ENABLE_REALTIME: bool = os.getenv('ENABLE_REALTIME', 'true').lower() == 'true'
    ENABLE_SELF_LEARNING: bool = os.getenv('ENABLE_SELF_LEARNING', 'true').lower() == 'true'
    ENABLE_SELF_HEALING: bool = os.getenv('ENABLE_SELF_HEALING', 'true').lower() == 'true'
    ENABLE_CCXT: bool = os.getenv('ENABLE_CCXT', 'true').lower() == 'true'
    ENABLE_SCHEDULERS: bool = os.getenv('ENABLE_SCHEDULERS', 'true').lower() == 'true'
    
    # Optional Integrations
    ENABLE_UAGENTS: bool = os.getenv('ENABLE_UAGENTS', 'false').lower() == 'true'
    PAYMENT_AGENT_ENABLED: bool = os.getenv('PAYMENT_AGENT_ENABLED', 'false').lower() == 'true'
    ENABLE_REALTIME_TRANSFERS: bool = os.getenv('ENABLE_REALTIME_TRANSFERS', 'false').lower() == 'true'
    
    # Email Feature Flags
    ENABLE_EMAIL_REPORTS: bool = os.getenv('ENABLE_EMAIL_REPORTS', 'true').lower() == 'true'
    REPORT_TIMES: str = os.getenv('REPORT_TIMES', '08:00,18:00')
    
    @classmethod
    def to_dict(cls) -> Dict[str, bool]:
        """Export all feature flags as dict"""
        return {
            'ENABLE_TRADING': cls.ENABLE_TRADING,
            'ENABLE_PAPER_TRADING': cls.ENABLE_PAPER_TRADING,
            'ENABLE_LIVE_TRADING': cls.ENABLE_LIVE_TRADING,
            'ENABLE_AUTOPILOT': cls.ENABLE_AUTOPILOT,
            'ENABLE_BODYGUARD': cls.ENABLE_BODYGUARD,
            'ENABLE_REALTIME': cls.ENABLE_REALTIME,
            'ENABLE_SELF_LEARNING': cls.ENABLE_SELF_LEARNING,
            'ENABLE_SELF_HEALING': cls.ENABLE_SELF_HEALING,
            'ENABLE_CCXT': cls.ENABLE_CCXT,
            'ENABLE_SCHEDULERS': cls.ENABLE_SCHEDULERS,
            'ENABLE_UAGENTS': cls.ENABLE_UAGENTS,
            'PAYMENT_AGENT_ENABLED': cls.PAYMENT_AGENT_ENABLED,
            'ENABLE_REALTIME_TRANSFERS': cls.ENABLE_REALTIME_TRANSFERS,
            'ENABLE_EMAIL_REPORTS': cls.ENABLE_EMAIL_REPORTS,
        }


class SystemSettings:
    """
    System-wide settings loaded from environment variables.
    Simple wrapper around os.getenv with type conversion and defaults.
    """
    
    def __init__(self):
        # Database
        self.MONGO_URL = os.getenv('MONGO_URL', 'mongodb://localhost:27017')
        self.DB_NAME = os.getenv('DB_NAME', 'amarktai_trading')
        
        # Security
        self.JWT_SECRET = os.getenv('JWT_SECRET', 'your-secret-key-change-in-production')
        self.ENCRYPTION_KEY = os.getenv('ENCRYPTION_KEY', '')
        self.AMARKTAI_FERNET_KEY = os.getenv('AMARKTAI_FERNET_KEY', '')
        self.FERNET_KEY = os.getenv('FERNET_KEY', '')
        
        # AI / OpenAI
        self.OPENAI_API_KEY = os.getenv('OPENAI_API_KEY', '')
        self.OPENAI_MODEL = os.getenv('OPENAI_MODEL', 'gpt-4o')
        
        # Email (SMTP)
        self.SMTP_HOST = os.getenv('SMTP_HOST', 'smtp.gmail.com')
        self.SMTP_PORT = int(os.getenv('SMTP_PORT', '587'))
        self.SMTP_USER = os.getenv('SMTP_USER', '')
        self.SMTP_PASSWORD = os.getenv('SMTP_PASSWORD', '')
        self.FROM_EMAIL = os.getenv('FROM_EMAIL', '')
        self.FROM_NAME = os.getenv('FROM_NAME', 'Amarktai Network')
        
        # Optional Integrations
        self.FETCHAI_API_KEY = os.getenv('FETCHAI_API_KEY', '')
        self.FLOKX_API_KEY = os.getenv('FLOKX_API_KEY', '')
        
        # Trading Limits
        self.MAX_TRADES_PER_BOT_PER_DAY = int(os.getenv('MAX_TRADES_PER_BOT_PER_DAY', '1000'))
        self.MAX_TRADES_PER_USER_PER_DAY = int(os.getenv('MAX_TRADES_PER_USER_PER_DAY', '3000'))
        self.MIN_TRADE_PROFIT_THRESHOLD_ZAR = float(os.getenv('MIN_TRADE_PROFIT_THRESHOLD_ZAR', '2.0'))
        
        # Paper → Live Promotion Criteria
        self.PAPER_TRAINING_DAYS = int(os.getenv('PAPER_TRAINING_DAYS', '7'))
        self.MIN_WIN_RATE = float(os.getenv('MIN_WIN_RATE', '0.52'))
        self.MIN_PROFIT_PERCENT = float(os.getenv('MIN_PROFIT_PERCENT', '0.03'))
        self.MIN_TRADES_FOR_PROMOTION = int(os.getenv('MIN_TRADES_FOR_PROMOTION', '25'))
        
        # Live Training Bay
        self.LIVE_MIN_TRAINING_HOURS = int(os.getenv('LIVE_MIN_TRAINING_HOURS', '24'))
        
        # Autopilot Settings - Bot Spawning & Reinvestment
        self.BOT_SPAWN_PROFIT_ZAR = int(os.getenv('BOT_SPAWN_PROFIT_ZAR', '1000'))
        self.NEW_BOT_SEED_CAPITAL_ZAR = int(os.getenv('NEW_BOT_SEED_CAPITAL_ZAR', '500'))
        self.REINVEST_THRESHOLD_ZAR = int(os.getenv('REINVEST_THRESHOLD_ZAR', '300'))
        self.MAX_TOTAL_BOTS = int(os.getenv('MAX_TOTAL_BOTS', '65'))
        self.TOP_PERFORMERS_COUNT = int(os.getenv('TOP_PERFORMERS_COUNT', '3'))
        self.EVOLUTION_MUTATION_RATE = float(os.getenv('EVOLUTION_MUTATION_RATE', '0.25'))
        self.QUARANTINE_THRESHOLD = float(os.getenv('QUARANTINE_THRESHOLD', '-0.05'))
        
        # Per-exchange bot spawning
        self.ENABLE_PER_EXCHANGE_BOT_SPAWN = os.getenv('ENABLE_PER_EXCHANGE_BOT_SPAWN', 'true').lower() == 'true'
        self.ENABLE_OVERALL_PROFIT_THRESHOLD = os.getenv('ENABLE_OVERALL_PROFIT_THRESHOLD', 'false').lower() == 'true'
        self.OVERALL_PROFIT_THRESHOLD_ZAR = int(os.getenv('OVERALL_PROFIT_THRESHOLD_ZAR', '5000'))
        
        # Risk Management
        self.STOP_LOSS_SAFE = float(os.getenv('STOP_LOSS_SAFE', '0.05'))
        self.STOP_LOSS_BALANCED = float(os.getenv('STOP_LOSS_BALANCED', '0.10'))
        self.STOP_LOSS_AGGRESSIVE = float(os.getenv('STOP_LOSS_AGGRESSIVE', '0.15'))
        self.MAX_HOURLY_LOSS_PERCENT = float(os.getenv('MAX_HOURLY_LOSS_PERCENT', '0.15'))
        self.MAX_DAILY_LOSS_PERCENT = float(os.getenv('MAX_DAILY_LOSS_PERCENT', '0.15'))
        self.MAX_DRAWDOWN_PERCENT = float(os.getenv('MAX_DRAWDOWN_PERCENT', '0.25'))
        self.MIN_POSITION_SIZE_PERCENT = float(os.getenv('MIN_POSITION_SIZE_PERCENT', '0.02'))
        self.MAX_POSITION_SIZE_PERCENT = float(os.getenv('MAX_POSITION_SIZE_PERCENT', '0.05'))
        
        # Self-healing
        self.MAX_ERRORS_PER_HOUR = int(os.getenv('MAX_ERRORS_PER_HOUR', '20'))
        
        # Wallet Transfer Limits & Security
        self.DAILY_WITHDRAWAL_LIMIT_USD = float(os.getenv('DAILY_WITHDRAWAL_LIMIT_USD', '10000'))
        self.MONTHLY_WITHDRAWAL_LIMIT_USD = float(os.getenv('MONTHLY_WITHDRAWAL_LIMIT_USD', '100000'))
        self.MAX_SINGLE_WITHDRAWAL_USD = float(os.getenv('MAX_SINGLE_WITHDRAWAL_USD', '5000'))
        self.REQUIRE_EMAIL_CONFIRMATION = os.getenv('REQUIRE_EMAIL_CONFIRMATION', 'true').lower() == 'true'
        self.EMAIL_CONFIRMATION_TIMEOUT_HOURS = int(os.getenv('EMAIL_CONFIRMATION_TIMEOUT_HOURS', '24'))
        self.REQUIRE_WHITELISTED_ADDRESS = os.getenv('REQUIRE_WHITELISTED_ADDRESS', 'true').lower() == 'true'
        self.MAX_WITHDRAWAL_ATTEMPTS_PER_HOUR = int(os.getenv('MAX_WITHDRAWAL_ATTEMPTS_PER_HOUR', '5'))
        self.REQUIRE_2FA_FOR_WITHDRAWALS = os.getenv('REQUIRE_2FA_FOR_WITHDRAWALS', 'false').lower() == 'true'
        self.REQUIRE_ADMIN_APPROVAL_ABOVE_ZAR = float(os.getenv('REQUIRE_ADMIN_APPROVAL_ABOVE_ZAR', '100000'))
        self.WALLET_MAX_TRANSFER_ZAR_PER_TX = float(os.getenv('WALLET_MAX_TRANSFER_ZAR_PER_TX', '50000'))
        self.WALLET_MAX_TRANSFER_ZAR_PER_DAY = float(os.getenv('WALLET_MAX_TRANSFER_ZAR_PER_DAY', '200000'))
        self.WALLET_MAX_TRANSFER_ZAR_PER_MONTH = float(os.getenv('WALLET_MAX_TRANSFER_ZAR_PER_MONTH', '2000000'))
        self.REQUIRE_ADDRESS_WHITELIST = os.getenv('REQUIRE_ADDRESS_WHITELIST', 'true').lower() == 'true'
        self.MIN_RESERVE_LUNO_ZAR = float(os.getenv('MIN_RESERVE_LUNO_ZAR', '10000'))
        self.MIN_RESERVE_PER_EXCHANGE_ZAR = float(os.getenv('MIN_RESERVE_PER_EXCHANGE_ZAR', '5000'))
        
        # Live Trading Gate Requirements
        self.REQUIRE_WALLET_FUNDED = os.getenv('REQUIRE_WALLET_FUNDED', 'true').lower() == 'true'
        self.REQUIRE_API_KEYS_FOR_LIVE = os.getenv('REQUIRE_API_KEYS_FOR_LIVE', 'true').lower() == 'true'
        
        # AI Models Configuration
        self.AI_MODEL_SYSTEM_BRAIN = os.getenv('AI_MODEL_SYSTEM_BRAIN', 'gpt-4o')
        self.AI_MODEL_TRADE_DECISION = os.getenv('AI_MODEL_TRADE_DECISION', 'gpt-4o')
        self.AI_MODEL_REPORTING = os.getenv('AI_MODEL_REPORTING', 'gpt-4')
        self.AI_MODEL_CHATOPS = os.getenv('AI_MODEL_CHATOPS', 'gpt-4o')
        
        # Validate bot limit
        expected = sum(ExchangeLimits.BOT_ALLOCATION.values())
        if self.MAX_TOTAL_BOTS != expected:
            raise ValueError(
                f"MAX_TOTAL_BOTS ({self.MAX_TOTAL_BOTS}) must equal {expected} "
                f"(sum of exchange allocations: {dict(ExchangeLimits.BOT_ALLOCATION)})"
            )
    
    @property
    def active_encryption_key(self) -> str:
        """Return first available encryption key"""
        return self.AMARKTAI_FERNET_KEY or self.FERNET_KEY or self.ENCRYPTION_KEY
    
    @property
    def from_email_address(self) -> str:
        """Return FROM_EMAIL or fallback to SMTP_USER"""
        return self.FROM_EMAIL or self.SMTP_USER
    
    @property
    def ai_models(self) -> Dict[str, str]:
        """Get AI model configuration"""
        return {
            'system_brain': self.AI_MODEL_SYSTEM_BRAIN,
            'trade_decision': self.AI_MODEL_TRADE_DECISION,
            'reporting': self.AI_MODEL_REPORTING,
            'chatops': self.AI_MODEL_CHATOPS,
        }


# Singleton instance
settings = SystemSettings()


# ============================================================================
# STARTUP VALIDATION & SELF-CHECK
# ============================================================================

def validate_exchange(exchange: str) -> bool:
    """Validate that exchange is in approved list"""
    return exchange.lower() in SUPPORTED_EXCHANGES_SET


def startup_self_check() -> None:
    """
    Startup self-check - fails fast with clear errors
    Called on application startup to validate configuration
    """
    errors = []
    
    # Check 1: Required environment keys
    required_keys = {
        'MONGO_URL': settings.MONGO_URL,
        'JWT_SECRET': settings.JWT_SECRET,
        'ENCRYPTION_KEY': settings.active_encryption_key,
    }
    
    _WEAK_SECRETS = {"your-secret-key", "secret", "change-me", "changeme",
                     "your-secret-key-change-in-production"}
    environment = os.getenv("ENVIRONMENT", "").lower()
    for key, value in required_keys.items():
        if not value:
            errors.append(f"❌ Missing required env key: {key}")
        elif key == 'JWT_SECRET' and (len(value) < 32 or value in _WEAK_SECRETS):
            msg = (
                f"❌ JWT_SECRET is too weak (length {len(value)} < 32) or uses a known default. "
                "Set a strong random secret of at least 32 characters."
            )
            if environment == "production":
                errors.append(msg)
            else:
                print(f"⚠️  Warning: {msg}")
        elif key != 'JWT_SECRET' and value in _WEAK_SECRETS:
            errors.append(f"❌ {key} is using a known-insecure default value")
    
    # Check 2: Exchange limits consistency
    for exchange in SUPPORTED_EXCHANGES:
        limits = ExchangeLimits.get_limits(exchange)
        bot_limit = ExchangeLimits.BOT_ALLOCATION.get(exchange, 0)
        
        if limits['max_bots'] != bot_limit:
            errors.append(
                f"❌ Inconsistent bot limits for {exchange}: "
                f"EXCHANGE_LIMITS={limits['max_bots']} vs BOT_ALLOCATION={bot_limit}"
            )
    
    # Check 3: Total bot capacity
    total_capacity = sum(ExchangeLimits.BOT_ALLOCATION.values())
    if total_capacity != settings.MAX_TOTAL_BOTS:
        errors.append(
            f"❌ MAX_TOTAL_BOTS ({settings.MAX_TOTAL_BOTS}) != "
            f"sum of BOT_ALLOCATION ({total_capacity})"
        )
    
    # Check 4: Email configuration (warning only)
    if FeatureFlags.ENABLE_EMAIL_REPORTS:
        if not settings.SMTP_USER or not settings.SMTP_PASSWORD:
            print("⚠️  Warning: Email reports enabled but SMTP credentials missing")
    
    # Check 5: Trading gates
    if FeatureFlags.ENABLE_LIVE_TRADING:
        if not (FeatureFlags.ENABLE_PAPER_TRADING or FeatureFlags.ENABLE_TRADING):
            errors.append("❌ ENABLE_LIVE_TRADING=true requires ENABLE_TRADING=true")
        if not FeatureFlags.ENABLE_AUTOPILOT:
            print("⚠️  Warning: ENABLE_LIVE_TRADING=true but ENABLE_AUTOPILOT=false")
    
    # Fail fast if errors found
    if errors:
        error_message = "\n".join(["🔥 Configuration validation failed:"] + errors)
        raise RuntimeError(error_message)
    
    # Success message
    print("✅ Configuration validation passed")
    print(f"✅ Supported exchanges: {', '.join(SUPPORTED_EXCHANGES)}")
    print(f"✅ Total bot capacity: {settings.MAX_TOTAL_BOTS}")
    print(f"✅ Feature flags loaded: {len(FeatureFlags.to_dict())} flags")


def get_system_info() -> Dict:
    """Get system configuration summary (non-sensitive)"""
    return {
        'supported_exchanges': SUPPORTED_EXCHANGES,
        'total_bot_capacity': settings.MAX_TOTAL_BOTS,
        'bot_allocation': ExchangeLimits.BOT_ALLOCATION,
        'feature_flags': FeatureFlags.to_dict(),
        'trading_enabled': FeatureFlags.ENABLE_TRADING,
        'paper_trading_enabled': FeatureFlags.ENABLE_PAPER_TRADING,
        'live_trading_enabled': FeatureFlags.ENABLE_LIVE_TRADING,
        'autopilot_enabled': FeatureFlags.ENABLE_AUTOPILOT,
        'email_reports_enabled': FeatureFlags.ENABLE_EMAIL_REPORTS,
        'spawn_threshold_zar': settings.BOT_SPAWN_PROFIT_ZAR,
        'reinvest_threshold_zar': settings.REINVEST_THRESHOLD_ZAR,
    }


# Export public API
__all__ = [
    'settings',
    'SUPPORTED_EXCHANGES',
    'SUPPORTED_EXCHANGES_SET',
    'ExchangeLimits',
    'FeatureFlags',
    'SystemSettings',
    'validate_exchange',
    'startup_self_check',
    'get_system_info',
]
