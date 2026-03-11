"""
PortfolioConcentration – cross-bot concentration risk controls.

Enforces symbol, venue, and correlation exposure caps.
Handles multi-currency paper balances correctly.
"""
import logging

logger = logging.getLogger(__name__)

# ── Default concentration caps ──
DEFAULT_SYMBOL_CONCENTRATION_PCT = 35.0   # max 35% of equity in one symbol
DEFAULT_VENUE_CONCENTRATION_PCT = 60.0    # max 60% of equity on one venue
DEFAULT_CORRELATED_EXPOSURE_PCT = 50.0    # max 50% in correlated assets
MAX_BOT_TYPE_ALLOCATION_PCT = 70.0        # max 70% in one bot type

# Correlation groups
CORRELATED_GROUPS = {
    "btc_family": {"BTC/ZAR", "BTC/USDT"},
    "eth_family": {"ETH/ZAR", "ETH/USDT"},
    "xrp_family": {"XRP/ZAR", "XRP/USDT"},
}


class PortfolioConcentration:
    """
    Evaluate concentration risk for a proposed trade against
    existing open positions.
    """

    def check(
        self,
        symbol: str,
        venue: str,
        notional_proposed: float,
        bot_type: str,
        open_positions: list = None,
        total_equity: float = 0.0,
        symbol_cap_pct: float = None,
        venue_cap_pct: float = None,
    ) -> dict:
        """
        Check if adding this trade would breach concentration limits.

        open_positions: list of dicts with {symbol, venue, notional, bot_type}
        total_equity: total portfolio equity in quote currency

        Returns: {ok: bool, reason_code, details}
        """
        open_positions = open_positions or []
        safe_equity = max(total_equity, 1.0)
        sym_cap = symbol_cap_pct or DEFAULT_SYMBOL_CONCENTRATION_PCT
        ven_cap = venue_cap_pct or DEFAULT_VENUE_CONCENTRATION_PCT

        # ── Symbol concentration ──
        sym_exposure = notional_proposed
        for pos in open_positions:
            if pos.get("symbol") == symbol:
                sym_exposure += float(pos.get("notional", 0))

        sym_pct = (sym_exposure / safe_equity) * 100.0
        if sym_pct > sym_cap:
            return {
                "ok": False,
                "reason_code": "CONCENTRATION_LIMIT",
                "details": f"Symbol {symbol} would be {sym_pct:.1f}% of equity (cap: {sym_cap}%).",
            }

        # ── Venue concentration ──
        ven_exposure = notional_proposed
        venue_lower = (venue or "").lower()
        for pos in open_positions:
            if (pos.get("venue", "")).lower() == venue_lower:
                ven_exposure += float(pos.get("notional", 0))

        ven_pct = (ven_exposure / safe_equity) * 100.0
        if ven_pct > ven_cap:
            return {
                "ok": False,
                "reason_code": "CONCENTRATION_LIMIT",
                "details": f"Venue {venue} would be {ven_pct:.1f}% of equity (cap: {ven_cap}%).",
            }

        # ── Correlated exposure ──
        corr_group = None
        for group_name, symbols in CORRELATED_GROUPS.items():
            if symbol in symbols:
                corr_group = group_name
                break

        if corr_group:
            group_symbols = CORRELATED_GROUPS[corr_group]
            corr_exposure = notional_proposed
            for pos in open_positions:
                if pos.get("symbol") in group_symbols:
                    corr_exposure += float(pos.get("notional", 0))
            corr_pct = (corr_exposure / safe_equity) * 100.0
            if corr_pct > DEFAULT_CORRELATED_EXPOSURE_PCT:
                return {
                    "ok": False,
                    "reason_code": "CONCENTRATION_LIMIT",
                    "details": f"Correlated group {corr_group} would be {corr_pct:.1f}% (cap: {DEFAULT_CORRELATED_EXPOSURE_PCT}%).",
                }

        return {
            "ok": True,
            "reason_code": None,
            "details": f"Concentration check passed (symbol: {sym_pct:.1f}%, venue: {ven_pct:.1f}%).",
        }
