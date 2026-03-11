"""
AllInCostModel – production-grade cost estimation for all bot types.

Supports multi-venue, multi-currency cost computation with conservative
defaults. Used as the single source of truth for round-trip cost estimation
before any trade is allowed.
"""
import logging

logger = logging.getLogger(__name__)

# ── Venue fee defaults (maker/taker in BPS) ──
# Conservative estimates used when user-specific fee tier is unknown.
VENUE_FEE_DEFAULTS_BPS = {
    "luno":    {"maker": 0,   "taker": 10,  "quote": "ZAR"},
    "binance": {"maker": 10,  "taker": 10,  "quote": "USDT"},
    "kucoin":  {"maker": 10,  "taker": 10,  "quote": "USDT"},
    "bybit":   {"maker": 10,  "taker": 10,  "quote": "USDT"},
    "kraken":  {"maker": 16,  "taker": 26,  "quote": "USDT"},
    "bitget":  {"maker": 10,  "taker": 10,  "quote": "USDT"},
    "gate":    {"maker": 20,  "taker": 20,  "quote": "USDT"},
}

# Conservative add-on for adverse selection when posting as maker (BPS)
MAKER_ADVERSE_SELECTION_BPS = {
    "luno": 5,
    "binance": 3,
    "kucoin": 4,
    "bybit": 3,
    "kraken": 4,
    "bitget": 4,
    "gate": 5,
}

# Default minimum slippage even when book appears deep (BPS)
MIN_SLIPPAGE_BPS = 2


class AllInCostModel:
    """
    Compute all-in round-trip cost for a proposed trade.

    Inputs:
        venue, symbol, quote_currency, side, order_mode (maker/taker),
        notional_size, best_bid, best_ask, mid, depth_snapshot,
        fee_profile (optional), spread, volatility_estimate

    Outputs dict with:
        fee_in_bps, fee_out_bps, spread_cost_bps, slippage_in_bps,
        slippage_out_bps, maker_adverse_selection_bps, all_in_cost_bps,
        all_in_cost_quote, projected_round_trip_cost_quote
    """

    def compute(
        self,
        venue: str,
        symbol: str,
        quote_currency: str,
        side: str,
        order_mode: str,
        notional_size: float,
        best_bid: float,
        best_ask: float,
        mid: float,
        depth_snapshot: dict = None,
        fee_profile: dict = None,
        spread: float = None,
        volatility_estimate: float = None,
    ) -> dict:
        venue_key = (venue or "").lower().replace(".", "").replace("io", "")
        if venue_key == "gateio":
            venue_key = "gate"
        defaults = VENUE_FEE_DEFAULTS_BPS.get(venue_key, {"maker": 20, "taker": 20, "quote": "USDT"})

        # ── Fee rates ──
        if fee_profile:
            fee_in_bps = float(fee_profile.get("maker_bps" if order_mode == "maker" else "taker_bps", defaults.get(order_mode, 20)))
            fee_out_bps = float(fee_profile.get("taker_bps", defaults.get("taker", 20)))
        else:
            fee_in_bps = float(defaults.get(order_mode, defaults.get("taker", 20)))
            fee_out_bps = float(defaults.get("taker", 20))

        # ── Spread cost ──
        if spread is not None and spread > 0:
            spread_cost_bps = spread * 10000.0  # spread as decimal → bps
        elif best_bid > 0 and best_ask > 0:
            spread_cost_bps = ((best_ask - best_bid) / mid) * 10000.0 if mid > 0 else 10.0
        else:
            spread_cost_bps = 10.0  # conservative fallback

        # ── Slippage estimation ──
        slippage_in_bps, slippage_out_bps = self._estimate_slippage(
            venue_key, notional_size, depth_snapshot, volatility_estimate
        )

        # ── Maker adverse selection (only for maker orders) ──
        maker_adverse_bps = 0.0
        if order_mode == "maker":
            maker_adverse_bps = float(MAKER_ADVERSE_SELECTION_BPS.get(venue_key, 5))

        # ── All-in cost (round-trip) ──
        all_in_cost_bps = (
            fee_in_bps
            + fee_out_bps
            + spread_cost_bps
            + slippage_in_bps
            + slippage_out_bps
            + maker_adverse_bps
        )

        # ── Quote currency cost ──
        safe_notional = max(notional_size, 0.0)
        all_in_cost_quote = safe_notional * (all_in_cost_bps / 10000.0)
        projected_round_trip_cost_quote = all_in_cost_quote

        return {
            "fee_in_bps": round(fee_in_bps, 2),
            "fee_out_bps": round(fee_out_bps, 2),
            "spread_cost_bps": round(spread_cost_bps, 2),
            "slippage_in_bps": round(slippage_in_bps, 2),
            "slippage_out_bps": round(slippage_out_bps, 2),
            "maker_adverse_selection_bps": round(maker_adverse_bps, 2),
            "all_in_cost_bps": round(all_in_cost_bps, 2),
            "all_in_cost_quote": round(all_in_cost_quote, 4),
            "projected_round_trip_cost_quote": round(projected_round_trip_cost_quote, 4),
            "venue": venue_key,
            "quote_currency": quote_currency or defaults.get("quote", "USDT"),
            "order_mode": order_mode,
        }

    def _estimate_slippage(
        self,
        venue: str,
        notional: float,
        depth_snapshot: dict = None,
        volatility: float = None,
    ) -> tuple:
        """
        Estimate entry + exit slippage in BPS.

        Uses order-book depth if available (VWAP sweep), otherwise applies
        conservative heuristic based on notional size and volatility.
        """
        if depth_snapshot and isinstance(depth_snapshot, dict):
            bids = depth_snapshot.get("bids", [])
            asks = depth_snapshot.get("asks", [])
            if bids and asks:
                slip_in = self._sweep_vwap_slippage(asks, notional)
                slip_out = self._sweep_vwap_slippage(bids, notional)
                return (max(slip_in, MIN_SLIPPAGE_BPS), max(slip_out, MIN_SLIPPAGE_BPS))

        # Heuristic fallback
        base_slip = 5.0  # 0.05%
        if volatility and volatility > 0:
            base_slip += min(volatility * 100, 10.0)  # vol contribution capped
        if notional > 100000:
            base_slip += 3.0
        elif notional > 50000:
            base_slip += 1.5

        return (max(base_slip, MIN_SLIPPAGE_BPS), max(base_slip, MIN_SLIPPAGE_BPS))

    @staticmethod
    def _sweep_vwap_slippage(levels: list, notional: float) -> float:
        """
        Sweep order-book levels to compute VWAP slippage in BPS.

        Each level: [price, quantity] or {"price": p, "qty": q}.
        """
        if not levels or notional <= 0:
            return MIN_SLIPPAGE_BPS

        filled_notional = 0.0
        filled_base = 0.0
        top_price = None

        for lvl in levels:
            if isinstance(lvl, (list, tuple)) and len(lvl) >= 2:
                price, qty = float(lvl[0]), float(lvl[1])
            elif isinstance(lvl, dict):
                price = float(lvl.get("price", 0))
                qty = float(lvl.get("qty", lvl.get("quantity", 0)))
            else:
                continue

            if price <= 0 or qty <= 0:
                continue

            if top_price is None:
                top_price = price

            level_notional = price * qty
            remaining = notional - filled_notional
            take_notional = min(level_notional, remaining)
            take_base = take_notional / price
            filled_notional += take_notional
            filled_base += take_base

            if filled_notional >= notional:
                break

        if filled_base <= 0 or top_price <= 0:
            return 8.0  # conservative if book is empty

        if filled_notional < notional:
            # Book too thin – high slippage
            return 15.0

        # VWAP = total cost / total base quantity
        vwap = filled_notional / filled_base
        slip_bps = abs(vwap - top_price) / top_price * 10000.0
        return max(min(slip_bps, 30.0), MIN_SLIPPAGE_BPS)
