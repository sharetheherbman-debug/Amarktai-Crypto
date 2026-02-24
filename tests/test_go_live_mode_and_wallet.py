"""
Go-Live Mode and Wallet Tests

Covers:
1. POST /api/system/mode — canonical alias sets flags and persists
2. POST /api/wallet/paper/set-balance — resets then funds wallet
3. Wallet endpoints require auth (401 without token, shape check with mock)
"""

import pytest
import sys
import os
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

# Stub out heavy optional dependencies so tests can import backend modules
# without needing the full production environment installed.
for _mod in ("ccxt", "ccxt.async_support", "ccxt_service", "tenacity"):
    if _mod not in sys.modules:
        sys.modules[_mod] = MagicMock()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_modes_col(initial_doc=None):
    """Return a mock system_modes_collection."""
    stored = [initial_doc] if initial_doc else []

    async def find_one(filt, projection=None):
        user_id = filt.get("user_id")
        for doc in stored:
            if doc.get("user_id") == user_id:
                return doc
        return None

    async def update_one(filt, update, upsert=False):
        user_id = filt.get("user_id")
        set_data = update.get("$set", {})
        for i, doc in enumerate(stored):
            if doc.get("user_id") == user_id:
                stored[i] = {**doc, **set_data}
                return MagicMock(modified_count=1, upserted_id=None)
        if upsert:
            stored.append({**filt, **set_data})
            return MagicMock(modified_count=0, upserted_id="new")
        return MagicMock(modified_count=0, upserted_id=None)

    col = MagicMock()
    col.find_one = AsyncMock(side_effect=find_one)
    col.update_one = AsyncMock(side_effect=update_one)
    col._stored = stored
    return col


def _make_wallets_col(initial_balance=0.0):
    """Return a mock wallets_collection."""
    stored = [{"user_id": "user1", "type": "paper", "balances": {"ZAR": initial_balance}}]

    async def find_one(filt, projection=None):
        return stored[0] if stored else None

    async def find_one_and_update(filt, update, upsert=False, return_document=None):
        inc = update.get("$inc", {})
        set_data = update.get("$set", {})
        doc = stored[0] if stored else {"user_id": "user1", "type": "paper", "balances": {"ZAR": 0.0}}
        if "balances.ZAR" in inc:
            doc["balances"]["ZAR"] = float(doc["balances"].get("ZAR", 0)) + float(inc["balances.ZAR"])
        for k, v in set_data.items():
            if k == "balances":
                doc["balances"] = v
            else:
                doc[k] = v
        if not stored:
            stored.append(doc)
        else:
            stored[0] = doc
        return doc

    async def insert_one(doc):
        stored.append(doc)
        return MagicMock(inserted_id="x")

    col = MagicMock()
    col.find_one = AsyncMock(side_effect=find_one)
    col.find_one_and_update = AsyncMock(side_effect=find_one_and_update)
    col.insert_one = AsyncMock(side_effect=insert_one)
    col.update_one = AsyncMock()
    col._stored = stored
    return col


# ---------------------------------------------------------------------------
# 1. POST /api/system/mode — canonical alias
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_set_mode_paper_persists():
    """POST /mode with paper_trading=True must persist paperTrading=True."""
    from routes.system_mode import set_mode, ModeSetRequest
    modes_col = _make_modes_col()

    with patch("database.system_modes_collection", modes_col):
        result = await set_mode(
            ModeSetRequest(paper_trading=True, live_trading=False, autonomous=False),
            user_id="user1"
        )

    assert result["success"] is True
    assert result["paperTrading"] is True
    assert result["liveTrading"] is False
    assert result["mode"] == "paper"
    # Persisted to DB
    saved = modes_col._stored[0]
    assert saved["paperTrading"] is True
    assert saved["liveTrading"] is False


@pytest.mark.asyncio
async def test_set_mode_paper_and_autonomous():
    """POST /mode with paper_trading=True + autonomous=True persists both flags."""
    from routes.system_mode import set_mode, ModeSetRequest
    modes_col = _make_modes_col()

    with patch("database.system_modes_collection", modes_col):
        result = await set_mode(
            ModeSetRequest(paper_trading=True, live_trading=False, autonomous=True),
            user_id="user1"
        )

    assert result["success"] is True
    assert result["paperTrading"] is True
    assert result["autopilot"] is True
    assert result["mode"] == "paper"
    saved = modes_col._stored[0]
    assert saved["autopilot"] is True


@pytest.mark.asyncio
async def test_set_mode_exclusivity_raises_400():
    """POST /mode with both paper_trading=True and live_trading=True must return 400."""
    from fastapi import HTTPException
    from routes.system_mode import set_mode, ModeSetRequest
    modes_col = _make_modes_col()

    with patch("database.system_modes_collection", modes_col):
        with pytest.raises(HTTPException) as exc_info:
            await set_mode(
                ModeSetRequest(paper_trading=True, live_trading=True, autonomous=False),
                user_id="user1"
            )

    assert exc_info.value.status_code == 400
    assert "mutually exclusive" in exc_info.value.detail


@pytest.mark.asyncio
async def test_set_mode_live_blocked_when_disabled():
    """POST /mode with live_trading=True must 403 when ENABLE_LIVE_TRADING is false."""
    from fastapi import HTTPException
    from routes.system_mode import set_mode, ModeSetRequest
    modes_col = _make_modes_col()

    with patch("database.system_modes_collection", modes_col), \
         patch("routes.system_mode.live_trading_enabled", return_value=False):
        with pytest.raises(HTTPException) as exc_info:
            await set_mode(
                ModeSetRequest(paper_trading=False, live_trading=True, autonomous=False),
                user_id="user1"
            )

    assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_set_mode_disabled_returns_disabled():
    """POST /mode with all flags False stores disabled state."""
    from routes.system_mode import set_mode, ModeSetRequest
    modes_col = _make_modes_col()

    with patch("database.system_modes_collection", modes_col):
        result = await set_mode(
            ModeSetRequest(paper_trading=False, live_trading=False, autonomous=False),
            user_id="user1"
        )

    assert result["mode"] == "disabled"
    assert result["paperTrading"] is False
    assert result["liveTrading"] is False


# ---------------------------------------------------------------------------
# 2. POST /api/wallet/paper/set-balance
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_set_balance_funds_to_30000():
    """POST /paper/set-balance with 30000 must result in wallet showing 30000 ZAR."""
    import services.paper_wallet_service as pwm
    from routes.wallet_hub import set_paper_wallet_balance, PaperSetBalanceRequest

    wallets_col = _make_wallets_col(initial_balance=0.0)
    wb_col = MagicMock()
    wb_col.update_one = AsyncMock()

    _summary = {"mode": "paper", "available_wallet_zar": 30000.0,
                "allocated_funds_zar": 0.0, "reserved_funds_zar": 0.0,
                "required_funds_zar": 0.0, "shortfall_zar": 0.0, "status": "ok"}

    with patch("database.wallets_collection", wallets_col), \
         patch("database.wallet_balances_collection", wb_col), \
         patch("routes.wallet_hub.wallet_summary_service.get_summary",
               new=AsyncMock(return_value=_summary)), \
         patch("routes.wallet_hub.get_paper_wallet_allocated_balances",
               new=AsyncMock(return_value={})), \
         patch("routes.wallet_hub.get_paper_wallet_balances",
               new=AsyncMock(return_value={"ZAR": 30000.0})):
        orig = pwm.paper_wallet_service.collection
        pwm.paper_wallet_service.collection = wallets_col
        try:
            result = await set_paper_wallet_balance(
                PaperSetBalanceRequest(balance_zar=30000.0),
                user_id="user1"
            )
        finally:
            pwm.paper_wallet_service.collection = orig

    assert result["success"] is True
    assert result["set_to"] == 30000.0
    balance_in_store = wallets_col._stored[0]["balances"]["ZAR"]
    assert float(balance_in_store) == 30000.0


@pytest.mark.asyncio
async def test_set_balance_negative_raises_400():
    """POST /paper/set-balance with negative amount must return 400."""
    from fastapi import HTTPException
    from routes.wallet_hub import set_paper_wallet_balance, PaperSetBalanceRequest

    wallets_col = _make_wallets_col(initial_balance=0.0)
    wb_col = MagicMock()
    wb_col.update_one = AsyncMock()

    import services.paper_wallet_service as pwm
    orig = pwm.paper_wallet_service.collection

    with patch("database.wallets_collection", wallets_col), \
         patch("database.wallet_balances_collection", wb_col):
        pwm.paper_wallet_service.collection = wallets_col
        try:
            with pytest.raises(HTTPException) as exc_info:
                await set_paper_wallet_balance(
                    PaperSetBalanceRequest(balance_zar=-100.0),
                    user_id="user1"
                )
        finally:
            pwm.paper_wallet_service.collection = orig

    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_set_balance_zero_clears_wallet():
    """POST /paper/set-balance with 0 must reset wallet to zero."""
    import services.paper_wallet_service as pwm
    from routes.wallet_hub import set_paper_wallet_balance, PaperSetBalanceRequest

    wallets_col = _make_wallets_col(initial_balance=50000.0)
    wb_col = MagicMock()
    wb_col.update_one = AsyncMock()

    _summary = {"mode": "paper", "available_wallet_zar": 0.0,
                "allocated_funds_zar": 0.0, "reserved_funds_zar": 0.0,
                "required_funds_zar": 0.0, "shortfall_zar": 0.0, "status": "ok"}

    with patch("database.wallets_collection", wallets_col), \
         patch("database.wallet_balances_collection", wb_col), \
         patch("routes.wallet_hub.wallet_summary_service.get_summary",
               new=AsyncMock(return_value=_summary)), \
         patch("routes.wallet_hub.get_paper_wallet_allocated_balances",
               new=AsyncMock(return_value={})), \
         patch("routes.wallet_hub.get_paper_wallet_balances",
               new=AsyncMock(return_value={"ZAR": 0.0})):
        orig = pwm.paper_wallet_service.collection
        pwm.paper_wallet_service.collection = wallets_col
        try:
            result = await set_paper_wallet_balance(
                PaperSetBalanceRequest(balance_zar=0.0),
                user_id="user1"
            )
        finally:
            pwm.paper_wallet_service.collection = orig

    assert result["success"] is True
    assert result["set_to"] == 0.0
    balance_in_store = wallets_col._stored[0]["balances"]["ZAR"]
    assert float(balance_in_store) == 0.0


# ---------------------------------------------------------------------------
# 3. Wallet endpoint auth model — routes use get_current_user (Bearer)
# ---------------------------------------------------------------------------

def test_wallet_hub_uses_get_current_user():
    """All wallet hub route handlers must depend on get_current_user."""
    from routes import wallet_hub
    from auth import get_current_user
    from fastapi import params

    # Inspect route handlers that must require auth
    protected = [
        wallet_hub.get_wallet_status_v2,
        wallet_hub.get_paper_wallet,
        wallet_hub.set_paper_wallet_balance,
        wallet_hub.reset_paper_wallet,
        wallet_hub.fund_paper_wallet,
    ]
    for handler in protected:
        deps = getattr(handler, "__dependencies__", []) or []
        # FastAPI stores dependencies in __wrapped__ or in the signature
        import inspect
        sig = inspect.signature(handler)
        dep_funcs = [
            p.default.dependency
            for p in sig.parameters.values()
            if isinstance(p.default, params.Depends)
        ]
        assert get_current_user in dep_funcs, (
            f"{handler.__name__} must depend on get_current_user "
            f"(same as /api/system/status and /api/risk/status)"
        )


def test_system_mode_post_uses_get_current_user():
    """POST /api/system/mode must depend on get_current_user."""
    from routes import system_mode
    from auth import get_current_user
    from fastapi import params
    import inspect

    sig = inspect.signature(system_mode.set_mode)
    dep_funcs = [
        p.default.dependency
        for p in sig.parameters.values()
        if isinstance(p.default, params.Depends)
    ]
    assert get_current_user in dep_funcs, (
        "set_mode (POST /api/system/mode) must depend on get_current_user"
    )


# ---------------------------------------------------------------------------
# 4. POST /api/user/paper-start-fresh
# ---------------------------------------------------------------------------

def _make_bots_col(paper_bots=3):
    """Mock bots collection with some paper bots."""
    stored = [
        {"id": f"bot_{i}", "user_id": "user1", "trading_mode": "paper"}
        for i in range(paper_bots)
    ]

    async def update_many(filt, update, upsert=False):
        count = 0
        for doc in stored:
            if doc.get("user_id") == filt.get("user_id") and doc.get("trading_mode") == "paper":
                doc.update(update.get("$set", {}))
                count += 1
        return MagicMock(modified_count=count)

    async def find_many(filt, projection=None):
        return [d for d in stored if d.get("deletion_reason") == "user_paper_start_fresh"]

    col = MagicMock()
    col.update_many = AsyncMock(side_effect=update_many)
    col.find = MagicMock(return_value=MagicMock(to_list=AsyncMock(side_effect=lambda n: find_many({}))))
    col._stored = stored
    return col


def _make_null_col():
    """Mock collection that returns empty for all ops."""
    col = MagicMock()
    col.find_one = AsyncMock(return_value=None)
    col.update_one = AsyncMock(return_value=MagicMock(modified_count=0))
    col.update_many = AsyncMock(return_value=MagicMock(modified_count=0))
    col.delete_many = AsyncMock(return_value=MagicMock(deleted_count=0))
    col.insert_one = AsyncMock(return_value=MagicMock(inserted_id="x"))
    col.find = MagicMock(return_value=MagicMock(to_list=AsyncMock(return_value=[])))
    return col


@pytest.mark.asyncio
async def test_user_paper_start_fresh_ok():
    """POST /user/paper-start-fresh with valid phrase returns ok=True."""
    from routes.admin_start_fresh import user_paper_start_fresh, StartFreshRequest

    bots_col = _make_null_col()
    trades_col = _make_null_col()
    orders_col = _make_null_col()
    users_col = _make_null_col()
    audit_col = _make_null_col()

    mock_wallet_result = {"wallet_before": {"ZAR": 30000}, "wallet_after": {"ZAR": 0}}

    import services.paper_wallet_service as pwm
    orig_reset = pwm.paper_wallet_service.reset

    async def fake_reset(uid):
        return mock_wallet_result

    pwm.paper_wallet_service.reset = fake_reset
    try:
        with patch("database.bots_collection", bots_col), \
             patch("database.trades_collection", trades_col), \
             patch("database.orders_collection", orders_col), \
             patch("database.users_collection", users_col), \
             patch("database.audit_logs_collection", audit_col), \
             patch("database.wallet_balances_collection", _make_null_col()), \
             patch("database.capital_injections_collection", _make_null_col()), \
             patch("database.paper_ledger_collection", None), \
             patch("database.bot_metrics_collection", None), \
             patch("database.bot_runtime_state_collection", None), \
             patch("database.bot_lifecycle_collection", None), \
             patch("database.performance_metrics_collection", None), \
             patch("database.balance_snapshots_collection", None):
            result = await user_paper_start_fresh(
                StartFreshRequest(
                    confirmation_phrase="START FRESH",
                    scope="paper_only",
                    also_reset_risk_locks=True,
                ),
                user_id="user1",
            )
    finally:
        pwm.paper_wallet_service.reset = orig_reset

    assert result["ok"] is True
    assert "deleted" in result
    assert result["wallet_after"] == {"ZAR": 0}


@pytest.mark.asyncio
async def test_user_paper_start_fresh_wrong_phrase():
    """POST /user/paper-start-fresh with wrong phrase raises 400."""
    from fastapi import HTTPException
    from routes.admin_start_fresh import user_paper_start_fresh, StartFreshRequest

    with pytest.raises(HTTPException) as exc_info:
        await user_paper_start_fresh(
            StartFreshRequest(confirmation_phrase="WRONG", scope="paper_only"),
            user_id="user1",
        )

    assert exc_info.value.status_code == 400


def test_user_paper_start_fresh_uses_get_current_user():
    """POST /api/user/paper-start-fresh must depend on get_current_user (not require_admin)."""
    from routes import admin_start_fresh
    from auth import get_current_user, require_admin
    from fastapi import params
    import inspect

    sig = inspect.signature(admin_start_fresh.user_paper_start_fresh)
    dep_funcs = [
        p.default.dependency
        for p in sig.parameters.values()
        if isinstance(p.default, params.Depends)
    ]
    assert get_current_user in dep_funcs, (
        "user_paper_start_fresh must depend on get_current_user"
    )
    assert require_admin not in dep_funcs, (
        "user_paper_start_fresh must NOT depend on require_admin"
    )
