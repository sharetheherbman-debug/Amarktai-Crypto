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


def _override_require_admin(user_id):
    """Factory: return a FastAPI dependency that always yields *user_id*."""
    def _dep():
        return user_id
    return _dep


def _override_require_admin_raise(exc):
    """Factory: return a FastAPI dependency that raises *exc*."""
    def _dep():
        raise exc
    return _dep


@pytest.mark.asyncio
async def test_start_fresh_requires_confirmation(client, mock_admin_user):
    """Test that start-fresh requires exact confirmation phrase"""
    from server import app
    from auth import require_admin

    app.dependency_overrides[require_admin] = _override_require_admin(mock_admin_user)
    try:
        # Test with missing confirmation
        response = client.post('/api/admin/start-fresh', json={
            "confirmation_phrase": "",
            "scope": "paper_only"
        })
        assert response.status_code == 400
        assert "confirmation phrase" in response.json()["detail"].lower()

        # Test with wrong confirmation
        response = client.post('/api/admin/start-fresh', json={
            "confirmation_phrase": "DELETE ALL DATA",
            "scope": "paper_only"
        })
        assert response.status_code == 400
        assert "START FRESH" in response.json()["detail"]
    finally:
        app.dependency_overrides.pop(require_admin, None)


@pytest.mark.asyncio
async def test_start_fresh_success_with_correct_confirmation(client, mock_admin_user):
    """Test that start-fresh works with correct confirmation"""
    from server import app
    from auth import require_admin

    app.dependency_overrides[require_admin] = _override_require_admin(mock_admin_user)
    try:
        # Mock the orchestrator run directly so the test is isolated from DB setup.
        mock_orch_result = {
            "bots_soft_deleted": 5,
            "trades_deleted": 10,
            "orders_deleted": 8,
            "fills_deleted": 15,
            "telemetry_deleted": 5,
            "risk_locks_reset": 1,
            "wallet_before": {},
            "wallet_after": {},
            "warnings": [],
            "post_reset": {},
        }
        with patch('routes.admin_start_fresh._orchestrator_run', new=AsyncMock(return_value=mock_orch_result)), \
             patch('routes.admin_start_fresh.db') as mock_db:
            mock_db.training_jobs_collection = MagicMock()
            mock_db.training_jobs_collection.delete_many = AsyncMock()
            mock_db.audit_logs_collection = MagicMock()
            mock_db.audit_logs_collection.insert_one = AsyncMock()

            response = client.post('/api/admin/start-fresh', json={
                "confirmation_phrase": "START FRESH",
                "scope": "paper_only",
                "also_reset_risk_locks": True
            })

            assert response.status_code == 200
            data = response.json()
            assert data["ok"] is True
            assert "deleted" in data
            assert data["deleted"]["bots_deleted"] == 5
    finally:
        app.dependency_overrides.pop(require_admin, None)


@pytest.mark.asyncio
async def test_start_fresh_non_admin_forbidden(client, mock_regular_user):
    """Test that non-admin users get 403"""
    from fastapi import HTTPException
    from server import app
    from auth import require_admin

    def _raise_403():
        raise HTTPException(status_code=403, detail="Admin access required")

    app.dependency_overrides[require_admin] = _raise_403
    try:
        response = client.post('/api/admin/start-fresh', json={
            "confirm": "START FRESH",
            "scope": "paper_only"
        })
        assert response.status_code == 403
    finally:
        app.dependency_overrides.pop(require_admin, None)


@pytest.mark.asyncio
async def test_reset_user_data_requires_confirmation(client, mock_admin_user):
    """Test that reset-user-data requires exact confirmation phrase"""
    from server import app
    from auth import require_admin

    app.dependency_overrides[require_admin] = _override_require_admin(mock_admin_user)
    try:
        # Test with missing confirmation
        response = client.post('/api/admin/reset-user-data', json={
            "confirmation_phrase": "",
            "target_user_id": "user_123",
            "wipe_bots": True
        })
        assert response.status_code == 400
        assert "confirmation phrase" in response.json()["detail"].lower()

        # Test with wrong confirmation
        response = client.post('/api/admin/reset-user-data', json={
            "confirmation_phrase": "RESET DATA",
            "target_user_id": "user_123",
            "wipe_bots": True
        })
        assert response.status_code == 400
        assert "RESET USER DATA" in response.json()["detail"]
    finally:
        app.dependency_overrides.pop(require_admin, None)


@pytest.mark.asyncio
async def test_reset_user_data_response_schema(client, mock_admin_user):
    """Test that reset-user-data returns correct response schema"""
    from server import app
    from auth import require_admin

    app.dependency_overrides[require_admin] = _override_require_admin(mock_admin_user)
    try:
        with patch('routes.admin_start_fresh.db') as mock_db:
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
                "confirmation_phrase": "RESET USER DATA",
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

    finally:
        app.dependency_overrides.pop(require_admin, None)
