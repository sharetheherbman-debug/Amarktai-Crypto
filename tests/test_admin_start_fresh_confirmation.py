"""
Test suite for admin start-fresh confirmation phrase requirement.
Tests the new confirmation-based reset instead of password-based.
"""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch, MagicMock


@pytest.fixture
def mock_admin_user():
    """Mock admin user for testing"""
    return "admin_user_123"


@pytest.fixture
def mock_regular_user():
    """Mock regular user for testing"""
    return "user_456"


@pytest.mark.asyncio
async def test_start_fresh_requires_confirmation(client, mock_admin_user):
    """Test that start-fresh requires exact confirmation phrase"""
    
    # Mock the require_admin dependency
    with patch('backend.routes.admin_start_fresh.require_admin', return_value=mock_admin_user):
        # Test with missing confirmation
        response = client.post('/api/admin/start-fresh', json={
            "confirm": "",
            "scope": "paper_only"
        })
        assert response.status_code == 400
        assert "confirmation phrase" in response.json()["detail"].lower()
        
        # Test with wrong confirmation
        response = client.post('/api/admin/start-fresh', json={
            "confirm": "DELETE ALL DATA",
            "scope": "paper_only"
        })
        assert response.status_code == 400
        assert "START FRESH" in response.json()["detail"]


@pytest.mark.asyncio
async def test_start_fresh_success_with_correct_confirmation(client, mock_admin_user):
    """Test that start-fresh works with correct confirmation"""
    
    with patch('backend.routes.admin_start_fresh.require_admin', return_value=mock_admin_user), \
         patch('backend.routes.admin_start_fresh.db') as mock_db:
        
        # Mock database operations
        mock_db.bots_collection.update_many = AsyncMock(return_value=MagicMock(modified_count=5))
        mock_db.bots_collection.find = AsyncMock(return_value=MagicMock(
            to_list=AsyncMock(return_value=[{"id": "bot1"}, {"id": "bot2"}])
        ))
        mock_db.trades_collection.delete_many = AsyncMock(return_value=MagicMock(deleted_count=10))
        mock_db.orders_collection.delete_many = AsyncMock(return_value=MagicMock(deleted_count=8))
        mock_db.fills_collection.delete_many = AsyncMock(return_value=MagicMock(deleted_count=15))
        mock_db.bot_performance_collection.delete_many = AsyncMock(return_value=MagicMock(deleted_count=5))
        mock_db.users_collection.update_one = AsyncMock(return_value=MagicMock(modified_count=1))
        mock_db.training_sessions_collection.delete_many = AsyncMock(return_value=MagicMock(deleted_count=2))
        mock_db.audit_logs_collection.insert_one = AsyncMock()
        
        # Test with correct confirmation
        response = client.post('/api/admin/start-fresh', json={
            "confirm": "START FRESH",
            "scope": "paper_only",
            "also_reset_risk_locks": True
        })
        
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert "deleted" in data
        assert data["deleted"]["bots_deleted"] == 5


@pytest.mark.asyncio  
async def test_start_fresh_non_admin_forbidden(client, mock_regular_user):
    """Test that non-admin users get 403"""
    
    from fastapi import HTTPException
    
    def mock_require_admin_fail():
        raise HTTPException(status_code=403, detail="Admin access required")
    
    with patch('backend.routes.admin_start_fresh.require_admin', side_effect=mock_require_admin_fail):
        response = client.post('/api/admin/start-fresh', json={
            "confirm": "START FRESH",
            "scope": "paper_only"
        })
        assert response.status_code == 403


@pytest.mark.asyncio
async def test_reset_user_data_requires_confirmation(client, mock_admin_user):
    """Test that reset-user-data requires exact confirmation phrase"""
    
    with patch('backend.routes.admin_start_fresh.require_admin', return_value=mock_admin_user):
        # Test with missing confirmation
        response = client.post('/api/admin/reset-user-data', json={
            "confirm": "",
            "target_user_id": "user_123",
            "wipe_bots": True
        })
        assert response.status_code == 400
        assert "confirmation phrase" in response.json()["detail"].lower()
        
        # Test with wrong confirmation
        response = client.post('/api/admin/reset-user-data', json={
            "confirm": "RESET DATA",
            "target_user_id": "user_123",
            "wipe_bots": True
        })
        assert response.status_code == 400
        assert "RESET USER DATA" in response.json()["detail"]


@pytest.mark.asyncio
async def test_reset_user_data_response_schema(client, mock_admin_user):
    """Test that reset-user-data returns correct response schema"""
    
    with patch('backend.routes.admin_start_fresh.require_admin', return_value=mock_admin_user), \
         patch('backend.routes.admin_start_fresh.db') as mock_db:
        
        # Mock database operations
        mock_db.users_collection.find_one = AsyncMock(return_value={
            "_id": "user_123",
            "email": "test@example.com",
            "username": "testuser"
        })
        mock_db.bots_collection.count_documents = AsyncMock(return_value=3)
        mock_db.trades_collection.count_documents = AsyncMock(return_value=0)
        mock_db.api_keys_collection.count_documents = AsyncMock(return_value=0)
        mock_db.bots_collection.delete_many = AsyncMock(return_value=MagicMock(deleted_count=3))
        mock_db.trades_collection.delete_many = AsyncMock(return_value=MagicMock(deleted_count=0))
        mock_db.api_keys_collection.delete_many = AsyncMock(return_value=MagicMock(deleted_count=0))
        mock_db.audit_logs_collection.insert_one = AsyncMock()
        mock_db.audit_logs_collection.update_one = AsyncMock()
        
        response = client.post('/api/admin/reset-user-data', json={
            "confirm": "RESET USER DATA",
            "target_user_id": "user_123",
            "wipe_bots": True,
            "wipe_trades": False,
            "wipe_keys": False
        })
        
        assert response.status_code == 200
        data = response.json()
        assert data["ok"] is True
        assert "deleted" in data
        assert "backup_id" in data
        assert data["deleted"]["bots"] == 3
