"""
Audit logger guard tests for missing collection handles.
"""

import pytest
from unittest.mock import patch
import os
import sys

backend_path = os.path.join(os.path.dirname(__file__), '..')
if backend_path not in sys.path:
    sys.path.insert(0, backend_path)

pytest.importorskip("motor")

import database as db
from engines.audit_logger import audit_logger
from services.safe_audit_logger import SafeAuditLogger


@pytest.mark.asyncio
async def test_audit_logger_handles_missing_collection():
    with patch.object(db, "audit_logs_collection", None), patch.object(db, "audit_logs", None):
        result = await audit_logger.log_event(
            "bot_created",
            "user-1",
            {"ip_address": "127.0.0.1"}
        )
        assert result is True


@pytest.mark.asyncio
async def test_safe_audit_logger_handles_missing_collection():
    logger = SafeAuditLogger()
    with patch.object(db, "audit_logs_collection", None):
        result = await logger.log_action("user-1", "test_action")
        assert result is True
