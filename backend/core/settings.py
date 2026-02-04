"""
ONE TRUTH Configuration Module
Single source of truth for all system settings, limits, and feature flags.
All modules MUST import from this module only.
"""

import os
from typing import Dict, List, Optional, Set
from pydantic import BaseSettings, Field, validator
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


class SystemSettings(BaseSettings):
    """
    System-wide settings loaded from environment variables.
    Uses Pydantic for validation and type safety.
    """
    
    # Database
    MONGO_URL: str = Field(default='mongodb://localhost:27017', env='MONGO_URL')
    DB_NAME: str = Field(default='amarktai_trading', env='DB_NAME')
    
    # Security
    JWT_SECRET: str = Field(default='your-secret-key-change-in-production', env='JWT_SECRET')
    ENCRYPTION_KEY: str = Field(default='', env='ENCRYPTION_KEY')
    AMARKTAI_FERNET_KEY: str = Field(default='', env='AMARKTAI_FERNET_KEY')
    FERNET_KEY: str = Field(default='', env='FERNET_KEY')
    
    # AI / OpenAI
    OPENAI_API_KEY: str = Field(default='', env='OPENAI_API_KEY')
    OPENAI_MODEL: str = Field(default='gpt-4o', env='OPENAI_MODEL')
    
    # Email (SMTP)
    SMTP_HOST: str = Field(default='smtp.gmail.com', env='SMTP_HOST')
    SMTP_PORT: int = Field(default=587, env='SMTP_PORT')
    SMTP_USER: str = Field(default='', env='SMTP_USER')
    SMTP_PASSWORD: str = Field(default='', env='SMTP_PASSWORD')
    FROM_EMAIL: str = Field(default='', env='FROM_EMAIL')
    FROM_NAME: str = Field(default='Amarktai Network', env='FROM_NAME')
    
    # Optional Integrations
    FETCHAI_API_KEY: str = Field(default='', env='FETCHAI_API_KEY')
    FLOKX_API_KEY: str = Field(default='', env='FLOKX_API_KEY')
    
    # Trading Limits
    MAX_TRADES_PER_BOT_PER_DAY: int = Field(default=1000, env='MAX_TRADES_PER_BOT_PER_DAY')
    MAX_TRADES_PER_USER_PER_DAY: int = Field(default=3000, env='MAX_TRADES_PER_USER_PER_DAY')
    MIN_TRADE_PROFIT_THRESHOLD_ZAR: float = Field(default=2.0)
    
    # Paper → Live Promotion Criteria
    PAPER_TRAINING_DAYS: int = Field(default=7, env='PAPER_TRAINING_DAYS')
    MIN_WIN_RATE: float = Field(default=0.52)
    MIN_PROFIT_PERCENT: float = Field(default=0.03)
    MIN_TRADES_FOR_PROMOTION: int = Field(default=25)
    
    # Live Training Bay
    LIVE_MIN_TRAINING_HOURS: int = Field(default=24, env='LIVE_MIN_TRAINING_HOURS')
    
    # Autopilot Settings - Bot Spawning & Reinvestment
    BOT_SPAWN_PROFIT_ZAR: int = Field(default=1000, env='BOT_SPAWN_PROFIT_ZAR')
    NEW_BOT_SEED_CAPITAL_ZAR: int = Field(default=500, env='NEW_BOT_SEED_CAPITAL_ZAR')
    REINVEST_THRESHOLD_ZAR: int = Field(default=300, env='REINVEST_THRESHOLD_ZAR')
    MAX_TOTAL_BOTS: int = Field(default=65, env='MAX_TOTAL_BOTS')
    TOP_PERFORMERS_COUNT: int = Field(default=3, env='TOP_PERFORMERS_COUNT')
    EVOLUTION_MUTATION_RATE: float = Field(default=0.25, env='EVOLUTION_MUTATION_RATE')
    QUARANTINE_THRESHOLD: float = Field(default=-0.05, env='QUARANTINE_THRESHOLD')
    
    # Per-exchange bot spawning
    ENABLE_PER_EXCHANGE_BOT_SPAWN: bool = Field(default=True, env='ENABLE_PER_EXCHANGE_BOT_SPAWN')
    ENABLE_OVERALL_PROFIT_THRESHOLD: bool = Field(default=False, env='ENABLE_OVERALL_PROFIT_THRESHOLD')
    OVERALL_PROFIT_THRESHOLD_ZAR: int = Field(default=5000, env='OVERALL_PROFIT_THRESHOLD_ZAR')
    
    # Risk Management
    STOP_LOSS_SAFE: float = Field(default=0.05)
    STOP_LOSS_BALANCED: float = Field(default=0.10)
    STOP_LOSS_AGGRESSIVE: float = Field(default=0.15)
    MAX_HOURLY_LOSS_PERCENT: float = Field(default=0.15)
    MAX_DAILY_LOSS_PERCENT: float = Field(default=0.15, env='MAX_DAILY_LOSS_PERCENT')
    MAX_DRAWDOWN_PERCENT: float = Field(default=0.25, env='MAX_DRAWDOWN_PERCENT')
    MIN_POSITION_SIZE_PERCENT: float = Field(default=0.02)
    MAX_POSITION_SIZE_PERCENT: float = Field(default=0.05)
    
    # Self-healing
    MAX_ERRORS_PER_HOUR: int = Field(default=20, env='MAX_ERRORS_PER_HOUR')
    
    # Wallet Transfer Limits & Security
    DAILY_WITHDRAWAL_LIMIT_USD: float = Field(default=10000, env='DAILY_WITHDRAWAL_LIMIT_USD')
    MONTHLY_WITHDRAWAL_LIMIT_USD: float = Field(default=100000, env='MONTHLY_WITHDRAWAL_LIMIT_USD')
    MAX_SINGLE_WITHDRAWAL_USD: float = Field(default=5000, env='MAX_SINGLE_WITHDRAWAL_USD')
    REQUIRE_EMAIL_CONFIRMATION: bool = Field(default=True, env='REQUIRE_EMAIL_CONFIRMATION')
    EMAIL_CONFIRMATION_TIMEOUT_HOURS: int = Field(default=24, env='EMAIL_CONFIRMATION_TIMEOUT_HOURS')
    REQUIRE_WHITELISTED_ADDRESS: bool = Field(default=True, env='REQUIRE_WHITELISTED_ADDRESS')
    MAX_WITHDRAWAL_ATTEMPTS_PER_HOUR: int = Field(default=5, env='MAX_WITHDRAWAL_ATTEMPTS_PER_HOUR')
    REQUIRE_2FA_FOR_WITHDRAWALS: bool = Field(default=False, env='REQUIRE_2FA_FOR_WITHDRAWALS')
    REQUIRE_ADMIN_APPROVAL_ABOVE_ZAR: float = Field(default=100000, env='REQUIRE_ADMIN_APPROVAL_ABOVE_ZAR')
    WALLET_MAX_TRANSFER_ZAR_PER_TX: float = Field(default=50000, env='WALLET_MAX_TRANSFER_ZAR_PER_TX')
    WALLET_MAX_TRANSFER_ZAR_PER_DAY: float = Field(default=200000, env='WALLET_MAX_TRANSFER_ZAR_PER_DAY')
    WALLET_MAX_TRANSFER_ZAR_PER_MONTH: float = Field(default=2000000, env='WALLET_MAX_TRANSFER_ZAR_PER_MONTH')
    REQUIRE_ADDRESS_WHITELIST: bool = Field(default=True, env='REQUIRE_ADDRESS_WHITELIST')
    MIN_RESERVE_LUNO_ZAR: float = Field(default=10000, env='MIN_RESERVE_LUNO_ZAR')
    MIN_RESERVE_PER_EXCHANGE_ZAR: float = Field(default=5000, env='MIN_RESERVE_PER_EXCHANGE_ZAR')
    
    # Live Trading Gate Requirements
    REQUIRE_WALLET_FUNDED: bool = Field(default=True, env='REQUIRE_WALLET_FUNDED')
    REQUIRE_API_KEYS_FOR_LIVE: bool = Field(default=True, env='REQUIRE_API_KEYS_FOR_LIVE')
    
    # AI Models Configuration
    AI_MODEL_SYSTEM_BRAIN: str = Field(default='gpt-4o', env='AI_MODEL_SYSTEM_BRAIN')
    AI_MODEL_TRADE_DECISION: str = Field(default='gpt-4o', env='AI_MODEL_TRADE_DECISION')
    AI_MODEL_REPORTING: str = Field(default='gpt-4', env='AI_MODEL_REPORTING')
    AI_MODEL_CHATOPS: str = Field(default='gpt-4o', env='AI_MODEL_CHATOPS')
    
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
    
    @validator('MAX_TOTAL_BOTS')
    def validate_bot_limit(cls, v):
        """Ensure MAX_TOTAL_BOTS matches sum of exchange allocations"""
        expected = sum(ExchangeLimits.BOT_ALLOCATION.values())
        if v != expected:
            raise ValueError(f"MAX_TOTAL_BOTS must equal {expected} (sum of exchange allocations)")
        return v
    
    class Config:
        env_file = '.env'
        case_sensitive = True


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
    
    for key, value in required_keys.items():
        if not value or value == 'your-secret-key-change-in-production':
            errors.append(f"❌ Missing or invalid required env key: {key}")
    
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
