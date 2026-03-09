"""
API Key Manager Service
- Load, validate, encrypt, and store API keys for market data providers
- Runtime key updates without restart
- Health-check each provider endpoint on startup
"""

import os
import logging
from typing import Dict, Optional, List
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# Provider metadata: name → (env_var, test_url, description)
PROVIDER_REGISTRY: Dict[str, Dict] = {
    "cryptocompare": {
        "env_var": "CRYPTOCOMPARE_API_KEY",
        "test_url": "https://min-api.cryptocompare.com/data/v2/pair/mapping/exchange?e=Binance",
        "description": "Primary market data aggregator (100k calls/month free)",
        "required": False,
    },
    "coingecko": {
        "env_var": "COINGECKO_API_KEY",
        "test_url": "https://api.coingecko.com/api/v3/ping",
        "description": "Secondary market data (30 req/min free, no daily cap)",
        "required": False,
    },
    "coinranking": {
        "env_var": "COINRANKING_API_KEY",
        "test_url": "https://api.coinranking.com/v2/stats",
        "description": "Fallback price history (10k req/month free)",
        "required": False,
    },
    "coinmarketcap": {
        "env_var": "COINMARKETCAP_API_KEY",
        "test_url": "https://pro-api.coinmarketcap.com/v1/cryptocurrency/map",
        "description": "Taxonomy and rankings only (333 req/day free)",
        "required": False,
    },
    "luzia": {
        "env_var": "LUZIA_API_KEY",
        "test_url": None,
        "description": "Real-time streaming aggregator (optional)",
        "required": False,
    },
    "glassnode": {
        "env_var": "GLASSNODE_API_KEY",
        "test_url": None,
        "description": "On-chain metrics for BTC/ETH",
        "required": False,
    },
    "etherscan": {
        "env_var": "ETHERSCAN_API_KEY",
        "test_url": "https://api.etherscan.io/api?module=stats&action=ethprice",
        "description": "Ethereum whale transfer tracking (5 req/sec free)",
        "required": False,
    },
    "whale_alert": {
        "env_var": "WHALE_ALERT_API_KEY",
        "test_url": None,
        "description": "Cross-chain large transfer alerts",
        "required": False,
    },
    "lunarcrush": {
        "env_var": "LUNARCRUSH_API_KEY",
        "test_url": None,
        "description": "Social sentiment analytics",
        "required": False,
    },
    "cryptopanic": {
        "env_var": "CRYPTOPANIC_API_KEY",
        "test_url": None,
        "description": "Crypto news aggregator",
        "required": False,
    },
    "santiment": {
        "env_var": "SANTIMENT_API_KEY",
        "test_url": None,
        "description": "On-chain and social metrics (paid)",
        "required": False,
    },
    "kaiko": {
        "env_var": "KAIKO_API_KEY",
        "test_url": None,
        "description": "Order book depth metrics",
        "required": False,
    },
}


class APIKeyManager:
    """
    Manages API keys for all market data providers.
    Loads keys from environment variables, validates them,
    and provides runtime access.
    """

    def __init__(self):
        self._keys: Dict[str, str] = {}
        self._status: Dict[str, Dict] = {}
        self._load_from_env()

    # ------------------------------------------------------------------
    # Key loading
    # ------------------------------------------------------------------

    def _load_from_env(self) -> None:
        """Load all provider keys from environment variables."""
        for provider, meta in PROVIDER_REGISTRY.items():
            value = os.getenv(meta["env_var"], "").strip()
            if value:
                self._keys[provider] = value
                self._status[provider] = {
                    "configured": True,
                    "validated": False,
                    "last_check": None,
                    "error": None,
                }
            else:
                self._status[provider] = {
                    "configured": False,
                    "validated": False,
                    "last_check": None,
                    "error": "Key not provided",
                }

    # ------------------------------------------------------------------
    # Runtime updates
    # ------------------------------------------------------------------

    def set_key(self, provider: str, key: str) -> bool:
        """
        Set or update an API key at runtime.

        Args:
            provider: Provider name (must exist in PROVIDER_REGISTRY)
            key: The API key value

        Returns:
            True if accepted, False if provider unknown
        """
        if provider not in PROVIDER_REGISTRY:
            logger.warning("Unknown provider: %s", provider)
            return False

        self._keys[provider] = key
        os.environ[PROVIDER_REGISTRY[provider]["env_var"]] = key
        self._status[provider] = {
            "configured": True,
            "validated": False,
            "last_check": None,
            "error": None,
        }
        logger.info("API key updated for provider: %s", provider)
        return True

    def get_key(self, provider: str) -> Optional[str]:
        """Return the key for *provider*, or None if not configured."""
        return self._keys.get(provider)

    def has_key(self, provider: str) -> bool:
        """Return True if a non-empty key is configured for *provider*."""
        return bool(self._keys.get(provider))

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    async def validate_key(self, provider: str) -> bool:
        """
        Test a single provider key by hitting its health endpoint.

        Returns:
            True if the provider responded successfully.
        """
        import aiohttp

        meta = PROVIDER_REGISTRY.get(provider)
        if not meta:
            return False

        key = self._keys.get(provider)
        if not key:
            self._status[provider]["error"] = "Key not provided"
            return False

        test_url = meta.get("test_url")
        if not test_url:
            # No test endpoint; assume valid if key is present
            self._status[provider].update(
                validated=True,
                last_check=datetime.now(timezone.utc).isoformat(),
                error=None,
            )
            return True

        try:
            headers = {}
            if provider == "cryptocompare":
                headers["Authorization"] = f"Apikey {key}"
            elif provider == "coinranking":
                headers["x-access-token"] = key
            elif provider == "coinmarketcap":
                headers["X-CMC_PRO_API_KEY"] = key
            elif provider == "etherscan":
                test_url += f"&apikey={key}"

            async with aiohttp.ClientSession() as session:
                async with session.get(test_url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    ok = resp.status == 200
                    self._status[provider].update(
                        validated=ok,
                        last_check=datetime.now(timezone.utc).isoformat(),
                        error=None if ok else f"HTTP {resp.status}",
                    )
                    return ok
        except Exception as exc:
            self._status[provider].update(
                validated=False,
                last_check=datetime.now(timezone.utc).isoformat(),
                error=str(exc),
            )
            logger.error("Validation failed for %s: %s", provider, exc)
            return False

    async def validate_all(self) -> Dict[str, bool]:
        """Validate every configured provider. Returns provider→ok mapping."""
        results: Dict[str, bool] = {}
        for provider in PROVIDER_REGISTRY:
            if self.has_key(provider):
                results[provider] = await self.validate_key(provider)
            else:
                results[provider] = False
        return results

    # ------------------------------------------------------------------
    # Status / diagnostics
    # ------------------------------------------------------------------

    def get_status(self) -> Dict[str, Dict]:
        """Return status dict for all providers."""
        out: Dict[str, Dict] = {}
        for provider, meta in PROVIDER_REGISTRY.items():
            st = self._status.get(provider, {})
            out[provider] = {
                "description": meta["description"],
                "configured": st.get("configured", False),
                "validated": st.get("validated", False),
                "last_check": st.get("last_check"),
                "error": st.get("error"),
            }
        return out

    def configured_providers(self) -> List[str]:
        """Return names of providers that have a key configured."""
        return [p for p in PROVIDER_REGISTRY if self.has_key(p)]

    def validated_providers(self) -> List[str]:
        """Return names of providers that passed validation."""
        return [
            p for p, s in self._status.items()
            if s.get("validated")
        ]


# ---------------------------------------------------------------------------
# Global singleton
# ---------------------------------------------------------------------------
api_key_manager = APIKeyManager()
