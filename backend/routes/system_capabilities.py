"""
System Capabilities Endpoint

Provides a unified view of system capabilities, configuration status,
and missing dependencies without exposing secrets.
"""

from fastapi import APIRouter, Depends
from datetime import datetime, timezone
import logging
import os

from auth import get_current_user
import database as db

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/system", tags=["System"])


@router.get("/capabilities")
async def get_system_capabilities(user_id: str = Depends(get_current_user)):
    """
    Get system capabilities and configuration status.
    
    Returns:
        - Feature flags (enable/disable settings)
        - Configuration status (configured/not_configured)
        - Missing dependencies (which keys are needed)
        - Runtime state (active/inactive)
        
    Does NOT expose actual API keys or secrets.
    """
    try:
        # Get system modes and flags
        modes_doc = await db.system_modes_collection.find_one({}, {"_id": 0})
        
        # Get user's API keys status (without exposing values)
        user_keys = await db.api_keys_collection.find_one(
            {"user_id": user_id},
            {"_id": 0, "user_id": 1}
        )
        
        # Check which keys are configured
        has_openai = bool(os.getenv("OPENAI_API_KEY"))
        has_huggingface = bool(os.getenv("HUGGINGFACE_API_KEY"))
        has_fetchai = bool(os.getenv("FETCHAI_API_KEY"))
        
        # Check exchange keys from user's key collection
        exchange_keys = {}
        if user_keys:
            # Get all fields except _id and user_id
            for key in ["luno_key", "luno_secret", "binance_key", "binance_secret", 
                       "kucoin_key", "kucoin_secret", "bybit_key", "bybit_secret",
                       "kraken_key", "kraken_secret", "bitget_key", "bitget_secret",
                       "gate_key", "gate_secret"]:
                # Reconstruct key data from database
                try:
                    key_doc = await db.api_keys_collection.find_one(
                        {"user_id": user_id},
                        {"_id": 0, key: 1}
                    )
                    exchange_keys[key] = bool(key_doc and key_doc.get(key))
                except Exception:
                    exchange_keys[key] = False
        
        # Determine exchange configuration status
        exchanges = {
            "luno": exchange_keys.get("luno_key", False) and exchange_keys.get("luno_secret", False),
            "binance": exchange_keys.get("binance_key", False) and exchange_keys.get("binance_secret", False),
            "kucoin": exchange_keys.get("kucoin_key", False) and exchange_keys.get("kucoin_secret", False),
            "bybit": exchange_keys.get("bybit_key", False) and exchange_keys.get("bybit_secret", False),
            "kraken": exchange_keys.get("kraken_key", False) and exchange_keys.get("kraken_secret", False),
            "bitget": exchange_keys.get("bitget_key", False) and exchange_keys.get("bitget_secret", False),
            "gate": exchange_keys.get("gate_key", False) and exchange_keys.get("gate_secret", False),
        }
        
        # Build capabilities response
        capabilities = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "user_id": user_id,
            
            # Feature flags (what's enabled in config)
            "feature_flags": {
                "enable_autopilot": modes_doc.get("enable_autopilot", False) if modes_doc else False,
                "enable_self_learning": modes_doc.get("enable_self_learning", True) if modes_doc else True,
                "enable_self_healing": modes_doc.get("enable_self_healing", True) if modes_doc else True,
                "enable_scheduler": modes_doc.get("enable_scheduler", True) if modes_doc else True,
            },
            
            # Trading mode flags (configured vs runtime)
            "trading_mode_flags": {
                "paper_trading_enabled": modes_doc.get("paper_trading", True) if modes_doc else True,
                "live_trading_enabled": modes_doc.get("live_trading", False) if modes_doc else False,
            },
            
            # Runtime state (what's currently active)
            "runtime_state": {
                "paper_trading_active": modes_doc.get("paper_trading", True) if modes_doc else True,
                "live_trading_active": modes_doc.get("live_trading", False) if modes_doc else False,
                "autopilot_active": modes_doc.get("autonomous", False) if modes_doc else False,
            },
            
            # AI/ML providers
            "ai_providers": {
                "openai": {
                    "configured": has_openai,
                    "required_for": ["AI chat", "Insights", "Predictions"],
                    "status": "configured" if has_openai else "not_configured"
                },
                "huggingface": {
                    "configured": has_huggingface,
                    "required_for": ["Sentiment analysis", "ML models"],
                    "status": "configured" if has_huggingface else "not_configured"
                },
                "fetchai": {
                    "configured": has_fetchai,
                    "required_for": ["Market signals", "Agent automation"],
                    "status": "configured" if has_fetchai else "not_configured"
                }
            },
            
            # Exchange configuration
            "exchanges": {
                exchange: {
                    "configured": is_configured,
                    "status": "configured" if is_configured else "not_configured",
                    "required_for": "live_trading" if exchange != "luno" else "wallet_balances"
                }
                for exchange, is_configured in exchanges.items()
            },
            
            # Missing dependencies summary
            "missing_dependencies": {
                "ai_providers": [
                    provider for provider, data in {
                        "OpenAI": has_openai,
                        "HuggingFace": has_huggingface,
                        "Fetch.ai": has_fetchai
                    }.items() if not data
                ],
                "exchanges": [
                    exchange.upper() for exchange, configured in exchanges.items() 
                    if not configured
                ],
                "count": {
                    "ai_providers": len([p for p in [has_openai, has_huggingface, has_fetchai] if not p]),
                    "exchanges": len([e for e in exchanges.values() if not e])
                }
            }
        }
        
        return capabilities
        
    except Exception as e:
        logger.error(f"Error getting system capabilities: {e}")
        # Return safe defaults on error
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "user_id": user_id,
            "error": "Failed to load capabilities",
            "feature_flags": {
                "enable_autopilot": False,
                "enable_self_learning": True,
                "enable_self_healing": True,
                "enable_scheduler": True,
            },
            "trading_mode_flags": {
                "paper_trading_enabled": True,
                "live_trading_enabled": False,
            },
            "runtime_state": {
                "paper_trading_active": True,
                "live_trading_active": False,
                "autopilot_active": False,
            },
            "ai_providers": {},
            "exchanges": {},
            "missing_dependencies": {
                "ai_providers": [],
                "exchanges": [],
                "count": {"ai_providers": 0, "exchanges": 0}
            }
        }
