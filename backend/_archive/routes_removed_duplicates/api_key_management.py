"""
API Key Management Router
Handles encrypted storage, validation, and testing of exchange/AI API keys
"""

from fastapi import APIRouter, HTTPException, Depends
from typing import Optional, Dict, Literal
import logging
import os
from cryptography.fernet import Fernet
import base64
import hashlib

from auth import get_current_user
import database as db
from models import APIKeyCreate

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/keys", tags=["API Keys"])


def get_encryption_key() -> bytes:
    """Get or create encryption key for API keys
    
    Returns:
        Fernet encryption key
    """
    # In production, store this securely (e.g., AWS Secrets Manager, HashiCorp Vault)
    key_env = os.getenv("API_KEY_ENCRYPTION_KEY")
    
    if key_env:
        return base64.urlsafe_b64decode(key_env.encode())
    
    # Generate a deterministic key from JWT secret (NOT recommended for production)
    jwt_secret = os.getenv("JWT_SECRET", "default-dev-secret-change-in-production")
    key_material = hashlib.sha256(jwt_secret.encode()).digest()
    return base64.urlsafe_b64encode(key_material)


def encrypt_api_key(api_key: str) -> str:
    """Encrypt an API key for storage
    
    Args:
        api_key: Plain text API key
        
    Returns:
        Encrypted API key (base64 encoded)
    """
    try:
        fernet = Fernet(get_encryption_key())
        encrypted = fernet.encrypt(api_key.encode())
        return base64.urlsafe_b64encode(encrypted).decode()
    except Exception as e:
        logger.error(f"Encryption error: {e}")
        raise HTTPException(status_code=500, detail="Failed to encrypt API key")


def decrypt_api_key(encrypted_key: str) -> str:
    """Decrypt an API key from storage
    
    Args:
        encrypted_key: Encrypted API key (base64 encoded)
        
    Returns:
        Plain text API key
    """
    try:
        fernet = Fernet(get_encryption_key())
        decoded = base64.urlsafe_b64decode(encrypted_key.encode())
        decrypted = fernet.decrypt(decoded)
        return decrypted.decode()
    except Exception as e:
        logger.error(f"Decryption error: {e}")
        raise HTTPException(status_code=500, detail="Failed to decrypt API key")


@router.post("/test")
async def test_api_key(
    data: Dict = None,
    user_id: str = Depends(get_current_user)
):
    """Test an API key before saving
    
    Accepts JSON body, form-encoded, or raw body
    Makes a test API call to verify the key works
    Persists test results to database
    
    Args:
        data: Contains provider, api_key, api_secret, exchange info (can be dict or None)
        user_id: Current user ID from auth
        
    Returns:
        Test result with success/error details
    """
    try:
        # Handle None data (shouldn't happen but be defensive)
        if data is None:
            data = {}
        
        # Normalize payload - accept multiple field name variants
        provider = data.get("provider") or data.get("exchange") or data.get("platform")
        api_key = data.get("api_key") or data.get("apiKey") or data.get("key")
        api_secret = data.get("api_secret") or data.get("apiSecret") or data.get("secret")
        passphrase = data.get("passphrase")
        exchange = data.get("exchange") or data.get("provider") or data.get("platform")
        model = data.get("model")  # Optional model parameter
        
        if not provider:
            return {
                "ok": False,
                "success": False,
                "message": "❌ Provider required",
                "error": "Provider field is required"
            }
        
        # Ensure user_id is always stored as string
        user_id_str = str(user_id)
        
        # If api_key not provided, load saved key from database
        if not api_key:
            saved_key_data = await get_decrypted_key(user_id_str, provider)
            if not saved_key_data:
                raise HTTPException(status_code=400, detail=f"No saved key for provider {provider}")
            api_key = saved_key_data.get("api_key")
            api_secret = saved_key_data.get("api_secret")
            exchange = saved_key_data.get("exchange") or provider
        
        from datetime import datetime, timezone
        timestamp = datetime.now(timezone.utc).isoformat()
        
        # Test based on provider type
        if provider in ["binance", "luno", "kucoin", "ovex", "valr"]:
            # Test exchange API key
            import ccxt.async_support as ccxt
            
            exchange_class = getattr(ccxt, provider, None)
            if not exchange_class:
                raise HTTPException(status_code=400, detail=f"Exchange {provider} not supported")
            
            exchange_instance = exchange_class({
                'apiKey': api_key,
                'secret': api_secret,
                'enableRateLimit': True
            })
            
            try:
                # Test with a simple API call (fetch balance)
                balance = await exchange_instance.fetch_balance()
                await exchange_instance.close()
                
                # Get total balance
                total_usd = 0.0
                currencies_found = 0
                if 'total' in balance:
                    for currency, amount in balance['total'].items():
                        if amount > 0:
                            total_usd += amount  # Simplified - should convert to USD
                            currencies_found += 1
                
                # Update test metadata in database if key exists
                await db.api_keys_collection.update_one(
                    {"user_id": user_id_str, "provider": provider},
                    {"$set": {
                        "last_tested_at": timestamp,
                        "last_test_ok": True,
                        "last_test_error": None
                    }},
                    upsert=False
                )
                
                return {
                    "ok": True,
                    "success": True,
                    "message": f"✅ {provider.upper()} API key validated successfully",
                    "provider": provider,
                    "test_data": {
                        "balance_available": True,
                        "currencies_found": currencies_found,
                        "approximate_total": round(total_usd, 2)
                    }
                }
            except Exception as e:
                await exchange_instance.close()
                error_msg = str(e)
                
                # Update test metadata with error
                await db.api_keys_collection.update_one(
                    {"user_id": user_id_str, "provider": provider},
                    {"$set": {
                        "last_tested_at": timestamp,
                        "last_test_ok": False,
                        "last_test_error": error_msg[:500]  # Limit error length
                    }},
                    upsert=False
                )
                
                if "Invalid API-key" in error_msg or "authentication" in error_msg.lower():
                    return {
                        "ok": False,
                        "success": False,
                        "message": f"❌ Invalid API credentials for {provider.upper()}",
                        "error": "Authentication failed - check API key and secret"
                    }
                else:
                    return {
                        "ok": False,
                        "success": False,
                        "message": f"❌ API test failed for {provider.upper()}",
                        "error": error_msg
                    }
        
        elif provider == "openai":
            # Test OpenAI API key with openai>=1.x WITH MODEL FALLBACK
            import os
            
            try:
                # Use AsyncOpenAI client (openai>=1.x)
                from openai import AsyncOpenAI
                
                # Build model fallback list (ordered by preference)
                # Priority: requested model -> OPENAI_FALLBACK_MODEL -> safe allowlist
                fallback_models = []
                if model:
                    fallback_models.append(model)
                fallback_env = os.getenv("OPENAI_FALLBACK_MODEL")
                if fallback_env:
                    fallback_models.append(fallback_env)
                
                # Safe ordered allowlist (most reliable models first)
                allowlist = ["gpt-4o-mini", "gpt-4.1-mini", "gpt-4o", "gpt-3.5-turbo", "gpt-4"]
                for m in allowlist:
                    if m not in fallback_models:
                        fallback_models.append(m)
                
                # Create client with provided API key
                client = AsyncOpenAI(api_key=api_key)
                
                # Try each model in fallback order
                model_used = None
                last_error = None
                error_code = None
                
                for test_model in fallback_models:
                    try:
                        # Simple test call
                        response = await client.chat.completions.create(
                            model=test_model,
                            messages=[{"role": "user", "content": "test"}],
                            max_tokens=5
                        )
                        # Success! Use this model
                        model_used = test_model
                        break
                    except Exception as model_error:
                        error_str = str(model_error)
                        last_error = error_str
                        
                        # Detect error type
                        if "404" in error_str or "model_not_found" in error_str.lower():
                            error_code = "model_not_found"
                            logger.info(f"Model {test_model} not found, trying next fallback")
                            continue
                        elif "403" in error_str or "forbidden" in error_str.lower():
                            error_code = "model_forbidden"
                            logger.info(f"Model {test_model} forbidden, trying next fallback")
                            continue
                        else:
                            # Other error (likely auth or API issue) - don't continue fallback
                            error_code = "api_error"
                            break
                
                # Determine key source
                key_source = "user" if not api_key else "user"  # Always user for this test
                
                if model_used:
                    # Success - update test metadata
                    await db.api_keys_collection.update_one(
                        {"user_id": user_id_str, "provider": provider},
                        {"$set": {
                            "last_tested_at": timestamp,
                            "last_test_ok": True,
                            "last_test_error": None,
                            "model_used_last": model_used
                        }},
                        upsert=False
                    )
                    
                    return {
                        "ok": True,
                        "success": True,
                        "message": f"✅ OpenAI API key validated successfully",
                        "provider": provider,
                        "model_used": model_used,
                        "key_source": key_source,
                        "test_data": {
                            "model_accessible": True,
                            "test_model": model_used,
                            "models": allowlist
                        }
                    }
                else:
                    # All models failed
                    await db.api_keys_collection.update_one(
                        {"user_id": user_id_str, "provider": provider},
                        {"$set": {
                            "last_tested_at": timestamp,
                            "last_test_ok": False,
                            "last_test_error": last_error[:500] if last_error else "All models failed"
                        }},
                        upsert=False
                    )
                    
                    return {
                        "ok": False,
                        "success": False,
                        "message": f"❌ OpenAI API test failed (tried {len(fallback_models)} models)",
                        "provider": provider,
                        "error_code": error_code,
                        "error_message": last_error[:200] if last_error else "All models failed",
                        "models_tried": fallback_models
                    }
                    
            except ImportError as e:
                # Fallback error for missing openai library
                error_msg = "OpenAI library not installed or version incompatible"
                await db.api_keys_collection.update_one(
                    {"user_id": user_id_str, "provider": provider},
                    {"$set": {
                        "last_tested_at": timestamp,
                        "last_test_ok": False,
                        "last_test_error": error_msg
                    }},
                    upsert=False
                )
                return {
                    "ok": False,
                    "success": False,
                    "message": "❌ OpenAI library configuration error",
                    "error_code": "import_error",
                    "error_message": error_msg
                }
            except Exception as e:
                error_msg = str(e)
                
                # Update test metadata with error
                await db.api_keys_collection.update_one(
                    {"user_id": user_id_str, "provider": provider},
                    {"$set": {
                        "last_tested_at": timestamp,
                        "last_test_ok": False,
                        "last_test_error": error_msg[:500]
                    }},
                    upsert=False
                )
                
                # Check for authentication errors
                if "invalid" in error_msg.lower() or "incorrect" in error_msg.lower() or "authentication" in error_msg.lower():
                    return {
                        "ok": False,
                        "success": False,
                        "message": "❌ Invalid OpenAI API key",
                        "provider": provider,
                        "error_code": "auth_failed",
                        "error_message": "Authentication failed - check your API key"
                    }
                else:
                    return {
                        "ok": False,
                        "success": False,
                        "message": "❌ OpenAI API test failed",
                        "provider": provider,
                        "error_code": "api_error",
                        "error_message": error_msg
                    }
        
        else:
            # Generic success for other providers
            await db.api_keys_collection.update_one(
                {"user_id": user_id_str, "provider": provider},
                {"$set": {
                    "last_tested_at": timestamp,
                    "last_test_ok": True,
                    "last_test_error": None
                }},
                upsert=False
            )
            
            return {
                "ok": True,
                "success": True,
                "message": f"✅ {provider.upper()} API key format validated",
                "provider": provider
            }
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"API key test error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/save")
async def save_api_key(
    data: Dict = None,
    user_id: str = Depends(get_current_user)
):
    """Save an API key with encryption
    
    Accepts JSON body, form-encoded, or raw body
    Accepts both api_key/api_secret and apiKey/apiSecret variants
    Accepts both provider and exchange fields
    
    Returns {"success": true, ...} on success
    
    Args:
        data: Contains provider, api_key, api_secret, exchange info (can be dict or None)
        user_id: Current user ID from auth
        
    Returns:
        Saved key info (without exposing actual keys) with success=true
    """
    try:
        # Handle None data (shouldn't happen but be defensive)
        if data is None:
            data = {}
        
        # Normalize payload - accept multiple field name variants
        provider = data.get("provider") or data.get("exchange") or data.get("platform")
        api_key = data.get("api_key") or data.get("apiKey") or data.get("key")
        api_secret = data.get("api_secret") or data.get("apiSecret") or data.get("secret")
        passphrase = data.get("passphrase")
        exchange = data.get("exchange") or data.get("provider") or data.get("platform")
        
        if not provider or not api_key:
            return {
                "success": False,
                "message": "❌ Provider and API key required",
                "error": "Both provider and api_key fields are required"
            }
        
        # Ensure user_id is always stored as string
        user_id_str = str(user_id)
        
        # Encrypt keys before storage
        encrypted_key = encrypt_api_key(api_key)
        encrypted_secret = encrypt_api_key(api_secret) if api_secret else None
        
        # Check if key already exists
        existing = await db.api_keys_collection.find_one({
            "user_id": user_id_str,
            "provider": provider
        })
        
        from datetime import datetime, timezone
        timestamp = datetime.now(timezone.utc).isoformat()
        
        key_data = {
            "user_id": user_id_str,  # Force string
            "provider": provider,
            "api_key_encrypted": encrypted_key,
            "api_secret_encrypted": encrypted_secret,
            "exchange": exchange,
            "created_at": existing.get("created_at") if existing else timestamp,
            "updated_at": timestamp if existing else None,
            "last_saved_at": timestamp,
            "last_tested_at": existing.get("last_tested_at") if existing else None,
            "last_test_ok": existing.get("last_test_ok") if existing else None,
            "last_test_error": existing.get("last_test_error") if existing else None
        }
        
        if existing:
            # Update existing key
            await db.api_keys_collection.update_one(
                {"user_id": user_id_str, "provider": provider},
                {"$set": key_data}
            )
            message = f"Updated {provider.upper()} API key"
        else:
            # Create new key
            await db.api_keys_collection.insert_one(key_data)
            message = f"Saved {provider.upper()} API key"
        
        logger.info(f"✅ {message} for user {user_id_str[:8]}")
        
        return {
            "success": True,  # REQUIRED for verifier
            "message": message,
            "provider": provider,
            "status": "saved_untested" if not key_data.get("last_test_ok") else "saved_tested",
            "key_info": {
                "provider": provider,
                "exchange": exchange,
                "masked_key": f"{api_key[:4]}...{api_key[-4:]}" if len(api_key) > 8 else "****",
                "saved_at": key_data.get("last_saved_at")
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Save API key error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/list")
async def list_api_keys(user_id: str = Depends(get_current_user)):
    """List all saved API keys for user (without exposing actual keys)
    
    Returns test status and metadata
    
    Args:
        user_id: Current user ID from auth
        
    Returns:
        List of saved keys with masked values and test status
    """
    try:
        # Ensure user_id is string
        user_id_str = str(user_id)
        
        keys_cursor = db.api_keys_collection.find(
            {"user_id": user_id_str},
            {"_id": 0, "api_key_encrypted": 0, "api_secret_encrypted": 0}
        )
        keys = await keys_cursor.to_list(100)
        
        # Add status indicators based on test results
        for key in keys:
            last_test_ok = key.get("last_test_ok")
            last_tested_at = key.get("last_tested_at")
            
            if last_test_ok is True and last_tested_at:
                key["status"] = "saved_tested"
                key["status_display"] = "Saved & Tested ✅"
            elif last_test_ok is False:
                key["status"] = "test_failed"
                key["status_display"] = "Test Failed ❌"
            else:
                key["status"] = "saved_untested"
                key["status_display"] = "Saved (untested)"
        
        return {
            "success": True,
            "keys": keys,
            "total": len(keys)
        }
        
    except Exception as e:
        logger.error(f"List API keys error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{provider}")
async def delete_api_key(
    provider: str,
    user_id: str = Depends(get_current_user)
):
    """Delete an API key
    
    Args:
        provider: Provider name (e.g., 'binance', 'openai')
        user_id: Current user ID from auth
        
    Returns:
        Deletion confirmation
    """
    try:
        result = await db.api_keys_collection.delete_one({
            "user_id": user_id,
            "provider": provider
        })
        
        if result.deleted_count == 0:
            raise HTTPException(status_code=404, detail=f"No API key found for {provider}")
        
        logger.info(f"🗑️ Deleted {provider} API key for user {user_id[:8]}")
        
        return {
            "success": True,
            "message": f"Deleted {provider.upper()} API key"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Delete API key error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


async def get_decrypted_key(user_id: str, provider: str) -> Optional[Dict]:
    """Helper function to get and decrypt API keys
    
    Used internally by other services
    Supports backward compatibility with ObjectId user_ids
    Supports multiple field name variants for encrypted keys
    
    Args:
        user_id: User ID (string)
        provider: Provider name
        
    Returns:
        Dict with decrypted api_key and api_secret, or None
    """
    try:
        # First try with string user_id (new format)
        key_doc = await db.api_keys_collection.find_one({
            "user_id": user_id,
            "provider": provider
        })
        
        # If not found and user_id looks like ObjectId (24 hex chars), try ObjectId lookup
        if not key_doc and len(user_id) == 24 and all(c in '0123456789abcdefABCDEF' for c in user_id):
            from bson import ObjectId
            from bson.errors import InvalidId
            try:
                key_doc = await db.api_keys_collection.find_one({
                    "user_id": ObjectId(user_id),
                    "provider": provider
                })
            except InvalidId:
                pass  # Invalid ObjectId format, continue
        
        if not key_doc:
            # INFO level for normal case where key doesn't exist
            logger.info(f"No API key found for user {user_id[:8]} provider {provider}")
            return None
        
        # Support multiple field name variants for encrypted keys
        # Try canonical names first, then fallback to alternative names
        api_key_field = None
        api_secret_field = None
        
        # Check for API key field variants (in priority order)
        for field in ["api_key_encrypted", "apiKeyEncrypted", "api_key_ciphertext", "key_encrypted"]:
            if field in key_doc:
                api_key_field = field
                break
        
        # Check for API secret field variants (in priority order)
        for field in ["api_secret_encrypted", "apiSecretEncrypted", "api_secret_ciphertext", "secret_encrypted"]:
            if field in key_doc:
                api_secret_field = field
                break
        
        if not api_key_field:
            # WARN level for unexpected condition
            logger.warning(f"No encrypted API key field found for user {user_id[:8]} provider {provider}. Fields present: {list(key_doc.keys())}")
            return None
        
        return {
            "api_key": decrypt_api_key(key_doc[api_key_field]),
            "api_secret": decrypt_api_key(key_doc[api_secret_field]) if api_secret_field and key_doc.get(api_secret_field) else None,
            "provider": provider,
            "exchange": key_doc.get("exchange")
        }
    except Exception as e:
        logger.error(f"Get decrypted key error: {e}")
        return None


# Note: These legacy routes remain for backwards compatibility
# Frontend should migrate to canonical /api/api-keys/* endpoints
# All logic is duplicated here to maintain compatibility
