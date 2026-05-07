import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


def test_paper_readiness_route_is_mounted():
    from server import app
    paths = app.openapi().get("paths", {})
    assert "/api/diagnostics/paper-trading-readiness" in paths

