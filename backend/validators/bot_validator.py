"""
Bot Creation Validator
Validates all bot creation parameters before database insertion
Uses canonical platform registry
"""

import asyncio
from typing import Dict, Tuple
from datetime import datetime, timezone
import logging

import database as db
from error_codes import ErrorCode, insufficient_funds_error
from engines.wallet_manager import wallet_manager
from services.paper_wallet_service import paper_wallet_service
from services.fx_normalizer import resolve_capital_for_exchange
from config.platforms import (
    is_valid_platform,
    get_max_bots,
    validate_platform_for_mode,
    normalize_platform_id,
    SUPPORTED_PLATFORMS,
    TOTAL_BOT_CAPACITY
)
from exchange_limits import get_scalper_cap, get_normal_cap, MAX_SCALPER_BOTS_GLOBAL

logger = logging.getLogger(__name__)


def _safe_int_cap(value, fallback: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(fallback)


    """Validates bot creation parameters"""
    
    def __init__(self):
        # Use canonical platform configuration
        self.supported_exchanges = SUPPORTED_PLATFORMS
        self.min_capital = 100  # R100 minimum
        self.max_capital = 100000  # R100,000 maximum
        self.max_bots_total = TOTAL_BOT_CAPACITY
    
    async def validate_bot_creation(self, user_id: str, bot_data: Dict) -> Tuple[bool, Dict]:
        """
        Validate all bot creation parameters
        
        Returns:
            (is_valid, error_or_data)
            If valid: (True, validated_data)
            If invalid: (False, error_dict)
        """
        
        # 1. Validate exchange using canonical registry
        exchange_raw = bot_data.get('exchange', '')
        exchange = normalize_platform_id(exchange_raw)
        
        if not is_valid_platform(exchange):
            return False, ErrorCode.format_error(
                ErrorCode.INVALID_EXCHANGE,
                exchange=exchange_raw
            )
        
        # Normalize exchange in bot data
        bot_data['exchange'] = exchange
        
        # 2. Validate trading mode for platform
        trading_mode = bot_data.get('trading_mode', 'paper')
        is_mode_valid, mode_error = validate_platform_for_mode(exchange, trading_mode)
        if not is_mode_valid:
            return False, ErrorCode.format_error(
                ErrorCode.VALIDATION_ERROR,
                details=mode_error
            )
        
        # 3. Validate capital amount
        capital = bot_data.get('capital', 0)
        if capital < self.min_capital or capital > self.max_capital:
            return False, ErrorCode.format_error(
                ErrorCode.INVALID_CAPITAL_AMOUNT,
                min=self.min_capital,
                max=self.max_capital
            )
        
        # 4. Check bot name uniqueness
        name = bot_data.get('name', '').strip()
        if not name:
            return False, ErrorCode.format_error(
                ErrorCode.VALIDATION_ERROR,
                details="Bot name is required"
            )
        
        existing_bot = await db.bots_collection.find_one({
            "user_id": user_id,
            "name": name,
            "status": {"$ne": "deleted"},
            "deleted": {"$ne": True},
            "deleted_at": {"$exists": False}
        }, {"_id": 0})
        
        if existing_bot:
            return False, ErrorCode.format_error(
                ErrorCode.BOT_NAME_DUPLICATE,
                name=name
            )
        
        # 5. Check exchange bot limit using canonical config
        exchange_bot_count = await db.bots_collection.count_documents({
            "user_id": user_id,
            "exchange": exchange,
            "status": {"$ne": "deleted"},
            "deleted": {"$ne": True},
            "deleted_at": {"$exists": False}
        })
        
        max_for_exchange = get_max_bots(exchange)
        if exchange_bot_count >= max_for_exchange:
            return False, ErrorCode.format_error(
                ErrorCode.EXCHANGE_BOT_LIMIT_REACHED,
                exchange=exchange.capitalize(),
                current=exchange_bot_count,
                max=max_for_exchange
            )
        
        # 6. Check total bot limit
        total_bots = await db.bots_collection.count_documents({
            "user_id": user_id,
            "status": {"$ne": "deleted"},
            "deleted": {"$ne": True},
            "deleted_at": {"$exists": False}
        })
        if total_bots >= self.max_bots_total:
            return False, {
                "code": "TOTAL_BOT_LIMIT_REACHED",
                "message": f"Maximum total bot limit reached. Current: {total_bots}, Max: {self.max_bots_total}",
                "action": "Delete inactive bots to create new ones",
                "severity": "error"
            }
        
        # 6. Check API keys for exchange - ONLY required for LIVE trading
        # Paper mode uses real market data but fake money, no API keys needed
        trading_mode = bot_data.get('trading_mode', 'paper').lower()
        
        if trading_mode == 'live':
            api_key_doc = await db.api_keys_collection.find_one({
                "user_id": user_id,
                "exchange": exchange
            }, {"_id": 0})
            
            if not api_key_doc:
                return False, ErrorCode.format_error(
                    ErrorCode.EXCHANGE_API_KEYS_MISSING,
                    exchange=exchange.capitalize()
                )
        else:
            # Paper mode - no API keys required, just log
            logger.info(f"Paper mode bot creation for {exchange} - API keys not required")
        
        # 7. Check available balance on exchange - ONLY for LIVE trading
        # Paper mode uses virtual capital, no real balance needed
        if trading_mode == 'live':
            balance_result = await wallet_manager.get_exchange_balance(user_id, exchange)
            
            if balance_result.get('error'):
                # If balance check fails, allow creation but warn
                logger.warning(f"Balance check failed for {exchange}: {balance_result.get('error')}")
            else:
                available = balance_result.get('zar_balance', 0)
                if available < capital:
                    # Create funding plan
                    from engines.funding_plan_manager import funding_plan_manager
                    
                    plan = await funding_plan_manager.create_funding_plan(
                        user_id=user_id,
                        target_exchange=exchange,
                        required_amount=capital,
                        reason="Bot creation",
                        bot_name=name
                    )
                    
                    error = ErrorCode.format_error(
                        ErrorCode.FUNDING_PLAN_REQUIRED,
                        amount=capital - available,
                        exchange=exchange.capitalize()
                    )
                    error['funding_plan_id'] = plan.get('plan_id')
                    error['available_balance'] = available
                    error['required_balance'] = capital
                    
                    return False, error
        else:
            # Paper mode: capital input is always in ZAR (user economic base).
            # For USDT exchanges, convert to the quote currency before wallet check.
            quote_capital, quote_currency, fx_rate_used = resolve_capital_for_exchange(capital, exchange)
            available = await paper_wallet_service.get_available_balance(user_id, quote_currency)
            if available < quote_capital:
                return False, {
                    "code": "PAPER_WALLET_INSUFFICIENT",
                    "message": (
                        f"Insufficient paper wallet funds ({quote_currency}). "
                        f"Available: {available:.2f} {quote_currency}, "
                        f"Required: {quote_capital:.2f} {quote_currency} "
                        f"(= R{capital:.2f} ZAR at {fx_rate_used:.4f} {quote_currency}/ZAR)"
                    ),
                    "action": "Add fake funds to your paper wallet before spawning bots.",
                    "severity": "error"
                }
        
        # 8. Validate risk mode
        valid_risk_modes = ['safe', 'balanced', 'risky', 'aggressive']
        risk_mode = bot_data.get('risk_mode', 'safe').lower()
        if risk_mode not in valid_risk_modes:
            risk_mode = 'safe'

        strategy_preset = bot_data.get("strategy_preset") or "adaptive"

        # 9. Preserve bot classification fields sent by the caller.
        # bot_type identifies the bot's operational class (normal / scalper / uagent).
        # Stripping this field was the root cause of scalper bots appearing as normal bots.
        valid_bot_types = {'normal', 'scalper', 'uagent'}
        raw_bot_type = (bot_data.get("bot_type") or "normal").lower()
        bot_type = raw_bot_type if raw_bot_type in valid_bot_types else "normal"

        # Enforce bot-class caps (scalper and normal) per exchange + global.
        if bot_type == "scalper":
            global_scalpers = await db.bots_collection.count_documents({
                "user_id": user_id,
                "bot_type": "scalper",
                "status": {"$ne": "deleted"},
                "deleted": {"$ne": True},
            })
            if global_scalpers >= MAX_SCALPER_BOTS_GLOBAL:
                return False, {
                    "code": "SCALPER_GLOBAL_CAP_REACHED",
                    "message": f"Scalper global cap reached ({global_scalpers}/{MAX_SCALPER_BOTS_GLOBAL})",
                    "action": "Delete or pause existing scalper bots before creating another.",
                    "severity": "error",
                }

            exchange_scalpers = await db.bots_collection.count_documents({
                "user_id": user_id,
                "exchange": exchange,
                "bot_type": "scalper",
                "status": {"$ne": "deleted"},
                "deleted": {"$ne": True},
            })
            scalper_cap = _safe_int_cap(get_scalper_cap(exchange), fallback=2)
            if exchange_scalpers >= scalper_cap:
                return False, {
                    "code": "SCALPER_EXCHANGE_CAP_REACHED",
                    "message": f"Scalper cap reached on {exchange} ({exchange_scalpers}/{scalper_cap})",
                    "action": "Use another exchange or retire an existing scalper bot.",
                    "severity": "error",
                }
        elif bot_type == "normal":
            exchange_normal = await db.bots_collection.count_documents({
                "user_id": user_id,
                "exchange": exchange,
                "bot_type": "normal",  # count only normal bots — scalpers have separate caps
                "status": {"$ne": "deleted"},
                "deleted": {"$ne": True},
            })
            normal_cap = _safe_int_cap(get_normal_cap(exchange), fallback=get_max_bots(exchange))
            if exchange_normal >= normal_cap:
                return False, {
                    "code": "NORMAL_EXCHANGE_CAP_REACHED",
                    "message": f"Normal-bot cap reached on {exchange} ({exchange_normal}/{normal_cap})",
                    "action": "Use another exchange or retire an existing normal bot.",
                    "severity": "error",
                }

        # profit_routing controls where scalper profits are directed.
        valid_profit_routings = {'RETURN_TO_MAIN', 'SCALPER_GROWTH'}
        raw_routing = (bot_data.get("profit_routing") or "RETURN_TO_MAIN").upper()
        profit_routing = raw_routing if raw_routing in valid_profit_routings else "RETURN_TO_MAIN"

        # Compute canonical capital fields — capital input is always ZAR.
        # For USDT exchanges the quote_capital is the USDT equivalent.
        # quote_capital / fx_rate_used == canonical_base_capital_zar (within rounding).
        # Note: for paper mode, resolve_capital_for_exchange was already called in the
        # wallet-check block above and quote_capital/quote_currency/fx_rate_used are set.
        # For live mode, compute them here.
        if trading_mode == 'live':
            quote_capital, quote_currency, fx_rate_used = resolve_capital_for_exchange(capital, exchange)

        # All validations passed - return validated data with lifecycle fields
        validated_data = {
            "name": name,
            "exchange": exchange,
            "risk_mode": risk_mode,
            # Canonical capital truth fields.
            # canonical_base_capital_zar — the user's economic base in ZAR terms;
            #   always the original R-amount the user entered.
            # initial_capital / current_capital — in quote currency (ZAR for Luno,
            #   USDT for Binance/KuCoin/etc.).  These are used for live trade sizing.
            # fx_rate_at_creation — USDT→ZAR rate used for the conversion.
            # quote_currency — native trading currency for this bot.
            "canonical_base_capital_zar": round(float(capital), 2),
            "initial_capital": quote_capital,
            "current_capital": quote_capital,
            "fx_rate_at_creation": fx_rate_used,
            "quote_currency": quote_currency,
            "total_profit": 0,
            "total_injections": 0,
            "trades_count": 0,
            "win_count": 0,
            "loss_count": 0,
            "status": "active",
            "mode": "paper",  # Always start in paper mode
            "trading_mode": "paper",
            "lifecycle_stage": "paper_training",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "first_trade_at": None,
            "last_trade_at": None,
            "paper_start_date": datetime.now(timezone.utc).isoformat(),
            "paper_end_eligible_at": None,  # Will be set after 7 days
            "promoted_to_live_at": None,
            "user_id": user_id,
            "strategy_preset": strategy_preset,
            "strategy": {"preset": strategy_preset},
            # Bot classification — must be preserved so scalper/uagent bots
            # appear in the correct fleet tab and counters.
            "bot_type": bot_type,
            "profit_routing": profit_routing,
        }
        
        return True, validated_data

# Global instance
bot_validator = BotValidator()
