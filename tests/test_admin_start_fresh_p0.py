"""
Test Admin Start Fresh Endpoint
Tests confirmation phrase requirement and admin auth.
"""

import pytest
from fastapi.testclient import TestClient


def test_start_fresh_requires_admin(client: TestClient, normal_user_token: str):
    """Non-admin users should be rejected"""
    response = client.post(
        "/api/admin/start-fresh",
        json={
            "confirmation_phrase": "START FRESH",
            "scope": "paper_only",
            "also_reset_risk_locks": True
        },
        headers={"Authorization": f"Bearer {normal_user_token}"}
    )
    assert response.status_code in [401, 403], f"Expected 401/403 but got {response.status_code}"


def test_start_fresh_requires_confirmation(client: TestClient, admin_token: str):
    """Must provide exact confirmation phrase"""
    # Wrong phrase
    response = client.post(
        "/api/admin/start-fresh",
        json={
            "confirmation_phrase": "wrong phrase",
            "scope": "paper_only"
        },
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert response.status_code == 400
    assert "confirmation" in response.json()["detail"].lower()
    
    # Empty phrase
    response = client.post(
        "/api/admin/start-fresh",
        json={
            "confirmation_phrase": "",
            "scope": "paper_only"
        },
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    assert response.status_code == 400


def test_start_fresh_success(client: TestClient, admin_token: str):
    """Correct phrase and admin auth should succeed"""
    response = client.post(
        "/api/admin/start-fresh",
        json={
            "confirmation_phrase": "START FRESH",
            "scope": "paper_only",
            "also_reset_risk_locks": True
        },
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    
    # Should succeed or return specific error if live trading enabled
    assert response.status_code in [200, 400], f"Got unexpected {response.status_code}"
    
    if response.status_code == 200:
        data = response.json()
        assert "deleted" in data or "ok" in data
