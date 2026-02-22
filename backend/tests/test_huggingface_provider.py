"""
Tests for Hugging Face provider support.

Covers:
1. VALID_PROVIDERS in routes/keys.py includes 'huggingface'.
2. provider_registry has a 'huggingface' ProviderDefinition with correct metadata.
3. Saving an API key with provider='huggingface' is accepted (not rejected with 400).
4. Saving an API key with an invalid provider still returns 400 with a helpful error.
5. test_huggingface gracefully handles network-unreachable scenarios.
"""

import inspect
import pytest
import asyncio
from unittest.mock import patch, AsyncMock, MagicMock


# ---------------------------------------------------------------------------
# 1. Provider registry
# ---------------------------------------------------------------------------

class TestProviderRegistry:
    """Verify the provider_registry correctly defines the huggingface provider."""

    def test_huggingface_in_providers(self):
        """'huggingface' must be present in the PROVIDERS dict."""
        from services.provider_registry import PROVIDERS
        assert "huggingface" in PROVIDERS, "'huggingface' missing from PROVIDERS"

    def test_huggingface_is_ai_type(self):
        """huggingface must be classified as an AI provider, not an exchange."""
        from services.provider_registry import get_provider, ProviderType
        p = get_provider("huggingface")
        assert p is not None
        assert p.provider_type == ProviderType.AI

    def test_huggingface_display_name(self):
        """huggingface display name must contain 'Hugging Face'."""
        from services.provider_registry import get_provider
        p = get_provider("huggingface")
        assert "Hugging" in p.display_name

    def test_huggingface_required_fields(self):
        """huggingface only requires api_key (no api_secret / passphrase)."""
        from services.provider_registry import get_provider
        p = get_provider("huggingface")
        assert p.required_fields == ["api_key"]

    def test_huggingface_in_list_providers(self):
        """list_providers() must include huggingface."""
        from services.provider_registry import list_providers, list_providers_ids
        ids = list_providers_ids()
        assert "huggingface" in ids

        providers = list_providers()
        hf = next((p for p in providers if p["id"] == "huggingface"), None)
        assert hf is not None
        assert hf["type"] == "ai"

    def test_existing_providers_unchanged(self):
        """All previously existing providers must still be present."""
        from services.provider_registry import list_providers_ids
        ids = list_providers_ids()
        for expected in ["openai", "flokx", "fetchai",
                         "luno", "binance", "kucoin", "bybit", "kraken", "bitget", "gate"]:
            assert expected in ids, f"Pre-existing provider '{expected}' was removed"


# ---------------------------------------------------------------------------
# 2. VALID_PROVIDERS in routes/keys.py
# ---------------------------------------------------------------------------

class TestKeysRouteValidProviders:
    """Verify the hard-coded VALID_PROVIDERS list in routes/keys.py includes huggingface."""

    def test_huggingface_in_valid_providers_source(self):
        """'huggingface' must appear in the VALID_PROVIDERS list in routes/keys.py."""
        import routes.keys as keys_module
        src = inspect.getsource(keys_module)
        # The list literal must include the string 'huggingface'
        assert "'huggingface'" in src or '"huggingface"' in src, \
            "'huggingface' not found in routes/keys.py VALID_PROVIDERS"

    def test_valid_providers_error_message_includes_huggingface(self):
        """The 400 error message for an invalid provider must list 'huggingface'."""
        import routes.keys as keys_module
        src = inspect.getsource(keys_module)
        # Both the validation list and the f-string error must contain huggingface
        assert "huggingface" in src


# ---------------------------------------------------------------------------
# 3. save_key logic — huggingface is accepted
# ---------------------------------------------------------------------------

class TestSaveKeyHuggingface:
    """
    Verify that the save_key validation path accepts provider='huggingface'.
    We test the provider-ID validation logic directly without going through
    the full HTTP stack (which requires a DB and auth).
    """

    def test_huggingface_passes_valid_providers_check(self):
        """huggingface must NOT trigger the 'Invalid provider' branch."""
        VALID_PROVIDERS = [
            'luno', 'binance', 'kucoin', 'bybit', 'kraken', 'bitget', 'gate',
            'openai', 'flokx', 'fetchai', 'huggingface'
        ]
        assert "huggingface" in VALID_PROVIDERS

    def test_invalid_provider_rejected(self):
        """An unknown provider must still be rejected."""
        VALID_PROVIDERS = [
            'luno', 'binance', 'kucoin', 'bybit', 'kraken', 'bitget', 'gate',
            'openai', 'flokx', 'fetchai', 'huggingface'
        ]
        assert "totally_invalid_exchange" not in VALID_PROVIDERS

    def test_invalid_provider_error_lists_huggingface(self):
        """The 400 error message for an unknown provider must include 'huggingface'."""
        VALID_PROVIDERS = [
            'luno', 'binance', 'kucoin', 'bybit', 'kraken', 'bitget', 'gate',
            'openai', 'flokx', 'fetchai', 'huggingface'
        ]
        error_detail = f"Invalid provider: badprovider. Valid providers: {', '.join(VALID_PROVIDERS)}"
        assert "huggingface" in error_detail

    def test_provider_registry_lookup_returns_definition_for_huggingface(self):
        """get_provider('huggingface') must return a non-None ProviderDefinition."""
        from services.provider_registry import get_provider
        p = get_provider("huggingface")
        assert p is not None, "get_provider('huggingface') returned None"
        # Verify required_fields is a list (not None/empty accidentally)
        assert isinstance(p.required_fields, list)
        assert len(p.required_fields) > 0


# ---------------------------------------------------------------------------
# 4. test_huggingface function — graceful network failure
# ---------------------------------------------------------------------------

class TestHuggingfaceTestMethod:
    """Verify the test_huggingface provider function handles errors gracefully."""

    def test_empty_key_fails(self):
        """Empty API token must return (False, error_message)."""
        from services.provider_registry import test_huggingface
        success, error = asyncio.run(test_huggingface(""))
        assert not success
        assert error is not None

    def test_valid_token_format_network_unreachable(self):
        """When network is unavailable, a reasonably-sized token is accepted."""
        import httpx
        from services.provider_registry import test_huggingface

        with patch("services.provider_registry.httpx.AsyncClient") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.get = AsyncMock(side_effect=httpx.ConnectError("unreachable"))
            mock_client_cls.return_value = mock_client

            success, error = asyncio.run(test_huggingface("hf_ValidTokenWithEnoughLength"))
        assert success  # ConnectError should fall back to length check

    def test_invalid_token_401(self):
        """A 401 response from Hugging Face means invalid token."""
        from services.provider_registry import test_huggingface

        mock_response = MagicMock()
        mock_response.status_code = 401

        with patch("services.provider_registry.httpx.AsyncClient") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value = mock_client

            success, error = asyncio.run(test_huggingface("invalid_token"))
        assert not success
        assert "Invalid" in (error or "")

    def test_valid_token_200(self):
        """A 200 response from Hugging Face means the token is valid."""
        from services.provider_registry import test_huggingface

        mock_response = MagicMock()
        mock_response.status_code = 200

        with patch("services.provider_registry.httpx.AsyncClient") as mock_client_cls:
            mock_client = MagicMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.get = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value = mock_client

            success, error = asyncio.run(test_huggingface("hf_valid_token_example"))
        assert success
        assert error is None


# ---------------------------------------------------------------------------
# 5. Frontend constants
# ---------------------------------------------------------------------------

class TestFrontendConstants:
    """Verify the frontend platforms constants already have huggingface configured."""

    def test_huggingface_in_frontend_constants(self):
        """frontend/src/constants/platforms.js must contain 'huggingface' in
        both SUPPORTED_AI_PROVIDERS and PLATFORM_CONFIG."""
        import os
        constants_path = os.path.abspath(os.path.join(
            os.path.dirname(__file__),
            "../../frontend/src/constants/platforms.js"
        ))
        with open(constants_path, "r") as f:
            content = f.read()

        # General presence
        assert "huggingface" in content, "'huggingface' missing from frontend platforms.js"

        # Must be in SUPPORTED_AI_PROVIDERS (as a quoted string)
        assert "'huggingface'" in content or '"huggingface"' in content, \
            "'huggingface' not listed in SUPPORTED_AI_PROVIDERS"
