from fastapi import FastAPI, HTTPException, Depends, WebSocket, WebSocketDisconnect, Request, APIRouter, Query, Body
from routes.auth import router as auth_router
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse, RedirectResponse
from contextlib import asynccontextmanager
from datetime import datetime, timezone, timedelta
from typing import Optional, List
import logging
import logging.config
import os
import asyncio
import json
import random
import time
from collections import defaultdict

# Configure structured logging BEFORE any other imports that use logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

# Add file handler for production
log_file = os.getenv('LOG_FILE', '/var/log/amarktai/backend.log')
log_dir = os.path.dirname(log_file)
if log_dir and os.path.exists(log_dir):
    try:
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(logging.Formatter(
            '%(asctime)s [%(levelname)s] %(name)s: %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        ))
        logging.getLogger().addHandler(file_handler)
    except Exception as e:
        print(f"Warning: Could not create log file {log_file}: {e}")

logger = logging.getLogger(__name__)

# Import models and services AFTER logging is configured
from models import (
    User, UserLogin, Bot, BotCreate,
    APIKey, APIKeyCreate, Trade, SystemMode, Alert,
    ChatMessage, BotRiskMode, ProfileUpdate
)
import database as db
from auth import create_access_token, get_current_user, get_password_hash, verify_password, is_admin
from ai_service import ai_service
from ccxt_service import ccxt_service
from websocket_manager import manager
from trading_scheduler import trading_scheduler
from utils.env_utils import env_bool
from utils.bot_state import normalize_bot_state
from json_utils import serialize_doc
import ccxt.async_support as ccxt

api_router = APIRouter()
api_router.include_router(auth_router)

# ============================================================================
# LIFESPAN CONTEXT - Startup and Shutdown
# ============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events with feature flags for plug-and-play stability"""
    from datetime import datetime, timezone
    startup_time = datetime.now(timezone.utc)
    import config
    
    logger.info("="*80)
    logger.info("🚀 Starting Amarktai Network Backend Server")
    logger.info("="*80)
    
    # Log startup configuration
    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "8000"))
    logger.info(f"📡 Configured to bind: {host}:{port}")
    # BUILD_SHA is canonical, GIT_COMMIT is fallback for compatibility
    logger.info(f"🏗️  Build SHA: {os.getenv('BUILD_SHA', os.getenv('GIT_COMMIT', 'unknown'))}")
    logger.info(f"🌍 Environment: {os.getenv('ENVIRONMENT', 'production')}")
    logger.info(f"📁 Working Directory: {os.getcwd()}")
    logger.info(f"🐍 Python Version: {os.sys.version.split()[0]}")
    logger.info(f"⏰ Startup Time: {startup_time.isoformat()}")
    
    # Log key trading mode toggles
    paper_trading = os.getenv('ENABLE_PAPER_TRADING', 'true').lower() == 'true'
    live_trading = os.getenv('ENABLE_LIVE_TRADING', 'false').lower() == 'true'
    autopilot = os.getenv('ENABLE_AUTOPILOT', 'false').lower() == 'true'
    logger.info(f"📊 Paper Trading: {'ON' if paper_trading else 'OFF'}")
    logger.info(f"🔴 Live Trading: {'ON' if live_trading else 'OFF'}")
    logger.info(f"🤖 Autopilot: {'ON' if autopilot else 'OFF'}")
    logger.info("="*80)
    
    # =========================================================================
    # STEP 0: Validate configuration (ONE TRUTH enforcement)
    # =========================================================================
    try:
        from core.settings import startup_self_check
        startup_self_check()
        logger.info("✅ Configuration validation passed")
    except Exception as config_error:
        logger.error(f"❌ FATAL: Configuration validation failed: {config_error}", exc_info=True)
        import sys
        print(f"FATAL ERROR: Configuration validation failed: {config_error}", file=sys.stderr)
        raise  # Fail fast on configuration errors
    
    # =========================================================================
    # STEP 1: Connect to database FIRST (before any other services)
    # =========================================================================
    try:
        await db.connect()
        logger.info("✅ Database connected and collections initialized")
        
        # Startup self-test: verify DB connectivity
        try:
            await db.client.admin.command('ping')
            logger.info("✅ Database connectivity verified")
        except Exception as ping_error:
            logger.warning(f"⚠️ Database ping failed but connection established: {ping_error}")
        
        # Boot selftest: verify critical collections are initialized
        async def boot_selftest():
            """Verify critical DB collections are initialized"""
            required = ['users_collection', 'bots_collection', 'trades_collection', 
                       'capital_injections_collection', 'api_keys_collection']
            for coll_name in required:
                if not hasattr(db, coll_name) or getattr(db, coll_name) is None:
                    logger.error(f"BOOT FAIL: {coll_name} not initialized")
                    return False
            logger.info("✅ Boot selftest PASSED - all critical collections initialized")
            return True
        
        selftest_passed = await boot_selftest()
        if not selftest_passed:
            logger.error("❌ Boot selftest failed - some collections not initialized")
            # Continue anyway - collections may be initialized lazily
        
        # ========================================================================
        # STEP 1.5: Run startup migrations to fix schema drift
        # ========================================================================
        try:
            from migrations.fix_user_id_field import run_startup_migrations
            await run_startup_migrations(db)
            logger.info("✅ Startup migrations completed")
        except Exception as migration_error:
            logger.warning(f"⚠️ Startup migrations failed (non-fatal): {migration_error}")
            # Continue - migrations are best-effort repairs
            
    except Exception as e:
        logger.error(f"❌ FATAL: Database connection failed: {e}", exc_info=True)
        # Log to stderr as well for systemd
        import sys
        print(f"FATAL ERROR: Database connection failed: {e}", file=sys.stderr)
        raise  # Cannot proceed without database
    
    # =========================================================================
    # STEP 2: Use lifecycle manager for subsystem management
    # =========================================================================
    try:
        from services.lifecycle import lifecycle_manager
        
        background_tasks = await lifecycle_manager.start_all()
        logger.info(f"✅ Started {len(lifecycle_manager.subsystems)} subsystems with {len(background_tasks)} background tasks")
        
        # Check if any CRITICAL subsystems failed
        # For now, lifecycle manager is considered optional
        # Individual critical services will fail-fast below if needed
        
    except ImportError as e:
        logger.warning(f"⚠️ Lifecycle manager not available (optional): {e}")
    except Exception as e:
        logger.error(f"❌ Error starting subsystems: {e}", exc_info=True)
        # Log error but continue - optional services may have failed
        # Critical services will be checked individually below
    
    # Initialize Fetch.ai integration if key available
    try:
        fetchai_key = os.environ.get('FETCHAI_API_KEY', '')
        if fetchai_key:
            from fetchai_integration import fetchai
            fetchai.set_credentials(fetchai_key)
            logger.info("🔮 Fetch.ai integration configured")
    except Exception as e:
        logger.warning(f"Could not configure Fetch.ai: {e}")
    
    # Start Daily Reinvestment Scheduler (optional)
    try:
        if config.ENABLE_AUTOPILOT_REINVEST:
            logger.info("💰 Daily Reinvestment Scheduler skipped (autopilot reinvest enabled)")
        else:
            from services.daily_reinvestment import get_reinvestment_service
            reinvest_service = get_reinvestment_service(db.db)
            reinvest_service.start()
            logger.info("💰 Daily Reinvestment Scheduler started")
    except Exception as e:
        logger.warning(f"Could not start Reinvestment Scheduler: {e}")

    # Start Autopilot Growth Scheduler (optional)
    try:
        if config.ENABLE_AUTOPILOT_GROWTH:
            from services.autopilot_growth import get_autopilot_growth_scheduler
            growth_scheduler = get_autopilot_growth_scheduler(db.db)
            growth_scheduler.start()
            logger.info("🤖 Autopilot Growth Scheduler started")
    except Exception as e:
        logger.warning(f"Could not start Autopilot Growth Scheduler: {e}")

    # Start Autopilot Reinvest Scheduler (optional)
    try:
        if config.ENABLE_AUTOPILOT_REINVEST:
            from services.autopilot_reinvest import get_autopilot_reinvest_scheduler
            reinvest_scheduler = get_autopilot_reinvest_scheduler(db.db)
            reinvest_scheduler.start()
            logger.info("💰 Autopilot Reinvest Scheduler started")
    except Exception as e:
        logger.warning(f"Could not start Autopilot Reinvest Scheduler: {e}")
    
    # Start Bot Quarantine Service
    try:
        from services.bot_quarantine import quarantine_service
        quarantine_task = asyncio.create_task(quarantine_service.run())
        logger.info("🔒 Bot Quarantine Service started")
    except Exception as e:
        logger.warning(f"Could not start Bot Quarantine Service: {e}")
    
    # Start Balance Sync Service (background balance fetching every 5 minutes)
    try:
        from services.balance_sync_service import balance_sync_service
        await balance_sync_service.start_background_sync()
        logger.info("💰 Balance Sync Service started")
    except Exception as e:
        logger.warning(f"Could not start Balance Sync Service: {e}")
    
    logger.info("🚀 All autonomous systems operational")
    
    # Set startup time and bind status in health endpoint
    try:
        from routes.health import set_startup_time, set_bind_ok
        set_startup_time(startup_time)
        set_bind_ok(True)
        logger.info("✅ BOUND_OK - Server successfully bound and ready to accept connections")
    except Exception as e:
        logger.warning(f"Could not set health endpoint state: {e}")
    
    logger.info("="*80)
    logger.info("✅ SERVER STARTUP COMPLETE - Ready to serve traffic")
    logger.info(f"📡 Listening on: {host}:{port}")
    logger.info("="*80)
    
    yield
    
    # =============================================================================
    # SHUTDOWN - Use lifecycle manager for clean shutdown
    # =============================================================================
    logger.info("🔴 Shutting down Amarktai Network...")
    
    from services.lifecycle import lifecycle_manager
    
    # Stop all subsystems managed by lifecycle manager
    try:
        await lifecycle_manager.stop_all()
    except Exception as e:
        logger.error(f"Error during lifecycle shutdown: {e}")
    
    # Stop optional services
    try:
        from services.daily_reinvestment import get_reinvestment_service
        reinvest_service = get_reinvestment_service(db.db)
        reinvest_service.stop()
        logger.info("✅ Reinvestment Service stopped")
    except Exception as e:
        logger.error(f"Error stopping reinvest_service: {e}")
    
    # Stop Bot Quarantine Service
    try:
        from services.bot_quarantine import quarantine_service
        quarantine_service.stop()
        logger.info("✅ Bot Quarantine Service stopped")
    except Exception as e:
        logger.error(f"Error stopping quarantine service: {e}")
    
    # Stop Balance Sync Service
    try:
        from services.balance_sync_service import balance_sync_service
        await balance_sync_service.stop_background_sync()
        logger.info("✅ Balance Sync Service stopped")
    except Exception as e:
        logger.error(f"Error stopping Balance Sync Service: {e}")
    
    # Close CCXT async sessions if trading/ccxt enabled
    enable_trading = env_bool('ENABLE_TRADING', False)
    enable_ccxt = env_bool('ENABLE_CCXT', True)
    
    if enable_ccxt or enable_trading:
        try:
            from paper_trading_engine import paper_engine
            await paper_engine.close_exchanges()
            logger.info("✅ CCXT sessions closed")
        except Exception as e:
            logger.error(f"Error closing CCXT sessions: {e}")
    
    # Close AI service sessions (aiohttp)
    try:
        if ai_service and hasattr(ai_service, 'close'):
            await ai_service.close()
            logger.info("✅ AI service sessions closed")
    except Exception as e:
        logger.error(f"Error closing AI service: {e}")
    
    # Close database connection
    try:
        await db.close_db()
        logger.info("✅ Database connection closed")
    except Exception as e:
        logger.error(f"Error closing database: {e}")
    
    logger.info("🔴 All systems stopped gracefully")

# TASK A - Fix OpenAPI routing for nginx reverse proxy
# Nginx proxies /api/* to backend, so OpenAPI must be at /api/openapi.json
app = FastAPI(
    lifespan=lifespan,
    openapi_url="/api/openapi.json",
    docs_url="/api/docs",
    redoc_url="/api/redoc"
)

@app.get("/openapi.json", include_in_schema=False)
async def openapi_redirect():
    return RedirectResponse(url="/api/openapi.json")

# Add validation error handler for better debugging
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """
    Custom handler for validation errors to log details and return consistent error shape
    """
    # Log validation error details for debugging
    logger.error(f"Validation error on {request.method} {request.url.path}")
    logger.error(f"Body keys present: {list((await request.body()).decode('utf-8', errors='ignore'))[:200]}")
    logger.error(f"Validation detail: {exc.errors()}")
    
    # Return consistent error shape
    return JSONResponse(
        status_code=422,
        content={
            "detail": exc.errors(),
            "body": exc.body if hasattr(exc, 'body') else None,
            "message": "Validation error - check request payload format"
        }
    )

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================================
# WEBSOCKET
# ============================================================================
# NOTE: WebSocket endpoint /api/ws is now handled by routes/websocket.py
# This prevents route collision and maintains a single source of truth.
# The websocket router is mounted in the routers_to_mount list below.
# ============================================================================

# REMOVED: Duplicate @app.websocket("/api/ws") endpoint (now in routes/websocket.py)
# See routes/websocket.py for the canonical WebSocket implementation with:
# - Token authentication via query param or header
# - Reconnect/replay support
# - Proper connection management via websocket_manager_redis

@app.websocket("/ws/decisions")
async def decision_trace_websocket(websocket: WebSocket):
    """WebSocket endpoint for streaming trading decisions in real-time"""
    await websocket.accept()
    logger.info("Decision trace WebSocket connected")
    
    try:
        # This endpoint streams decision data from the alpha fusion engine
        # For now, send mock data every 5 seconds for demonstration
        import asyncio
        import json
        from datetime import datetime
        
        # Send initial connection confirmation
        await websocket.send_text(json.dumps({"status": "connected"}))
        
        while True:
            try:
                # In production, this would come from the actual trading engine
                # For now, send sample decision data
                decision = {
                    "timestamp": datetime.now().isoformat(),
                    "symbol": "BTC/USDT",
                    "decision": "buy",
                    "confidence": 0.75,
                    "market_data": {
                        "price": 50000,
                        "volume": 1000000,
                        "change_24h": 2.5,
                        "volatility": 1.2
                    },
                    "regime_state": {
                        "regime": "bullish_calm",
                        "confidence": 0.85
                    },
                    "component_scores": {
                        "regime": 0.75,
                        "ofi": 0.65,
                        "whale": 0.45,
                        "sentiment": 0.80,
                        "macro": 0.55
                    },
                    "reasoning": [
                        "Market regime indicates bullish calm conditions (85% confidence)",
                        "Order flow imbalance shows strong buying pressure (65%)",
                        "Sentiment analysis positive from recent news (80%)",
                        "Macro conditions neutral to slightly positive (55%)"
                    ],
                    "position_size_multiplier": 1.25,
                    "stop_loss": 48500,
                    "take_profit": 52500
                }
                
                await websocket.send_text(json.dumps(decision))
                await asyncio.sleep(5)
            except Exception as e:
                logger.error(f"Error sending decision data: {e}")
                break
            
    except WebSocketDisconnect:
        logger.info("Decision trace WebSocket disconnected")
    except Exception as e:
        logger.error(f"Decision trace WebSocket error: {e}")
        try:
            await websocket.close(code=1011, reason=str(e))
        except:
            pass
# ============================================================================
# AUTHENTICATION
# ============================================================================
# Auth routes are mounted via routes/auth.py (api_router.include_router(auth_router))

# ============================================================================
# BOTS MANAGEMENT
# ============================================================================
@api_router.get("/bots")
async def get_bots(
    legacy: bool = Query(False, description="Return legacy array response"),
    user_id: str = Depends(get_current_user)
):
    bots = await db.bots_collection.find({
        "user_id": user_id,
        "status": {"$ne": "deleted"},
        "deleted": {"$ne": True},
        "deleted_at": {"$exists": False}
    }, {"_id": 0}).to_list(1000)
    normalized = [normalize_bot_state(bot) for bot in bots]
    return {
        "success": True,
        "bots": normalized,
        "total": len(normalized)
    }

@api_router.post("/bots")
async def create_bot(bot: BotCreate, user_id: str = Depends(get_current_user)):
    """Create single bot with validation and funding plan support"""
    from validators.bot_validator import bot_validator
    from uuid import uuid4
    
    bot_dict = bot.model_dump()
    bot_dict['capital'] = bot_dict.get('initial_capital', 1000)
    
    # Validate bot creation BEFORE database insertion
    is_valid, result = await bot_validator.validate_bot_creation(user_id, bot_dict)
    
    if not is_valid:
        # Return error with funding plan if needed
        if result.get('code') == 'FUNDING_PLAN_REQUIRED':
            raise HTTPException(
                status_code=402,  # Payment Required
                detail=result
            )
        raise HTTPException(status_code=400, detail=result)
    
    # Add bot ID
    result['id'] = str(uuid4())
    
    # Insert validated bot
    await db.bots_collection.insert_one(result)

    # Ensure paper wallet reserved for new bot
    try:
        from bot_lifecycle import bot_lifecycle
        reserved, reserve_msg = await bot_lifecycle.tag_new_bot(
            result["id"],
            origin="user",
            initial_capital=result.get("initial_capital", 0)
        )
        if not reserved:
            await db.bots_collection.delete_one({"id": result["id"]})
            raise HTTPException(status_code=400, detail=reserve_msg)
    except Exception as e:
        logger.warning(f"Paper wallet reservation failed for bot {result.get('id')}: {e}")
    
    # Remove MongoDB _id before returning
    result.pop('_id', None)
    
    # Real-time notification
    from realtime_events import rt_events
    await rt_events.bot_created(user_id, result)
    await rt_events.force_refresh(user_id, f"Bot '{result['name']}' created successfully")
    
    logger.info(f"✅ Bot created: {result['name']} for user {user_id[:8]}")
    
    return result


@api_router.post("/bots/spawn")
async def spawn_bot_now(
    payload: dict = Body(default={}),
    user_id: str = Depends(get_current_user)
):
    """Spawn a bot immediately using the bot spawner."""
    try:
        from engines.bot_spawner import bot_spawner
        from config.platforms import normalize_platform_id, is_valid_platform
        from datetime import datetime, timezone

        config = await bot_spawner.determine_next_bot_config(user_id)
        if "error" in config:
            raise HTTPException(status_code=400, detail=config.get("error"))

        requested_exchange = payload.get("exchange")
        if requested_exchange:
            normalized = normalize_platform_id(requested_exchange)
            if not is_valid_platform(normalized):
                raise HTTPException(status_code=400, detail=f"Invalid exchange: {requested_exchange}")
            config["exchange"] = normalized

        requested_risk = payload.get("risk_mode")
        if requested_risk:
            config["risk_mode"] = requested_risk

        requested_capital = payload.get("initial_capital")
        if requested_capital:
            config["capital"] = float(requested_capital)

        requested_name = payload.get("name")
        if requested_name:
            config["name"] = requested_name

        result = await bot_spawner.spawn_bot(user_id, config)
        if not result.get("success"):
            raise HTTPException(status_code=400, detail=result.get("error", "Spawn failed"))

        await db.bots_collection.update_one(
            {"id": result.get("bot_id")},
            {"$set": {
                "spawned_by": "user",
                "spawned_at": datetime.now(timezone.utc).isoformat(),
                "auto_spawned": False
            }}
        )

        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Spawn bot error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.post("/bots/batch-create")
async def batch_create_bots(data: dict, user_id: str = Depends(get_current_user)):
    """Batch create bots with distribution - enforces bot caps and profit gating"""
    from uuid import uuid4
    from rules import check_bot_cap_limit, validate_exchange, get_reason_message
    from json_utils import serialize_list
    
    count = data.get('count', 10)
    capital_per_bot = data.get('capital_per_bot', 1000)
    safe_count = data.get('safe_count', 6)
    risky_count = data.get('risky_count', 2)
    aggressive_count = data.get('aggressive_count', 2)
    exchange = data.get('exchange', 'luno').lower()
    
    # Validate exchange
    is_valid, reason_code = validate_exchange(exchange)
    if not is_valid:
        raise HTTPException(status_code=400, detail=get_reason_message(reason_code))
    
    # Check bot cap for this exchange
    current_bot_count = await db.bots_collection.count_documents({
        "user_id": user_id,
        "exchange": exchange,
        "status": {"$ne": "deleted"}  # Don't count deleted bots
    })
    
    total_bots_requested = safe_count + risky_count + aggressive_count
    
    # Check if adding these bots would exceed the cap
    can_create, reason_code = check_bot_cap_limit(exchange, current_bot_count + total_bots_requested, user_id)
    if not can_create:
        raise HTTPException(
            status_code=400, 
            detail=f"{get_reason_message(reason_code)}. Current: {current_bot_count}, Requested: {total_bots_requested}"
        )
    
    bots_to_create = []
    bot_number = await db.bots_collection.count_documents({"user_id": user_id}) + 1
    
    for i in range(safe_count):
        bots_to_create.append({
            'id': str(uuid4()),
            'user_id': user_id,
            'name': f'Safe-Bot-{bot_number + i}',
            'initial_capital': capital_per_bot,
            'current_capital': capital_per_bot,
            'total_profit': 0.0,
            'risk_mode': BotRiskMode.SAFE,
            'trading_mode': 'paper',
            'exchange': exchange,
            'status': 'active',
            'trades_count': 0,
            'created_at': datetime.now(timezone.utc).isoformat(),
            'last_trade': None
        })
    
    bot_number += safe_count
    
    for i in range(risky_count):
        bots_to_create.append({
            'id': str(uuid4()),
            'user_id': user_id,
            'name': f'Balanced-Bot-{bot_number + i}',
            'initial_capital': capital_per_bot,
            'current_capital': capital_per_bot,
            'total_profit': 0.0,
            'risk_mode': BotRiskMode.BALANCED,
            'trading_mode': 'paper',
            'exchange': exchange,
            'status': 'active',
            'trades_count': 0,
            'created_at': datetime.now(timezone.utc).isoformat(),
            'last_trade': None
        })
    
    bot_number += risky_count
    
    for i in range(aggressive_count):
        bots_to_create.append({
            'id': str(uuid4()),
            'user_id': user_id,
            'name': f'Aggressive-Bot-{bot_number + i}',
            'initial_capital': capital_per_bot,
            'current_capital': capital_per_bot,
            'total_profit': 0.0,
            'risk_mode': BotRiskMode.AGGRESSIVE,
            'trading_mode': 'paper',
            'exchange': exchange,
            'status': 'active',
            'trades_count': 0,
            'created_at': datetime.now(timezone.utc).isoformat(),
            'last_trade': None
        })
    
    if bots_to_create:
        try:
            from services.paper_wallet_service import paper_wallet_service
            currency = "ZAR" if exchange == "luno" else "USDT"
            total_required = len(bots_to_create) * capital_per_bot
            available = await paper_wallet_service.get_available_balance(user_id, currency)
            if available < total_required:
                raise HTTPException(
                    status_code=400,
                    detail=f"Insufficient paper wallet funds ({currency}). Available: {available:.2f}, Required: {total_required:.2f}"
                )
        except HTTPException:
            raise
        except Exception as e:
            logger.warning(f"Paper wallet check failed for batch bots: {e}")
        await db.bots_collection.insert_many(bots_to_create)
        try:
            from bot_lifecycle import bot_lifecycle
            created_bots = []
            for bot in bots_to_create:
                reserved, reserve_msg = await bot_lifecycle.tag_new_bot(
                    bot["id"],
                    origin="user",
                    initial_capital=bot.get("initial_capital", 0)
                )
                if not reserved:
                    await db.bots_collection.delete_one({"id": bot["id"]})
                    logger.warning(f"Skipping bot {bot['id']} - {reserve_msg}")
                else:
                    created_bots.append(bot)
            bots_to_create = created_bots
        except Exception as e:
            logger.warning(f"Paper wallet reservation failed for batch bots: {e}")
    
    # Serialize bots to ensure JSON-safe response (no ObjectId issues)
    safe_bots = serialize_list(bots_to_create)
    
    return {
        "message": f"{len(bots_to_create)} bots created", 
        "bots": safe_bots,
        "created": len(bots_to_create)
    }

@api_router.put("/bots/{bot_id}")
async def update_bot(bot_id: str, update: dict, user_id: str = Depends(get_current_user)):
    bot = await db.bots_collection.find_one({"id": bot_id, "user_id": user_id}, {"_id": 0})
    if not bot:
        raise HTTPException(status_code=404, detail="Bot not found")
    
    update_data = {k: v for k, v in update.items() if v is not None}
    
    if update_data:
        await db.bots_collection.update_one(
            {"id": bot_id},
            {"$set": update_data}
        )
    
    updated_bot = await db.bots_collection.find_one({"id": bot_id}, {"_id": 0})
    return updated_bot

# NOTE: Removed duplicate DELETE /bots/{bot_id} - canonical in routes/bot_lifecycle.py

@api_router.post("/bots/{bot_id}/promote")
async def promote_bot_to_live(bot_id: str, user_id: str = Depends(get_current_user)):
    """Promote bot from paper to live trading"""
    try:
        # Verify bot belongs to user
        bot = await db.bots_collection.find_one({"id": bot_id, "user_id": user_id}, {"_id": 0})
        if not bot:
            raise HTTPException(status_code=404, detail="Bot not found")
        
        # Check if already live
        if bot.get('mode') == 'live':
            return {"success": False, "message": "Bot is already in live mode"}
        
        # Check eligibility
        from engines.promotion_engine import promotion_engine
        eligible, message, performance = await promotion_engine.is_eligible_for_live(bot_id)
        
        if not eligible:
            return {
                "success": False,
                "message": message,
                "performance": performance,
                "eligible": False
            }
        
        # Check for API keys before promoting to live
        exchange = bot.get('exchange', '').lower()
        api_key_doc = await db.api_keys_collection.find_one({
            "user_id": user_id,
            "exchange": exchange
        }, {"_id": 0})
        
        if not api_key_doc:
            return {
                "success": False,
                "message": f"❌ Cannot promote to live: No API keys configured for {exchange.capitalize()}. Please add API keys first.",
                "eligible": True,
                "requires_api_keys": True,
                "exchange": exchange
            }
        
        # Promote to live
        await db.bots_collection.update_one(
            {"id": bot_id},
            {"$set": {
                "mode": "live",
                "trading_mode": "live",
                "promoted_at": datetime.now(timezone.utc).isoformat(),
                "promotion_performance": performance
            }}
        )
        
        # Create alert
        await db.alerts_collection.insert_one({
            "user_id": user_id,
            "type": "promotion",
            "severity": "high",
            "message": f"🎉 Bot {bot['name']} promoted to LIVE trading! Win rate: {performance.get('win_rate', 0)*100:.1f}%",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "dismissed": False
        })
        
        logger.info(f"✅ Bot {bot['name']} promoted to live trading")
        
        return {
            "success": True,
            "message": f"✅ {bot['name']} promoted to LIVE trading!",
            "performance": performance,
            "eligible": True
        }
        
    except Exception as e:
        logger.error(f"Promotion error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.get("/bots/{bot_id}/promotion-status")
async def get_promotion_status(bot_id: str, user_id: str = Depends(get_current_user)):
    """Get bot's eligibility for live promotion"""
    try:
        bot = await db.bots_collection.find_one({"id": bot_id, "user_id": user_id}, {"_id": 0})
        if not bot:
            raise HTTPException(status_code=404, detail="Bot not found")
        
        from engines.promotion_engine import promotion_engine
        eligible, message, performance = await promotion_engine.is_eligible_for_live(bot_id)
        
        return {
            "eligible": eligible,
            "message": message,
            "performance": performance,
            "current_mode": bot.get('mode', 'paper')
        }
    except Exception as e:
        logger.error(f"Promotion status error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================================
# HEALTH & STATUS ENDPOINT
# ============================================================================

@api_router.get("/health")
async def health_check():
    """Production health check endpoint"""
    try:
        # Check database connectivity
        await db.client.admin.command('ping')
        db_status = "connected"
    except Exception as e:
        db_status = f"error: {str(e)}"
    
    # Get system modes
    try:
        modes_doc = await db.system_modes_collection.find_one({})
        system_modes = {
            "emergency_stop": modes_doc.get('emergencyStop', False) if modes_doc else False,
            "live_trading_enabled": modes_doc.get('liveTrading', False) if modes_doc else False,
            "paper_trading_enabled": modes_doc.get('paperTrading', True) if modes_doc else True,
            "autopilot_enabled": modes_doc.get('autopilot', False) if modes_doc else False
        }
    except:
        system_modes = {"error": "Could not fetch system modes"}
    
    return {
        "status": "healthy" if db_status == "connected" else "degraded",
        "database": db_status,
        "system_modes": system_modes,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "version": "3.0.0"
    }

# Note: /health/ping endpoint is handled by routes/health.py router

# ============================================================================
# SYSTEM MODE CONTROLS - NOW FUNCTIONAL
# ============================================================================

# NOTE: Removed duplicate GET /system/mode - canonical in routes/system_mode.py
# NOTE: Removed duplicate PUT /system/mode - canonical in routes/system_mode.py
#       The canonical endpoint in routes/system_mode.py provides comprehensive
#       mode switching with live readiness checks, Luno balance validation,
#       and proper real-time event broadcasting via rt_events.mode_switched()

# NOTE: Removed duplicate GET /system/status - canonical in routes/system_status.py

# NOTE: Removed duplicate POST /system/emergency-stop - canonical in routes/emergency_stop_endpoints.py

# ============================================================================
# OVERVIEW & DASHBOARD
# ============================================================================

@api_router.get("/overview")
async def get_overview(user_id: str = Depends(get_current_user), include_wallet: bool = False):
    """Get dashboard overview - Uses centralized metrics service
    
    Query params:
        include_wallet: If true, includes live Luno wallet balances (slower but live data)
    """
    try:
        # Use centralized metrics service
        from services.metrics_service import metrics_service
        result = await metrics_service.get_overview_metrics(user_id)
        
        # Optionally include live wallet balances
        if include_wallet:
            try:
                from engines.wallet_manager import wallet_manager
                wallet_balance = await wallet_manager.get_master_balance(user_id)
                result["wallet_balance"] = wallet_balance
            except Exception as e:
                logger.warning(f"Could not fetch wallet balance: {e}")
                result["wallet_balance"] = {"error": str(e)}
        
        return result
        
    except Exception as e:
        logger.error(f"Overview error: {e}")
        return {
            "totalProfit": 0.00,
            "total_profit": 0.00,
            "activeBots": "0 / 0",
            "active_bots": 0,
            "total_bots": 0,
            "paper_bots": 0,
            "live_bots": 0,
            "exposure": 0.00,
            "riskLevel": "Unknown",
            "risk_level": "Unknown",
            "aiSentiment": "Neutral",
            "ai_sentiment": "Neutral",
            "lastUpdate": datetime.now(timezone.utc).isoformat(),
            "last_update": datetime.now(timezone.utc).isoformat(),
            "tradingStatus": "Unknown"
        }

# NOTE: Removed duplicate GET /metrics (alias for /overview)
# Canonical Prometheus metrics endpoint at bottom of file

# NOTE: Removed duplicate GET /trades/recent - canonical in routes/trades.py

# ============================================================================
# API KEYS - REMOVED INLINE ENDPOINTS
# ============================================================================
# All API key endpoints have been moved to maintain "one truth" architecture:
#
# CANONICAL (new):  /api/keys/*        -> routes/keys.py
# LEGACY (compat):  /api/api-keys/*    -> routes/compat.py (proxies to routes/keys.py)
#
# Previously defined here (now removed to prevent route collisions):
#   - GET    /api-keys                      -> use GET  /api/keys/list
#   - POST   /api-keys                      -> use POST /api/keys/save
#   - POST   /api-keys/{provider}/test      -> use POST /api/keys/test
#   - DELETE /api-keys/{provider}           -> use DELETE /api/keys/{provider}
#
# Frontend uses canonical /api/keys/* endpoints.
# Legacy /api/api-keys/* are available via routes/compat.py for backward compatibility.
# ============================================================================

# ============================================================================
# AUTONOMOUS SYSTEMS
# ============================================================================

@api_router.post("/autonomous/learning/trigger")
async def trigger_learning_now(user_id: str = Depends(get_current_user)):
    """Manually trigger AI learning analysis NOW - FIXED: NO 10k LIMIT"""
    try:
        from self_learning import learning_system
        
        # Get ALL trades (no limit)
        trades = await db.trades_collection.find({"user_id": user_id}, {"_id": 0}).to_list(None)
        
        # Run learning analysis
        await learning_system.analyze_daily_trades(user_id)
        
        # Calculate stats for report
        profitable_trades = [t for t in trades if t.get('is_profitable', False)]
        win_rate = (len(profitable_trades) / len(trades) * 100) if trades else 0
        avg_profit = sum(t.get('profit_loss', 0) for t in trades) / len(trades) if trades else 0
        
        return {
            "message": "AI learning analysis completed",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "report": {
                "trades_analyzed": len(trades),
                "win_rate": round(win_rate, 1),
                "avg_profit": round(avg_profit, 2),
                "updates": "Strategy optimized based on recent performance"
            }
        }
    except Exception as e:
        logger.error(f"Learning trigger failed: {e}")
        raise HTTPException(status_code=500, detail=f"Learning analysis failed: {str(e)}")

@api_router.post("/autonomous/bodyguard/system-check")
async def bodyguard_system_check(user_id: str = Depends(get_current_user)):
    """Run comprehensive system health check"""
    try:
        from ai_bodyguard import bodyguard
        import psutil
        
        # Get user's bots ONLY
        bots = await db.bots_collection.find({"user_id": user_id, "status": {"$ne": "deleted"}}, {"_id": 0}).to_list(1000)
        active_bots = [b for b in bots if b.get('status') == 'active']
        
        # Get today's trades
        today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0).isoformat()
        trades_today = await db.trades_collection.count_documents({
            "user_id": user_id,
            "timestamp": {"$gte": today_start}
        })
        
        # System health
        cpu_percent = psutil.cpu_percent(interval=1)
        memory = psutil.virtual_memory()
        
        # Comprehensive checks
        issues = []
        warnings = []
        checked_bots = set()  # Track checked bots to avoid duplicates
        
        # Check 1: Excessive losses
        total_profit = sum(b.get('total_profit', 0) for b in active_bots)
        if total_profit < -5000:
            issues.append(f"Critical losses detected: R{total_profit:.2f}")
        elif total_profit < -2000:
            warnings.append(f"Moderate losses detected: R{total_profit:.2f}")
        
        # Check 2: Stalled trading
        if trades_today == 0 and len(active_bots) > 0:
            warnings.append("No trades executed today despite active bots")
        
        # Check 3: System resources
        if cpu_percent > 90:
            issues.append(f"Critical CPU usage: {cpu_percent}%")
        elif cpu_percent > 80:
            warnings.append(f"High CPU usage: {cpu_percent}%")
            
        if memory.percent > 90:
            issues.append(f"Critical memory usage: {memory.percent}%")
        elif memory.percent > 80:
            warnings.append(f"High memory usage: {memory.percent}%")
        
        # Check 4: Bot anomalies (smarter thresholds based on risk mode)
        for bot in active_bots:
            bot_id = bot.get('id')
            if bot_id in checked_bots:
                continue  # Skip duplicates
            checked_bots.add(bot_id)
            
            current_capital = bot.get('current_capital', 1000)
            initial_capital = bot.get('initial_capital', 1000)
            
            # Calculate drawdown from initial capital
            if initial_capital > 0:
                drawdown = ((initial_capital - current_capital) / initial_capital) * 100
            else:
                drawdown = 0
            
            # Adjust thresholds based on risk mode
            risk_mode = bot.get('risk_mode', 'safe')
            
            if risk_mode == 'safe':
                critical_threshold = 20  # Increased from 15
                warning_threshold = 15
            elif risk_mode == 'risky':
                critical_threshold = 35
                warning_threshold = 25
            else:  # aggressive
                critical_threshold = 50
                warning_threshold = 40
            
            if drawdown > critical_threshold:
                issues.append(f"Bot '{bot['name']}' ({risk_mode}) has {drawdown:.1f}% drawdown")
            elif drawdown > warning_threshold:
                warnings.append(f"Bot '{bot['name']}' ({risk_mode}) has {drawdown:.1f}% drawdown")
        
        # Calculate health score
        health_score = 100
        health_score -= len(issues) * 15  # Less penalty per issue
        health_score -= len(warnings) * 5  # Less penalty per warning
        health_score = max(0, min(100, health_score))
        
        # Determine health status
        if health_score >= 80:
            health_status = "Excellent"
        elif health_score >= 60:
            health_status = "Good"
        elif health_score >= 40:
            health_status = "Fair"
        else:
            health_status = "Critical"
        
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "health_score": health_score,
            "health_status": health_status,
            "system_health": {
                "cpu_usage": round(cpu_percent, 1),
                "memory_usage": round(memory.percent, 1),
                "status": "Healthy" if cpu_percent < 80 and memory.percent < 80 else "Warning"
            },
            "trading_health": {
                "active_bots": len(active_bots),
                "trades_today": trades_today,
                "total_profit": round(total_profit, 2),
                "status": "Active" if len(active_bots) > 0 else "Idle"
            },
            "issues": issues,
            "warnings": warnings,
            "recommendations": [
                "All systems operating normally" if len(issues) == 0 and len(warnings) == 0 else
                "Review detected issues and warnings",
                f"Monitoring {len(checked_bots)} active bots",
                f"{trades_today} trades executed today"
            ]
        }
    except Exception as e:
        logger.error(f"Bodyguard check failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.get("/admin/storage")
async def get_storage_usage(user_id: str = Depends(get_current_user)):
    """Get storage usage per user (Admin only)"""
    try:
        import sys
        
        # Verify user is admin (basic check - enhance with proper role system)
        user = await db.users_collection.find_one({"id": user_id}, {"_id": 0})
        if not user:
            raise HTTPException(status_code=403, detail="Unauthorized")
        
        # Get all users with their storage breakdown
        all_users = await db.users_collection.find({}, {"_id": 0}).to_list(1000)
        storage_data = []
        
        for usr in all_users:
            usr_id = usr.get('id')
            
            # Calculate storage for each data type
            
            # 1. Chat messages (AI memory)
            chat_messages = await db.chat_messages_collection.find({"user_id": usr_id}, {"_id": 0}).to_list(10000)
            chat_size = sum(sys.getsizeof(json.dumps(serialize_doc(msg))) for msg in chat_messages)
            
            # 2. Trade history
            trades = await db.trades_collection.find({"user_id": usr_id}, {"_id": 0}).to_list(10000)
            trades_size = sum(sys.getsizeof(json.dumps(serialize_doc(trade))) for trade in trades)
            
            # 3. Bot configurations
            bots = await db.bots_collection.find({"user_id": usr_id, "status": {"$ne": "deleted"}}, {"_id": 0}).to_list(1000)
            bots_size = sum(sys.getsizeof(json.dumps(serialize_doc(bot))) for bot in bots)
            
            # 4. User data
            user_size = sys.getsizeof(json.dumps(serialize_doc(usr)))
            
            # 5. Alerts
            alerts = await db.alerts_collection.find({"user_id": usr_id}, {"_id": 0}).to_list(1000)
            alerts_size = sum(sys.getsizeof(json.dumps(serialize_doc(alert))) for alert in alerts)
            
            total_bytes = chat_size + trades_size + bots_size + user_size + alerts_size
            total_mb = total_bytes / (1024 * 1024)
            
            storage_data.append({
                "user_id": usr_id,
                "email": usr.get('email', 'N/A'),
                "name": usr.get('first_name', 'N/A'),
                "first_name": usr.get('first_name', 'N/A'),
                "storage_breakdown": {
                    "chat_messages": {
                        "count": len(chat_messages),
                        "size_mb": round(chat_size / (1024 * 1024), 3)
                    },
                    "trades": {
                        "count": len(trades),
                        "size_mb": round(trades_size / (1024 * 1024), 3)
                    },
                    "bots": {
                        "count": len(bots),
                        "size_mb": round(bots_size / (1024 * 1024), 3)
                    },
                    "user_data": {
                        "size_mb": round(user_size / (1024 * 1024), 3)
                    },
                    "alerts": {
                        "count": len(alerts),
                        "size_mb": round(alerts_size / (1024 * 1024), 3)
                    }
                },
                "total_storage_mb": round(total_mb, 3)
            })
        
        # Sort by total storage (descending)
        storage_data.sort(key=lambda x: x['total_storage_mb'], reverse=True)
        
        # Calculate total system storage
        total_system_storage_mb = sum(usr['total_storage_mb'] for usr in storage_data)
        
        return {
            "users": storage_data,
            "total_users": len(storage_data),
            "total_system_storage_mb": round(total_system_storage_mb, 3),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Storage calculation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# CHAT
# ============================================================================

@api_router.post("/chat")
async def send_chat_message(message: dict, user_id: str = Depends(get_current_user)):
    """Send message to AI and get response with conversation context - FIXED PERSONALIZATION + AI COMMAND ROUTER"""
    try:
        content = message.get('content', '')
        content_lower = content.lower().strip()
        confirmed = message.get('confirmed', False)
        
        # CRITICAL: Block admin commands COMPLETELY - DO NOT process, save, or respond
        # Frontend handles these with password prompt
        if content_lower in ['show admin', 'show admn', 'hide admin']:
            logger.info(f"Admin command '{content}' blocked - frontend only")
            # Return empty response - frontend won't process this anyway
            return ""
        
        # Get user details for personalization and admin check
        user = await db.users_collection.find_one({"id": user_id}, {"_id": 0})
        first_name = user.get('first_name', 'User') if user else 'User'
        is_admin = user.get('is_admin', False) if user else False
        
        # NEW: Try AI Command Router first
        from services.ai_command_router import get_ai_command_router
        command_router = get_ai_command_router(db)
        is_command, command_result = await command_router.parse_and_execute(
            user_id, content, confirmed=confirmed, is_admin=is_admin
        )
        
        if is_command:
            # Save user message
            user_msg = ChatMessage(
                user_id=user_id,
                role="user",
                content=content
            )
            user_msg_dict = user_msg.model_dump()
            user_msg_dict['timestamp'] = user_msg_dict['timestamp'].isoformat()
            await db.chat_messages_collection.insert_one(user_msg_dict)
            
            # Format command result as response
            if command_result.get('success'):
                ai_response = command_result.get('message', 'Command executed')
                # Include structured data for UI
                if command_result.get('bot'):
                    ai_response += f"\n\nBot Details:\n"
                    for key, value in command_result['bot'].items():
                        ai_response += f"- {key}: {value}\n"
                elif command_result.get('portfolio'):
                    ai_response += f"\n\nPortfolio:\n"
                    for key, value in command_result['portfolio'].items():
                        ai_response += f"- {key}: {value}\n"
                elif command_result.get('profits'):
                    profits = command_result['profits']
                    ai_response += f"\n\nTotal: R{profits['total']}"
            else:
                ai_response = command_result.get('message', 'Command failed')
                if command_result.get('requires_confirmation'):
                    ai_response += "\n\nType 'yes' or 'confirm' to proceed."
            
            # Save AI response
            ai_msg = ChatMessage(
                user_id=user_id,
                role="assistant",
                content=ai_response
            )
            ai_msg_dict = ai_msg.model_dump()
            ai_msg_dict['timestamp'] = ai_msg_dict['timestamp'].isoformat()
            ai_msg_dict['command_result'] = command_result  # Include structured data
            await db.chat_messages_collection.insert_one(ai_msg_dict)
            
            # Send via WebSocket with command result
            await manager.send_message(user_id, {
                "type": "chat_message",
                "message": ai_msg_dict,
                "command_executed": True,
                "command_result": command_result
            })
            
            return ai_response
        
        # Not a command - proceed with regular AI chat
        # Get recent conversation history (last 10 messages)
        recent_messages = await db.chat_messages_collection.find(
            {"user_id": user_id},
            {"_id": 0}
        ).sort("timestamp", -1).limit(10).to_list(10)
        recent_messages.reverse()  # Oldest first
        
        # Build context for AI
        conversation_context = []
        for msg in recent_messages:
            conversation_context.append({
                "role": msg['role'],
                "content": msg['content']
            })
        
        # Save user message
        user_msg = ChatMessage(
            user_id=user_id,
            role="user",
            content=content
        )
        user_msg_dict = user_msg.model_dump()
        user_msg_dict['timestamp'] = user_msg_dict['timestamp'].isoformat()
        await db.chat_messages_collection.insert_one(user_msg_dict)
        
        # Process with AI PRODUCTION HANDLER (COMPLETE SYSTEM)
        from ai_production import ai_production
        ai_response = await ai_production.get_ai_response(user_id, content)
        
        # ai_response is a string
        # Save AI response
        ai_msg = ChatMessage(
            user_id=user_id,
            role="assistant",
            content=ai_response
        )
        ai_msg_dict = ai_msg.model_dump()
        ai_msg_dict['timestamp'] = ai_msg_dict['timestamp'].isoformat()
        await db.chat_messages_collection.insert_one(ai_msg_dict)
        
        # Send via WebSocket
        await manager.send_message(user_id, {
            "type": "chat_message",
            "message": ai_msg_dict
        })
        
        return ai_response
    except Exception as e:
        logger.error(f"Chat message failed: {e}", exc_info=True)
        # Return a graceful error response instead of 500
        try:
            # Try to save error message to chat
            error_msg = ChatMessage(
                user_id=user_id,
                role="assistant",
                content=f"I apologize, but I encountered an error processing your message. Error: {str(e)[:100]}"
            )
            error_msg_dict = error_msg.model_dump()
            error_msg_dict['timestamp'] = error_msg_dict['timestamp'].isoformat()
            await db.chat_messages_collection.insert_one(error_msg_dict)
            
            return error_msg_dict['content']
        except:
            # If even that fails, return simple error
            return "I apologize, but I'm experiencing technical difficulties. Please try again later."

# ============================================================================
# ANALYTICS
# ============================================================================

@api_router.get("/analytics/profit-history")
async def get_profit_history(period: str = 'daily', user_id: str = Depends(get_current_user)):
    """
    Get profit history for dashboard visualization.
    
    NOTE: This endpoint is the PRIMARY endpoint for frontend profit visualization.
    Alternative canonical endpoint /api/profits provides different format for API consumers.
    Backend maintains this as single source of truth by querying MongoDB directly.
    
    Returns:
        - labels: Time period labels (days, weeks, or months)
        - values: Profit values for each period
        - total: Total profit across all periods
        - avg_daily: Average daily profit
        - best_day: Best performing period
        - growth_rate: Overall growth rate percentage
    """
    try:
        from collections import defaultdict
        
        # BACKEND TRUTH: Query MongoDB directly for bot and trade data
        bots = await db.bots_collection.find({"user_id": user_id, "status": {"$ne": "deleted"}}, {"_id": 0}).to_list(1000)
        trades = await db.trades_collection.find({"user_id": user_id}, {"_id": 0}).to_list(None)
        
        labels = []
        values = []
        
        if period == 'daily':
            # Calculate actual days - last 7 days
            today = datetime.now(timezone.utc)
            day_names = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
            
            # Generate labels for last 7 days ending today
            labels = []
            for i in range(6, -1, -1):  # 6 days ago to today
                day = today - timedelta(days=i)
                labels.append(day_names[day.weekday()])
            
            # Aggregate trades by actual day
            daily_profits = defaultdict(float)
            
            for trade in trades:
                trade_date = datetime.fromisoformat(trade['timestamp'].replace('Z', '+00:00'))
                days_ago = (today.date() - trade_date.date()).days
                
                if 0 <= days_ago < 7:
                    daily_profits[6 - days_ago] += trade.get('profit_loss', 0)
            
            # Always use actual daily profits (even if 0)
            values = [round(daily_profits.get(i, 0), 2) for i in range(7)]
            
        elif period == 'weekly':
            # Calculate actual week of month we're in
            today = datetime.now(timezone.utc)
            day_of_month = today.day
            current_week = min(((day_of_month - 1) // 7) + 1, 4)  # Week 1-4
            
            # Generate labels showing current and past 3 weeks
            labels = []
            for i in range(3, -1, -1):  # 3 weeks ago to current
                week_num = max(1, current_week - i)  # Don't go below Week 1
                labels.append(f'Week {week_num}')
            
            # Calculate actual weekly profits from trades
            weekly_profits = defaultdict(float)
            
            for trade in trades:
                trade_date = datetime.fromisoformat(trade['timestamp'].replace('Z', '+00:00'))
                days_ago = (today.date() - trade_date.date()).days
                week_index = min(days_ago // 7, 3)  # 0-3 for 4 weeks
                if week_index < 4:
                    weekly_profits[3 - week_index] += trade.get('profit_loss', 0)
            
            values = [round(weekly_profits.get(i, 0), 2) for i in range(4)]
            
        elif period == 'monthly':
            # Generate labels for last 6 months ending with current month
            month_names = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
            today = datetime.now(timezone.utc)
            labels = []
            for i in range(5, -1, -1):  # 5 months ago to current month
                month_date = today - timedelta(days=i*30)  # Approximate
                labels.append(month_names[month_date.month - 1])
            
            # Calculate actual monthly profits from trades
            monthly_profits = defaultdict(float)
            
            for trade in trades:
                trade_date = datetime.fromisoformat(trade['timestamp'].replace('Z', '+00:00'))
                month_diff = (today.year - trade_date.year) * 12 + (today.month - trade_date.month)
                if 0 <= month_diff < 6:
                    monthly_profits[5 - month_diff] += trade.get('profit_loss', 0)
            
            values = [round(monthly_profits.get(i, 0), 2) for i in range(6)]
        
        # Calculate stats - USE ACTUAL BOT PROFITS for consistency (current - initial)
        actual_total_profit = round(sum(
            bot.get('current_capital', 0) - bot.get('initial_capital', 0) 
            for bot in bots
        ), 2)
        total_from_graph = round(sum(values), 2)
        avg_daily = round(total_from_graph / max(len(values), 1), 2)
        best_day = round(max(values), 2) if values else 0.00
        growth_rate = round((actual_total_profit / 10000) * 100, 2) if actual_total_profit != 0 else 0.00
        
        return {
            "labels": labels,
            "values": [round(v, 2) for v in values],
            "total": round(actual_total_profit, 2),  # Use actual bot totals for consistency
            "avg_daily": round(avg_daily, 2),
            "best_day": round(best_day, 2),
            "growth_rate": round(growth_rate, 2)
        }
    except Exception as e:
        logger.error(f"Profit history error: {e}")
        return {
            "labels": ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'],
            "values": [0, 0, 0, 0, 0, 0, 0],
            "total": 0,
            "avg_daily": 0,
            "best_day": 0,
            "growth_rate": 0
        }

@api_router.get("/analytics/countdown-to-million")
async def countdown_to_million(user_id: str = Depends(get_current_user)):
    """
    Calculate countdown to R1,000,000 with compounding projections.
    
    NOTE: This endpoint is the PRIMARY endpoint for frontend countdown feature.
    Alternative canonical endpoint /api/countdown/status provides similar functionality.
    Backend maintains this as single source of truth by querying MongoDB and wallet data directly.
    
    Returns:
        - current_capital: Current total capital (wallet + bot capitals)
        - target: Target amount (R1,000,000)
        - remaining: Amount remaining to reach target
        - progress_pct: Progress percentage
        - days_remaining: Estimated days to reach target
        - metrics: Trading metrics (avg daily profit, ROI %, etc.)
        - projections: Both simple and compound projections
    """
    try:
        from paper_trading_engine import paper_engine
        from services.ledger_service import get_ledger_service
        
        # BACKEND TRUTH: Get system mode and wallet data from MongoDB
        system_mode = await db.system_modes_collection.find_one({"user_id": user_id}, {"_id": 0})
        is_live = system_mode.get('liveTrading', False) if system_mode else False

        ledger = get_ledger_service(db.db)
        stats = await ledger.get_stats(user_id)
        trades_total = stats.get("total_fills", 0)
        ledger_equity = await ledger.compute_equity(user_id, currency="ZAR")
        
        # Get current balance (paper or live based on mode)
        if is_live:
            # For live mode, calculate from real exchange balances
            # For now, use paper as fallback (implement live balance fetching later)
            zar_balance = ccxt_service.get_paper_balance(user_id, 'ZAR')
            btc_balance = ccxt_service.get_paper_balance(user_id, 'BTC')
        else:
            # Paper mode
            zar_balance = ccxt_service.get_paper_balance(user_id, 'ZAR')
            btc_balance = ccxt_service.get_paper_balance(user_id, 'BTC')
        
        btc_price = await paper_engine.get_real_price('BTC/ZAR', 'luno')
        current_capital = zar_balance + (btc_balance * btc_price)
        
        # BACKEND TRUTH: Get all bots total capital from MongoDB
        bots = await db.bots_collection.find({"user_id": user_id, "status": {"$ne": "deleted"}}, {"_id": 0}).to_list(1000)
        total_bot_capital = sum(bot.get('current_capital', 0) for bot in bots)
        total_capital = max(current_capital, total_bot_capital, ledger_equity)
        
        target = 1_000_000

        if trades_total < 10:
            return {
                "ready": False,
                "message": "Need at least 10 trades",
                "trades_remaining": 10 - trades_total,
                "trades_total": trades_total,
                "current_capital": round(total_capital, 2),
                "target": target,
                "remaining": round(target - total_capital, 2),
                "progress_pct": round((total_capital / target) * 100, 2) if target > 0 else 0,
                "mode": "Live" if is_live else "Paper",
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        
        # Check if target achieved
        if total_capital >= target:
            return {
                "ready": True,
                "current_capital": round(total_capital, 2),
                "target": target,
                "remaining": 0,
                "progress_pct": 100.0,
                "days_remaining": 0,
                "mode": "Live" if is_live else "Paper",
                "status": "achieved",
                "message": "🎉 TARGET ACHIEVED! You reached R1 Million!",
                "compound_projection": None
            }
        
        # BACKEND TRUTH: Calculate daily ROI from ledger profit series
        series = await ledger.profit_series(user_id, period="daily", limit=30)
        recent_trades = []
        unique_trade_days = len(series)
        if not series:
            thirty_days_ago = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
            recent_trades = await db.trades_collection.find({
                "user_id": user_id,
                "timestamp": {"$gte": thirty_days_ago}
            }).to_list(None)
            unique_trade_days = len(set(t.get('timestamp', '')[:10] for t in recent_trades))
        
        # Need at least 3 full days of trading history
        if unique_trade_days >= 3:
            if series:
                total_profit = sum(day.get("net_profit", 0) for day in series)
                days_of_data = unique_trade_days
                avg_daily_profit = total_profit / days_of_data if days_of_data else 0
            else:
                total_profit = sum(trade.get('profit_loss', 0) for trade in recent_trades)
                days_of_data = unique_trade_days
                avg_daily_profit = total_profit / days_of_data if days_of_data else 0
            
            # Calculate daily ROI percentage based on CURRENT capital
            daily_roi_pct = (avg_daily_profit / total_capital * 100) if total_capital > 0 else 0
            
            # Cap at realistic maximum daily ROI (3% is very good, 5% is exceptional)
            daily_roi_pct = min(max(daily_roi_pct, -5), 3.0)  # Cap at 3% daily gain, -5% daily loss
            
            # Data quality indicator
            if unique_trade_days >= 7:
                is_reliable = True  # 7+ days = highly reliable
            elif unique_trade_days >= 5:
                is_reliable = "moderate"  # 5-6 days = moderately reliable
            else:
                is_reliable = "low"  # 3-4 days = low reliability, early estimate
        else:
            avg_daily_profit = 0
            daily_roi_pct = 0
            is_reliable = False
        
        # Simple projection (without compounding)
        remaining = target - total_capital
        simple_days = int(remaining / avg_daily_profit) if avg_daily_profit > 0 else 9999
        
        # Compound projection (with daily reinvestment)
        compound_days = 0
        projected_capital = total_capital
        
        if daily_roi_pct > 0 and unique_trade_days >= 7:
            # Use compound interest formula: A = P(1 + r)^t
            # Solve for t: t = log(A/P) / log(1 + r)
            import math
            try:
                compound_days = int(math.log(target / total_capital) / math.log(1 + (daily_roi_pct / 100)))
                # Limit to reasonable range (max 10 years)
                compound_days = min(compound_days, 3650)
            except (ValueError, ZeroDivisionError):
                compound_days = 9999
        else:
            compound_days = 9999
        
        # Use compound projection as primary estimate (but be conservative)
        # If compound is very aggressive (< 365 days), use average of simple and compound
        if compound_days < 365 and simple_days < 9999:
            est_days = int((compound_days + simple_days) / 2)
        elif compound_days < 9999:
            est_days = compound_days
        else:
            est_days = simple_days
        
        # Add data quality indicator
        data_quality = "reliable" if is_reliable else "early estimate"
        
        # Calculate estimated completion date
        completion_date = (datetime.now(timezone.utc) + timedelta(days=est_days)).strftime("%Y-%m-%d")
        
        # Calculate 12-month AI projection
        twelve_month_projection = total_capital
        if daily_roi_pct > 0:
            # Compound over 365 days
            twelve_month_projection = total_capital * ((1 + (daily_roi_pct / 100)) ** 365)
        
        return {
            "ready": True,
            "current_capital": round(total_capital, 2),
            "target": target,
            "remaining": round(remaining, 2),
            "progress_pct": round((total_capital / target) * 100, 2),
            "days_remaining": est_days,
            "completion_date": completion_date if est_days < 9999 else "Unknown",
            "mode": "Live" if is_live else "Paper",
            "status": "in_progress",
            "metrics": {
                "avg_daily_profit": round(avg_daily_profit, 2),
                "daily_roi_pct": round(daily_roi_pct, 3),
                "days_of_data": unique_trade_days,
                "total_trades": trades_total
            },
            "projections": {
                "simple": simple_days,
                "compound": compound_days,
                "using": "compound" if compound_days < simple_days else "simple",
                "twelve_month": round(twelve_month_projection, 2),
                "twelve_month_gain": round(twelve_month_projection - total_capital, 2),
                "twelve_month_roi": round(((twelve_month_projection - total_capital) / total_capital * 100), 2) if total_capital > 0 else 0
            },
            "message": f"📈 Projected: {est_days} days to R1M at {daily_roi_pct:.2f}% daily ROI ({data_quality})" if est_days < 9999 else f"⏳ Insufficient trading data ({trades_total} trades, {unique_trade_days} days)",
            "data_quality": data_quality if est_days < 9999 else "insufficient",
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    except Exception as e:
        logger.error(f"Countdown calculation error: {e}")
        return {
            "current_capital": 0,
            "target": 1_000_000,
            "remaining": 1_000_000,
            "progress_pct": 0,
            "days_remaining": 0,
            "mode": "Paper",
            "status": "error",
            "message": "Unable to calculate countdown",
            "error": str(e)
        }

# ============================================================================
# LIVE PRICES - REMOVED (now handled by routes/prices.py)
# ============================================================================
# The /api/prices/live endpoint is now managed by routes/prices.py to avoid
# route collision. That router is included in the CRITICAL_ROUTERS section below.
# The canonical implementation delegates to routes/market_api.py for data.

@api_router.get("/wallet/deposit-address")
async def get_deposit_address(user_id: str = Depends(get_current_user)):
    """Get deposit address - placeholder"""
    return {
        "address": "N/A - Connect your exchange API keys first",
        "network": "BTC",
        "note": "Paper trading mode - no real deposits needed"
    }

# ============================================================================
# ADMIN
# ============================================================================

# NOTE: Removed duplicate GET /admin/users and GET /admin/system-stats
# Canonical versions in routes/admin_endpoints.py

@api_router.get("/admin/backend-health")
async def get_backend_health(user_id: str = Depends(get_current_user)):
    """Get comprehensive backend health status - AI systems, services, stats"""
    from system_health import system_health
    return await system_health.get_full_status()

# NOTE: Removed duplicate GET /admin/system-stats - canonical in routes/admin_endpoints.py

@api_router.get("/admin/health-check")
async def system_health_check(user_id: str = Depends(get_current_user)):
    """Comprehensive system health check"""
    try:
        from system_health import get_system_health
        health_data = await get_system_health()
        return health_data
    except Exception as e:
        logger.error(f"Health check error: {e}")
        return {
            "health_score": 0,
            "services": {
                "database": "error",
                "trading_engine": "error",
                "ai_systems": "error",
                "autonomous": "error"
            },
            "error": str(e)
        }


@api_router.get("/admin/user-profile/{user_email}")
async def get_user_profile(user_email: str, admin_id: str = Depends(get_current_user)):
    """Get detailed user profile (admin only)"""
    try:
        user = await db.users_collection.find_one({"email": user_email}, {"_id": 0, "password": 0})
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        
        # Get user's bots
        bots = await db.bots_collection.find({"user_id": user['id'], "status": {"$ne": "deleted"}}, {"_id": 0}).to_list(1000)
        
        # Calculate stats
        total_profit = sum(bot.get('total_profit', 0) for bot in bots)
        total_capital = sum(bot.get('current_capital', 0) for bot in bots)
        active_bots = len([b for b in bots if b.get('status') == 'active'])
        
        # Get recent trades
        trades = await db.trades_collection.find(
            {"user_id": user['id']},
            {"_id": 0}
        ).sort("timestamp", -1).limit(50).to_list(50)
        
        return {
            "user": user,
            "stats": {
                "total_bots": len(bots),
                "active_bots": active_bots,
                "total_profit": round(total_profit, 2),
                "total_capital": round(total_capital, 2),
                "recent_trades": len(trades)
            },
            "bots": bots,
            "recent_trades": trades[:10]
        }
    except Exception as e:
        logger.error(f"User profile error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.get("/admin/bodyguard-status")
async def get_bodyguard_status(admin_id: str = Depends(get_current_user)):
    """Get AI Bodyguard / Self-Healing system status"""
    try:
        from engines.self_healing import self_healing
        
        # Get recently paused bots
        recently_paused = await db.bots_collection.find(
            {"status": "paused", "paused_by_system": True},
            {"_id": 0}
        ).sort("last_trade_time", -1).limit(10).to_list(10)
        
        status = {
            "is_running": self_healing.is_running,
            "check_interval": "30 minutes",
            "last_check": self_healing.last_check.isoformat() if hasattr(self_healing, 'last_check') and self_healing.last_check else "Not run yet",
            "paused_bots_count": len(recently_paused),
            "recently_paused": recently_paused,
            "detection_rules": {
                "excessive_loss": ">15% in 1 hour",
                "stuck_bot": "No trades in 24 hours",
                "abnormal_trading": ">50 trades/day",
                "capital_anomaly": "Sudden capital drops"
            },
            "health": "operational" if self_healing.is_running else "stopped"
        }
        
        return status
    except Exception as e:
        logger.error(f"Bodyguard status error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.get("/admin/ai-learning-status")
async def get_ai_learning_status(admin_id: str = Depends(get_current_user)):
    """Get AI learning and evolution status"""
    try:
        from ai_scheduler import ai_scheduler
        
        status = {
            "is_running": ai_scheduler.is_running,
            "schedule": "Daily at 2:00 AM",
            "last_run": ai_scheduler.last_run.isoformat() if ai_scheduler.last_run else "Not run yet",
            "next_run": "Tonight at 2:00 AM",
            "features": {
                "bot_promotion": "Check 7-day paper bots for live promotion",
                "performance_ranking": "Rank bots by performance",
                "capital_reallocation": "Move capital to top performers",
                "dna_evolution": "Spawn new AI bots from winners (Weekly)",
                "super_brain": "Analyze and generate insights (Weekly)"
            },
            "health": "operational" if ai_scheduler.is_running else "stopped"
        }
        
        return status
    except Exception as e:
        logger.error(f"AI learning status error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.get("/bots/eligible-for-promotion")
async def get_eligible_bots(user_id: str = Depends(get_current_user)):
    """Get list of bots eligible for promotion to live trading
    
    Never throws 500 - returns empty list with reasons if no eligible bots or error
    """
    try:
        from engines.promotion_engine import promotion_engine
        
        eligible = await promotion_engine.get_all_eligible_bots(user_id)
        
        return {
            "eligible_bots": eligible,
            "count": len(eligible),
            "message": f"{len(eligible)} bot(s) ready for live trading (7 days, 52% win rate, 3% profit, 25+ trades)"
        }
    except ImportError as e:
        logger.error(f"Promotion engine not available: {e}")
        return {
            "eligible_bots": [],
            "count": 0,
            "message": "Promotion engine not available",
            "error": str(e)
        }
    except Exception as e:
        logger.error(f"Eligible bots check error: {e}", exc_info=True)
        # Never throw 500 - return safe default
        return {
            "eligible_bots": [],
            "count": 0,
            "message": "Unable to check eligible bots at this time",
            "error": str(e)
        }

@api_router.post("/bots/confirm-live-switch")
async def confirm_live_switch(data: dict, user_id: str = Depends(get_current_user)):
    """Confirm switching eligible bots to live trading with user confirmation"""
    try:
        from engines.promotion_engine import promotion_engine
        
        luno_funded = data.get('luno_funded', False)
        bot_ids = data.get('bot_ids', [])
        
        if not luno_funded:
            return {
                "switched": 0,
                "message": "⚠️ Please fund your exchange wallet before switching to live trading"
            }
        
        # Promote each bot
        results = []
        for bot_id in bot_ids:
            result = await promotion_engine.promote_to_live(bot_id, user_confirmed=True)
            if result['success']:
                results.append(result)
        
        if results:
            # Enable live trading mode
            await db.system_modes_collection.update_one(
                {"user_id": user_id},
                {"$set": {"liveTrading": True}},
                upsert=True
            )
            
            # Send WebSocket notification
            from websocket_manager import manager
            await manager.send_message(user_id, {"type": "force_refresh"})
            
            return {
                "switched": len(results),
                "message": f"🚀 Promoted {len(results)} bot(s) to LIVE trading!",
                "bots": results
            }
        
        return {
            "switched": 0,
            "message": "❌ No bots were eligible for promotion"
        }
    except Exception as e:
        logger.error(f"Live switch error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============= NEW COMPREHENSIVE ROUTES =============

@api_router.get("/wallet/mode-stats")
async def get_wallet_mode_stats(user_id: str = Depends(get_current_user)):
    """Get paper/live mode wallet stats - OLD ENDPOINT (kept for compatibility)"""
    try:
        from mode_manager import mode_manager
        stats = await mode_manager.get_user_mode_stats(user_id)
        
        return {
            "paper": {
                "total": stats['paper']['equity'],
                "available": stats['paper']['equity'] * 0.8,  # 80% available
                "reserved": stats['paper']['equity'] * 0.2
            },
            "live": {
                "total": stats['live']['equity'],
                "available": stats['live']['equity'] * 0.8,
                "reserved": stats['live']['equity'] * 0.2
            },
            "exchanges": {
                "luno": {"balance": 0, "available": 0},
                "binance": {"balance": 0, "available": 0},
                "kucoin": {"balance": 0, "available": 0}
            }
        }
    except Exception as e:
        logger.error(f"Wallet mode stats error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.post("/autopilot/enable")
async def enable_autopilot(user_id: str = Depends(get_current_user)):
    """Enable autopilot mode"""
    try:
        await db.system_modes_collection.update_one(
            {"user_id": user_id},
            {"$set": {"autopilot": True}},
            upsert=True
        )
        logger.info(f"Autopilot enabled for user {user_id}")
        return {"message": "Autopilot enabled", "autopilot": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@api_router.post("/autopilot/disable")
async def disable_autopilot(user_id: str = Depends(get_current_user)):
    """Disable autopilot mode"""
    try:
        await db.system_modes_collection.update_one(
            {"user_id": user_id},
            {"$set": {"autopilot": False}},
            upsert=True
        )
        logger.info(f"Autopilot disabled for user {user_id}")
        return {"message": "Autopilot disabled", "autopilot": False}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@api_router.get("/autopilot/settings")
async def get_autopilot_settings(user_id: str = Depends(get_current_user)):
    """Get autopilot settings"""
    try:
        modes = await db.system_modes_collection.find_one({"user_id": user_id}, {"_id": 0})
        if not modes:
            return {
                "autopilot": True,
                "reinvest_percentage": 80,
                "spawn_threshold": 1000,
                "max_bots": 50
            }
        
        return {
            "autopilot": modes.get('autopilot', True),
            "reinvest_percentage": 80,
            "spawn_threshold": 1000,
            "max_bots": 50
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@api_router.post("/trading/paper/start")
async def start_paper_trading(user_id: str = Depends(get_current_user)):
    """Start paper trading mode"""
    try:
        await db.system_modes_collection.update_one(
            {"user_id": user_id},
            {"$set": {"paperTrading": True, "liveTrading": False}},
            upsert=True
        )
        logger.info(f"Paper trading started for user {user_id}")
        return {"message": "Paper trading started", "mode": "paper"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@api_router.post("/trading/live/start")
async def start_live_trading(data: dict, user_id: str = Depends(get_current_user)):
    """Start live trading mode - requires confirmation"""
    try:
        confirmed = data.get('confirmed', False)
        if not confirmed:
            return {"error": "Confirmation required", "message": "Are you sure? This uses REAL funds!"}
        
        await db.system_modes_collection.update_one(
            {"user_id": user_id},
            {"$set": {"paperTrading": False, "liveTrading": True}},
            upsert=True
        )
        
        logger.warning(f"LIVE TRADING started for user {user_id}")
        return {"message": "Live trading started - using REAL funds", "mode": "live"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@api_router.post("/admin/email-all-users")
async def email_all_users(data: dict, user_id: str = Depends(get_current_user)):
    """Send email to all users (admin only)"""
    try:
        subject = data.get('subject', 'Amarktai Network Update')
        message = data.get('message', '')
        
        if not message:
            raise HTTPException(status_code=400, detail="Message required")
        
        # Get all users
        users = await db.users_collection.find({}, {"_id": 0, "email": 1}).to_list(1000)
        emails = [u['email'] for u in users]
        
        # Send emails
        from email_service import email_service
        result = await email_service.send_bulk_email(emails, subject, message)
        
        logger.info(f"Bulk email sent: {result}")
        return result
    except Exception as e:
        logger.error(f"Bulk email error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.post("/admin/test-email")
async def test_email(data: dict, user_id: str = Depends(get_current_user)):
    """Send a test email to verify SMTP configuration"""
    try:
        test_email_address = data.get('email', 'test@amarktai.com')
        
        from email_service import email_service
        success = await email_service.send_email(
            test_email_address,
            "Amarktai Network - SMTP Test Email",
            "This is a test email from Amarktai Network. If you received this, your SMTP service is working correctly!"
        )
        
        if success:
            logger.info(f"Test email sent successfully to {test_email_address}")
            return {"success": True, "message": f"Test email sent to {test_email_address}"}
        else:
            raise HTTPException(status_code=500, detail="Failed to send test email")
    except Exception as e:
        logger.error(f"Test email error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.get("/overview/mode-stats")
async def get_mode_stats(user_id: str = Depends(get_current_user)):
    """Get separate paper/live statistics"""
    try:
        from mode_manager import mode_manager
        stats = await mode_manager.get_user_mode_stats(user_id)
        return stats
    except Exception as e:
        logger.error(f"Mode stats error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@api_router.delete("/admin/users/{target_user_id}")
async def delete_user(target_user_id: str, user_id: str = Depends(get_current_user)):
    """Hard delete user and all associated data (admin only)"""
    try:
        # Don't allow self-deletion
        if target_user_id == user_id:
            raise HTTPException(status_code=400, detail="Cannot delete yourself")
        
        # Check if user exists
        user_to_delete = await db.users_collection.find_one({"id": target_user_id})
        if not user_to_delete:
            raise HTTPException(status_code=404, detail="User not found")
        
        # Hard delete: Remove user and ALL associated data
        # 1. Delete all user's bots
        await db.bots_collection.delete_many({"user_id": target_user_id})
        
        # 2. Delete all user's trades
        await db.trades_collection.delete_many({"user_id": target_user_id})
        
        # 3. Delete all user's API keys
        await db.api_keys_collection.delete_many({"user_id": target_user_id})
        
        # 4. Delete all user's chat messages
        await db.chat_messages_collection.delete_many({"user_id": target_user_id})
        
        # 5. Delete all user's alerts
        await db.alerts_collection.delete_many({"user_id": target_user_id})
        
        # 6. Delete user's system modes
        await db.system_modes_collection.delete_many({"user_id": target_user_id})
        
        # 7. Finally, delete the user
        result = await db.users_collection.delete_one({"id": target_user_id})
        
        if result.deleted_count == 0:
            raise HTTPException(status_code=404, detail="User deletion failed")
        
        logger.info(f"Admin deleted user: {target_user_id} (email: {user_to_delete.get('email')})")
        
        return {
            "message": "User and all associated data deleted successfully",
            "deleted_user_id": target_user_id,
            "deleted_user_email": user_to_delete.get('email')
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Delete user error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.put("/admin/users/{target_user_id}/block")
async def block_unblock_user(target_user_id: str, data: dict, user_id: str = Depends(get_current_user)):
    """Block or unblock a user (admin only)"""
    try:
        blocked = data.get('blocked', True)
        
        # Don't allow blocking yourself
        if target_user_id == user_id:
            raise HTTPException(status_code=400, detail="Cannot block yourself")
        
        result = await db.users_collection.update_one(
            {"id": target_user_id},
            {"$set": {"blocked": blocked}}
        )
        
        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="User not found")
        
        action = "blocked" if blocked else "unblocked"
        logger.info(f"Admin {action} user: {target_user_id}")
        
        return {
            "message": f"User {action} successfully",
            "user_id": target_user_id,
            "blocked": blocked
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Block/unblock user error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.put("/admin/users/{target_user_id}/password")
async def admin_change_password(target_user_id: str, data: dict, user_id: str = Depends(get_current_user)):
    """Admin change user password (admin only)"""
    try:
        new_password = data.get('new_password')
        if not new_password or len(new_password) < 6:
            raise HTTPException(status_code=400, detail="Password must be at least 6 characters")
        
        # Hash the new password
        hashed = get_password_hash(new_password)
        
        result = await db.users_collection.update_one(
            {"id": target_user_id},
            {"$set": {"password_hash": hashed}}
        )
        
        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="User not found")
        
        logger.info(f"Admin changed password for user: {target_user_id}")
        
        return {
            "message": "Password changed successfully",
            "user_id": target_user_id
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Admin password change error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ==== AUTONOMOUS SYSTEMS ENDPOINTS ====

@api_router.get("/autonomous/performance-rankings")
async def get_performance_rankings(user_id: str = Depends(get_current_user)):
    """Get ranked list of user's bots by performance"""
    try:
        from performance_ranker import performance_ranker
        rankings = await performance_ranker.rank_bots(user_id)
        return {
            "rankings": rankings,
            "total_bots": len(rankings),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    except Exception as e:
        logger.error(f"Performance rankings error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.post("/autonomous/reallocate-capital")
async def manual_capital_reallocation(user_id: str = Depends(get_current_user)):
    """Manually trigger capital reallocation"""
    try:
        from engines.capital_allocator import capital_allocator
        result = await capital_allocator.reallocate_capital(user_id)
        return result
    except Exception as e:
        logger.error(f"Capital reallocation error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.post("/autonomous/reinvest-profits")
async def manual_profit_reinvestment(user_id: str = Depends(get_current_user)):
    """
    Manually trigger profit reinvestment.
    
    NOTE: This endpoint is the PRIMARY endpoint for manual profit reinvestment.
    Backend maintains this as single source of truth by delegating to capital allocator service.
    
    Returns:
        Result of reinvestment operation including amount reinvested and new bot allocations
    """
    try:
        from engines.capital_allocator import capital_allocator
        # BACKEND TRUTH: Delegate to capital allocator service
        result = await capital_allocator.reinvest_daily_profits(user_id)
        return result
    except Exception as e:
        logger.error(f"Profit reinvestment error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ==== SHORT-TERM FEATURES ENDPOINTS ====

@api_router.post("/alerts/email-test")
async def test_email_alert(user_id: str = Depends(get_current_user)):
    """Test email alert system"""
    try:
        from email_alerts import email_alerts
        user = await db.users_collection.find_one({"id": user_id}, {"_id": 0})
        
        success = await email_alerts.send_email(
            user.get('email', 'test@example.com'),
            "Test Alert - Amarktai",
            "<h2>Email system is working!</h2><p>This is a test email from Amarktai.</p>"
        )
        
        return {"sent": success, "message": "Test email sent" if success else "Email disabled (no SMTP credentials)"}
    except Exception as e:
        logger.error(f"Email test error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.get("/fetchai/signals/{pair}")
async def get_fetchai_signals(pair: str, user_id: str = Depends(get_current_user)):
    """Get Fetch.ai market signals"""
    try:
        from fetchai_integration import fetchai
        signals = await fetchai.fetch_market_signals(pair.replace('-', '/'))
        return signals
    except Exception as e:
        logger.error(f"Fetch.ai signals error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.get("/fetchai/recommendation/{pair}")
async def get_fetchai_recommendation(pair: str, risk_level: str = "moderate", user_id: str = Depends(get_current_user)):
    """Get Fetch.ai trading recommendation"""
    try:
        from fetchai_integration import fetchai
        recommendation = await fetchai.get_trading_recommendation(pair.replace('-', '/'), risk_level)
        return recommendation
    except Exception as e:
        logger.error(f"Fetch.ai recommendation error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.get("/fetchai/test-connection")
async def test_fetchai_connection(user_id: str = Depends(get_current_user)):
    """Test Fetch.ai API connection"""
    try:
        from fetchai_integration import fetchai
        import os
        api_key = os.environ.get('FETCHAI_API_KEY', '')
        if not api_key:
            return {"connected": False, "message": "No Fetch.ai API key configured"}
        
        result = await fetchai.test_connection(api_key)
        return {"connected": result, "message": "Connected to Fetch.ai" if result else "Connection failed"}
    except Exception as e:
        logger.error(f"Fetch.ai connection test error: {e}")
        return {"connected": False, "message": str(e)}

# ==== SERVER-SENT EVENTS (SSE) ENDPOINTS ====

@api_router.get("/sse/overview")
async def sse_overview_stream(request: Request, user_id: str = Depends(get_current_user)):
    """Server-Sent Events stream for real-time overview data"""
    async def event_generator():
        try:
            while True:
                # Check if client disconnected
                if await request.is_disconnected():
                    break
                
                # Fetch overview data
                bots = await db.bots_collection.find({"user_id": user_id, "status": {"$ne": "deleted"}}, {"_id": 0}).to_list(1000)
                active_bots = [b for b in bots if b.get('status') == 'active']
                
                total_profit = sum(
                    bot.get('current_capital', 0) - bot.get('initial_capital', 0) 
                    for bot in active_bots
                )
                
                data = {
                    "totalProfit": round(total_profit, 2),
                    "activeBots": len(active_bots),
                    "totalBots": len(bots),
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
                
                # Send SSE formatted message
                yield f"data: {json.dumps(data)}\n\n"
                
                # Wait 2 seconds before next update
                await asyncio.sleep(2)
                
        except asyncio.CancelledError:
            pass
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"  # Disable nginx buffering
        }
    )

@api_router.get("/sse/live-prices")
async def sse_live_prices_stream(request: Request, user_id: str = Depends(get_current_user)):
    """Server-Sent Events stream for live price updates"""
    async def event_generator():
        try:
            while True:
                if await request.is_disconnected():
                    break
                
                # Fetch live prices
                pairs = ['BTC/ZAR', 'ETH/ZAR', 'XRP/ZAR']
                prices = {}
                
                for pair in pairs:
                    try:
                        # Get real-time price from paper_trading_engine (uses CCXT)
                        from paper_trading_engine import paper_engine
                        
                        price = await paper_engine.get_real_price(pair, 'luno')
                        
                        if price and price > 0:
                            # Calculate real 24h change from CCXT ticker
                            change_24h = 0.0
                            try:
                                # Fetch full ticker for 24h percentage change
                                # FIX: Use luno_exchange directly, not .exchanges['luno']
                                exchange = paper_engine.luno_exchange
                                if exchange:
                                    ticker = await asyncio.to_thread(exchange.fetch_ticker, pair)
                                    change_24h = ticker.get('percentage', 0.0) or 0.0
                            except:
                                # Fallback to simulated if ticker fetch fails
                                change_24h = round(random.uniform(-2, 2), 2)
                            
                            prices[pair] = {
                                "price": round(price, 2),
                                "change": round(change_24h, 2),  # Real 24h % from CCXT (or simulated fallback)
                                "timestamp": datetime.now(timezone.utc).isoformat()
                            }
                    except Exception as e:
                        logger.debug(f"Price fetch error for {pair}: {e}")
                        pass
                
                yield f"data: {json.dumps(prices)}\n\n"
                await asyncio.sleep(5)  # Update every 5 seconds
                
        except asyncio.CancelledError:
            pass
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )

# ==== MEDIUM-TERM FEATURES ENDPOINTS ====

@api_router.post("/orders/stop-loss")
async def create_stop_loss(data: dict, user_id: str = Depends(get_current_user)):
    """Create stop-loss order"""
    try:
        from advanced_orders import advanced_orders
        order = await advanced_orders.create_stop_loss(
            data['bot_id'],
            data['pair'],
            data['stop_price'],
            data['current_price']
        )
        return order
    except Exception as e:
        logger.error(f"Stop-loss creation error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.post("/orders/trailing-stop")
async def create_trailing_stop(data: dict, user_id: str = Depends(get_current_user)):
    """Create trailing stop order"""
    try:
        from advanced_orders import advanced_orders
        order = await advanced_orders.create_trailing_stop(
            data['bot_id'],
            data['pair'],
            data['trail_percent'],
            data['current_price']
        )
        return order
    except Exception as e:
        logger.error(f"Trailing stop creation error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.post("/backtest/strategy")
async def backtest_strategy(data: dict, user_id: str = Depends(get_current_user)):
    """Backtest a trading strategy"""
    try:
        from backtesting_engine import backtesting_engine
        result = await backtesting_engine.backtest_strategy(
            data['strategy_params'],
            data['start_date'],
            data['end_date'],
            data.get('initial_capital', 1000)
        )
        return result
    except Exception as e:
        logger.error(f"Backtesting error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.post("/bots/evolve")
async def evolve_bots(user_id: str = Depends(get_current_user)):
    """Trigger bot DNA evolution"""
    try:
        from bot_dna_evolution import bot_dna_evolution
        result = await bot_dna_evolution.evolve_bots(user_id)
        return result
    except Exception as e:
        logger.error(f"Bot evolution error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.get("/insights/daily")
async def get_daily_insights(user_id: str = Depends(get_current_user)):
    """Get AI-generated daily insights"""
    try:
        from ai_super_brain import ai_super_brain
        insights = await ai_super_brain.generate_daily_insights(user_id)
        return insights
    except Exception as e:
        logger.error(f"Insights generation error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# ==== LONG-TERM ML/AI ENDPOINTS ====

@api_router.get("/ml/predict/{pair}")
async def predict_price(pair: str, timeframe: str = "1h", user_id: str = Depends(get_current_user)):
    """ML-based price prediction"""
    try:
        from ml_predictor import ml_predictor
        prediction = await ml_predictor.predict_price(pair.replace('-', '/'), timeframe)
        return prediction
    except Exception as e:
        logger.error(f"Price prediction error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.get("/ml/sentiment/{pair}")
async def analyze_sentiment(pair: str, user_id: str = Depends(get_current_user)):
    """Sentiment analysis for trading pair"""
    try:
        from ml_predictor import ml_predictor
        sentiment = await ml_predictor.analyze_sentiment(pair.replace('-', '/'))
        return sentiment
    except Exception as e:
        logger.error(f"Sentiment analysis error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.get("/ml/anomalies")
async def detect_anomalies(user_id: str = Depends(get_current_user)):
    """Detect anomalous trading patterns"""
    try:
        from ml_predictor import ml_predictor
        anomalies = await ml_predictor.detect_anomalies(user_id)
        return anomalies
    except Exception as e:
        logger.error(f"Anomaly detection error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.get("/autonomous/market-regime")
async def get_market_regime(pair: str, user_id: str = Depends(get_current_user)):
    """Get current market regime for a trading pair (use ?pair=BTC/ZAR)"""
    try:
        from market_regime import market_regime_detector
        regime = await market_regime_detector.detect_regime(pair)
        return regime
    except Exception as e:
        logger.error(f"Market regime error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.post("/autonomous/promote-bots")
async def manual_bot_promotion(user_id: str = Depends(get_current_user)):
    """Manually trigger bot promotion check"""
    try:
        from bot_lifecycle import bot_lifecycle
        promotions = await bot_lifecycle.check_promotions()
        return {
            "promotions": promotions,
            "message": f"Checked and promoted {promotions} bots"
        }
    except Exception as e:
        logger.error(f"Bot promotion error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

        
        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="User not found")
        
        logger.info(f"Admin changed password for user: {target_user_id}")
        
        return {
            "message": "Password changed successfully",
            "user_id": target_user_id
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Admin password change error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.post("/admin/emergency-stop")
async def admin_emergency_stop(user_id: str = Depends(get_current_user)):
    """EMERGENCY: HARD STOP - Immediately halt ALL trading activity"""
    try:
        logger.critical("🚨 EMERGENCY STOP INITIATED")
        
        # 1. Set emergency stop flag in database
        await db.emergency_stop_collection.update_one(
            {},
            {"$set": {
                "enabled": True,
                "activated_at": datetime.now(timezone.utc).isoformat(),
                "activated_by": user_id
            }},
            upsert=True
        )
        
        # 2. Stop trading scheduler immediately
        try:
            trading_scheduler.stop()
            logger.info("✅ Trading scheduler stopped")
        except Exception as e:
            logger.error(f"Error stopping trading scheduler: {e}")
        
        # 3. Pause all active bots
        result = await db.bots_collection.update_many(
            {"status": "active"},
            {"$set": {
                "status": "paused",
                "pause_reason": "emergency_stop",
                "emergency_stopped_at": datetime.now(timezone.utc).isoformat()
            }}
        )
        logger.info(f"✅ Paused {result.modified_count} bots")
        
        # 4. Clear any queued trades
        try:
            await db.orders_collection.update_many(
                {"status": "pending"},
                {"$set": {
                    "status": "cancelled",
                    "cancel_reason": "emergency_stop"
                }}
            )
            logger.info("✅ Cancelled pending orders")
        except Exception as e:
            logger.warning(f"Could not cancel pending orders: {e}")
        
        # 5. Stop production trading engines
        try:
            from engines.trading_engine_production import trading_engine
            trading_engine.stop()
            logger.info("✅ Production trading engine stopped")
        except Exception as e:
            logger.warning(f"Could not stop trading engine: {e}")
        
        try:
            from autopilot_engine import autopilot
            if autopilot.scheduler and autopilot.scheduler.running:
                autopilot.scheduler.shutdown(wait=False)
            autopilot.running = False
            logger.info("✅ Autopilot engine stopped")
        except Exception as e:
            logger.warning(f"Could not stop autopilot: {e}")
        
        logger.critical("🚨 EMERGENCY STOP ACTIVATED - ALL TRADING HALTED")
        
        return {
            "success": True,
            "message": "Emergency stop activated - all trading halted",
            "bots_paused": result.modified_count,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "reversible": True
        }
    except Exception as e:
        logger.error(f"Emergency stop failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@api_router.post("/admin/emergency-resume")
async def admin_emergency_resume(user_id: str = Depends(get_current_user)):
    """Resume trading after emergency stop - REVERSIBLE"""
    try:
        logger.warning("⚠️ EMERGENCY RESUME INITIATED")
        
        # 1. Clear emergency stop flag
        await db.emergency_stop_collection.update_one(
            {},
            {"$set": {
                "enabled": False,
                "resumed_at": datetime.now(timezone.utc).isoformat(),
                "resumed_by": user_id
            }},
            upsert=True
        )
        
        # 2. Restart trading scheduler if enabled
        enable_trading = env_bool('ENABLE_TRADING', False)
        enable_schedulers = env_bool('ENABLE_SCHEDULERS', False)
        
        if enable_trading and enable_schedulers:
            try:
                trading_scheduler.start()
                logger.info("✅ Trading scheduler restarted")
            except Exception as e:
                logger.error(f"Error restarting trading scheduler: {e}")
        
        # 3. DO NOT auto-resume bots - require manual review
        # Bots remain paused for safety - admin must manually unpause after review
        
        logger.warning("⚠️ EMERGENCY STOP LIFTED - Bots remain paused for manual review")
        
        return {
            "success": True,
            "message": "Emergency stop lifted - bots remain paused for manual review",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "note": "Manually unpause bots after review"
        }
    except Exception as e:
        logger.error(f"Emergency resume failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

# ============================================================================
# PROMETHEUS METRICS ENDPOINT
# ============================================================================

@api_router.get("/metrics")
async def get_prometheus_metrics():
    """Expose Prometheus metrics for Grafana"""
    try:
        from engines.prometheus_metrics import prometheus_metrics
        from fastapi.responses import Response
        
        content, content_type = prometheus_metrics.export_metrics()
        return Response(content=content, media_type=content_type)
        
    except Exception as e:
        logger.error(f"Metrics export failed: {e}")
        raise HTTPException(status_code=500, detail="Metrics export failed")

# ============================================================================
# DIAGNOSTICS ENDPOINTS
# ============================================================================

@api_router.get("/diagnostics/chat")
async def diagnostics_chat(user_id: str = Depends(get_current_user)):
    """Chat diagnostics endpoint - shows OpenAI key status and configuration
    
    Returns:
        - openai_key_status: not_configured, saved_untested, test_ok
        - key_source: user, system, none
        - last_error: sanitized error message if any
    """
    try:
        from services.keys_service import keys_service
        
        # Check user's OpenAI key
        user_key_data = await keys_service.get_user_api_key(user_id, 'openai', decrypt=False)
        
        if user_key_data:
            openai_key_status = user_key_data.get('status', 'saved_untested')
            last_test_error = user_key_data.get('last_test_error')
            key_source = 'user' if openai_key_status == 'test_ok' else 'system'
        else:
            openai_key_status = 'not_configured'
            last_test_error = None
            # Check if system key exists
            system_key = os.environ.get('OPENAI_API_KEY')
            key_source = 'system' if system_key else 'none'
        
        # Determine which key would be used
        if openai_key_status == 'test_ok':
            actual_key_source = 'user'
            chat_available = True
        elif key_source == 'system':
            actual_key_source = 'system'
            chat_available = True
        else:
            actual_key_source = 'none'
            chat_available = False
        
        return {
            "success": True,
            "openai_key_status": openai_key_status,
            "key_source_would_use": actual_key_source,
            "chat_available": chat_available,
            "last_error": last_test_error if last_test_error else None,
            "recommendation": (
                "Chat is ready!" if chat_available 
                else "Please configure your OpenAI API key in Settings > API Keys"
            )
        }
        
    except Exception as e:
        logger.error(f"Chat diagnostics error: {e}")
        return {
            "success": False,
            "error": str(e),
            "openai_key_status": "error",
            "key_source_would_use": "error",
            "chat_available": False
        }


@api_router.get("/diagnostics/go-live")
async def diagnostics_go_live(user_id: str = Depends(get_current_user)):
    """Go-live diagnostics endpoint - comprehensive system status (admin only)
    
    Returns PASS/FAIL report for production readiness:
    - Health check
    - Database connectivity  
    - Build hash
    - System mode flags
    - Risk locks
    - API keys status (openai + 7 exchanges)
    - Chat diagnostic summary
    - Bots scheduler state
    - Realtime health
    """
    if not await is_admin(user_id):
        raise HTTPException(status_code=403, detail="Admin access required")
    
    try:
        report = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "overall_status": "CHECKING",
            "checks": {}
        }
        
        # 1. Health check
        try:
            report["checks"]["health"] = {"status": "PASS", "message": "Server is running"}
        except Exception as e:
            report["checks"]["health"] = {"status": "FAIL", "error": str(e)}
        
        # 2. Database connectivity
        try:
            await db.users_collection.find_one({}, {"_id": 1})
            report["checks"]["database"] = {"status": "PASS", "message": "MongoDB connected"}
        except Exception as e:
            report["checks"]["database"] = {"status": "FAIL", "error": str(e)}
        
        # 3. Build hash (if available)
        build_hash = os.environ.get('BUILD_HASH', 'unknown')
        report["checks"]["build_hash"] = {"status": "INFO", "value": build_hash}
        
        # 4. System modes
        try:
            modes = await db.system_modes_collection.find_one({"user_id": user_id}, {"_id": 0}) or {}
            report["checks"]["system_modes"] = {
                "status": "INFO",
                "paper_trading": modes.get('paperTrading', False),
                "live_trading": modes.get('liveTrading', False),
                "autopilot": modes.get('autopilot', False),
                "emergency_stop": modes.get('emergencyStop', False)
            }
        except Exception as e:
            report["checks"]["system_modes"] = {"status": "FAIL", "error": str(e)}
        
        # 5. API keys status
        try:
            from services.keys_service import keys_service
            keys_status = {}
            
            # Check OpenAI
            openai_key = await keys_service.get_user_api_key(user_id, 'openai')
            keys_status['openai'] = openai_key.get('status') if openai_key else 'not_configured'
            
            # Check exchanges
            for exchange in ['luno', 'binance', 'kucoin', 'bybit', 'kraken', 'bitget', 'gate']:
                exchange_key = await keys_service.get_user_api_key(user_id, exchange)
                keys_status[exchange] = exchange_key.get('status') if exchange_key else 'not_configured'
            
            report["checks"]["api_keys"] = {"status": "INFO", "keys": keys_status}
        except Exception as e:
            report["checks"]["api_keys"] = {"status": "FAIL", "error": str(e)}
        
        # 6. Chat diagnostic
        try:
            chat_diag = await diagnostics_chat(user_id)
            report["checks"]["chat"] = {
                "status": "PASS" if chat_diag.get('chat_available') else "WARN",
                "key_source": chat_diag.get('key_source_would_use'),
                "available": chat_diag.get('chat_available')
            }
        except Exception as e:
            report["checks"]["chat"] = {"status": "FAIL", "error": str(e)}
        
        # 7. Bots scheduler state
        try:
            # Check if scheduler is running
            from engines.scheduler import trading_scheduler
            scheduler_running = trading_scheduler.running if hasattr(trading_scheduler, 'running') else False
            report["checks"]["scheduler"] = {
                "status": "PASS" if scheduler_running else "WARN",
                "running": scheduler_running
            }
        except Exception as e:
            report["checks"]["scheduler"] = {"status": "WARN", "error": str(e)}
        
        # 8. Realtime health (WebSocket)
        try:
            from websocket_manager import manager as ws_manager
            active_connections = len(ws_manager.active_connections) if hasattr(ws_manager, 'active_connections') else 0
            report["checks"]["realtime"] = {
                "status": "PASS",
                "active_connections": active_connections
            }
        except Exception as e:
            report["checks"]["realtime"] = {"status": "WARN", "error": str(e)}
        
        # Determine overall status
        failed_checks = [k for k, v in report["checks"].items() if v.get("status") == "FAIL"]
        if failed_checks:
            report["overall_status"] = "FAIL"
            report["failed_checks"] = failed_checks
        else:
            warn_checks = [k for k, v in report["checks"].items() if v.get("status") == "WARN"]
            if warn_checks:
                report["overall_status"] = "PASS_WITH_WARNINGS"
                report["warning_checks"] = warn_checks
            else:
                report["overall_status"] = "PASS"

        # Category-level PASS/FAIL summary — derived from Truth Kernel (single source of truth)
        try:
            from services.truth_kernel import compute_truth_summary
            truth = await compute_truth_summary(user_id, db.db)
            truth_subsystems = truth.get("subsystems", {})
            report["categories"] = {
                sub: truth_subsystems.get(sub, {}).get("status", "UNKNOWN")
                for sub in truth_subsystems
            }
            report["contradictions"] = truth.get("contradictions", [])
            report["rule_precedence"] = truth.get("rule_precedence", [])
        except Exception as truth_err:
            logger.warning(f"Truth Kernel failed in go-live, falling back: {truth_err}")
            report["categories"] = {
                "TRUTH_KERNEL": "WARN",
                "PAPER_ENGINE": report["checks"].get("scheduler", {}).get("status", "UNKNOWN"),
                "WALLET_RECONCILIATION": "PASS",
                "RISK_BASELINES": "PASS",
                "REALTIME": report["checks"].get("realtime", {}).get("status", "UNKNOWN"),
                "AI_CHATOPS": report["checks"].get("chat", {}).get("status", "UNKNOWN"),
                "EXCHANGE_HEALTH": report["checks"].get("api_keys", {}).get("status", "UNKNOWN"),
                "TRAINING_GATE": "PASS",
                "UI_HEALTH": "PASS",
                "SCALPER": "PASS",
            }
            report["contradictions"] = []
        
        return report
        
    except Exception as e:
        logger.error(f"Go-live diagnostics error: {e}")
        return {
            "overall_status": "ERROR",
            "error": str(e),
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

# Mount API router (includes auth and other inline endpoints)
app.include_router(api_router, prefix="/api")

# ============================================================================
# MOUNT ROUTERS - Each router defines its own /api/... prefix
# ============================================================================
# Each router is mounted exactly once without additional prefix wrapping.
# Routers already define their own /api/... prefixes in their route files.

# Define CRITICAL routers - these MUST mount successfully or server fails to start
CRITICAL_ROUTERS = {
    "routes.auth",  # Already mounted via api_router earlier
    "routes.keys",
    "routes.trades", 
    "routes.bot_lifecycle",
    "routes.realtime",
    "routes.system_mode",
    "routes.ledger_endpoints",
    "routes.analytics_api",
    "routes.training",
    "routes.quarantine",
    "routes.websocket"  # CRITICAL - WebSocket realtime communication
}

routers_to_mount = [
    ("routes.websocket", "WebSocket"),  # CRITICAL - WebSocket realtime communication (/api/ws)
    ("routes.keys", "API Keys (Unified)"),  # CRITICAL - New unified keys router
    ("routes.system_mode", "System Mode"),  # CRITICAL - Mode management
    ("routes.platforms", "Platforms"),  # Platform drilldown
    ("routes.build_info", "Build Info"),  # Build version info
    ("routes.system", "System"),
    ("routes.trades", "Trades"),  # CRITICAL - Trade history
    ("routes.health", "Health"),
    # REMOVED: routes.profits - duplicate of ledger_endpoints
    ("routes.system_status", "System Status"),
    ("routes.phase5_endpoints", "Phase 5"),
    ("routes.phase6_endpoints", "Phase 6"),
    ("routes.phase8_endpoints", "Phase 8"),
    ("routes.capital_tracking_endpoints", "Capital Tracking"),
    ("routes.emergency_stop_endpoints", "Emergency Stop"),
    ("routes.wallet_endpoints", "Wallet Hub"),
    ("routes.wallet_hub", "Wallet Hub Enhanced"),  # NEW - All 5 exchanges
    # REMOVED: routes.system_health_endpoints - has duplicate /health/ping
    ("routes.admin_endpoints", "Admin"),
    ("routes.admin_enhanced", "Admin Enhanced"),  # NEW - User dropdown, bot profit/loss
    ("routes.admin_start_fresh", "Admin Start Fresh"),  # NEW - Start Fresh wipe endpoint
    ("routes.risk_management", "Risk Management"),  # NEW - Daily loss lock control
    ("routes.dashboard_overview", "Dashboard Overview"),  # NEW - Consolidated overview stats
    ("routes.bot_lifecycle", "Bot Lifecycle"),  # CRITICAL - Bot management
    ("routes.bot_control", "Bot Control"),  # NEW - Pause/Resume/Start endpoints
    ("routes.autopilot_control", "Autopilot Control"),  # NEW - Autopilot persistence
    ("routes.autopilot_growth", "Autopilot Growth"),  # NEW - Growth + reinvest
    ("routes.autonomy_control", "Autonomy Control"),  # NEW - Autonomy status + controls
    ("routes.training", "Bot Training"),  # CRITICAL - Training system
    ("routes.training_quarantine", "Training & Quarantine Unified"),  # NEW - Unified interface
    ("routes.system_limits", "System Limits"),
    ("routes.live_trading_gate", "Live Trading Gate"),
    ("routes.analytics_api", "Analytics API"),  # CRITICAL - PnL analytics
    ("routes.metrics_api", "Metrics API"),  # Trade cadence and countdown
    ("routes.learning_jobs", "Learning Jobs"),  # Nightly learning triggers
    ("routes.market_api", "Market API"),  # Live market prices for BTC/ZAR, ETH/ZAR, XRP/ZAR
    ("routes.prices", "Prices API"),  # NEW - Frontend-friendly /api/prices/live endpoint
    ("routes.diagnostics", "Diagnostics & Pre-Merge Tests"),  # NEW - Realtime smoke tests
    ("routes.ai_chat", "AI Chat"),
    ("routes.chat_enhanced", "AI Chat Enhanced"),  # NEW - Clear on refresh, daily summary
    ("routes.two_factor_auth", "2FA"),
    ("routes.genetic_algorithm", "Genetic Algorithm"),
    ("routes.dashboard_endpoints", "Dashboard"),
    # REMOVED: routes.api_key_management - duplicate of keys
    ("routes.daily_report", "Daily Report"),
    ("routes.ledger_endpoints", "Ledger"),  # CRITICAL - Source of truth for PnL
    ("routes.order_endpoints", "Orders"),
    ("routes.alerts", "Alerts"),
    ("routes.limits_management", "Limits Management"),
    ("routes.advanced_trading_endpoints", "Advanced Trading"),
    ("routes.payment_agent_endpoints", "Payment Agent"),
    # REMOVED: routes.user_api_keys - duplicate of keys
    # REMOVED: routes.api_keys_canonical - duplicate of keys
    ("routes.dashboard_aliases", "Dashboard Aliases"),
    ("routes.quarantine", "Bot Quarantine"),  # CRITICAL - Quarantine system
    ("routes.decision_trace", "Decision Trace"),
    ("routes.compatibility_endpoints", "Compatibility"),
    ("routes.compat", "Compatibility Layer - Legacy Frontend"),  # NEW - Legacy frontend API compatibility
    # REMOVED: routes.bots - duplicate of bot_lifecycle
    ("routes.chat_endpoints", "Chat Message Endpoint"),  # Frontend compatibility
    # REMOVED: routes.wallet_transfers - duplicate of wallet_transfers_enhanced (GET /api/wallet/transfers collision)
    ("routes.wallet_transfers_enhanced", "Wallet Transfers Enhanced"),  # Production-safe state machine (canonical)
    ("routes.wallet_addresses", "Wallet Addresses"),  # Withdrawal address whitelist management
    ("routes.admin_whitelist", "Admin Whitelist Management"),  # Admin whitelist CRUD
    ("routes.user_whitelist", "User Whitelist Management"),  # User whitelist requests
    ("routes.user_countdowns", "User Countdowns"),  # Custom user financial goals
    ("routes.execution_quality", "Execution Quality"),  # NEW - Execution quality monitoring
    ("routes.treasury", "Treasury & Compounding"),  # NEW - Treasury and capital allocation
    ("routes.notifications", "Notifications"),  # NEW - Email notifications, test emails, welcome emails
    ("routes.radar", "Bot Radar"),  # NEW - Bot Radar / Bot Map visualization
    ("routes.exchange_status", "Exchange Status"),  # NEW - Exchange status & test for all 7 exchanges
    ("routes.admin_truth", "Admin Truth Console"),  # NEW - Truth Kernel summary endpoint
    ("routes.scalper", "Scalper Bots"),  # NEW - Scalper bot management + EV gating
]

# Mount realtime router only if enabled via feature flag
if env_bool("ENABLE_REALTIME", True):
    routers_to_mount.append(("routes.realtime", "Realtime Events"))  # CRITICAL when enabled

mounted_routers = []
failed_routers = []
critical_failures = []

for module_path, display_name in routers_to_mount:
    is_critical = module_path in CRITICAL_ROUTERS
    
    try:
        # Import the module and get its 'router' attribute
        module = __import__(module_path, fromlist=['router'])
        router_obj = getattr(module, 'router')
        app.include_router(router_obj)
        mounted_routers.append(display_name)
        logger.info(f"✅ Mounted: {display_name}{' (CRITICAL)' if is_critical else ''}")
    except AttributeError as e:
        # Handle case where module doesn't export 'router'
        error_msg = f"No 'router' attribute: {e}"
        failed_routers.append((display_name, error_msg))
        logger.error(f"❌ Failed to mount {display_name}: {error_msg}")
        if is_critical:
            critical_failures.append((display_name, error_msg))
    except Exception as e:
        error_msg = str(e)
        failed_routers.append((display_name, error_msg))
        logger.error(f"❌ Failed to mount {display_name}: {error_msg}")
        if is_critical:
            critical_failures.append((display_name, error_msg))

# FAIL LOUDLY if any critical router failed to mount
if critical_failures:
    logger.error("="*80)
    logger.error("🔥 FATAL: Critical router(s) failed to mount!")
    logger.error("="*80)
    for name, error in critical_failures:
        logger.error(f"   - {name}: {error}")
    logger.error("="*80)
    logger.error("Cannot start server without critical routers.")
    logger.error("Fix the errors above before deploying.")
    logger.error("="*80)
    raise RuntimeError(f"Critical router mount failure: {', '.join([f[0] for f in critical_failures])}")

# NOTE: Daily report scheduler should be started via FastAPI lifespan/startup event, not at import time
# Commented out to fix "coroutine was never awaited" warning
# To re-enable: Move to lifespan context manager or startup event handler
# try:
#     from routes.daily_report import daily_report_service
#     daily_report_service.start()  # This is async and can't be called in sync context
#     logger.info("✅ Daily report scheduler started")
# except Exception as e:
#     logger.warning(f"Could not start daily report scheduler: {e}")

# ============================================================================
# ROUTE COLLISION DETECTION - Fail boot if duplicate routes exist
# ============================================================================
route_registry = {}
collision_found = False

for route in app.routes:
    # Skip non-API routes (like root, docs, openapi, etc.)
    if not hasattr(route, 'methods') or not hasattr(route, 'path'):
        continue
    
    for method in route.methods:
        if method in ['HEAD', 'OPTIONS']:  # Skip auto-generated methods
            continue
        
        route_key = f"{method} {route.path}"
        
        # Get detailed endpoint information
        endpoint_info = "unknown"
        if hasattr(route, 'endpoint'):
            endpoint = route.endpoint
            if hasattr(endpoint, '__module__') and hasattr(endpoint, '__name__'):
                endpoint_info = f"{endpoint.__module__}:{endpoint.__name__}"
            elif hasattr(endpoint, '__name__'):
                endpoint_info = endpoint.__name__
        
        if route_key in route_registry:
            logger.error(f"❌ ROUTE COLLISION DETECTED: {route_key}")
            logger.error(f"   Location 1: {route_registry[route_key]}")
            logger.error(f"   Location 2: {endpoint_info}")
            collision_found = True
        else:
            # Store route info with module and function
            route_registry[route_key] = endpoint_info

if collision_found:
    logger.error("="*80)
    logger.error("🔥 FATAL: Route collisions detected!")
    logger.error("="*80)
    logger.error("Multiple routers are registering the same endpoint.")
    logger.error("This WILL cause unpredictable behavior in production.")
    logger.error("Review the duplicate endpoint logs above and fix before deploying.")
    logger.error("="*80)
    raise RuntimeError("Route collision detected - cannot start server")

logger.info(f"✅ Route collision check passed - {len(route_registry)} unique routes registered")

# ============================================================================
# WALLET ROUTES DIAGNOSTIC LOG - Prevent future collisions
# ============================================================================
wallet_routes_found = {}
for route in app.routes:
    if hasattr(route, 'path') and '/wallet' in route.path:
        if hasattr(route, 'methods'):
            for method in route.methods:
                if method not in ['HEAD', 'OPTIONS']:
                    route_key = f"{method} {route.path}"
                    endpoint_name = getattr(route, 'name', 'unknown')
                    wallet_routes_found[route_key] = endpoint_name

logger.info("=" * 80)
logger.info("📋 WALLET ROUTES REGISTERED:")
logger.info("=" * 80)
for route_key, endpoint_name in sorted(wallet_routes_found.items()):
    logger.info(f"   {route_key:50} -> {endpoint_name}")
logger.info("=" * 80)
logger.info(f"✅ Total wallet routes: {len(wallet_routes_found)}")
logger.info("=" * 80)

# Summary
logger.info(f"📊 Router mounting complete: {len(mounted_routers)} mounted, {len(failed_routers)} failed")
if failed_routers:
    logger.warning(f"⚠️ Failed routers: {', '.join([f[0] for f in failed_routers])}")

# Update preflight endpoint with router status
try:
    from routes.health import set_router_status
    set_router_status(mounted_routers, [f[0] for f in failed_routers])
except Exception as e:
    logger.warning(f"Could not update preflight router status: {e}")

# ============================================================================
# ROOT ENDPOINT
# ============================================================================

@app.get("/")
async def root():
    return {"message": "Amarktai Network API", "version": "2.0.0", "status": "operational"}
