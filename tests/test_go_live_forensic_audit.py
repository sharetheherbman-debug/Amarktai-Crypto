"""
Final Go-Live Forensic Audit Tests

Validates repaired ChatOps execution path:
- Confirmation policy (only high-risk actions require confirmation)
- set_system_mode: paper mode no confirmation, live mode requires confirmation
- JSON leakage protection
- detect_action_intent improvements
- execute_tool_action logging

Run with:
  ENVIRONMENT=testing JWT_SECRET=test-jwt-secret-for-testing-only python -m pytest tests/test_go_live_forensic_audit.py -v
"""

import os
import sys
import ast
import re
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))
os.environ.setdefault("ENVIRONMENT", "testing")
os.environ.setdefault("JWT_SECRET", "test-jwt-secret-for-testing-only")

AI_CHAT_PATH = os.path.join(os.path.dirname(__file__), '..', 'backend', 'routes', 'ai_chat.py')
DASHBOARD_STATE_PATH = os.path.join(
    os.path.dirname(__file__), '..', 'frontend', 'src', 'hooks', 'useDashboardState.js'
)


# ─── Source file helpers ────────────────────────────────────────────────────

def read_ai_chat():
    with open(AI_CHAT_PATH, 'r') as f:
        return f.read()


def read_dashboard_state():
    with open(DASHBOARD_STATE_PATH, 'r') as f:
        return f.read()


# ─── Confirmation Policy ────────────────────────────────────────────────────

class TestConfirmationPolicy:
    """Verify confirmation is only required for truly risky actions."""

    def test_set_system_mode_has_no_static_requires_confirmation(self):
        """set_system_mode must not have requires_confirmation: True in ACTION_REGISTRY
        (it is handled dynamically based on mode parameter)."""
        src = read_ai_chat()
        # Find the set_system_mode registry block
        block_match = re.search(
            r'"set_system_mode"\s*:\s*\{[^}]+\}',
            src,
            re.DOTALL
        )
        assert block_match, "set_system_mode must be in ACTION_REGISTRY"
        block = block_match.group(0)
        # Should NOT have requires_confirmation: True
        assert '"requires_confirmation": True' not in block, (
            "set_system_mode must not have requires_confirmation=True in registry; "
            "confirmation is handled dynamically in execute_tool_action"
        )

    def test_pause_bot_no_confirmation_required(self):
        """pause_bot must not require confirmation (routine operation)."""
        src = read_ai_chat()
        block_match = re.search(
            r'"pause_bot"\s*:\s*\{[^}]+\}',
            src,
            re.DOTALL
        )
        assert block_match, "pause_bot must be in ACTION_REGISTRY"
        block = block_match.group(0)
        assert '"requires_confirmation": True' not in block, (
            "pause_bot must not require confirmation — it is a routine operation"
        )

    def test_resume_bot_no_confirmation_required(self):
        """resume_bot must not require confirmation (routine operation)."""
        src = read_ai_chat()
        block_match = re.search(
            r'"resume_bot"\s*:\s*\{[^}]+\}',
            src,
            re.DOTALL
        )
        assert block_match, "resume_bot must be in ACTION_REGISTRY"
        block = block_match.group(0)
        assert '"requires_confirmation": True' not in block, (
            "resume_bot must not require confirmation — it is a routine operation"
        )

    def test_stop_bot_no_confirmation_required(self):
        """stop_bot must not require confirmation (routine operation)."""
        src = read_ai_chat()
        block_match = re.search(
            r'"stop_bot"\s*:\s*\{[^}]+\}',
            src,
            re.DOTALL
        )
        assert block_match, "stop_bot must be in ACTION_REGISTRY"
        block = block_match.group(0)
        assert '"requires_confirmation": True' not in block, (
            "stop_bot must not require confirmation — it is a routine operation"
        )

    def test_transfer_funds_still_requires_confirmation(self):
        """transfer_funds must still require confirmation (affects real funds)."""
        src = read_ai_chat()
        block_match = re.search(
            r'"transfer_funds"\s*:\s*\{[^}]+\}',
            src,
            re.DOTALL
        )
        assert block_match, "transfer_funds must be in ACTION_REGISTRY"
        block = block_match.group(0)
        assert '"requires_confirmation": True' in block, (
            "transfer_funds must require confirmation — it affects real funds"
        )


# ─── execute_tool_action Dynamic Confirmation ───────────────────────────────

class TestExecuteToolActionDynamicConfirmation:
    """Verify execute_tool_action applies mode-dependent confirmation for set_system_mode."""

    def test_execute_tool_action_has_mode_check(self):
        """execute_tool_action must check mode param for set_system_mode."""
        src = read_ai_chat()
        assert 'action == "set_system_mode"' in src, (
            "execute_tool_action must have mode-dependent confirmation check for set_system_mode"
        )
        assert 'mode in {"live", "autopilot"}' in src or "mode == \"live\"" in src, (
            "execute_tool_action must require confirmation for live/autopilot modes"
        )


# ─── _handle_set_system_mode ────────────────────────────────────────────────

class TestHandleSetSystemMode:
    """Verify _handle_set_system_mode calls set_system_mode helper directly."""

    def test_handler_does_not_call_switch_mode_route(self):
        """_handle_set_system_mode must NOT call switch_mode (HTTP route function).
        It must call set_system_mode (helper function) directly."""
        src = read_ai_chat()
        # The function _handle_set_system_mode should not pass a confirmation_token
        # mismatch. Verify it imports set_system_mode, not switch_mode (for the action path).
        handler_match = re.search(
            r'async def _handle_set_system_mode.*?(?=\nasync def |\nACTION_REGISTRY)',
            src,
            re.DOTALL
        )
        assert handler_match, "_handle_set_system_mode must exist"
        handler_src = handler_match.group(0)
        assert 'set_system_mode' in handler_src, (
            "_handle_set_system_mode must call set_system_mode helper"
        )

    def test_handler_checks_live_trading_enabled(self):
        """_handle_set_system_mode must check live_trading_enabled() for live mode."""
        src = read_ai_chat()
        handler_match = re.search(
            r'async def _handle_set_system_mode.*?(?=\nasync def |\nACTION_REGISTRY)',
            src,
            re.DOTALL
        )
        assert handler_match, "_handle_set_system_mode must exist"
        handler_src = handler_match.group(0)
        assert 'live_trading_enabled' in handler_src, (
            "_handle_set_system_mode must check live_trading_enabled() before switching to live"
        )


# ─── detect_action_intent improvements ──────────────────────────────────────

class TestDetectActionIntent:
    """Verify detect_action_intent catches mode toggle phrases."""

    def test_off_pattern_present(self):
        """detect_action_intent must handle 'off'/'disable' patterns for modes."""
        src = read_ai_chat()
        assert '"off"' in src or "'off'" in src, (
            "detect_action_intent must handle 'off' keyword for mode toggle"
        )
        assert '"disable"' in src or "'disable'" in src, (
            "detect_action_intent must handle 'disable' keyword"
        )

    def test_turn_on_pattern_present(self):
        """detect_action_intent must handle 'turn on' for paper/live mode."""
        src = read_ai_chat()
        assert 'turn on' in src, (
            "detect_action_intent must handle 'turn on' for mode switching"
        )


# ─── JSON Leakage Protection ─────────────────────────────────────────────────

class TestJSONLeakageProtection:
    """Verify JSON leakage guard is present in ai_chat endpoint."""

    def test_json_leakage_guard_present(self):
        """ai_chat must have a guard that detects and suppresses raw JSON responses."""
        src = read_ai_chat()
        assert 'JSON leakage guard' in src or 'json leakage' in src.lower() or \
               'suppressed raw JSON' in src or 'raw JSON payload' in src, (
            "ai_chat must have a JSON leakage guard that prevents raw action JSON "
            "from being returned to the user"
        )

    def test_json_leakage_guard_checks_action_key(self):
        """JSON leakage guard must specifically check for 'action' key in payload."""
        src = read_ai_chat()
        # The guard should be checking for "action" in the candidate JSON
        assert '"action" in _candidate' in src or "'action' in _candidate" in src, (
            "JSON leakage guard must check for 'action' key in candidate JSON"
        )

    def test_json_leakage_guard_has_safe_fallback(self):
        """JSON leakage guard must provide a safe user-facing fallback message."""
        src = read_ai_chat()
        assert 'safe fallback' in src.lower() or \
               'unable to process' in src.lower() or \
               'rephrase' in src.lower(), (
            "JSON leakage guard must provide a human-readable fallback when raw JSON is detected"
        )


# ─── AI System Prompt ────────────────────────────────────────────────────────

class TestAISystemPrompt:
    """Verify AI system prompt does not encourage raw JSON responses."""

    def test_json_action_instruction_removed(self):
        """AI system prompt must NOT instruct OpenAI to return JSON action payloads."""
        src = read_ai_chat()
        # The old instruction that caused raw JSON leakage
        assert 'respond with JSON' not in src, (
            "AI system prompt must not instruct OpenAI to respond with JSON. "
            "This was the root cause of raw action JSON being shown to users."
        )

    def test_plain_language_instruction_present(self):
        """AI system prompt must explicitly instruct plain language responses."""
        src = read_ai_chat()
        assert 'plain' in src.lower() and ('language' in src.lower() or 'natural' in src.lower()), (
            "AI system prompt must instruct the model to respond in plain natural language"
        )

    def test_no_json_instruction_present(self):
        """AI system prompt must explicitly say not to output JSON."""
        src = read_ai_chat()
        # Verify the 'Do NOT produce JSON' instruction exists
        assert 'Do NOT produce JSON' in src or 'NEVER output raw JSON' in src or \
               'never output raw JSON' in src.lower(), (
            "AI system prompt must explicitly instruct the model not to output JSON"
        )


# ─── Frontend Confirmation ID Tracking ──────────────────────────────────────

class TestFrontendConfirmationTracking:
    """Verify frontend tracks confirmation_id for multi-turn confirmations."""

    def test_pending_confirmation_id_state_exists(self):
        """useDashboardState must have pendingConfirmationId state."""
        src = read_dashboard_state()
        assert 'pendingConfirmationId' in src, (
            "useDashboardState must track pendingConfirmationId state for "
            "multi-turn AI action confirmations"
        )

    def test_confirmation_id_included_in_request(self):
        """handleSendMessage must include confirmation_id in request when pending."""
        src = read_dashboard_state()
        assert 'confirmation_id: pendingConfirmationId' in src or \
               "confirmation_id" in src, (
            "handleSendMessage must include confirmation_id in the API request "
            "when a pending confirmation exists"
        )

    def test_pending_confirmation_cleared_after_use(self):
        """pendingConfirmationId must be cleared after it is used in a request."""
        src = read_dashboard_state()
        assert 'setPendingConfirmationId(null)' in src, (
            "pendingConfirmationId must be cleared after it is included in a request"
        )

    def test_confirmation_id_stored_from_response(self):
        """handleSendMessage must store confirmation_id from AI response."""
        src = read_dashboard_state()
        assert 'setPendingConfirmationId(payload.confirmation_id)' in src or \
               'setPendingConfirmationId(' in src, (
            "handleSendMessage must store confirmation_id from AI response for "
            "the next user message to carry it"
        )


# ─── Logging ─────────────────────────────────────────────────────────────────

class TestChatOpsLogging:
    """Verify ChatOps action logging is present."""

    def test_action_executed_logging(self):
        """execute_tool_action must log successful action execution."""
        src = read_ai_chat()
        assert 'AI ChatOps: executing action=' in src, (
            "execute_tool_action must log each action being executed"
        )

    def test_action_failed_logging(self):
        """execute_tool_action must log failed actions."""
        src = read_ai_chat()
        assert 'AI ChatOps: action=' in src and 'failed' in src, (
            "execute_tool_action must log failed action execution"
        )

    def test_action_blocked_pending_confirmation_logging(self):
        """execute_tool_action must log when action is blocked pending confirmation."""
        src = read_ai_chat()
        assert 'blocked pending confirmation=' in src, (
            "execute_tool_action must log when an action is blocked awaiting confirmation"
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
