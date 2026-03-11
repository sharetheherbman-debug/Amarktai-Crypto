"""
SlippageEstimator – book-sweep VWAP estimator from L2 depth.

No fake slippage=0 unless depth truly supports it.
Tracks calibration buckets by venue/symbol/order_type/notional_bucket.
"""
import logging
import time

logger = logging.getLogger(__name__)

# Notional buckets for calibration (in quote currency)
NOTIONAL_BUCKETS = [500, 2000, 10000, 50000, 200000]

MIN_SLIPPAGE_BPS = 2.0


def _bucket_label(notional: float) -> str:
    for b in NOTIONAL_BUCKETS:
        if notional <= b:
            return f"<={b}"
    return f">{NOTIONAL_BUCKETS[-1]}"


class SlippageEstimator:
    """
    Estimates slippage from L2 order-book depth using VWAP sweep.
    Maintains calibration telemetry for future learning.
    """

    def __init__(self):
        # In-memory calibration store: {(venue, symbol, side, bucket): [estimates]}
        self._calibration: dict = {}

    def estimate(
        self,
        venue: str,
        symbol: str,
        side: str,
        notional: float,
        order_book: dict = None,
        volatility: float = None,
    ) -> dict:
        """
        Estimate slippage in BPS for a proposed order.

        Returns:
            {
                slippage_bps: float,
                method: str,      # "vwap_sweep" | "heuristic"
                depth_sufficient: bool,
                levels_consumed: int,
                book_total_notional: float,
            }
        """
        if order_book and isinstance(order_book, dict):
            levels = order_book.get("asks" if side == "buy" else "bids", [])
            if levels:
                return self._sweep(venue, symbol, side, notional, levels)

        return self._heuristic(venue, symbol, side, notional, volatility)

    def _sweep(self, venue, symbol, side, notional, levels) -> dict:
        """VWAP sweep across order-book levels."""
        if not levels or notional <= 0:
            return {
                "slippage_bps": 8.0,
                "method": "heuristic",
                "depth_sufficient": False,
                "levels_consumed": 0,
                "book_total_notional": 0.0,
            }

        filled_notional = 0.0
        filled_base = 0.0
        top_price = None
        levels_consumed = 0
        book_total = 0.0

        for lvl in levels:
            price, qty = self._parse_level(lvl)
            if price <= 0 or qty <= 0:
                continue

            level_notional = price * qty
            book_total += level_notional

            if top_price is None:
                top_price = price

            remaining = notional - filled_notional
            if remaining <= 0:
                break

            take_notional = min(level_notional, remaining)
            take_base = take_notional / price
            filled_notional += take_notional
            filled_base += take_base
            levels_consumed += 1

        depth_sufficient = filled_notional >= notional
        if filled_base <= 0 or top_price is None or top_price <= 0:
            return {
                "slippage_bps": 15.0,
                "method": "vwap_sweep",
                "depth_sufficient": False,
                "levels_consumed": levels_consumed,
                "book_total_notional": round(book_total, 2),
            }

        # VWAP = total cost / total base quantity
        vwap = filled_notional / filled_base
        slip_bps = abs(vwap - top_price) / top_price * 10000.0

        if not depth_sufficient:
            slip_bps = max(slip_bps, 15.0)

        slip_bps = max(slip_bps, MIN_SLIPPAGE_BPS)
        slip_bps = min(slip_bps, 50.0)  # hard cap

        # Record for calibration
        self._record_estimate(venue, symbol, side, notional, slip_bps)

        return {
            "slippage_bps": round(slip_bps, 2),
            "method": "vwap_sweep",
            "depth_sufficient": depth_sufficient,
            "levels_consumed": levels_consumed,
            "book_total_notional": round(book_total, 2),
        }

    def _heuristic(self, venue, symbol, side, notional, volatility) -> dict:
        """Heuristic fallback when no depth data available."""
        base = 5.0
        if volatility and volatility > 0:
            base += min(volatility * 100, 10.0)
        if notional > 100000:
            base += 4.0
        elif notional > 50000:
            base += 2.0
        elif notional > 10000:
            base += 1.0

        base = max(base, MIN_SLIPPAGE_BPS)
        return {
            "slippage_bps": round(base, 2),
            "method": "heuristic",
            "depth_sufficient": False,
            "levels_consumed": 0,
            "book_total_notional": 0.0,
        }

    def _record_estimate(self, venue, symbol, side, notional, slip_bps):
        """Record estimate for calibration telemetry."""
        bucket = _bucket_label(notional)
        key = (venue.lower(), symbol, side, bucket)
        if key not in self._calibration:
            self._calibration[key] = []
        entries = self._calibration[key]
        entries.append({"slip_bps": slip_bps, "ts": time.time()})
        # Keep last 100 per bucket
        if len(entries) > 100:
            self._calibration[key] = entries[-100:]

    def record_realized(self, venue, symbol, side, notional, realized_slip_bps):
        """Hook for realized fill data to improve future estimates."""
        bucket = _bucket_label(notional)
        key = (venue.lower(), symbol, side, bucket)
        if key not in self._calibration:
            self._calibration[key] = []
        self._calibration[key].append({
            "slip_bps": realized_slip_bps,
            "ts": time.time(),
            "realized": True,
        })

    def get_calibration_summary(self, venue=None, symbol=None) -> dict:
        """Return calibration stats for diagnostics."""
        summary = {}
        for key, entries in self._calibration.items():
            v, s, side, bucket = key
            if venue and v != venue.lower():
                continue
            if symbol and s != symbol:
                continue
            vals = [e["slip_bps"] for e in entries]
            realized = [e["slip_bps"] for e in entries if e.get("realized")]
            summary[f"{v}:{s}:{side}:{bucket}"] = {
                "count": len(vals),
                "mean_bps": round(sum(vals) / len(vals), 2) if vals else 0,
                "realized_count": len(realized),
                "realized_mean_bps": round(sum(realized) / len(realized), 2) if realized else 0,
            }
        return summary

    @staticmethod
    def _parse_level(lvl):
        """Parse a single order-book level."""
        if isinstance(lvl, (list, tuple)) and len(lvl) >= 2:
            return float(lvl[0]), float(lvl[1])
        if isinstance(lvl, dict):
            return (
                float(lvl.get("price", 0)),
                float(lvl.get("qty", lvl.get("quantity", lvl.get("amount", 0)))),
            )
        return 0.0, 0.0
