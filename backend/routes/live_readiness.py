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
from config.platforms import SUPPORTED_PLATFORMS

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/live", tags=["Live Trading"])

# AI/non-exchange providers that must never be treated as CCXT exchanges
NON_EXCHANGE_PROVIDERS = frozenset({'openai', 'huggingface', 'coinstats', 'fetchai'})

# Per-exchange default test symbol when no active bot pair is available
_EXCHANGE_DEFAULT_SYMBOL: Dict[str, str] = {
    'luno': 'BTC/ZAR',
    'binance': 'BTC/USDT',
    'kucoin': 'BTC/USDT',
    'bybit': 'BTC/USDT',
    'kraken': 'BTC/USD',
    'bitget': 'BTC/USDT',
    'gate': 'BTC/USDT',
}

class ExchangeReadiness:
    """Per-exchange readiness check"""
    
    @staticmethod
    async def _get_test_symbol(user_id: str, exchange_name: str, markets: dict) -> str:
        """Pick the best test symbol for this exchange.
        
        Preference order:
        1. Pair from any active bot on this exchange for this user.
        2. Exchange-specific default (BTC/ZAR for luno, BTC/USDT elsewhere).
        3. First market found that contains BTC.
        Falls back to exchange default even when not in markets (caller handles warning).
        """
        # 1. Check active bot pairs
        try:
            bots = await db.bots_collection.find(
                {"user_id": user_id, "exchange": exchange_name, "status": "active"},
                {"_id": 0, "pair": 1}
            ).to_list(20)
            for bot in bots:
                pair = bot.get("pair")
                if pair and pair in markets:
                    return pair
        except Exception:
            pass

        # 2. Exchange-specific default
        default = _EXCHANGE_DEFAULT_SYMBOL.get(exchange_name.lower(), 'BTC/USDT')
        if default in markets:
            return default

        # 3. First BTC market
        for sym in markets:
            if sym.startswith('BTC/'):
                return sym

        return default

    @staticmethod
    async def check_exchange(user_id: str, exchange_name: str) -> Dict:
        """Check readiness for a specific exchange (CCXT-only).
        
        Returns:
            {
                "exchange": str,
                "ready": bool,
                "checks": {
                    "api_key": {"status": "ok|warning|error", "message": str},
                    "connection": {"status": "ok|error", "message": str},
                    "balance": {"status": "ok|warning", "message": str, "raw_totals": dict},
                    "symbol": {"status": "ok|warning", "message": str, "tradable": bool},
                    "min_notional": {"status": "ok", "message": str}
                },
                "errors": List[str],
                "warnings": List[str]
            }
        """
        result = {
            "exchange": exchange_name,
            "ready": False,
            "checks": {},
            "errors": [],
            "warnings": []
        }

        # Guard: never attempt CCXT for AI/non-exchange providers
        if exchange_name.lower() in NON_EXCHANGE_PROVIDERS:
            result["errors"].append(f"{exchange_name} is not a CCXT exchange")
            return result
        
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
            exchange_obj = ccxt_service.init_exchange(
                exchange_name,
                decrypted['api_key'],
                decrypted.get('api_secret', ''),
                testnet=False,
                passphrase=decrypted.get('passphrase')
            )
            
            # Try to fetch balance to test connection
            import asyncio
            balance = await asyncio.to_thread(exchange_obj.fetch_balance)
            
            result["checks"]["connection"] = {
                "status": "ok",
                "message": "Connection successful"
            }
            
            # Check 3: Balance - report raw per-currency totals (no fake USD 1:1 sum)
            raw_totals: Dict[str, float] = {}
            for currency, data in balance.items():
                if isinstance(data, dict) and 'total' in data:
                    total = data.get('total', 0) or 0
                    if total > 0:
                        raw_totals[currency] = total

            has_balance = bool(raw_totals)
            result["checks"]["balance"] = {
                "status": "ok" if has_balance else "warning",
                "message": f"Balances: {raw_totals}" if has_balance else "Zero balance detected",
                "raw_totals": raw_totals,
                "balance_usd": "unknown"  # Real conversion requires price feed
            }
            if not has_balance:
                result["warnings"].append("Zero balance on exchange")
            
            # Check 4: Symbol tradable – use per-exchange / per-bot pair
            try:
                markets = await asyncio.to_thread(exchange_obj.load_markets)
                test_symbol = await ExchangeReadiness._get_test_symbol(
                    user_id, exchange_name, markets
                )
                if test_symbol in markets:
                    market = markets[test_symbol]
                    result["checks"]["symbol"] = {
                        "status": "ok",
                        "message": f"{test_symbol} is tradable",
                        "symbol": test_symbol,
                        "tradable": True,
                        "min_amount": market.get("limits", {}).get("amount", {}).get("min"),
                        "min_cost": market.get("limits", {}).get("cost", {}).get("min")
                    }
                else:
                    result["checks"]["symbol"] = {
                        "status": "warning",
                        "message": f"Test symbol {test_symbol} not found in markets",
                        "symbol": test_symbol,
                        "tradable": False
                    }
                    result["warnings"].append(f"Test symbol {test_symbol} not in markets")
            except Exception as e:
                result["checks"]["symbol"] = {
                    "status": "warning",
                    "message": f"Failed to load markets: {str(e)}"
                }
                result["warnings"].append(f"Market data warning: {str(e)}")
            
            # Check 5: Min notional/cost requirements
            try:
                sym_check = result["checks"].get("symbol", {})
                if sym_check.get("tradable"):
                    min_cost = sym_check.get("min_cost", 0) or 0
                    if min_cost > 0:
                        result["checks"]["min_notional"] = {
                            "status": "ok",
                            "message": f"Min cost: {min_cost}",
                            "min_cost": min_cost
                        }
                    else:
                        result["checks"]["min_notional"] = {
                            "status": "ok",
                            "message": "No minimum cost requirement"
                        }
            except Exception as e:
                logger.warning(f"Min notional check failed: {e}")
            
            # Overall readiness: only hard errors block readiness (warnings do not)
            if len(result["errors"]) == 0:
                result["ready"] = True
            
        except Exception as e:
            result["checks"]["connection"] = {
                "status": "error",
                "message": f"Connection failed: {str(e)}"
            }
            result["errors"].append(f"Connection error: {str(e)}")
        
        return result


async def _get_provider_status(user_id: str, provider_name: str) -> Dict:
    """Return status dict for a non-exchange AI provider based on stored key metadata."""
    try:
        key_doc = await db.api_keys_collection.find_one(
            {"user_id": user_id,
             "$or": [{"provider": provider_name}, {"exchange": provider_name}]},
            {"_id": 0, "last_test_ok": 1, "last_tested_at": 1, "last_test_error": 1, "status": 1}
        )
        if not key_doc:
            return {"provider": provider_name, "configured": False, "status": "not_configured"}

        last_test_ok = key_doc.get("last_test_ok")
        if last_test_ok is True:
            status = "ok"
        elif last_test_ok is False:
            status = "error"
        else:
            status = "configured_untested"

        return {
            "provider": provider_name,
            "configured": True,
            "status": status,
            "last_test_ok": last_test_ok,
            "last_tested_at": key_doc.get("last_tested_at"),
            "last_test_error": key_doc.get("last_test_error") if last_test_ok is False else None,
        }
    except Exception as e:
        logger.warning(f"Provider status check failed for {provider_name}: {e}")
        return {"provider": provider_name, "configured": False, "status": "error", "error": str(e)}


@router.get("/readiness")
async def get_live_readiness(user_id: str = Depends(get_current_user)):
    """Get comprehensive live trading readiness status.
    
    Returns:
        {
            "ready": bool,
            "overall_errors": List[str],
            "exchanges": Dict[str, ReadinessCheck],   # real CCXT exchanges only
            "providers": Dict[str, ProviderStatus],   # AI providers only
            "timestamp": str
        }
    """
    try:
        # Get overall readiness from existing check
        overall_ready, overall_errors = await check_live_readiness(user_id)
        
        # Get all API key docs for this user
        api_keys = await db.api_keys_collection.find(
            {"user_id": user_id},
            {"_id": 0, "exchange": 1, "provider": 1}
        ).to_list(100)

        # Partition into real exchanges vs AI providers
        supported_exchange_set = set(SUPPORTED_PLATFORMS)
        exchange_names_seen: set = set()
        provider_names_seen: set = set()

        for key_doc in api_keys:
            name = (key_doc.get('exchange') or key_doc.get('provider') or '').lower()
            if not name:
                continue
            if name in NON_EXCHANGE_PROVIDERS:
                provider_names_seen.add(name)
            elif name in supported_exchange_set:
                exchange_names_seen.add(name)
            # Unknown names are silently ignored

        # Build exchange readiness (CCXT only)
        exchanges: Dict = {}
        for exchange_name in exchange_names_seen:
            readiness = await ExchangeReadiness.check_exchange(user_id, exchange_name)
            exchanges[exchange_name] = readiness

        # Build AI provider status (no CCXT, key presence + last_test_ok)
        all_ai_providers = list(NON_EXCHANGE_PROVIDERS)
        # Always include all known AI providers in response (even if not configured)
        for pname in all_ai_providers:
            if pname not in provider_names_seen:
                provider_names_seen.add(pname)
        providers: Dict = {}
        for pname in all_ai_providers:
            providers[pname] = await _get_provider_status(user_id, pname)

        return {
            "success": True,
            "ready": overall_ready,
            "overall_errors": overall_errors,
            "exchanges": exchanges,
            "exchange_count": len(exchanges),
            "ready_exchanges": sum(1 for e in exchanges.values() if e.get("ready")),
            "providers": providers,
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
