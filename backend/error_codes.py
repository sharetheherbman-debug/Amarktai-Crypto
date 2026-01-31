"""
Standardized Error Codes for Amarktai Network
Provides clear, actionable error messages for all operations
"""

class ErrorCode:
    """Standardized error codes with clear messages"""
    
    # Bot Creation Errors
    INSUFFICIENT_FUNDS_EXCHANGE = {
        "code": "INSUFFICIENT_FUNDS_EXCHANGE",
        "message": "Insufficient funds on {exchange}. Required: R{required}, Available: R{available}",
        "action": "Please deposit funds or reduce bot capital",
        "severity": "error"
    }
    
    EXCHANGE_BOT_LIMIT_REACHED = {
        "code": "EXCHANGE_BOT_LIMIT_REACHED",
        "message": "Maximum bot limit reached for {exchange}. Current: {current}, Max: {max}",
        "action": "Delete inactive bots or upgrade your plan",
        "severity": "error"
    }
    
    INVALID_CAPITAL_AMOUNT = {
        "code": "INVALID_CAPITAL_AMOUNT",
        "message": "Invalid capital amount. Must be between R{min} and R{max}",
        "action": "Adjust capital amount within valid range",
        "severity": "error"
    }
    
    INVALID_EXCHANGE = {
        "code": "INVALID_EXCHANGE",
        "message": "Exchange '{exchange}' is not supported",
        "action": "Choose from: Luno, Binance, KuCoin, Bybit, Bitget",
        "severity": "error"
    }
    
    EXCHANGE_API_KEYS_MISSING = {
        "code": "EXCHANGE_API_KEYS_MISSING",
        "message": "No API keys configured for {exchange}",
        "action": "Add your {exchange} API keys in Settings → Exchange Keys",
        "severity": "error"
    }
    
    BOT_NAME_DUPLICATE = {
        "code": "BOT_NAME_DUPLICATE",
        "message": "Bot name '{name}' already exists",
        "action": "Choose a unique bot name",
        "severity": "error"
    }
    
    # Trading Errors
    INSUFFICIENT_BOT_CAPITAL = {
        "code": "INSUFFICIENT_BOT_CAPITAL",
        "message": "Bot has insufficient capital for trade. Capital: R{capital}, Required: R{required}",
        "action": "Bot will be paused. Add capital or adjust position size",
        "severity": "warning"
    }
    
    DAILY_TRADE_LIMIT_REACHED = {
        "code": "DAILY_TRADE_LIMIT_REACHED",
        "message": "Daily trade limit reached. Trades today: {current}, Max: {max}",
        "action": "Limit will reset at midnight UTC",
        "severity": "warning"
    }
    
    RISK_LIMIT_EXCEEDED = {
        "code": "RISK_LIMIT_EXCEEDED",
        "message": "Risk limit exceeded: {reason}",
        "action": "Reduce position size or wait for existing trades to close",
        "severity": "error"
    }
    
    MAX_EXPOSURE_EXCEEDED = {
        "code": "MAX_EXPOSURE_EXCEEDED",
        "message": "Maximum {asset} exposure exceeded. Current: {current}%, Max: {max}%",
        "action": "Close some {asset} positions before opening new ones",
        "severity": "error"
    }
    
    EMERGENCY_STOP_ACTIVE = {
        "code": "EMERGENCY_STOP_ACTIVE",
        "message": "Emergency stop is active. All trading paused",
        "action": "Disable emergency stop to resume trading",
        "severity": "critical"
    }
    
    # Order Errors
    MINIMUM_ORDER_SIZE = {
        "code": "MINIMUM_ORDER_SIZE",
        "message": "Order size below minimum. Size: {size}, Min: {min}",
        "action": "Increase position size or adjust bot capital",
        "severity": "error"
    }
    
    INVALID_ORDER_PRECISION = {
        "code": "INVALID_ORDER_PRECISION",
        "message": "Order amount precision invalid for {pair}. Precision: {precision}",
        "action": "System will auto-adjust. This is usually temporary",
        "severity": "warning"
    }
    
    RATE_LIMIT_EXCEEDED = {
        "code": "RATE_LIMIT_EXCEEDED",
        "message": "Exchange rate limit exceeded for {exchange}",
        "action": "Trading will auto-resume after cooldown period",
        "severity": "warning"
    }
    
    # Wallet & Funding Errors
    FUNDING_PLAN_REQUIRED = {
        "code": "FUNDING_PLAN_REQUIRED",
        "message": "Funding required: R{amount} to {exchange}",
        "action": "View funding plan in Wallet Hub",
        "severity": "info",
        "funding_plan_id": None  # Will be set dynamically
    }
    
    INSUFFICIENT_MASTER_WALLET = {
        "code": "INSUFFICIENT_MASTER_WALLET",
        "message": "Master Luno wallet has insufficient funds. Required: R{required}, Available: R{available}",
        "action": "Deposit funds to your Luno wallet",
        "severity": "error"
    }
    
    WITHDRAWAL_LIMIT_EXCEEDED = {
        "code": "WITHDRAWAL_LIMIT_EXCEEDED",
        "message": "Daily withdrawal limit exceeded. Amount: R{amount}, Limit: R{limit}",
        "action": "Try again tomorrow or contact support for higher limits",
        "severity": "error"
    }
    
    # System Errors
    DATABASE_ERROR = {
        "code": "DATABASE_ERROR",
        "message": "Database operation failed",
        "action": "Please try again. Contact support if issue persists",
        "severity": "critical"
    }
    
    EXCHANGE_CONNECTION_ERROR = {
        "code": "EXCHANGE_CONNECTION_ERROR",
        "message": "Cannot connect to {exchange}",
        "action": "Check exchange status. Trading will auto-resume when connection restored",
        "severity": "warning"
    }
    
    VALIDATION_ERROR = {
        "code": "VALIDATION_ERROR",
        "message": "Validation failed: {details}",
        "action": "Check your input and try again",
        "severity": "error"
    }
    
    @staticmethod
    def format_error(error_template: dict, **kwargs) -> dict:
        """
        Format an error with dynamic values
        
        Usage:
            error = ErrorCode.format_error(
                ErrorCode.INSUFFICIENT_FUNDS_EXCHANGE,
                exchange="Binance",
                required=1000,
                available=500
            )
        """
        formatted = error_template.copy()
        
        # Format message with kwargs
        formatted['message'] = formatted['message'].format(**kwargs)
        
        # Format action if it contains placeholders
        if '{' in formatted.get('action', ''):
            formatted['action'] = formatted['action'].format(**kwargs)
        
        # Add any extra fields from kwargs
        for key, value in kwargs.items():
            if key not in formatted:
                formatted[key] = value
        
        return formatted

# Convenience functions for common errors
def insufficient_funds_error(exchange: str, required: float, available: float) -> dict:
    return ErrorCode.format_error(
        ErrorCode.INSUFFICIENT_FUNDS_EXCHANGE,
        exchange=exchange,
        required=required,
        available=available
    )

def funding_plan_error(amount: float, exchange: str, plan_id: str) -> dict:
    error = ErrorCode.format_error(
        ErrorCode.FUNDING_PLAN_REQUIRED,
        amount=amount,
        exchange=exchange
    )
    error['funding_plan_id'] = plan_id
    return error

def daily_limit_error(current: int, max: int) -> dict:
    return ErrorCode.format_error(
        ErrorCode.DAILY_TRADE_LIMIT_REACHED,
        current=current,
        max=max
    )
