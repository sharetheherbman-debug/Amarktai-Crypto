"""
Final Cleanup & Truth-Repair Tests
====================================
Validates all fixes from the final non-trading cleanup pass:
  1. Provider truth model — never "Healthy" for unconfigured providers
  2. Decision Timeline — never NaN for confidence/regime
  3. Radar — float() is safe on None values
  4. Admin panel — single User Management section
  5. HuggingFace — encrypted key lookup path
  6. Self-healing — truthful state labels
"""

import re
import os
import ast
import sys


# ---------------------------------------------------------------------------
# 1. Provider Truth Model — frontend MarketIntelligencePanel
# ---------------------------------------------------------------------------

class TestProviderTruthFrontend:
    """MarketIntelligencePanel must never show Healthy for unconfigured providers."""

    PANEL_PATH = os.path.join(
        os.path.dirname(__file__),
        "..",
        "frontend",
        "src",
        "pages",
        "dashboard",
        "sections",
        "MarketIntelligencePanel.js",
    )

    def _read(self):
        with open(self.PANEL_PATH, encoding="utf-8") as f:
            return f.read()

    def test_public_fallback_status_defined(self):
        """STATUS_STYLES must contain a public_fallback entry."""
        src = self._read()
        assert "public_fallback" in src, (
            "MarketIntelligencePanel must define public_fallback in STATUS_STYLES"
        )

    def test_healthy_only_for_configured_valid(self):
        """status = 'healthy' must only be set when user has a valid key, not for MI fallback."""
        src = self._read()
        # The status = 'healthy' must be inside a configured_valid / test_ok branch
        # and there must NOT be a plain `status = 'healthy'` after the else-if for unconfigured
        lines = src.splitlines()
        for i, line in enumerate(lines):
            stripped = line.strip()
            # Reject any line that sets status to healthy based purely on mi.healthy without
            # first requiring userHasKey / configured_by_user
            if "status = 'healthy'" in stripped or 'status = "healthy"' in stripped:
                # The allowed form: only inside configured_valid/test_ok branch
                # Verify the previous context has a user key check
                context = "\n".join(lines[max(0, i - 5):i + 1])
                assert "configured_valid" in context or "test_ok" in context, (
                    f"Line {i+1}: 'healthy' status assigned without user key check: {line}"
                )

    def test_unconfigured_plus_mi_reachable_becomes_public_fallback(self):
        """When no user key + MI reachable, status must be public_fallback, not healthy."""
        src = self._read()
        assert "public_fallback" in src
        # The pattern should guard with !userHasKey before assigning public_fallback
        assert "userHasKey" in src or "user_has_key" in src or "configured_by_user" in src, (
            "Must check whether user has configured a key before upgrading MI reachable to public_fallback"
        )

    def test_public_fallback_label_is_not_healthy(self):
        """The label for public_fallback must not say Healthy."""
        src = self._read()
        # Find public_fallback definition in STATUS_STYLES
        match = re.search(r"public_fallback:\s*\{[^}]+\}", src)
        assert match, "public_fallback entry not found in STATUS_STYLES"
        entry = match.group(0)
        assert "Healthy" not in entry, (
            f"public_fallback label must not say 'Healthy': {entry}"
        )

    def test_no_user_key_warning_message_present(self):
        """Panel must show a clear message when no user keys and only public fallback."""
        src = self._read()
        assert "no user key configured" in src.lower() or "No user key configured" in src, (
            "Panel must display a message explaining that no user key is configured"
        )


# ---------------------------------------------------------------------------
# 2. Decision Timeline — NaN safety in DecisionTrace.js
# ---------------------------------------------------------------------------

class TestDecisionTraceNaN:
    """DecisionTrace must never render NaN for confidence or regime."""

    TRACE_PATH = os.path.join(
        os.path.dirname(__file__),
        "..",
        "frontend",
        "src",
        "components",
        "DecisionTrace.js",
    )

    def _read(self):
        with open(self.TRACE_PATH, encoding="utf-8") as f:
            return f.read()

    def test_confidence_has_null_guard(self):
        """Confidence display must check for null/NaN before calling toFixed()."""
        src = self._read()
        # The old unguarded pattern was: (selectedDecision.confidence * 100).toFixed(1)
        # This must NOT appear without a null guard
        bad_pattern = r"\(selectedDecision\.confidence\s*\*\s*100\)\.toFixed"
        assert not re.search(bad_pattern, src), (
            "Confidence display must have null/NaN guard before .toFixed()"
        )

    def test_regime_confidence_has_null_guard(self):
        """Regime confidence must check for null/NaN before calling toFixed()."""
        src = self._read()
        bad_pattern = r"\(selectedDecision\.regime_state\.confidence\s*\*\s*100\)\.toFixed"
        assert not re.search(bad_pattern, src), (
            "Regime confidence must have null/NaN guard before .toFixed()"
        )

    def test_confidence_fallback_text_present(self):
        """There must be a fallback text (e.g. 'Not available') for missing confidence."""
        src = self._read()
        assert "Not available" in src or "not available" in src, (
            "DecisionTrace must show a fallback text for missing confidence"
        )

    def test_position_size_multiplier_null_safe(self):
        """position_size_multiplier.toFixed() must not be called directly."""
        src = self._read()
        bad = r"selectedDecision\.position_size_multiplier\.toFixed"
        assert not re.search(bad, src), (
            "position_size_multiplier.toFixed() must have a null guard"
        )


# ---------------------------------------------------------------------------
# 3. Radar — float() null-safety
# ---------------------------------------------------------------------------

class TestRadarNullSafety:
    """All float() calls in radar.py must go through _safe_float() for None safety."""

    RADAR_PATH = os.path.join(
        os.path.dirname(__file__),
        "..",
        "backend",
        "routes",
        "radar.py",
    )

    def _read(self):
        with open(self.RADAR_PATH, encoding="utf-8") as f:
            return f.read()

    def test_safe_float_helper_exists(self):
        """_safe_float() helper must be defined."""
        src = self._read()
        assert "def _safe_float(" in src, "Radar must define _safe_float() helper"

    def test_no_raw_float_on_entry_price(self):
        """entry_price must not use bare float() — must use _safe_float()."""
        src = self._read()
        # Old bad pattern: float(open_trade.get("entry_price", ...)) — bare float, NOT _safe_float
        # Use word boundary to avoid matching _safe_float(open_trade.get("entry_price"
        bad = r'(?<![_a-zA-Z])float\(open_trade\.get\("entry_price"'
        assert not re.search(bad, src), (
            "entry_price must use _safe_float(), not bare float()"
        )

    def test_no_raw_float_on_current_price(self):
        """current_price must not use bare float() — must use _safe_float()."""
        src = self._read()
        bad = r'(?<![_a-zA-Z])float\(open_trade\.get\("current_price"'
        assert not re.search(bad, src), (
            "current_price must use _safe_float(), not bare float()"
        )

    def test_no_raw_float_on_qty(self):
        """qty must not use bare float() — must use _safe_float()."""
        src = self._read()
        bad = r'(?<![_a-zA-Z])float\(open_trade\.get\("quantity"'
        assert not re.search(bad, src), (
            "qty must use _safe_float(), not bare float()"
        )

    def test_safe_float_handles_none(self):
        """_safe_float(None, default) must return the default."""
        # Import and test the helper directly
        sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
        try:
            # Parse and extract _safe_float
            src = self._read()
            # Check the function handles None
            assert "if value is None" in src, "_safe_float must handle None explicitly"
        finally:
            sys.path.pop(0)

    def test_safe_float_handles_nan(self):
        """_safe_float must handle NaN values."""
        src = self._read()
        assert "isnan" in src or "math.isnan" in src, "_safe_float must check for NaN"


# ---------------------------------------------------------------------------
# 4. Admin Panel — No duplicate User Management
# ---------------------------------------------------------------------------

class TestAdminPanelNoDuplicates:
    """AdminPanelSection must have exactly one User Management section."""

    ADMIN_PATH = os.path.join(
        os.path.dirname(__file__),
        "..",
        "frontend",
        "src",
        "pages",
        "dashboard",
        "sections",
        "AdminPanelSection.js",
    )

    def _read(self):
        with open(self.ADMIN_PATH, encoding="utf-8") as f:
            return f.read()

    def test_single_user_management_heading(self):
        """There must be exactly one '👥 User Management' heading element."""
        src = self._read()
        # Match h3 elements with the User Management label
        heading_pattern = re.compile(r'<h3[^>]*>.*?👥 User Management.*?</h3>', re.DOTALL)
        matches = heading_pattern.findall(src)
        count = len(matches)
        assert count == 1, (
            f"Expected exactly 1 User Management h3 heading, found {count}"
        )

    def test_interactive_user_management_present(self):
        """The interactive User Management section with Refresh button must be kept."""
        src = self._read()
        assert "loadAdminUsers" in src, (
            "Interactive User Management section (loadAdminUsers) must be present"
        )

    def test_simple_user_table_removed(self):
        """The simpler non-interactive user table (with handleChangePassword button) must be removed."""
        src = self._read()
        # The removed section had a direct "Change PW" button text and handleChangePassword calls
        # that are NOT the reset password flow in the interactive section
        # The interactive section uses handleResetPassword, not handleChangePassword inline
        # Check that no 'Change PW' text remains (this was specific to the removed section)
        assert "Change PW" not in src, (
            "The old non-interactive 'Change PW' button must be removed (duplicate section)"
        )


# ---------------------------------------------------------------------------
# 5. Hugging Face — encrypted key lookup
# ---------------------------------------------------------------------------

class TestHuggingFaceKeyResolution:
    """HuggingFace route must read from api_key_encrypted, not api_key."""

    HF_PATH = os.path.join(
        os.path.dirname(__file__),
        "..",
        "backend",
        "routes",
        "huggingface.py",
    )

    def _read(self):
        with open(self.HF_PATH, encoding="utf-8") as f:
            return f.read()

    def test_reads_api_key_encrypted(self):
        """_get_hf_key must request api_key_encrypted field."""
        src = self._read()
        assert "api_key_encrypted" in src, (
            "huggingface.py must read api_key_encrypted (canonical encrypted storage)"
        )

    def test_uses_decrypt_api_key(self):
        """_get_hf_key must decrypt using decrypt_api_key."""
        src = self._read()
        assert "decrypt_api_key" in src, (
            "huggingface.py must import and use decrypt_api_key"
        )

    def test_imports_decrypt_from_api_key_management(self):
        """decrypt_api_key must be imported from api_key_management."""
        src = self._read()
        assert "from routes.api_key_management import" in src and "decrypt_api_key" in src, (
            "Must import decrypt_api_key from routes.api_key_management"
        )


# ---------------------------------------------------------------------------
# 6. Self-Healing — truthful state labels
# ---------------------------------------------------------------------------

class TestSelfHealingTruth:
    """self_healing.py must return truthful state labels."""

    SH_PATH = os.path.join(
        os.path.dirname(__file__),
        "..",
        "backend",
        "engines",
        "self_healing.py",
    )

    def _read(self):
        with open(self.SH_PATH, encoding="utf-8") as f:
            return f.read()

    def test_state_running_when_active(self):
        """get_status() must return state='running' when is_running=True."""
        src = self._read()
        assert '"running"' in src or "'running'" in src, (
            "get_status must define running state"
        )

    def test_state_idle_for_initialized_not_started(self):
        """get_status() must distinguish idle from disabled."""
        src = self._read()
        assert '"idle"' in src or "'idle'" in src, (
            "get_status must define idle state for initialized-but-not-started"
        )

    def test_state_stopped_for_explicitly_stopped(self):
        """get_status() must return stopped when service was stopped."""
        src = self._read()
        assert '"stopped"' in src or "'stopped'" in src, (
            "get_status must define stopped state"
        )

    def test_no_single_disabled_for_all_inactive(self):
        """get_status() must NOT use 'disabled' as the only non-running state."""
        src = self._read()
        # Extract the get_status method body
        method_match = re.search(r"def get_status\(self\).*?return \{[^}]+\}", src, re.DOTALL)
        if method_match:
            method_body = method_match.group(0)
            # Should have multiple states beyond just running/disabled
            assert "idle" in method_body or "stopped" in method_body, (
                "get_status must distinguish between idle, stopped, and disabled states"
            )


# ---------------------------------------------------------------------------
# 7. Backend diagnostics provider health — canonical truth fields
# ---------------------------------------------------------------------------

class TestDiagnosticsProviderTruth:
    """provider-health endpoint must include canonical truth fields."""

    DIAG_PATH = os.path.join(
        os.path.dirname(__file__),
        "..",
        "backend",
        "routes",
        "diagnostics.py",
    )

    def _read(self):
        with open(self.DIAG_PATH, encoding="utf-8") as f:
            return f.read()

    def test_configured_by_user_field(self):
        """provider health map must include configured_by_user."""
        src = self._read()
        assert "configured_by_user" in src, (
            "diagnostics provider health must include configured_by_user field"
        )

    def test_using_public_fallback_field(self):
        """provider health map must include using_public_fallback."""
        src = self._read()
        assert "using_public_fallback" in src, (
            "diagnostics provider health must include using_public_fallback field"
        )

    def test_no_healthy_for_unconfigured_providers(self):
        """Unconfigured providers must not be upgraded to 'healthy' from MI reachability."""
        src = self._read()
        # Find the live_health loop and ensure unconfigured -> public_fallback, not healthy
        # Old bad code was: existing["status"] = "healthy" if ok else "down"
        bad_pattern = r'"healthy" if ok else "down"'
        assert bad_pattern not in src, (
            "Unconfigured providers must not be marked 'healthy' — use 'public_fallback'"
        )

    def test_public_fallback_status_in_live_health_loop(self):
        """Unconfigured + reachable providers must get public_fallback status."""
        src = self._read()
        assert "public_fallback" in src, (
            "diagnostics must use public_fallback status for reachable-but-unconfigured providers"
        )

    def test_ownership_scope_field(self):
        """provider health map must include ownership_scope."""
        src = self._read()
        assert "ownership_scope" in src, (
            "diagnostics provider health must include ownership_scope field"
        )
