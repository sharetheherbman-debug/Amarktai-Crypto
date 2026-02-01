"""
Transfer State Machine - Production-Safe Wallet Transfers
NON-NEGOTIABLE: Real CCXT API, Idempotency, State Tracking, 2FA

State Flow: requested → (needs_approval?) approved → queued → broadcast → confirmed | failed

Updated to use TransferJob model from models.py for consistency.
"""

import asyncio
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, List
from enum import Enum
import logging
import hashlib

import config
import database as db
from realtime_events import manager
from models import TransferState, TransferJob, TransferLedgerEvent

logger = logging.getLogger(__name__)


class TransferBlockedReason(str, Enum):
    """Reasons why a transfer might be blocked"""
    EMERGENCY_STOP = "emergency_stop"
    INSUFFICIENT_BALANCE = "insufficient_balance"
    RESERVED_FUNDS = "reserved_funds"
    LIMIT_EXCEEDED = "limit_exceeded"
    MISSING_2FA = "missing_2fa"
    MISSING_APPROVAL = "missing_approval"
    INVALID_ADDRESS = "invalid_address"
    EXCHANGE_ERROR = "exchange_error"


class TransferStateMachine:
    """
    Production-safe transfer state machine with idempotency
    """
    
    def __init__(self):
        self.processing_jobs = {}  # Track in-flight transfers
        
    async def request_transfer(
        self,
        user_id: str,
        from_exchange: str,
        to_exchange: str,
        currency: str,
        amount: float,
        idempotency_key: str,
        totp_code: Optional[str] = None,
        withdrawal_address: Optional[str] = None,
        notes: Optional[str] = None
    ) -> Dict:
        """
        Request a new transfer with idempotency
        
        Args:
            user_id: User ID
            from_exchange: Source exchange
            to_exchange: Destination exchange
            currency: Currency code
            amount: Amount to transfer
            idempotency_key: Unique key to prevent duplicate transfers
            totp_code: TOTP 2FA code (required if REQUIRE_2FA_FOR_WITHDRAWALS=1)
            withdrawal_address: Optional whitelisted address
            notes: Optional transfer notes
            
        Returns:
            Dict with transfer_id and state
        """
        try:
            # 1. Check idempotency - prevent duplicate submissions
            existing = await self._check_idempotency(user_id, idempotency_key)
            if existing:
                return {
                    "success": True,
                    "transfer_id": existing["transfer_id"],
                    "state": existing["state"],
                    "message": "Transfer already exists (idempotent)",
                    "idempotent": True
                }
            
            # 2. Validate emergency stop
            emergency_stop = await self._check_emergency_stop(user_id)
            if emergency_stop["active"]:
                await self._emit_blocked(user_id, idempotency_key, 
                                        TransferBlockedReason.EMERGENCY_STOP)
                return {
                    "success": False,
                    "error": "EMERGENCY_STOP_ACTIVE",
                    "message": "Transfers blocked by emergency stop"
                }
            
            # 3. Validate 2FA if required
            if getattr(config, 'REQUIRE_2FA_FOR_WITHDRAWALS', False):
                if not totp_code:
                    await self._emit_blocked(user_id, idempotency_key,
                                            TransferBlockedReason.MISSING_2FA)
                    return {
                        "success": False,
                        "error": "2FA_REQUIRED",
                        "message": "TOTP code required for withdrawals"
                    }
                
                # Verify TOTP code
                totp_valid = await self._verify_totp(user_id, totp_code)
                if not totp_valid:
                    return {
                        "success": False,
                        "error": "INVALID_2FA",
                        "message": "Invalid TOTP code"
                    }
            
            # 4. Check reserved funds
            reserved_check = await self._check_reserved_funds(
                user_id, from_exchange, currency, amount
            )
            if not reserved_check["allowed"]:
                await self._emit_blocked(user_id, idempotency_key,
                                        TransferBlockedReason.RESERVED_FUNDS)
                return {
                    "success": False,
                    "error": "RESERVED_FUNDS",
                    "message": reserved_check["message"],
                    "reserved": reserved_check["reserved"],
                    "available": reserved_check["available"]
                }
            
            # 5. Check withdrawal limits
            limit_check = await self._check_limits(user_id, amount)
            if not limit_check["allowed"]:
                await self._emit_blocked(user_id, idempotency_key,
                                        TransferBlockedReason.LIMIT_EXCEEDED)
                return {
                    "success": False,
                    "error": "LIMIT_EXCEEDED",
                    "message": limit_check["message"]
                }
            
            # 6. Generate transfer_id
            transfer_id = f"txf_{uuid.uuid4().hex[:16]}"
            
            # 7. Determine if admin approval needed
            amount_zar = await self._convert_to_zar(amount, currency)
            approval_threshold = getattr(config, 'REQUIRE_ADMIN_APPROVAL_ABOVE_ZAR', 100000)
            needs_approval = amount_zar > approval_threshold
            
            initial_state = TransferState.NEEDS_APPROVAL if needs_approval else TransferState.REQUESTED
            
            # 8. Create transfer job
            transfer_job = {
                "transfer_id": transfer_id,
                "user_id": user_id,
                "idempotency_key": idempotency_key,
                "from_exchange": from_exchange,
                "to_exchange": to_exchange,
                "currency": currency,
                "amount": amount,
                "amount_zar": amount_zar,
                "withdrawal_address": withdrawal_address,
                "state": initial_state,
                "needs_approval": needs_approval,
                "approval_status": None,
                "withdrawal_txid": None,
                "notes": notes,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "state_history": [
                    {
                        "state": initial_state,
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    }
                ]
            }
            
            # 9. Save to transfer_jobs collection
            await db.db["transfer_jobs"].insert_one(transfer_job)
            
            # 10. Save to immutable ledger
            await self._append_ledger(transfer_id, "transfer_requested", transfer_job)
            
            # 11. Reserve funds
            await self._reserve_funds(user_id, from_exchange, currency, amount, transfer_id)
            
            # 12. Emit event
            await manager.broadcast_to_user(user_id, {
                "type": "transfer_job_created",
                "transfer_id": transfer_id,
                "state": initial_state,
                "needs_approval": needs_approval,
                "timestamp": datetime.now(timezone.utc).isoformat()
            })
            
            logger.info(f"Transfer requested: {transfer_id} ({from_exchange} → {to_exchange}, {amount} {currency})")
            
            return {
                "success": True,
                "transfer_id": transfer_id,
                "state": initial_state,
                "needs_approval": needs_approval,
                "message": "Transfer request created successfully"
            }
            
        except Exception as e:
            logger.error(f"Transfer request failed: {e}")
            return {
                "success": False,
                "error": "INTERNAL_ERROR",
                "message": str(e)
            }
    
    async def approve_transfer(self, transfer_id: str, admin_id: str, notes: Optional[str] = None) -> Dict:
        """Admin approval for large transfers"""
        try:
            transfer = await db.db["transfer_jobs"].find_one({"transfer_id": transfer_id})
            if not transfer:
                return {"success": False, "error": "NOT_FOUND"}
            
            if transfer["state"] != TransferState.NEEDS_APPROVAL:
                return {"success": False, "error": "INVALID_STATE", 
                       "message": f"Transfer in state {transfer['state']}, expected {TransferState.NEEDS_APPROVAL}"}
            
            # Update state
            await self._transition_state(transfer_id, TransferState.APPROVED, 
                                        f"Approved by admin {admin_id}")
            
            # Log approval in audit_log
            await db.db["audit_log"].insert_one({
                "event": "transfer_approved",
                "transfer_id": transfer_id,
                "admin_id": admin_id,
                "notes": notes,
                "timestamp": datetime.now(timezone.utc).isoformat()
            })
            
            # Queue for execution
            await self._queue_transfer(transfer_id)
            
            return {"success": True, "state": TransferState.APPROVED}
            
        except Exception as e:
            logger.error(f"Transfer approval failed: {e}")
            return {"success": False, "error": str(e)}
    
    async def reject_transfer(self, transfer_id: str, admin_id: str, reason: str) -> Dict:
        """Admin rejection of transfer"""
        try:
            transfer = await db.db["transfer_jobs"].find_one({"transfer_id": transfer_id})
            if not transfer:
                return {"success": False, "error": "NOT_FOUND"}
            
            # Update state
            await self._transition_state(transfer_id, TransferState.CANCELLED, 
                                        f"Rejected by admin {admin_id}: {reason}")
            
            # Release reserved funds
            await self._release_funds(
                transfer["user_id"],
                transfer["from_exchange"],
                transfer["currency"],
                transfer["amount"],
                transfer_id
            )
            
            # Log rejection
            await db.db["audit_log"].insert_one({
                "event": "transfer_rejected",
                "transfer_id": transfer_id,
                "admin_id": admin_id,
                "reason": reason,
                "timestamp": datetime.now(timezone.utc).isoformat()
            })
            
            return {"success": True, "state": TransferState.CANCELLED}
            
        except Exception as e:
            logger.error(f"Transfer rejection failed: {e}")
            return {"success": False, "error": str(e)}
    
    async def _queue_transfer(self, transfer_id: str):
        """Add approved transfer to execution queue"""
        transfer = await db.db["transfer_jobs"].find_one({"transfer_id": transfer_id})
        if not transfer:
            return
        
        await self._transition_state(transfer_id, TransferState.QUEUED, "Added to execution queue")
        
        # Start async processing
        asyncio.create_task(self._execute_transfer(transfer_id))
    
    async def _execute_transfer(self, transfer_id: str):
        """Execute transfer using CCXT"""
        try:
            import ccxt.async_support as ccxt
            
            transfer = await db.db["transfer_jobs"].find_one({"transfer_id": transfer_id})
            if not transfer:
                return
            
            # Transition to broadcast
            await self._transition_state(transfer_id, TransferState.BROADCAST, "Executing withdrawal")
            
            # Get API keys
            from_keys = await db.api_keys_collection.find_one({
                "user_id": transfer["user_id"],
                "provider": transfer["from_exchange"],
                "connected": True
            })
            
            if not from_keys:
                await self._transition_state(transfer_id, TransferState.FAILED, "Missing API keys")
                return
            
            # Initialize exchange
            exchange_class = getattr(ccxt, transfer["from_exchange"], None)
            if not exchange_class:
                await self._transition_state(transfer_id, TransferState.FAILED, 
                                            f"Exchange {transfer['from_exchange']} not supported")
                return
            
            exchange = exchange_class({
                'apiKey': from_keys['api_key'],
                'secret': from_keys['api_secret'],
                'password': from_keys.get('passphrase'),
                'enableRateLimit': True,
            })
            
            # Get withdrawal address if not provided
            withdrawal_address = transfer.get("withdrawal_address")
            if not withdrawal_address:
                # Fetch deposit address from destination exchange
                withdrawal_address = await self._get_deposit_address(
                    transfer["user_id"],
                    transfer["to_exchange"],
                    transfer["currency"]
                )
            
            # Execute withdrawal
            try:
                withdrawal_response = await exchange.withdraw(
                    transfer["currency"],
                    transfer["amount"],
                    withdrawal_address,
                    None,  # tag
                    {}
                )
                
                withdrawal_txid = withdrawal_response.get('id') or withdrawal_response.get('txid')
                
                # Update job with txid
                await db.db["transfer_jobs"].update_one(
                    {"transfer_id": transfer_id},
                    {
                        "$set": {
                            "withdrawal_txid": withdrawal_txid,
                            "withdrawal_response": withdrawal_response,
                            "updated_at": datetime.now(timezone.utc).isoformat()
                        }
                    }
                )
                
                await self._append_ledger(transfer_id, "withdrawal_broadcast", {
                    "withdrawal_txid": withdrawal_txid,
                    "response": withdrawal_response
                })
                
                # Monitor for confirmation
                await self._monitor_withdrawal(transfer_id, from_keys, exchange_class)
                
            except Exception as withdrawal_err:
                logger.error(f"Withdrawal failed: {withdrawal_err}")
                await self._transition_state(transfer_id, TransferState.FAILED, str(withdrawal_err))
                
                # Release reserved funds on failure
                await self._release_funds(
                    transfer["user_id"],
                    transfer["from_exchange"],
                    transfer["currency"],
                    transfer["amount"],
                    transfer_id
                )
            finally:
                await exchange.close()
                
        except Exception as e:
            logger.error(f"Transfer execution failed: {e}")
            await self._transition_state(transfer_id, TransferState.FAILED, str(e))
    
    async def _monitor_withdrawal(self, transfer_id: str, from_keys: Dict, exchange_class):
        """Monitor withdrawal confirmation with backoff retry"""
        max_attempts = 60
        check_interval = 30
        
        for attempt in range(max_attempts):
            await asyncio.sleep(check_interval)
            
            try:
                exchange = exchange_class({
                    'apiKey': from_keys['api_key'],
                    'secret': from_keys['api_secret'],
                    'password': from_keys.get('passphrase'),
                    'enableRateLimit': True,
                })
                
                transfer = await db.db["transfer_jobs"].find_one({"transfer_id": transfer_id})
                withdrawal_txid = transfer.get("withdrawal_txid")
                
                if withdrawal_txid:
                    withdrawal_status = await exchange.fetch_withdrawal(
                        withdrawal_txid,
                        transfer["currency"]
                    )
                    
                    status_code = withdrawal_status.get('status', 'pending')
                    
                    if status_code in ['ok', 'complete', 'confirmed', 'success']:
                        await self._transition_state(transfer_id, TransferState.CONFIRMED, 
                                                    "Withdrawal confirmed")
                        await self._release_funds(
                            transfer["user_id"],
                            transfer["from_exchange"],
                            transfer["currency"],
                            transfer["amount"],
                            transfer_id
                        )
                        await exchange.close()
                        return
                    
                    elif status_code in ['failed', 'rejected', 'canceled']:
                        await self._transition_state(transfer_id, TransferState.FAILED, 
                                                    f"Withdrawal {status_code}")
                        await self._release_funds(
                            transfer["user_id"],
                            transfer["from_exchange"],
                            transfer["currency"],
                            transfer["amount"],
                            transfer_id
                        )
                        await exchange.close()
                        return
                
                await exchange.close()
                
            except Exception as e:
                logger.warning(f"Withdrawal monitoring error (attempt {attempt+1}/{max_attempts}): {e}")
                # Continue monitoring
        
        # Timeout
        logger.warning(f"Transfer {transfer_id} monitoring timed out")
        await db.db["transfer_jobs"].update_one(
            {"transfer_id": transfer_id},
            {"$set": {"status_note": "Confirmation timeout - manual verification required"}}
        )
    
    async def _check_idempotency(self, user_id: str, idempotency_key: str) -> Optional[Dict]:
        """Check if transfer with this idempotency key already exists"""
        existing = await db.db["transfer_jobs"].find_one({
            "user_id": user_id,
            "idempotency_key": idempotency_key
        })
        return existing
    
    async def _check_emergency_stop(self, user_id: str) -> Dict:
        """Check if emergency stop is active"""
        # Check system-wide emergency stop
        system_stop = await db.db["system_settings"].find_one({"key": "emergency_stop"})
        if system_stop and system_stop.get("value") == True:
            return {"active": True, "scope": "system"}
        
        # Check user-specific stop
        user_stop = await db.db["user_settings"].find_one({
            "user_id": user_id,
            "emergency_stop": True
        })
        if user_stop:
            return {"active": True, "scope": "user"}
        
        return {"active": False}
    
    async def _verify_totp(self, user_id: str, totp_code: str) -> bool:
        """Verify TOTP 2FA code"""
        try:
            import pyotp
            
            user = await db.users_collection.find_one({"id": user_id})
            if not user or not user.get("two_factor_secret"):
                return False
            
            totp = pyotp.TOTP(user["two_factor_secret"])
            return totp.verify(totp_code, valid_window=1)
            
        except Exception as e:
            logger.error(f"TOTP verification failed: {e}")
            return False
    
    async def _check_reserved_funds(self, user_id: str, exchange: str, currency: str, amount: float) -> Dict:
        """Check if funds are available (not reserved elsewhere)"""
        try:
            # Get reserved funds for this user/exchange/currency
            reserved_doc = await db.db["reserved_funds"].find_one({
                "user_id": user_id,
                "exchange": exchange,
                "currency": currency
            })
            
            reserved = reserved_doc.get("amount", 0) if reserved_doc else 0
            
            # Get actual balance (would integrate with balance sync)
            balance = await self._get_balance(user_id, exchange, currency)
            
            available = balance - reserved
            
            if amount > available:
                return {
                    "allowed": False,
                    "message": f"Insufficient available balance. Available: {available} {currency}, Requested: {amount} {currency}",
                    "reserved": reserved,
                    "available": available,
                    "balance": balance
                }
            
            return {"allowed": True, "available": available}
            
        except Exception as e:
            logger.error(f"Reserved funds check failed: {e}")
            return {"allowed": False, "message": f"Error checking reserved funds: {e}"}
    
    async def _get_balance(self, user_id: str, exchange: str, currency: str) -> float:
        """Get current balance from balance snapshots"""
        snapshot = await db.db["balances_snapshots"].find_one({
            "user_id": user_id,
            "exchange": exchange,
            "currency": currency
        }, sort=[("timestamp", -1)])
        
        if snapshot:
            return snapshot.get("balance", 0)
        return 0
    
    async def _check_limits(self, user_id: str, amount: float) -> Dict:
        """Check withdrawal limits"""
        # Simplified - would implement full limit checking
        max_single = getattr(config, 'MAX_SINGLE_WITHDRAWAL_USD', 50000)
        if amount > max_single:
            return {"allowed": False, "message": f"Exceeds single withdrawal limit: {max_single}"}
        return {"allowed": True}
    
    async def _convert_to_zar(self, amount: float, currency: str) -> float:
        """Convert amount to ZAR for approval threshold checking"""
        # Simplified - would use real exchange rates
        if currency == "ZAR":
            return amount
        # Mock conversion rates
        rates = {"USD": 18.5, "BTC": 800000, "ETH": 50000}
        return amount * rates.get(currency, 1)
    
    async def _transition_state(self, transfer_id: str, new_state: TransferState, note: Optional[str] = None):
        """Transition transfer to new state"""
        update_doc = {
            "state": new_state,
            "updated_at": datetime.now(timezone.utc).isoformat()
        }
        
        if note:
            update_doc["state_note"] = note
        
        # Append to history
        await db.db["transfer_jobs"].update_one(
            {"transfer_id": transfer_id},
            {
                "$set": update_doc,
                "$push": {
                    "state_history": {
                        "state": new_state,
                        "note": note,
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    }
                }
            }
        )
        
        # Append to immutable ledger
        await self._append_ledger(transfer_id, f"state_transition_{new_state}", {"note": note})
        
        # Emit realtime event
        transfer = await db.db["transfer_jobs"].find_one({"transfer_id": transfer_id})
        if transfer:
            await manager.broadcast_to_user(transfer["user_id"], {
                "type": "transfer_job_updated",
                "transfer_id": transfer_id,
                "state": new_state,
                "note": note,
                "timestamp": datetime.now(timezone.utc).isoformat()
            })
    
    async def _append_ledger(self, transfer_id: str, event: str, data: Dict):
        """Append event to immutable transfers_ledger"""
        await db.db["transfers_ledger"].insert_one({
            "transfer_id": transfer_id,
            "event": event,
            "data": data,
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
    
    async def _reserve_funds(self, user_id: str, exchange: str, currency: str, amount: float, transfer_id: str):
        """Reserve funds for pending transfer"""
        await db.db["reserved_funds"].update_one(
            {"user_id": user_id, "exchange": exchange, "currency": currency},
            {
                "$inc": {"amount": amount},
                "$push": {
                    "reservations": {
                        "transfer_id": transfer_id,
                        "amount": amount,
                        "timestamp": datetime.now(timezone.utc).isoformat()
                    }
                }
            },
            upsert=True
        )
    
    async def _release_funds(self, user_id: str, exchange: str, currency: str, amount: float, transfer_id: str):
        """Release reserved funds"""
        await db.db["reserved_funds"].update_one(
            {"user_id": user_id, "exchange": exchange, "currency": currency},
            {
                "$inc": {"amount": -amount},
                "$pull": {"reservations": {"transfer_id": transfer_id}}
            }
        )
    
    async def _emit_blocked(self, user_id: str, idempotency_key: str, reason: TransferBlockedReason):
        """Emit transfer blocked event"""
        await manager.broadcast_to_user(user_id, {
            "type": "transfer_blocked",
            "idempotency_key": idempotency_key,
            "reason": reason,
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
    
    async def _get_deposit_address(self, user_id: str, exchange: str, currency: str) -> str:
        """Get deposit address for destination exchange"""
        import ccxt.async_support as ccxt
        
        to_keys = await db.api_keys_collection.find_one({
            "user_id": user_id,
            "provider": exchange,
            "connected": True
        })
        
        if not to_keys:
            raise Exception(f"No API keys for {exchange}")
        
        exchange_class = getattr(ccxt, exchange, None)
        exchange_obj = exchange_class({
            'apiKey': to_keys['api_key'],
            'secret': to_keys['api_secret'],
            'password': to_keys.get('passphrase'),
            'enableRateLimit': True,
        })
        
        try:
            deposit_address_response = await exchange_obj.fetch_deposit_address(currency)
            return deposit_address_response['address']
        finally:
            await exchange_obj.close()


# Global instance
transfer_state_machine = TransferStateMachine()
