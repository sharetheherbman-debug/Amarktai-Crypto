#!/usr/bin/env python3
"""
Generate a stable inventory of backend FastAPI endpoints.

Outputs artifacts/endpoints.json with:
  {method, path, name, tags, requires_auth}
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Iterable

from fastapi.routing import APIRoute
from starlette.routing import WebSocketRoute


AUTH_DEPENDENCY_NAMES = {
    "get_current_user",
    "require_admin",
    "require_admin_user",
    "is_admin",
}


def dependency_requires_auth(dependency) -> bool:
    call = getattr(dependency, "call", None)
    name = getattr(call, "__name__", "")
    if name in AUTH_DEPENDENCY_NAMES:
        return True
    for sub_dep in getattr(dependency, "dependencies", []):
        if dependency_requires_auth(sub_dep):
            return True
    return False


def route_requires_auth(route) -> bool:
    if getattr(route, "path", "").startswith("/api/ws"):
        return True

    dependant = getattr(route, "dependant", None)
    if not dependant:
        return False

    for dependency in dependant.dependencies:
        if dependency_requires_auth(dependency):
            return True

    for param in list(getattr(dependant, "header_params", [])) + list(
        getattr(dependant, "query_params", [])
    ):
        if param.name.lower() in {"authorization", "token", "access_token"}:
            return True

    return False


def normalize_methods(methods: Iterable[str]) -> list[str]:
    return sorted(method for method in methods if method not in {"HEAD", "OPTIONS"})


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    backend_dir = repo_root / "backend"
    sys.path.insert(0, str(backend_dir))

    from server import app

    endpoints = []
    for route in app.routes:
        if isinstance(route, APIRoute):
            requires_auth = route_requires_auth(route)
            tags = sorted(getattr(route, "tags", []) or [])
            for method in normalize_methods(route.methods):
                endpoints.append(
                    {
                        "method": method,
                        "path": route.path,
                        "name": route.name,
                        "tags": tags,
                        "requires_auth": requires_auth,
                    }
                )
        elif isinstance(route, WebSocketRoute):
            endpoints.append(
                {
                    "method": "WEBSOCKET",
                    "path": route.path,
                    "name": route.name,
                    "tags": [],
                    "requires_auth": route_requires_auth(route),
                }
            )

    endpoints.sort(key=lambda item: (item["path"], item["method"]))

    artifacts_dir = repo_root / "artifacts"
    artifacts_dir.mkdir(exist_ok=True)
    output_path = artifacts_dir / "endpoints.json"
    output_path.write_text(json.dumps(endpoints, indent=2, sort_keys=True))

    print(f"Wrote {len(endpoints)} endpoints to {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
