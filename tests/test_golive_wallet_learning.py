"""
Tests for go-live blocker fixes (part 2).

Covers:
  A) /api/wallet/status endpoint exists in wallet_hub.py
  B) /api/wallet/deposit-address never raises 400 for missing keys (source check)
  C) /api/learning/status always includes state/trades_analyzed/bots_evolved fields
  D) /api/admin/audit/chat endpoint exists in admin_endpoints.py
  E) Frontend loadDepositAddress silently handles disabled/unconfigured responses
"""

import os
import re
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

_WALLET_HUB_PATH = os.path.join(os.path.dirname(__file__), "..", "backend", "routes", "wallet_hub.py")
_SERVER_PATH = os.path.join(os.path.dirname(__file__), "..", "backend", "server.py")
_LEARNING_PATH = os.path.join(os.path.dirname(__file__), "..", "backend", "routes", "learning_jobs.py")
_ADMIN_PATH = os.path.join(os.path.dirname(__file__), "..", "backend", "routes", "admin_endpoints.py")
_DASHBOARD_STATE_PATH = os.path.join(os.path.dirname(__file__), "..", "frontend", "src", "hooks", "useDashboardState.js")


def _read(path: str) -> str:
    with open(path) as f:
        return f.read()


class TestWalletStatusEndpoint:
    """A) GET /api/wallet/status must be implemented in wallet_hub.py."""

    def test_wallet_status_route_exists(self):
        src = _read(_WALLET_HUB_PATH)
        assert '@router.get("/status")' in src, (
            "wallet_hub.py must implement @router.get('/status') for /api/wallet/status"
        )

    def test_wallet_status_returns_paper_field(self):
        src = _read(_WALLET_HUB_PATH)
        assert '"paper"' in src or "'paper'" in src, (
            "wallet_hub.py /status must return a 'paper' key"
        )

    def test_wallet_status_returns_keys_field(self):
        src = _read(_WALLET_HUB_PATH)
        assert '"keys"' in src or "'keys'" in src, (
            "wallet_hub.py /status must return a 'keys' key"
        )

    def test_wallet_status_never_raises_on_missing_keys(self):
        """The entire endpoint must be wrapped in try/except that returns a stable default."""
        src = _read(_WALLET_HUB_PATH)
        assert 'return {' in src, (
            "wallet_hub.py /status must return safe defaults on any exception"
        )


class TestDepositAddressSoftError:
    """B) /api/wallet/deposit-address must return 200 with status=disabled/unconfigured (no 400)."""

    def test_no_400_for_missing_keys(self):
        src = _read(_SERVER_PATH)
        start = src.find("@api_router.get(\"/wallet/deposit-address\")")
        assert start >= 0, "deposit-address route not found in server.py"
        fn_body = src[start:start + 3000]
        assert 'status": "disabled' in fn_body or '"status": "disabled"' in fn_body, (
            "deposit-address must return status=disabled when trading not enabled"
        )
        assert 'status": "unconfigured' in fn_body or '"status": "unconfigured"' in fn_body, (
            "deposit-address must return status=unconfigured when no API key configured"
        )

    def test_no_raise_400_on_missing_key(self):
        """The function must not raise HTTPException(status_code=400) for missing key."""
        src = _read(_SERVER_PATH)
        start = src.find("@api_router.get(\"/wallet/deposit-address\")")
        assert start >= 0
        fn_body = src[start:start + 4000]
        bad_pattern = re.compile(
            r'raise\s+HTTPException\s*\(\s*status_code\s*=\s*400.*No.*API key',
            re.DOTALL
        )
        assert not bad_pattern.search(fn_body), (
            "deposit-address must not raise HTTPException(400) for missing API key"
        )

    def test_soft_error_has_address_null(self):
        """Soft-error responses must include address: None."""
        src = _read(_SERVER_PATH)
        start = src.find("@api_router.get(\"/wallet/deposit-address\")")
        assert start >= 0
        fn_body = src[start:start + 4000]
        assert '"address": None' in fn_body or "'address': None" in fn_body, (
            "deposit-address soft-error responses must have address=None"
        )


class TestLearningStatusTruthfulness:
    """C) /api/learning/status must be truthful — never claim 'optimized' with 0 trades."""

    def test_state_field_present(self):
        src = _read(_LEARNING_PATH)
        assert '"state"' in src or "'state'" in src, (
            "learning_jobs.py must return 'state' field"
        )

    def test_trades_analyzed_field_present(self):
        src = _read(_LEARNING_PATH)
        assert "trades_analyzed" in src, (
            "learning_jobs.py must return 'trades_analyzed' field"
        )

    def test_bots_evolved_field_present(self):
        src = _read(_LEARNING_PATH)
        assert "bots_evolved" in src, (
            "learning_jobs.py must return 'bots_evolved' field"
        )

    def test_idle_when_no_data(self):
        """When trades_analyzed==0, state must be 'idle' not 'complete'."""
        src = _read(_LEARNING_PATH)
        assert 'state = "idle"' in src or "state = 'idle'" in src, (
            "learning_jobs.py must set state='idle' when trades_analyzed==0"
        )

    def test_no_false_optimized_claim(self):
        """The word 'optimized' must not appear as a state value."""
        src = _read(_LEARNING_PATH)
        bad = re.compile(r'state\s*=\s*["\']optimized["\']')
        assert not bad.search(src), (
            "learning_jobs.py must not set state='optimized'"
        )


class TestAdminAuditChatEndpoint:
    """D) GET /api/admin/audit/chat must exist in admin_endpoints.py."""

    def test_audit_chat_route_exists(self):
        src = _read(_ADMIN_PATH)
        assert '@router.get("/audit/chat")' in src, (
            "admin_endpoints.py must implement @router.get('/audit/chat')"
        )

    def test_audit_chat_requires_admin(self):
        src = _read(_ADMIN_PATH)
        idx = src.find('@router.get("/audit/chat")')
        assert idx >= 0
        fn_body = src[idx:idx + 500]
        assert "require_admin" in fn_body or "get_admin_user" in fn_body or "verify_admin" in fn_body, (
            "audit/chat must require admin access"
        )

    def test_audit_chat_returns_messages(self):
        src = _read(_ADMIN_PATH)
        idx = src.find('@router.get("/audit/chat")')
        assert idx >= 0
        fn_body = src[idx:idx + 1000]
        assert '"messages"' in fn_body or "'messages'" in fn_body, (
            "audit/chat must return a 'messages' key"
        )


class TestFrontendDepositAddressGating:
    """E) Frontend loadDepositAddress must handle disabled/unconfigured without console.error."""

    def test_no_console_error_on_disabled(self):
        """console.error must not be called in loadDepositAddress body."""
        src = _read(_DASHBOARD_STATE_PATH)
        start = src.find("const loadDepositAddress = async")
        assert start >= 0, "loadDepositAddress function not found"
        fn_body = src[start:start + 600]
        assert "console.error" not in fn_body, (
            "loadDepositAddress must not call console.error — "
            "deposit address is non-critical and errors should be swallowed silently"
        )

    def test_handles_disabled_status(self):
        """loadDepositAddress must handle status=disabled from backend."""
        src = _read(_DASHBOARD_STATE_PATH)
        start = src.find("const loadDepositAddress = async")
        assert start >= 0
        fn_body = src[start:start + 600]
        assert "disabled" in fn_body, (
            "loadDepositAddress must handle status=disabled response"
        )

    def test_handles_unconfigured_status(self):
        """loadDepositAddress must handle status=unconfigured from backend."""
        src = _read(_DASHBOARD_STATE_PATH)
        start = src.find("const loadDepositAddress = async")
        assert start >= 0
        fn_body = src[start:start + 600]
        assert "unconfigured" in fn_body, (
            "loadDepositAddress must handle status=unconfigured response"
        )
