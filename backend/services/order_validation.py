"""
Order Validation Service - Centralized Exchange Rules Enforcement
Ensures all orders (paper and live) pass precision, min notional, and exchange rules.
"""
from typing import Tuple, Dict, Optional
from decimal import Decimal, ROUND_DOWN
import math
from logger_config import logger


# Exchange-specific rules
EXCHANGE_RULES = {
    "binance": {
        "BTC/USDT": {
            "min_qty": 0.00001,
            "max_qty": 9000.0,
            "step_size": 0.00001,
            "price_tick": 0.01,
            "min_notional": 10.0,  # USDT
            "max_precision": 5
        },
        "ETH/USDT": {
            "min_qty": 0.0001,
            "max_qty": 90000.0,
            "step_size": 0.0001,
            "price_tick": 0.01,
            "min_notional": 10.0,
            "max_precision": 4
        }
    },
    "luno": {
        "BTC/ZAR": {
            "min_qty": 0.0001,
            "max_qty": 100.0,
            "step_size": 0.0001,
            "price_tick": 1.0,
            "min_notional": 10.0,  # ZAR
            "max_precision": 4
        },
        "ETH/ZAR": {
            "min_qty": 0.001,
            "max_qty": 1000.0,
            "step_size": 0.001,
            "price_tick": 1.0,
            "min_notional": 10.0,
            "max_precision": 3
        }
    },
    "kucoin": {
        "BTC/USDT": {
            "min_qty": 0.00001,
            "max_qty": 10000.0,
            "step_size": 0.00001,
            "price_tick": 0.1,
            "min_notional": 1.0,  # USDT
            "max_precision": 5
        },
        "ETH/USDT": {
            "min_qty": 0.0001,
            "max_qty": 100000.0,
            "step_size": 0.0001,
            "price_tick": 0.01,
            "min_notional": 1.0,
            "max_precision": 4
        }
    },
    "bybit": {
        "BTC/USDT": {
            "min_qty": 0.00001,
            "max_qty": 10000.0,
            "step_size": 0.00001,
            "price_tick": 0.1,
            "min_notional": 10.0,
            "max_precision": 5
        },
        "ETH/USDT": {
            "min_qty": 0.0001,
            "max_qty": 100000.0,
            "step_size": 0.0001,
            "price_tick": 0.01,
            "min_notional": 10.0,
            "max_precision": 4
        }
    },
    "bitget": {
        "BTC/USDT": {
            "min_qty": 0.00001,
            "max_qty": 10000.0,
            "step_size": 0.00001,
            "price_tick": 0.1,
            "min_notional": 5.0,
            "max_precision": 5
        },
        "ETH/USDT": {
            "min_qty": 0.0001,
            "max_qty": 100000.0,
            "step_size": 0.0001,
            "price_tick": 0.01,
            "min_notional": 5.0,
            "max_precision": 4
        }
    },
    "kraken": {
        "BTC/USDT": {
            "min_qty": 0.0001,
            "max_qty": 500.0,
            "step_size": 0.0001,
            "price_tick": 0.1,
            "min_notional": 10.0,  # USD equivalent
            "max_precision": 4
        },
        "ETH/USDT": {
            "min_qty": 0.001,
            "max_qty": 5000.0,
            "step_size": 0.001,
            "price_tick": 0.01,
            "min_notional": 10.0,
            "max_precision": 3
        },
        "BTC/USD": {
            "min_qty": 0.0001,
            "max_qty": 500.0,
            "step_size": 0.0001,
            "price_tick": 0.1,
            "min_notional": 10.0,
            "max_precision": 4
        },
        "ETH/USD": {
            "min_qty": 0.001,
            "max_qty": 5000.0,
            "step_size": 0.001,
            "price_tick": 0.01,
            "min_notional": 10.0,
            "max_precision": 3
        },
    },
    "gate": {
        "BTC/USDT": {
            "min_qty": 0.00001,
            "max_qty": 10000.0,
            "step_size": 0.00001,
            "price_tick": 0.1,
            "min_notional": 1.0,  # USDT
            "max_precision": 5
        },
        "ETH/USDT": {
            "min_qty": 0.0001,
            "max_qty": 100000.0,
            "step_size": 0.0001,
            "price_tick": 0.01,
            "min_notional": 1.0,
            "max_precision": 4
        },
    },
}

# Exchange fees (maker/taker)
EXCHANGE_FEES = {
    "binance": {"maker": 0.001, "taker": 0.001},   # 0.1%
    "luno": {"maker": 0.0, "taker": 0.001},         # 0% maker, 0.1% taker
    "kucoin": {"maker": 0.001, "taker": 0.001},     # 0.1%
    "bybit": {"maker": 0.001, "taker": 0.001},      # 0.1%
    "bitget": {"maker": 0.001, "taker": 0.001},     # 0.1%
    "kraken": {"maker": 0.0016, "taker": 0.0026},   # 0.16% maker / 0.26% taker
    "gate": {"maker": 0.002, "taker": 0.002},       # 0.2%
}

# Slippage estimates (percentage)
SLIPPAGE_ESTIMATES = {
    "market": 0.001,  # 0.1% for market orders
    "limit": 0.0  # No slippage for limit orders
}


class OrderValidator:
    """
    Validates orders against exchange-specific rules.
    Ensures precision, min notional, and other constraints are met.
    """
    
    def __init__(self):
        self.rules = EXCHANGE_RULES
        self.fees = EXCHANGE_FEES
        self.slippage = SLIPPAGE_ESTIMATES
    
    def get_symbol_rules(self, exchange: str, symbol: str) -> Optional[Dict]:
        """Get rules for a specific symbol on an exchange"""
        exchange = exchange.lower()
        
        # Normalize symbol format
        if "/" not in symbol:
            # Try to infer format
            if "USDT" in symbol.upper():
                symbol = symbol.upper().replace("USDT", "/USDT")
            elif "ZAR" in symbol.upper():
                symbol = symbol.upper().replace("ZAR", "/ZAR")
        
        return self.rules.get(exchange, {}).get(symbol.upper())
    
    def clamp_precision(self, value: float, max_precision: int) -> float:
        """
        Clamp a value to maximum precision (decimal places).
        
        Args:
            value: The value to clamp
            max_precision: Maximum number of decimal places
        
        Returns:
            Clamped value
        """
        if max_precision == 0:
            return float(int(value))
        
        multiplier = 10 ** max_precision
        return math.floor(value * multiplier) / multiplier
    
    def round_to_step_size(self, value: float, step_size: float) -> float:
        """
        Round a value to the nearest step size.
        
        Args:
            value: The value to round
            step_size: The step size (e.g., 0.00001)
        
        Returns:
            Rounded value
        """
        if step_size == 0:
            return value
        
        return math.floor(value / step_size) * step_size
    
    def validate_order(
        self,
        exchange: str,
        symbol: str,
        side: str,
        quantity: float,
        price: float,
        order_type: str = "market"
    ) -> Tuple[bool, str, Dict]:
        """
        Validate an order against exchange rules.
        
        Args:
            exchange: Exchange name (binance, luno, kucoin, etc.)
            symbol: Trading symbol (BTC/USDT, BTC/ZAR, etc.)
            side: Order side (buy, sell)
            quantity: Order quantity
            price: Order price
            order_type: Order type (market, limit)
        
        Returns:
            (is_valid, error_message, adjusted_params)
            
        adjusted_params contains:
            - quantity: Adjusted quantity (clamped to precision)
            - price: Adjusted price (clamped to tick size)
            - notional: Order notional value (quantity * price)
            - fees: Estimated fees
            - slippage: Estimated slippage
        """
        try:
            # Get symbol rules
            rules = self.get_symbol_rules(exchange, symbol)
            if not rules:
                # No rules found - allow but warn
                logger.warning(f"No rules found for {exchange} {symbol} - allowing order")
                return True, "", {
                    "quantity": quantity,
                    "price": price,
                    "notional": quantity * price,
                    "fees": 0.0,
                    "slippage": 0.0
                }
            
            # Clamp quantity to precision
            max_precision = rules["max_precision"]
            step_size = rules["step_size"]
            
            # Round to step size first, then clamp precision
            adjusted_qty = self.round_to_step_size(quantity, step_size)
            adjusted_qty = self.clamp_precision(adjusted_qty, max_precision)
            
            # Check minimum quantity
            if adjusted_qty < rules["min_qty"]:
                return False, f"Quantity {adjusted_qty} below minimum {rules['min_qty']}", {}
            
            # Check maximum quantity
            if adjusted_qty > rules["max_qty"]:
                return False, f"Quantity {adjusted_qty} above maximum {rules['max_qty']}", {}
            
            # Clamp price to tick size
            price_tick = rules["price_tick"]
            adjusted_price = self.round_to_step_size(price, price_tick)
            
            # Calculate notional
            notional = adjusted_qty * adjusted_price
            
            # Check minimum notional
            min_notional = rules["min_notional"]
            if notional < min_notional:
                return False, \
                    f"Order notional {notional:.2f} below minimum {min_notional:.2f}", {}
            
            # Calculate fees
            fee_schedule = self.fees.get(exchange.lower(), {"maker": 0.001, "taker": 0.001})
            fee_rate = fee_schedule["taker"] if order_type == "market" else fee_schedule["maker"]
            estimated_fees = notional * fee_rate
            
            # Calculate slippage
            slippage_rate = self.slippage.get(order_type, 0.0)
            estimated_slippage = notional * slippage_rate
            
            adjusted_params = {
                "quantity": adjusted_qty,
                "price": adjusted_price,
                "notional": notional,
                "fees": estimated_fees,
                "slippage": estimated_slippage,
                "total_cost": notional + estimated_fees + estimated_slippage
            }
            
            return True, "", adjusted_params
        
        except Exception as e:
            logger.error(f"Error validating order: {e}")
            return False, f"Validation error: {str(e)}", {}
    
    def get_realistic_fill_price(
        self,
        base_price: float,
        side: str,
        order_type: str = "market",
        volatility: float = 0.0001
    ) -> float:
        """
        Calculate realistic fill price with spread and slippage.
        
        Args:
            base_price: Current market price
            side: buy or sell
            order_type: market or limit
            volatility: Market volatility (used for spread calculation)
        
        Returns:
            Realistic fill price
        """
        # Market orders have slippage
        if order_type == "market":
            slippage = base_price * 0.0005  # 0.05% slippage
            
            if side == "buy":
                # Buying - pay slightly higher
                return base_price + slippage
            else:
                # Selling - receive slightly lower
                return base_price - slippage
        
        # Limit orders fill at limit price (no slippage)
        return base_price


# Singleton instance
order_validator = OrderValidator()
