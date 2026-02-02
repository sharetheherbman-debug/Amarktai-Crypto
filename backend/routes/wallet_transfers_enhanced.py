"""
Enhanced Wallet Transfer Routes - Production-Safe State Machine

This router provides production-safe wallet transfer endpoints using the
TransferStateMachine service with idempotency, 2FA, and approval workflow.

Endpoints:
- POST /api/wallet/transfers/create - Create new transfer with state machine
- GET /api/wallet/transfers - List transfers
- GET /api/wallet/transfers/{transfer_id} - Get transfer details
- POST /api/wallet/transfers/{transfer_id}/cancel - Cancel transfer
- POST /api/admin/transfers/{transfer_id}/approve - Admin approve (admin only)
- POST /api/admin/transfers/{transfer_id}/reject - Admin reject (admin only)
- GET /api/admin/transfers/pending - List pending approvals (admin only)
"""

from fastapi import APIRouter, HTTPException, Depends, Body
from datetime import datetime, timezone
from typing import Optional
import logging
import uuid

from auth import get_current_user, get_admin_user
import database as db
from models import TransferJobCreate, TransferState, TransferJob
from services.transfer_state_machine import TransferStateMachine

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/wallet", tags=["Wallet Transfers - Enhanced"])

# Initialize transfer state machine
transfer_machine = TransferStateMachine()


# ============================================================================
# User Transfer Endpoints
# ============================================================================
@router.post("/transfers/create")
async def create_transfer_with_state_machine(
    request: TransferJobCreate,
    user_id: str = Depends(get_current_user)
):
    """
    Create a new wallet transfer with production-safe state machine
    
    Features:
    - Idempotency via idempotency_key (prevents duplicate transfers)
    - 2FA verification (if REQUIRE_2FA_FOR_WITHDRAWALS=1)
    - Automatic approval workflow (if amount > threshold)
    - Transfer limits enforcement (per-tx, daily, monthly)
    - Emergency stop checking
    - Withdrawal limits enforcement
    - Address whitelist enforcement
    - Tag/memo support for applicable currencies
    - Reserved funds checking
    - Real-time SSE events
    
    Request Body:
    {
        "from_exchange": "luno",
        "to_exchange": "binance",
        "currency": "ZAR",
        "amount": 5000.0,
        "idempotency_key": "unique-key-12345",
        "totp_code": "123456",  // Optional, required if 2FA enabled
        "withdrawal_address": "0x123...",  // Optional, will fetch if not provided
        "tag": "12345678",  // Optional, for XRP/XLM etc.
        "memo": "12345678",  // Alternative to tag
        "network": "ERC20",  // Optional, network specification
        "reason": "manual_allocation",
        "notes": "Moving funds for new bot"
    }
    
    Response:
    {
        "success": true,
        "transfer_id": "uuid",
        "state": "approved" | "needs_approval",
        "message": "Transfer created successfully",
        "idempotent": false  // true if this was a duplicate request
    }
    """
    try:
        result = await transfer_machine.request_transfer(
            user_id=user_id,
            from_exchange=request.from_exchange,
            to_exchange=request.to_exchange,
            currency=request.currency,
            amount=request.amount,
            idempotency_key=request.idempotency_key,
            totp_code=request.totp_code,
            withdrawal_address=request.withdrawal_address,
            tag=request.tag,
            memo=request.memo,
            network=request.network,
            notes=request.notes
        )
        
        return result
        
    except Exception as e:
        logger.error(f"Transfer creation error: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to create transfer: {str(e)}"
        )


@router.get("/transfers")
async def list_transfers(
    user_id: str = Depends(get_current_user),
    limit: int = 50,
    state: Optional[str] = None
):
    """
    List user's transfer history
    
    Query Parameters:
    - limit: Maximum number of transfers to return (default 50)
    - state: Filter by state (requested, approved, confirmed, failed, etc.)
    
    Returns list of transfers with current state and history.
    """
    try:
        query = {"user_id": user_id}
        
        if state:
            try:
                # Validate state
                TransferState(state)
                query["state"] = state
            except ValueError:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid state: {state}"
                )
        
        transfers = await db.transfer_jobs_collection.find(
            query,
            {"_id": 0}
        ).sort("requested_at", -1).limit(limit).to_list(limit)
        
        return {
            "success": True,
            "transfers": transfers,
            "count": len(transfers)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"List transfers error: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to list transfers: {str(e)}"
        )


@router.get("/transfers/{transfer_id}")
async def get_transfer_details(
    transfer_id: str,
    user_id: str = Depends(get_current_user)
):
    """
    Get detailed information about a specific transfer
    
    Includes:
    - Current state
    - Complete state history
    - Approval information (if applicable)
    - Error details (if failed)
    - Blockchain transaction ID (if confirmed)
    """
    try:
        transfer = await db.transfer_jobs_collection.find_one(
            {"id": transfer_id, "user_id": user_id},
            {"_id": 0}
        )
        
        if not transfer:
            raise HTTPException(
                status_code=404,
                detail="Transfer not found"
            )
        
        return {
            "success": True,
            "transfer": transfer
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get transfer error: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get transfer: {str(e)}"
        )


@router.post("/transfers/{transfer_id}/cancel")
async def cancel_transfer(
    transfer_id: str,
    reason: str = Body(..., embed=True),
    user_id: str = Depends(get_current_user)
):
    """
    Cancel a pending transfer
    
    Only transfers in 'requested' or 'needs_approval' state can be cancelled.
    Transfers that are already broadcast cannot be cancelled.
    
    Request Body:
    {
        "reason": "Changed my mind" | "Wrong amount" | etc.
    }
    """
    try:
        transfer = await db.transfer_jobs_collection.find_one(
            {"id": transfer_id, "user_id": user_id}
        )
        
        if not transfer:
            raise HTTPException(
                status_code=404,
                detail="Transfer not found"
            )
        
        current_state = TransferState(transfer["state"])
        
        # Can only cancel pending transfers
        if current_state not in [TransferState.REQUESTED, TransferState.NEEDS_APPROVAL]:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot cancel transfer in state: {current_state.value}"
            )
        
        # Update state to cancelled
        now = datetime.now(timezone.utc)
        
        await db.transfer_jobs_collection.update_one(
            {"id": transfer_id},
            {
                "$set": {
                    "state": TransferState.CANCELLED.value,
                    "completed_at": now
                },
                "$push": {
                    "state_history": {
                        "state": TransferState.CANCELLED.value,
                        "timestamp": now.isoformat(),
                        "reason": f"User cancelled: {reason}",
                        "actor_id": user_id
                    }
                }
            }
        )
        
        # Log to immutable ledger
        await db.transfers_ledger_collection.insert_one({
            "id": str(uuid.uuid4()),
            "transfer_job_id": transfer_id,
            "event_type": "cancellation",
            "from_state": current_state.value,
            "to_state": TransferState.CANCELLED.value,
            "timestamp": now,
            "actor_id": user_id,
            "reason": f"User cancelled: {reason}"
        })
        
        return {
            "success": True,
            "message": "Transfer cancelled successfully",
            "transfer_id": transfer_id,
            "state": TransferState.CANCELLED.value
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Cancel transfer error: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to cancel transfer: {str(e)}"
        )


# ============================================================================
# Admin Transfer Approval Endpoints  
# ============================================================================

# Note: Admin endpoints are included in this router for now
# They could be split into a separate admin_transfer_approvals.py file later


@router.get("/admin/transfers/pending", tags=["Admin - Transfer Approvals"])
async def list_pending_approvals(
    admin_id: str = Depends(get_admin_user),
    limit: int = 100
):
    """
    List all transfers awaiting admin approval
    
    Only accessible by admin users.
    Returns transfers in 'needs_approval' state.
    """
    try:
        transfers = await db.transfer_jobs_collection.find(
            {"state": TransferState.NEEDS_APPROVAL.value},
            {"_id": 0}
        ).sort("requested_at", 1).limit(limit).to_list(limit)
        
        return {
            "success": True,
            "pending_transfers": transfers,
            "count": len(transfers)
        }
        
    except Exception as e:
        logger.error(f"List pending approvals error: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to list pending approvals: {str(e)}"
        )


@router.post("/admin/transfers/{transfer_id}/approve", tags=["Admin - Transfer Approvals"])
async def approve_transfer(
    transfer_id: str,
    approval_reason: str = Body(..., embed=True),
    admin_id: str = Depends(get_admin_user)
):
    """
    Approve a pending transfer
    
    Admin-only endpoint. Approves a transfer that requires approval
    due to amount exceeding threshold.
    
    Request Body:
    {
        "approval_reason": "Verified with user, legitimate transfer"
    }
    """
    try:
        transfer = await db.transfer_jobs_collection.find_one(
            {"id": transfer_id}
        )
        
        if not transfer:
            raise HTTPException(
                status_code=404,
                detail="Transfer not found"
            )
        
        if transfer["state"] != TransferState.NEEDS_APPROVAL.value:
            raise HTTPException(
                status_code=400,
                detail=f"Transfer is not pending approval (current state: {transfer['state']})"
            )
        
        # Update to approved state
        now = datetime.now(timezone.utc)
        
        await db.transfer_jobs_collection.update_one(
            {"id": transfer_id},
            {
                "$set": {
                    "state": TransferState.APPROVED.value,
                    "approved_by": admin_id,
                    "approved_at": now,
                    "approval_reason": approval_reason
                },
                "$push": {
                    "state_history": {
                        "state": TransferState.APPROVED.value,
                        "timestamp": now.isoformat(),
                        "reason": f"Admin approved: {approval_reason}",
                        "actor_id": admin_id
                    }
                }
            }
        )
        
        # Log to immutable ledger
        await db.transfers_ledger_collection.insert_one({
            "id": str(uuid.uuid4()),
            "transfer_job_id": transfer_id,
            "event_type": "approval",
            "from_state": TransferState.NEEDS_APPROVAL.value,
            "to_state": TransferState.APPROVED.value,
            "timestamp": now,
            "actor_id": admin_id,
            "reason": f"Admin approved: {approval_reason}"
        })
        
        return {
            "success": True,
            "message": "Transfer approved successfully",
            "transfer_id": transfer_id,
            "state": TransferState.APPROVED.value
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Approve transfer error: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to approve transfer: {str(e)}"
        )


@router.post("/admin/transfers/{transfer_id}/reject", tags=["Admin - Transfer Approvals"])
async def reject_transfer(
    transfer_id: str,
    rejection_reason: str = Body(..., embed=True),
    admin_id: str = Depends(get_admin_user)
):
    """
    Reject a pending transfer
    
    Admin-only endpoint. Rejects a transfer that requires approval.
    The transfer will be cancelled and funds will not be transferred.
    
    Request Body:
    {
        "rejection_reason": "Suspicious activity detected"
    }
    """
    try:
        transfer = await db.transfer_jobs_collection.find_one(
            {"id": transfer_id}
        )
        
        if not transfer:
            raise HTTPException(
                status_code=404,
                detail="Transfer not found"
            )
        
        if transfer["state"] != TransferState.NEEDS_APPROVAL.value:
            raise HTTPException(
                status_code=400,
                detail=f"Transfer is not pending approval (current state: {transfer['state']})"
            )
        
        # Update to cancelled state
        now = datetime.now(timezone.utc)
        
        await db.transfer_jobs_collection.update_one(
            {"id": transfer_id},
            {
                "$set": {
                    "state": TransferState.CANCELLED.value,
                    "approved_by": admin_id,
                    "approved_at": now,
                    "approval_reason": f"REJECTED: {rejection_reason}",
                    "completed_at": now
                },
                "$push": {
                    "state_history": {
                        "state": TransferState.CANCELLED.value,
                        "timestamp": now.isoformat(),
                        "reason": f"Admin rejected: {rejection_reason}",
                        "actor_id": admin_id
                    }
                }
            }
        )
        
        # Log to immutable ledger
        await db.transfers_ledger_collection.insert_one({
            "id": str(uuid.uuid4()),
            "transfer_job_id": transfer_id,
            "event_type": "rejection",
            "from_state": TransferState.NEEDS_APPROVAL.value,
            "to_state": TransferState.CANCELLED.value,
            "timestamp": now,
            "actor_id": admin_id,
            "reason": f"Admin rejected: {rejection_reason}"
        })
        
        return {
            "success": True,
            "message": "Transfer rejected successfully",
            "transfer_id": transfer_id,
            "state": TransferState.CANCELLED.value
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Reject transfer error: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to reject transfer: {str(e)}"
        )
