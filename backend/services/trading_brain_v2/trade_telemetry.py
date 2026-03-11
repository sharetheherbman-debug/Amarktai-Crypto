"""
TradeTelemetry – attribution and learning data for Trading Brain V2.

Records trade intent, predicted edge, confidence, regime snapshot,
cost estimates, fill data, and realized metrics for post-trade analysis.
"""
import logging
import time

logger = logging.getLogger(__name__)


class TradeTelemetry:
    """
    Build telemetry records for trade lifecycle events.
    Records are designed for persistence in MongoDB for calibration.
    """

    @staticmethod
    def build_entry_record(
        bot_id: str,
        symbol: str,
        venue: str,
        side: str,
        bot_type: str,
        entry_price: float,
        notional: float,
        predicted_edge_bps: float,
        confidence: float,
        regime_snapshot: dict,
        cost_estimate: dict,
        target_policy: dict,
        feasibility_result: dict,
        order_mode: str = "taker",
    ) -> dict:
        """Build entry telemetry record."""
        return {
            "event": "trade_entry",
            "ts": time.time(),
            "bot_id": bot_id,
            "symbol": symbol,
            "venue": venue,
            "side": side,
            "bot_type": bot_type,
            "entry_price": entry_price,
            "notional": notional,
            "order_mode": order_mode,
            "predicted_edge_bps": round(predicted_edge_bps, 2),
            "confidence": round(confidence, 4),
            "regime_snapshot": _safe_dict(regime_snapshot),
            "cost_estimate": _safe_dict(cost_estimate),
            "target_policy": _safe_dict(target_policy),
            "feasibility_result": _safe_dict(feasibility_result),
        }

    @staticmethod
    def build_exit_record(
        bot_id: str,
        symbol: str,
        venue: str,
        side: str,
        bot_type: str,
        entry_price: float,
        exit_price: float,
        notional: float,
        gross_pnl: float,
        net_pnl: float,
        fee_total: float,
        spread_cost: float,
        slippage_cost: float,
        hold_seconds: float,
        exit_reason_code: str,
        predicted_edge_bps: float = 0.0,
        regime_at_entry: str = "",
        regime_at_exit: str = "",
        max_adverse_excursion: float = 0.0,
        max_favorable_excursion: float = 0.0,
    ) -> dict:
        """Build exit telemetry record with full attribution."""
        realized_edge_bps = 0.0
        if notional > 0:
            realized_edge_bps = (net_pnl / notional) * 10000.0

        implementation_shortfall = predicted_edge_bps - realized_edge_bps

        return {
            "event": "trade_exit",
            "ts": time.time(),
            "bot_id": bot_id,
            "symbol": symbol,
            "venue": venue,
            "side": side,
            "bot_type": bot_type,
            "entry_price": entry_price,
            "exit_price": exit_price,
            "notional": notional,
            "gross_pnl": round(gross_pnl, 4),
            "net_pnl": round(net_pnl, 4),
            "fee_total": round(fee_total, 4),
            "spread_cost": round(spread_cost, 4),
            "slippage_cost": round(slippage_cost, 4),
            "hold_seconds": round(hold_seconds, 2),
            "exit_reason_code": exit_reason_code,
            "predicted_edge_bps": round(predicted_edge_bps, 2),
            "realized_edge_bps": round(realized_edge_bps, 2),
            "implementation_shortfall_bps": round(implementation_shortfall, 2),
            "regime_at_entry": regime_at_entry,
            "regime_at_exit": regime_at_exit,
            "max_adverse_excursion": round(max_adverse_excursion, 4),
            "max_favorable_excursion": round(max_favorable_excursion, 4),
        }

    @staticmethod
    def build_skip_record(
        bot_id: str,
        symbol: str,
        venue: str,
        bot_type: str,
        reason_code: str,
        reason_text: str,
        diagnostics: dict = None,
    ) -> dict:
        """Build skip telemetry record."""
        return {
            "event": "trade_skip",
            "ts": time.time(),
            "bot_id": bot_id,
            "symbol": symbol,
            "venue": venue,
            "bot_type": bot_type,
            "reason_code": reason_code,
            "reason_text": reason_text,
            "diagnostics": _safe_dict(diagnostics),
        }


def _safe_dict(d):
    """Ensure dict is safe for MongoDB serialization."""
    if not d or not isinstance(d, dict):
        return {}
    result = {}
    for k, v in d.items():
        if v is None:
            result[k] = None
        elif isinstance(v, float):
            result[k] = 0.0 if v != v else v  # NaN → 0
        elif isinstance(v, dict):
            result[k] = _safe_dict(v)
        else:
            result[k] = v
    return result
