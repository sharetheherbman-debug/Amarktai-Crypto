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
from services.paper_wallet_service import paper_wallet_service
from services.system_mode_service import system_mode_service
from engines.wallet_manager import wallet_manager

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


class PaperDepositRequest(BaseModel):
    amount: float
    currency: str = "ZAR"


class PaperResetRequest(BaseModel):
    confirm: bool = False


class PaperSetBalanceRequest(BaseModel):
    balance_zar: float
    confirmed: bool = False


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


async def get_paper_wallet_allocated_balances(user_id: str) -> Dict:
    """Calculate allocated paper wallet balances from active bot ledgers"""
    try:
        if db.paper_ledger_collection is None:
            return {}
        pipeline = [
            {"$match": {"user_id": user_id, "status": "active"}},
            {"$group": {"_id": "$currency", "total": {"$sum": "$current_balance"}}}
        ]
        results = await db.paper_ledger_collection.aggregate(pipeline).to_list(100)
        return {r.get("_id") or "ZAR": round(float(r.get("total", 0) or 0), 2) for r in results}
        
    except Exception as e:
        logger.error(f"Get paper wallet allocated balances error: {e}")
        return {}


async def get_paper_wallet_balances(user_id: str) -> Dict:
    """Calculate total paper wallet balances (available + allocated)."""
    available = await paper_wallet_service.get_balances(user_id)
    allocated = await get_paper_wallet_allocated_balances(user_id)
    totals = {}
    for currency, amount in available.get("balances", {}).items():
        totals[currency] = totals.get(currency, 0) + float(amount or 0)
    for currency, amount in allocated.items():
        totals[currency] = totals.get(currency, 0) + float(amount or 0)
    return {currency: round(amount, 2) for currency, amount in totals.items()}


@router.get("/paper")
async def get_paper_wallet(user_id: str = Depends(get_current_user)):
    """Get paper wallet balances and totals with canonical funded status."""
    from services.canonical import get_canonical_wallet_truth
    available = await paper_wallet_service.get_balances(user_id)
    allocated = await get_paper_wallet_allocated_balances(user_id)
    totals = await get_paper_wallet_balances(user_id)
    total_value = sum(float(value or 0) for value in totals.values())
    # Derive funded_status from canonical service (single source of truth)
    wallet_truth = await get_canonical_wallet_truth(user_id)
    funded_status = wallet_truth["funded_status"]
    return {
        "user_id": user_id,
        "available": available.get("balances", {}),
        "allocated": allocated,
        "balances": totals,
        "total": round(total_value, 2),
        "funded_status": funded_status,
        "status": funded_status,
        "shortfall": wallet_truth["shortfall"],
        "required": wallet_truth["required"],
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


@router.post("/paper/deposit")
async def deposit_paper_wallet(
    request: PaperDepositRequest,
    user_id: str = Depends(get_current_user)
):
    if request.amount <= 0:
        raise HTTPException(status_code=400, detail="Amount must be positive")
    result = await paper_wallet_service.deposit(user_id, request.amount, request.currency)
    try:
        await db.audit_logs_collection.insert_one({
            "user_id": user_id,
            "action": "paper_wallet_topup",
            "details": {
                "amount": request.amount,
                "currency": request.currency.upper()
            },
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
    except Exception as e:
        logger.warning(f"Paper wallet topup audit failed: {e}")
    return {
        "success": True,
        "balances": result.get("balances", {}),
        "total": result.get("total", 0),
        "currency": request.currency.upper()
    }


@router.post("/paper/topup")
async def topup_paper_wallet(
    request: PaperDepositRequest,
    user_id: str = Depends(get_current_user)
):
    """Top up paper wallet (alias for deposit for backward compatibility)."""
    return await deposit_paper_wallet(request, user_id)


@router.post("/paper/reset")
async def reset_paper_wallet(
    request: PaperResetRequest,
    user_id: str = Depends(get_current_user)
):
    if not request.confirm:
        raise HTTPException(status_code=400, detail="Confirmation required")
    result = await paper_wallet_service.reset(user_id)
    return {
        "success": True,
        "balances": result.get("balances", {}),
        "total": result.get("total", 0)
    }


@router.post("/paper/set-balance")
async def set_paper_wallet_balance(
    request: PaperSetBalanceRequest,
    user_id: str = Depends(get_current_user)
):
    """Set (overwrite) the paper wallet ZAR balance to an exact amount.

    This is the canonical endpoint for the dashboard reset/fund flow.
    Unlike ``/paper/deposit`` (which increments), this endpoint
    unconditionally sets ``balance_zar`` as the new available ZAR balance.

    Args:
        balance_zar: Target ZAR balance (must be >= 0)
        confirmed: Must be ``true`` to execute; if ``false`` a dry-run
                   preview is returned with no DB change.

    Returns:
        success, balances, total, currency, action
    """
    if request.balance_zar < 0:
        raise HTTPException(status_code=400, detail="balance_zar must be non-negative")

    if not request.confirmed:
        return {
            "success": False,
            "preview": True,
            "balance_zar": request.balance_zar,
            "message": "Send confirmed=true to apply this balance.",
        }

    result = await paper_wallet_service.set_balance(user_id, request.balance_zar, "ZAR")

    try:
        await db.audit_logs_collection.insert_one({
            "user_id": user_id,
            "action": "paper_wallet_set_balance",
            "details": {
                "balance_zar": request.balance_zar,
                "currency": "ZAR",
            },
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
    except Exception as e:
        logger.warning(f"Paper wallet set-balance audit failed: {e}")

    return {
        "success": True,
        "balances": result.get("balances", {}),
        "total": result.get("total", 0),
        "currency": "ZAR",
    }


@router.get("/live")
async def get_live_wallet(user_id: str = Depends(get_current_user)):
    """Get live wallet balances when live mode is enabled."""
    mode = await system_mode_service.get_current_mode(user_id)
    if mode != "live":
        raise HTTPException(
            status_code=400,
            detail="Live wallet unavailable while live trading is disabled. Enable live mode first."
        )
    master_balance = await wallet_manager.get_master_balance(user_id)
    if master_balance.get("error"):
        raise HTTPException(status_code=400, detail=master_balance.get("error"))
    exchange_balances = await wallet_manager.get_all_balances(user_id)
    return {
        "success": True,
        "master_wallet": master_balance,
        "exchanges": exchange_balances,
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


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
        allocated_balances = await get_paper_wallet_allocated_balances(user_id)
        
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
        
        master_wallet = {}
        try:
            master_balance = await wallet_manager.get_master_balance(user_id)
            if master_balance.get("error"):
                master_wallet = {
                    "total_zar": 0,
                    "btc_balance": 0,
                    "eth_balance": 0,
                    "xrp_balance": 0,
                    "exchange": "luno",
                    "error": master_balance.get("error")
                }
            else:
                master_wallet = {
                    "total_zar": master_balance.get("total_zar", 0),
                    "btc_balance": master_balance.get("btc", 0),
                    "eth_balance": master_balance.get("eth", 0),
                    "xrp_balance": master_balance.get("xrp", 0),
                    "exchange": master_balance.get("exchange", "luno")
                }
        except Exception as e:
            logger.warning(f"Master wallet lookup failed: {e}")
            master_wallet = {
                "total_zar": 0,
                "btc_balance": 0,
                "eth_balance": 0,
                "xrp_balance": 0,
                "exchange": "luno",
                "error": str(e)
            }

        return {
            "user_id": user_id,
            "paper_balances": paper_balances,
            "paper_allocated": allocated_balances,
            "live_balances": live_balances,
            "total_paper": round(sum(paper_balances.values()), 2),
            "total_live": round(sum(live_balances.values()), 2),
            "master_wallet": master_wallet,
            "zar": master_wallet.get("total_zar", 0),
            "btc": master_wallet.get("btc_balance", 0),
            "btc_balance": master_wallet.get("btc_balance", 0),
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


# ── Currency / Crypto Converter ───────────────────────────────────────────────
# Reuses the canonical fx_normalizer as single source of truth.
# Supports ZAR, USD, GBP, EUR, USDT, BTC, ETH.
# This is intentionally a lightweight synchronous-style endpoint; for live
# crypto quotes the caller may refresh on demand.

_SUPPORTED_CONVERTER_CURRENCIES = {"ZAR", "USD", "GBP", "EUR", "USDT", "BUSD", "USDC", "BTC", "ETH"}

# Static fallback cross-rates vs ZAR (operator-overridable via env vars).
import os as _os
_USD_ZAR: float = float(_os.getenv("USD_ZAR_RATE", "18.5"))
_GBP_ZAR: float = float(_os.getenv("GBP_ZAR_RATE", "23.5"))
_EUR_ZAR: float = float(_os.getenv("EUR_ZAR_RATE", "20.0"))
_BTC_ZAR: float = float(_os.getenv("BTC_ZAR_RATE", "1400000.0"))
_ETH_ZAR: float = float(_os.getenv("ETH_ZAR_RATE", "60000.0"))


def _get_to_zar_rate(currency: str) -> tuple:
    """Return (rate, source) to convert *currency* → ZAR.

    This helper extends fx_normalizer.get_fx_rate() to cover more fiat
    currencies (USD, GBP, EUR) and crypto (BTC, ETH) beyond USDT.
    For USDT-family and ZAR the canonical fx_normalizer is always used.
    """
    from services.fx_normalizer import get_fx_rate as _fx_get
    cur = currency.upper()
    if cur == "ZAR":
        return 1.0, "identity"
    # USDT-family → delegate to canonical normalizer
    if cur in {"USDT", "BUSD", "USDC"}:
        return _fx_get("USDT", "ZAR")
    # Other fiat / crypto — static fallback with env-var override
    _fallbacks = {
        "USD": (_USD_ZAR, "env_fallback_usd"),
        "GBP": (_GBP_ZAR, "env_fallback_gbp"),
        "EUR": (_EUR_ZAR, "env_fallback_eur"),
        "BTC": (_BTC_ZAR, "env_fallback_btc"),
        "ETH": (_ETH_ZAR, "env_fallback_eth"),
    }
    if cur in _fallbacks:
        return _fallbacks[cur]
    logger.warning("Converter: unknown currency %s; using 1.0 identity", cur)
    return 1.0, "unknown"


class ConvertRequest(BaseModel):
    amount: float
    from_currency: str
    to_currency: str = "ZAR"


@router.post("/converter")
async def convert_currency(
    req: ConvertRequest,
    user_id: str = Depends(get_current_user),
):
    """Convert an amount between supported currencies.

    Single source of truth: uses fx_normalizer for USDT/BUSD/USDC→ZAR; static
    fallback rates (env-overridable) for USD, GBP, EUR, BTC, ETH.

    Supported currencies: ZAR, USD, GBP, EUR, USDT, BUSD, USDC, BTC, ETH.

    Returns full labeled response — no naked numbers.
    """
    from_cur = req.from_currency.upper().strip()
    to_cur = req.to_currency.upper().strip()

    if from_cur not in _SUPPORTED_CONVERTER_CURRENCIES:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported from_currency '{from_cur}'. Supported: {sorted(_SUPPORTED_CONVERTER_CURRENCIES)}",
        )
    if to_cur not in _SUPPORTED_CONVERTER_CURRENCIES:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported to_currency '{to_cur}'. Supported: {sorted(_SUPPORTED_CONVERTER_CURRENCIES)}",
        )
    if req.amount < 0:
        raise HTTPException(status_code=400, detail="amount must be >= 0")

    # Convert: from_currency → ZAR → to_currency
    from_rate_to_zar, from_source = _get_to_zar_rate(from_cur)
    to_rate_to_zar, to_source = _get_to_zar_rate(to_cur)

    # Guard against zero rates (should not happen for supported currencies)
    if to_rate_to_zar <= 0:
        to_rate_to_zar = 1.0

    amount_in_zar = req.amount * from_rate_to_zar
    converted_amount = round(amount_in_zar / to_rate_to_zar, 8) if to_cur != "ZAR" else round(amount_in_zar, 2)

    return {
        "input_amount": req.amount,
        "input_currency": from_cur,
        "output_amount": converted_amount,
        "output_currency": to_cur,
        "via_zar_amount": round(amount_in_zar, 2),
        "from_rate_to_zar": round(from_rate_to_zar, 6),
        "to_rate_to_zar": round(to_rate_to_zar, 6),
        "effective_rate": round(from_rate_to_zar / to_rate_to_zar, 8) if to_rate_to_zar > 0 else None,
        "rate_source": f"{from_source}/{to_source}",
        "supported_currencies": sorted(_SUPPORTED_CONVERTER_CURRENCIES),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@router.get("/converter/rates")
async def get_converter_rates(user_id: str = Depends(get_current_user)):
    """Return all current converter rates relative to ZAR.

    Useful for the frontend to pre-populate the converter widget.
    """
    rates = {}
    for cur in sorted(_SUPPORTED_CONVERTER_CURRENCIES):
        rate, source = _get_to_zar_rate(cur)
        rates[cur] = {
            "rate_to_zar": round(rate, 6),
            "source": source,
        }
    return {
        "rates": rates,
        "base_currency": "ZAR",
        "supported_currencies": sorted(_SUPPORTED_CONVERTER_CURRENCIES),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
