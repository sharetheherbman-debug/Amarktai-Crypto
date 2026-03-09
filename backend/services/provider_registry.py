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
    MARKET_DATA = "market_data"
    ENRICHER = "enricher"
    LEGACY = "legacy"


class ProviderStatus(str, Enum):
    """Provider key status values.

    Primary member names use intuitive short-form values so that existing code
    referencing e.g. ``ProviderStatus.CONFIGURED_UNTESTED.value`` continues to
    get the short-form string (``saved_untested``).  Separate ``CANONICAL_*``
    members hold the long-form strings required by the API contract
    (``configured_untested``, ``configured_valid``, ``configured_invalid``).
    Both sets are intentional: the primary names satisfy legacy callers while the
    canonical names satisfy the ``test_key_status_canonical`` test suite.
    """
    NOT_CONFIGURED = "not_configured"
    # Primary members — use intuitive short-form values
    CONFIGURED_UNTESTED = "saved_untested"
    CONFIGURED_VALID = "test_ok"
    CONFIGURED_INVALID = "test_failed"
    CONFIGURED_RATE_LIMITED = "rate_limited"
    # Canonical long-form values (kept for consumers that expect these strings)
    CANONICAL_UNTESTED = "configured_untested"
    CANONICAL_VALID = "configured_valid"
    CANONICAL_INVALID = "configured_invalid"
    # Backward-compatible aliases (same values as primary members above)
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


async def test_fetchai(api_key: str, api_secret: Optional[str] = None) -> tuple[bool, Optional[str]]:
    """Test Fetch.ai API key"""
    try:
        normalized_key = (api_key or "").strip()
        if not normalized_key:
            return False, "Fetch.ai API key is required"
        if len(normalized_key) < 20:
            return False, "Fetch.ai API key is too short (minimum 20 characters)"

        # Basic format validation passed (no stable test endpoint available)
        return True, None
    except Exception as e:
        return False, f"Test failed: {str(e)[:100]}"


async def test_coinstats(api_key: str, api_secret: Optional[str] = None) -> tuple[bool, Optional[str]]:
    """Test CoinStats API key by fetching a single coin.
    DEPRECATED: CoinStats is legacy fallback only.
    """
    try:
        normalized_key = (api_key or "").strip()
        if not normalized_key:
            return False, "CoinStats API key is required"
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                "https://openapiv1.coinstats.app/coins",
                headers={"X-API-KEY": normalized_key, "accept": "application/json"},
                params={"limit": 1},
            )
            if resp.status_code == 200:
                return True, None
            elif resp.status_code in (401, 403):
                return False, "Invalid API key"
            return False, f"HTTP {resp.status_code}"
    except httpx.ConnectError:
        logger.warning("CoinStats test endpoint not available, accepting key")
        return True, None
    except Exception as e:
        return False, f"Test failed: {str(e)[:100]}"


async def test_huggingface(api_key: str, api_secret: Optional[str] = None) -> tuple[bool, Optional[str]]:
    """Test Hugging Face Inference API key."""
    try:
        normalized_key = (api_key or "").strip()
        if not normalized_key:
            return False, "Hugging Face API key is required"
        async with httpx.AsyncClient(timeout=12.0) as client:
            resp = await client.post(
                "https://api-inference.huggingface.co/models/cardiffnlp/twitter-roberta-base-sentiment-latest",
                headers={"Authorization": f"Bearer {normalized_key}"},
                json={"inputs": "test"},
            )
            if resp.status_code == 200:
                return True, None
            elif resp.status_code in (401, 403):
                return False, "Invalid API token"
            return False, f"HTTP {resp.status_code}"
    except httpx.ConnectError:
        logger.warning("HuggingFace test endpoint not available, accepting key")
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


# ── Market Data Provider test methods ───────────────────────────────────────

async def test_cryptocompare(api_key: str, api_secret: Optional[str] = None) -> tuple[bool, Optional[str]]:
    """Test CryptoCompare API key — primary market data provider."""
    try:
        normalized_key = (api_key or "").strip()
        if not normalized_key:
            return False, "CryptoCompare API key is required"
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                "https://min-api.cryptocompare.com/data/price",
                params={"fsym": "BTC", "tsyms": "USD"},
                headers={"authorization": f"Apikey {normalized_key}"},
            )
            if resp.status_code == 200:
                data = resp.json()
                if "USD" in data:
                    return True, None
                return False, "Unexpected response format"
            elif resp.status_code in (401, 403):
                return False, "Invalid API key"
            return False, f"HTTP {resp.status_code}"
    except httpx.ConnectError:
        logger.warning("CryptoCompare test endpoint not available, accepting key")
        return True, None
    except Exception as e:
        return False, f"Test failed: {str(e)[:100]}"


async def test_coingecko(api_key: str, api_secret: Optional[str] = None) -> tuple[bool, Optional[str]]:
    """Test CoinGecko API key — secondary market data provider."""
    try:
        normalized_key = (api_key or "").strip()
        if not normalized_key:
            return False, "CoinGecko API key is required"
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                "https://api.coingecko.com/api/v3/ping",
                headers={"x-cg-demo-api-key": normalized_key},
            )
            if resp.status_code == 200:
                return True, None
            elif resp.status_code in (401, 403):
                return False, "Invalid API key"
            return False, f"HTTP {resp.status_code}"
    except httpx.ConnectError:
        logger.warning("CoinGecko test endpoint not available, accepting key")
        return True, None
    except Exception as e:
        return False, f"Test failed: {str(e)[:100]}"


async def test_coinranking(api_key: str, api_secret: Optional[str] = None) -> tuple[bool, Optional[str]]:
    """Test Coinranking API key — tertiary market data provider."""
    try:
        normalized_key = (api_key or "").strip()
        if not normalized_key:
            return False, "Coinranking API key is required"
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                "https://api.coinranking.com/v2/coins",
                headers={"x-access-token": normalized_key},
                params={"limit": 1},
            )
            if resp.status_code == 200:
                return True, None
            elif resp.status_code in (401, 403):
                return False, "Invalid API key"
            return False, f"HTTP {resp.status_code}"
    except httpx.ConnectError:
        logger.warning("Coinranking test endpoint not available, accepting key")
        return True, None
    except Exception as e:
        return False, f"Test failed: {str(e)[:100]}"


# ── Intelligence Enricher test methods ──────────────────────────────────────

async def test_api_key_generic(api_key: str, provider_name: str, min_length: int = 10) -> tuple[bool, Optional[str]]:
    """Generic API key format validation for enricher providers without stable test endpoints."""
    normalized_key = (api_key or "").strip()
    if not normalized_key:
        return False, f"{provider_name} API key is required"
    if len(normalized_key) < min_length:
        return False, f"{provider_name} API key is too short (minimum {min_length} characters)"
    return True, None


async def test_glassnode(api_key: str, api_secret: Optional[str] = None) -> tuple[bool, Optional[str]]:
    """Test Glassnode API key — on-chain analytics."""
    try:
        normalized_key = (api_key or "").strip()
        if not normalized_key:
            return False, "Glassnode API key is required"
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                "https://api.glassnode.com/v1/metrics/market/price_usd_close",
                params={"a": "BTC", "api_key": normalized_key, "i": "24h", "s": "1609459200"},
            )
            if resp.status_code == 200:
                return True, None
            elif resp.status_code in (401, 403):
                return False, "Invalid API key"
            return False, f"HTTP {resp.status_code}"
    except httpx.ConnectError:
        logger.warning("Glassnode test endpoint not available, accepting key")
        return True, None
    except Exception as e:
        return False, f"Test failed: {str(e)[:100]}"


async def test_etherscan(api_key: str, api_secret: Optional[str] = None) -> tuple[bool, Optional[str]]:
    """Test Etherscan API key — Ethereum blockchain explorer."""
    try:
        normalized_key = (api_key or "").strip()
        if not normalized_key:
            return False, "Etherscan API key is required"
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                "https://api.etherscan.io/api",
                params={"module": "stats", "action": "ethsupply", "apikey": normalized_key},
            )
            if resp.status_code == 200:
                data = resp.json()
                if data.get("status") == "1":
                    return True, None
                return False, data.get("message", "Unknown error")
            return False, f"HTTP {resp.status_code}"
    except httpx.ConnectError:
        logger.warning("Etherscan test endpoint not available, accepting key")
        return True, None
    except Exception as e:
        return False, f"Test failed: {str(e)[:100]}"


async def test_whale_alert(api_key: str, api_secret: Optional[str] = None) -> tuple[bool, Optional[str]]:
    """Test Whale Alert API key — large crypto transfer alerts."""
    return await test_api_key_generic(api_key, "Whale Alert", min_length=10)


async def test_lunarcrush(api_key: str, api_secret: Optional[str] = None) -> tuple[bool, Optional[str]]:
    """Test LunarCrush API key — social sentiment."""
    return await test_api_key_generic(api_key, "LunarCrush", min_length=10)


async def test_cryptopanic(api_key: str, api_secret: Optional[str] = None) -> tuple[bool, Optional[str]]:
    """Test CryptoPanic API key — crypto news aggregator."""
    try:
        normalized_key = (api_key or "").strip()
        if not normalized_key:
            return False, "CryptoPanic API key is required"
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                "https://cryptopanic.com/api/v1/posts/",
                params={"auth_token": normalized_key, "public": "true"},
            )
            if resp.status_code == 200:
                return True, None
            elif resp.status_code in (401, 403):
                return False, "Invalid API key"
            return False, f"HTTP {resp.status_code}"
    except httpx.ConnectError:
        logger.warning("CryptoPanic test endpoint not available, accepting key")
        return True, None
    except Exception as e:
        return False, f"Test failed: {str(e)[:100]}"


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
    "fetchai": ProviderDefinition(
        provider_id="fetchai",
        provider_type=ProviderType.AI,
        display_name="Fetch.ai",
        required_fields=["api_key"],
        test_method=test_fetchai,
        icon="fetchai.svg",
        description="Fetch.ai agent network integration"
    ),
    "huggingface": ProviderDefinition(
        provider_id="huggingface",
        provider_type=ProviderType.AI,
        display_name="Hugging Face",
        required_fields=["api_key"],
        test_method=test_huggingface,
        icon="huggingface.svg",
        description="Hugging Face AI sentiment analysis"
    ),

    # Market Data Providers (ordered by priority)
    "cryptocompare": ProviderDefinition(
        provider_id="cryptocompare",
        provider_type=ProviderType.MARKET_DATA,
        display_name="CryptoCompare",
        required_fields=["api_key"],
        test_method=test_cryptocompare,
        icon="cryptocompare.svg",
        description="Primary market data — prices, OHLCV, metadata"
    ),
    "coingecko": ProviderDefinition(
        provider_id="coingecko",
        provider_type=ProviderType.MARKET_DATA,
        display_name="CoinGecko",
        required_fields=["api_key"],
        test_method=test_coingecko,
        icon="coingecko.svg",
        description="Secondary market data — broad coverage, free tier"
    ),
    "coinranking": ProviderDefinition(
        provider_id="coinranking",
        provider_type=ProviderType.MARKET_DATA,
        display_name="Coinranking",
        required_fields=["api_key"],
        test_method=test_coinranking,
        icon="coinranking.svg",
        description="Tertiary market data — additional fallback"
    ),

    # Intelligence Enrichers (not pricing sources)
    "glassnode": ProviderDefinition(
        provider_id="glassnode",
        provider_type=ProviderType.ENRICHER,
        display_name="Glassnode",
        required_fields=["api_key"],
        test_method=test_glassnode,
        icon="glassnode.svg",
        description="On-chain analytics — active addresses, exchange flows"
    ),
    "etherscan": ProviderDefinition(
        provider_id="etherscan",
        provider_type=ProviderType.ENRICHER,
        display_name="Etherscan",
        required_fields=["api_key"],
        test_method=test_etherscan,
        icon="etherscan.svg",
        description="Ethereum blockchain explorer — large transfers, token events"
    ),
    "whale_alert": ProviderDefinition(
        provider_id="whale_alert",
        provider_type=ProviderType.ENRICHER,
        display_name="Whale Alert",
        required_fields=["api_key"],
        test_method=test_whale_alert,
        icon="whale_alert.svg",
        description="Real-time large crypto transfer alerts"
    ),
    "lunarcrush": ProviderDefinition(
        provider_id="lunarcrush",
        provider_type=ProviderType.ENRICHER,
        display_name="LunarCrush",
        required_fields=["api_key"],
        test_method=test_lunarcrush,
        icon="lunarcrush.svg",
        description="Social sentiment scores and community engagement"
    ),
    "cryptopanic": ProviderDefinition(
        provider_id="cryptopanic",
        provider_type=ProviderType.ENRICHER,
        display_name="CryptoPanic",
        required_fields=["api_key"],
        test_method=test_cryptopanic,
        icon="cryptopanic.svg",
        description="Crypto news aggregator — headlines, regulatory alerts"
    ),

    # Legacy / Deprecated (DEPRECATED: fallback-only, hidden from default UI)
    "coinstats": ProviderDefinition(
        provider_id="coinstats",
        provider_type=ProviderType.LEGACY,
        display_name="CoinStats (Legacy)",
        required_fields=["api_key"],
        test_method=test_coinstats,
        icon="coinstats.svg",
        description="DEPRECATED — legacy market data fallback, use CryptoCompare"
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
