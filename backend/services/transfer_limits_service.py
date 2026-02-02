"""
Transfer Limits Enforcement Service

Enforces per-transaction, daily, and monthly transfer limits for wallet transfers.
Tracks usage in MongoDB and ensures limits are not exceeded.
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Optional
from decimal import Decimal

import config
import database as db
from engines.audit_logger import audit_logger

logger = logging.getLogger(__name__)


class TransferLimitsService:
    """Service for enforcing wallet transfer limits"""
    
    def __init__(self):
        self.per_tx_limit = config.WALLET_MAX_TRANSFER_ZAR_PER_TX
        self.daily_limit = config.WALLET_MAX_TRANSFER_ZAR_PER_DAY
        self.monthly_limit = config.WALLET_MAX_TRANSFER_ZAR_PER_MONTH
    
    async def check_limits(
        self,
        user_id: str,
        amount_zar: float,
        exchange: str = None,
        currency: str = None
    ) -> Dict:
        """
        Check if transfer is within limits (per-tx, daily, monthly)
        
        Args:
            user_id: User ID
            amount_zar: Transfer amount in ZAR
            exchange: Optional exchange filter
            currency: Optional currency filter
            
        Returns:
            Dict with 'allowed' bool, 'reason_code', and 'message'
        """
        try:
            # 1. Check per-transaction limit
            if amount_zar > self.per_tx_limit:
                await self._log_limit_violation(
                    user_id,
                    "LIMIT_PER_TX",
                    amount_zar,
                    self.per_tx_limit
                )
                return {
                    "allowed": False,
                    "reason_code": "LIMIT_PER_TX",
                    "message": f"Transfer amount R{amount_zar:,.2f} exceeds per-transaction limit of R{self.per_tx_limit:,.2f}",
                    "limit": self.per_tx_limit,
                    "requested": amount_zar
                }
            
            # 2. Check daily limit
            daily_check = await self._check_daily_limit(user_id, amount_zar)
            if not daily_check["allowed"]:
                return daily_check
            
            # 3. Check monthly limit
            monthly_check = await self._check_monthly_limit(user_id, amount_zar)
            if not monthly_check["allowed"]:
                return monthly_check
            
            return {
                "allowed": True,
                "message": "Transfer within all limits"
            }
            
        except Exception as e:
            logger.error(f"Error checking transfer limits: {e}")
            # Fail closed - deny on error
            return {
                "allowed": False,
                "reason_code": "SYSTEM_ERROR",
                "message": f"Unable to verify limits: {str(e)}"
            }
    
    async def _check_daily_limit(self, user_id: str, amount_zar: float) -> Dict:
        """Check daily transfer limit"""
        try:
            # Get start of current day (UTC)
            now = datetime.now(timezone.utc)
            day_start = datetime(now.year, now.month, now.day, 0, 0, 0, tzinfo=timezone.utc)
            
            # Get today's usage
            usage_doc = await db.db["wallet_transfer_usage"].find_one({
                "user_id": user_id,
                "period_type": "daily",
                "period_start": day_start.isoformat()
            })
            
            current_usage = usage_doc["total_amount_zar"] if usage_doc else 0
            projected_usage = current_usage + amount_zar
            
            if projected_usage > self.daily_limit:
                await self._log_limit_violation(
                    user_id,
                    "LIMIT_DAILY",
                    projected_usage,
                    self.daily_limit
                )
                return {
                    "allowed": False,
                    "reason_code": "LIMIT_DAILY",
                    "message": f"Daily limit exceeded. Used: R{current_usage:,.2f}, Requested: R{amount_zar:,.2f}, Limit: R{self.daily_limit:,.2f}",
                    "limit": self.daily_limit,
                    "used": current_usage,
                    "requested": amount_zar,
                    "available": max(0, self.daily_limit - current_usage)
                }
            
            return {
                "allowed": True,
                "used": current_usage,
                "available": self.daily_limit - projected_usage
            }
            
        except Exception as e:
            logger.error(f"Error checking daily limit: {e}")
            return {
                "allowed": False,
                "reason_code": "SYSTEM_ERROR",
                "message": f"Unable to verify daily limit: {str(e)}"
            }
    
    async def _check_monthly_limit(self, user_id: str, amount_zar: float) -> Dict:
        """Check monthly transfer limit"""
        try:
            # Get start of current month (UTC)
            now = datetime.now(timezone.utc)
            month_start = datetime(now.year, now.month, 1, 0, 0, 0, tzinfo=timezone.utc)
            
            # Get this month's usage
            usage_doc = await db.db["wallet_transfer_usage"].find_one({
                "user_id": user_id,
                "period_type": "monthly",
                "period_start": month_start.isoformat()
            })
            
            current_usage = usage_doc["total_amount_zar"] if usage_doc else 0
            projected_usage = current_usage + amount_zar
            
            if projected_usage > self.monthly_limit:
                await self._log_limit_violation(
                    user_id,
                    "LIMIT_MONTHLY",
                    projected_usage,
                    self.monthly_limit
                )
                return {
                    "allowed": False,
                    "reason_code": "LIMIT_MONTHLY",
                    "message": f"Monthly limit exceeded. Used: R{current_usage:,.2f}, Requested: R{amount_zar:,.2f}, Limit: R{self.monthly_limit:,.2f}",
                    "limit": self.monthly_limit,
                    "used": current_usage,
                    "requested": amount_zar,
                    "available": max(0, self.monthly_limit - current_usage)
                }
            
            return {
                "allowed": True,
                "used": current_usage,
                "available": self.monthly_limit - projected_usage
            }
            
        except Exception as e:
            logger.error(f"Error checking monthly limit: {e}")
            return {
                "allowed": False,
                "reason_code": "SYSTEM_ERROR",
                "message": f"Unable to verify monthly limit: {str(e)}"
            }
    
    async def record_transfer(
        self,
        user_id: str,
        transfer_id: str,
        amount_zar: float,
        exchange: str,
        currency: str
    ) -> None:
        """
        Record a successful transfer for limit tracking
        
        Args:
            user_id: User ID
            transfer_id: Transfer ID
            amount_zar: Transfer amount in ZAR
            exchange: Exchange name
            currency: Currency code
        """
        try:
            now = datetime.now(timezone.utc)
            
            # Record for daily tracking
            day_start = datetime(now.year, now.month, now.day, 0, 0, 0, tzinfo=timezone.utc)
            await db.db["wallet_transfer_usage"].update_one(
                {
                    "user_id": user_id,
                    "period_type": "daily",
                    "period_start": day_start.isoformat()
                },
                {
                    "$inc": {
                        "total_amount_zar": amount_zar,
                        "transfer_count": 1
                    },
                    "$push": {
                        "transfers": {
                            "transfer_id": transfer_id,
                            "amount_zar": amount_zar,
                            "exchange": exchange,
                            "currency": currency,
                            "timestamp": now.isoformat()
                        }
                    },
                    "$setOnInsert": {
                        "period_end": (day_start + timedelta(days=1)).isoformat()
                    }
                },
                upsert=True
            )
            
            # Record for monthly tracking
            month_start = datetime(now.year, now.month, 1, 0, 0, 0, tzinfo=timezone.utc)
            # Calculate next month start
            if now.month == 12:
                next_month_start = datetime(now.year + 1, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
            else:
                next_month_start = datetime(now.year, now.month + 1, 1, 0, 0, 0, tzinfo=timezone.utc)
            
            await db.db["wallet_transfer_usage"].update_one(
                {
                    "user_id": user_id,
                    "period_type": "monthly",
                    "period_start": month_start.isoformat()
                },
                {
                    "$inc": {
                        "total_amount_zar": amount_zar,
                        "transfer_count": 1
                    },
                    "$push": {
                        "transfers": {
                            "transfer_id": transfer_id,
                            "amount_zar": amount_zar,
                            "exchange": exchange,
                            "currency": currency,
                            "timestamp": now.isoformat()
                        }
                    },
                    "$setOnInsert": {
                        "period_end": next_month_start.isoformat()
                    }
                },
                upsert=True
            )
            
            logger.info(f"Recorded transfer {transfer_id} for limit tracking: R{amount_zar:,.2f}")
            
        except Exception as e:
            logger.error(f"Error recording transfer for limits: {e}")
            # Don't fail the transfer if recording fails, just log
    
    async def get_usage_summary(self, user_id: str) -> Dict:
        """
        Get current usage summary for a user
        
        Args:
            user_id: User ID
            
        Returns:
            Dict with daily and monthly usage
        """
        try:
            now = datetime.now(timezone.utc)
            day_start = datetime(now.year, now.month, now.day, 0, 0, 0, tzinfo=timezone.utc)
            month_start = datetime(now.year, now.month, 1, 0, 0, 0, tzinfo=timezone.utc)
            
            # Get daily usage
            daily_usage = await db.db["wallet_transfer_usage"].find_one({
                "user_id": user_id,
                "period_type": "daily",
                "period_start": day_start.isoformat()
            })
            
            # Get monthly usage
            monthly_usage = await db.db["wallet_transfer_usage"].find_one({
                "user_id": user_id,
                "period_type": "monthly",
                "period_start": month_start.isoformat()
            })
            
            return {
                "per_tx_limit": self.per_tx_limit,
                "daily": {
                    "limit": self.daily_limit,
                    "used": daily_usage["total_amount_zar"] if daily_usage else 0,
                    "available": self.daily_limit - (daily_usage["total_amount_zar"] if daily_usage else 0),
                    "transfer_count": daily_usage["transfer_count"] if daily_usage else 0
                },
                "monthly": {
                    "limit": self.monthly_limit,
                    "used": monthly_usage["total_amount_zar"] if monthly_usage else 0,
                    "available": self.monthly_limit - (monthly_usage["total_amount_zar"] if monthly_usage else 0),
                    "transfer_count": monthly_usage["transfer_count"] if monthly_usage else 0
                }
            }
            
        except Exception as e:
            logger.error(f"Error getting usage summary: {e}")
            return {
                "error": str(e),
                "per_tx_limit": self.per_tx_limit,
                "daily": {"limit": self.daily_limit, "used": 0, "available": self.daily_limit},
                "monthly": {"limit": self.monthly_limit, "used": 0, "available": self.monthly_limit}
            }
    
    async def _log_limit_violation(
        self,
        user_id: str,
        reason_code: str,
        attempted_amount: float,
        limit: float
    ) -> None:
        """Log a limit violation attempt"""
        try:
            await audit_logger.log_event(
                event_type="transfer_limit_violation",
                user_id=user_id,
                details={
                    "reason_code": reason_code,
                    "attempted_amount_zar": attempted_amount,
                    "limit_zar": limit
                },
                severity="warning"
            )
        except Exception as e:
            logger.error(f"Error logging limit violation: {e}")


# Global instance
transfer_limits_service = TransferLimitsService()
