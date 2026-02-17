"""
HuggingFace Key Resolver Service
Centralized HuggingFace API key resolution for all AI modules.

Resolution priority:
1. Per-user key from database (encrypted)
2. System environment variable (HUGGINGFACE_API_KEY or HF_API_KEY)
3. None (gracefully handle missing key)

Usage:
    from services.huggingface_key_resolver import resolve_huggingface_key
    
    api_key, source = await resolve_huggingface_key(user_id)
    if api_key:
        # Use the key
        from huggingface_hub import InferenceClient
        client = InferenceClient(token=api_key)
        logger.info(f"HuggingFace key resolved source={source}")
    else:
        # Handle missing key gracefully
        logger.warning(f"HuggingFace key missing source={source}")
"""

import os
import logging
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


async def resolve_huggingface_key(user_id: Optional[str]) -> Tuple[Optional[str], str]:
    """
    Resolve HuggingFace API key with canonical priority.
    
    Priority:
    1. Per-user key from database (if user_id provided and key exists)
    2. System environment variable HUGGINGFACE_API_KEY or HF_API_KEY
    3. None (missing)
    
    Args:
        user_id: User ID (optional). If None, skips user key lookup.
        
    Returns:
        Tuple of (api_key, source) where:
        - api_key: The resolved API key string, or None if missing
        - source: One of "user", "system", or "missing"
    
    Examples:
        >>> api_key, source = await resolve_huggingface_key("user123")
        >>> logger.info(f"HuggingFace key resolved source={source}")
    """
    try:
        # Step 1: Try per-user key if user_id provided
        if user_id:
            try:
                from routes.api_key_management import get_decrypted_key
                
                key_data = await get_decrypted_key(user_id, "huggingface")
                if key_data and key_data.get("api_key"):
                    user_key = key_data.get("api_key", "").strip()
                    if user_key:
                        logger.info(f"HuggingFace key resolved source=user for user {user_id[:8]}")
                        return user_key, "user"
            except Exception as e:
                # Don't fail if user key lookup fails - fall through to system key
                logger.warning(f"Failed to get user HuggingFace key for {user_id[:8] if user_id else 'unknown'}: {e}")
        
        # Step 2: Try system environment variables
        # Check both HUGGINGFACE_API_KEY and HF_API_KEY (common aliases)
        system_key = os.getenv("HUGGINGFACE_API_KEY", "").strip()
        if not system_key:
            system_key = os.getenv("HF_API_KEY", "").strip()
        
        if system_key:
            logger.info(f"HuggingFace key resolved source=system for user {user_id[:8] if user_id else 'system'}")
            return system_key, "system"
        
        # Step 3: No key available
        logger.warning(f"HuggingFace key resolved source=missing for user {user_id[:8] if user_id else 'system'}")
        return None, "missing"
        
    except Exception as e:
        # Never raise - return missing on any error
        logger.error(f"Error resolving HuggingFace key for user {user_id[:8] if user_id else 'system'}: {e}")
        return None, "missing"


async def get_huggingface_client(user_id: Optional[str] = None, model: Optional[str] = None):
    """
    Get HuggingFace InferenceClient with resolved key.
    
    Convenience wrapper around resolve_huggingface_key that returns
    a ready-to-use InferenceClient.
    
    Args:
        user_id: User ID (optional)
        model: Model name/ID to use (optional)
        
    Returns:
        Tuple of (client, source) where:
        - client: InferenceClient instance or None if no key
        - source: Key source ("user", "system", or "missing")
    
    Examples:
        >>> client, source = await get_huggingface_client(user_id, model="bert-base-uncased")
        >>> if client:
        >>>     result = client.feature_extraction("Hello world")
    """
    try:
        from huggingface_hub import InferenceClient
        
        api_key, source = await resolve_huggingface_key(user_id)
        
        if api_key:
            client = InferenceClient(token=api_key, model=model)
            return client, source
        else:
            return None, source
            
    except ImportError:
        logger.error("HuggingFace Hub package not installed - please install huggingface_hub")
        return None, "missing"
    except Exception as e:
        logger.error(f"Error creating HuggingFace client: {e}")
        return None, "missing"


async def test_huggingface_connection(user_id: Optional[str] = None) -> dict:
    """
    Test HuggingFace API connection with the resolved key.
    
    Args:
        user_id: User ID (optional)
        
    Returns:
        Dict with status and message:
        {
            "status": "success" | "error",
            "message": "...",
            "source": "user" | "system" | "missing"
        }
    """
    try:
        api_key, source = await resolve_huggingface_key(user_id)
        
        if not api_key:
            return {
                "status": "error",
                "message": "No HuggingFace API key configured",
                "source": source
            }
        
        # Try to validate the key by making a simple API call
        try:
            from huggingface_hub import HfApi
            
            api = HfApi(token=api_key)
            # Simple validation - try to get user info
            user_info = api.whoami()
            
            return {
                "status": "success",
                "message": f"Connected as {user_info.get('name', 'Unknown')}",
                "source": source,
                "user_info": {
                    "name": user_info.get("name"),
                    "fullname": user_info.get("fullname"),
                    "type": user_info.get("type")
                }
            }
        except Exception as e:
            return {
                "status": "error",
                "message": f"Failed to connect to HuggingFace: {str(e)}",
                "source": source
            }
            
    except Exception as e:
        logger.error(f"Error testing HuggingFace connection: {e}")
        return {
            "status": "error",
            "message": str(e),
            "source": "missing"
        }
