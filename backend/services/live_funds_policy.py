"""
Live-Funds Control Policy
==========================
Hard monetary limits, approval requirements, reconciliation checks, and
audit trail for all real-money (live trading) actions.

This module sits between the live trading engine and actual order placement.
It must be checked for EVERY real-money action.

NEVER modify the paper-trading path — this service only governs live mode.

Usage:
    from services.live_funds_policy import live_funds_policy

    # Before placing a live trade
    ok, violations = await live_funds_policy.check_trade(
        user_id="u123",
        exchange="binance",
        notional_zar=2500.0,
        bot_id="bot456",
    )
    if not ok:
        raise TradingGateError(violations[0])

    # After reconciling exchange balance
    await live_funds_policy.reconcile_exchange_balance(
        user_id="u123",
        exchange="binance",
        reported_balance_zar=18500.0,
        expected_balance_zar=18000.0,
    )
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Tuple

import database as db
import config

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Fund categories
# ---------------------------------------------------------------------------

class FundCategory:
    PAPER     = "paper"      # Simulated paper-trading funds
    LIVE      = "live"       # Real-money trading funds on exchange
    TREASURY  = "treasury"   # Reserve / surplus funds — not actively deployed
    RESERVE   = "reserve"    # Emergency / locked reserve, never traded


# ---------------------------------------------------------------------------
# Policy violation codes
# ---------------------------------------------------------------------------

class LiveFundsViolation:
    MOVEMENT_NOT_ALLOWED     = "live_funds_movement_not_allowed"
    TRADE_SIZE_TOO_LARGE     = "live_trade_size_too_large"
    TRADE_SIZE_TOO_SMALL     = "live_trade_size_too_small"
    EXCHANGE_EXPOSURE_BREACH = "live_exchange_exposure_breach"
    DAILY_LOSS_LIMIT_HIT     = "live_daily_loss_limit_hit"
    DAILY_TRANSFER_LIMIT_HIT = "live_daily_transfer_limit_hit"
    REQUIRES_ADMIN_APPROVAL  = "live_requires_admin_approval"
    DESTINATION_NOT_WHITELISTED = "live_destination_not_whitelisted"
    RECONCILIATION_FAILED    = "live_reconciliation_failed"
    PAPER_FUNDS_ONLY         = "paper_funds_only_no_live_allowed"
    INSUFFICIENT_BALANCE     = "live_insufficient_balance"


# ---------------------------------------------------------------------------
# Live Funds Policy service
# ---------------------------------------------------------------------------

class LiveFundsPolicyService:
    """
    Enforces all monetary hard limits for live-money trading.

    Every check returns (ok: bool, violations: List[str]) so the caller
    can decide how to proceed without catching exceptions for control flow.

    All violations and approvals are written to the audit_logs_collection
    so there is a complete, tamper-evident record of every live-money decision.
    """

    # ────────────────────────────────────────────────────────────────── guards

    def _is_live_movement_globally_allowed(self) -> bool:
        """
        Both ENABLE_LIVE_TRADING and LIVE_FUNDS_MOVEMENT_ALLOWED must be True.
        LIVE_FUNDS_MOVEMENT_ALLOWED is a separate explicit kill-switch that
        must be manually enabled once the pre-live checklist is satisfied.
        """
        return (
            getattr(config, "ENABLE_LIVE_TRADING", False)
            and getattr(config, "LIVE_FUNDS_MOVEMENT_ALLOWED", False)
        )

    # ──────────────────────────────────────────────────────── trade validation

    async def check_trade(
        self,
        user_id: str,
        exchange: str,
        notional_zar: float,
        bot_id: Optional[str] = None,
        direction: str = "buy",
    ) -> Tuple[bool, List[str]]:
        """
        Validate a proposed live trade against all policy limits.

        Checks (in order):
        1. Global live-funds kill-switch
        2. Per-trade size (min and max in ZAR)
        3. Per-exchange total exposure
        4. Daily loss circuit breaker
        5. Admin-approval threshold

        Returns (allowed, violation_codes).
        """
        violations: List[str] = []

        # 1. Global kill-switch
        if not self._is_live_movement_globally_allowed():
            violations.append(LiveFundsViolation.MOVEMENT_NOT_ALLOWED)
            await self._audit(user_id, "trade_blocked", {
                "exchange": exchange, "notional_zar": notional_zar,
                "bot_id": bot_id, "reason": LiveFundsViolation.MOVEMENT_NOT_ALLOWED,
            })
            return False, violations

        max_size = getattr(config, "LIVE_MAX_TRADE_SIZE_ZAR", 5000.0)
        min_size = getattr(config, "LIVE_MIN_TRADE_SIZE_ZAR", 50.0)

        # 2. Trade size limits
        if notional_zar > max_size:
            violations.append(
                f"{LiveFundsViolation.TRADE_SIZE_TOO_LARGE}: "
                f"{notional_zar:.2f} ZAR > {max_size:.2f} ZAR limit"
            )
        if notional_zar < min_size:
            violations.append(
                f"{LiveFundsViolation.TRADE_SIZE_TOO_SMALL}: "
                f"{notional_zar:.2f} ZAR < {min_size:.2f} ZAR minimum"
            )

        # 3. Per-exchange exposure
        exposure_ok, exposure_violations = await self._check_exchange_exposure(
            user_id, exchange, notional_zar
        )
        violations.extend(exposure_violations)

        # 4. Daily loss circuit breaker
        loss_ok, loss_violations = await self._check_daily_loss(user_id)
        violations.extend(loss_violations)

        # 5. Admin approval threshold
        approval_threshold = getattr(config, "LIVE_REQUIRE_ADMIN_APPROVAL_ABOVE_ZAR", 10000.0)
        if notional_zar > approval_threshold:
            violations.append(
                f"{LiveFundsViolation.REQUIRES_ADMIN_APPROVAL}: "
                f"{notional_zar:.2f} ZAR exceeds {approval_threshold:.2f} ZAR approval threshold"
            )

        allowed = len(violations) == 0

        await self._audit(user_id, "trade_check", {
            "exchange": exchange,
            "notional_zar": notional_zar,
            "bot_id": bot_id,
            "direction": direction,
            "allowed": allowed,
            "violations": violations,
        })

        if not allowed:
            logger.warning(
                "[LIVE-FUNDS] Trade BLOCKED | user=%s | exchange=%s | %.2f ZAR | %s",
                user_id[:8], exchange, notional_zar, violations,
            )
        else:
            logger.info(
                "[LIVE-FUNDS] Trade ALLOWED | user=%s | exchange=%s | %.2f ZAR",
                user_id[:8], exchange, notional_zar,
            )

        return allowed, violations

    # ───────────────────────────────────────────────── transfer / withdrawal

    async def check_transfer(
        self,
        user_id: str,
        destination_address: str,
        amount_zar: float,
        exchange: str,
        currency: str = "ZAR",
    ) -> Tuple[bool, List[str]]:
        """
        Validate a proposed real-money withdrawal/transfer.

        Checks:
        1. Global kill-switch
        2. Destination is whitelisted
        3. Daily transfer limit
        4. Admin approval threshold
        """
        violations: List[str] = []

        if not self._is_live_movement_globally_allowed():
            violations.append(LiveFundsViolation.MOVEMENT_NOT_ALLOWED)
            return False, violations

        # Whitelist check
        whitelist_ok, whitelist_violations = await self._check_whitelist(
            user_id, destination_address
        )
        violations.extend(whitelist_violations)

        # Daily transfer limit
        transfer_ok, transfer_violations = await self._check_daily_transfer_limit(
            user_id, amount_zar
        )
        violations.extend(transfer_violations)

        # Admin approval
        approval_threshold = getattr(config, "LIVE_REQUIRE_ADMIN_APPROVAL_ABOVE_ZAR", 10000.0)
        if amount_zar > approval_threshold:
            violations.append(
                f"{LiveFundsViolation.REQUIRES_ADMIN_APPROVAL}: "
                f"{amount_zar:.2f} ZAR exceeds {approval_threshold:.2f} ZAR threshold"
            )

        allowed = len(violations) == 0

        await self._audit(user_id, "transfer_check", {
            "exchange": exchange,
            "destination": destination_address[:12] + "...",
            "amount_zar": amount_zar,
            "currency": currency,
            "allowed": allowed,
            "violations": violations,
        })

        return allowed, violations

    # ─────────────────────────────────────────────────────── reconciliation

    async def reconcile_exchange_balance(
        self,
        user_id: str,
        exchange: str,
        reported_balance_zar: float,
        expected_balance_zar: float,
    ) -> Dict[str, Any]:
        """
        Compare the exchange's reported balance against our internal ledger.

        If the discrepancy exceeds LIVE_RECONCILIATION_TOLERANCE_PCT, emits
        a reconciliation alert and writes to audit log.

        Returns a dict with:
        - reconciled: bool
        - discrepancy_pct: float
        - discrepancy_zar: float
        - action_taken: str
        """
        if expected_balance_zar == 0:
            return {
                "reconciled": True,
                "discrepancy_pct": 0.0,
                "discrepancy_zar": 0.0,
                "action_taken": "skipped_zero_expected",
            }

        diff_zar = abs(reported_balance_zar - expected_balance_zar)
        diff_pct = (diff_zar / max(expected_balance_zar, 1.0)) * 100.0
        tolerance = getattr(config, "LIVE_RECONCILIATION_TOLERANCE_PCT", 0.5)

        reconciled = diff_pct <= tolerance

        result: Dict[str, Any] = {
            "reconciled": reconciled,
            "discrepancy_pct": round(diff_pct, 4),
            "discrepancy_zar": round(diff_zar, 2),
            "reported_balance_zar": reported_balance_zar,
            "expected_balance_zar": expected_balance_zar,
            "tolerance_pct": tolerance,
            "action_taken": "none",
        }

        if not reconciled:
            result["action_taken"] = "reconciliation_alert"
            logger.error(
                "[LIVE-FUNDS] RECONCILIATION MISMATCH | user=%s | exchange=%s | "
                "reported=%.2f ZAR | expected=%.2f ZAR | diff=%.2f ZAR (%.2f%%)",
                user_id[:8], exchange,
                reported_balance_zar, expected_balance_zar, diff_zar, diff_pct,
            )
            await self._audit(user_id, "reconciliation_mismatch", {
                "exchange": exchange,
                **result,
            })

            # Emit alert if realtime manager available
            try:
                from websocket_manager import manager
                await manager.send_to_user(user_id, {
                    "type": "live_funds_alert",
                    "severity": "critical",
                    "exchange": exchange,
                    "message": (
                        f"Reconciliation mismatch on {exchange}: "
                        f"reported {reported_balance_zar:.2f} ZAR vs "
                        f"expected {expected_balance_zar:.2f} ZAR "
                        f"({diff_pct:.2f}% difference)"
                    ),
                    "discrepancy_zar": diff_zar,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })
            except Exception as ws_err:
                logger.debug("Reconciliation alert WS broadcast failed (non-fatal): %s", ws_err)
        else:
            await self._audit(user_id, "reconciliation_ok", {
                "exchange": exchange,
                **result,
            })

        return result

    # ───────────────────────────────────────────────────────── daily summary

    async def get_daily_summary(self, user_id: str) -> Dict[str, Any]:
        """
        Return today's live-funds usage vs limits for admin/dashboard display.
        """
        today_start = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        today_iso = today_start.isoformat()

        daily_loss = await self._get_daily_loss(user_id, today_iso)
        daily_transfer = await self._get_daily_transfer_total(user_id, today_iso)

        return {
            "date_utc": today_iso,
            "movement_globally_allowed": self._is_live_movement_globally_allowed(),
            "limits": {
                "max_trade_size_zar":          getattr(config, "LIVE_MAX_TRADE_SIZE_ZAR", 5000.0),
                "min_trade_size_zar":          getattr(config, "LIVE_MIN_TRADE_SIZE_ZAR", 50.0),
                "max_exchange_exposure_zar":   getattr(config, "LIVE_MAX_EXCHANGE_EXPOSURE_ZAR", 20000.0),
                "max_daily_loss_zar":          getattr(config, "LIVE_MAX_DAILY_LOSS_ZAR", 2000.0),
                "max_daily_transfer_zar":      getattr(config, "LIVE_MAX_DAILY_TRANSFER_ZAR", 10000.0),
                "admin_approval_above_zar":    getattr(config, "LIVE_REQUIRE_ADMIN_APPROVAL_ABOVE_ZAR", 10000.0),
                "reconciliation_tolerance_pct": getattr(config, "LIVE_RECONCILIATION_TOLERANCE_PCT", 0.5),
            },
            "today": {
                "realized_loss_zar":   round(daily_loss, 2),
                "transferred_out_zar": round(daily_transfer, 2),
            },
            "circuit_breakers": {
                "daily_loss_triggered":    daily_loss >= getattr(config, "LIVE_MAX_DAILY_LOSS_ZAR", 2000.0),
                "daily_transfer_exceeded": daily_transfer >= getattr(config, "LIVE_MAX_DAILY_TRANSFER_ZAR", 10000.0),
            },
            "fund_categories": {
                "paper":    FundCategory.PAPER,
                "live":     FundCategory.LIVE,
                "treasury": FundCategory.TREASURY,
                "reserve":  FundCategory.RESERVE,
            },
        }

    # ──────────────────────────────────────────────────── internal helpers

    async def _check_exchange_exposure(
        self, user_id: str, exchange: str, new_notional_zar: float
    ) -> Tuple[bool, List[str]]:
        """Sum current live positions on the exchange + proposed trade."""
        violations: List[str] = []
        try:
            if db.bots_collection is None:
                return True, violations

            bots = await db.bots_collection.find(
                {"user_id": user_id, "exchange": exchange, "trading_mode": "live"},
                {"_id": 0, "current_capital": 1},
            ).to_list(100)

            current_exposure = sum(float(b.get("current_capital", 0) or 0) for b in bots)
            total_exposure = current_exposure + new_notional_zar
            max_exposure = getattr(config, "LIVE_MAX_EXCHANGE_EXPOSURE_ZAR", 20000.0)

            if total_exposure > max_exposure:
                violations.append(
                    f"{LiveFundsViolation.EXCHANGE_EXPOSURE_BREACH}: "
                    f"{total_exposure:.2f} ZAR would exceed {max_exposure:.2f} ZAR on {exchange}"
                )
        except Exception as err:
            logger.warning("Exchange exposure check failed (non-fatal): %s", err)
        return len(violations) == 0, violations

    async def _check_daily_loss(self, user_id: str) -> Tuple[bool, List[str]]:
        """Check if the daily loss circuit breaker has been triggered."""
        violations: List[str] = []
        try:
            today_iso = datetime.now(timezone.utc).replace(
                hour=0, minute=0, second=0, microsecond=0
            ).isoformat()
            daily_loss = await self._get_daily_loss(user_id, today_iso)
            max_loss = getattr(config, "LIVE_MAX_DAILY_LOSS_ZAR", 2000.0)
            if daily_loss >= max_loss:
                violations.append(
                    f"{LiveFundsViolation.DAILY_LOSS_LIMIT_HIT}: "
                    f"{daily_loss:.2f} ZAR daily loss >= {max_loss:.2f} ZAR limit"
                )
        except Exception as err:
            logger.warning("Daily loss check failed (non-fatal): %s", err)
        return len(violations) == 0, violations

    async def _get_daily_loss(self, user_id: str, today_iso: str) -> float:
        """Sum realized losses from live trades today (negative P&L only)."""
        try:
            if db.trades_collection is None:
                return 0.0
            docs = await db.trades_collection.find(
                {
                    "user_id": user_id,
                    "trading_mode": "live",
                    "status": "closed",
                    "created_at": {"$gte": today_iso},
                    "profit_loss": {"$lt": 0},
                },
                {"_id": 0, "profit_loss": 1},
            ).to_list(1000)
            return abs(sum(float(d.get("profit_loss", 0) or 0) for d in docs))
        except Exception as err:
            logger.warning("Daily loss query failed (non-fatal): %s", err)
            return 0.0

    async def _check_daily_transfer_limit(
        self, user_id: str, amount_zar: float
    ) -> Tuple[bool, List[str]]:
        """Check if today's transfer total + proposed amount exceeds the daily cap."""
        violations: List[str] = []
        try:
            today_iso = datetime.now(timezone.utc).replace(
                hour=0, minute=0, second=0, microsecond=0
            ).isoformat()
            today_total = await self._get_daily_transfer_total(user_id, today_iso)
            max_transfer = getattr(config, "LIVE_MAX_DAILY_TRANSFER_ZAR", 10000.0)
            if today_total + amount_zar > max_transfer:
                violations.append(
                    f"{LiveFundsViolation.DAILY_TRANSFER_LIMIT_HIT}: "
                    f"today {today_total:.2f} + {amount_zar:.2f} ZAR would exceed "
                    f"{max_transfer:.2f} ZAR daily limit"
                )
        except Exception as err:
            logger.warning("Daily transfer check failed (non-fatal): %s", err)
        return len(violations) == 0, violations

    async def _get_daily_transfer_total(self, user_id: str, today_iso: str) -> float:
        """Sum all outbound live transfers today."""
        try:
            if db.audit_logs_collection is None:
                return 0.0
            docs = await db.audit_logs_collection.find(
                {
                    "user_id": user_id,
                    "action": "transfer_check",
                    "allowed": True,
                    "timestamp": {"$gte": today_iso},
                },
                {"_id": 0, "amount_zar": 1},
            ).to_list(1000)
            return sum(float(d.get("amount_zar", 0) or 0) for d in docs)
        except Exception as err:
            logger.warning("Daily transfer total query failed (non-fatal): %s", err)
            return 0.0

    async def _check_whitelist(
        self, user_id: str, destination_address: str
    ) -> Tuple[bool, List[str]]:
        """Verify withdrawal destination is in the user's approved whitelist."""
        violations: List[str] = []
        try:
            # wallet_addresses_collection is used by routes/wallet_addresses.py
            if db.wallet_addresses_collection is not None:
                doc = await db.wallet_addresses_collection.find_one(
                    {
                        "user_id": user_id,
                        "address": destination_address,
                        "status": "approved",
                    },
                    {"_id": 0, "address": 1},
                )
                if not doc:
                    violations.append(
                        f"{LiveFundsViolation.DESTINATION_NOT_WHITELISTED}: "
                        f"address {destination_address[:12]}... is not in approved whitelist"
                    )
        except Exception as err:
            # Fail-safe: block if whitelist check errors
            logger.error("Whitelist check error — blocking transfer: %s", err)
            violations.append(
                f"{LiveFundsViolation.DESTINATION_NOT_WHITELISTED}: "
                f"whitelist check unavailable — transfer blocked for safety"
            )
        return len(violations) == 0, violations

    # ─────────────────────────────────────────────────────────── audit trail

    async def _audit(
        self,
        user_id: str,
        action: str,
        details: Dict[str, Any],
    ) -> None:
        """
        Write an immutable audit record for every live-funds policy decision.

        Uses audit_logs_collection. Never raises — a failed audit write must
        not block the trade decision.
        """
        try:
            if db.audit_logs_collection is None:
                logger.warning("[LIVE-FUNDS] audit_logs_collection unavailable — record not persisted")
                return

            await db.audit_logs_collection.insert_one({
                "user_id":    user_id,
                "category":   "live_funds_policy",
                "action":     action,
                "timestamp":  datetime.now(timezone.utc).isoformat(),
                **details,
            })
        except Exception as err:
            logger.error("[LIVE-FUNDS] Audit write failed (non-fatal): %s", err)


# Module-level singleton
live_funds_policy = LiveFundsPolicyService()

__all__ = [
    "live_funds_policy",
    "LiveFundsPolicyService",
    "LiveFundsViolation",
    "FundCategory",
]
