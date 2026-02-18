"""
Tests for admin unlock password functionality
"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import Mock, patch, AsyncMock
import os


@pytest.fixture
def mock_db():
    """Mock database collections"""
    with patch('routes.admin_endpoints.db') as mock:
        mock.users_collection = AsyncMock()
        mock.audit_logs_collection = None
        yield mock


@pytest.fixture
def mock_audit_logger():
    """Mock audit logger"""
    with patch('routes.admin_endpoints.audit_logger') as mock:
        mock.log_event = AsyncMock()
        yield mock


@pytest.mark.asyncio
async def test_admin_unlock_with_default_password(mock_db, mock_audit_logger):
    """Test admin unlock with default password when ADMIN_PASSWORD not set"""
    from routes.admin_endpoints import unlock_admin_panel, AdminUnlockRequest
    from auth import create_access_token
    
    # Setup
    user_id = "test_user_123"
    mock_db.users_collection.update_one = AsyncMock()
    
    # Clear environment variable to test default
    original_password = os.environ.get('ADMIN_PASSWORD')
    if 'ADMIN_PASSWORD' in os.environ:
        del os.environ['ADMIN_PASSWORD']
    
    try:
        # Test with correct default password (case-insensitive)
        request = AdminUnlockRequest(password="Ashmor12@")
        result = await unlock_admin_panel(request, current_user_id=user_id)
        
        assert result["success"] is True
        assert result["message"] == "Admin panel unlocked"
        assert "admin_token" in result
        assert result["user"]["is_admin"] is True
        
        # Verify user was updated
        mock_db.users_collection.update_one.assert_called_once()
        
    finally:
        # Restore original environment
        if original_password:
            os.environ['ADMIN_PASSWORD'] = original_password


@pytest.mark.asyncio
async def test_admin_unlock_case_insensitive(mock_db, mock_audit_logger):
    """Test admin unlock is case-insensitive"""
    from routes.admin_endpoints import unlock_admin_panel, AdminUnlockRequest
    
    user_id = "test_user_123"
    mock_db.users_collection.update_one = AsyncMock()
    
    # Test with lowercase version
    request = AdminUnlockRequest(password="ashmor12@")
    result = await unlock_admin_panel(request, current_user_id=user_id)
    
    assert result["success"] is True
    
    # Test with mixed case
    request2 = AdminUnlockRequest(password="AshMor12@")
    result2 = await unlock_admin_panel(request2, current_user_id=user_id)
    
    assert result2["success"] is True


@pytest.mark.asyncio
async def test_admin_unlock_wrong_password(mock_db, mock_audit_logger):
    """Test admin unlock fails with wrong password"""
    from routes.admin_endpoints import unlock_admin_panel, AdminUnlockRequest
    from fastapi import HTTPException
    
    user_id = "test_user_123"
    
    # Test with wrong password
    request = AdminUnlockRequest(password="WrongPassword123")
    
    with pytest.raises(HTTPException) as exc_info:
        await unlock_admin_panel(request, current_user_id=user_id)
    
    assert exc_info.value.status_code == 403
    assert "Invalid admin password" in str(exc_info.value.detail)
    
    # Verify audit log was called for failed attempt
    mock_audit_logger.log_event.assert_called_once()
    call_args = mock_audit_logger.log_event.call_args
    assert call_args.kwargs['event_type'] == 'admin_unlock_failed'


@pytest.mark.asyncio
async def test_admin_unlock_empty_password(mock_db, mock_audit_logger):
    """Test admin unlock fails with empty password"""
    from routes.admin_endpoints import unlock_admin_panel, AdminUnlockRequest
    from fastapi import HTTPException
    
    user_id = "test_user_123"
    
    # Test with empty password
    request = AdminUnlockRequest(password="   ")
    
    with pytest.raises(HTTPException) as exc_info:
        await unlock_admin_panel(request, current_user_id=user_id)
    
    assert exc_info.value.status_code == 400
    assert "Password is required" in str(exc_info.value.detail)


@pytest.mark.asyncio
async def test_admin_unlock_misconfigured_password(mock_db, mock_audit_logger):
    """Test admin unlock fails gracefully when ADMIN_PASSWORD is empty string"""
    from routes.admin_endpoints import unlock_admin_panel, AdminUnlockRequest
    from fastapi import HTTPException
    
    user_id = "test_user_123"
    
    # Set ADMIN_PASSWORD to empty string (misconfiguration)
    original_password = os.environ.get('ADMIN_PASSWORD')
    os.environ['ADMIN_PASSWORD'] = ""
    
    try:
        request = AdminUnlockRequest(password="AnyPassword")
        
        with pytest.raises(HTTPException) as exc_info:
            await unlock_admin_unlock(request, current_user_id=user_id)
        
        assert exc_info.value.status_code == 500
        assert "Server configuration error" in str(exc_info.value.detail)
        
    finally:
        # Restore original environment
        if original_password:
            os.environ['ADMIN_PASSWORD'] = original_password
        elif 'ADMIN_PASSWORD' in os.environ:
            del os.environ['ADMIN_PASSWORD']
