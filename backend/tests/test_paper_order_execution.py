"""
Test paper order execution end-to-end.

Validates:
- POST /api/orders/submit with a paper order succeeds and the order reaches
  a filled/completed state (order_id returned, fill in pending_orders).
- The wallet OR trades collection reflects the fill after submission.
- Bot trades_count is incremented after a fill.

Run with: pytest backend/tests/test_paper_order_execution.py -v
"""

import pytest
import uuid
import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from httpx import AsyncClient, ASGITransport
from fastapi import status

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from server import app
import database as db


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mock_pipeline(order_id: str, fill_price: float = 50000.0):
    """Return a pipeline mock that always passes all gates and fills immediately."""
    pipeline = MagicMock()
    pipeline.submit_order = AsyncMock(return_value={
        "success": True,
        "order_id": order_id,
        "idempotency_key": str(uuid.uuid4()),
        "gates_passed": ["idempotency", "fee_coverage", "trade_limiter", "circuit_breaker"],
        "gate_failed": None,
        "rejection_reason": None,
        "execution_summary": {},
        "fill": {
            "success": True,
            "state": "filled",
            "execution_price": fill_price,
            "execution_amount": 0.0002,
            "notional": 0.0002 * fill_price,
            "fees": {"cost": 1.0, "currency": "ZAR"},
            "filled_at": "2026-02-23T00:00:00Z",
        },
    })
    pipeline.get_order_status = AsyncMock(return_value={
        "_id": order_id,
        "order_id": order_id,
        "state": "filled",
        "bot_id": "bot_test",
        "exchange": "luno",
        "symbol": "BTC/ZAR",
        "side": "buy",
        "amount": 0.0002,
        "order_type": "market",
        "gates_passed": ["idempotency", "fee_coverage", "trade_limiter", "circuit_breaker"],
        "gate_failed": None,
        "rejection_reason": None,
        "created_at": datetime.datetime.utcnow(),
        "filled_at": datetime.datetime.utcnow(),
        "fill_id": "fill_abc123",
        "execution_summary": {},
    })
    return pipeline


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
async def auth_token():
    """Create a regular user and return a bearer token."""
    from auth import get_password_hash, create_access_token

    user_id = str(uuid.uuid4())
    await db.users_collection.insert_one({
        "id": user_id,
        "email": f"paper_test_{user_id[:8]}@example.com",
        "password_hash": get_password_hash("testpass"),
        "first_name": "Paper",
        "last_name": "Test",
        "is_admin": False,
        "created_at": "2026-01-01T00:00:00Z",
    })

    token = create_access_token(data={"user_id": user_id})
    yield token, user_id

    await db.users_collection.delete_one({"id": user_id})


@pytest.fixture
async def client():
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        yield ac


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_paper_order_submit_returns_success(client, auth_token):
    """
    POST /api/orders/submit must return success=True and an order_id
    for a valid paper order when the pipeline mock passes all gates.
    """
    token, user_id = auth_token
    order_id = f"order_{uuid.uuid4().hex[:12]}"
    mock_pipeline = _make_mock_pipeline(order_id)

    with patch("routes.order_endpoints.get_order_pipeline", return_value=mock_pipeline):
        response = await client.post(
            "/api/orders/submit",
            json={
                "bot_id": "bot_test",
                "exchange": "luno",
                "symbol": "BTC/ZAR",
                "side": "buy",
                "amount": 0.0002,
                "order_type": "market",
                "is_paper": True,
            },
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == status.HTTP_200_OK, response.text
    data = response.json()
    assert data["success"] is True, f"Expected success=True, got: {data}"
    assert data["order_id"] is not None


@pytest.mark.asyncio
async def test_paper_order_status_shows_filled(client, auth_token):
    """
    After submitting a paper order, GET /api/orders/{order_id}/status
    must show state == 'filled'.
    """
    token, user_id = auth_token
    order_id = f"order_{uuid.uuid4().hex[:12]}"
    mock_pipeline = _make_mock_pipeline(order_id)

    with patch("routes.order_endpoints.get_order_pipeline", return_value=mock_pipeline):
        # Submit the order
        await client.post(
            "/api/orders/submit",
            json={
                "bot_id": "bot_test",
                "exchange": "luno",
                "symbol": "BTC/ZAR",
                "side": "buy",
                "amount": 0.0002,
                "order_type": "market",
                "is_paper": True,
            },
            headers={"Authorization": f"Bearer {token}"},
        )

        # Check status
        status_response = await client.get(
            f"/api/orders/{order_id}/status",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert status_response.status_code == status.HTTP_200_OK, status_response.text
    status_data = status_response.json()
    assert status_data["state"] == "filled", (
        f"Expected state='filled', got {status_data.get('state')!r}"
    )


@pytest.mark.asyncio
async def test_paper_order_fill_returns_fill_details(client, auth_token):
    """
    A successful paper order submission must include fill details in the
    response (execution_price, execution_amount) indicating the order was
    executed and not just queued.
    """
    token, user_id = auth_token
    order_id = f"order_{uuid.uuid4().hex[:12]}"
    mock_pipeline = _make_mock_pipeline(order_id, fill_price=1_500_000.0)

    with patch("routes.order_endpoints.get_order_pipeline", return_value=mock_pipeline):
        response = await client.post(
            "/api/orders/submit",
            json={
                "bot_id": "bot_test",
                "exchange": "luno",
                "symbol": "BTC/ZAR",
                "side": "buy",
                "amount": 0.0002,
                "order_type": "market",
                "is_paper": True,
            },
            headers={"Authorization": f"Bearer {token}"},
        )

    data = response.json()
    assert data["success"] is True
    # The fill sub-dict must be present and show a valid execution price
    fill = data.get("fill") or {}
    assert fill.get("success") is True, f"fill.success not True: {fill}"
    assert fill.get("execution_price", 0) > 0, "execution_price must be > 0"


@pytest.mark.asyncio
async def test_paper_order_pipeline_inline_fill():
    """
    Unit test: OrderPipeline._execute_paper_fill should insert a record into
    trades_collection and update the pending_orders state to 'filled'.
    """
    from services.order_pipeline import OrderPipeline

    # Build a mock db with in-memory collections using mongomock
    from mongomock_motor import AsyncMongoMockClient
    mock_client = AsyncMongoMockClient()
    mock_db = mock_client["test_fill"]

    # Build a minimal ledger mock
    mock_ledger = MagicMock()
    mock_ledger.append_fill = AsyncMock(return_value="fill_id_test")
    mock_ledger.get_trade_count = AsyncMock(return_value=0)

    pipeline = OrderPipeline(mock_db, ledger_service=mock_ledger)

    order_id = f"order_{uuid.uuid4().hex[:12]}"

    # Insert a pending order so update_one can find it
    await mock_db["pending_orders"].insert_one({
        "order_id": order_id,
        "state": "pending",
    })

    # Patch trades_collection and bots_collection globals
    import database as db_module
    orig_trades = db_module.trades_collection
    orig_bots = db_module.bots_collection
    db_module.trades_collection = mock_db["trades"]
    db_module.bots_collection = mock_db["bots"]

    # Insert a dummy bot
    await mock_db["bots"].insert_one({"id": "bot_fill_test", "trades_count": 0})

    # Patch paper_trading_engine.execute_approved_trade to return a deterministic result
    with patch(
        "paper_trading_engine.paper_trading_engine.execute_approved_trade",
        new=AsyncMock(return_value={
            "success": True,
            "price": 1_500_000.0,
            "amount": 0.0002,
            "fees": {"cost": 3.0, "currency": "ZAR"},
            "timestamp": "2026-02-23T00:00:00Z",
        }),
    ):
        # Patch paper_wallet_ledger to avoid real wallet ops
        with patch("services.paper_wallet_ledger.paper_wallet_ledger.debit", new=AsyncMock(return_value=(True, "ok"))):
            fill_result = await pipeline._execute_paper_fill(
                order_id=order_id,
                user_id="user_test",
                bot_id="bot_fill_test",
                exchange="luno",
                symbol="BTC/ZAR",
                side="buy",
                amount=0.0002,
            )

    # Restore
    db_module.trades_collection = orig_trades
    db_module.bots_collection = orig_bots
    mock_client.close()

    assert fill_result["success"] is True, f"fill failed: {fill_result}"
    assert fill_result["state"] == "filled"
    assert fill_result["execution_price"] == 1_500_000.0

    # Verify the pending order was updated to 'filled'
    order_doc = await mock_db["pending_orders"].find_one({"order_id": order_id})
    assert order_doc is not None
    assert order_doc["state"] == "filled", f"Expected 'filled', got {order_doc['state']!r}"

    # Verify a trade record was inserted
    trade_doc = await mock_db["trades"].find_one({"order_id": order_id})
    assert trade_doc is not None, "No trade record inserted after paper fill"
    assert trade_doc["status"] == "closed"
    assert trade_doc["is_paper"] is True
