from fastapi import HTTPException, Depends, APIRouter, Request
import os
from datetime import datetime, timezone, timedelta
from typing import Optional, List
import logging
from uuid import uuid4

from models import User, UserLogin, UserRegister, Bot, BotCreate, APIKey, APIKeyCreate, Trade, SystemMode, Alert, ChatMessage, BotRiskMode
import database as db
from auth import create_access_token, get_current_user, get_password_hash, verify_password

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/auth/register")
async def register(request: Request, user: UserRegister):
    # Check invite code from header or body
    expected = (os.getenv("INVITE_CODE") or "").strip()
    provided_header = (request.headers.get("X-Invite-Code") or "").strip()
    provided_body = (user.invite_code or "").strip()
    provided = provided_header or provided_body
    
    if expected and provided != expected:
        raise HTTPException(status_code=403, detail="Invalid invite code")
    
    # Validate password: exactly one of password or password_hash must be provided
    if not user.password and not user.password_hash:
        raise HTTPException(status_code=400, detail="Either password or password_hash is required")
    if user.password and user.password_hash:
        raise HTTPException(status_code=400, detail="Provide either password or password_hash, not both")
    
    # Get plain password (prefer password field, treat password_hash as plain password for legacy)
    plain_password = user.password if user.password else user.password_hash

    # Normalize email to lowercase for consistency
    normalized_email = user.email.lower().strip()
    
    existing = await db.users_collection.find_one({"email": normalized_email}, {"_id": 0})
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")

    # Create user dict
    user_id = str(uuid4())
    hashed_pwd = get_password_hash(plain_password)
    
    # MIGRATION STRATEGY:
    # Store hash in both hashed_password (canonical) and password_hash (legacy)
    # This provides backward compatibility during transition period
    # After all users have logged in at least once (auto-migration), 
    # consider removing password_hash field in future version
    user_dict = {
        "id": user_id,
        "first_name": user.first_name,
        "email": normalized_email,
        "hashed_password": hashed_pwd,  # Canonical field (new standard)
        "password_hash": hashed_pwd,     # Keep for backward compatibility
        "created_at": datetime.now(timezone.utc).isoformat(),
        "currency": "ZAR",
        "system_mode": "testing",
        "autopilot_enabled": True,
        "bodyguard_enabled": True,
        "learning_enabled": True,
        "emergency_stop": False,
        "blocked": False,
        "is_admin": False,  # Default: regular user (admin must be set manually in DB)
        "two_factor_enabled": False
    }

    await db.users_collection.insert_one(user_dict)
    user_dict.pop("_id", None)

    # Send welcome email (non-blocking, best effort)
    # Note: User already has password from registration, so welcome email
    # provides a set-password link as an OPTIONAL way to change their password.
    # This is a convenience feature for users who want to reset immediately.
    try:
        from services.enhanced_email_service import enhanced_email_service
        from core.settings import FeatureFlags
        
        if FeatureFlags.ENABLE_EMAIL_REPORTS and enhanced_email_service.enabled:
            # Generate a password setup token for the welcome email
            # This is optional - user can login with their existing password
            # or use the link to set a new one
            import asyncio
            asyncio.create_task(enhanced_email_service.send_welcome_email(
                normalized_email,
                set_password_token=None  # Will generate internally and link to /set-password
            ))
            logger.info(f"📧 Welcome email queued for {normalized_email}")
    except Exception as email_error:
        # Don't fail registration if email fails
        logger.warning(f"Failed to send welcome email to {normalized_email}: {email_error}")

    # Create token
    access_token = create_access_token({"user_id": user_id})
    
    # Sanitize user object - NEVER return sensitive fields
    sensitive_fields = {'password_hash', 'hashed_password', 'hashedPassword', 'new_password', 'password', '_id'}
    sanitized_user = {k: v for k, v in user_dict.items() if k not in sensitive_fields}
    
    # Return with both new and legacy fields
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "token": access_token,  # Legacy field for backward compatibility
        "user": sanitized_user
    }




@router.post("/auth/login")
async def login(credentials: UserLogin):
    # Normalize email to lowercase for consistency
    normalized_email = credentials.email.lower().strip()
    
    user = await db.users_collection.find_one({"email": normalized_email}, {"_id": 0})
    
    if not user:
        raise HTTPException(status_code=401, detail="Invalid email or password")
    
    # Backward compatibility: check multiple password hash fields
    # Priority: hashed_password (new standard) > password_hash > hashedPassword (legacy)
    stored_hash = None
    hash_field_used = None
    
    if 'hashed_password' in user and user['hashed_password']:
        stored_hash = user['hashed_password']
        hash_field_used = 'hashed_password'
    elif 'password_hash' in user and user['password_hash']:
        stored_hash = user['password_hash']
        hash_field_used = 'password_hash'
    elif 'hashedPassword' in user and user['hashedPassword']:
        stored_hash = user['hashedPassword']
        hash_field_used = 'hashedPassword'
    
    if not stored_hash:
        logger.error(f"User {normalized_email} has no password hash field")
        raise HTTPException(status_code=401, detail="Invalid email or password")
    
    # Verify password against stored hash
    if not verify_password(credentials.password, stored_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    
    # Auto-migrate: ensure hashed_password is set to canonical field
    # MIGRATION STRATEGY: After successful login, migrate legacy hash fields
    # to canonical hashed_password field. Keep password_hash for compatibility.
    # This allows gradual migration without breaking existing users.
    if hash_field_used != 'hashed_password':
        logger.info(f"Migrating user {normalized_email} from {hash_field_used} to hashed_password")
        await db.users_collection.update_one(
            {"email": normalized_email},
            {"$set": {
                "hashed_password": stored_hash,
                # Keep password_hash for backward compatibility
                "password_hash": stored_hash
            }}
        )
    
    # BLOCKER FIX: Normalize user_id to handle both 'id' and '_id' fields
    # Some users may only have '_id' (MongoDB ObjectId), others have 'id' (string UUID)
    user_id = str(user.get("id") or user.get("_id"))
    
    # Auto-migrate: ensure 'id' field exists for users that only have '_id'
    if "id" not in user:
        logger.info(f"Migrating user {normalized_email} - adding 'id' field from '_id'")
        await db.users_collection.update_one(
            {"email": normalized_email},
            {"$set": {"id": user_id}}
        )
        user["id"] = user_id  # Update local copy
    
    access_token = create_access_token({"user_id": user_id})
    
    # Sanitize user object - NEVER return sensitive fields
    sensitive_fields = {'password_hash', 'hashed_password', 'hashedPassword', 'new_password', 'password', '_id'}
    sanitized_user = {k: v for k, v in user.items() if k not in sensitive_fields}
    
    # Return with both new and legacy fields
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "token": access_token,  # Legacy field for backward compatibility
        "user": sanitized_user
    }


@router.get("/auth/me")
async def get_current_user_profile(user_id: str = Depends(get_current_user)):
    """Get current user profile - tries both 'id' field and MongoDB '_id' ObjectId
    
    Returns user object with both 'id' and 'user_id' fields for frontend compatibility.
    """
    from bson import ObjectId
    from bson.errors import InvalidId
    
    # First try with string id field (preferred)
    user = await db.users_collection.find_one({"id": user_id}, {"_id": 0})
    
    # If not found, try with ObjectId (fallback for older users)
    if not user:
        # Validate ObjectId format before querying (24 hex characters)
        if len(user_id) == 24 and all(c in '0123456789abcdefABCDEF' for c in user_id):
            try:
                user = await db.users_collection.find_one({"_id": ObjectId(user_id)})
                if user:
                    # Remove _id and use id field going forward
                    user.pop("_id", None)
                    # Ensure id field exists for future queries
                    if "id" not in user:
                        user["id"] = user_id
            except InvalidId:
                pass  # Invalid ObjectId despite format check
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Sanitize - never return sensitive fields
    sensitive_fields = {'password_hash', 'hashed_password', 'hashedPassword', 'new_password', 'password', '_id'}
    sanitized_user = {k: v for k, v in user.items() if k not in sensitive_fields}
    
    # Ensure both 'id' and 'user_id' fields are present for frontend compatibility
    if 'id' in sanitized_user:
        sanitized_user['user_id'] = sanitized_user['id']
    elif 'user_id' in sanitized_user:
        sanitized_user['id'] = sanitized_user['user_id']
    else:
        # Neither field present - add both using the user_id from token
        sanitized_user['id'] = user_id
        sanitized_user['user_id'] = user_id
    
    return sanitized_user


@router.put("/auth/profile")
async def update_profile(update: dict, user_id: str = Depends(get_current_user)):
    """Update user profile - sanitized and validated"""
    try:
        # Prevent updating sensitive fields
        forbidden_fields = {'password_hash', 'hashed_password', 'hashedPassword', 'new_password', 'password', 'id', '_id', 'email'}
        update_data = {k: v for k, v in update.items() if v is not None and k not in forbidden_fields}
        
        if not update_data:
            raise HTTPException(status_code=400, detail="No valid fields to update")
        
        # Update user profile
        result = await db.users_collection.update_one(
            {"id": user_id},
            {"$set": update_data}
        )
        
        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="User not found")
        
        # Clear AI chat cache to use new name if name changed
        if 'first_name' in update_data:
            from ai_service import ai_service
            if user_id in ai_service.chats:
                del ai_service.chats[user_id]
                logger.info(f"Cleared AI chat cache for user {user_id} after name update")
        
        # Fetch and return updated user
        user = await db.users_collection.find_one({"id": user_id}, {"_id": 0})
        if not user:
            raise HTTPException(status_code=404, detail="User not found after update")
        
        # Sanitize - never return sensitive fields
        sensitive_fields = {'password_hash', 'hashed_password', 'hashedPassword', 'new_password', 'password', '_id'}
        sanitized_user = {k: v for k, v in user.items() if k not in sensitive_fields}
        
        return {
            "success": True,
            "message": "Profile updated successfully",
            "user": sanitized_user
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Profile update error: {e}")
        raise HTTPException(status_code=500, detail=f"Profile update failed: {str(e)}")


@router.get("/auth/profile")
async def get_profile(user_id: str = Depends(get_current_user)):
    """Get user profile - backward-compatible alias to /auth/me
    
    This endpoint provides the same functionality as GET /auth/me
    to maintain compatibility with frontend expectations.
    
    Returns:
        Sanitized user profile (no password fields)
    """
    from bson import ObjectId
    from bson.errors import InvalidId
    
    # First try with string id field (preferred)
    user = await db.users_collection.find_one({"id": user_id}, {"_id": 0})
    
    # If not found, try with ObjectId (fallback for older users)
    if not user:
        # Validate ObjectId format before querying (24 hex characters)
        if len(user_id) == 24 and all(c in '0123456789abcdefABCDEF' for c in user_id):
            try:
                user = await db.users_collection.find_one({"_id": ObjectId(user_id)})
                if user:
                    # Remove _id and use id field going forward
                    user.pop("_id", None)
                    # Ensure id field exists for future queries
                    if "id" not in user:
                        user["id"] = user_id
            except InvalidId:
                pass  # Invalid ObjectId despite format check
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Sanitize - never return sensitive fields
    sensitive_fields = {'password_hash', 'hashed_password', 'hashedPassword', 'new_password', 'password', '_id'}
    return {k: v for k, v in user.items() if k not in sensitive_fields}


