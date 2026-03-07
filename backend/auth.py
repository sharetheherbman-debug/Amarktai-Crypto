from datetime import datetime, timedelta, timezone
from typing import Optional
import logging
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import HTTPException, status, Depends, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import os

JWT_SECRET = os.getenv("JWT_SECRET", "your-secret-key")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")  # Allow override via env
ALGORITHM = JWT_ALGORITHM  # Keep for backward compatibility
ACCESS_TOKEN_EXPIRE_HOURS = 24

# ---------- Startup validation ----------
_UNSAFE_JWT_DEFAULTS = {
    "your-secret-key",
    "your-secret-key-change-in-production",
    "change-me-use-openssl-rand-hex-32",
    "changeme",
    "",
}

def validate_jwt_secret():
    """Fail fast if JWT_SECRET is still a placeholder.

    Called once at import time so the server refuses to start with an
    insecure configuration.  The check is skipped when ENVIRONMENT is
    explicitly set to 'testing' (used by the test-suite).
    """
    env = os.getenv("ENVIRONMENT", "").lower()
    if env == "testing":
        return  # allow tests to run with dummy values
    if JWT_SECRET in _UNSAFE_JWT_DEFAULTS:
        raise RuntimeError(
            "CRITICAL: JWT_SECRET is not set or is still a default placeholder. "
            "Set a strong random value via: openssl rand -hex 32"
        )

validate_jwt_secret()

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBearer()
optional_security = HTTPBearer(auto_error=False)
logger = logging.getLogger(__name__)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(hours=ACCESS_TOKEN_EXPIRE_HOURS)
    to_encode.update({"exp": expire})
    
    # Ensure standard "sub" field is set for JWT compliance
    # Support both "user_id" and "sub" for backward compatibility
    if "user_id" in to_encode and "sub" not in to_encode:
        to_encode["sub"] = to_encode["user_id"]
    elif "sub" in to_encode and "user_id" not in to_encode:
        to_encode["user_id"] = to_encode["sub"]
    
    encoded_jwt = jwt.encode(to_encode, JWT_SECRET, algorithm=ALGORITHM)
    return encoded_jwt

def decode_token(token: str) -> dict:
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> str:
    """Get current user ID from JWT token - returns string user_id
    
    Supports both "sub" (JWT standard) and "user_id" (legacy) fields for backward compatibility.
    Always returns a string user_id, never a dict.
    """
    token = credentials.credentials
    payload = decode_token(token)
    
    # Try standard "sub" field first, then fallback to "user_id" for backward compatibility
    user_id: str = payload.get("sub") or payload.get("user_id")
    
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
        )
    return user_id

async def get_optional_user(credentials: HTTPAuthorizationCredentials = Depends(optional_security)) -> Optional[str]:
    """Get user ID from JWT if available, otherwise return None."""
    if not credentials:
        return None
    try:
        payload = decode_token(credentials.credentials)
    except HTTPException:
        return None
    except Exception as exc:
        logger.debug("Optional auth decode failed: %s", exc)
        return None

    return payload.get("sub") or payload.get("user_id")

async def resolve_current_user(current_user) -> str:
    """Normalize get_current_user() return value to always return user_id string
    
    Handles multiple formats that get_current_user() might return:
    - string user_id (most common)
    - dict with 'id' or 'user_id' field
    - email string (lookup in database)
    - ObjectId (convert to string)
    
    Returns: user_id as string, suitable for database lookups
    """
    import database as db
    from bson import ObjectId
    from bson.errors import InvalidId
    
    # Case 1: Already a string (most common)
    if isinstance(current_user, str):
        # Check if it looks like an email (contains @)
        if "@" in current_user:
            # Look up user by email to get user_id
            user = await db.users_collection.find_one(
                {"email": current_user}, 
                {"_id": 0, "id": 1}
            )
            if user and "id" in user:
                return user["id"]
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found by email"
            )
        # Already a user_id string
        return current_user
    
    # Case 2: Dict with user info
    if isinstance(current_user, dict):
        # Try common field names
        if "id" in current_user:
            return str(current_user["id"])
        if "user_id" in current_user:
            return str(current_user["user_id"])
        if "_id" in current_user:
            return str(current_user["_id"])
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid user dict format"
        )
    
    # Case 3: ObjectId
    if isinstance(current_user, ObjectId):
        return str(current_user)
    
    # Unknown format
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=f"Unsupported current_user type: {type(current_user)}"
    )

async def verify_admin_password(password: str) -> bool:
    """Verify admin password"""
    admin_password = os.getenv("ADMIN_PASSWORD", "ashmor12@")
    return password == admin_password

async def is_admin(user_id: str) -> bool:
    """Check if user has admin privileges - never crashes"""
    try:
        import database as db
        from bson import ObjectId
        from bson.errors import InvalidId
        
        # Try by id field first
        user = await db.users_collection.find_one({"id": user_id}, {"_id": 0})
        
        # Fallback to ObjectId if not found and format is valid (24 hex characters)
        if not user and len(user_id) == 24 and all(c in '0123456789abcdefABCDEF' for c in user_id):
            try:
                user = await db.users_collection.find_one({"_id": ObjectId(user_id)})
            except InvalidId:
                pass  # Invalid ObjectId despite format check
        
        if not user:
            return False
        
        # Check if user has is_admin field set to True or role == 'admin'
        return user.get('is_admin', False) or user.get('role', '') == 'admin'
    except Exception as e:
        # Log error but don't crash - default to non-admin
        import logging
        logging.getLogger(__name__).error(f"Error checking admin status: {e}")
        return False

async def require_admin(user_id: str = Depends(get_current_user)) -> str:
    """Require user to be admin, raises 403 if not"""
    if not await is_admin(user_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required"
        )
    return user_id

# Alias for backward compatibility with routers that import get_admin_user
get_admin_user = require_admin
