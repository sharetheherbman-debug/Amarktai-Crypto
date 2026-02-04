"""Health routes for ping endpoints.

This module provides basic health check endpoints for deployment verification.
"""

from fastapi import APIRouter, HTTPException
from datetime import datetime, timezone
import logging
import os
import subprocess
import database as db
from utils.env_utils import env_bool

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/health", tags=["Health"])

# Module-level state for preflight checks (populated by server.py at startup)
_router_status = {"mounted": [], "failed": []}
_startup_time = None
_bind_ok = False


def set_startup_time(timestamp: datetime):
    """Called by server.py after successful startup."""
    global _startup_time
    _startup_time = timestamp


def set_bind_ok(status: bool = True):
    """Called by server.py after successful socket bind."""
    global _bind_ok
    _bind_ok = status


# Module-level build hash cache (computed once at import time)
_BUILD_HASH_CACHE = None


def get_build_hash() -> str:
    """Get current git commit SHA for build identification (cached)."""
    global _BUILD_HASH_CACHE
    
    # Return cached value if available
    if _BUILD_HASH_CACHE is not None:
        return _BUILD_HASH_CACHE
    
    try:
        # First try BUILD_SHA environment variable
        build_sha = os.environ.get("BUILD_SHA")
        if build_sha:
            _BUILD_HASH_CACHE = build_sha
            return build_sha
        
        # Fall back to git command (with restricted scope and timeout)
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
            cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            check=False  # Don't raise on non-zero exit
        )
        if result.returncode == 0:
            _BUILD_HASH_CACHE = result.stdout.strip()
            return _BUILD_HASH_CACHE
    except Exception as e:
        logger.debug(f"Could not get build hash: {e}")
    
    # Cache the unknown value to avoid repeated failures
    _BUILD_HASH_CACHE = "unknown"
    return "unknown"


def set_router_status(mounted: list, failed: list):
    """Called by server.py after router mounting completes."""
    _router_status["mounted"] = mounted
    _router_status["failed"] = failed


@router.get("/preflight")
async def preflight_check() -> dict:
    """
    Pre-deployment readiness check (no auth required).
    
    Returns comprehensive system readiness including:
    - Feature flags configuration
    - Router mounting status
    - Service connectivity (DB, CCXT)
    - Authentication configuration
    
    Returns:
        dict: ok=True if system is ready, ok=False if critical issues detected
    """
    try:
        # Collect feature flags
        flags = {
            "ENABLE_TRADING": env_bool("ENABLE_TRADING", False),
            "ENABLE_AUTOPILOT": env_bool("ENABLE_AUTOPILOT", False),
            "ENABLE_SCHEDULERS": env_bool("ENABLE_SCHEDULERS", False),
            "ENABLE_CCXT": env_bool("ENABLE_CCXT", True),
            "ENABLE_REALTIME": env_bool("ENABLE_REALTIME", True),
        }
        
        # Check router mounting status
        routers = {
            "mounted": _router_status["mounted"],
            "failed": _router_status["failed"],
        }
        
        # Check services
        services = {}
        
        # Database check (required)
        try:
            if db.client is not None:
                await db.client.admin.command('ping')
                services["db"] = "ok"
            else:
                services["db"] = "fail"
        except Exception as e:
            logger.error(f"Preflight DB check failed: {e}")
            services["db"] = "fail"
        
        # Redis check (optional - only if used)
        services["redis"] = "skipped"  # Not used in this deployment
        
        # CCXT check (only if enabled)
        if flags["ENABLE_CCXT"]:
            try:
                import ccxt
                # Simple sanity check - can we instantiate?
                services["ccxt"] = "ok"
            except Exception as e:
                logger.warning(f"Preflight CCXT check failed: {e}")
                services["ccxt"] = "fail"
        else:
            services["ccxt"] = "skipped"
        
        # Paper trading DB check (required for paper trading mode)
        try:
            # Check if paper trading engine can access DB collections
            if db.bots_collection is not None and db.trades_collection is not None:
                services["paper_trading_db"] = "ok"
            else:
                services["paper_trading_db"] = "error"
        except Exception as e:
            logger.warning(f"Preflight paper trading DB check failed: {e}")
            services["paper_trading_db"] = "error"
        
        # OpenAI key source check (for AI features)
        env_openai_key = os.getenv("OPENAI_API_KEY")
        if env_openai_key:
            services["openai_key_source"] = "env"
        else:
            services["openai_key_source"] = "none"
        
        # Note: Cannot check user-saved keys without authentication in preflight
        # User-saved keys would override env in actual usage
        
        # API keys count (global count - no user context in preflight)
        keys = {}
        try:
            if db.api_keys_collection is not None:
                total_count = await db.api_keys_collection.count_documents({})
                keys["saved_count_global"] = total_count
            else:
                keys["saved_count_global"] = 0
        except Exception as e:
            logger.warning(f"Preflight keys count check failed: {e}")
            keys["saved_count_global"] = 0
        
        # Auth configuration check
        jwt_secret = os.getenv("JWT_SECRET", "")
        auth = {
            "jwt_secret_present": bool(jwt_secret and jwt_secret != "your-secret-key-change-in-production-min-32-chars"),
            "algorithm": "HS256"
        }
        
        # Determine overall readiness
        ok = True
        issues = []
        
        # Critical: Any router failed to mount
        if routers["failed"]:
            ok = False
            issues.append(f"Router mount failures: {len(routers['failed'])}")
        
        # Critical: Database must be available
        if services["db"] != "ok":
            ok = False
            issues.append("Database not available")
        
        # Critical: JWT secret must be configured
        if not auth["jwt_secret_present"]:
            ok = False
            issues.append("JWT_SECRET not configured or using default")
        
        # Critical: Realtime router must be mounted if enabled
        if flags["ENABLE_REALTIME"]:
            realtime_mounted = any("realtime" in m.lower() for m in routers["mounted"])
            if not realtime_mounted:
                ok = False
                issues.append("ENABLE_REALTIME=true but realtime router not mounted")
        
        # Warning: CCXT should work if enabled
        if flags["ENABLE_CCXT"] and services["ccxt"] != "ok":
            # Not critical - just a warning
            logger.warning("ENABLE_CCXT=true but CCXT service check failed")
        
        response = {
            "ok": ok,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "flags": flags,
            "routers": routers,
            "services": services,
            "auth": auth,
            "keys": keys,
        }
        
        if not ok:
            response["issues"] = issues
        
        return response
        
    except Exception as e:
        logger.error(f"Preflight check error: {e}", exc_info=True)
        return {
            "ok": False,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "error": str(e),
            "issues": ["Preflight check crashed - see logs"]
        }


@router.get("/ping")
async def health_ping() -> dict:
    """Return a comprehensive health check response with build info and uptime.
    
    Enhanced endpoint that includes:
    - Database connectivity status
    - Build hash for deployment verification
    - Server uptime since startup
    - Socket bind status
    
    Returns:
        - HTTP 200 with status="healthy" when database is connected
        - HTTP 503 with status="unhealthy" when database is disconnected or error occurs
    """
    try:
        current_time = datetime.now(timezone.utc)
        
        # Calculate uptime
        uptime_seconds = None
        if _startup_time:
            uptime_seconds = (current_time - _startup_time).total_seconds()
        
        # Test database connection
        db_status = "unknown"
        if db.client is not None:
            try:
                await db.client.admin.command('ping')
                db_status = "connected"
            except Exception as e:
                logger.error(f"Database ping failed: {e}")
                db_status = "error"
        else:
            db_status = "disconnected"
        
        # Build response
        response = {
            "status": "healthy" if db_status == "connected" else "unhealthy",
            "db": db_status,
            "timestamp": current_time.isoformat(),
            "build_hash": get_build_hash(),
            "bind_ok": _bind_ok,
        }
        
        # Add uptime if available
        if uptime_seconds is not None:
            response["uptime_seconds"] = round(uptime_seconds, 2)
            response["uptime_formatted"] = format_uptime(uptime_seconds)
        
        # Return 503 if unhealthy
        if db_status != "connected":
            raise HTTPException(
                status_code=503,
                detail=response
            )
        
        return response
        
    except HTTPException:
        raise  # Re-raise HTTPException as-is
    except Exception as e:
        # Unexpected error - return 503
        logger.error(f"Health check failed: {e}")
        raise HTTPException(
            status_code=503,
            detail={
                "status": "unhealthy",
                "db": "error",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "error": str(e),
                "build_hash": get_build_hash(),
                "bind_ok": _bind_ok
            }
        )


def format_uptime(seconds: float) -> str:
    """Format uptime in human-readable format."""
    days = int(seconds // 86400)
    hours = int((seconds % 86400) // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    
    parts = []
    if days > 0:
        parts.append(f"{days}d")
    if hours > 0:
        parts.append(f"{hours}h")
    if minutes > 0:
        parts.append(f"{minutes}m")
    parts.append(f"{secs}s")
    
    return " ".join(parts)


@router.get("/ready")
async def health_ready() -> dict:
    """Application readiness check - verifies DB connectivity and critical collections exist.
    
    This endpoint should be used by orchestrators (Kubernetes, systemd) to determine
    if the application is ready to serve traffic.
    
    Returns:
        - HTTP 200 when ready (DB connected, critical collections exist)
        - HTTP 503 when not ready (with reason in response)
    """
    issues = []
    
    try:
        # 1. Check database connection
        if db.client is None:
            issues.append("Database client not initialized")
        else:
            try:
                await db.client.admin.command('ping')
            except Exception as e:
                issues.append(f"Database ping failed: {str(e)}")
        
        # 2. Check critical collections are initialized
        required_collections = {
            'users_collection': 'users',
            'bots_collection': 'bots',
            'trades_collection': 'trades',
            'api_keys_collection': 'api_keys',
        }
        
        for attr_name, display_name in required_collections.items():
            if not hasattr(db, attr_name) or getattr(db, attr_name) is None:
                issues.append(f"Collection '{display_name}' not initialized")
        
        # 3. Check JWT secret is configured properly
        jwt_secret = os.getenv("JWT_SECRET", "")
        if not jwt_secret or jwt_secret == "your-secret-key" or len(jwt_secret) < 32:
            issues.append("JWT_SECRET not properly configured (must be 32+ chars)")
        
        # If any issues found, return 503
        if issues:
            logger.warning(f"Health ready check failed: {issues}")
            raise HTTPException(
                status_code=503,
                detail={
                    "status": "not_ready",
                    "ready": False,
                    "issues": issues,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
            )
        
        # All checks passed - return 200
        return {
            "status": "ready",
            "ready": True,
            "db": "connected",
            "collections": list(required_collections.values()),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        
    except HTTPException:
        raise  # Re-raise HTTPException as-is
    except Exception as e:
        # Unexpected error during readiness check - return 503
        logger.error(f"Health ready check error: {e}", exc_info=True)
        raise HTTPException(
            status_code=503,
            detail={
                "status": "not_ready",
                "ready": False,
                "error": str(e),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )
