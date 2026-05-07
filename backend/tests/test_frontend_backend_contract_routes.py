import os


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def test_frontend_contract_routes_declared():
    route_checks = {
        "/api/system/paper-reset": (_read(os.path.join(ROOT, "routes", "system_mode.py")), ['prefix="/api/system"', '@router.post("/paper-reset")']),
        "/api/wallet/platform": (_read(os.path.join(ROOT, "routes", "wallet_hub.py")), ['prefix="/api/wallet"', '@router.get("/platform")']),
        "/api/wallet/platform/summary": (_read(os.path.join(ROOT, "routes", "wallet_hub.py")), ['prefix="/api/wallet"', '@router.get("/platform/summary")']),
        "/api/radar/snapshot": (_read(os.path.join(ROOT, "routes", "dashboard_overview.py")), ['@router.get("/api/radar/snapshot")']),
        "/api/dashboard/snapshot": (_read(os.path.join(ROOT, "routes", "dashboard_overview.py")), ['@router.get("/api/dashboard/snapshot")']),
        "/api/overview/snapshot": (_read(os.path.join(ROOT, "routes", "dashboard_overview.py")), ['@router.get("/api/overview/snapshot")']),
        "/api/bots/status": (_read(os.path.join(ROOT, "routes", "bot_lifecycle.py")), ['prefix="/api/bots"', '@router.get("/status")']),
        "/api/bots": (_read(os.path.join(ROOT, "server.py")), ['@api_router.get("/bots")']),
        "/api/trades/recent": (_read(os.path.join(ROOT, "routes", "trades.py")), ['prefix="/api/trades"', '@router.get("/recent")']),
        "/api/wallet/paper": (_read(os.path.join(ROOT, "routes", "wallet_hub.py")), ['prefix="/api/wallet"', '@router.get("/paper")']),
        "/api/diagnostics/live-trading-readiness": (_read(os.path.join(ROOT, "routes", "diagnostics.py")), ['prefix="/api/diagnostics"', '@router.get("/live-trading-readiness")']),
        "/api/diagnostics/paper-trading-readiness": (_read(os.path.join(ROOT, "routes", "diagnostics.py")), ['prefix="/api/diagnostics"', '@router.get("/paper-trading-readiness")']),
    }
    missing = [
        route
        for route, (src, tokens) in route_checks.items()
        if not all(token in src for token in tokens)
    ]
    assert not missing, f"Missing route declarations: {missing}"
