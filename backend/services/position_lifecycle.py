"""
Position Lifecycle Contract

Every open position MUST have:
  - TP (take-profit) and SL (stop-loss) prices
  - Max hold time based on risk_mode (safe=6h, balanced=3h, aggressive=90m)
  - Optional trailing stop once in profit

Exit reason codes for forced exits:
  TIME_EXIT       — max hold time exceeded
  STAGNATION_EXIT — price has not moved enough within stagnation window
  RISK_EXIT       — unrealized loss exceeds risk threshold
  TARGET_EXIT     — take-profit reached
  STOP_EXIT       — stop-loss hit
  TRAIL_EXIT      — trailing stop triggered

All exits are recorded in the ledger with the reason code.
"""

from datetime import datetime, timezone, timedelta
from typing import Dict, Optional, Tuple
import logging

logger = logging.getLogger(__name__)

# Reason codes
TIME_EXIT = "TIME_EXIT"
STAGNATION_EXIT = "STAGNATION_EXIT"
RISK_EXIT = "RISK_EXIT"
TARGET_EXIT = "TARGET_EXIT"
STOP_EXIT = "STOP_EXIT"
TRAIL_EXIT = "TRAIL_EXIT"

# Max hold durations by risk mode (seconds)
MAX_HOLD_SECONDS: Dict[str, int] = {
    "safe": 6 * 3600,        # 6 hours
    "balanced": 3 * 3600,    # 3 hours
    "aggressive": 90 * 60,   # 90 minutes
}

# Stagnation: if price moves less than this % in the stagnation window, exit
STAGNATION_THRESHOLD_PCT = 0.05   # 0.05%
STAGNATION_WINDOW_SECONDS: Dict[str, int] = {
    "safe": 3 * 3600,
    "balanced": 90 * 60,
    "aggressive": 45 * 60,
}

# Default TP/SL percentages if not specified
DEFAULT_TP_PCT: Dict[str, float] = {
    "safe": 1.0,       # 1%
    "balanced": 1.5,   # 1.5%
    "aggressive": 2.5, # 2.5%
}
DEFAULT_SL_PCT: Dict[str, float] = {
    "safe": 0.5,       # 0.5%
    "balanced": 1.0,   # 1%
    "aggressive": 1.5, # 1.5%
}

# Trailing stop activation: once in profit by this %, activate trailing
TRAILING_ACTIVATION_PCT = 0.5  # 0.5% in profit to activate
TRAILING_DISTANCE_PCT = 0.3    # 0.3% trailing distance


def compute_position_limits(
    entry_price: float,
    side: str,
    risk_mode: str = "balanced",
    tp_price: Optional[float] = None,
    sl_price: Optional[float] = None,
) -> Dict:
    """
    Compute TP, SL, and max hold time for a new position.

    Returns:
        {
            "take_profit": float,
            "stop_loss": float,
            "max_hold_seconds": int,
            "trailing_activation_price": float,
            "trailing_distance_pct": float,
        }
    """
    risk_mode = risk_mode.lower() if risk_mode else "balanced"
    if risk_mode not in MAX_HOLD_SECONDS:
        risk_mode = "balanced"

    tp_pct = DEFAULT_TP_PCT[risk_mode] / 100.0
    sl_pct = DEFAULT_SL_PCT[risk_mode] / 100.0

    if side.lower() == "buy":
        tp = tp_price if tp_price else entry_price * (1 + tp_pct)
        sl = sl_price if sl_price else entry_price * (1 - sl_pct)
        trailing_activation = entry_price * (1 + TRAILING_ACTIVATION_PCT / 100.0)
    else:
        tp = tp_price if tp_price else entry_price * (1 - tp_pct)
        sl = sl_price if sl_price else entry_price * (1 + sl_pct)
        trailing_activation = entry_price * (1 - TRAILING_ACTIVATION_PCT / 100.0)

    return {
        "take_profit": round(tp, 8),
        "stop_loss": round(sl, 8),
        "max_hold_seconds": MAX_HOLD_SECONDS[risk_mode],
        "trailing_activation_price": round(trailing_activation, 8),
        "trailing_distance_pct": TRAILING_DISTANCE_PCT,
    }


def check_position_exit(
    side: str,
    entry_price: float,
    current_price: float,
    opened_at: datetime,
    risk_mode: str = "balanced",
    tp: Optional[float] = None,
    sl: Optional[float] = None,
    trailing_stop: Optional[float] = None,
    capital: float = 0,
    qty: float = 0,
    price_history: Optional[list] = None,
    now: Optional[datetime] = None,
) -> Tuple[bool, Optional[str], str]:
    """
    Evaluate whether an open position should be force-exited.

    Returns:
        (should_exit: bool, reason_code: str|None, reason_text: str)
    """
    now = now or datetime.now(timezone.utc)
    risk_mode = (risk_mode or "balanced").lower()
    if risk_mode not in MAX_HOLD_SECONDS:
        risk_mode = "balanced"

    max_hold = MAX_HOLD_SECONDS[risk_mode]
    elapsed = (now - opened_at).total_seconds() if opened_at else 0

    is_buy = side.lower() == "buy"

    # 1. Time exit
    if elapsed >= max_hold:
        return True, TIME_EXIT, f"Max hold time exceeded ({int(elapsed)}s >= {max_hold}s)"

    # 2. Take profit
    if tp:
        if (is_buy and current_price >= tp) or (not is_buy and current_price <= tp):
            return True, TARGET_EXIT, f"Take-profit reached at {current_price}"

    # 3. Stop loss
    if sl:
        if (is_buy and current_price <= sl) or (not is_buy and current_price >= sl):
            return True, STOP_EXIT, f"Stop-loss hit at {current_price}"

    # 4. Trailing stop
    if trailing_stop:
        if (is_buy and current_price <= trailing_stop) or (not is_buy and current_price >= trailing_stop):
            return True, TRAIL_EXIT, f"Trailing stop triggered at {current_price}"

    # 5. Risk exit (unrealized loss exceeds 3% of capital)
    if capital > 0 and qty > 0:
        if is_buy:
            unrealized = (current_price - entry_price) * qty
        else:
            unrealized = (entry_price - current_price) * qty
        if unrealized < -(capital * 0.03):
            return True, RISK_EXIT, f"Unrealized loss {unrealized:.2f} exceeds 3% of capital"

    # 6. Stagnation exit
    stag_window = STAGNATION_WINDOW_SECONDS.get(risk_mode, 5400)
    if elapsed >= stag_window and price_history:
        # Check if price has moved less than threshold
        recent = [p for t, p in price_history if (now - t).total_seconds() <= stag_window]
        if len(recent) >= 2:
            price_range = max(recent) - min(recent)
            if entry_price > 0 and (price_range / entry_price * 100) < STAGNATION_THRESHOLD_PCT:
                return True, STAGNATION_EXIT, f"Price stagnated ({price_range:.2f} range in {stag_window}s)"

    return False, None, "Position open"


def compute_trailing_stop(
    side: str,
    current_price: float,
    highest_price: float,
    lowest_price: float,
    trailing_distance_pct: float = TRAILING_DISTANCE_PCT,
) -> Optional[float]:
    """
    Compute trailing stop price based on the best price seen since entry.
    Returns None if trailing stop is not applicable.
    """
    distance = trailing_distance_pct / 100.0

    if side.lower() == "buy":
        # For longs, trail below the highest price
        if highest_price > 0:
            return round(highest_price * (1 - distance), 8)
    else:
        # For shorts, trail above the lowest price
        if lowest_price > 0:
            return round(lowest_price * (1 + distance), 8)

    return None
