"""
Canonical API Keys Management
Consolidates all API key operations into one place with encryption at rest
Legacy routes alias to these handlers
"""

from fastapi import APIRouter, HTTPException, Depends
from typing import Optional, Dict, List
from pydantic import BaseModel, Field
import logging
from datetime import datetime, timezone

from auth import get_current_user, is_admin
from routes.api_key_management import (
    encrypt_api_key, 
    decrypt_api_key,
    get_decrypted_key
)
import database as db

logger = logging.getLogger(__name__)

# Canonical router with /api/api-keys prefix
router = APIRouter(prefix="/api/api-keys", tags=["API Keys (Canonical)"])


class APIKeyTestRequest(BaseModel):
    provider: str = Field(..., description="Exchange or service provider")
    api_key: str = Field(..., description="API key to test")
    api_secret: Optional[str] = Field(None, description="API secret (for exchanges)")


class APIKeySaveRequest(BaseModel):
    provider: Optional[str] = Field(None, description="Exchange or service provider")
    api_key: Optional[str] = Field(None, description="API key")
    api_secret: Optional[str] = Field(None, description="API secret (for exchanges)")
    exchange: Optional[str] = Field(None, description="Exchange name (legacy)")
    # Legacy camelCase support
    apiKey: Optional[str] = Field(None, description="API key (camelCase legacy)")
    apiSecret: Optional[str] = Field(None, description="API secret (camelCase legacy)")
    key: Optional[str] = Field(None, description="API key (short form legacy)")
    secret: Optional[str] = Field(None, description="API secret (short form legacy)")


@router.get("")
async def list_api_keys(user_id: str = Depends(get_current_user)):
    """
    List all API keys for the current user (masked, encrypted at rest)
    Never returns plaintext keys
    Returns test status and metadata
    """
    try:
        # Ensure user_id is string
        user_id_str = str(user_id)
        
        keys_cursor = db.api_keys_collection.find(
            {"user_id": user_id_str},
            {"_id": 0, "api_key_encrypted": 0, "api_secret_encrypted": 0}
        )
        keys = await keys_cursor.to_list(100)
        
        # Add status indicators
        for key in keys:
            # Mask any remaining sensitive data
            if 'api_key' in key:
                key['api_key_masked'] = f"{key['api_key'][:4]}..." if len(key.get('api_key', '')) > 4 else '***'
                del key['api_key']
            if 'secret' in key:
                key['secret'] = '***'
            
            # Add test status
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


@router.post("")
async def save_api_key(
    data: APIKeySaveRequest,
    user_id: str = Depends(get_current_user)
):
    """
    Save an API key with encryption at rest
    Keys are encrypted using Fernet symmetric encryption
    
    BACKWARD COMPATIBILITY: Accepts multiple field name variants:
    - provider OR exchange (exchange maps to provider)
    - api_key OR apiKey OR key
    - api_secret OR apiSecret OR secret
    """
    try:
        # Normalize from Pydantic model - support legacy field names
        # Provider: accept 'provider' or 'exchange' (legacy)
        provider = data.provider or data.exchange
        
        # API Key: accept 'api_key', 'apiKey' (camelCase), or 'key' (short form)
        api_key = data.api_key or data.apiKey or data.key
        
        # API Secret: accept 'api_secret', 'apiSecret', or 'secret'
        api_secret = data.api_secret or data.apiSecret or data.secret
        
        exchange = provider  # Normalize exchange to provider value
        
        if not provider or not api_key:
            raise HTTPException(status_code=400, detail="Provider and API key required")
        
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
            "success": True,
            "message": message,
            "provider": provider,
            "status": "saved_untested" if not key_data.get("last_test_ok") else "saved_tested",
            "masked_key": f"{api_key[:4]}...{api_key[-4:]}" if len(api_key) > 8 else "****",
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Save API key error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{provider}")
async def delete_api_key(
    provider: str,
    user_id: str = Depends(get_current_user)
):
    """Delete an API key for the current user
    
    Returns success even if key doesn't exist (idempotent)
    """
    try:
        result = await db.api_keys_collection.delete_one({
            "user_id": user_id,
            "provider": provider
        })
        
        if result.deleted_count == 0:
            logger.info(f"ℹ️ No {provider} API key found for user {user_id[:8]} (already deleted)")
            return {
                "success": True,
                "message": f"{provider.upper()} API key not found (already deleted)"
            }
        
        logger.info(f"🗑️ Deleted {provider} API key for user {user_id[:8]}")
        
        return {
            "success": True,
            "message": f"Deleted {provider.upper()} API key"
        }
        
    except Exception as e:
        logger.error(f"Delete API key error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{provider}/test")
async def test_api_key(
    provider: str,
    data: Dict,
    user_id: str = Depends(get_current_user)
):
    """
    Test an API key before saving
    Makes a lightweight API call to verify credentials
    Persists test results to database
    Uses model fallback chain for OpenAI testing
    
    Returns small, friendly error messages (never stack traces)
    """
    try:
        # Normalize payload - accept multiple field name variants
        api_key = data.get("api_key") or data.get("apiKey") or data.get("key")
        api_secret = data.get("api_secret") or data.get("apiSecret") or data.get("secret")
        passphrase = data.get("passphrase")
        
        if not api_key:
            return {
                "success": False,
                "ok": False,
                "error": "API key is required",
                "provider": provider
            }
        
        # Ensure user_id is string
        user_id_str = str(user_id)
        
        timestamp = datetime.now(timezone.utc).isoformat()
        
        # Use keys service for testing
        from services.keys_service import keys_service
        
        success, metadata, error = await keys_service.test_api_key(
            provider, api_key, api_secret, passphrase
        )
        
        # Update test metadata in database if key exists
        update_data = {
            "last_tested_at": timestamp,
            "last_test_ok": success,
            "last_test_error": error if not success else None
        }
        
        # Add metadata if available
        if metadata:
            update_data.update(metadata)
        
        await db.api_keys_collection.update_one(
            {"user_id": user_id_str, "provider": provider},
            {"$set": update_data},
            upsert=False  # Don't create if doesn't exist
        )
        
        if success:
            # Build success message
            message = f"✅ {provider.upper()} API key validated successfully"
            if provider == 'openai' and metadata and metadata.get('working_model'):
                message += f" (using model: {metadata['working_model']})"
            elif metadata and metadata.get('currencies_found'):
                message += f" ({metadata['currencies_found']} currencies found)"
            
            return {
                "success": True,
                "ok": True,
                "message": message,
                "provider": provider,
                "metadata": metadata or {}
            }
        else:
            # Return friendly error message (truncate if too long)
            error_msg = error or "Validation failed"
            if len(error_msg) > 200:
                error_msg = error_msg[:200] + "..."
            
            return {
                "success": False,
                "ok": False,
                "message": f"❌ API test failed for {provider.upper()}",
                "error": error_msg,
                "provider": provider
            }
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"API key test error: {e}", exc_info=True)
        # Return friendly error, never stack trace
        error_msg = str(e)
        if len(error_msg) > 200:
            error_msg = error_msg[:200] + "..."
        
        return {
            "success": False,
            "ok": False,
            "error": error_msg or "Test failed due to internal error",
            "provider": provider
        }
