"""
OpenAI Key Resolver Service
Centralized OpenAI API key resolution for all AI modules.

Resolution priority:
1. Per-user key from database (encrypted)
2. System environment variable (OPENAI_API_KEY)
3. None (gracefully handle missing key)

Usage:
    from services.openai_key_resolver import resolve_openai_key
    
    api_key, source = await resolve_openai_key(user_id)
    if api_key:
        # Use the key
        client = AsyncOpenAI(api_key=api_key)
        logger.info(f"OpenAI key resolved source={source}")
    else:
        # Handle missing key gracefully
        logger.warning(f"OpenAI key missing source={source}")
"""

import os
import logging
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


async def resolve_openai_key(user_id: Optional[str]) -> Tuple[Optional[str], str]:
    """
    Resolve OpenAI API key with canonical priority.
    
    Priority:
    1. Per-user key from database (if user_id provided and key exists)
    2. System environment variable OPENAI_API_KEY
    3. None (missing)
    
    Args:
        user_id: User ID (optional). If None, skips user key lookup.
        
    Returns:
        Tuple of (api_key, source) where:
        - api_key: The resolved API key string, or None if missing
        - source: One of "user", "system", or "missing"
    
    Examples:
        >>> api_key, source = await resolve_openai_key("user123")
        >>> logger.info(f"OpenAI key resolved source={source}")
    """
    try:
        # Step 1: Try per-user key if user_id provided
        if user_id:
            try:
                from routes.api_key_management import get_decrypted_key
                
                key_data = await get_decrypted_key(user_id, "openai")
                if key_data and key_data.get("api_key"):
                    user_key = key_data.get("api_key", "").strip()
                    if user_key:
                        logger.info(f"OpenAI key resolved source=user for user {user_id[:8]}")
                        return user_key, "user"
            except Exception as e:
                # Don't fail if user key lookup fails - fall through to system key
                logger.warning(f"Failed to get user OpenAI key for {user_id[:8] if user_id else 'unknown'}: {e}")
        
        # Step 2: Try system environment variable
        system_key = os.getenv("OPENAI_API_KEY", "").strip()
        if system_key:
            logger.info(f"OpenAI key resolved source=system for user {user_id[:8] if user_id else 'system'}")
            return system_key, "system"
        
        # Step 3: No key available
        logger.warning(f"OpenAI key resolved source=missing for user {user_id[:8] if user_id else 'system'}")
        return None, "missing"
        
    except Exception as e:
        # Never raise - return missing on any error
        logger.error(f"Error resolving OpenAI key for user {user_id[:8] if user_id else 'system'}: {e}")
        return None, "missing"


async def get_openai_client(user_id: Optional[str] = None):
    """
    Get AsyncOpenAI client with resolved key.
    
    Convenience wrapper around resolve_openai_key that returns
    a ready-to-use AsyncOpenAI client.
    
    Args:
        user_id: User ID (optional)
        
    Returns:
        Tuple of (client, source) where:
        - client: AsyncOpenAI instance or None if no key
        - source: Key source ("user", "system", or "missing")
    
    Examples:
        >>> client, source = await get_openai_client(user_id)
        >>> if client:
        >>>     response = await client.chat.completions.create(...)
    """
    try:
        from openai import AsyncOpenAI
        
        api_key, source = await resolve_openai_key(user_id)
        
        if api_key:
            client = AsyncOpenAI(api_key=api_key)
            return client, source
        else:
            return None, source
            
    except ImportError:
        logger.error("OpenAI package not installed")
        return None, "missing"
    except Exception as e:
        logger.error(f"Error creating OpenAI client: {e}")
        return None, "missing"
