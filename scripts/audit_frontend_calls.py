#!/usr/bin/env python3
"""
Scan frontend source for /api/ usage in API calls and WebSocket wiring.

Outputs artifacts/frontend_calls.json with:
  {path, files:[{file,line,snippet}]}
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path


API_LITERAL = re.compile(r'(["\'])(/api/[^"\']+)\1')
COMMENT_PREFIXES = ("//", "/*", "*", "*/")
CALL_KEYWORDS = ("axios", "fetch", "EventSource", "WebSocket", "endpoint", "wsUrl", "apiClient")


def is_comment_line(line: str) -> bool:
    stripped = line.strip()
    return stripped.startswith(COMMENT_PREFIXES)


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    frontend_src = repo_root / "frontend" / "src"
    if not frontend_src.exists():
        raise SystemExit("frontend/src not found")

    calls: dict[str, list[dict[str, str | int]]] = defaultdict(list)
    seen = set()

    for file_path in frontend_src.rglob("*"):
        if file_path.suffix not in {".js", ".jsx", ".ts", ".tsx"}:
            continue
        content = file_path.read_text(errors="ignore").splitlines()
        for idx, line in enumerate(content, start=1):
            if "/api/" not in line or is_comment_line(line):
                continue
            if not any(keyword in line for keyword in CALL_KEYWORDS):
                continue
            for match in API_LITERAL.finditer(line):
                path = match.group(2)
                entry = (
                    path,
                    str(file_path.relative_to(repo_root)),
                    idx,
                    line.strip(),
                )
                if entry in seen:
                    continue
                seen.add(entry)
                calls[path].append(
                    {
                        "file": entry[1],
                        "line": entry[2],
                        "snippet": entry[3],
                    }
                )

    results = []
    for path in sorted(calls.keys()):
        entries = sorted(calls[path], key=lambda item: (item["file"], item["line"]))
        results.append({"path": path, "files": entries})

    artifacts_dir = repo_root / "artifacts"
    artifacts_dir.mkdir(exist_ok=True)
    output_path = artifacts_dir / "frontend_calls.json"
    output_path.write_text(json.dumps(results, indent=2, sort_keys=True))
    print(f"Wrote {len(results)} frontend call entries to {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
