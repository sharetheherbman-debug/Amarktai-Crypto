"""
Wallet Hub for All 7 exchanges

Provides unified wallet interface for:
- Luno, Binance, KuCoin, Bybit, Kraken, Bitget, Gate.io
- Paper wallet simulation
- Live wallet integration (when keys available)
- Production-safe transfers with state machine
"""

from fastapi import APIRouter, HTTPException, Depends
from typing import Optional, Dict, List
from pydantic import BaseModel
import logging
from datetime import datetime, timezone

from auth import get_current_user
import database as db
from realtime_events import manager
from config.platforms import SUPPORTED_PLATFORMS
from services.transfer_state_machine import transfer_state_machine

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/wallet", tags=["Wallet Hub"])


class TransferRequest(BaseModel):
    from_exchange: str
    to_exchange: str
    amount: float
    currency: str = "ZAR"
    idempotency_key: str  # Required for production safety
    totp_code: Optional[str] = None  # Required if 2FA enabled
    withdrawal_address: Optional[str] = None  # Optional whitelisted address
    notes: Optional[str] = None


@router.get("/health")
async def get_wallet_health(user_id: str = Depends(get_current_user)):
    """
    Get wallet health status for all 7 exchanges
    
    Shows:
    - Keys status (missing, connected, error)
    - Paper balances
    - Live balances (if keys available)
    - Exchange-specific details
    """
    try:
        # Check API keys for all supported exchanges
        wallet_status = {}
        
        for exchange in SUPPORTED_PLATFORMS:
            # Check if user has keys for this exchange
            api_key = await db.api_keys_collection.find_one({
                "user_id": user_id,
                "provider": exchange
            })
            
            if not api_key:
                wallet_status[exchange] = {
                    "status": "keys_missing",
                    "message": f"No API keys configured for {exchange.upper()}",
                    "has_keys": False,
                    "paper_mode_available": True
                }
            elif not api_key.get("last_test_ok"):
                wallet_status[exchange] = {
                    "status": "keys_untested",
                    "message": f"API keys exist but not tested",
                    "has_keys": True,
                    "paper_mode_available": True
                }
            else:
                wallet_status[exchange] = {
                    "status": "connected",
                    "message": f"Connected to {exchange.upper()}",
                    "has_keys": True,
                    "paper_mode_available": True,
                    "last_tested": api_key.get("last_tested_at")
                }
        
        # Get paper wallet balances (simulated from bots)
        paper_balances = await get_paper_wallet_balances(user_id)
        
        return {
            "user_id": user_id,
            "exchanges": wallet_status,
            "paper_balances": paper_balances,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as e:
        logger.error(f"Get wallet health error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


async def get_paper_wallet_balances(user_id: str) -> Dict:
    """Calculate paper wallet balances from bot capital"""
    try:
        # Group bot capital by exchange
        bots_cursor = db.bots_collection.find(
            {
                "user_id": user_id,
                "trading_mode": "paper",
                "status": {"$nin": ["deleted"]}
            },
            {"_id": 0, "exchange": 1, "current_capital": 1}
        )
        bots = await bots_cursor.to_list(1000)
        
        # Sum by exchange
        balances = {}
        for bot in bots:
            exchange = bot.get("exchange", "unknown")
            capital = bot.get("current_capital", 0)
            
            if exchange not in balances:
                balances[exchange] = 0
            balances[exchange] += capital
        
        # Round all balances
        for exchange in balances:
            balances[exchange] = round(balances[exchange], 2)
        
        return balances
        
    except Exception as e:
        logger.error(f"Get paper wallet balances error: {e}")
        return {}


@router.post("/transfer")
async def transfer_funds(
    request: TransferRequest,
    user_id: str = Depends(get_current_user)
):
    """
    Transfer funds between exchanges - PRODUCTION SAFE
    
    Uses transfer_state_machine for:
    - Idempotency (prevents double-send)
    - 2FA enforcement (if REQUIRE_2FA_FOR_WITHDRAWALS=1)
    - Approval workflows (for large amounts)
    - Reserved funds checking
    - State tracking (requested → approved → queued → broadcast → confirmed)
    
    Paper mode: Simulates transfer
    Live mode: Executes real CCXT withdrawal with all safety checks
    """
    try:
        # Validate exchanges
        if request.from_exchange not in SUPPORTED_PLATFORMS:
            raise HTTPException(status_code=400, detail=f"Invalid source exchange: {request.from_exchange}")
        if request.to_exchange not in SUPPORTED_PLATFORMS:
            raise HTTPException(status_code=400, detail=f"Invalid destination exchange: {request.to_exchange}")
        
        # Validate amount
        if request.amount <= 0:
            raise HTTPException(status_code=400, detail="Amount must be positive")
        
        # Check if user has keys for both exchanges
        from_keys = await db.api_keys_collection.find_one({
            "user_id": user_id,
            "provider": request.from_exchange
        })
        
        to_keys = await db.api_keys_collection.find_one({
            "user_id": user_id,
            "provider": request.to_exchange
        })
        
        # Determine if this is paper or live transfer
        is_paper = not (from_keys and to_keys and from_keys.get("last_test_ok") and to_keys.get("last_test_ok"))
        
        if is_paper:
            # Paper mode transfer (simulated) - bypass state machine for simplicity
            transfer_id = f"paper_transfer_{datetime.now(timezone.utc).timestamp()}"
            
            # Log the transfer
            await db.wallet_transfers_collection.insert_one({
                "id": transfer_id,
                "user_id": user_id,
                "from_exchange": request.from_exchange,
                "to_exchange": request.to_exchange,
                "amount": request.amount,
                "currency": request.currency,
                "status": "simulated",
                "mode": "paper",
                "idempotency_key": request.idempotency_key,
                "timestamp": datetime.now(timezone.utc).isoformat()
            })
            
            # Broadcast realtime event
            await manager.broadcast_json({
                "type": "wallet_transfer",
                "user_id": user_id,
                "transfer_id": transfer_id,
                "mode": "paper",
                "from_exchange": request.from_exchange,
                "to_exchange": request.to_exchange,
                "amount": request.amount,
                "timestamp": datetime.now(timezone.utc).isoformat()
            })
            
            logger.info(f"Paper transfer simulated: {request.amount} {request.currency} from {request.from_exchange} to {request.to_exchange}")
            
            return {
                "success": True,
                "transfer_id": transfer_id,
                "mode": "paper",
                "message": "Transfer simulated (paper mode)",
                "from_exchange": request.from_exchange,
                "to_exchange": request.to_exchange,
                "amount": request.amount,
                "currency": request.currency
            }
        else:
            # Live mode transfer - use production-safe state machine
            logger.info(f"Live transfer requested: {request.amount} {request.currency} from {request.from_exchange} to {request.to_exchange}")
            
            result = await transfer_state_machine.request_transfer(
                user_id=user_id,
                from_exchange=request.from_exchange,
                to_exchange=request.to_exchange,
                currency=request.currency,
                amount=request.amount,
                idempotency_key=request.idempotency_key,
                totp_code=request.totp_code,
                withdrawal_address=request.withdrawal_address,
                notes=request.notes
            )
            
            if not result.get("success"):
                # Return error without raising exception (error codes expected by frontend)
                return result
            
            return {
                **result,
                "mode": "live",
                "from_exchange": request.from_exchange,
                "to_exchange": request.to_exchange,
                "amount": request.amount,
                "currency": request.currency
            }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Transfer funds error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/balances")
async def get_all_balances(user_id: str = Depends(get_current_user)):
    """
    Get balances across all 7 exchanges
    
    Returns both paper and live balances (if keys available).
    """
    try:
        # Get paper balances
        paper_balances = await get_paper_wallet_balances(user_id)
        
        # Get live balances when keys are available
        live_balances = {}
        
        for exchange in SUPPORTED_PLATFORMS:
            api_key_doc = await db.api_keys_collection.find_one({
                "user_id": user_id,
                "service": exchange
            })
            
            if api_key_doc and api_key_doc.get("last_test_ok"):
                # Keys exist and were tested successfully
                try:
                    # Use ccxt to get real balance
                    from ccxt_service import ccxt_service
                    balance_data = await ccxt_service.get_balance(user_id, exchange)
                    
                    if balance_data and balance_data.get("total"):
                        # Convert to ZAR equivalent if needed
                        total_usd = sum([
                            float(balance_data["total"].get(currency, 0))
                            for currency in balance_data["total"]
                        ])
                        # Simple approximation: 1 USD = 18 ZAR
                        live_balances[exchange] = round(total_usd * 18, 2)
                    else:
                        live_balances[exchange] = 0.0
                        
                except Exception as e:
                    logger.warning(f"Failed to get live balance for {exchange}: {e}")
                    live_balances[exchange] = 0.0
            else:
                live_balances[exchange] = 0.0
        
        return {
            "user_id": user_id,
            "paper_balances": paper_balances,
            "live_balances": live_balances,
            "total_paper": round(sum(paper_balances.values()), 2),
            "total_live": round(sum(live_balances.values()), 2),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as e:
        logger.error(f"Get all balances error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/transactions")
async def get_wallet_transactions(
    limit: int = 100,
    user_id: str = Depends(get_current_user)
):
    """
    Get wallet transaction history
    
    Includes transfers, deposits, withdrawals.
    """
    try:
        # Get transfers
        transfers_cursor = db.wallet_transfers_collection.find(
            {"user_id": user_id},
            {"_id": 0}
        ).sort("timestamp", -1).limit(limit)
        
        transfers = await transfers_cursor.to_list(limit)
        
        return {
            "user_id": user_id,
            "transactions": transfers,
            "total": len(transfers)
        }
        
    except Exception as e:
        logger.error(f"Get wallet transactions error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# ADMIN APPROVAL ENDPOINTS
# ============================================================================

@router.post("/admin/approve/{transfer_id}")
async def admin_approve_transfer(
    transfer_id: str,
    notes: Optional[str] = None,
    admin_id: str = Depends(get_current_user)
):
    """
    Admin approval for large transfers
    
    Requires admin role. Transitions transfer from NEEDS_APPROVAL → APPROVED → QUEUED
    """
    try:
        # Check if user is admin
        user = await db.users_collection.find_one({"id": admin_id})
        if not user or user.get("role") != "admin":
            raise HTTPException(status_code=403, detail="Admin access required")
        
        result = await transfer_state_machine.approve_transfer(
            transfer_id=transfer_id,
            admin_id=admin_id,
            notes=notes
        )
        
        if not result.get("success"):
            raise HTTPException(status_code=400, detail=result.get("error", "Approval failed"))
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Admin approve transfer error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/admin/reject/{transfer_id}")
async def admin_reject_transfer(
    transfer_id: str,
    reason: str,
    admin_id: str = Depends(get_current_user)
):
    """
    Admin rejection of transfer
    
    Requires admin role. Transitions transfer to CANCELLED and releases reserved funds
    """
    try:
        # Check if user is admin
        user = await db.users_collection.find_one({"id": admin_id})
        if not user or user.get("role") != "admin":
            raise HTTPException(status_code=403, detail="Admin access required")
        
        result = await transfer_state_machine.reject_transfer(
            transfer_id=transfer_id,
            admin_id=admin_id,
            reason=reason
        )
        
        if not result.get("success"):
            raise HTTPException(status_code=400, detail=result.get("error", "Rejection failed"))
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Admin reject transfer error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/admin/pending-approvals")
async def get_pending_approvals(
    admin_id: str = Depends(get_current_user)
):
    """
    Get all pending transfer approvals
    
    Requires admin role. Returns list of transfers needing approval
    """
    try:
        # Check if user is admin
        user = await db.users_collection.find_one({"id": admin_id})
        if not user or user.get("role") != "admin":
            raise HTTPException(status_code=403, detail="Admin access required")
        
        # Get pending approvals
        pending_cursor = db.db["transfer_jobs"].find(
            {"state": "needs_approval"},
            {"_id": 0}
        ).sort("created_at", -1)
        
        pending = await pending_cursor.to_list(100)
        
        return {
            "pending_approvals": pending,
            "count": len(pending)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get pending approvals error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
