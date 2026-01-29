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


# Get build info at startup
BUILD_SHA = os.environ.get("BUILD_SHA") or get_git_sha()
BUILD_TIME = os.environ.get("BUILD_TIME") or datetime.utcnow().isoformat()
BUILD_BRANCH = os.environ.get("BUILD_BRANCH") or get_git_branch()


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
    """
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
