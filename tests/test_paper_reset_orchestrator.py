"""
Tests for the paper reset orchestrator and related reset flows.

Validates:
1. After paper reset, drawdown=0% and equity_peak == current_capital for surviving bots.
2. After reset, daily_capital_baseline is initialised so the first tick does NOT
   trip the circuit breaker.
3. Paper fills deletion actually deletes the right documents (fills_deleted > 0
   when fills exist).
4. Bot diagnostics endpoint returns required performance/circuit-breaker fields.
5. The orchestrator is called by all three reset surfaces
   (admin start-fresh, user paper-start-fresh, paper-sandbox/reset).
"""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, call
from datetime import datetime, timezone


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_bot(
    bot_id: str,
    user_id: str = "user_test",
    current_capital: float = 500.0,
    equity_peak: float = 1000.0,
    status: str = "active",
    trading_mode: str = "paper",
    daily_capital_baseline: float = 1000.0,
    daily_baseline_date: str = "2020-01-01",
    last_order_error: str = "Circuit breaker: daily loss limit exceeded",
) -> dict:
    return {
        "id": bot_id,
        "user_id": user_id,
        "name": f"Bot {bot_id}",
        "exchange": "luno",
        "trading_mode": trading_mode,
        "status": status,
        "current_capital": current_capital,
        "initial_capital": 1000.0,
        "equity_peak": equity_peak,
        "daily_capital_baseline": daily_capital_baseline,
        "daily_baseline_date": daily_baseline_date,
        "last_order_error": last_order_error,
        "paused_by_bodyguard": False,
        "paused_by_system": False,
    }


# ---------------------------------------------------------------------------
# Unit tests for the orchestrator itself (no server required)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_orchestrator_resets_equity_peak_on_surviving_bots():
    """After run(), surviving bots must have equity_peak == current_capital."""
    from services.paper_reset_orchestrator import run

    user_id = "orch_test_user"
    bot = _make_bot("bot_alive", user_id=user_id, current_capital=500.0, equity_peak=1000.0)

    # Mock DB so no real MongoDB needed
    mock_active_bots_cursor = MagicMock()
    mock_active_bots_cursor.to_list = AsyncMock(return_value=[bot])

    mock_surviving_bots_cursor = MagicMock()
    mock_surviving_bots_cursor.to_list = AsyncMock(return_value=[bot])

    # Track which update_one calls happened
    update_one_calls = []

    async def _mock_update_one(filt, update, *args, **kwargs):
        update_one_calls.append((filt, update))
        return MagicMock(modified_count=1)

    mock_bots_col = MagicMock()
    mock_bots_col.find = MagicMock(return_value=mock_active_bots_cursor)
    mock_bots_col.update_many = AsyncMock(return_value=MagicMock(modified_count=1))
    mock_bots_col.update_one = _mock_update_one
    mock_bots_col.count_documents = AsyncMock(return_value=0)

    mock_trades_col = MagicMock()
    mock_trades_col.delete_many = AsyncMock(return_value=MagicMock(deleted_count=0))
    mock_trades_col.count_documents = AsyncMock(return_value=0)

    mock_orders_col = MagicMock()
    mock_orders_col.delete_many = AsyncMock(return_value=MagicMock(deleted_count=0))

    mock_users_col = MagicMock()
    mock_users_col.update_one = AsyncMock(return_value=MagicMock(modified_count=1))

    # Both the "active bots to delete" and "surviving bots" queries return the
    # same bot document for simplicity — the important assertions are on the
    # fields that get updated (equity_peak, daily_capital_baseline, etc.).
    def _find_side_effect(filt, projection=None):
        c = MagicMock()
        c.to_list = AsyncMock(return_value=[bot])
        return c

    mock_bots_col.find = _find_side_effect

    with patch("services.paper_reset_orchestrator.db") as mock_db:
        mock_db.bots_collection = mock_bots_col
        mock_db.trades_collection = mock_trades_col
        mock_db.orders_collection = mock_orders_col
        mock_db.users_collection = mock_users_col
        mock_db.bot_metrics_collection = MagicMock()
        mock_db.bot_metrics_collection.delete_many = AsyncMock(return_value=MagicMock(deleted_count=0))
        mock_db.balance_snapshots_collection = None
        mock_db.paper_ledger_collection = None
        mock_db.bot_runtime_state_collection = None
        mock_db.bot_lifecycle_collection = None
        mock_db.performance_metrics_collection = None
        mock_db.wallet_balances_collection = None
        mock_db.capital_injections_collection = None
        mock_db.user_countdowns_collection = None
        mock_db.paper_reset_baselines_collection = None
        mock_db.db = None  # no raw db

        result = await run(user_id=user_id, scope="paper_only", also_reset_risk_locks=True)

    # At least one update_one should have set equity_peak = current_capital
    equity_peak_resets = [
        u for (f, u) in update_one_calls
        if u.get("$set", {}).get("equity_peak") is not None
    ]
    assert len(equity_peak_resets) >= 1, (
        "orchestrator must reset equity_peak on surviving bots; "
        f"update_one calls were: {update_one_calls}"
    )

    # equity_peak must be set to current_capital (500.0)
    first_reset = equity_peak_resets[0]
    assert first_reset["$set"]["equity_peak"] == 500.0, (
        f"equity_peak should be 500.0 (current_capital), got {first_reset['$set']['equity_peak']}"
    )
    assert first_reset["$set"]["current_drawdown_pct"] == 0.0


@pytest.mark.asyncio
async def test_orchestrator_resets_daily_baseline_to_today():
    """After run(), surviving bots must have daily_capital_baseline = current_capital
    and daily_baseline_date = today (UTC)."""
    from services.paper_reset_orchestrator import run

    user_id = "orch_baseline_user"
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    bot = _make_bot(
        "bot_baseline",
        user_id=user_id,
        current_capital=800.0,
        equity_peak=1000.0,
        daily_capital_baseline=1000.0,
        daily_baseline_date="2020-01-01",  # stale
    )

    update_one_calls = []

    async def _mock_update_one(filt, update, *args, **kwargs):
        update_one_calls.append((filt, update))
        return MagicMock(modified_count=1)

    mock_bots_col = MagicMock()
    mock_bots_col.update_many = AsyncMock(return_value=MagicMock(modified_count=1))
    mock_bots_col.update_one = _mock_update_one
    mock_bots_col.count_documents = AsyncMock(return_value=0)

    call_count = [0]
    def _find_side_effect(filt, projection=None):
        c = MagicMock()
        call_count[0] += 1
        c.to_list = AsyncMock(return_value=[bot])
        return c

    mock_bots_col.find = _find_side_effect

    with patch("services.paper_reset_orchestrator.db") as mock_db:
        mock_db.bots_collection = mock_bots_col
        mock_db.trades_collection = MagicMock()
        mock_db.trades_collection.delete_many = AsyncMock(return_value=MagicMock(deleted_count=0))
        mock_db.trades_collection.count_documents = AsyncMock(return_value=0)
        mock_db.orders_collection = MagicMock()
        mock_db.orders_collection.delete_many = AsyncMock(return_value=MagicMock(deleted_count=0))
        mock_db.bot_metrics_collection = MagicMock()
        mock_db.bot_metrics_collection.delete_many = AsyncMock(return_value=MagicMock(deleted_count=0))
        mock_db.users_collection = MagicMock()
        mock_db.users_collection.update_one = AsyncMock(return_value=MagicMock(modified_count=1))
        mock_db.balance_snapshots_collection = None
        mock_db.paper_ledger_collection = None
        mock_db.bot_runtime_state_collection = None
        mock_db.bot_lifecycle_collection = None
        mock_db.performance_metrics_collection = None
        mock_db.wallet_balances_collection = None
        mock_db.capital_injections_collection = None
        mock_db.user_countdowns_collection = None
        mock_db.paper_reset_baselines_collection = None
        mock_db.db = None

        await run(user_id=user_id, scope="paper_only")

    baseline_resets = [
        u for (f, u) in update_one_calls
        if u.get("$set", {}).get("daily_capital_baseline") is not None
    ]
    assert len(baseline_resets) >= 1, "orchestrator must reset daily_capital_baseline"

    reset_set = baseline_resets[0]["$set"]
    assert reset_set["daily_capital_baseline"] == 800.0, (
        f"daily_capital_baseline should be 800.0 (current_capital), got {reset_set['daily_capital_baseline']}"
    )
    assert reset_set["daily_baseline_date"] == today_str, (
        f"daily_baseline_date should be today ({today_str}), got {reset_set['daily_baseline_date']}"
    )


@pytest.mark.asyncio
async def test_orchestrator_deletes_paper_fills():
    """Orchestrator must delete fills_ledger documents tagged is_paper=True."""
    from services.paper_reset_orchestrator import run

    user_id = "orch_fills_user"
    bot = _make_bot("bot_fills", user_id=user_id)

    fill_delete_calls = []

    async def _fills_delete(filt):
        fill_delete_calls.append(filt)
        return MagicMock(deleted_count=5)

    mock_fills_ledger = MagicMock()
    mock_fills_ledger.delete_many = _fills_delete

    def _raw_db_getitem(self, name):
        if name == "fills_ledger":
            return mock_fills_ledger
        m = MagicMock()
        m.delete_many = AsyncMock(return_value=MagicMock(deleted_count=0))
        return m

    mock_raw_db = MagicMock()
    mock_raw_db.__getitem__ = _raw_db_getitem

    mock_bots_col = MagicMock()
    mock_bots_col.update_many = AsyncMock(return_value=MagicMock(modified_count=1))
    mock_bots_col.update_one = AsyncMock(return_value=MagicMock(modified_count=1))
    mock_bots_col.count_documents = AsyncMock(return_value=0)

    def _find_side(filt, projection=None):
        c = MagicMock()
        c.to_list = AsyncMock(return_value=[bot])
        return c

    mock_bots_col.find = _find_side

    with patch("services.paper_reset_orchestrator.db") as mock_db:
        mock_db.bots_collection = mock_bots_col
        mock_db.trades_collection = MagicMock()
        mock_db.trades_collection.delete_many = AsyncMock(return_value=MagicMock(deleted_count=0))
        mock_db.trades_collection.count_documents = AsyncMock(return_value=0)
        mock_db.orders_collection = MagicMock()
        mock_db.orders_collection.delete_many = AsyncMock(return_value=MagicMock(deleted_count=0))
        mock_db.bot_metrics_collection = MagicMock()
        mock_db.bot_metrics_collection.delete_many = AsyncMock(return_value=MagicMock(deleted_count=0))
        mock_db.users_collection = MagicMock()
        mock_db.users_collection.update_one = AsyncMock(return_value=MagicMock(modified_count=1))
        mock_db.balance_snapshots_collection = None
        mock_db.paper_ledger_collection = None
        mock_db.bot_runtime_state_collection = None
        mock_db.bot_lifecycle_collection = None
        mock_db.performance_metrics_collection = None
        mock_db.wallet_balances_collection = None
        mock_db.capital_injections_collection = None
        mock_db.user_countdowns_collection = None
        mock_db.paper_reset_baselines_collection = None
        mock_db.db = mock_raw_db

        result = await run(user_id=user_id, scope="paper_only")

    assert result["fills_deleted"] > 0, (
        "orchestrator must report fills_deleted > 0 when fills exist; "
        f"result was {result}"
    )

    paper_fill_deletes = [
        f for f in fill_delete_calls
        if f.get("is_paper") is True and f.get("user_id") == user_id
    ]
    assert len(paper_fill_deletes) >= 1, (
        "orchestrator must delete fills_ledger with is_paper=True filter"
    )


@pytest.mark.asyncio
async def test_orchestrator_resets_last_order_error():
    """After run(), surviving bots must have last_order_error cleared."""
    from services.paper_reset_orchestrator import run

    user_id = "orch_error_user"
    bot = _make_bot(
        "bot_error",
        user_id=user_id,
        last_order_error="Circuit breaker: daily loss limit exceeded",
    )

    unset_calls = []

    async def _mock_update_one(filt, update, *args, **kwargs):
        unset_calls.append(update.get("$unset", {}))
        return MagicMock(modified_count=1)

    mock_bots_col = MagicMock()
    mock_bots_col.update_many = AsyncMock(return_value=MagicMock(modified_count=1))
    mock_bots_col.update_one = _mock_update_one
    mock_bots_col.count_documents = AsyncMock(return_value=0)

    def _find_side(filt, projection=None):
        c = MagicMock()
        c.to_list = AsyncMock(return_value=[bot])
        return c

    mock_bots_col.find = _find_side

    with patch("services.paper_reset_orchestrator.db") as mock_db:
        mock_db.bots_collection = mock_bots_col
        mock_db.trades_collection = MagicMock()
        mock_db.trades_collection.delete_many = AsyncMock(return_value=MagicMock(deleted_count=0))
        mock_db.trades_collection.count_documents = AsyncMock(return_value=0)
        mock_db.orders_collection = MagicMock()
        mock_db.orders_collection.delete_many = AsyncMock(return_value=MagicMock(deleted_count=0))
        mock_db.bot_metrics_collection = MagicMock()
        mock_db.bot_metrics_collection.delete_many = AsyncMock(return_value=MagicMock(deleted_count=0))
        mock_db.users_collection = MagicMock()
        mock_db.users_collection.update_one = AsyncMock(return_value=MagicMock(modified_count=1))
        mock_db.balance_snapshots_collection = None
        mock_db.paper_ledger_collection = None
        mock_db.bot_runtime_state_collection = None
        mock_db.bot_lifecycle_collection = None
        mock_db.performance_metrics_collection = None
        mock_db.wallet_balances_collection = None
        mock_db.capital_injections_collection = None
        mock_db.user_countdowns_collection = None
        mock_db.paper_reset_baselines_collection = None
        mock_db.db = None

        await run(user_id=user_id, scope="paper_only")

    # At least one $unset should include last_order_error
    last_order_error_unsets = [
        u for u in unset_calls if "last_order_error" in u
    ]
    assert len(last_order_error_unsets) >= 1, (
        "orchestrator must $unset last_order_error on surviving bots"
    )


# ---------------------------------------------------------------------------
# Tests for bot diagnostics endpoint fields
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_bot_diagnostics_returns_performance_and_circuit_breaker_fields(
    client, admin_token
):
    """GET /api/bots/{bot_id}/diagnostics must return performance and
    circuit_breaker sub-objects with required fields."""
    import sys
    from server import app
    from auth import get_current_user

    bot_id = "diag_test_bot"
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    _bot_doc = {
        "id": bot_id,
        "user_id": "admin_user_test",
        "name": "Diag Bot",
        "exchange": "luno",
        "status": "active",
        "trading_mode": "paper",
        "current_capital": 500.0,
        "initial_capital": 1000.0,
        "equity_peak": 500.0,  # reset properly → drawdown=0
        "daily_capital_baseline": 500.0,
        "daily_baseline_date": today_str,
        "circuit_breaker_loss_pct": 0.10,
        "max_drawdown_pct": 0.15,
        "last_order_error": None,
        "paused_by_bodyguard": False,
        "paused_by_system": False,
    }

    # Stub engines.trade_budget_manager and services.bodyguard_service at sys.modules level
    # so local imports inside the endpoint function pick them up.
    mock_tbm_instance = MagicMock()
    mock_tbm_instance.calculate_bot_daily_budget = AsyncMock(return_value=50)
    mock_tbm_instance.get_bot_remaining_budget = AsyncMock(return_value=50)
    mock_tbm_instance.can_execute_trade = AsyncMock(return_value=(True, "OK"))

    mock_bg_instance = MagicMock()
    mock_bg_instance.get_bot_drawdown_status = AsyncMock(return_value={})

    mock_tbm_mod = MagicMock()
    mock_tbm_mod.trade_budget_manager = mock_tbm_instance
    mock_bg_mod = MagicMock()
    mock_bg_mod.bodyguard_service = mock_bg_instance

    def _dep():
        return "admin_user_test"

    app.dependency_overrides[get_current_user] = _dep
    try:
        with patch("routes.bot_lifecycle.db") as mock_db, \
             patch.dict(sys.modules, {
                 "engines.trade_budget_manager": mock_tbm_mod,
                 "services.bodyguard_service": mock_bg_mod,
             }):

            mock_db.bots_collection = MagicMock()
            mock_db.bots_collection.find_one = AsyncMock(return_value=_bot_doc)
            mock_db.users_collection = MagicMock()
            mock_db.users_collection.find_one = AsyncMock(return_value={
                "id": "admin_user_test",
                "emergency_stop": False,
                "autopilot_enabled": True,
            })
            mock_db.api_keys_collection = MagicMock()
            mock_db.api_keys_collection.find_one = AsyncMock(return_value=None)

            response = client.get(
                f"/api/bots/{bot_id}/diagnostics",
                headers={"Authorization": f"Bearer {admin_token}"},
            )

        assert response.status_code == 200, response.text
        data = response.json()

        # Required top-level keys
        assert "performance" in data, "diagnostics must include 'performance'"
        assert "circuit_breaker" in data, "diagnostics must include 'circuit_breaker'"

        perf = data["performance"]
        assert "current_equity" in perf
        assert "equity_peak" in perf
        assert "computed_drawdown_pct" in perf
        assert "daily_capital_baseline" in perf
        assert "daily_baseline_date" in perf
        assert "daily_pnl_pct" in perf

        cb = data["circuit_breaker"]
        assert "daily_loss_limit_pct" in cb
        assert "max_drawdown_limit_pct" in cb
        assert "would_trip_daily_loss" in cb
        assert "would_trip_max_drawdown" in cb
        assert "next_action" in cb

        # With equity_peak == current_capital, drawdown must be 0
        assert perf["computed_drawdown_pct"] == 0.0, (
            f"drawdown should be 0 when equity_peak==current_capital; got {perf['computed_drawdown_pct']}"
        )
        assert cb["would_trip_daily_loss"] is False

    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_bot_diagnostics_circuit_breaker_trips_when_baseline_stale(
    client, admin_token
):
    """Circuit breaker 'would_trip_daily_loss' must be True when daily loss
    exceeds the limit due to a stale baseline."""
    import sys
    from server import app
    from auth import get_current_user

    bot_id = "cb_trip_bot"

    _bot_doc = {
        "id": bot_id,
        "user_id": "admin_user_test",
        "name": "CB Bot",
        "exchange": "luno",
        "status": "active",
        "trading_mode": "paper",
        "current_capital": 500.0,
        "initial_capital": 1000.0,
        "equity_peak": 1000.0,
        "daily_capital_baseline": 1000.0,   # high baseline vs current 500 → -50% loss
        "daily_baseline_date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "circuit_breaker_loss_pct": 0.10,   # 10% limit
        "max_drawdown_pct": 0.15,
        "last_order_error": "Circuit breaker: daily loss limit exceeded",
        "paused_by_bodyguard": False,
        "paused_by_system": False,
    }

    def _dep():
        return "admin_user_test"

    app.dependency_overrides[get_current_user] = _dep
    try:
        mock_tbm_instance2 = MagicMock()
        mock_tbm_instance2.calculate_bot_daily_budget = AsyncMock(return_value=50)
        mock_tbm_instance2.get_bot_remaining_budget = AsyncMock(return_value=50)
        mock_tbm_instance2.can_execute_trade = AsyncMock(return_value=(True, "OK"))
        mock_bg_instance2 = MagicMock()
        mock_bg_instance2.get_bot_drawdown_status = AsyncMock(return_value={})
        mock_tbm_mod2 = MagicMock()
        mock_tbm_mod2.trade_budget_manager = mock_tbm_instance2
        mock_bg_mod2 = MagicMock()
        mock_bg_mod2.bodyguard_service = mock_bg_instance2

        with patch("routes.bot_lifecycle.db") as mock_db, \
             patch.dict(sys.modules, {
                 "engines.trade_budget_manager": mock_tbm_mod2,
                 "services.bodyguard_service": mock_bg_mod2,
             }):

            mock_db.bots_collection = MagicMock()
            mock_db.bots_collection.find_one = AsyncMock(return_value=_bot_doc)
            mock_db.users_collection = MagicMock()
            mock_db.users_collection.find_one = AsyncMock(return_value={
                "id": "admin_user_test",
                "emergency_stop": False,
                "autopilot_enabled": True,
            })
            mock_db.api_keys_collection = MagicMock()
            mock_db.api_keys_collection.find_one = AsyncMock(return_value=None)

            response = client.get(
                f"/api/bots/{bot_id}/diagnostics",
                headers={"Authorization": f"Bearer {admin_token}"},
            )

        assert response.status_code == 200, response.text
        data = response.json()

        cb = data["circuit_breaker"]
        assert cb["would_trip_daily_loss"] is True, (
            "circuit breaker should trip when current_capital=500 < baseline=1000 "
            "with 10% daily loss limit"
        )
        # The diagnostics reasons must explain WHY the bot is paused
        assert any("circuit breaker" in r.lower() or "daily loss" in r.lower()
                   for r in data.get("reasons", [])), (
            f"reasons must mention circuit breaker; got {data.get('reasons')}"
        )
        # next_action must suggest a recovery path
        assert "reset" in cb["next_action"].lower(), (
            f"next_action should mention reset; got {cb['next_action']}"
        )

    finally:
        app.dependency_overrides.pop(get_current_user, None)


# ---------------------------------------------------------------------------
# Integration: admin start-fresh uses orchestrator
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_admin_start_fresh_delegates_to_orchestrator(client, admin_token):
    """POST /api/admin/start-fresh must call the orchestrator and return ok=True."""
    from server import app
    from auth import require_admin

    def _admin_dep():
        return "admin_user_test"

    app.dependency_overrides[require_admin] = _admin_dep
    try:
        mock_result = {
            "bots_soft_deleted": 5,
            "trades_deleted": 20,
            "orders_deleted": 15,
            "fills_deleted": 30,
            "telemetry_deleted": 5,
            "risk_locks_reset": 1,
            "wallet_before": {},
            "wallet_after": {},
            "warnings": [],
            "post_reset": {},
        }

        with patch("routes.admin_start_fresh._orchestrator_run", new=AsyncMock(return_value=mock_result)), \
             patch("routes.admin_start_fresh.db") as mock_db:
            mock_db.training_jobs_collection = MagicMock()
            mock_db.training_jobs_collection.delete_many = AsyncMock()
            mock_db.audit_logs_collection = MagicMock()
            mock_db.audit_logs_collection.insert_one = AsyncMock()

            response = client.post(
                "/api/admin/start-fresh",
                json={"confirmation_phrase": "START FRESH", "scope": "paper_only"},
                headers={"Authorization": f"Bearer {admin_token}"},
            )

        assert response.status_code == 200, response.text
        data = response.json()
        assert data["ok"] is True
        assert data["deleted"]["bots_deleted"] == 5
        assert data["deleted"]["fills_deleted"] == 30

    finally:
        app.dependency_overrides.pop(require_admin, None)


# ---------------------------------------------------------------------------
# Integration: user paper-start-fresh uses orchestrator
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_user_paper_start_fresh_delegates_to_orchestrator(client, normal_user_token):
    """POST /api/user/paper-start-fresh must call the orchestrator."""
    from server import app
    from auth import get_current_user

    def _user_dep():
        return "normal_user_test"

    app.dependency_overrides[get_current_user] = _user_dep
    try:
        mock_result = {
            "bots_soft_deleted": 3,
            "trades_deleted": 10,
            "orders_deleted": 8,
            "fills_deleted": 12,
            "telemetry_deleted": 3,
            "risk_locks_reset": 1,
            "wallet_before": {},
            "wallet_after": {},
            "warnings": [],
            "post_reset": {"active_bots": 0},
        }

        with patch("routes.admin_start_fresh._orchestrator_run", new=AsyncMock(return_value=mock_result)):
            response = client.post(
                "/api/user/paper-start-fresh",
                json={"confirmation_phrase": "START FRESH"},
                headers={"Authorization": f"Bearer {normal_user_token}"},
            )

        assert response.status_code == 200, response.text
        data = response.json()
        assert data["ok"] is True
        assert data["deleted"]["bots_deleted"] == 3

    finally:
        app.dependency_overrides.pop(get_current_user, None)


# ---------------------------------------------------------------------------
# Integration: paper-sandbox/reset uses orchestrator
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_paper_sandbox_reset_delegates_to_orchestrator(client, normal_user_token):
    """POST /api/system/paper-sandbox/reset must call the orchestrator."""
    from server import app
    from auth import get_current_user

    def _user_dep():
        return "normal_user_test"

    app.dependency_overrides[get_current_user] = _user_dep
    try:
        mock_result = {
            "bots_soft_deleted": 2,
            "fills_deleted": 7,
            "warnings": [],
        }

        with patch("routes.system._orchestrator_run", new=AsyncMock(return_value=mock_result)), \
             patch("routes.system.db") as mock_db:
            mock_db.audit_logs_collection = MagicMock()
            mock_db.audit_logs_collection.insert_one = AsyncMock()

            response = client.post(
                "/api/system/paper-sandbox/reset",
                json={
                    "confirmed": True,
                    "confirmation_phrase": "RESET PAPER SANDBOX",
                },
                headers={"Authorization": f"Bearer {normal_user_token}"},
            )

        assert response.status_code == 200, response.text
        data = response.json()
        assert data["success"] is True

    finally:
        app.dependency_overrides.pop(get_current_user, None)


# ---------------------------------------------------------------------------
# Confirmation phrase validation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_start_fresh_wrong_phrase_returns_400(client, admin_token):
    """POST /api/admin/start-fresh with wrong phrase must return 400."""
    from server import app
    from auth import require_admin

    def _admin_dep():
        return "admin_user_test"

    app.dependency_overrides[require_admin] = _admin_dep
    try:
        response = client.post(
            "/api/admin/start-fresh",
            json={"confirmation_phrase": "delete everything", "scope": "paper_only"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 400
        assert "START FRESH" in response.json()["detail"]
    finally:
        app.dependency_overrides.pop(require_admin, None)


@pytest.mark.asyncio
async def test_paper_sandbox_reset_wrong_phrase_returns_400(client, normal_user_token):
    """POST /api/system/paper-sandbox/reset with wrong phrase must return 400."""
    from server import app
    from auth import get_current_user

    def _user_dep():
        return "normal_user_test"

    app.dependency_overrides[get_current_user] = _user_dep
    try:
        response = client.post(
            "/api/system/paper-sandbox/reset",
            json={"confirmed": True, "confirmation_phrase": "wrong"},
            headers={"Authorization": f"Bearer {normal_user_token}"},
        )
        assert response.status_code == 400
        assert "RESET PAPER SANDBOX" in response.json()["detail"]
    finally:
        app.dependency_overrides.pop(get_current_user, None)
