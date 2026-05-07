import os
import sys
from types import SimpleNamespace

import pytest

backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, backend_dir)


class _Cursor:
    def __init__(self, rows):
        self._rows = rows

    async def to_list(self, _length):
        return list(self._rows)


class _Collection:
    def __init__(self, docs=None, count=0):
        self._docs = docs or []
        self._count = count

    async def find_one(self, *_args, **_kwargs):
        return self._docs[0] if self._docs else None

    def find(self, *_args, **_kwargs):
        return _Cursor(self._docs)

    async def count_documents(self, *_args, **_kwargs):
        return self._count


def _fake_signal(status="ok", edge=40.0, diagnostics=None):
    return SimpleNamespace(
        signal_status=status,
        expected_edge_bps=edge,
        confidence=0.8,
        regime="stable_uptrend",
        diagnostics=diagnostics or {},
    )


def _load_diagnostics(monkeypatch):
    class _FakeRouter:
        def __init__(self, *args, **kwargs):
            pass

        def get(self, *args, **kwargs):
            def _decorator(func):
                return func
            return _decorator

    fake_fastapi = SimpleNamespace(
        APIRouter=_FakeRouter,
        HTTPException=Exception,
        Depends=lambda dep: dep,
    )
    fake_db = SimpleNamespace(
        system_modes_collection=_Collection(),
        bots_collection=_Collection(),
        api_keys_collection=_Collection(),
        trades_collection=_Collection(),
    )
    monkeypatch.setitem(sys.modules, "fastapi", fake_fastapi)
    monkeypatch.setitem(sys.modules, "database", fake_db)
    monkeypatch.setitem(sys.modules, "auth", SimpleNamespace(get_current_user=lambda: "u1"))
    monkeypatch.setitem(
        sys.modules,
        "trading_scheduler",
        SimpleNamespace(trading_scheduler=SimpleNamespace(is_running=False, tick_count=0, last_tick=None)),
    )
    monkeypatch.setitem(
        sys.modules,
        "services.signal_engine",
        SimpleNamespace(SignalEngine=lambda *_args, **_kwargs: None),
    )
    class _PaperWalletLedger:
        async def get_balance(self, _bot_id):
            return True, 1000.0, "funded"

    monkeypatch.setitem(
        sys.modules,
        "services.paper_wallet_ledger",
        SimpleNamespace(paper_wallet_ledger=_PaperWalletLedger()),
    )
    monkeypatch.setitem(
        sys.modules,
        "websocket_manager",
        SimpleNamespace(manager=SimpleNamespace(active_connections={}, redis_enabled=False, last_event=None)),
    )
    monkeypatch.setitem(sys.modules, "realtime_events", SimpleNamespace(rt_events=SimpleNamespace()))
    monkeypatch.setitem(
        sys.modules,
        "config",
        SimpleNamespace(
            PAPER_MAX_HOLD_MINUTES=120,
            PAPER_STALE_EXIT_MINUTES=60,
            SOFT_MAX_HOLD_SECONDS=300,
            HARD_MAX_HOLD_SECONDS=600,
            MIN_TRADES_FOR_PROMOTION=20,
            MIN_WIN_RATE=0.55,
            MAX_DRAWDOWN_PCT=0.2,
            MIN_EXPECTANCY_ZAR=0.0,
        ),
    )
    if "routes.diagnostics" in sys.modules:
        del sys.modules["routes.diagnostics"]
    import routes.diagnostics as diag
    return diag


@pytest.mark.asyncio
async def test_live_readiness_fails_when_emergency_stop_active(monkeypatch):
    diag = _load_diagnostics(monkeypatch)

    fake_db = SimpleNamespace(
        system_modes_collection=_Collection([{"user_id": "u1", "emergencyStop": True, "liveTrading": False}]),
        bots_collection=_Collection([{"id": "b1", "exchange": "binance", "trading_mode": "live", "status": "active", "max_drawdown": 0.01}], count=0),
        api_keys_collection=_Collection([{"last_test_ok": True}]),
        trades_collection=_Collection([{"profit_loss": 15.0}, {"profit_loss": -5.0}], count=0),
    )
    monkeypatch.setattr(diag, "db", fake_db)
    monkeypatch.setenv("ENABLE_TRADING", "true")
    monkeypatch.setenv("ENABLE_LIVE_TRADING", "false")
    monkeypatch.setenv("MACRO_SIGNAL_WEIGHT", "0")

    class _SignalEngine:
        def __init__(self, *_args, **_kwargs):
            pass

        async def get_signal(self, **_kwargs):
            return _fake_signal()

    monkeypatch.setitem(sys.modules, "services.signal_engine", SimpleNamespace(SignalEngine=_SignalEngine))
    monkeypatch.setattr("trading_scheduler.trading_scheduler.is_running", True)

    fake_route = SimpleNamespace(path="/api/a", methods={"GET"})
    fake_server = SimpleNamespace(app=SimpleNamespace(routes=[fake_route]))
    monkeypatch.setitem(sys.modules, "server", fake_server)

    result = await diag.live_trading_readiness(user_id="u1")
    assert result["status"] == "FAIL"
    assert "emergency_stop_active" in result["blockers"]


@pytest.mark.asyncio
async def test_live_readiness_detects_route_collision(monkeypatch):
    diag = _load_diagnostics(monkeypatch)

    fake_db = SimpleNamespace(
        system_modes_collection=_Collection([{"user_id": "u1", "emergencyStop": False, "liveTrading": True}]),
        bots_collection=_Collection([{"id": "b1", "exchange": "binance", "trading_mode": "live", "status": "active", "max_drawdown": 0.01}], count=0),
        api_keys_collection=_Collection([{"last_test_ok": True}]),
        trades_collection=_Collection([{"profit_loss": 20.0}, {"profit_loss": -5.0}], count=0),
    )
    monkeypatch.setattr(diag, "db", fake_db)
    monkeypatch.setenv("ENABLE_TRADING", "true")
    monkeypatch.setenv("ENABLE_LIVE_TRADING", "true")
    monkeypatch.setenv("MACRO_SIGNAL_WEIGHT", "0")
    monkeypatch.setattr("trading_scheduler.trading_scheduler.is_running", True)

    class _SignalEngine:
        def __init__(self, *_args, **_kwargs):
            pass

        async def get_signal(self, **_kwargs):
            return _fake_signal()

    monkeypatch.setitem(sys.modules, "services.signal_engine", SimpleNamespace(SignalEngine=_SignalEngine))

    dup_a = SimpleNamespace(path="/api/x", methods={"GET"})
    dup_b = SimpleNamespace(path="/api/x", methods={"GET"})
    fake_server = SimpleNamespace(app=SimpleNamespace(routes=[dup_a, dup_b]))
    monkeypatch.setitem(sys.modules, "server", fake_server)

    result = await diag.live_trading_readiness(user_id="u1")
    assert result["checks"]["route_integrity_ok"] is False
    assert "route_integrity_failed" in result["blockers"]


@pytest.mark.asyncio
async def test_runtime_truth_reports_scheduler_and_redis(monkeypatch):
    diag = _load_diagnostics(monkeypatch)

    fake_db = SimpleNamespace(
        system_modes_collection=_Collection([{"user_id": "u1", "emergencyStop": False, "liveTrading": False}]),
        bots_collection=_Collection([{"id": "b1", "exchange": "binance", "status": "active", "trading_mode": "paper", "pair": "BTC/USDT"}]),
        trades_collection=_Collection([], count=2),
    )
    monkeypatch.setattr(diag, "db", fake_db)
    monkeypatch.setattr("trading_scheduler.trading_scheduler.is_running", True)
    monkeypatch.setattr("trading_scheduler.trading_scheduler.tick_count", 7)
    monkeypatch.setattr("trading_scheduler.trading_scheduler.last_tick", None)
    monkeypatch.setattr("websocket_manager.manager.active_connections", {"u1": [object()], "u2": [object(), object()]})
    monkeypatch.setattr("websocket_manager.manager.redis_enabled", True)
    monkeypatch.setattr("websocket_manager.manager.last_event", {"type": "heartbeat"})

    class _SignalEngine:
        def __init__(self, *_args, **_kwargs):
            pass

        async def get_signal(self, **_kwargs):
            return _fake_signal(status="ok", edge=12.3)

    monkeypatch.setitem(sys.modules, "services.signal_engine", SimpleNamespace(SignalEngine=_SignalEngine))

    payload = await diag.runtime_truth(user_id="u1")
    assert payload["active_scheduler"]["running"] is True
    assert payload["active_exchanges"] == ["binance"]
    assert payload["open_trades"] == 2
    assert payload["redis_state"]["enabled"] is True


@pytest.mark.asyncio
async def test_order_pipeline_blocks_unhealthy_signal_and_fake_inputs():
    from services.order_pipeline import OrderPipeline

    class _Db:
        def __getitem__(self, _key):
            return _Collection()

    class _SignalEngine:
        async def get_signal(self, **_kwargs):
            return _fake_signal(status="error", edge=0.0, diagnostics={"error": "engine_down"})

    pipeline = OrderPipeline(db=_Db(), signal_engine=_SignalEngine())
    result = await pipeline._check_fee_coverage(
        user_id="u1",
        bot_id="b1",
        exchange="binance",
        symbol="BTC/USDT",
        side="buy",
        amount=1.0,
        price=50000.0,
        order_type="market",
        is_paper=False,
    )
    assert result["passed"] is False
    assert "Signal engine unhealthy" in result["reason"]

    class _FakeSignalEngine:
        async def get_signal(self, **_kwargs):
            return _fake_signal(
                status="ok",
                edge=60.0,
                diagnostics={"macro": {"is_simulated": True}},
            )

    pipeline.signal_engine = _FakeSignalEngine()
    result = await pipeline._check_fee_coverage(
        user_id="u1",
        bot_id="b1",
        exchange="binance",
        symbol="BTC/USDT",
        side="buy",
        amount=1.0,
        price=50000.0,
        order_type="market",
        is_paper=False,
    )
    assert result["passed"] is False
    assert "Simulated/fake" in result["reason"]


@pytest.mark.asyncio
async def test_order_pipeline_blocks_negative_expectancy_and_bearish_spot(monkeypatch):
    from services.order_pipeline import OrderPipeline

    class _Db:
        def __getitem__(self, key):
            if key == "bots":
                return _Collection([{"id": "b1", "market_type": "spot", "supports_shorting": False}])
            return _Collection()

    class _SignalEngine:
        async def get_signal(self, **_kwargs):
            return _fake_signal(
                status="ok",
                edge=5.0,
                diagnostics={"ml": {"direction": "down"}, "regime": {"regime": "stable_downtrend"}},
            )

    monkeypatch.setenv("ENABLE_FUTURES_SHORTS", "false")
    monkeypatch.setenv("LIVE_SHORTING_ENABLED", "false")
    pipeline = OrderPipeline(db=_Db(), signal_engine=_SignalEngine())

    result = await pipeline._check_fee_coverage(
        user_id="u1",
        bot_id="b1",
        exchange="binance",
        symbol="BTC/USDT",
        side="buy",
        amount=1.0,
        price=50000.0,
        order_type="market",
        is_paper=False,
    )
    assert result["passed"] is False
    assert "Negative expectancy" in result["reason"] or "Fees exceed expected edge" in result["reason"]

    class _PositiveEdgeBearSignal:
        async def get_signal(self, **_kwargs):
            return _fake_signal(
                status="ok",
                edge=120.0,
                diagnostics={"ml": {"direction": "down"}, "regime": {"regime": "stable_downtrend"}},
            )

    pipeline.signal_engine = _PositiveEdgeBearSignal()
    result = await pipeline._check_fee_coverage(
        user_id="u1",
        bot_id="b1",
        exchange="binance",
        symbol="BTC/USDT",
        side="buy",
        amount=1.0,
        price=50000.0,
        order_type="market",
        is_paper=False,
    )
    assert result["passed"] is False
    assert result["reason"] == "bearish_spot_no_short"
