"""
ExecutionRouterV2 – route by expected net profitability.

Routes trades to venues based on expected cost, edge, reliability,
and venue availability. Decides maker/taker and repricing policy.
"""
import logging

logger = logging.getLogger(__name__)


class ExecutionRouterV2:
    """
    Route execution decisions based on economics.
    """

    def route(
        self,
        candidate_venues: list,
        symbol: str,
        side: str,
        notional: float,
        expected_edges: dict = None,
        expected_costs: dict = None,
        venue_availability: dict = None,
        bot_type: str = "normal",
        signal_confidence: float = 0.5,
        regime_label: str = "unknown",
    ) -> dict:
        """
        Select best venue and execution mode.

        candidate_venues: ["luno", "binance", ...]
        expected_edges: {venue: edge_bps}
        expected_costs: {venue: cost_bps}
        venue_availability: {venue: True/False}

        Returns:
            {
                routed_venue, maker_taker, repricing_policy,
                cancellation_policy, slippage_guardrails, reason
            }
        """
        expected_edges = expected_edges or {}
        expected_costs = expected_costs or {}
        venue_availability = venue_availability or {}

        best_venue = None
        best_net = float("-inf")
        best_mode = "taker"

        for venue in candidate_venues:
            if not venue_availability.get(venue, True):
                continue

            edge = expected_edges.get(venue, 0.0)
            cost = expected_costs.get(venue, 0.0)
            net = edge - cost

            if net > best_net:
                best_net = net
                best_venue = venue

        if best_venue is None:
            return {
                "routed_venue": None,
                "maker_taker": None,
                "repricing_policy": None,
                "cancellation_policy": None,
                "slippage_guardrails": None,
                "reason": "No available venue with positive expected net.",
            }

        # Maker/taker decision
        best_mode = self._decide_maker_taker(
            bot_type, signal_confidence, regime_label, best_net
        )

        # Policies
        repricing = self._repricing_policy(best_mode, bot_type)
        cancellation = self._cancellation_policy(best_mode, bot_type)
        slippage_guard = self._slippage_guardrails(bot_type, best_venue)

        return {
            "routed_venue": best_venue,
            "maker_taker": best_mode,
            "repricing_policy": repricing,
            "cancellation_policy": cancellation,
            "slippage_guardrails": slippage_guard,
            "expected_net_edge_bps": round(best_net, 2),
            "reason": f"Best net edge on {best_venue}: {best_net:.1f} bps as {best_mode}.",
        }

    @staticmethod
    def _decide_maker_taker(bot_type, confidence, regime_label, net_edge_bps):
        """Decide order mode based on bot type and conditions."""
        if bot_type == "scalper":
            if regime_label in ("breakout", "high_volatility"):
                return "taker"  # momentum burst
            return "taker"  # scalpers default taker for speed

        # Normal / trend bots prefer maker
        if regime_label == "breakout" and confidence > 0.75:
            return "taker"  # urgency on breakout
        if net_edge_bps > 30:
            return "taker"  # strong edge, grab it
        return "maker"

    @staticmethod
    def _repricing_policy(mode, bot_type):
        if mode == "maker":
            return {
                "enabled": True,
                "max_reprices": 3,
                "reprice_interval_seconds": 10 if bot_type == "scalper" else 30,
                "max_reprice_distance_bps": 5,
            }
        return {"enabled": False}

    @staticmethod
    def _cancellation_policy(mode, bot_type):
        if mode == "maker":
            timeout = 30 if bot_type == "scalper" else 120
            return {
                "cancel_after_seconds": timeout,
                "cancel_on_spread_widen_bps": 10,
            }
        return {"cancel_after_seconds": None}

    @staticmethod
    def _slippage_guardrails(bot_type, venue):
        if bot_type == "scalper":
            return {"max_slippage_bps": 15, "abort_on_exceed": True}
        return {"max_slippage_bps": 30, "abort_on_exceed": True}
