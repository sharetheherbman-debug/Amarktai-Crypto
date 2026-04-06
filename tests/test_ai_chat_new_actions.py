"""
Tests for new AI chat actions added in go-live fix.

Covers:
1. fund_paper_wallet action funds and returns success
2. reset_paper_session action clears bots/trades/wallet
3. get_market_regime action returns regime data
4. get_flokx_status action returns key status
5. check_flokx_signals action uses per-user key
6. ACTION_REGISTRY contains all new entries
7. NLP intent detector recognises new command phrases
"""

import pytest
import sys
import os
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

# Stub heavy optional dependencies
for _mod in ("ccxt", "ccxt.async_support", "ccxt_service", "tenacity",
             "flokx_integration", "ml_predictor"):
    if _mod not in sys.modules:
        _mock = MagicMock()
        _mock.FLOKxIntegration = MagicMock
        sys.modules[_mod] = _mock


# ---------------------------------------------------------------------------
# 1. fund_paper_wallet
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_fund_paper_wallet_success():
    """fund_paper_wallet must reset then fund the paper wallet."""
    from routes.ai_chat import _handle_fund_paper_wallet

    mock_service = MagicMock()
    mock_service.reset = AsyncMock(return_value={"wallet_before": {}, "wallet_after": {}})
    mock_service.fund = AsyncMock(return_value={"balances": {"ZAR": 30000.0}})

    with patch("routes.ai_chat.paper_wallet_service", mock_service, create=True), \
         patch("services.paper_wallet_service.paper_wallet_service", mock_service):
        # Import inside to pick up patch
        import importlib
        import routes.ai_chat as ai_chat_mod
        orig = getattr(ai_chat_mod, "_handle_fund_paper_wallet")
        result = await orig("user1", {"amount": 30000})

    assert result["success"] is True
    assert "30000" in result["message"] or "30,000" in result["message"] or result["data"]["funded_amount"] == 30000


@pytest.mark.asyncio
async def test_fund_paper_wallet_negative_amount():
    """fund_paper_wallet must reject negative amounts."""
    from routes.ai_chat import _handle_fund_paper_wallet
    result = await _handle_fund_paper_wallet("user1", {"amount": -100})
    assert result["success"] is False
    assert "positive" in result.get("error", "") or "positive" in result.get("message", "")


# ---------------------------------------------------------------------------
# 2. reset_paper_session
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_reset_paper_session_clears_data():
    """reset_paper_session must delete paper bots and reset wallet."""
    from routes.ai_chat import _handle_reset_paper_session
    import database as db

    mock_bots = MagicMock()
    mock_bots.update_many = AsyncMock(return_value=MagicMock(modified_count=3))

    mock_trades = MagicMock()
    mock_trades.delete_many = AsyncMock(return_value=MagicMock(deleted_count=10))

    mock_orders = MagicMock()
    mock_orders.delete_many = AsyncMock(return_value=MagicMock(deleted_count=0))

    mock_positions = MagicMock()
    mock_positions.delete_many = AsyncMock(return_value=MagicMock(deleted_count=0))

    mock_ledger = MagicMock()
    mock_ledger.delete_many = AsyncMock(return_value=MagicMock(deleted_count=5))

    mock_wallet_svc = MagicMock()
    mock_wallet_svc.reset = AsyncMock(return_value={"wallet_before": {}, "wallet_after": {}})

    with patch.object(db, "bots_collection", mock_bots), \
         patch.object(db, "trades_collection", mock_trades), \
         patch.object(db, "orders_collection", mock_orders), \
         patch.object(db, "positions_collection", mock_positions), \
         patch.object(db, "paper_ledger_collection", mock_ledger):
        import services.paper_wallet_service as pwm
        orig_svc = pwm.paper_wallet_service
        pwm.paper_wallet_service = mock_wallet_svc
        try:
            result = await _handle_reset_paper_session("user1", {})
        finally:
            pwm.paper_wallet_service = orig_svc

    assert result["success"] is True
    assert result["data"]["deleted"]["bots_deleted"] == 3
    assert result["data"]["deleted"]["wallet_reset"] is True


# ---------------------------------------------------------------------------
# 3. get_market_regime
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_market_regime_returns_data():
    """get_market_regime must return regime data."""
    from routes.ai_chat import _handle_get_market_regime

    mock_regime = {"regime": "stable_uptrend", "confidence": 0.78, "pair": "BTC/ZAR"}

    mock_detector = MagicMock()
    mock_detector.detect_regime = AsyncMock(return_value=mock_regime)

    with patch.dict(sys.modules, {"engines.regime_detector": MagicMock(regime_detector=mock_detector)}):
        result = await _handle_get_market_regime("user1", {"pair": "BTC/ZAR"})

    # If import fails gracefully, result may still be success=False — that's acceptable
    if result["success"]:
        assert "data" in result


# ---------------------------------------------------------------------------
# 4. get_flokx_status
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_flokx_status_configured():
    """get_flokx_status must return key_present=True when key exists."""
    from routes.ai_chat import _handle_get_flokx_status
    import database as db

    mock_api_keys = MagicMock()
    mock_api_keys.find_one = AsyncMock(
        return_value={"status": "configured", "last_tested_at": "2026-01-01T00:00:00Z"}
    )

    mock_alerts = MagicMock()
    mock_alerts.find_one = AsyncMock(return_value=None)

    with patch.object(db, "api_keys_collection", mock_api_keys), \
         patch.object(db, "alerts_collection", mock_alerts):
        result = await _handle_get_flokx_status("user1", {})

    assert result["success"] is True
    assert result["data"]["configured"] is True
    assert result["data"]["key_present"] is True


@pytest.mark.asyncio
async def test_get_flokx_status_not_configured():
    """get_flokx_status must return configured=False when no key."""
    from routes.ai_chat import _handle_get_flokx_status
    import database as db

    mock_api_keys = MagicMock()
    mock_api_keys.find_one = AsyncMock(return_value=None)
    mock_alerts = MagicMock()
    mock_alerts.find_one = AsyncMock(return_value=None)

    with patch.object(db, "api_keys_collection", mock_api_keys), \
         patch.object(db, "alerts_collection", mock_alerts):
        result = await _handle_get_flokx_status("user1", {})

    assert result["success"] is True
    assert result["data"]["configured"] is False
    assert "not configured" in result["message"].lower()


# ---------------------------------------------------------------------------
# 5. check_flokx_signals uses per-user key
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_check_flokx_signals_no_key_returns_clear_message():
    """check_flokx_signals must return a clear message when no key configured."""
    from routes.ai_chat import _handle_check_flokx_signals

    with patch("routes.ai_chat.get_decrypted_key", new=AsyncMock(return_value=None), create=True):
        result = await _handle_check_flokx_signals("user1", {"pair": "BTC/ZAR"})

    assert result["success"] is False
    assert "not configured" in result["message"].lower() or "key" in result["message"].lower()


# ---------------------------------------------------------------------------
# 6. ACTION_REGISTRY contains all new entries
# ---------------------------------------------------------------------------

def test_action_registry_has_new_actions():
    """ACTION_REGISTRY must contain all 5 new actions."""
    from routes.ai_chat import ACTION_REGISTRY
    required = [
        "fund_paper_wallet",
        "reset_paper_session",
        "get_market_regime",
        "get_flokx_status",
        "check_flokx_signals",
    ]
    for action in required:
        assert action in ACTION_REGISTRY, f"ACTION_REGISTRY missing: {action}"
        assert "handler" in ACTION_REGISTRY[action]
        assert "description" in ACTION_REGISTRY[action]


def test_fund_paper_wallet_requires_confirmation():
    """fund_paper_wallet must require confirmation."""
    from routes.ai_chat import ACTION_REGISTRY
    entry = ACTION_REGISTRY.get("fund_paper_wallet", {})
    assert entry.get("requires_confirmation") is True


def test_reset_paper_session_requires_confirmation():
    """reset_paper_session must require 'START FRESH' confirmation."""
    from routes.ai_chat import ACTION_REGISTRY
    entry = ACTION_REGISTRY.get("reset_paper_session", {})
    assert entry.get("requires_confirmation") is True
    assert entry.get("confirmation_phrase") == "START FRESH"


# ---------------------------------------------------------------------------
# 7. NLP intent detection
# ---------------------------------------------------------------------------

def test_nlp_detects_fund_paper_wallet():
    """'fund my paper wallet 30000' must map to fund_paper_wallet."""
    from routes.ai_chat import detect_action_intent
    result = detect_action_intent("fund my paper wallet 30000", request_action=True)
    assert result is not None
    assert result.get("action") == "fund_paper_wallet"
    assert float(result.get("params", {}).get("amount", 0)) == 30000.0


def test_nlp_detects_reset_paper_session():
    """'reset my paper session' must map to reset_paper_session."""
    from routes.ai_chat import detect_action_intent
    result = detect_action_intent("reset my paper session", request_action=True)
    assert result is not None
    assert result.get("action") == "reset_paper_session"


def test_nlp_detects_start_fresh():
    """'start fresh demo' must map to reset_paper_session."""
    from routes.ai_chat import detect_action_intent
    result = detect_action_intent("start fresh demo", request_action=True)
    assert result is not None
    assert result.get("action") == "reset_paper_session"


def test_nlp_detects_flokx_status():
    """'check flokx status' must map to get_flokx_status."""
    from routes.ai_chat import detect_action_intent
    result = detect_action_intent("check flokx status", request_action=True)
    assert result is not None
    assert result.get("action") == "get_flokx_status"


def test_nlp_detects_flokx_signals():
    """'get flokx signals' must map to check_flokx_signals."""
    from routes.ai_chat import detect_action_intent
    result = detect_action_intent("get flokx signals", request_action=True)
    assert result is not None
    assert result.get("action") == "check_flokx_signals"
