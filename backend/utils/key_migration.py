"""
API Key Migration Utility

Migrates API keys encrypted with old derived Fernet key (from JWT_SECRET)
to new dedicated AMARKTAI_FERNET_KEY encryption.

This allows seamless transition when switching from derived keys to dedicated keys.
"""

import os
import base64
import hashlib
import logging
from typing import Optional, Tuple
from cryptography.fernet import Fernet, InvalidToken

logger = logging.getLogger(__name__)


def get_derived_key_from_jwt() -> bytes:
    """Get the old derived Fernet key from JWT_SECRET
    
    This is the OLD method that we're migrating away from.
    Used only for decrypting old keys during migration.
    
    Returns:
        bytes: Base64-encoded Fernet key derived from JWT_SECRET
    """
    jwt_secret = os.getenv("JWT_SECRET", "default-dev-secret-change-in-production")
    key_material = hashlib.sha256(jwt_secret.encode()).digest()
    return base64.urlsafe_b64encode(key_material)


def get_new_fernet_key() -> Optional[bytes]:
    """Get the new dedicated Fernet key
    
    Returns:
        bytes: Base64-encoded Fernet key from AMARKTAI_FERNET_KEY or None if not set
    """
    key_env = os.getenv("AMARKTAI_FERNET_KEY") or os.getenv("FERNET_KEY")
    if not key_env:
        return None
    return key_env.encode()


async def migrate_encrypted_key(encrypted_value: str) -> Tuple[bool, Optional[str], Optional[str]]:
    """Attempt to migrate an encrypted key from old to new encryption
    
    Tries to decrypt with old derived key, then re-encrypt with new key.
    
    Args:
        encrypted_value: The encrypted token to migrate
        
    Returns:
        Tuple of (success: bool, new_encrypted_value: str or None, error: str or None)
    """
    old_key = get_derived_key_from_jwt()
    new_key = get_new_fernet_key()
    
    if not new_key:
        return False, None, "AMARKTAI_FERNET_KEY not set - cannot migrate"
    
    try:
        # Try to decrypt with old key
        old_fernet = Fernet(old_key)
        plaintext = old_fernet.decrypt(encrypted_value.encode())
        
        # Re-encrypt with new key
        new_fernet = Fernet(new_key)
        new_encrypted = new_fernet.encrypt(plaintext)
        
        return True, new_encrypted.decode(), None
        
    except InvalidToken:
        # Not encrypted with old key, might already be migrated or corrupted
        return False, None, "Token not encrypted with derived key (might already be migrated)"
    except Exception as e:
        return False, None, f"Migration failed: {str(e)}"


async def migrate_user_keys(user_id: str) -> dict:
    """Migrate all API keys for a user from old to new encryption
    
    Args:
        user_id: User ID to migrate keys for
        
    Returns:
        dict: Migration results with counts
    """
    import database as db
    
    # Check if new key is configured
    new_key = get_new_fernet_key()
    if not new_key:
        return {
            "success": False,
            "error": "AMARKTAI_FERNET_KEY not configured - cannot migrate",
            "migrated": 0,
            "failed": 0,
            "skipped": 0
        }
    
    # Get all keys for user
    keys = await db.api_keys_collection.find({"user_id": user_id}).to_list(100)
    
    migrated_count = 0
    failed_count = 0
    skipped_count = 0
    errors = []
    
    for key_doc in keys:
        provider = key_doc.get("provider", "unknown")
        
        # Try to migrate api_key_encrypted
        if "api_key_encrypted" in key_doc:
            success, new_value, error = await migrate_encrypted_key(key_doc["api_key_encrypted"])
            if success:
                await db.api_keys_collection.update_one(
                    {"_id": key_doc["_id"]},
                    {"$set": {"api_key_encrypted": new_value}}
                )
                migrated_count += 1
                logger.info(f"✅ Migrated api_key for user {user_id[:8]}, provider {provider}")
            elif "might already be migrated" in (error or ""):
                skipped_count += 1
                logger.debug(f"⏭️ Skipped api_key for user {user_id[:8]}, provider {provider}: {error}")
            else:
                failed_count += 1
                errors.append(f"{provider}: {error}")
                logger.warning(f"❌ Failed to migrate api_key for user {user_id[:8]}, provider {provider}: {error}")
        
        # Try to migrate api_secret_encrypted
        if "api_secret_encrypted" in key_doc and key_doc["api_secret_encrypted"]:
            success, new_value, error = await migrate_encrypted_key(key_doc["api_secret_encrypted"])
            if success:
                await db.api_keys_collection.update_one(
                    {"_id": key_doc["_id"]},
                    {"$set": {"api_secret_encrypted": new_value}}
                )
                logger.info(f"✅ Migrated api_secret for user {user_id[:8]}, provider {provider}")
        
        # Try to migrate passphrase_encrypted
        if "passphrase_encrypted" in key_doc and key_doc["passphrase_encrypted"]:
            success, new_value, error = await migrate_encrypted_key(key_doc["passphrase_encrypted"])
            if success:
                await db.api_keys_collection.update_one(
                    {"_id": key_doc["_id"]},
                    {"$set": {"passphrase_encrypted": new_value}}
                )
                logger.info(f"✅ Migrated passphrase for user {user_id[:8]}, provider {provider}")
    
    return {
        "success": True,
        "migrated": migrated_count,
        "failed": failed_count,
        "skipped": skipped_count,
        "errors": errors,
        "total_keys": len(keys)
    }


async def migrate_all_keys() -> dict:
    """Migrate all API keys in the system from old to new encryption
    
    Returns:
        dict: Migration results with counts by user
    """
    import database as db
    
    # Get all unique user IDs that have API keys
    pipeline = [
        {"$group": {"_id": "$user_id"}},
        {"$limit": 1000}
    ]
    
    user_ids_cursor = db.api_keys_collection.aggregate(pipeline)
    user_ids = [doc["_id"] async for doc in user_ids_cursor]
    
    total_migrated = 0
    total_failed = 0
    total_skipped = 0
    user_results = []
    
    for user_id in user_ids:
        result = await migrate_user_keys(str(user_id))
        total_migrated += result.get("migrated", 0)
        total_failed += result.get("failed", 0)
        total_skipped += result.get("skipped", 0)
        user_results.append({
            "user_id": str(user_id)[:8] + "...",
            **result
        })
    
    return {
        "success": True,
        "total_users": len(user_ids),
        "total_migrated": total_migrated,
        "total_failed": total_failed,
        "total_skipped": total_skipped,
        "user_results": user_results
    }
