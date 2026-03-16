"""
Execution Quality Gate — bot-type-aware and exchange-aware pre-entry filter.

This module adds a second layer of quality screening on top of
TradeFeasibilityGate.  Where TradeFeasibilityGate checks hard economic
thresholds (edge, cost, confidence floor), the ExecutionQualityGate checks
*execution realism* — can we actually realize this edge given current
spread and slippage conditions, and does the signal consensus support entry
under the active policy pack?

Entry is rejected when ANY of the following apply:
  1. Spread too large for expected move under this policy pack
  2. Slippage estimate would consume too much of projected edge
  3. Projected net profit after all costs is below pack's multiplier × floor
  4. Signal consensus count is below pack minimum
  5. Regime confidence is too low for the policy pack
  6. Market quality score is below pack minimum

All rejections produce structured reason codes with diagnostics metadata.

Usage
-----
    from services.trading_brain_v2.quality_gates import ExecutionQualityGate
    gate = ExecutionQualityGate()
    result = gate.evaluate(
        policy_pack=pack,
        spread_pct=0.12,
        estimated_slippage_pct=0.05,
        projected_net_profit_quote=2.50,
        min_profit_required_quote=1.00,
        consensus_sources=2,
        regime_confidence=0.68,
        market_quality=0.45,
        bot_type="normal",
        exchange="luno",
    )
    # result["approved"]        → True / False
    # result["reason_code"]     → ReasonCodes constant
    # result["pack_name"]       → "balanced"
    # result["diagnostics"]     → dict with per-check detail
"""
from __future__ import annotations

import logging
from typing import Dict, Optional

from .reason_codes import ReasonCodes
from .policy_packs import get_policy_pack, get_default_pack_for_bot_type, POLICY_PACK_VERSION

logger = logging.getLogger(__name__)

# ── Reason codes for execution quality gate ───────────────────────────────
# Reference ReasonCodes class constants directly to avoid duplication.
_RC_SPREAD_TOO_WIDE_FOR_PACK      = ReasonCodes.SPREAD_EXCEEDS_PACK_LIMIT
_RC_SLIPPAGE_TOO_HIGH_FOR_PACK    = ReasonCodes.SLIPPAGE_EXCEEDS_PACK_LIMIT
_RC_PROFIT_BELOW_PACK_FLOOR       = ReasonCodes.PROFIT_BELOW_PACK_FLOOR
_RC_CONSENSUS_TOO_WEAK            = ReasonCodes.CONSENSUS_TOO_WEAK
_RC_REGIME_CONF_TOO_LOW_FOR_PACK  = ReasonCodes.REGIME_CONF_TOO_LOW_FOR_PACK
_RC_MARKET_QUALITY_TOO_LOW        = ReasonCodes.MARKET_QUALITY_TOO_LOW
_RC_APPROVED                      = ReasonCodes.ENTRY_APPROVED


class ExecutionQualityGate:
    """
    Bot-type-aware execution quality gate.

    Checks spread, slippage, profit adequacy, consensus, regime confidence,
    and market quality against the active policy pack thresholds.
    """

    def evaluate(
        self,
        *,
        policy_pack: Dict,
        spread_pct: float,
        estimated_slippage_pct: float = 0.0,
        projected_net_profit_quote: float = 0.0,
        min_profit_required_quote: float = 0.0,
        consensus_sources: int = 0,
        regime_confidence: float = 1.0,
        market_quality: float = 1.0,
        bot_type: str = "normal",
        exchange: str = "",
    ) -> Dict:
        """
        Evaluate execution quality against the active policy pack.

        Parameters
        ----------
        policy_pack : dict
            A policy pack returned by get_policy_pack() or select_pack_for_bot()
        spread_pct : float
            Current bid-ask spread as a percentage of mid price
        estimated_slippage_pct : float
            Estimated fill slippage as a percentage
        projected_net_profit_quote : float
            Projected net profit in quote currency (after fees + costs)
        min_profit_required_quote : float
            Canonical minimum profit from compute_min_net_profit_required()
        consensus_sources : int
            Number of signal sources in agreement at entry
        regime_confidence : float
            Current regime confidence score (0–1)
        market_quality : float
            Aggregated market quality score (0–1)
        bot_type : str
            Bot strategy type
        exchange : str
            Exchange name

        Returns
        -------
        dict:
            approved            — bool
            reason_code         — str (machine-readable)
            reason_text         — str (human-readable)
            pack_name           — str
            pack_version        — str
            diagnostics         — dict with per-check detail
            all_checks          — list of {check, passed, threshold, actual}
        """
        pack_name = policy_pack.get("pack_name", "unknown")
        pack_ver = policy_pack.get("pack_version", POLICY_PACK_VERSION)

        # ── Pack thresholds ──
        max_spread     = float(policy_pack.get("max_spread_pct", 0.35))
        max_slip       = float(policy_pack.get("max_slippage_pct", 0.20))
        min_conf       = float(policy_pack.get("min_entry_confidence", 0.40))
        min_quality    = float(policy_pack.get("min_market_quality", 0.30))
        min_consensus  = int(policy_pack.get("min_consensus_sources", 1))
        pack_mult      = float(policy_pack.get("min_projected_net_profit_multiplier", 1.5))

        safe_spread  = float(spread_pct or 0.0)
        safe_slip    = float(estimated_slippage_pct or 0.0)
        safe_proj    = float(projected_net_profit_quote or 0.0)
        safe_min     = float(min_profit_required_quote or 0.0)
        safe_conf    = float(regime_confidence or 0.0)
        safe_quality = float(market_quality or 0.0)
        safe_consens = int(consensus_sources or 0)

        # Pack-specific profit floor = canonical floor × pack multiplier
        pack_profit_floor = safe_min * pack_mult

        checks = []

        # ── 1. Spread check ──
        spread_ok = safe_spread <= max_spread
        checks.append({
            "check":     "spread",
            "passed":    spread_ok,
            "threshold": max_spread,
            "actual":    safe_spread,
            "unit":      "pct",
        })
        if not spread_ok:
            return self._reject(
                _RC_SPREAD_TOO_WIDE_FOR_PACK,
                f"Spread {safe_spread:.3f}% exceeds pack '{pack_name}' limit {max_spread:.3f}%.",
                pack_name, pack_ver, checks,
                spread=safe_spread, max_spread=max_spread,
            )

        # ── 2. Slippage check ──
        slip_ok = safe_slip <= max_slip
        checks.append({
            "check":     "slippage",
            "passed":    slip_ok,
            "threshold": max_slip,
            "actual":    safe_slip,
            "unit":      "pct",
        })
        if not slip_ok:
            return self._reject(
                _RC_SLIPPAGE_TOO_HIGH_FOR_PACK,
                f"Estimated slippage {safe_slip:.3f}% exceeds pack '{pack_name}' limit {max_slip:.3f}%.",
                pack_name, pack_ver, checks,
                slippage=safe_slip, max_slippage=max_slip,
            )

        # ── 3. Pack profit floor check ──
        profit_ok = safe_proj >= pack_profit_floor
        checks.append({
            "check":     "pack_profit_floor",
            "passed":    profit_ok,
            "threshold": pack_profit_floor,
            "actual":    safe_proj,
            "unit":      "quote",
            "multiplier": pack_mult,
        })
        if not profit_ok:
            return self._reject(
                _RC_PROFIT_BELOW_PACK_FLOOR,
                (
                    f"Projected profit {safe_proj:.4f} < pack '{pack_name}' floor "
                    f"{pack_profit_floor:.4f} ({pack_mult:.1f}× min={safe_min:.4f})."
                ),
                pack_name, pack_ver, checks,
                projected=safe_proj, floor=pack_profit_floor, min_required=safe_min,
            )

        # ── 4. Consensus check ──
        consensus_ok = safe_consens >= min_consensus
        checks.append({
            "check":     "consensus",
            "passed":    consensus_ok,
            "threshold": min_consensus,
            "actual":    safe_consens,
            "unit":      "sources",
        })
        if not consensus_ok:
            return self._reject(
                _RC_CONSENSUS_TOO_WEAK,
                f"Consensus {safe_consens} sources < pack '{pack_name}' minimum {min_consensus}.",
                pack_name, pack_ver, checks,
                consensus=safe_consens, min_consensus=min_consensus,
            )

        # ── 5. Regime confidence check ──
        conf_ok = safe_conf >= min_conf
        checks.append({
            "check":     "regime_confidence",
            "passed":    conf_ok,
            "threshold": min_conf,
            "actual":    safe_conf,
            "unit":      "score",
        })
        if not conf_ok:
            return self._reject(
                _RC_REGIME_CONF_TOO_LOW_FOR_PACK,
                f"Regime confidence {safe_conf:.2f} < pack '{pack_name}' minimum {min_conf:.2f}.",
                pack_name, pack_ver, checks,
                regime_confidence=safe_conf, min_confidence=min_conf,
            )

        # ── 6. Market quality check ──
        quality_ok = safe_quality >= min_quality
        checks.append({
            "check":     "market_quality",
            "passed":    quality_ok,
            "threshold": min_quality,
            "actual":    safe_quality,
            "unit":      "score",
        })
        if not quality_ok:
            return self._reject(
                _RC_MARKET_QUALITY_TOO_LOW,
                f"Market quality {safe_quality:.2f} < pack '{pack_name}' minimum {min_quality:.2f}.",
                pack_name, pack_ver, checks,
                market_quality=safe_quality, min_quality=min_quality,
            )

        # ── All checks passed ──
        return {
            "approved":    True,
            "reason_code": _RC_APPROVED,
            "reason_text": (
                f"All execution quality checks passed for pack '{pack_name}'."
            ),
            "pack_name":   pack_name,
            "pack_version": pack_ver,
            "diagnostics": {
                "spread_pct":             safe_spread,
                "slippage_pct":           safe_slip,
                "projected_profit":       safe_proj,
                "pack_profit_floor":      pack_profit_floor,
                "consensus_sources":      safe_consens,
                "regime_confidence":      safe_conf,
                "market_quality":         safe_quality,
            },
            "all_checks": checks,
        }

    # ── Internal helpers ──

    @staticmethod
    def _reject(
        reason_code: str,
        reason_text: str,
        pack_name: str,
        pack_version: str,
        checks: list,
        **extra,
    ) -> Dict:
        diagnostics = dict(extra)
        diagnostics["checks_at_reject"] = len(checks)
        diagnostics["last_check"] = checks[-1] if checks else {}
        return {
            "approved":     False,
            "reason_code":  reason_code,
            "reason_text":  reason_text,
            "pack_name":    pack_name,
            "pack_version": pack_version,
            "diagnostics":  diagnostics,
            "all_checks":   checks,
        }
