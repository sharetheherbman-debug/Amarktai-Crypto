"""
Build Info Router - Provides build version and deployment information
"""

from fastapi import APIRouter
from datetime import datetime
from pathlib import Path
import os
import socket
import subprocess
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/build", tags=["Build"])


def _find_repo_root() -> Path:
    """Locate the repository root directory.

    Resolution order:
    1. AMARKTAI_REPO_ROOT env var — set by ops/systemd when the backend is
       deployed without a .git directory.
    2. Walk upward from this file looking for a .git/ folder (max 5 levels).
       Covers dev and CI environments where the repo is fully cloned.
    3. Fallback: derive from this file's path assuming the standard layout
       build_info.py → routes/ → backend/ → <repo_root>.
    """
    _MAX_UPWARD_SEARCH_LEVELS = 5

    # 1. Explicit env override
    env_root = os.environ.get("AMARKTAI_REPO_ROOT", "").strip()
    if env_root:
        p = Path(env_root)
        if p.is_dir():
            return p

    # 2. Walk upward looking for .git/
    current = Path(__file__).resolve().parent
    for _ in range(_MAX_UPWARD_SEARCH_LEVELS):
        if (current / ".git").is_dir():
            return current
        parent = current.parent
        if parent == current:  # filesystem root
            break
        current = parent

    # 3. Standard layout fallback
    return Path(__file__).resolve().parents[2]


# Repo root is resolved once at module load time.
_REPO_ROOT = _find_repo_root()

_LOOPBACK = {"127.0.0.1", "localhost", "::1"}


def get_git_sha() -> str:
    """Get current git commit SHA.

    Resolution order:
    1. BUILD_SHA env var (set at deploy time)
    2. GIT_SHA / GITHUB_SHA env vars (set by CI)
    3. .version file in repo root (written by deploy scripts)
    4. git subprocess
    """
    for env_var in ("BUILD_SHA", "GIT_SHA", "GITHUB_SHA"):
        val = os.environ.get(env_var, "").strip()
        if val:
            return val[:12]  # keep short form

    # .version file written by deployment pipeline
    version_file = _REPO_ROOT / ".version"
    try:
        if version_file.exists():
            lines = version_file.read_text().strip().splitlines()
            for line in lines:
                if line.startswith("sha=") or line.startswith("SHA="):
                    return line.split("=", 1)[1].strip()[:12]
            if lines:
                return lines[0].strip()[:12]
    except Exception:
        pass

    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
            cwd=_REPO_ROOT,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception as e:
        logger.warning(f"Failed to get git SHA: {e}")
    
    return "unknown"


def get_git_branch() -> str:
    """Get current git branch.

    Resolution order:
    1. BUILD_BRANCH env var (set at deploy time)
    2. GIT_BRANCH / GITHUB_REF_NAME env vars (set by CI)
    3. .version file in repo root
    4. git subprocess
    """
    for env_var in ("BUILD_BRANCH", "GIT_BRANCH", "GITHUB_REF_NAME"):
        val = os.environ.get(env_var, "").strip()
        if val:
            return val

    version_file = _REPO_ROOT / ".version"
    try:
        if version_file.exists():
            for line in version_file.read_text().strip().splitlines():
                if line.startswith("branch=") or line.startswith("BRANCH="):
                    return line.split("=", 1)[1].strip()
    except Exception:
        pass

    try:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
            cwd=_REPO_ROOT,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception as e:
        logger.warning(f"Failed to get git branch: {e}")
    
    return "unknown"


def get_git_dirty() -> bool:
    """Check if working tree has uncommitted changes."""
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain"],
            capture_output=True,
            text=True,
            timeout=5,
            cwd=_REPO_ROOT,
        )
        if result.returncode == 0:
            return bool(result.stdout.strip())
    except Exception:
        pass
    return False


def _get_deployment_host() -> str:
    """Return the real deployment hostname, never a loopback address."""
    hostname_env = os.environ.get("HOSTNAME")
    if hostname_env:
        return hostname_env
    host_env = os.environ.get("HOST", "")
    if host_env and host_env not in _LOOPBACK:
        return host_env
    return socket.gethostname()


def _get_db_info() -> dict:
    """Return safe (credential-free) DB connection info."""
    try:
        from database import _parse_mongo_config
        mongo_url, db_name = _parse_mongo_config()
        from urllib.parse import urlparse
        parsed = urlparse(mongo_url)
        safe_host = f"{parsed.hostname or 'unknown'}:{parsed.port or 27017}"
    except Exception:
        safe_host = "unknown"
        db_name = os.getenv("DB_NAME", os.getenv("MONGO_URI", "").split("/")[-1] or "unknown")
    return {"host": safe_host, "name": db_name}


def _get_feature_flags() -> dict:
    """Return current feature flag state."""
    def _b(key: str, default: str = "false") -> bool:
        return os.getenv(key, default).lower() == "true"
    return {
        "paper_trading": _b("ENABLE_PAPER_TRADING", "true"),
        "live_trading": _b("ENABLE_LIVE_TRADING"),
        "autopilot": _b("ENABLE_AUTOPILOT"),
        "schedulers": _b("ENABLE_SCHEDULERS"),
    }


# Get build info at startup
BUILD_SHA = os.environ.get("BUILD_SHA") or get_git_sha()
BUILD_TIME = os.environ.get("BUILD_TIME") or datetime.utcnow().isoformat()
BUILD_BRANCH = os.environ.get("BUILD_BRANCH") or get_git_branch()
BUILD_DIRTY = get_git_dirty()


@router.get("")
@router.get("/info")
async def get_build_info():
    """Get build information (no authentication required)
    
    This endpoint is publicly accessible to verify deployment status.
    
    Returns:
        version: Git SHA or build ID
        built_at: Build timestamp (ISO format)
        backend_path: Working directory of backend
        env: Environment name (prod/staging/dev)
        api_base: API base path
        mongodb: safe DB host + db name
        flags: enabled feature flags
    """
    db_info = _get_db_info()
    return {
        "version": BUILD_SHA,
        "built_at": BUILD_TIME,
        "backend_path": os.getcwd(),
        "env": os.environ.get("ENVIRONMENT", "production"),
        "api_base": "/api",
        "backend": {
            "sha": BUILD_SHA,
            "branch": BUILD_BRANCH,
            "build_time": BUILD_TIME,
            "dirty": BUILD_DIRTY,
            "python_version": os.sys.version.split()[0],
            "working_directory": os.getcwd()
        },
        "mongodb": db_info,
        "flags": _get_feature_flags(),
        "frontend": {
            "expected_sha": BUILD_SHA,
            "note": "Frontend build SHA should be displayed in UI footer"
        },
        "deployment": {
            "environment": os.environ.get("ENVIRONMENT", "production"),
            "host": _get_deployment_host(),
            "deployed_at": BUILD_TIME
        }
    }


@router.get("/build")
async def get_build_info_legacy():
    """Legacy endpoint - redirects to /info"""
    return await get_build_info()
