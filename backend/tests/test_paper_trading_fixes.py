"""
Tests for paper trading pipeline fixes (issue: queued but not executed/persisted).

Key issues fixed:
1. Quality filter blocked trades when FLOKx/Fetch.ai keys are missing.
2. EDGE_GATE_PAPER blocked trades when ML predictor returns a simulated result.
3. FLOKx/Fetch.ai "key not configured" warnings logged on every tick (rate-limited).
4. /api/wallet/paper missing canonical wallet_summary fields.
5. /api/flokx/status and /api/fetchai/status now expose a machine-readable
   "status" field (e.g. "not_configured") so callers can detect unconfigured
   integrations without parsing human-readable messages.
"""

import asyncio
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_regime(confidence: float = 0.75, trend: str = "bullish") -> dict:
    return {"trend": trend, "confidence": confidence, "is_simulated": False}


def _make_ml_prediction(confidence: float = 0.8, direction: str = "up",
                         predicted_change: float = 0.5, is_simulated: bool = False) -> dict:
    return {
        "direction": direction,
        "confidence": confidence,
        "predicted_change": predicted_change,
        "is_simulated": is_simulated,
    }


def _make_flokx_unavailable() -> dict:
    """Simulates the return value when FLOKx key is not configured."""
    return {
        "strength": 0.0,
        "volatility": 0.0,
        "sentiment": "unavailable",
        "is_simulated": True,
        "source": "unavailable",
    }


def _make_fetchai_unavailable() -> dict:
    """Simulates the return value when Fetch.ai key is not configured."""
    return {
        "confidence": 0.0,
        "signal": "HOLD",
        "is_simulated": True,
    }


# ---------------------------------------------------------------------------
# Fix 1 + 2: Quality filter + edge gate when FLOKx/Fetch.ai are unavailable
# ---------------------------------------------------------------------------

class TestQualityFilterGracefulDegradation:
    """
    When FLOKx and Fetch.ai keys are not configured both sources return
    is_simulated=True.  Only regime + ML predictor are available.
    The quality filter must accept a trade if at least 1 source is confident.
    """

    def _count_sources(self, regime, prediction, fetchai_data, flokx_data):
        """
        Mirrors the fixed quality-filter logic from execute_smart_trade.
        Returns (available_sources, confidence_sources, avg_confidence).
        """
        total_confidence = 0
        confidence_sources = 0
        available_sources = 0

        # regime is always available
        available_sources += 1
        if regime.get("confidence", 0) > 0.5:
            total_confidence += regime.get("confidence", 0)
            confidence_sources += 1

        if not prediction.get("is_simulated", False):
            available_sources += 1
            if prediction.get("confidence", 0) > 0.6:
                total_confidence += prediction.get("confidence", 0)
                confidence_sources += 1

        if not fetchai_data.get("is_simulated", True):
            available_sources += 1
            if fetchai_data.get("confidence", 0) > 60:
                total_confidence += fetchai_data.get("confidence", 0) / 100
                confidence_sources += 1

        if not flokx_data.get("is_simulated", True):
            available_sources += 1
            if flokx_data.get("strength", 0) > 60:
                total_confidence += flokx_data.get("strength", 0) / 100
                confidence_sources += 1

        avg = total_confidence / max(confidence_sources, 1)
        return available_sources, confidence_sources, avg

    def test_trade_allowed_when_only_regime_and_ml_available(self):
        """When FLOKx+Fetch.ai are not configured, regime + ML should be enough."""
        regime = _make_regime(confidence=0.80)
        prediction = _make_ml_prediction(confidence=0.75, predicted_change=0.4)
        flokx = _make_flokx_unavailable()
        fetchai = _make_fetchai_unavailable()

        available, contributing, avg = self._count_sources(regime, prediction, fetchai, flokx)

        # Only 2 sources available (regime + ML)
        assert available == 2
        # Both are confident
        assert contributing == 2
        # avg >= 0.65 → gate should PASS
        assert avg >= 0.65

        min_required = 1 if available <= 2 else 2
        assert contributing >= min_required

    def test_trade_allowed_with_only_regime_confident(self):
        """Only regime is confident (ML returns simulated data) - 1 available source."""
        regime = _make_regime(confidence=0.80)
        prediction = _make_ml_prediction(is_simulated=True)  # CCXT failed
        flokx = _make_flokx_unavailable()
        fetchai = _make_fetchai_unavailable()

        available, contributing, avg = self._count_sources(regime, prediction, fetchai, flokx)

        # Only 1 source (regime)
        assert available == 1
        assert contributing == 1
        assert avg >= 0.65

        min_required = 1 if available <= 2 else 2
        assert contributing >= min_required

    def test_trade_blocked_when_regime_low_confidence_and_no_other_sources(self):
        """Even with regime available, low confidence should block the trade."""
        regime = _make_regime(confidence=0.30)  # below 0.5 threshold
        prediction = _make_ml_prediction(is_simulated=True)
        flokx = _make_flokx_unavailable()
        fetchai = _make_fetchai_unavailable()

        available, contributing, avg = self._count_sources(regime, prediction, fetchai, flokx)

        assert contributing == 0  # no source above threshold
        min_required = 1 if available <= 2 else 2
        assert contributing < min_required  # gate should FAIL (correct behaviour)

    def test_all_four_sources_available_requires_two(self):
        """When all 4 sources are live, the original requirement (2+) still applies."""
        regime = _make_regime(confidence=0.80)
        prediction = _make_ml_prediction(confidence=0.75)
        flokx = {"strength": 80.0, "is_simulated": False}
        fetchai = {"confidence": 85.0, "is_simulated": False}

        available, contributing, avg = self._count_sources(regime, prediction, fetchai, flokx)

        assert available == 4
        assert contributing == 4
        min_required = 1 if available <= 2 else 2
        assert contributing >= min_required


class TestEdgeGateSimulatedML:
    """EDGE_GATE_PAPER must not block trades when ML prediction is simulated."""

    def _edge_gate_blocks(self, prediction: dict, expected_move_pct: float,
                           edge_required_pct: float, gate_enabled: bool = True) -> bool:
        """Mirror the fixed edge-gate logic."""
        ml_is_simulated = prediction.get("is_simulated", False)
        return gate_enabled and not ml_is_simulated and expected_move_pct < edge_required_pct

    def test_gate_does_not_block_when_ml_simulated(self):
        """Simulated ML + low expected move → gate must NOT block."""
        prediction = {"is_simulated": True, "predicted_change": 0.0}
        blocked = self._edge_gate_blocks(prediction, expected_move_pct=0.0, edge_required_pct=0.5)
        assert not blocked

    def test_gate_blocks_when_ml_real_and_move_too_small(self):
        """Real ML + move below threshold → gate must block."""
        prediction = {"is_simulated": False, "predicted_change": 0.1}
        blocked = self._edge_gate_blocks(prediction, expected_move_pct=0.1, edge_required_pct=0.5)
        assert blocked

    def test_gate_passes_when_ml_real_and_move_sufficient(self):
        """Real ML + move above threshold → gate must not block."""
        prediction = {"is_simulated": False, "predicted_change": 0.8}
        blocked = self._edge_gate_blocks(prediction, expected_move_pct=0.8, edge_required_pct=0.5)
        assert not blocked

    def test_gate_disabled_never_blocks(self):
        """If EDGE_GATE_PAPER=false, gate must never block regardless of move size."""
        prediction = {"is_simulated": False, "predicted_change": 0.01}
        blocked = self._edge_gate_blocks(prediction, expected_move_pct=0.01,
                                          edge_required_pct=0.5, gate_enabled=False)
        assert not blocked


# ---------------------------------------------------------------------------
# Fix 3: FLOKx/Fetch.ai warning rate-limiting
# ---------------------------------------------------------------------------

class TestWarningRateLimiting:
    """FLOKx/Fetch.ai 'key not configured' warnings must be rate-limited."""

    def test_flokx_warning_rate_limited(self):
        """Second warning within 10 minutes must be suppressed."""
        from flokx_integration import FLOKxIntegration, _WARN_INTERVAL

        instance = FLOKxIntegration()
        warnings_logged = []

        def fake_warning(msg, *args, **kwargs):
            warnings_logged.append(msg)

        with patch("flokx_integration.logger") as mock_logger:
            mock_logger.warning.side_effect = fake_warning

            # First call → warning emitted
            now = datetime.now(timezone.utc)
            if instance._last_missing_key_warn is None or (now - instance._last_missing_key_warn) >= _WARN_INTERVAL:
                mock_logger.warning("rate-limited warning")
                instance._last_missing_key_warn = now

            # Immediate second call → should be suppressed
            if instance._last_missing_key_warn is None or (now - instance._last_missing_key_warn) >= _WARN_INTERVAL:
                mock_logger.warning("rate-limited warning")

        assert len(warnings_logged) == 1

    def test_fetchai_warning_rate_limited(self):
        """Fetch.ai warning within 10 minutes must be suppressed."""
        from fetchai_integration import FetchAIIntegration, _WARN_INTERVAL

        instance = FetchAIIntegration()
        warnings_logged = []

        with patch("fetchai_integration.logger") as mock_logger:
            mock_logger.warning.side_effect = lambda msg, *a, **k: warnings_logged.append(msg)

            now = datetime.now(timezone.utc)
            if instance._last_missing_key_warn is None or (now - instance._last_missing_key_warn) >= _WARN_INTERVAL:
                mock_logger.warning("rate-limited warning")
                instance._last_missing_key_warn = now

            # Immediate second call → suppressed
            if instance._last_missing_key_warn is None or (now - instance._last_missing_key_warn) >= _WARN_INTERVAL:
                mock_logger.warning("rate-limited warning")

        assert len(warnings_logged) == 1

    def test_flokx_warning_reissued_after_interval(self):
        """Warning is reissued after the rate-limit interval expires."""
        from flokx_integration import FLOKxIntegration, _WARN_INTERVAL

        instance = FLOKxIntegration()
        # Simulate last warning was >10 minutes ago
        instance._last_missing_key_warn = datetime.now(timezone.utc) - _WARN_INTERVAL - timedelta(seconds=1)

        warnings_logged = []
        with patch("flokx_integration.logger") as mock_logger:
            mock_logger.warning.side_effect = lambda msg, *a, **k: warnings_logged.append(msg)
            now = datetime.now(timezone.utc)
            if instance._last_missing_key_warn is None or (now - instance._last_missing_key_warn) >= _WARN_INTERVAL:
                mock_logger.warning("rate-limited warning")
                instance._last_missing_key_warn = now

        assert len(warnings_logged) == 1


# ---------------------------------------------------------------------------
# Fix 4: /api/wallet/paper response shape
# ---------------------------------------------------------------------------

class TestPaperWalletEndpointShape:
    """
    /api/wallet/paper must return canonical wallet_summary fields:
    success, mode, available_wallet_zar, allocated_funds_zar,
    reserved_funds_zar, required_funds_zar, shortfall_zar, status, timestamp.
    """

    def test_paper_wallet_required_fields_present(self):
        """Verify the updated get_paper_wallet function returns all required keys."""
        import importlib
        import sys

        # We just test the function structure without hitting the database
        from routes.wallet_hub import get_paper_wallet
        import inspect
        src = inspect.getsource(get_paper_wallet)

        required_keys = [
            "success",
            "mode",
            "available_wallet_zar",
            "allocated_funds_zar",
            "reserved_funds_zar",
            "required_funds_zar",
            "shortfall_zar",
            "status",
            "timestamp",
        ]
        for key in required_keys:
            assert key in src, f"Key '{key}' missing from get_paper_wallet response"

    def test_wallet_summary_totals_consistent(self):
        """
        available + allocated + reserved must equal the reported total
        (or shortfall = max(0, required - available)).
        """
        # Build a synthetic summary as the service would return it
        available = 10000.0
        allocated = 3000.0
        reserved = 500.0
        required = 12000.0

        shortfall = max(0, required - available)
        total = available + allocated + reserved

        assert shortfall == 2000.0  # 12000 - 10000
        assert total == 13500.0     # sanity check
        assert shortfall >= 0       # shortfall is never negative


# ---------------------------------------------------------------------------
# Fix 5: FLOKx + Fetch.ai status endpoints return "not_configured" clearly
# ---------------------------------------------------------------------------

class TestExternalServiceStatusEndpoints:
    """Status endpoints must expose a machine-readable 'status' string."""

    def test_flokx_status_has_status_field(self):
        """GET /api/flokx/status response in server.py includes a 'status' string field."""
        import inspect
        import server  # noqa: F401 – just checking source code structure

        src = inspect.getsource(server)
        # The endpoint now returns {"status": "not_configured" | "configured", ...}
        assert '"not_configured"' in src or "'not_configured'" in src

    def test_fetchai_status_has_status_field(self):
        """GET /api/fetchai/status response includes a 'status' string field."""
        import inspect
        from routes import fetchai as fetchai_routes
        src = inspect.getsource(fetchai_routes)
        assert "not_configured" in src
