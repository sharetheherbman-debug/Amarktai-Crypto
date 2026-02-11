#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${1:-${AMARKTAI_API_URL:-${API_BASE:-http://localhost:8000}}}"
BASE_URL="${BASE_URL%/}"
OPENAPI_URL="${BASE_URL}/api/openapi.json"

TMP_DIR="$(mktemp -d)"
cleanup() {
  rm -rf "$TMP_DIR"
}
trap cleanup EXIT

echo "Fetching OpenAPI spec from ${OPENAPI_URL}..."
curl -fsS "${OPENAPI_URL}" -o "${TMP_DIR}/openapi.json"

python3 - "${TMP_DIR}/openapi.json" <<'PY'
import json
import re
import sys
from pathlib import Path

openapi_path = Path(sys.argv[1])
repo_root = Path(__file__).resolve().parents[1]
frontend_src = repo_root / "frontend" / "src"

openapi = json.loads(openapi_path.read_text())
paths = sorted(openapi.get("paths", {}).keys())

def normalize_path(raw: str) -> str:
    raw = raw.split("?", 1)[0]
    if raw != "/" and raw.endswith("/"):
        raw = raw[:-1]
    return raw

patterns = []
for path in paths:
    normalized = normalize_path(path)
    pattern = re.sub(r"\{[^/]+\}", "[^/]+", normalized)
    patterns.append(re.compile(rf"^{pattern}/?$"))

api_pattern = re.compile(r'(["\'])(/api/[^"\']+)\1')
comment_prefixes = ("//", "/*", "*", "*/")

allowlist = {
    "/api/ws",
    "/api/ws/decisions",
}

missing = []

for file_path in frontend_src.rglob("*"):
    if file_path.suffix not in {".js", ".jsx", ".ts", ".tsx"}:
        continue
    for line in file_path.read_text(errors="ignore").splitlines():
        stripped = line.strip()
        if stripped.startswith(comment_prefixes):
            continue
        for match in api_pattern.finditer(line):
            raw_path = match.group(2)
            normalized = normalize_path(raw_path)
            if normalized in allowlist:
                continue
            if any(regex.match(normalized) for regex in patterns):
                continue
            missing.append((normalized, str(file_path.relative_to(repo_root))))

if missing:
    print("FAIL: Frontend references endpoints missing from OpenAPI:")
    for path, file_path in sorted(set(missing)):
        print(f"  - {path} ({file_path})")
    sys.exit(1)

print("PASS: All frontend /api/* routes exist in OpenAPI.")
PY
