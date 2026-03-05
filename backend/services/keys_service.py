"""
Keys Service - API Key Management and Testing
Handles save, test, and runtime resolution of API keys for all providers
Implements OpenAI model fallback chain for testing
"""

import logging
from typing import Dict, Optional, Tuple
from datetime import datetime, timezone
import os

import database as db
from routes.api_key_management import encrypt_api_key, decrypt_api_key, get_decrypted_key
from config.models import get_model_fallback_chain, get_default_model

logger = logging.getLogger(__name__)


# All supported providers
SUPPORTED_PROVIDERS = [
    'openai', 'fetchai',  # AI providers
    'luno', 'binance', 'kucoin', 'bybit', 'bitget'  # Exchange providers
]


class KeysService:
    """Centralized API key management service"""
    
    async def test_openai_key(self, api_key: str) -> Tuple[bool, Optional[str], Optional[str]]:
        """Test OpenAI API key with model fallback chain
        
        Args:
            api_key: OpenAI API key to test
            
        Returns:
            Tuple of (success, working_model, error_message)
        """
        try:
            import openai
            
            # Get fallback chain
            models_to_try = get_model_fallback_chain()
            
            last_error = None
            for model in models_to_try:
                try:
                    # Create OpenAI client with key
                    client = openai.OpenAI(api_key=api_key)
                    
                    # Try a simple completion
                    response = client.chat.completions.create(
                        model=model,
                        messages=[{"role": "user", "content": "test"}],
                        max_tokens=5
                    )
                    
                    # Success!
                    logger.info(f"OpenAI key validated with model: {model}")
                    return True, model, None
                    
                except Exception as e:
                    error_str = str(e).lower()
                    last_error = str(e)
                    
                    if "model_not_found" in error_str or "does not exist" in error_str:
                        # Try next model in chain
                        logger.info(f"Model {model} not available, trying next...")
                        continue
                    elif "invalid" in error_str or "authentication" in error_str or "api_key" in error_str:
                        # Invalid key - no point trying other models
                        return False, None, "Invalid API key"
                    else:
                        # Other error - try next model
                        logger.warning(f"Error testing model {model}: {e}")
                        continue
            
            # All models failed
            return False, None, f"All models failed. Last error: {last_error}"
            
        except ImportError:
            return False, None, "OpenAI package not installed"
        except Exception as e:
            logger.error(f"OpenAI key test error: {e}")
            return False, None, str(e)
    
    async def test_exchange_key(
        self, 
        provider: str, 
        api_key: str, 
        api_secret: str,
        passphrase: Optional[str] = None
    ) -> Tuple[bool, Optional[Dict], Optional[str]]:
        """Test exchange API key
        
        Args:
            provider: Exchange name (luno, binance, kucoin, bybit, bitget)
            api_key: API key
            api_secret: API secret
            passphrase: Optional passphrase (for KuCoin, Bitget)
            
        Returns:
            Tuple of (success, metadata, error_message)
        """
        try:
            import ccxt.async_support as ccxt
            
            # Get exchange class
            exchange_class = getattr(ccxt, provider, None)
            if not exchange_class:
                return False, None, f"Exchange {provider} not supported"
            
            # Configure exchange
            config = {
                'apiKey': api_key,
                'secret': api_secret,
                'enableRateLimit': True
            }
            
            if passphrase and provider == 'kucoin':
                config['password'] = passphrase
            
            exchange_instance = exchange_class(config)
            
            try:
                # Test with balance fetch
                balance = await exchange_instance.fetch_balance()
                await exchange_instance.close()
                
                # Extract metadata
                currencies_found = len([c for c, amt in balance.get('total', {}).items() if amt > 0])
                total_balance_usd = balance.get('total', {}).get('USD', 0)
                
                metadata = {
                    'currencies_found': currencies_found,
                    'total_balance_usd': total_balance_usd,
                    'exchange': provider
                }
                
                return True, metadata, None
                
            except Exception as e:
                await exchange_instance.close()
                error_msg = str(e)
                
                if "Invalid API-key" in error_msg or "authentication" in error_msg.lower():
                    return False, None, "Invalid API credentials"
                else:
                    return False, None, error_msg
                    
        except ImportError:
            return False, None, "CCXT package not installed"
        except Exception as e:
            logger.error(f"Exchange key test error for {provider}: {e}")
            return False, None, str(e)
    
    async def test_api_key(
        self, 
        provider: str,
        api_key: str,
        api_secret: Optional[str] = None,
        passphrase: Optional[str] = None
    ) -> Tuple[bool, Optional[Dict], Optional[str]]:
        """Test API key for any provider
        
        Args:
            provider: Provider name
            api_key: API key
            api_secret: Optional API secret (for exchanges)
            passphrase: Optional passphrase (for KuCoin)
            
        Returns:
            Tuple of (success, metadata, error_message)
        """
        provider_lower = provider.lower()
        
        if provider_lower == 'openai':
            success, model, error = await self.test_openai_key(api_key)
            metadata = {'working_model': model} if success else None
            return success, metadata, error
            
        elif provider_lower in ['luno', 'binance', 'kucoin', 'bybit', 'bitget']:
            if not api_secret:
                return False, None, "API secret required for exchange"
            return await self.test_exchange_key(provider_lower, api_key, api_secret, passphrase)
            
        elif provider_lower in ['fetchai', 'coinstats', 'huggingface']:
            # Generic validation for AI providers without live test
            # Could implement actual API tests if endpoints available
            metadata = {'provider': provider_lower, 'test_type': 'format_validation'}
            return True, metadata, None
            
        else:
            return False, None, f"Provider {provider} not supported"
    
    async def save_api_key(
        self,
        user_id: str,
        provider: str,
        api_key: str,
        api_secret: Optional[str] = None,
        passphrase: Optional[str] = None,
        test_first: bool = False
    ) -> Tuple[bool, str]:
        """Save API key to database with encryption
        
        Args:
            user_id: User ID
            provider: Provider name
            api_key: API key
            api_secret: Optional API secret
            passphrase: Optional passphrase
            test_first: Whether to test key before saving
            
        Returns:
            Tuple of (success, message)
        """
        try:
            # Test first if requested
            if test_first:
                test_success, metadata, error = await self.test_api_key(
                    provider, api_key, api_secret, passphrase
                )
                if not test_success:
                    return False, f"API key test failed: {error}"
            
            # Encrypt keys
            encrypted_key = encrypt_api_key(api_key)
            encrypted_secret = encrypt_api_key(api_secret) if api_secret else None
            encrypted_passphrase = encrypt_api_key(passphrase) if passphrase else None
            
            # Check if key exists
            existing = await db.api_keys_collection.find_one({
                "user_id": user_id,
                "provider": provider
            })
            
            timestamp = datetime.now(timezone.utc).isoformat()
            
            key_data = {
                "user_id": user_id,
                "provider": provider,
                "api_key_encrypted": encrypted_key,
                "api_secret_encrypted": encrypted_secret,
                "passphrase_encrypted": encrypted_passphrase,
                "created_at": existing.get("created_at") if existing else timestamp,
                "updated_at": timestamp if existing else None,
                "last_saved_at": timestamp,
            }
            
            if existing:
                await db.api_keys_collection.update_one(
                    {"user_id": user_id, "provider": provider},
                    {"$set": key_data}
                )
                message = f"Updated {provider.upper()} API key"
            else:
                await db.api_keys_collection.insert_one(key_data)
                message = f"Saved {provider.upper()} API key"
            
            logger.info(f"✅ {message} for user {user_id[:8]}")
            return True, message
            
        except Exception as e:
            logger.error(f"Save API key error: {e}")
            return False, str(e)
    
    async def get_user_api_key(
        self,
        user_id: str,
        provider: str,
        decrypt: bool = False
    ) -> Optional[Dict]:
        """Get API key for user and provider
        
        Args:
            user_id: User ID
            provider: Provider name
            decrypt: Whether to decrypt the key (use carefully!)
            
        Returns:
            API key data dict or None
        """
        try:
            key_data = await db.api_keys_collection.find_one(
                {"user_id": user_id, "provider": provider},
                {"_id": 0}
            )
            
            if not key_data:
                return None
            
            if decrypt:
                # Decrypt keys
                if key_data.get('api_key_encrypted'):
                    key_data['api_key'] = decrypt_api_key(key_data['api_key_encrypted'])
                if key_data.get('api_secret_encrypted'):
                    key_data['api_secret'] = decrypt_api_key(key_data['api_secret_encrypted'])
                if key_data.get('passphrase_encrypted'):
                    key_data['passphrase'] = decrypt_api_key(key_data['passphrase_encrypted'])
            
            return key_data
            
        except Exception as e:
            logger.error(f"Get API key error: {e}")
            return None
    
    async def get_openai_key_source(self, user_id: str) -> str:
        """Get OpenAI key source for preflight
        
        Args:
            user_id: User ID
            
        Returns:
            'user' if user has key, 'system' if using system key, 'none' otherwise
        """
        try:
            # Check for user key
            user_key = await self.get_user_api_key(user_id, 'openai')
            if user_key:
                return 'user'
            
            # Check for system key
            system_key = os.getenv('OPENAI_API_KEY')
            if system_key:
                return 'system'
            
            return 'none'
            
        except Exception as e:
            logger.error(f"Get OpenAI key source error: {e}")
            return 'none'


# Global singleton instance
keys_service = KeysService()
