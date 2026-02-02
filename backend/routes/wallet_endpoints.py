"""
Wallet Hub API Endpoints
Provides balance information and funding plans
"""

from fastapi import APIRouter, HTTPException, Depends
from typing import Dict
import logging
from datetime import datetime, timezone

from auth import get_current_user
from engines.wallet_manager import wallet_manager
from engines.funding_plan_manager import funding_plan_manager
from jobs.wallet_balance_monitor import wallet_balances_collection
import database as db
from config.exchange_config import get_required_fields, get_deposit_requirements

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/wallet", tags=["Wallet Hub"])

@router.get("/balances-legacy", include_in_schema=False)
async def get_wallet_balances_legacy(user_id: str = Depends(get_current_user)):
    """Get all wallet balances for user (LEGACY - use /api/wallet/balances from wallet_hub instead)"""
    try:
        # Safe check for wallet collection initialization
        if wallet_balances_collection is None:
            logger.warning("wallet_balances_collection not initialized, returning empty state")
            return {
                "user_id": user_id,
                "master_wallet": {
                    "total_zar": 0,
                    "btc_balance": 0,
                    "eth_balance": 0,
                    "xrp_balance": 0,
                    "exchange": "luno",
                    "status": "not_configured"
                },
                "exchanges": {},
                "timestamp": None,
                "last_updated": "never",
                "note": "Wallet collection not initialized. Check database setup."
            }
        
        # Get cached balances
        cached = await wallet_balances_collection.find_one(
            {"user_id": user_id},
            {"_id": 0}
        )
        
        if cached:
            # Normalize field names for frontend compatibility
            if cached.get('master_wallet'):
                mw = cached['master_wallet']
                cached['master_wallet'] = {
                    "total_zar": mw.get('total_zar', 0),
                    "btc_balance": mw.get('btc', mw.get('btc_balance', 0)),
                    "eth_balance": mw.get('eth', mw.get('eth_balance', 0)),
                    "xrp_balance": mw.get('xrp', mw.get('xrp_balance', 0)),
                    "exchange": mw.get('exchange', 'luno')
                }
            return cached
        
        # If no cached data, fetch fresh
        master_balance = await wallet_manager.get_master_balance(user_id)
        
        # Handle API key not configured case
        if master_balance.get('error'):
            normalized_master = {
                "total_zar": 0,
                "btc_balance": 0,
                "eth_balance": 0,
                "xrp_balance": 0,
                "exchange": "luno",
                "error": master_balance['error']
            }
        else:
            # Normalize master_balance field names for frontend
            normalized_master = {
                "total_zar": master_balance.get('total_zar', 0),
                "btc_balance": master_balance.get('btc', 0),
                "eth_balance": master_balance.get('eth', 0),
                "xrp_balance": master_balance.get('xrp', 0),
                "exchange": master_balance.get('exchange', 'luno')
            }
        
        # Get exchange balances (placeholder for now - will be populated by wallet monitor job)
        exchange_balances = {}
        
        return {
            "user_id": user_id,
            "master_wallet": normalized_master,
            "exchanges": exchange_balances,
            "timestamp": None,
            "last_updated": "just_now"
        }
        
    except Exception as e:
        import traceback
        logger.error(f"Get wallet balances error: {e}")
        logger.error(f"Traceback: {traceback.format_exc()}")
        # Return safe empty state instead of 500 error
        return {
            "user_id": user_id,
            "master_wallet": {
                "total_zar": 0,
                "btc_balance": 0,
                "eth_balance": 0,
                "xrp_balance": 0,
                "exchange": "luno",
                "status": "error"
            },
            "exchanges": {},
            "timestamp": None,
            "last_updated": "error",
            "error": str(e)
        }

@router.get("/requirements")
async def get_capital_requirements(user_id: str = Depends(get_current_user)):
    """
    Get capital requirements per exchange based on active bots.
    Returns required exchanges, required fields per exchange, whether keys are present,
    and deposit requirements if applicable.
    """
    try:
        # Safe check for collection initialization
        if db.bots_collection is None:
            logger.warning("bots_collection not initialized")
            return {
                "user_id": user_id,
                "requirements": {},
                "summary": {
                    "total_required": 0,
                    "total_available": 0,
                    "overall_health": "unknown"
                },
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "note": "Collections not initialized"
            }
        
        # Get all active bots
        bots = await db.bots_collection.find(
            {"user_id": user_id, "status": "active"},
            {"_id": 0}
        ).to_list(1000)
        
        # Get user's API keys to check what's configured
        api_keys_present = {}
        try:
            user_keys = await db.api_keys_collection.find(
                {"user_id": user_id},
                {"_id": 0, "provider": 1, "exchange": 1}
            ).to_list(100)
            
            for key in user_keys:
                provider = key.get('provider') or key.get('exchange')
                if provider:
                    api_keys_present[provider.lower()] = True
        except Exception as e:
            logger.warning(f"Could not fetch API keys: {e}")
        
        # Calculate required capital per exchange
        requirements = {}
        
        for bot in bots:
            exchange = bot.get('exchange', 'unknown').lower()
            capital = bot.get('current_capital', 0)
            
            if exchange not in requirements:
                requirements[exchange] = {
                    "exchange": exchange,
                    "required_capital": 0,
                    "bots_count": 0,
                    "available_capital": 0,
                    "surplus_deficit": 0,
                    "health": "unknown",
                    "api_key_present": api_keys_present.get(exchange, False),
                    "required_fields": get_required_fields(exchange),
                    "deposit_requirements": get_deposit_requirements(exchange)
                }
            
            requirements[exchange]['required_capital'] += capital
            requirements[exchange]['bots_count'] += 1
        
        # Initialize balances to None
        balances = None
        
        # Get actual balances (safe check for collection)
        if wallet_balances_collection is not None:
            balances = await wallet_balances_collection.find_one(
                {"user_id": user_id},
                {"_id": 0}
            )
            
            if balances:
                for exchange, req in requirements.items():
                    exchange_balance = balances.get('exchanges', {}).get(exchange, {})
                    available = exchange_balance.get('zar_balance', 0)
                    req['available_capital'] = available
                    req['surplus_deficit'] = available - req['required_capital']
                    
                    # Determine health
                    if req['surplus_deficit'] >= 1000:
                        req['health'] = 'healthy'
                    elif req['surplus_deficit'] >= 0:
                        req['health'] = 'adequate'
                    elif req['surplus_deficit'] >= -500:
                        req['health'] = 'warning'
                    else:
                        req['health'] = 'critical'
        else:
            logger.warning("wallet_balances_collection not initialized")
        
        # Calculate summary
        total_required = sum(req['required_capital'] for req in requirements.values())
        total_available = sum(req['available_capital'] for req in requirements.values())
        
        return {
            "user_id": user_id,
            "requirements": requirements,
            "summary": {
                "total_required": round(total_required, 2),
                "total_available": round(total_available, 2),
                "overall_health": "healthy" if total_available >= total_required else "warning",
                "exchanges_count": len(requirements),
                "keys_configured": sum(1 for req in requirements.values() if req['api_key_present'])
            },
            "timestamp": balances.get('timestamp') if balances else datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as e:
        logger.error(f"Get capital requirements error: {e}")
        # Return safe default instead of 500
        return {
            "user_id": user_id,
            "requirements": {},
            "summary": {
                "total_required": 0,
                "total_available": 0,
                "overall_health": "error"
            },
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "error": str(e)
        }

@router.get("/funding-plans")
async def get_funding_plans(
    status: str = None,
    user_id: str = Depends(get_current_user)
):
    """Get all funding plans for user"""
    try:
        plans = await funding_plan_manager.get_user_funding_plans(
            user_id,
            status=status
        )
        
        return {
            "user_id": user_id,
            "plans": plans,
            "count": len(plans)
        }
        
    except Exception as e:
        logger.error(f"Get funding plans error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/funding-plans/{plan_id}")
async def get_funding_plan(plan_id: str, user_id: str = Depends(get_current_user)):
    """Get specific funding plan"""
    try:
        plan = await funding_plan_manager.get_funding_plan(plan_id)
        
        if plan.get('error'):
            raise HTTPException(status_code=404, detail=plan['error'])
        
        # Verify ownership
        if plan.get('user_id') != user_id:
            raise HTTPException(status_code=403, detail="Not authorized")
        
        return plan
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get funding plan error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/funding-plans/{plan_id}/cancel")
async def cancel_funding_plan(plan_id: str, user_id: str = Depends(get_current_user)):
    """Cancel a funding plan"""
    try:
        plan = await funding_plan_manager.get_funding_plan(plan_id)
        
        if plan.get('error'):
            raise HTTPException(status_code=404, detail=plan['error'])
        
        # Verify ownership
        if plan.get('user_id') != user_id:
            raise HTTPException(status_code=403, detail="Not authorized")
        
        success = await funding_plan_manager.cancel_funding_plan(plan_id)
        
        return {
            "success": success,
            "plan_id": plan_id,
            "message": "Funding plan cancelled"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Cancel funding plan error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/transfer-manual", include_in_schema=False)
async def create_transfer_manual(
    from_exchange: str,
    to_exchange: str,
    amount: float,
    currency: str = "ZAR",  # Default ZAR for South African users, configurable per request
    user_id: str = Depends(get_current_user)
):
    """
    Create and execute internal transfer between exchanges (LEGACY - use /api/wallet/transfer from wallet_hub instead)
    
    SAFETY: Validates balances, creates audit trail, monitors limits
    Only transfers between user's own exchange accounts
    
    Parameters:
    - from_exchange: Source exchange (luno, binance, kucoin)
    - to_exchange: Destination exchange
    - amount: Transfer amount
    - currency: Currency code (default: ZAR, also supports: BTC, ETH, USDT)
    
    Note: Currency defaults to ZAR for South African market.
    Set explicitly for international users (e.g., currency="USDT" for Binance/KuCoin)
    """
    try:
        # Validation
        if amount <= 0:
            raise HTTPException(status_code=400, detail="Amount must be positive")
        
        if from_exchange == to_exchange:
            raise HTTPException(status_code=400, detail="Cannot transfer to same exchange")
        
        # Import supported exchanges from canonical source
        from config.platforms import SUPPORTED_PLATFORMS
        if from_exchange not in SUPPORTED_PLATFORMS or to_exchange not in SUPPORTED_PLATFORMS:
            raise HTTPException(
                status_code=400, 
                detail=f"Unsupported exchange. Supported: {', '.join(SUPPORTED_PLATFORMS)}"
            )
        
        # Get current balances
        from_balance = await wallet_manager.get_exchange_balance(user_id, from_exchange)
        to_balance = await wallet_manager.get_exchange_balance(user_id, to_exchange)
        
        # Check source has sufficient balance
        available = from_balance.get(currency.upper(), 0)
        if available < amount:
            raise HTTPException(
                status_code=400,
                detail=f"Insufficient balance. Available: {currency}{available:.2f}, Requested: {currency}{amount:.2f}"
            )
        
        # For now, create a transfer record and return instructions
        # Full automation requires exchange API withdrawal/deposit setup
        transfer_record = {
            "user_id": user_id,
            "from_exchange": from_exchange,
            "to_exchange": to_exchange,
            "amount": amount,
            "currency": currency,
            "status": "pending_manual",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "instructions_provided": True
        }
        
        # Store transfer record in database
        result = await db.wallet_transfers.insert_one(transfer_record)
        transfer_id = str(result.inserted_id)
        
        # Create detailed instructions
        instructions = {
            "transfer_id": transfer_id,
            "from": from_exchange,
            "to": to_exchange,
            "amount": amount,
            "currency": currency,
            "status": "pending_manual",
            "steps": [
                f"1. Log into {from_exchange.capitalize()} account",
                f"2. Navigate to Withdraw/Send section",
                f"3. Select {currency}",
                f"4. Enter amount: {currency}{amount:.2f}",
                f"5. Get deposit address from {to_exchange.capitalize()}:",
                f"   - Log into {to_exchange.capitalize()}",
                f"   - Go to Deposit section",
                f"   - Copy {currency} deposit address",
                f"6. Paste address in {from_exchange.capitalize()} withdrawal form",
                f"7. Confirm withdrawal (verify all details!)",
                f"8. Wait for blockchain confirmation (10-60 minutes)",
                f"9. Funds will appear in {to_exchange.capitalize()} automatically"
            ],
            "warnings": [
                f"⚠️ DOUBLE-CHECK the deposit address - wrong address = permanent loss!",
                f"⚠️ Ensure you're sending {currency} to a {currency} address",
                f"⚠️ Small test transfer recommended for first time",
                f"⚠️ Network fees will be deducted from the amount"
            ],
            "safety_tips": [
                "✅ Use exchange's internal transfer if available (faster, cheaper)",
                "✅ Save confirmation emails and transaction IDs",
                "✅ Contact support if funds don't arrive within 2 hours"
            ]
        }
        
        # Audit log
        from engines.audit_logger import audit_logger
        await audit_logger.log_event(
            event_type="wallet_transfer_initiated",
            user_id=user_id,
            details={
                "transfer_id": transfer_id,
                "from": from_exchange,
                "to": to_exchange,
                "amount": amount,
                "currency": currency
            },
            severity="info"
        )
        
        logger.info(f"Transfer created: {user_id[:8]} {from_exchange} -> {to_exchange} {currency}{amount}")
        
        return {
            "success": True,
            "message": "Transfer instructions generated",
            "transfer_id": transfer_id,
            "instructions": instructions,
            "note": "🚧 Automated transfers coming soon! For now, follow manual steps carefully."
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Create transfer error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
