"""
Portfolio Meta-Controller — dynamic capital allocation across bot classes.

Purpose:
  Dynamically allocate capital between scalper and normal bots based on
  real-time market conditions and bot performance metrics.

Inputs:
  market_regime, volatility, orderbook_quality, whale_flow_direction,
  sentiment_score, bot_performance, capital_efficiency, current_drawdown,
  current_exposure

Outputs:
  preferred_bot_class, capital_weights, exchange_exposure_limit,
  pair_exposure_limit, risk_multiplier, hold_time_profile

Optional mode:
  scalper_priority_mode — biases allocation toward scalpers when enabled.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


# ── Enums & Dataclasses ─────────────────────────────────────────────────────

class BotClassPreference(str, Enum):
    SCALPER = "scalper"
    NORMAL = "normal"
    BALANCED = "balanced"


class HoldTimeProfile(str, Enum):
    ULTRA_SHORT = "ultra_short"    # 10s - 2min
    SHORT = "short"                # 2min - 5min
    MEDIUM = "medium"              # 5min - 30min
    LONG = "long"                  # 30min - 90min


@dataclass
class MetaControllerInput:
    """Inputs for meta-controller decision."""
    market_regime: str = "unknown"
    volatility: float = 0.0
    orderbook_quality: float = 0.5       # 0-1
    whale_flow_direction: str = "neutral" # inflow / outflow / neutral
    sentiment_score: float = 0.5         # 0-1
    bot_performance_score: float = 0.5   # 0-1  (aggregate)
    capital_efficiency: float = 0.0      # pct/hr
    current_drawdown: float = 0.0        # 0-1
    current_exposure: float = 0.0        # fraction of total capital in use
    scalper_priority_mode: bool = False


@dataclass
class MetaControllerOutput:
    """Decision output from the meta-controller."""
    preferred_bot_class: str = "balanced"
    scalper_weight: float = 0.5
    normal_weight: float = 0.5
    exchange_exposure_limit: float = 0.25  # max fraction per exchange
    pair_exposure_limit: float = 0.10      # max fraction per pair
    risk_multiplier: float = 1.0
    hold_time_profile: str = "medium"
    reasoning: str = ""
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


# ── Controller ───────────────────────────────────────────────────────────────

class PortfolioMetaController:
    """
    Decides how capital should be split between scalper and normal bots
    and sets exposure / risk limits based on market conditions.
    """

    # Regime -> base scalper weight (rest goes to normal bots)
    REGIME_SCALPER_BIAS: Dict[str, float] = {
        "trending": 0.30,
        "ranging": 0.65,
        "volatile": 0.40,
        "low_volatility": 0.55,
        "panic": 0.15,
        "accumulation": 0.50,
        # legacy aliases
        "bullish_calm": 0.35,
        "bearish_volatile": 0.25,
        "squeeze": 0.60,
        "unknown": 0.45,
    }

    REGIME_RISK_MULT: Dict[str, float] = {
        "trending": 1.1,
        "ranging": 1.0,
        "volatile": 0.7,
        "low_volatility": 1.0,
        "panic": 0.4,
        "accumulation": 0.9,
        "bullish_calm": 1.1,
        "bearish_volatile": 0.6,
        "squeeze": 0.8,
        "unknown": 0.8,
    }

    REGIME_HOLD_PROFILE: Dict[str, str] = {
        "trending": HoldTimeProfile.LONG.value,
        "ranging": HoldTimeProfile.SHORT.value,
        "volatile": HoldTimeProfile.ULTRA_SHORT.value,
        "low_volatility": HoldTimeProfile.MEDIUM.value,
        "panic": HoldTimeProfile.ULTRA_SHORT.value,
        "accumulation": HoldTimeProfile.MEDIUM.value,
        "bullish_calm": HoldTimeProfile.LONG.value,
        "bearish_volatile": HoldTimeProfile.ULTRA_SHORT.value,
        "squeeze": HoldTimeProfile.SHORT.value,
        "unknown": HoldTimeProfile.MEDIUM.value,
    }

    def decide(self, inputs: MetaControllerInput) -> MetaControllerOutput:
        """
        Compute portfolio allocation decision.

        Pure function — no I/O.  Suitable for testing and back-testing.
        """
        regime = inputs.market_regime.lower()

        # 1. Base scalper weight from regime
        scalper_w = self.REGIME_SCALPER_BIAS.get(regime, 0.45)

        # 2. Adjust for scalper priority mode
        if inputs.scalper_priority_mode:
            scalper_w = min(1.0, scalper_w + 0.15)

        # 3. Adjust for volatility (high vol -> more scalpers)
        if inputs.volatility > 0.03:
            scalper_w = min(1.0, scalper_w + 0.10)
        elif inputs.volatility < 0.005:
            scalper_w = max(0.0, scalper_w - 0.10)

        # 4. Adjust for drawdown (high drawdown -> reduce risk, favour scalpers)
        if inputs.current_drawdown > 0.05:
            scalper_w = min(1.0, scalper_w + 0.10)

        # 5. Whale flow adjustments
        if inputs.whale_flow_direction == "outflow":
            scalper_w = min(1.0, scalper_w + 0.05)

        # 6. Clamp
        scalper_w = round(max(0.0, min(1.0, scalper_w)), 2)
        normal_w = round(1.0 - scalper_w, 2)

        # 7. Determine preferred class
        if scalper_w >= 0.60:
            preferred = BotClassPreference.SCALPER.value
        elif scalper_w <= 0.35:
            preferred = BotClassPreference.NORMAL.value
        else:
            preferred = BotClassPreference.BALANCED.value

        # 8. Risk multiplier from regime
        risk_mult = self.REGIME_RISK_MULT.get(regime, 0.8)
        # Reduce further under heavy drawdown
        if inputs.current_drawdown > 0.05:
            risk_mult *= 0.8
        risk_mult = round(max(0.1, min(2.0, risk_mult)), 2)

        # 9. Exposure limits - tighter when risk is high
        exchange_limit = round(min(0.30, 0.25 / max(risk_mult, 0.3)), 2)
        pair_limit = round(min(0.15, 0.10 / max(risk_mult, 0.3)), 2)

        # 10. Hold-time profile from regime
        hold_profile = self.REGIME_HOLD_PROFILE.get(regime, HoldTimeProfile.MEDIUM.value)

        reasoning = (
            f"regime={regime}, vol={inputs.volatility:.4f}, "
            f"dd={inputs.current_drawdown:.2%}, "
            f"scalper_priority={'ON' if inputs.scalper_priority_mode else 'OFF'}"
        )

        return MetaControllerOutput(
            preferred_bot_class=preferred,
            scalper_weight=scalper_w,
            normal_weight=normal_w,
            exchange_exposure_limit=exchange_limit,
            pair_exposure_limit=pair_limit,
            risk_multiplier=risk_mult,
            hold_time_profile=hold_profile,
            reasoning=reasoning,
        )

    def get_summary(self, inputs: Optional[MetaControllerInput] = None) -> Dict[str, Any]:
        """Return a JSON-safe summary for dashboard display."""
        if inputs is None:
            inputs = MetaControllerInput()
        out = self.decide(inputs)
        return {
            "preferred_bot_class": out.preferred_bot_class,
            "scalper_weight": out.scalper_weight,
            "normal_weight": out.normal_weight,
            "exchange_exposure_limit": out.exchange_exposure_limit,
            "pair_exposure_limit": out.pair_exposure_limit,
            "risk_multiplier": out.risk_multiplier,
            "hold_time_profile": out.hold_time_profile,
            "reasoning": out.reasoning,
            "timestamp": out.timestamp,
        }


# Global singleton
portfolio_meta_controller = PortfolioMetaController()
