"""
Provider Registry - Canonical definition of all supported providers
Defines required fields, validation, testing, and display metadata for each provider
"""

from typing import Dict, List, Optional, Callable, Any
from enum import Enum
import logging
import ccxt.async_support as ccxt
import httpx

logger = logging.getLogger(__name__)


class ProviderType(str, Enum):
    """Provider category"""
    AI = "ai"
    EXCHANGE = "exchange"


class ProviderStatus(str, Enum):
    """Provider key status - canonical values for go-live"""
    NOT_CONFIGURED = "not_configured"
    CONFIGURED_UNTESTED = "configured_untested"  # Canonical status
    CONFIGURED_VALID = "configured_valid"  # Canonical status
    CONFIGURED_INVALID = "configured_invalid"  # Canonical status
    CONFIGURED_RATE_LIMITED = "rate_limited"
    
    # Legacy aliases for backward compatibility (accept on read, normalize on write)
    SAVED_UNTESTED = "saved_untested"
    TEST_OK = "test_ok"
    TEST_FAILED = "test_failed"


class ProviderDefinition:
    """Definition of a single provider"""
    
    def __init__(
        self,
        provider_id: str,
        provider_type: ProviderType,
        display_name: str,
        required_fields: List[str],
        test_method: Callable,
        icon: str = None,
        description: str = None
    ):
        self.provider_id = provider_id
        self.provider_type = provider_type
        self.display_name = display_name
        self.required_fields = required_fields
        self.test_method = test_method
        self.icon = icon or f"{provider_id}.svg"
        self.description = description or f"{display_name} integration"


# Test methods for each provider

async def test_openai(api_key: str, api_secret: Optional[str] = None) -> tuple[bool, Optional[str]]:
    """Test OpenAI API key by making a simple API call"""
    try:
        import openai
        client = openai.AsyncOpenAI(api_key=api_key)
        
        # Simple test: list models
        models = await client.models.list()
        
        if models and len(models.data) > 0:
            return True, None
        else:
            return False, "No models available with this API key"
    except Exception as e:
        error_msg = str(e)
        if "Incorrect API key" in error_msg or "invalid" in error_msg.lower():
            return False, "Invalid API key"
        elif "quota" in error_msg.lower():
            return False, "API quota exceeded"
        else:
            return False, f"Test failed: {error_msg[:100]}"


async def test_flokx(api_key: str, api_secret: Optional[str] = None) -> tuple[bool, Optional[str]]:
    """Test Flokx AI API key"""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                "https://api.flokx.ai/v1/status",
                headers={"Authorization": f"Bearer {api_key}"},
                timeout=10.0
            )
            
            if response.status_code == 200:
                return True, None
            elif response.status_code == 401:
                return False, "Invalid API key"
            else:
                return False, f"API returned status {response.status_code}"
    except httpx.ConnectError:
        # Flokx might not have a status endpoint, accept key if no connection
        logger.warning("Flokx test endpoint not available, accepting key")
        return True, None
    except Exception as e:
        return False, f"Test failed: {str(e)[:100]}"


async def test_fetchai(api_key: str, api_secret: Optional[str] = None) -> tuple[bool, Optional[str]]:
    """Test Fetch.ai API key"""
    try:
        # Fetch.ai uses agent addresses, validate format
        if not api_key.startswith("agent"):
            return False, "API key must start with 'agent'"
        
        if len(api_key) < 20:
            return False, "API key too short"
        
        # Basic format validation passed
        return True, None
    except Exception as e:
        return False, f"Test failed: {str(e)[:100]}"


async def test_luno(api_key: str, api_secret: str) -> tuple[bool, Optional[str]]:
    """Test Luno exchange credentials"""
    try:
        exchange = ccxt.luno({
            'apiKey': api_key,
            'secret': api_secret,
            'enableRateLimit': True
        })
        
        # Test by fetching balance
        balance = await exchange.fetch_balance()
        await exchange.close()
        
        return True, None
    except ccxt.AuthenticationError:
        return False, "Invalid API key or secret"
    except ccxt.PermissionDenied:
        return False, "API key lacks required permissions"
    except Exception as e:
        error_msg = str(e)
        return False, f"Test failed: {error_msg[:100]}"


async def test_binance(api_key: str, api_secret: str) -> tuple[bool, Optional[str]]:
    """Test Binance exchange credentials"""
    try:
        exchange = ccxt.binance({
            'apiKey': api_key,
            'secret': api_secret,
            'enableRateLimit': True
        })
        
        # Test by fetching account status
        balance = await exchange.fetch_balance()
        await exchange.close()
        
        return True, None
    except ccxt.AuthenticationError:
        return False, "Invalid API key or secret"
    except ccxt.PermissionDenied:
        return False, "API key lacks required permissions (need reading permissions)"
    except Exception as e:
        error_msg = str(e)
        return False, f"Test failed: {error_msg[:100]}"


async def test_kucoin(api_key: str, api_secret: str, passphrase: str = None) -> tuple[bool, Optional[str]]:
    """Test KuCoin exchange credentials"""
    try:
        exchange = ccxt.kucoin({
            'apiKey': api_key,
            'secret': api_secret,
            'password': passphrase,
            'enableRateLimit': True
        })
        
        # Test by fetching balance
        balance = await exchange.fetch_balance()
        await exchange.close()
        
        return True, None
    except ccxt.AuthenticationError:
        return False, "Invalid API key, secret, or passphrase"
    except ccxt.PermissionDenied:
        return False, "API key lacks required permissions"
    except Exception as e:
        error_msg = str(e)
        return False, f"Test failed: {error_msg[:100]}"


async def test_bybit(api_key: str, api_secret: str) -> tuple[bool, Optional[str]]:
    """Test Bybit exchange credentials"""
    try:
        exchange = ccxt.bybit({
            'apiKey': api_key,
            'secret': api_secret,
            'enableRateLimit': True
        })
        
        # Test by fetching balance
        balance = await exchange.fetch_balance()
        await exchange.close()
        
        return True, None
    except ccxt.AuthenticationError:
        return False, "Invalid API key or secret"
    except ccxt.PermissionDenied:
        return False, "API key lacks required permissions"
    except Exception as e:
        error_msg = str(e)
        return False, f"Test failed: {error_msg[:100]}"


async def test_bitget(api_key: str, api_secret: str, passphrase: str = None) -> tuple[bool, Optional[str]]:
    """Test Bitget exchange credentials"""
    try:
        exchange = ccxt.bitget({
            'apiKey': api_key,
            'secret': api_secret,
            'password': passphrase,
            'enableRateLimit': True
        })
        
        # Test by fetching balance
        balance = await exchange.fetch_balance()
        await exchange.close()
        
        return True, None
    except ccxt.AuthenticationError:
        return False, "Invalid API key, secret, or passphrase"
    except ccxt.PermissionDenied:
        return False, "API key lacks required permissions"
    except Exception as e:
        error_msg = str(e)
        return False, f"Test failed: {error_msg[:100]}"


async def test_kraken(api_key: str, api_secret: str) -> tuple[bool, Optional[str]]:
    """Test Kraken exchange credentials"""
    try:
        exchange = ccxt.kraken({
            'apiKey': api_key,
            'secret': api_secret,
            'enableRateLimit': True
        })
        
        # Test by fetching balance
        balance = await exchange.fetch_balance()
        await exchange.close()
        
        return True, None
    except ccxt.AuthenticationError:
        return False, "Invalid API key or secret"
    except ccxt.PermissionDenied:
        return False, "API key lacks required permissions"
    except Exception as e:
        error_msg = str(e)
        return False, f"Test failed: {error_msg[:100]}"


async def test_gate(api_key: str, api_secret: str) -> tuple[bool, Optional[str]]:
    """Test Gate.io exchange credentials"""
    try:
        exchange = ccxt.gateio({  # CCXT uses 'gateio' as the ID
            'apiKey': api_key,
            'secret': api_secret,
            'enableRateLimit': True
        })
        
        # Test by fetching balance
        balance = await exchange.fetch_balance()
        await exchange.close()
        
        return True, None
    except ccxt.AuthenticationError:
        return False, "Invalid API key or secret"
    except ccxt.PermissionDenied:
        return False, "API key lacks required permissions"
    except Exception as e:
        error_msg = str(e)
        return False, f"Test failed: {error_msg[:100]}"


# Provider definitions

PROVIDERS: Dict[str, ProviderDefinition] = {
    # AI Providers
    "openai": ProviderDefinition(
        provider_id="openai",
        provider_type=ProviderType.AI,
        display_name="OpenAI",
        required_fields=["api_key"],
        test_method=test_openai,
        icon="openai.svg",
        description="OpenAI GPT models for AI trading intelligence"
    ),
    "flokx": ProviderDefinition(
        provider_id="flokx",
        provider_type=ProviderType.AI,
        display_name="Flokx AI",
        required_fields=["api_key"],
        test_method=test_flokx,
        icon="flokx.svg",
        description="Flokx AI for advanced market analysis"
    ),
    "fetchai": ProviderDefinition(
        provider_id="fetchai",
        provider_type=ProviderType.AI,
        display_name="Fetch.ai",
        required_fields=["api_key"],
        test_method=test_fetchai,
        icon="fetchai.svg",
        description="Fetch.ai agent network integration"
    ),
    
    # Exchange Providers
    "luno": ProviderDefinition(
        provider_id="luno",
        provider_type=ProviderType.EXCHANGE,
        display_name="LUNO",
        required_fields=["api_key", "api_secret"],
        test_method=test_luno,
        icon="luno.svg",
        description="LUNO cryptocurrency exchange"
    ),
    "binance": ProviderDefinition(
        provider_id="binance",
        provider_type=ProviderType.EXCHANGE,
        display_name="Binance",
        required_fields=["api_key", "api_secret"],
        test_method=test_binance,
        icon="binance.svg",
        description="Binance global cryptocurrency exchange"
    ),
    "kucoin": ProviderDefinition(
        provider_id="kucoin",
        provider_type=ProviderType.EXCHANGE,
        display_name="KuCoin",
        required_fields=["api_key", "api_secret", "passphrase"],
        test_method=test_kucoin,
        icon="kucoin.svg",
        description="KuCoin cryptocurrency exchange"
    ),
    "bybit": ProviderDefinition(
        provider_id="bybit",
        provider_type=ProviderType.EXCHANGE,
        display_name="Bybit",
        required_fields=["api_key", "api_secret"],
        test_method=test_bybit,
        icon="bybit.svg",
        description="Bybit global derivatives and cryptocurrency exchange"
    ),
    "bitget": ProviderDefinition(
        provider_id="bitget",
        provider_type=ProviderType.EXCHANGE,
        display_name="Bitget",
        required_fields=["api_key", "api_secret", "passphrase"],
        test_method=test_bitget,
        icon="bitget.svg",
        description="Bitget global cryptocurrency and derivatives exchange"
    ),
    "kraken": ProviderDefinition(
        provider_id="kraken",
        provider_type=ProviderType.EXCHANGE,
        display_name="Kraken",
        required_fields=["api_key", "api_secret"],
        test_method=test_kraken,
        icon="kraken.svg",
        description="Kraken US-based cryptocurrency exchange"
    ),
    "gate": ProviderDefinition(
        provider_id="gate",
        provider_type=ProviderType.EXCHANGE,
        display_name="Gate.io",
        required_fields=["api_key", "api_secret"],
        test_method=test_gate,
        icon="gateio.svg",
        description="Gate.io global cryptocurrency exchange"
    ),
}


def get_provider(provider_id: str) -> Optional[ProviderDefinition]:
    """Get provider definition by ID"""
    return PROVIDERS.get(provider_id)


def list_providers_ids() -> List[str]:
    """List all provider IDs"""
    return list(PROVIDERS.keys())


def list_providers() -> List[Dict[str, Any]]:
    """List all providers with metadata"""
    return [
        {
            "id": provider_id,
            "type": provider.provider_type.value,
            "display_name": provider.display_name,
            "required_fields": provider.required_fields,
            "icon": provider.icon,
            "description": provider.description
        }
        for provider_id, provider in PROVIDERS.items()
    ]


def list_providers_by_type(provider_type: ProviderType) -> List[Dict[str, Any]]:
    """List providers filtered by type"""
    return [
        {
            "id": provider_id,
            "type": provider.provider_type.value,
            "display_name": provider.display_name,
            "required_fields": provider.required_fields,
            "icon": provider.icon,
            "description": provider.description
        }
        for provider_id, provider in PROVIDERS.items()
        if provider.provider_type == provider_type
    ]


async def test_provider(provider_id: str, credentials: Dict[str, str]) -> tuple[bool, Optional[str]]:
    """Test provider credentials
    
    Args:
        provider_id: Provider identifier
        credentials: Dict with api_key, api_secret, passphrase, etc.
        
    Returns:
        Tuple of (success: bool, error_message: Optional[str])
    """
    provider = get_provider(provider_id)
    
    if not provider:
        return False, f"Unknown provider: {provider_id}"
    
    # Extract credentials based on required fields
    api_key = credentials.get("api_key")
    api_secret = credentials.get("api_secret")
    passphrase = credentials.get("passphrase")
    
    if not api_key:
        return False, "API key is required"
    
    # Check required fields
    for field in provider.required_fields:
        if field not in credentials or not credentials[field]:
            return False, f"Required field missing: {field}"
    
    # Call provider test method
    try:
        if provider_id in ["kucoin", "bitget"]:
            # Both KuCoin and Bitget require passphrase
            return await provider.test_method(api_key, api_secret, passphrase)
        elif api_secret:
            return await provider.test_method(api_key, api_secret)
        else:
            return await provider.test_method(api_key)
    except Exception as e:
        logger.error(f"Provider test error for {provider_id}: {e}")
        return False, f"Test error: {str(e)[:100]}"
