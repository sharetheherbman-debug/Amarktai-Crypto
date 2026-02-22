"""
Live Trading Readiness Check Endpoint
Provides detailed per-exchange readiness status for live trading
"""

from fastapi import APIRouter, HTTPException, Depends
from typing import Dict, List
import logging
from datetime import datetime, timezone

from auth import get_current_user
import database as db
from ccxt_service import CCXTService
from routes.system_mode import check_live_readiness
from routes.api_key_management import get_decrypted_key

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/live", tags=["Live Trading"])

class ExchangeReadiness:
    """Per-exchange readiness check"""
    
    @staticmethod
    async def check_exchange(user_id: str, exchange_name: str) -> Dict:
        """Check readiness for specific exchange
        
        Returns:
            {
                "exchange": str,
                "ready": bool,
                "checks": {
                    "api_key": {"status": "ok|error", "message": str},
                    "connection": {"status": "ok|error", "message": str},
                    "balance": {"status": "ok|error", "message": str, "balance": float},
                    "symbol": {"status": "ok|error", "message": str, "tradable": bool},
                    "min_notional": {"status": "ok|error", "message": str}
                },
                "errors": List[str]
            }
        """
        result = {
            "exchange": exchange_name,
            "ready": False,
            "checks": {},
            "errors": [],
            "warnings": []
        }
        
        # Check 1: API Key exists and valid (stored under 'provider' or legacy 'exchange' field)
        key_doc = await db.api_keys_collection.find_one({
            "user_id": user_id,
            "$or": [{"exchange": exchange_name}, {"provider": exchange_name}]
        }, {"_id": 0})
        
        if not key_doc:
            result["checks"]["api_key"] = {
                "status": "error",
                "message": "API key not configured"
            }
            result["errors"].append("API key not configured")
            return result
        
        result["checks"]["api_key"] = {
            "status": "ok",
            "message": "API key found",
            "last_tested": key_doc.get("last_tested_at")
        }
        
        if not key_doc.get("last_test_ok"):
            result["checks"]["api_key"]["status"] = "warning"
            result["warnings"].append("API key not recently tested")
        
        # Check 2: Connection test
        try:
            decrypted = await get_decrypted_key(user_id, exchange_name)
            if not decrypted or not decrypted.get("api_key"):
                result["checks"]["connection"] = {
                    "status": "error",
                    "message": "API key decryption failed or key incomplete"
                }
                result["errors"].append("API key unavailable for connection test")
                return result

            ccxt_service = CCXTService()
            exchange = ccxt_service.init_exchange(
                exchange_name,
                decrypted['api_key'],
                decrypted.get('api_secret', ''),
                testnet=False,
                passphrase=decrypted.get('passphrase')
            )
            
            # Try to fetch balance to test connection
            import asyncio
            balance = await asyncio.to_thread(exchange.fetch_balance)
            
            result["checks"]["connection"] = {
                "status": "ok",
                "message": "Connection successful"
            }
            
            # Check 3: Balance available
            total_balance_usd = 0
            for currency, data in balance.items():
                if isinstance(data, dict) and 'total' in data:
                    # Note: Simplified balance calculation - in production, would need
                    # proper currency-to-USD conversion rates via price feed
                    total_balance_usd += data.get('total', 0)  # Assumes USD or converts at 1:1
            
            if total_balance_usd > 0:
                result["checks"]["balance"] = {
                    "status": "ok",
                    "message": f"Balance available: ~${total_balance_usd:.2f}",
                    "balance": total_balance_usd
                }
            else:
                result["checks"]["balance"] = {
                    "status": "warning",
                    "message": "Zero balance detected",
                    "balance": 0
                }
                result["warnings"].append("Zero balance on exchange")
            
            # Check 4: Symbol tradable (test with BTC/USDT as common pair)
            try:
                markets = await asyncio.to_thread(exchange.load_markets)
                test_symbol = "BTC/USDT"
                if test_symbol in markets:
                    market = markets[test_symbol]
                    result["checks"]["symbol"] = {
                        "status": "ok",
                        "message": f"{test_symbol} is tradable",
                        "tradable": True,
                        "min_amount": market.get("limits", {}).get("amount", {}).get("min"),
                        "min_cost": market.get("limits", {}).get("cost", {}).get("min")
                    }
                else:
                    result["checks"]["symbol"] = {
                        "status": "warning",
                        "message": f"{test_symbol} not found",
                        "tradable": False
                    }
            except Exception as e:
                result["checks"]["symbol"] = {
                    "status": "error",
                    "message": f"Failed to load markets: {str(e)}"
                }
                result["errors"].append(f"Market data error: {str(e)}")
            
            # Check 5: Min notional/cost requirements
            try:
                if "symbol" in result["checks"] and result["checks"]["symbol"].get("tradable"):
                    min_cost = result["checks"]["symbol"].get("min_cost", 0)
                    if min_cost and min_cost > 0:
                        result["checks"]["min_notional"] = {
                            "status": "ok",
                            "message": f"Min cost: ${min_cost:.2f}",
                            "min_cost": min_cost
                        }
                    else:
                        result["checks"]["min_notional"] = {
                            "status": "ok",
                            "message": "No minimum cost requirement"
                        }
            except Exception as e:
                logger.warning(f"Min notional check failed: {e}")
            
            # Overall readiness
            if len(result["errors"]) == 0:
                result["ready"] = True
            
        except Exception as e:
            result["checks"]["connection"] = {
                "status": "error",
                "message": f"Connection failed: {str(e)}"
            }
            result["errors"].append(f"Connection error: {str(e)}")
        
        return result


@router.get("/readiness")
async def get_live_readiness(user_id: str = Depends(get_current_user)):
    """Get comprehensive live trading readiness status
    
    Returns:
        {
            "ready": bool,
            "overall_errors": List[str],
            "exchanges": Dict[str, ReadinessCheck],
            "timestamp": str
        }
    """
    try:
        # Get overall readiness from existing check
        overall_ready, overall_errors = await check_live_readiness(user_id)
        
        # Get per-exchange readiness
        api_keys = await db.api_keys_collection.find(
            {"user_id": user_id},
            {"_id": 0, "exchange": 1, "provider": 1}
        ).to_list(100)
        
        exchanges = {}
        for key_doc in api_keys:
            exchange_name = key_doc.get('exchange') or key_doc.get('provider')
            if not exchange_name:
                continue
            readiness = await ExchangeReadiness.check_exchange(user_id, exchange_name)
            exchanges[exchange_name] = readiness
        
        return {
            "success": True,
            "ready": overall_ready,
            "overall_errors": overall_errors,
            "exchanges": exchanges,
            "exchange_count": len(exchanges),
            "ready_exchanges": sum(1 for e in exchanges.values() if e.get("ready")),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as e:
        logger.error(f"Live readiness check error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/readiness/{exchange}")
async def get_exchange_readiness(
    exchange: str,
    user_id: str = Depends(get_current_user)
):
    """Get readiness status for specific exchange"""
    try:
        readiness = await ExchangeReadiness.check_exchange(user_id, exchange)
        return {
            "success": True,
            **readiness,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    except Exception as e:
        logger.error(f"Exchange readiness check error for {exchange}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
