import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


def test_dashboard_snapshot_routes_mounted():
    from server import app
    paths = app.openapi().get("paths", {})
    assert "/api/dashboard/snapshot" in paths
    assert "/api/overview/snapshot" in paths
    assert "/api/radar/snapshot" in paths

