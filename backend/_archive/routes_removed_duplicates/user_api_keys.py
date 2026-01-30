"""
User API Key Management
Handles per-user API keys for OpenAI, FLock.io, and Fetch wallet
"""

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from typing import Optional, Dict, Literal
import logging
import os

from auth import get_current_user
import database as db
from routes.api_key_management import encrypt_api_key, decrypt_api_key

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/user", tags=["User Settings"])


class UserAPIKeyRequest(BaseModel):
    """Request model for saving user API keys"""
    service: Literal["openai", "flock", "fetch_wallet"]
    key: str = Field(..., min_length=1, description="API key or wallet seed")
    

class UserAPIKeyResponse(BaseModel):
    """Response model for API key operations"""
    success: bool
    message: str
    service: str


class PaymentConfigRequest(BaseModel):
    """Request model for payment agent configuration"""
    enabled: bool = False
    wallet_seed: Optional[str] = None
    daily_budget_fet: float = Field(default=100, ge=10, le=10000)
    network: Literal["testnet", "mainnet"] = "testnet"
    max_single_transaction_fet: float = Field(default=50, ge=1, le=1000)


class PaymentConfigResponse(BaseModel):
    """Response model for payment configuration"""
    success: bool
    message: str
    config: Optional[Dict] = None


async def get_user_api_key(user_id: str, service: str) -> Optional[str]:
    """
    Get user's API key for a specific service
    
    Args:
        user_id: User ID
        service: Service name (openai, flock, fetch_wallet)
        
    Returns:
        Decrypted API key or None if not found
    """
    try:
        user = await db.users_collection.find_one({"_id": user_id})
        if not user:
            return None
            
        api_keys = user.get("api_keys", {})
        encrypted_key = api_keys.get(service)
        
        if encrypted_key:
            return decrypt_api_key(encrypted_key)
        return None
    except Exception as e:
        logger.error(f"Error retrieving user API key for {service}: {e}")
        return None


async def set_user_api_key(user_id: str, service: str, api_key: str) -> bool:
    """
    Save user's API key for a specific service
    
    Args:
        user_id: User ID
        service: Service name
        api_key: Plain text API key to encrypt and store
        
    Returns:
        True if successful, False otherwise
    """
    try:
        encrypted_key = encrypt_api_key(api_key)
        
        result = await db.users_collection.update_one(
            {"_id": user_id},
            {
                "$set": {
                    f"api_keys.{service}": encrypted_key,
                    "updated_at": datetime.utcnow()
                }
            },
            upsert=True
        )
        
        return result.modified_count > 0 or result.upserted_id is not None
    except Exception as e:
        logger.error(f"Error saving user API key for {service}: {e}")
        return False


@router.post("/api-keys", response_model=UserAPIKeyResponse)
async def save_user_api_key(
    data: UserAPIKeyRequest,
    user_id: str = Depends(get_current_user)
):
    """
    Save user's API key for OpenAI, FLock.io, or Fetch wallet
    
    Encrypts and stores the key securely in MongoDB.
    Users can provide their own keys or use system defaults.
    
    Args:
        data: Service and API key to save
        user_id: Current user ID from JWT
        
    Returns:
        Success status and message
    """
    try:
        # Validate service
        if data.service not in ["openai", "flock", "fetch_wallet"]:
            raise HTTPException(status_code=400, detail="Invalid service")
        
        # Validate key format
        if data.service == "openai" and not data.key.startswith("sk-"):
            raise HTTPException(
                status_code=400, 
                detail="Invalid OpenAI key format (should start with 'sk-')"
            )
        elif data.service == "flock" and not data.key.startswith("flock_"):
            raise HTTPException(
                status_code=400,
                detail="Invalid FLock.io key format (should start with 'flock_')"
            )
        elif data.service == "fetch_wallet":
            words = data.key.strip().split()
            if len(words) != 24:
                raise HTTPException(
                    status_code=400,
                    detail="Invalid Fetch wallet seed (must be 24 words)"
                )
        
        # Save encrypted key
        success = await set_user_api_key(user_id, data.service, data.key)
        
        if not success:
            raise HTTPException(status_code=500, detail="Failed to save API key")
        
        logger.info(f"User {user_id} saved {data.service} API key")
        
        return UserAPIKeyResponse(
            success=True,
            message=f"{data.service.title()} API key saved successfully",
            service=data.service
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in save_user_api_key: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api-keys/{service}")
async def get_api_key_status(
    service: Literal["openai", "flock", "fetch_wallet"],
    user_id: str = Depends(get_current_user)
):
    """
    Check if user has configured an API key for a service
    
    Args:
        service: Service to check
        user_id: Current user ID
        
    Returns:
        Status of the API key (configured or using system default)
    """
    try:
        user_key = await get_user_api_key(user_id, service)
        system_key = os.getenv(f"{service.upper()}_API_KEY") or os.getenv("FETCH_WALLET_SEED")
        
        return {
            "service": service,
            "user_configured": user_key is not None,
            "system_available": system_key is not None,
            "status": "user" if user_key else ("system" if system_key else "none")
        }
    except Exception as e:
        logger.error(f"Error checking API key status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/api-keys/{service}")
async def delete_user_api_key(
    service: Literal["openai", "flock", "fetch_wallet"],
    user_id: str = Depends(get_current_user)
):
    """
    Delete user's API key for a service
    
    After deletion, system will fall back to default key if available.
    
    Args:
        service: Service to delete key for
        user_id: Current user ID
        
    Returns:
        Success status
    """
    try:
        result = await db.users_collection.update_one(
            {"_id": user_id},
            {"$unset": {f"api_keys.{service}": ""}}
        )
        
        if result.modified_count > 0:
            logger.info(f"User {user_id} deleted {service} API key")
            return {
                "success": True,
                "message": f"{service.title()} API key deleted. Using system default."
            }
        else:
            return {
                "success": False,
                "message": "No API key found to delete"
            }
    except Exception as e:
        logger.error(f"Error deleting API key: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/payment-config", response_model=PaymentConfigResponse)
async def save_payment_config(
    config: PaymentConfigRequest,
    user_id: str = Depends(get_current_user)
):
    """
    Save user's payment agent configuration
    
    Includes wallet seed, budget limits, and network selection.
    
    Args:
        config: Payment configuration
        user_id: Current user ID
        
    Returns:
        Success status and saved configuration
    """
    try:
        # If enabling payment agent, wallet seed is required
        if config.enabled and not config.wallet_seed:
            raise HTTPException(
                status_code=400,
                detail="Wallet seed required to enable payment agent"
            )
        
        # Encrypt wallet seed if provided
        encrypted_seed = None
        if config.wallet_seed:
            encrypted_seed = encrypt_api_key(config.wallet_seed)
        
        # Save configuration
        payment_config = {
            "enabled": config.enabled,
            "daily_budget_fet": config.daily_budget_fet,
            "network": config.network,
            "max_single_transaction_fet": config.max_single_transaction_fet
        }
        
        if encrypted_seed:
            payment_config["wallet_seed"] = encrypted_seed
        
        result = await db.users_collection.update_one(
            {"_id": user_id},
            {
                "$set": {
                    "payment_config": payment_config,
                    "updated_at": datetime.utcnow()
                }
            }
        )
        
        if result.modified_count > 0 or result.matched_count > 0:
            logger.info(f"User {user_id} updated payment configuration")
            
            # Return config without sensitive data
            safe_config = payment_config.copy()
            if "wallet_seed" in safe_config:
                safe_config["wallet_seed"] = "***configured***"
            
            return PaymentConfigResponse(
                success=True,
                message="Payment configuration saved successfully",
                config=safe_config
            )
        else:
            raise HTTPException(status_code=500, detail="Failed to save configuration")
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error saving payment config: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/payment-config")
async def get_payment_config(user_id: str = Depends(get_current_user)):
    """
    Get user's payment agent configuration
    
    Args:
        user_id: Current user ID
        
    Returns:
        Payment configuration (without sensitive wallet seed)
    """
    try:
        user = await db.users_collection.find_one({"_id": user_id})
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        config = user.get("payment_config", {})
        
        # Remove sensitive wallet seed from response
        safe_config = {
            "enabled": config.get("enabled", False),
            "daily_budget_fet": config.get("daily_budget_fet", 100),
            "network": config.get("network", "testnet"),
            "max_single_transaction_fet": config.get("max_single_transaction_fet", 50),
            "has_wallet": "wallet_seed" in config
        }
        
        return safe_config
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving payment config: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/generate-wallet")
async def generate_fetch_wallet(user_id: str = Depends(get_current_user)):
    """
    Generate a new Fetch.ai wallet for the user
    
    Creates a new wallet with a 24-word mnemonic seed phrase.
    User must save the seed phrase securely.
    
    Args:
        user_id: Current user ID
        
    Returns:
        New wallet address and mnemonic
    """
    try:
        from cosmpy.aerial.wallet import LocalWallet
        from cosmpy.crypto.keypairs import PrivateKey
        
        # Generate new wallet
        private_key = PrivateKey()
        wallet = LocalWallet(private_key)
        
        # Generate 24-word mnemonic
        mnemonic = private_key.to_mnemonic()
        address = str(wallet.address())
        
        logger.info(f"Generated new Fetch wallet for user {user_id}: {address}")
        
        return {
            "success": True,
            "address": address,
            "mnemonic": mnemonic,
            "warning": "Save this mnemonic securely. It cannot be recovered if lost."
        }
        
    except Exception as e:
        logger.error(f"Error generating wallet: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate wallet")


# Helper function to get user's OpenAI client
async def get_user_openai_client(user_id: str):
    """
    Get OpenAI client using user's key or system default
    
    Args:
        user_id: User ID
        
    Returns:
        OpenAI client instance
    """
    from openai import AsyncOpenAI
    
    user_key = await get_user_api_key(user_id, "openai")
    api_key = user_key if user_key else os.getenv("OPENAI_API_KEY")
    
    if not api_key:
        raise ValueError("No OpenAI API key configured (user or system)")
    
    return AsyncOpenAI(api_key=api_key)


# Helper function to get user's FLock client
async def get_user_flock_client(user_id: str):
    """
    Get FLock.io client using user's key or system default
    
    Args:
        user_id: User ID
        
    Returns:
        FLock client instance or None
    """
    from engines.flock_ai_client import FlockAIClient
    
    user_key = await get_user_api_key(user_id, "flock")
    api_key = user_key if user_key else os.getenv("FLOCK_API_KEY")
    
    if not api_key:
        return None
    
    return FlockAIClient(api_key=api_key)


# Helper function to get user's payment agent
async def get_user_payment_agent(user_id: str):
    """
    Get payment agent using user's wallet or system default
    
    Args:
        user_id: User ID
        
    Returns:
        Payment agent instance or None
    """
    from engines.payment_agent import PaymentAgent
    
    user = await db.users_collection.find_one({"_id": user_id})
    if not user:
        return None
    
    payment_config = user.get("payment_config", {})
    
    if not payment_config.get("enabled", False):
        return None
    
    # Get user's wallet seed
    encrypted_seed = payment_config.get("wallet_seed")
    if encrypted_seed:
        wallet_seed = decrypt_api_key(encrypted_seed)
    else:
        # Fall back to system wallet
        wallet_seed = os.getenv("FETCH_WALLET_SEED")
    
    if not wallet_seed:
        return None
    
    # Create payment agent with user's configuration
    agent = PaymentAgent(
        wallet_seed=wallet_seed,
        network=payment_config.get("network", "testnet"),
        daily_budget_fet=payment_config.get("daily_budget_fet", 100),
        max_single_transaction_fet=payment_config.get("max_single_transaction_fet", 50)
    )
    
    return agent


from datetime import datetime
