"""
Shared pytest fixtures for backend/tests.

Provides an in-memory MongoDB via mongomock_motor so tests do not require
a live MongoDB instance.  All modules that import `database` (db) will use
the mock collections instead of a real server.
"""
import sys
import os
import pytest
from unittest.mock import AsyncMock, patch

# Ensure the backend package is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

try:
    from mongomock_motor import AsyncMongoMockClient
    _MONGOMOCK_AVAILABLE = True
except ImportError:
    _MONGOMOCK_AVAILABLE = False


@pytest.fixture(autouse=True)
async def mock_database():
    """
    Patch the `database` module to use an in-memory MongoDB for every test.

    Replaces `db.connect` with a no-op and wires all collection globals to
    mongomock_motor collections so no live MongoDB connection is needed.
    """
    if not _MONGOMOCK_AVAILABLE:
        yield
        return

    import database as db_module

    client = AsyncMongoMockClient()
    mock_db = client["test_amarktai"]

    # Keep a reference to the originals so we can restore them
    orig_connect = db_module.connect
    orig_client = db_module.client
    orig_db = db_module.db

    # Patch db.connect to set up mock collections without touching real MongoDB
    async def _mock_connect():
        db_module.client = client
        db_module.db = mock_db
        await _set_collections(db_module, mock_db)

    db_module.connect = _mock_connect
    db_module.client = client
    db_module.db = mock_db
    await _set_collections(db_module, mock_db)

    yield mock_db

    # Restore originals after each test
    db_module.connect = orig_connect
    db_module.client = orig_client
    db_module.db = orig_db

    client.close()


async def _set_collections(db_module, mock_db):
    """Wire all collection globals in the database module to mock collections."""
    collection_map = {
        "users_collection": "users",
        "bots_collection": "bots",
        "trades_collection": "trades",
        "api_keys_collection": "api_keys",
        "alerts_collection": "alerts",
        "sessions_collection": "sessions",
        "system_config_collection": "system_config",
        "system_modes_collection": "system_modes",
        "chat_messages_collection": "chat_messages",
        "chat_sessions_collection": "chat_sessions",
        "bot_lifecycle_collection": "bot_lifecycle",
        "bot_metrics_collection": "bot_metrics",
        "system_metrics_collection": "system_metrics",
        "bot_runtime_state_collection": "bot_runtime_state",
        "training_jobs_collection": "training_jobs",
        "risk_profiles_collection": "risk_profiles",
        "market_regimes_collection": "market_regimes",
        "learning_data_collection": "learning_data",
        "learning_logs_collection": "learning_logs",
        "audit_logs_collection": "audit_logs",
        "notifications_collection": "notifications",
        "reports_collection": "reports",
        "promotion_requests_collection": "promotion_requests",
        "decisions_collection": "decisions",
        "reinvest_requests_collection": "reinvest_requests",
        "autopilot_actions_collection": "autopilot_actions",
        "rogue_detections_collection": "rogue_detections",
        "autopilot_milestones_collection": "autopilot_milestones",
        "autopilot_reinvest_events_collection": "autopilot_reinvest_events",
        "emergency_stop_collection": "emergency_stop",
        "wallet_balances_collection": "wallet_balances",
        "capital_injections_collection": "capital_injections",
        "wallets_collection": "wallets",
        "ledger_collection": "ledger",
        "profits_collection": "profits",
        "profit_ledger_collection": "profit_ledger",
        "funding_plans_collection": "funding_plans",
        "wallet_transfers_collection": "wallet_transfers",
        "transfer_jobs_collection": "transfer_jobs",
        "orders_collection": "orders",
        "positions_collection": "positions",
        "balance_snapshots_collection": "balance_snapshots",
        "performance_metrics_collection": "performance_metrics",
        "user_countdowns_collection": "user_countdowns",
        "price_snapshots_collection": "price_snapshots",
        "paper_ledger_collection": "paper_ledger",
        "learning_runs_collection": "learning_runs",
        "learning_changes_collection": "learning_changes",
        "learning_metrics_collection": "learning_metrics",
        "strategy_versions_collection": "strategy_versions",
        "bot_strategy_assignments_collection": "bot_strategy_assignments",
        "action_audit_log_collection": "action_audit_log",
        "user_memory_collection": "user_memory",
        "chatops_actions_collection": "chatops_actions",
        "chatops_confirmations_collection": "chatops_confirmations",
    }
    for attr, collection_name in collection_map.items():
        if hasattr(db_module, attr):
            setattr(db_module, attr, mock_db[collection_name])

    # Legacy aliases
    for alias in ("wallet_balances", "capital_injections", "audit_logs", "funding_plans"):
        if hasattr(db_module, alias):
            setattr(db_module, alias, mock_db[alias])
