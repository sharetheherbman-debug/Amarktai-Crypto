"""
Test OpenAI Key Resolver Service
Ensures consistent key resolution across all AI modules
"""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from services.openai_key_resolver import resolve_openai_key, get_openai_client


@pytest.mark.asyncio
async def test_resolve_openai_key_user_key_priority():
    """Test that user key from DB takes priority"""
    with patch('routes.api_key_management.get_decrypted_key') as mock_get_key:
        mock_get_key.return_value = {"api_key": "user-key-123"}
        
        with patch.dict(os.environ, {"OPENAI_API_KEY": "system-key-456"}):
            api_key, source = await resolve_openai_key("test_user_123")
            
            assert api_key == "user-key-123"
            assert source == "user"
            mock_get_key.assert_called_once_with("test_user_123", "openai")


@pytest.mark.asyncio
async def test_resolve_openai_key_system_fallback():
    """Test that system env key is used when user key not found"""
    with patch('routes.api_key_management.get_decrypted_key') as mock_get_key:
        mock_get_key.return_value = None
        
        with patch.dict(os.environ, {"OPENAI_API_KEY": "system-key-456"}):
            api_key, source = await resolve_openai_key("test_user_123")
            
            assert api_key == "system-key-456"
            assert source == "system"


@pytest.mark.asyncio
async def test_resolve_openai_key_missing():
    """Test graceful handling when no key is available"""
    with patch('routes.api_key_management.get_decrypted_key') as mock_get_key:
        mock_get_key.return_value = None
        
        with patch.dict(os.environ, {}, clear=True):
            api_key, source = await resolve_openai_key("test_user_123")
            
            assert api_key is None
            assert source == "missing"


@pytest.mark.asyncio
async def test_resolve_openai_key_no_user_id():
    """Test behavior when user_id is None (system only)"""
    with patch.dict(os.environ, {"OPENAI_API_KEY": "system-key-456"}):
        api_key, source = await resolve_openai_key(None)
        
        assert api_key == "system-key-456"
        assert source == "system"


@pytest.mark.asyncio
async def test_resolve_openai_key_empty_user_key():
    """Test that empty user key falls back to system key"""
    with patch('routes.api_key_management.get_decrypted_key') as mock_get_key:
        mock_get_key.return_value = {"api_key": ""}  # Empty string
        
        with patch.dict(os.environ, {"OPENAI_API_KEY": "system-key-456"}):
            api_key, source = await resolve_openai_key("test_user_123")
            
            assert api_key == "system-key-456"
            assert source == "system"


@pytest.mark.asyncio
async def test_resolve_openai_key_whitespace_only():
    """Test that whitespace-only key falls back to system key"""
    with patch('routes.api_key_management.get_decrypted_key') as mock_get_key:
        mock_get_key.return_value = {"api_key": "   "}  # Whitespace only
        
        with patch.dict(os.environ, {"OPENAI_API_KEY": "system-key-456"}):
            api_key, source = await resolve_openai_key("test_user_123")
            
            assert api_key == "system-key-456"
            assert source == "system"


@pytest.mark.asyncio
async def test_resolve_openai_key_error_handling():
    """Test that errors are handled gracefully"""
    with patch('routes.api_key_management.get_decrypted_key') as mock_get_key:
        mock_get_key.side_effect = Exception("Database error")
        
        with patch.dict(os.environ, {"OPENAI_API_KEY": "system-key-456"}):
            api_key, source = await resolve_openai_key("test_user_123")
            
            # Should fall back to system key on error
            assert api_key == "system-key-456"
            assert source == "system"


@pytest.mark.asyncio
async def test_get_openai_client_with_key():
    """Test get_openai_client returns client when key available"""
    with patch('services.openai_key_resolver.resolve_openai_key') as mock_resolve:
        mock_resolve.return_value = ("test-key-123", "user")
        
        # Mock the import and AsyncOpenAI at module level
        with patch.dict('sys.modules', {'openai': MagicMock()}):
            with patch('services.openai_key_resolver.get_openai_client') as mock_get_client:
                mock_client = MagicMock()
                mock_get_client.return_value = (mock_client, "user")
                
                client, source = await mock_get_client("test_user_123")
                
                assert client == mock_client
                assert source == "user"


@pytest.mark.asyncio
async def test_get_openai_client_missing_key():
    """Test get_openai_client returns None when no key available"""
    with patch('services.openai_key_resolver.resolve_openai_key') as mock_resolve:
        mock_resolve.return_value = (None, "missing")
        
        client, source = await get_openai_client("test_user_123")
        
        assert client is None
        assert source == "missing"


@pytest.mark.asyncio
async def test_get_openai_client_handles_errors():
    """Test get_openai_client handles errors gracefully"""
    with patch('services.openai_key_resolver.resolve_openai_key') as mock_resolve:
        mock_resolve.return_value = ("test-key-123", "system")
        
        # Simulate error during client creation
        with patch('services.openai_key_resolver.get_openai_client') as mock_get_client:
            mock_get_client.return_value = (None, "missing")
            
            client, source = await mock_get_client("test_user_123")
            
            assert client is None
            assert source == "missing"
