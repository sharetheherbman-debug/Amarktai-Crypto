"""
Admin Whitelist Management Routes

Admin-only endpoints for managing withdrawal address whitelist.
"""

from fastapi import APIRouter, HTTPException, Depends, Body
from typing import Optional
import logging

from auth import get_admin_user
from services.address_whitelist import address_whitelist_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin/whitelist", tags=["Admin - Whitelist Management"])


@router.get("/pending")
async def list_pending_whitelist_approvals(
    admin_id: str = Depends(get_admin_user)
):
    """
    List all pending whitelist address approvals
    
    Admin-only endpoint. Returns addresses awaiting approval.
    """
    try:
        pending = await address_whitelist_service.get_pending_approvals()
        
        return {
            "success": True,
            "pending_addresses": pending,
            "count": len(pending)
        }
        
    except Exception as e:
        logger.error(f"Error listing pending approvals: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to list pending approvals: {str(e)}"
        )


@router.post("/{address_id}/approve")
async def approve_whitelist_address(
    address_id: str,
    admin_id: str = Depends(get_admin_user)
):
    """
    Approve a pending withdrawal address
    
    Admin-only endpoint. Approves an address for use in withdrawals.
    """
    try:
        result = await address_whitelist_service.approve_address(address_id, admin_id)
        
        if not result["success"]:
            raise HTTPException(
                status_code=400,
                detail=result.get("message", "Failed to approve address")
            )
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error approving address: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to approve address: {str(e)}"
        )


@router.post("/{address_id}/reject")
async def reject_whitelist_address(
    address_id: str,
    reason: str = Body(..., embed=True),
    admin_id: str = Depends(get_admin_user)
):
    """
    Reject a pending withdrawal address
    
    Admin-only endpoint. Rejects an address with a reason.
    
    Request Body:
    {
        "reason": "Invalid address format" | "Suspicious address" | etc.
    }
    """
    try:
        result = await address_whitelist_service.reject_address(address_id, admin_id, reason)
        
        if not result["success"]:
            raise HTTPException(
                status_code=400,
                detail=result.get("message", "Failed to reject address")
            )
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error rejecting address: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to reject address: {str(e)}"
        )


@router.get("/all")
async def list_all_whitelist_addresses(
    admin_id: str = Depends(get_admin_user),
    user_id: Optional[str] = None,
    exchange: Optional[str] = None,
    currency: Optional[str] = None,
    status: Optional[str] = None
):
    """
    List all whitelist addresses with optional filters
    
    Admin-only endpoint. Can filter by user, exchange, currency, or status.
    
    Query Parameters:
    - user_id: Filter by user ID
    - exchange: Filter by exchange
    - currency: Filter by currency
    - status: Filter by status (pending_approval, approved, rejected)
    """
    try:
        import database as db
        
        query = {}
        
        if user_id:
            query["user_id"] = user_id
        if exchange:
            query["exchange"] = exchange
        if currency:
            query["currency"] = currency
        if status:
            query["status"] = status
        
        addresses = await db.db["withdrawal_addresses"].find(
            query,
            {"_id": 0}
        ).sort("created_at", -1).to_list(500)
        
        return {
            "success": True,
            "addresses": addresses,
            "count": len(addresses),
            "filters": {
                "user_id": user_id,
                "exchange": exchange,
                "currency": currency,
                "status": status
            }
        }
        
    except Exception as e:
        logger.error(f"Error listing addresses: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to list addresses: {str(e)}"
        )


@router.delete("/{address_id}")
async def delete_whitelist_address(
    address_id: str,
    admin_id: str = Depends(get_admin_user)
):
    """
    Delete a withdrawal address
    
    Admin-only endpoint. Permanently deletes an address from the whitelist.
    """
    try:
        import database as db
        
        address = await db.db["withdrawal_addresses"].find_one({"address_id": address_id})
        
        if not address:
            raise HTTPException(
                status_code=404,
                detail="Address not found"
            )
        
        await db.db["withdrawal_addresses"].delete_one({"address_id": address_id})
        
        # Log deletion
        from engines.audit_logger import audit_logger
        await audit_logger.log_event(
            event_type="withdrawal_address_deleted_by_admin",
            user_id=address["user_id"],
            details={
                "address_id": address_id,
                "exchange": address["exchange"],
                "currency": address["currency"],
                "deleted_by": admin_id
            },
            severity="warning"
        )
        
        return {
            "success": True,
            "message": "Address deleted successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting address: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to delete address: {str(e)}"
        )
