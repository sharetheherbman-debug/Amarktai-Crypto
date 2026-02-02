"""
Withdrawal Address Management Endpoints

User and admin endpoints for managing whitelisted withdrawal addresses.
All endpoints combined in a single router with different auth requirements.
"""

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from typing import Optional, List
import logging

from auth import get_current_user, get_admin_user
from services.address_whitelist import address_whitelist_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/wallet", tags=["Wallet Addresses"])


class AddressCreateRequest(BaseModel):
    exchange: str
    currency: str
    address: str
    tag: Optional[str] = None
    network: Optional[str] = None
    label: Optional[str] = None


class AddressApprovalRequest(BaseModel):
    address_id: str


class AddressRejectionRequest(BaseModel):
    address_id: str
    reason: str


# User endpoints
@router.post("/addresses/add")
async def add_withdrawal_address(
    request: AddressCreateRequest,
    user_id: str = Depends(get_current_user)
):
    """
    Add a new withdrawal address (requires admin approval)
    
    Request body:
        exchange: Target exchange name
        currency: Currency code (BTC, ETH, etc.)
        address: Withdrawal address
        tag: Optional memo/tag for currencies that require it
        network: Optional network (ERC20, TRC20, etc.)
        label: Optional label for the address
        
    Returns:
        address_id and status
    """
    try:
        result = await address_whitelist_service.add_address(
            user_id=user_id,
            exchange=request.exchange,
            currency=request.currency,
            address=request.address,
            tag=request.tag,
            network=request.network,
            label=request.label
        )
        
        if not result["success"]:
            raise HTTPException(status_code=400, detail=result.get("message", "Failed to add address"))
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error adding address: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/addresses/list")
async def list_withdrawal_addresses(
    exchange: Optional[str] = None,
    currency: Optional[str] = None,
    user_id: str = Depends(get_current_user)
):
    """
    Get user's whitelisted addresses
    
    Query params:
        exchange: Optional filter by exchange
        currency: Optional filter by currency
        
    Returns:
        List of addresses with status
    """
    try:
        addresses = await address_whitelist_service.get_user_addresses(
            user_id=user_id,
            exchange=exchange,
            currency=currency
        )
        
        return {
            "success": True,
            "addresses": addresses,
            "count": len(addresses)
        }
        
    except Exception as e:
        logger.error(f"Error listing addresses: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/addresses/{address_id}")
async def delete_withdrawal_address(
    address_id: str,
    user_id: str = Depends(get_current_user)
):
    """
    Delete a withdrawal address
    
    Path params:
        address_id: Address ID to delete
        
    Returns:
        Success status
    """
    try:
        result = await address_whitelist_service.delete_address(address_id, user_id)
        
        if not result["success"]:
            status_code = 404 if result.get("error") == "NOT_FOUND" else 403 if result.get("error") == "UNAUTHORIZED" else 400
            raise HTTPException(status_code=status_code, detail=result.get("message", "Failed to delete address"))
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting address: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# Admin endpoints
@router.get("/admin/addresses/pending")
async def get_pending_address_approvals(
    admin_id: str = Depends(get_admin_user)
):
    """
    Get all pending address approvals (admin only)
    
    Returns:
        List of addresses pending approval
    """
    try:
        addresses = await address_whitelist_service.get_pending_approvals()
        
        return {
            "success": True,
            "pending_addresses": addresses,
            "count": len(addresses)
        }
        
    except Exception as e:
        logger.error(f"Error fetching pending approvals: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/admin/addresses/approve")
async def approve_withdrawal_address(
    request: AddressApprovalRequest,
    admin_id: str = Depends(get_admin_user)
):
    """
    Approve a pending withdrawal address (admin only)
    
    Request body:
        address_id: Address ID to approve
        
    Returns:
        Success status
    """
    try:
        result = await address_whitelist_service.approve_address(
            address_id=request.address_id,
            admin_id=admin_id
        )
        
        if not result["success"]:
            status_code = 404 if result.get("error") == "NOT_FOUND" else 400
            raise HTTPException(status_code=status_code, detail=result.get("message", "Failed to approve address"))
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error approving address: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/admin/addresses/reject")
async def reject_withdrawal_address(
    request: AddressRejectionRequest,
    admin_id: str = Depends(get_admin_user)
):
    """
    Reject a pending withdrawal address (admin only)
    
    Request body:
        address_id: Address ID to reject
        reason: Rejection reason
        
    Returns:
        Success status
    """
    try:
        result = await address_whitelist_service.reject_address(
            address_id=request.address_id,
            admin_id=admin_id,
            reason=request.reason
        )
        
        if not result["success"]:
            status_code = 404 if result.get("error") == "NOT_FOUND" else 400
            raise HTTPException(status_code=status_code, detail=result.get("message", "Failed to reject address"))
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error rejecting address: {e}")
        raise HTTPException(status_code=500, detail=str(e))
