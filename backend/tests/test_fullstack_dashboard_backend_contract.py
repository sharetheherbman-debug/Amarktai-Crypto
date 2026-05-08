import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


def test_fullstack_dashboard_backend_contract_routes_present():
    from server import app

    paths = app.openapi().get("paths", {})
    required = {
        "/api/system/paper-reset/validate",
        "/api/system/paper-reset",
        "/api/wallet/platform",
        "/api/wallet/platform/summary",
        "/api/wallet/paper",
        "/api/radar/snapshot",
        "/api/dashboard/snapshot",
        "/api/overview/snapshot",
        "/api/diagnostics/paper-trading-readiness",
        "/api/diagnostics/live-trading-readiness",
        "/api/diagnostics/trading-logic-version",
        "/api/diagnostics/paper-execution-proof",
        "/api/diagnostics/learning-last-run",
        "/api/bots/status",
        "/api/bots",
        "/api/bots/seed-paper",
        "/api/trades/recent",
        "/api/keys/status",
    }
    missing = sorted(path for path in required if path not in paths)
    assert not missing, f"Missing required full-stack contract routes: {missing}"

