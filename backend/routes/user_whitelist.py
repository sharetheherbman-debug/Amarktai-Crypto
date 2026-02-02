"""
User Whitelist Management Routes

User-facing endpoints for managing withdrawal address whitelist requests.
"""

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import Optional
import logging

from auth import get_current_user
from services.address_whitelist import address_whitelist_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/wallet/whitelist", tags=["Wallet - Whitelist"])


class WhitelistAddressRequest(BaseModel):
    """Request to add a new whitelisted address"""
    exchange: str
    currency: str
    address: str
    tag: Optional[str] = None
    network: Optional[str] = None
    label: Optional[str] = None


@router.post("/request")
async def request_whitelist_address(
    request: WhitelistAddressRequest,
    user_id: str = Depends(get_current_user)
):
    """
    Request to add a new withdrawal address to whitelist
    
    Requires admin approval before the address can be used.
    
    Request Body:
    {
        "exchange": "binance",
        "currency": "BTC",
        "address": "bc1q...",
        "tag": "12345678",  // Optional, for XRP/XLM etc.
        "network": "BTC",  // Optional
        "label": "My Binance BTC Address"  // Optional
    }
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
            raise HTTPException(
                status_code=400,
                detail=result.get("message", "Failed to add address")
            )
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error requesting whitelist address: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to request address: {str(e)}"
        )


@router.get("/my-addresses")
async def get_my_whitelist_addresses(
    user_id: str = Depends(get_current_user),
    exchange: Optional[str] = None,
    currency: Optional[str] = None
):
    """
    Get user's whitelisted addresses
    
    Query Parameters:
    - exchange: Optional exchange filter
    - currency: Optional currency filter
    
    Returns list of addresses with their approval status.
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
        logger.error(f"Error getting whitelist addresses: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get addresses: {str(e)}"
        )


@router.delete("/{address_id}")
async def delete_my_whitelist_address(
    address_id: str,
    user_id: str = Depends(get_current_user)
):
    """
    Delete a user's whitelisted address
    
    Users can only delete their own addresses.
    """
    try:
        result = await address_whitelist_service.delete_address(address_id, user_id)
        
        if not result["success"]:
            error_code = result.get("error")
            if error_code == "NOT_FOUND":
                raise HTTPException(status_code=404, detail="Address not found")
            elif error_code == "UNAUTHORIZED":
                raise HTTPException(status_code=403, detail="Not authorized")
            else:
                raise HTTPException(status_code=400, detail=result.get("message"))
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting address: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to delete address: {str(e)}"
        )
