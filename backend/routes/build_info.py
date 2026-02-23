"""
Build Info Router - Provides build version and deployment information
"""

from fastapi import APIRouter
from datetime import datetime
import os
import subprocess
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/build", tags=["Build"])


def get_git_sha() -> str:
    """Get current git commit SHA"""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception as e:
        logger.warning(f"Failed to get git SHA: {e}")
    
    return "unknown"


def get_git_branch() -> str:
    """Get current git branch"""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception as e:
        logger.warning(f"Failed to get git branch: {e}")
    
    return "unknown"


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
            "host": os.environ.get("HOSTNAME", "unknown"),
            "deployed_at": BUILD_TIME
        }
    }


@router.get("/build")
async def get_build_info_legacy():
    """Legacy endpoint - redirects to /info"""
    return await get_build_info()
