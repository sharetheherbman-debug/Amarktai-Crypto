"""
Withdrawal Address Whitelist Service

Manages whitelisted withdrawal addresses for secure transfers.
Requires admin approval for new addresses.
"""

import logging
from datetime import datetime, timezone
from typing import Optional, Dict, List
import re

import database as db
from engines.audit_logger import audit_logger

logger = logging.getLogger(__name__)


class AddressWhitelistService:
    """Service for managing whitelisted withdrawal addresses"""
    
    @staticmethod
    def _validate_address_format(address: str, currency: str, network: str = None) -> Dict:
        """
        Validate address format for the given currency
        
        Returns:
            Dict with 'valid' bool and optional 'error' message
        """
        if not address or len(address) < 10:
            return {"valid": False, "error": "Address too short"}
        
        currency_upper = currency.upper()
        
        # Bitcoin addresses
        if currency_upper in ['BTC', 'BITCOIN']:
            # Legacy (1...), SegWit (3...), Bech32 (bc1...)
            if re.match(r'^[13][a-km-zA-HJ-NP-Z1-9]{25,34}$', address):
                return {"valid": True}
            if re.match(r'^bc1[a-z0-9]{39,59}$', address.lower()):
                return {"valid": True}
            return {"valid": False, "error": "Invalid Bitcoin address format"}
        
        # Ethereum addresses
        if currency_upper in ['ETH', 'ETHEREUM', 'USDT', 'USDC', 'DAI']:
            if re.match(r'^0x[a-fA-F0-9]{40}$', address):
                return {"valid": True}
            return {"valid": False, "error": "Invalid Ethereum address format"}
        
        # XRP addresses
        if currency_upper in ['XRP', 'RIPPLE']:
            if re.match(r'^r[0-9a-zA-Z]{24,34}$', address):
                return {"valid": True}
            return {"valid": False, "error": "Invalid XRP address format"}
        
        # For other currencies, just check basic format
        if len(address) < 10 or len(address) > 100:
            return {"valid": False, "error": "Address length out of acceptable range"}
        
        return {"valid": True}
    
    async def add_address(
        self,
        user_id: str,
        exchange: str,
        currency: str,
        address: str,
        tag: Optional[str] = None,
        network: Optional[str] = None,
        label: Optional[str] = None
    ) -> Dict:
        """
        Request to add a new whitelisted address
        
        Args:
            user_id: User ID
            exchange: Target exchange
            currency: Currency code
            address: Withdrawal address
            tag: Optional memo/tag for currencies that require it
            network: Optional network specification (e.g., ERC20, TRC20)
            label: Optional label for the address
            
        Returns:
            Dict with address_id and status
        """
        try:
            # Validate address format
            validation = self._validate_address_format(address, currency, network)
            if not validation["valid"]:
                return {
                    "success": False,
                    "error": "INVALID_ADDRESS",
                    "message": validation.get("error", "Invalid address format")
                }
            
            # Check if address already exists
            existing = await db.db["withdrawal_addresses"].find_one({
                "user_id": user_id,
                "exchange": exchange,
                "currency": currency,
                "address": address
            })
            
            if existing:
                return {
                    "success": True,
                    "address_id": existing["address_id"],
                    "status": existing["status"],
                    "message": "Address already exists"
                }
            
            # Create new address entry (pending approval)
            address_id = f"addr_{user_id[:8]}_{exchange}_{currency}_{datetime.now(timezone.utc).timestamp()}"
            
            address_doc = {
                "address_id": address_id,
                "user_id": user_id,
                "exchange": exchange,
                "currency": currency,
                "address": address,
                "tag": tag,
                "network": network,
                "label": label or f"{exchange} {currency}",
                "status": "pending_approval",  # pending_approval, approved, rejected
                "created_at": datetime.now(timezone.utc).isoformat(),
                "approved_at": None,
                "approved_by": None,
                "rejection_reason": None
            }
            
            await db.db["withdrawal_addresses"].insert_one(address_doc)
            
            # Log the request
            await audit_logger.log_event(
                event_type="withdrawal_address_requested",
                user_id=user_id,
                details={
                    "address_id": address_id,
                    "exchange": exchange,
                    "currency": currency,
                    "label": label
                },
                severity="info"
            )
            
            logger.info(f"New withdrawal address requested: {address_id}")
            
            return {
                "success": True,
                "address_id": address_id,
                "status": "pending_approval",
                "message": "Address submitted for approval"
            }
            
        except Exception as e:
            logger.error(f"Error adding withdrawal address: {e}")
            return {
                "success": False,
                "error": "SYSTEM_ERROR",
                "message": str(e)
            }
    
    async def approve_address(self, address_id: str, admin_id: str) -> Dict:
        """
        Approve a pending withdrawal address
        
        Args:
            address_id: Address ID to approve
            admin_id: Admin user ID
            
        Returns:
            Dict with success status
        """
        try:
            address = await db.db["withdrawal_addresses"].find_one({"address_id": address_id})
            
            if not address:
                return {
                    "success": False,
                    "error": "NOT_FOUND",
                    "message": "Address not found"
                }
            
            if address["status"] != "pending_approval":
                return {
                    "success": False,
                    "error": "INVALID_STATUS",
                    "message": f"Address is already {address['status']}"
                }
            
            # Update to approved
            await db.db["withdrawal_addresses"].update_one(
                {"address_id": address_id},
                {
                    "$set": {
                        "status": "approved",
                        "approved_at": datetime.now(timezone.utc).isoformat(),
                        "approved_by": admin_id
                    }
                }
            )
            
            # Log approval
            await audit_logger.log_event(
                event_type="withdrawal_address_approved",
                user_id=address["user_id"],
                details={
                    "address_id": address_id,
                    "exchange": address["exchange"],
                    "currency": address["currency"],
                    "approved_by": admin_id
                },
                severity="info"
            )
            
            logger.info(f"Withdrawal address approved: {address_id} by {admin_id}")
            
            return {
                "success": True,
                "message": "Address approved successfully"
            }
            
        except Exception as e:
            logger.error(f"Error approving address: {e}")
            return {
                "success": False,
                "error": "SYSTEM_ERROR",
                "message": str(e)
            }
    
    async def reject_address(self, address_id: str, admin_id: str, reason: str) -> Dict:
        """
        Reject a pending withdrawal address
        
        Args:
            address_id: Address ID to reject
            admin_id: Admin user ID
            reason: Rejection reason
            
        Returns:
            Dict with success status
        """
        try:
            address = await db.db["withdrawal_addresses"].find_one({"address_id": address_id})
            
            if not address:
                return {
                    "success": False,
                    "error": "NOT_FOUND",
                    "message": "Address not found"
                }
            
            # Update to rejected
            await db.db["withdrawal_addresses"].update_one(
                {"address_id": address_id},
                {
                    "$set": {
                        "status": "rejected",
                        "rejection_reason": reason,
                        "rejected_at": datetime.now(timezone.utc).isoformat(),
                        "rejected_by": admin_id
                    }
                }
            )
            
            # Log rejection
            await audit_logger.log_event(
                event_type="withdrawal_address_rejected",
                user_id=address["user_id"],
                details={
                    "address_id": address_id,
                    "exchange": address["exchange"],
                    "currency": address["currency"],
                    "rejected_by": admin_id,
                    "reason": reason
                },
                severity="warning"
            )
            
            logger.info(f"Withdrawal address rejected: {address_id} by {admin_id}")
            
            return {
                "success": True,
                "message": "Address rejected"
            }
            
        except Exception as e:
            logger.error(f"Error rejecting address: {e}")
            return {
                "success": False,
                "error": "SYSTEM_ERROR",
                "message": str(e)
            }
    
    async def get_user_addresses(self, user_id: str, exchange: str = None, currency: str = None) -> List[Dict]:
        """
        Get user's whitelisted addresses
        
        Args:
            user_id: User ID
            exchange: Optional exchange filter
            currency: Optional currency filter
            
        Returns:
            List of addresses
        """
        try:
            query = {"user_id": user_id}
            
            if exchange:
                query["exchange"] = exchange
            
            if currency:
                query["currency"] = currency
            
            addresses = await db.db["withdrawal_addresses"].find(
                query,
                {"_id": 0}
            ).sort("created_at", -1).to_list(100)
            
            return addresses
            
        except Exception as e:
            logger.error(f"Error fetching addresses: {e}")
            return []
    
    async def get_pending_approvals(self) -> List[Dict]:
        """
        Get all pending address approvals for admins
        
        Returns:
            List of pending addresses
        """
        try:
            addresses = await db.db["withdrawal_addresses"].find(
                {"status": "pending_approval"},
                {"_id": 0}
            ).sort("created_at", 1).to_list(100)
            
            return addresses
            
        except Exception as e:
            logger.error(f"Error fetching pending approvals: {e}")
            return []
    
    async def is_address_whitelisted(self, user_id: str, exchange: str, currency: str, address: str) -> bool:
        """
        Check if an address is whitelisted for the user
        
        Args:
            user_id: User ID
            exchange: Exchange name
            currency: Currency code
            address: Withdrawal address
            
        Returns:
            True if whitelisted and approved
        """
        try:
            result = await db.db["withdrawal_addresses"].find_one({
                "user_id": user_id,
                "exchange": exchange,
                "currency": currency,
                "address": address,
                "status": "approved"
            })
            
            return result is not None
            
        except Exception as e:
            logger.error(f"Error checking whitelist: {e}")
            return False
    
    async def delete_address(self, address_id: str, user_id: str) -> Dict:
        """
        Delete a withdrawal address
        
        Args:
            address_id: Address ID to delete
            user_id: User ID (for authorization)
            
        Returns:
            Dict with success status
        """
        try:
            address = await db.db["withdrawal_addresses"].find_one({"address_id": address_id})
            
            if not address:
                return {
                    "success": False,
                    "error": "NOT_FOUND",
                    "message": "Address not found"
                }
            
            if address["user_id"] != user_id:
                return {
                    "success": False,
                    "error": "UNAUTHORIZED",
                    "message": "Not authorized to delete this address"
                }
            
            await db.db["withdrawal_addresses"].delete_one({"address_id": address_id})
            
            # Log deletion
            await audit_logger.log_event(
                event_type="withdrawal_address_deleted",
                user_id=user_id,
                details={
                    "address_id": address_id,
                    "exchange": address["exchange"],
                    "currency": address["currency"]
                },
                severity="info"
            )
            
            logger.info(f"Withdrawal address deleted: {address_id}")
            
            return {
                "success": True,
                "message": "Address deleted successfully"
            }
            
        except Exception as e:
            logger.error(f"Error deleting address: {e}")
            return {
                "success": False,
                "error": "SYSTEM_ERROR",
                "message": str(e)
            }


# Global instance
address_whitelist_service = AddressWhitelistService()
