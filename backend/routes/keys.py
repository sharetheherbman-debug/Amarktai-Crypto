"""
Canonical API Keys Router - Unified key management with provider registry
Handles all 11 providers: openai, flokx, fetchai, huggingface, luno, binance, kucoin, bybit, kraken, bitget, gate
"""

from fastapi import APIRouter, HTTPException, Depends
from typing import Optional, Dict, List
from pydantic import BaseModel, Field
import logging
from datetime import datetime, timezone
from uuid import uuid4

from auth import get_current_user, is_admin
from routes.api_key_management import encrypt_api_key, decrypt_api_key
from services.provider_registry import (
    list_providers,
    list_providers_ids,
    get_provider,
    test_provider,
    ProviderStatus
)
import database as db
from realtime_events import rt_events

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/keys", tags=["API Keys"])


def normalize_status(status: str) -> str:
    """Normalize legacy status values to canonical ones
    
    Accepts legacy values (saved_untested, test_ok, test_failed) and
    normalizes them to canonical values (configured_untested, configured_valid, configured_invalid)
    for consistent API responses.
    """
    # Map legacy statuses to canonical ones
    legacy_mapping = {
        "saved_untested": ProviderStatus.CONFIGURED_UNTESTED.value,
        "test_ok": ProviderStatus.CONFIGURED_VALID.value,
        "test_failed": ProviderStatus.CONFIGURED_INVALID.value,
    }
    
    # Return normalized status or original if already canonical
    return legacy_mapping.get(status, status)


def get_status_display(status: str) -> str:
    """Get human-readable display text for canonical status"""
    status_displays = {
        ProviderStatus.NOT_CONFIGURED.value: "Not configured",
        ProviderStatus.CONFIGURED_UNTESTED.value: "Configured (untested)",
        ProviderStatus.CONFIGURED_VALID.value: "Valid ✅",
        ProviderStatus.CONFIGURED_INVALID.value: "Invalid ❌",
        ProviderStatus.CONFIGURED_RATE_LIMITED.value: "Rate limited ⏱️",
    }
    
    return status_displays.get(status, status)


class APIKeySaveRequest(BaseModel):
    """Request to save API key - strict schema, no additional properties"""
    model_config = {"extra": "forbid"}  # Strict: no additional properties allowed
    
    provider: str = Field(..., description="Provider ID (e.g., 'openai', 'binance')")
    api_key: str = Field(..., description="API key")
    api_secret: Optional[str] = Field(None, description="API secret (required for exchanges)")
    passphrase: Optional[str] = Field(None, description="Passphrase (required for KuCoin)")
    name: Optional[str] = Field(None, description="Optional friendly name for this key")


class APIKeyTestRequest(BaseModel):
    """Request to test API key - strict schema"""
    model_config = {"extra": "forbid"}  # Strict: no additional properties allowed
    
    provider: str = Field(..., description="Provider ID")
    api_key: Optional[str] = Field(None, description="API key to test (if not saved)")
    api_secret: Optional[str] = Field(None, description="API secret (if not saved)")
    passphrase: Optional[str] = Field(None, description="Passphrase (if not saved)")


@router.get("/providers")
async def get_providers_list():
    """Get list of all supported providers with metadata
    
    Returns provider definitions including:
    - id, type, display_name
    - required_fields
    - icon, description
    
    This endpoint is public (no auth) so frontend can render the providers list
    """
    try:
        providers = list_providers()
        
        return {
            "success": True,
            "providers": providers,
            "total": len(providers)
        }
    except Exception as e:
        logger.error(f"Get providers error: {e}")
        raise HTTPException(status_code=500, detail=str(e))




@router.get("/status")
async def get_keys_status(user_id: str = Depends(get_current_user)):
    """
    Get status of all API keys for current user
    
    Returns status per provider:
    - not_configured: No key exists
    - configured_untested: Key saved but not tested
    - configured_valid: Key tested successfully
    - configured_invalid: Key test failed
    - configured_rate_limited: Key hit rate limit (optional)
    
    This is a simplified, focused endpoint specifically for status checks
    """
    try:
        # Get all providers
        all_providers = list_providers()
        # Fix: list_providers() returns List[Dict], not objects. Use dict key access.
        provider_ids = [p['id'] for p in all_providers]
        
        # Get saved keys for user
        keys_cursor = db.api_keys_collection.find(
            {"user_id": str(user_id)},
            {"_id": 0, "provider": 1, "status": 1, "last_tested_at": 1, "last_test_error": 1, "updated_at": 1}
        )
        saved_keys = await keys_cursor.to_list(100)
        
        # Build status map
        status_map = {}
        
        for provider_id in provider_ids:
            # Find key for this provider
            key = next((k for k in saved_keys if k['provider'] == provider_id), None)
            
            if key:
                # Normalize legacy status to canonical
                raw_status = key.get("status", ProviderStatus.CONFIGURED_UNTESTED.value)
                canonical_status = normalize_status(raw_status)
                
                status_map[provider_id] = {
                    "status": canonical_status,
                    "last_tested_at": key.get("last_tested_at"),
                    "last_test_error": key.get("last_test_error"),
                    "updated_at": key.get("updated_at")
                }
            else:
                status_map[provider_id] = {
                    "status": ProviderStatus.NOT_CONFIGURED.value,
                    "last_tested_at": None,
                    "last_test_error": None,
                    "updated_at": None
                }
        
        return {
            "success": True,
            "status_map": status_map
        }
        
    except Exception as e:
        logger.error(f"Get keys status error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/list")
async def list_user_keys(user_id: str = Depends(get_current_user)):
    """List all providers with their status for current user
    
    Returns status for ALL providers, even if not configured:
    - not_configured: No key saved
    - configured_untested: Key saved but never tested
    - configured_valid: Key tested successfully
    - configured_invalid: Last test failed
    
    Never returns plaintext keys (only masked)
    """
    try:
        # Get all providers
        all_providers = list_providers()
        
        # Get saved keys for user
        keys_cursor = db.api_keys_collection.find(
            {"user_id": str(user_id)},
            {"_id": 0, "api_key_encrypted": 0, "api_secret_encrypted": 0}
        )
        saved_keys = await keys_cursor.to_list(100)
        
        # Build status map
        keys_by_provider = {key['provider']: key for key in saved_keys}
        
        # Build response with all providers
        result = []
        for provider_info in all_providers:
            provider_id = provider_info['id']
            saved_key = keys_by_provider.get(provider_id)
            
            if not saved_key:
                # Not configured
                status_obj = {
                    "provider": provider_id,
                    "display_name": provider_info['display_name'],
                    "type": provider_info['type'],
                    "status": ProviderStatus.NOT_CONFIGURED.value,
                    "status_display": "Not configured",
                    "icon": provider_info['icon'],
                    "required_fields": provider_info['required_fields']
                }
            else:
                # Key exists, determine status based on test results
                last_test_ok = saved_key.get("last_test_ok")
                last_tested_at = saved_key.get("last_tested_at")
                last_test_error = saved_key.get("last_test_error")
                
                # Determine canonical status
                if last_test_ok is True:
                    status = ProviderStatus.CONFIGURED_VALID.value
                elif last_test_ok is False:
                    status = ProviderStatus.CONFIGURED_INVALID.value
                else:
                    status = ProviderStatus.CONFIGURED_UNTESTED.value
                
                # Get display text for canonical status
                status_display = get_status_display(status)
                if status == ProviderStatus.CONFIGURED_INVALID.value and last_test_error:
                    status_display += f" - {last_test_error}"
                
                status_obj = {
                    "provider": provider_id,
                    "display_name": provider_info['display_name'],
                    "type": provider_info['type'],
                    "status": status,  # Canonical status
                    "status_display": status_display,
                    "icon": provider_info['icon'],
                    "required_fields": provider_info['required_fields'],
                    "key_preview": "****" + saved_key.get("api_key_encrypted", "")[-4:] if saved_key.get("api_key_encrypted") else None,  # Masked preview
                    "name": saved_key.get("name"),  # Friendly name if provided
                    "created_at": saved_key.get("created_at"),
                    "updated_at": saved_key.get("updated_at"),
                    "last_tested_at": last_tested_at,
                    "last_test_error": last_test_error if last_test_ok is False else None
                }
            
            result.append(status_obj)
        
        return {
            "success": True,
            "keys": result,
            "total": len(result)
        }
        
    except Exception as e:
        logger.error(f"List keys error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/save")
async def save_key(
    data: APIKeySaveRequest,
    user_id: str = Depends(get_current_user)
):
    """Save API key with encryption
    
    Validates provider exists and required fields are provided
    Encrypts key before storage
    Implements read-after-write verification
    Emits realtime event on success
    """
    try:
        # Normalize provider ID to lowercase and validate
        provider_id = data.provider.lower().strip()
        
        # Strict normalization to the 7 supported exchange IDs + AI providers
        VALID_PROVIDERS = ['luno', 'binance', 'kucoin', 'bybit', 'kraken', 'bitget', 'gate', 'openai', 'flokx', 'fetchai', 'huggingface']
        
        if provider_id not in VALID_PROVIDERS:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid provider: {data.provider}. Valid providers: {', '.join(VALID_PROVIDERS)}"
            )
        
        # Validate provider exists in registry
        provider_def = get_provider(provider_id)
        if not provider_def:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown provider: {provider_id}. Valid providers: {', '.join(VALID_PROVIDERS)}"
            )
        
        # Log save attempt (no secrets)
        logger.info(f"🔑 Saving API key for user {user_id[:8]}, provider: {provider_id}")
        
        # Build credentials dict
        credentials = {
            "api_key": data.api_key,
            "api_secret": data.api_secret,
            "passphrase": data.passphrase
        }
        
        # Validate required fields
        for field in provider_def.required_fields:
            if not credentials.get(field):
                raise HTTPException(
                    status_code=400,
                    detail=f"Required field missing for {provider_def.display_name}: {field}"
                )
        
        # Encrypt credentials
        encrypted_payload = {
            "api_key": encrypt_api_key(data.api_key),
            "api_secret": encrypt_api_key(data.api_secret) if data.api_secret else None,
            "passphrase": encrypt_api_key(data.passphrase) if data.passphrase else None
        }
        
        # Check if key exists
        existing = await db.api_keys_collection.find_one({
            "user_id": str(user_id),
            "provider": provider_id
        })
        
        timestamp = datetime.now(timezone.utc).isoformat()
        
        # Generate id if this is a new key, preserve existing id for updates
        # Note: Existing ids are preserved as-is for backward compatibility
        key_id = existing.get("id") if existing else str(uuid4())
        
        key_doc = {
            "id": key_id,  # Always include id field
            "user_id": str(user_id),
            "provider": provider_id,
            "api_key_encrypted": encrypted_payload["api_key"],
            "api_secret_encrypted": encrypted_payload["api_secret"],
            "passphrase_encrypted": encrypted_payload["passphrase"],
            "name": data.name,  # Optional friendly name
            "created_at": existing.get("created_at") if existing else timestamp,
            "updated_at": timestamp,
            "last_tested_at": None,  # Reset test status when key changes
            "last_test_ok": None,
            "last_test_error": None,
            "status": ProviderStatus.CONFIGURED_UNTESTED.value
        }
        
        if existing:
            # Update
            result = await db.api_keys_collection.update_one(
                {"user_id": str(user_id), "provider": provider_id},
                {"$set": key_doc}
            )
            message = f"Updated {provider_def.display_name} API key"
            
            if result.modified_count == 0:
                logger.warning(f"Update returned 0 modified for user {user_id[:8]}, provider {provider_id}")
        else:
            # Insert
            insert_result = await db.api_keys_collection.insert_one(key_doc)
            message = f"Saved {provider_def.display_name} API key"
            
            if not insert_result.inserted_id:
                logger.error(f"Insert failed for user {user_id[:8]}, provider {provider_id}")
                raise HTTPException(
                    status_code=500,
                    detail=f"Failed to save key: insert returned no ID"
                )
        
        # READ-AFTER-WRITE VERIFICATION
        verification = await db.api_keys_collection.find_one({
            "user_id": str(user_id),
            "provider": provider_id
        })
        
        if not verification:
            logger.error(f"Read-after-write verification failed for user {user_id[:8]}, provider {provider_id}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to save key: verification failed (key not found after save)"
            )
        
        logger.info(f"✅ {message} for user {user_id[:8]}, provider: {provider_id} (verified)")
        
        # Emit realtime event
        try:
            await rt_events.key_saved(user_id, provider_id, provider_def.display_name)
        except Exception as e:
            logger.warning(f"Failed to emit key_saved event: {e}")
        
        return {
            "success": True,
            "message": message,
            "provider": provider_id,
            "status": ProviderStatus.CONFIGURED_UNTESTED.value,  # Canonical status
            "status_display": get_status_display(ProviderStatus.CONFIGURED_UNTESTED.value),
            "updated_at": timestamp
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Save key error for user {user_id[:8]}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/test")
async def test_key(
    data: APIKeyTestRequest,
    user_id: str = Depends(get_current_user)
):
    """Test API key by making a real API call
    
    Can test saved key (no credentials in request) or new key (credentials provided)
    Updates status in database on success/failure
    Emits realtime event with result
    """
    try:
        # Normalize provider ID
        provider_id = data.provider.lower().strip()
        
        # Log test attempt (no secrets)
        logger.info(f"🔑 Testing API key for user {user_id[:8]}, provider: {provider_id}")
        
        # Validate provider exists
        provider_def = get_provider(provider_id)
        if not provider_def:
            # Get list of valid providers for error message
            valid_providers = ", ".join(sorted(list_providers_ids()))
            raise HTTPException(
                status_code=400,
                detail=f"Unknown provider: {provider_id}. Valid providers: {valid_providers}"
            )
        
        # Get credentials - either from request or from database
        if data.api_key:
            # Test with provided credentials
            credentials = {
                "api_key": data.api_key,
                "api_secret": data.api_secret,
                "passphrase": data.passphrase
            }
        else:
            # Test with saved credentials
            saved_key = await db.api_keys_collection.find_one({
                "user_id": str(user_id),
                "provider": provider_id
            })
            
            if not saved_key:
                raise HTTPException(
                    status_code=404,
                    detail=f"No saved key found for {provider_def.display_name}. Provide api_key to test."
                )
            
            # Decrypt saved credentials
            credentials = {
                "api_key": decrypt_api_key(saved_key["api_key_encrypted"]),
                "api_secret": decrypt_api_key(saved_key["api_secret_encrypted"]) if saved_key.get("api_secret_encrypted") else None,
                "passphrase": decrypt_api_key(saved_key["passphrase_encrypted"]) if saved_key.get("passphrase_encrypted") else None
            }
        
        # Test the credentials
        success, error_message = await test_provider(provider_id, credentials)
        
        # Update database if testing saved key
        if not data.api_key:
            timestamp = datetime.now(timezone.utc).isoformat()
            # Use canonical statuses
            canonical_status = ProviderStatus.CONFIGURED_VALID.value if success else ProviderStatus.CONFIGURED_INVALID.value
            update_data = {
                "last_tested_at": timestamp,
                "last_test_ok": success,
                "last_test_error": error_message if not success else None,
                "status": canonical_status
            }
            
            await db.api_keys_collection.update_one(
                {"user_id": str(user_id), "provider": provider_id},
                {"$set": update_data}
            )
        
        # Emit realtime event
        try:
            await rt_events.key_tested(user_id, provider_id, provider_def.display_name, success, error_message)
        except Exception as e:
            logger.warning(f"Failed to emit key_tested event: {e}")
        
        if success:
            logger.info(f"✅ {provider_def.display_name} key test passed for user {user_id[:8]}, provider: {provider_id}")
            return {
                "success": True,
                "message": f"{provider_def.display_name} key is valid",
                "provider": provider_id,
                "status": ProviderStatus.CONFIGURED_VALID.value,  # Canonical status
                "status_display": get_status_display(ProviderStatus.CONFIGURED_VALID.value)
            }
        else:
            logger.warning(f"❌ {provider_def.display_name} key test failed for user {user_id[:8]}, provider: {provider_id}: {error_message}")
            return {
                "success": False,
                "message": f"Test failed: {error_message}",
                "provider": provider_id,
                "status": ProviderStatus.CONFIGURED_INVALID.value,  # Canonical status
                "status_display": get_status_display(ProviderStatus.CONFIGURED_INVALID.value)
            }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Test key error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{provider}")
async def save_key_provider_path(
    provider: str,
    data: APIKeySaveRequest,
    user_id: str = Depends(get_current_user)
):
    """Save API key with encryption (path parameter version)
    
    Legacy endpoint for backward compatibility.
    Validates provider exists and required fields are provided
    Encrypts key before storage
    Emits realtime event on success
    """
    # Override provider from path parameter
    data.provider = provider
    return await save_key(data, user_id)


@router.get("/{provider}")
async def get_key(
    provider: str,
    user_id: str = Depends(get_current_user)
):
    """Get masked API key for provider
    
    Returns masked key info (never exposes actual key)
    Includes test status if key has been tested
    """
    try:
        # Validate provider exists
        provider_def = get_provider(provider)
        if not provider_def:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown provider: {provider}"
            )
        
        # Get key from database
        saved_key = await db.api_keys_collection.find_one(
            {"user_id": str(user_id), "provider": provider},
            {"_id": 0, "api_key_encrypted": 0, "api_secret_encrypted": 0, "passphrase_encrypted": 0}
        )
        
        if not saved_key:
            raise HTTPException(
                status_code=404,
                detail=f"No API key found for {provider_def.display_name}"
            )
        
        # Build response with canonical statuses
        last_test_ok = saved_key.get("last_test_ok")
        
        if last_test_ok is True:
            status = ProviderStatus.CONFIGURED_VALID.value
        elif last_test_ok is False:
            status = ProviderStatus.CONFIGURED_INVALID.value
        else:
            status = ProviderStatus.CONFIGURED_UNTESTED.value
        
        status_display = get_status_display(status)
        
        return {
            "success": True,
            "provider": provider,
            "display_name": provider_def.display_name,
            "status": status,  # Canonical status
            "status_display": status_display,
            "created_at": saved_key.get("created_at"),
            "updated_at": saved_key.get("updated_at"),
            "last_tested_at": saved_key.get("last_tested_at"),
            "last_test_error": saved_key.get("last_test_error") if last_test_ok is False else None
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Get key error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{provider}")
async def delete_key(
    provider: str,
    user_id: str = Depends(get_current_user)
):
    """Delete API key for provider
    
    Idempotent - returns success even if key doesn't exist
    Emits realtime event on deletion
    """
    try:
        # Validate provider exists
        provider_def = get_provider(provider)
        if not provider_def:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown provider: {provider}"
            )
        
        # Delete key
        result = await db.api_keys_collection.delete_one({
            "user_id": str(user_id),
            "provider": provider
        })
        
        if result.deleted_count == 0:
            logger.info(f"ℹ️ No {provider} key found for user {user_id[:8]} (already deleted)")
            return {
                "success": True,
                "message": f"{provider_def.display_name} key not found (already deleted)"
            }
        
        logger.info(f"🗑️ Deleted {provider} key for user {user_id[:8]}")
        
        # Emit realtime event
        try:
            await rt_events.key_deleted(user_id, provider, provider_def.display_name)
        except Exception as e:
            logger.warning(f"Failed to emit key_deleted event: {e}")
        
        return {
            "success": True,
            "message": f"Deleted {provider_def.display_name} API key"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Delete key error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
