"""
Contradiction Detector — Flags impossible system states

Checks for logical contradictions that indicate data corruption,
race conditions, or configuration errors. Contradictions surface in:
  - /api/admin/truth/summary
  - /api/diagnostics/go-live
  - Evidence pack report
"""

from typing import Dict, List, Any
import logging

logger = logging.getLogger(__name__)

# Contradiction severity levels
SEVERITY_CRITICAL = "critical"  # Immediate action required
SEVERITY_WARNING = "warning"    # Should be investigated
SEVERITY_INFO = "info"          # Informational anomaly


def detect_contradictions(
    bots: Dict[str, Any],
    wallet: Dict[str, Any],
    risk: Dict[str, Any],
    scheduler: Dict[str, Any],
    exchanges: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """
    Detect impossible/contradictory states across subsystems.

    Returns a list of contradiction dicts:
      {
        "id": str,           # unique contradiction identifier
        "severity": str,     # critical / warning / info
        "description": str,  # human-readable description
        "expected": str,     # what should be true
        "actual": str,       # what was found
        "subsystems": list,  # affected subsystem names
      }
    """
    contradictions: List[Dict[str, Any]] = []

    # ── 1. Eligible bots but scheduler stale ────────────────────────────
    if bots.get("eligible_count", 0) > 0 and scheduler.get("stale"):
        contradictions.append({
            "id": "ELIGIBLE_BOTS_NO_TICK",
            "severity": SEVERITY_CRITICAL,
            "description": "Eligible bots exist but scheduler has not ticked recently",
            "expected": "Scheduler should tick within 120s when eligible bots exist",
            "actual": f"eligible_count={bots['eligible_count']}, last_tick={scheduler.get('last_tick')}, lag={scheduler.get('lag_seconds')}s",
            "subsystems": ["BOT_ELIGIBILITY", "PAPER_ENGINE"],
        })

    # ── 2. Wallet: allocated > total ────────────────────────────────────
    if wallet.get("reserved", 0) > wallet.get("total", 0) + 0.01:
        contradictions.append({
            "id": "ALLOCATED_EXCEEDS_TOTAL",
            "severity": SEVERITY_CRITICAL,
            "description": "Wallet reserved/allocated exceeds total balance",
            "expected": "reserved <= total",
            "actual": f"reserved={wallet.get('reserved')}, total={wallet.get('total')}",
            "subsystems": ["WALLET_RECONCILIATION"],
        })

    # ── 3. Wallet: available < 0 ────────────────────────────────────────
    if wallet.get("negative_balance"):
        contradictions.append({
            "id": "NEGATIVE_BALANCE",
            "severity": SEVERITY_CRITICAL,
            "description": "Wallet has negative available or reserved balance",
            "expected": "available >= 0 and reserved >= 0",
            "actual": f"available={wallet.get('available')}, reserved={wallet.get('reserved')}",
            "subsystems": ["WALLET_RECONCILIATION"],
        })

    # ── 4. Equity peak mismatch ─────────────────────────────────────────
    if risk.get("peak_equity", 0) > 0 and risk.get("total_equity", 0) == 0:
        # Peak equity recorded but current equity is zero while bots still have capital
        if bots.get("total_bots", 0) > 0:
            contradictions.append({
                "id": "EQUITY_PEAK_MISMATCH",
                "severity": SEVERITY_WARNING,
                "description": "Peak equity > 0 but current equity is 0 while bots exist",
                "expected": "If bots exist with capital, total_equity should be > 0",
                "actual": f"peak_equity={risk.get('peak_equity')}, total_equity={risk.get('total_equity')}, bots={bots.get('total_bots')}",
                "subsystems": ["RISK_BASELINES", "BOT_ELIGIBILITY"],
            })

    # ── 5. Drawdown exceeded but no lock ────────────────────────────────
    if risk.get("drawdown_pct", 0) > 15 and bots.get("eligible_count", 0) > 0:
        contradictions.append({
            "id": "DRAWDOWN_NO_LOCK",
            "severity": SEVERITY_WARNING,
            "description": "Drawdown exceeds 15% but eligible bots still trading",
            "expected": "Circuit breaker should lock bots when drawdown > 15%",
            "actual": f"drawdown_pct={risk.get('drawdown_pct')}, eligible_bots={bots.get('eligible_count')}",
            "subsystems": ["RISK_BASELINES", "BOT_ELIGIBILITY"],
        })

    # ── 6. Bots marked active but not eligible ──────────────────────────
    ineligible_reasons = bots.get("ineligible_reasons", {})
    if bots.get("total_bots", 0) > 0 and bots.get("eligible_count", 0) == 0 and bots.get("ineligible_count", 0) > 0:
        # All bots ineligible — check if they're all supposed to be
        all_reasons = []
        for reasons in ineligible_reasons.values():
            all_reasons.extend(reasons)
        if not all_reasons:
            contradictions.append({
                "id": "BOTS_INELIGIBLE_NO_REASON",
                "severity": SEVERITY_WARNING,
                "description": "All bots are ineligible but no reason codes provided",
                "expected": "Ineligible bots should have reason codes",
                "actual": f"total={bots.get('total_bots')}, eligible=0, reasons=empty",
                "subsystems": ["BOT_ELIGIBILITY", "TRUTH_KERNEL"],
            })

    # ── 7. Scheduler says running but last_tick is stale ────────────────
    if scheduler.get("running") and scheduler.get("stale"):
        contradictions.append({
            "id": "SCHEDULER_RUNNING_BUT_STALE",
            "severity": SEVERITY_WARNING,
            "description": "Scheduler reports running=true but last tick is stale",
            "expected": "If running, last_tick should be within 120s",
            "actual": f"running={scheduler.get('running')}, lag={scheduler.get('lag_seconds')}s",
            "subsystems": ["PAPER_ENGINE"],
        })

    # ── 8. Balance check failed ─────────────────────────────────────────
    if not wallet.get("balance_check", True):
        contradictions.append({
            "id": "BALANCE_MISMATCH",
            "severity": SEVERITY_CRITICAL,
            "description": "Wallet total != available + reserved",
            "expected": "total == available + reserved",
            "actual": f"total={wallet.get('total')}, available={wallet.get('available')}, reserved={wallet.get('reserved')}",
            "subsystems": ["WALLET_RECONCILIATION"],
        })

    return contradictions
