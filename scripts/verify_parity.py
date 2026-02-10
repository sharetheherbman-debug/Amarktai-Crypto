#!/usr/bin/env python3
"""
Compare backend endpoint inventory with frontend API usage.

Fails if frontend calls missing endpoints or if common response-shape
mismatches are detected.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import urlparse


def load_json(path: Path):
    return json.loads(path.read_text())


def normalize_path(raw: str) -> str:
    if "://" in raw or raw.startswith("ws"):
        parsed = urlparse(raw)
        path = parsed.path or ""
        if parsed.query:
            path = f"{path}?{parsed.query}"
    else:
        path = raw
    path = path.split("?", 1)[0]
    if not path.startswith("/"):
        path = f"/{path}"
    if path != "/" and path.endswith("/"):
        path = path[:-1]
    return path


def build_backend_patterns(endpoints):
    patterns = []
    for endpoint in endpoints:
        path = normalize_path(endpoint["path"])
        pattern = re.sub(r"\{[^/]+\}", "[^/]+", path)
        patterns.append((endpoint["path"], re.compile(rf"^{pattern.rstrip('/')}/?$")))
    return patterns


def get_context(lines, line_number, window=8):
    """Return context using 1-based line numbers from audit output."""
    start = max(line_number - 1, 0)
    end = min(line_number + window - 1, len(lines))
    return "\n".join(lines[start:end])


def analyze_shape(path, context_text, file_text=""):
    mismatches = []
    expected_keys = set(re.findall(r"\.data\.([A-Za-z0-9_]+)", context_text))

    array_usage = bool(
        re.search(r"Array\.isArray\([^)]*data", context_text)
        or re.search(r"\bdata\.map\(", context_text)
    )
    normalize_usage = "normalizeLivePrices" in context_text

    if path.startswith("/api/prices/live"):
        has_prices_reference = "prices" in expected_keys or re.search(
            r"\bdata\.prices\b", context_text
        )
        if has_prices_reference and not (array_usage or normalize_usage):
            mismatches.append("expects data.prices but /api/prices/live returns a raw array")

    if path.startswith("/api/keys/status"):
        keys_ref = "keys" in expected_keys or re.search(r"\bdata\.keys\b", context_text)
        status_ref = "status_map" in expected_keys or re.search(r"\bdata\.status_map\b", context_text)
        if keys_ref and not status_ref and "status_map" not in file_text:
            mismatches.append("expects keys array but /api/keys/status returns status_map")

    if path.startswith("/api/admin/overview"):
        if expected_keys and "stats" not in expected_keys:
            mismatches.append("expects fields beyond stats in /api/admin/overview response")

    return mismatches


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    artifacts_dir = repo_root / "artifacts"
    endpoints_path = artifacts_dir / "endpoints.json"
    calls_path = artifacts_dir / "frontend_calls.json"

    if not endpoints_path.exists() or not calls_path.exists():
        raise SystemExit("Run audit_endpoints.py and audit_frontend_calls.py first.")

    endpoints = load_json(endpoints_path)
    frontend_calls = load_json(calls_path)

    backend_patterns = build_backend_patterns(endpoints)

    missing = []
    shape_mismatches = []
    total_calls = 0

    file_cache = {}

    for entry in frontend_calls:
        raw_path = entry["path"]
        normalized = normalize_path(raw_path)
        total_calls += 1

        if not any(regex.match(normalized) for _, regex in backend_patterns):
            missing.append(normalized)

        for file_entry in entry.get("files", []):
            file_path = repo_root / file_entry["file"]
            if file_path not in file_cache:
                file_cache[file_path] = file_path.read_text(errors="ignore").splitlines()
            lines = file_cache[file_path]
            context_text = get_context(lines, file_entry["line"])
            mismatches = analyze_shape(normalized, context_text, "\n".join(lines))
            for mismatch in mismatches:
                shape_mismatches.append(
                    {
                        "path": normalized,
                        "file": file_entry["file"],
                        "line": file_entry["line"],
                        "message": mismatch,
                    }
                )

    print("=== Parity Report ===")
    print(f"Backend endpoints: {len(endpoints)}")
    print(f"Frontend call sites: {total_calls}")

    if missing:
        print("\nMissing backend endpoints:")
        for path in sorted(set(missing)):
            print(f"  - {path}")

    if shape_mismatches:
        print("\nResponse shape warnings:")
        for mismatch in shape_mismatches:
            print(
                f"  - {mismatch['path']} @ {mismatch['file']}:{mismatch['line']} -> {mismatch['message']}"
            )

    if missing or shape_mismatches:
        print("\nFAIL: Parity checks detected issues.")
        return 1

    print("\nPASS: Frontend/backend parity verified.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
