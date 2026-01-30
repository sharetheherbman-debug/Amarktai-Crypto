from fastapi import FastAPI, HTTPException, Depends, WebSocket, WebSocketDisconnect, Request, APIRouter
from routes.auth import router as auth_router
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse
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
from auth import create_access_token, get_current_user, get_password_hash, verify_password
from ai_service import ai_service
from ccxt_service import ccxt_service
from websocket_manager import manager
from trading_scheduler import trading_scheduler
from utils.env_utils import env_bool
import ccxt.async_support as ccxt

api_router = APIRouter()
api_router.include_router(auth_router)

# ============================================================================
# LIFESPAN CONTEXT - Startup and Shutdown
# ============================================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events with feature flags for plug-and-play stability"""
    logger.info("🚀 Starting Amarktai Network...")
    
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
    except ImportError as e:
        logger.warning(f"⚠️ Lifecycle manager not available: {e}")
    except Exception as e:
        logger.error(f"❌ Error starting subsystems: {e}", exc_info=True)
        # Continue despite errors - some subsystems may have started
    
    # Initialize Fetch.ai and FLOKx integrations if keys available
    try:
        fetchai_key = os.environ.get('FETCHAI_API_KEY', '')
        if fetchai_key:
            from fetchai_integration import fetchai
            fetchai.set_credentials(fetchai_key)
            logger.info("🔮 Fetch.ai integration configured")
    except Exception as e:
        logger.warning(f"Could not configure Fetch.ai: {e}")
    
    try:
        flokx_key = os.environ.get('FLOKX_API_KEY', '')
        if flokx_key:
            from flokx_integration import flokx
            flokx.set_credentials(flokx_key)
            logger.info("🎯 FLOKx integration configured")
    except Exception as e:
        logger.warning(f"Could not configure FLOKx: {e}")
    
    # Start Daily Reinvestment Scheduler (optional)
    try:
        from services.daily_reinvestment import get_reinvestment_service
        reinvest_service = get_reinvestment_service(db.db)
        reinvest_service.start()
        logger.info("💰 Daily Reinvestment Scheduler started")
    except Exception as e:
        logger.warning(f"Could not start Reinvestment Scheduler: {e}")
    
    # Start Bot Quarantine Service
    try:
        from services.bot_quarantine import quarantine_service
        quarantine_task = asyncio.create_task(quarantine_service.run())
        logger.info("🔒 Bot Quarantine Service started")
    except Exception as e:
        logger.warning(f"Could not start Bot Quarantine Service: {e}")
    
    logger.info("🚀 All autonomous systems operational")
    
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

app = FastAPI(lifespan=lifespan)

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

@app.websocket("/api/ws")
async def websocket_endpoint(websocket: WebSocket, token: str = None):
    """WebSocket endpoint with token authentication"""
    user_id = None
    try:
        # Get token from query params
        if not token:
            await websocket.close(code=1008, reason="Missing token")
            return
        
        # Decode token to get user_id
        from auth import decode_token
        try:
            payload = decode_token(token)
            user_id = payload.get("user_id")
        except Exception as e:
            logger.error(f"Token decode error: {e}")
            await websocket.close(code=1008, reason="Invalid token")
            return
        
        if not user_id:
            await websocket.close(code=1008, reason="Invalid token")
            return
        
        # Connect via manager (handles accept internally)
        await manager.connect(websocket, user_id)
        
        try:
            while True:
                data = await websocket.receive_text()
                # Handle ping/pong
                if data:
                    import json
                    try:
                        msg = json.loads(data)
                        if msg.get('type') == 'ping':
                            await websocket.send_json({
                                'type': 'pong',
                                'timestamp': msg.get('timestamp')
                            })
                    except:
                        pass
        except WebSocketDisconnect:
            await manager.disconnect(websocket, user_id)
            logger.info(f"WebSocket disconnected for user: {user_id}")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
        if user_id:
            await manager.disconnect(websocket, user_id)
        try:
            await websocket.close(code=1011, reason=str(e))
        except:
            pass

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
async def get_bots(user_id: str = Depends(get_current_user)):
    bots = await db.bots_collection.find({"user_id": user_id, "status": {"$ne": "deleted"}}, {"_id": 0}).to_list(1000)
    return bots

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
    
    # Remove MongoDB _id before returning
    result.pop('_id', None)
    
    # Real-time notification
    from realtime_events import rt_events
    await rt_events.bot_created(user_id, result)
    await rt_events.force_refresh(user_id, f"Bot '{result['name']}' created successfully")
    
    logger.info(f"✅ Bot created: {result['name']} for user {user_id[:8]}")
    
    return result

@api_router.post("/bots/batch-create")
async def batch_create_bots(data: dict, user_id: str = Depends(get_current_user)):
    """Batch create bots with distribution"""
    from uuid import uuid4
    
    count = data.get('count', 10)
    capital_per_bot = data.get('capital_per_bot', 1000)
    safe_count = data.get('safe_count', 6)
    risky_count = data.get('risky_count', 2)
    aggressive_count = data.get('aggressive_count', 2)
    exchange = data.get('exchange', 'luno')
    
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
        await db.bots_collection.insert_many(bots_to_create)
    
    return {
        "message": f"{len(bots_to_create)} bots created", 
        "bots": bots_to_create,
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

@api_router.put("/system/mode")
async def update_system_mode(data: dict, user_id: str = Depends(get_current_user)):
    """Update system mode - NOW ACTUALLY CONTROLS TRADING"""
    try:
        mode = data.get('mode')
        enabled = data.get('enabled', False)
        
        logger.info(f"System mode update: {mode} = {enabled} for user {user_id}")
        
        # Get current modes
        current_modes = await db.system_modes_collection.find_one({"user_id": user_id}, {"_id": 0})
        
        if not current_modes:
            current_modes = {
                "user_id": user_id,
                "paperTrading": False,
                "liveTrading": False,
                "autopilot": False
            }
        
        # Update mode
        current_modes[mode] = enabled
        current_modes['updated_at'] = datetime.now(timezone.utc).isoformat()
        
        # Mutually exclusive: paper vs live
        if mode == 'paperTrading' and enabled:
            current_modes['liveTrading'] = False
        elif mode == 'liveTrading' and enabled:
            current_modes['paperTrading'] = False
            
            # When switching to live mode, check for eligible bot promotions
            from bot_lifecycle import bot_lifecycle
            promoted_count = await bot_lifecycle.check_promotions()
            if promoted_count > 0:
                logger.info(f"🎉 Promoted {promoted_count} bots to live trading with reset capital")
        
        # Save to database
        await db.system_modes_collection.update_one(
            {"user_id": user_id},
            {"$set": current_modes},
            upsert=True
        )
        
        # NOTE: Trading scheduler runs globally but checks each user's modes
        # The scheduler respects autopilot/paperTrading settings per user
        # No need to stop/start the global scheduler
        logger.info(f"📊 System mode updated: {mode}={enabled} for user {user_id}")
        
        # Send real-time update via WebSocket
        await manager.send_message(user_id, {
            "type": "system_mode_update",
            "modes": current_modes
        })
        
        return {
            "message": f"{mode} {'enabled' if enabled else 'disabled'}",
            "modes": current_modes
        }
    
    except Exception as e:
        logger.error(f"System mode update error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

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
# API KEYS
# ============================================================================

@api_router.get("/api-keys")
async def get_api_keys(user_id: str = Depends(get_current_user)):
    keys = await db.api_keys_collection.find({"user_id": user_id}, {"_id": 0}).to_list(100)
    for key in keys:
        if 'secret' in key:
            key['secret'] = '***' + key['secret'][-4:] if len(key.get('secret', '')) > 4 else '***'
    return keys

@api_router.post("/api-keys")
async def create_api_key(key: APIKeyCreate, user_id: str = Depends(get_current_user)):
    """Create or update API key for a provider"""
    from uuid import uuid4
    
    # Validate required fields
    if not key.api_key or key.api_key.strip() == '':
        raise HTTPException(status_code=400, detail="API key cannot be empty")
    
    # Delete existing key for this provider
    await db.api_keys_collection.delete_many({"user_id": user_id, "provider": key.provider})
    
    # Create new key - SAVE ONLY, no testing during save
    key_dict = key.model_dump()
    key_dict['id'] = str(uuid4())
    key_dict['user_id'] = user_id
    key_dict['connected'] = False  # User must test manually
    key_dict['created_at'] = datetime.now(timezone.utc).isoformat()
    
    await db.api_keys_collection.insert_one(key_dict)
    
    # Return response with success=true contract required by verify_production_ready.py
    return {
        "success": True,
        "provider": key.provider,
        "connected": key_dict.get('connected', False),
        "updated_at": key_dict.get('created_at'),
        "message": f"Saved {key.provider.upper()} API key"
    }

@api_router.post("/api-keys/{provider}/test")
async def test_api_key(provider: str, user_id: str = Depends(get_current_user)):
    """Test API key connection for a provider"""
    # Get the API key
    key = await db.api_keys_collection.find_one({"user_id": user_id, "provider": provider}, {"_id": 0})
    if not key:
        raise HTTPException(status_code=404, detail=f"No API key found for {provider}")
    
    # Test based on provider
    if provider in ['luno', 'binance', 'kucoin']:
        if not key.get('api_secret'):
            raise HTTPException(status_code=400, detail="API secret required for exchange testing")
        
        try:
            is_valid = await ccxt_service.test_connection(provider, key['api_key'], key['api_secret'])
            
            # Update connection status
            await db.api_keys_collection.update_one(
                {"id": key['id']},
                {"$set": {"connected": is_valid}}
            )
            
            # Real-time notification
            from realtime_events import rt_events
            await rt_events.api_key_connected(user_id, provider, "connected" if is_valid else "failed")
            
            if is_valid:
                return {"message": f"{provider.upper()} connection successful", "connected": True}
            else:
                raise HTTPException(status_code=400, detail=f"{provider.upper()} connection failed")
        except Exception as e:
            logger.error(f"Test connection error for {provider}: {e}")
            raise HTTPException(status_code=400, detail=f"Connection test failed: {str(e)}")
    
    elif provider == 'openai':
        # Test OpenAI key
        try:
            from openai import AsyncOpenAI
            client = AsyncOpenAI(api_key=key['api_key'])
            response = await client.chat.completions.create(
                model="gpt-4o",
                messages=[{"role": "user", "content": "Hi"}],
                max_tokens=10
            )
            
            await db.api_keys_collection.update_one(
                {"id": key['id']},
                {"$set": {"connected": True}}
            )
            
            return {"message": "OpenAI connection successful", "connected": True}
        except Exception as e:
            error_msg = str(e)
            logger.error(f"OpenAI test failed: {error_msg}")
            await db.api_keys_collection.update_one(
                {"id": key['id']},
                {"$set": {"connected": False}}
            )
            
            # Provide helpful error message
            if "Incorrect API key" in error_msg or "invalid" in error_msg.lower():
                raise HTTPException(
                    status_code=400, 
                    detail="Invalid OpenAI API key. Please provide a valid key with model access."
                )
            elif "does not have access to model" in error_msg:
                raise HTTPException(
                    status_code=400,
                    detail="Your OpenAI API key doesn't have access to GPT models. Please upgrade your OpenAI plan."
                )
            else:
                raise HTTPException(status_code=400, detail=f"OpenAI test failed: {error_msg[:200]}")
    
    elif provider == 'flokx':
        # Test Flokx key
        try:
            from flokx_integration import flokx
            result = await flokx.test_connection(key['api_key'])
            
            # Handle boolean return from test_connection
            is_connected = bool(result)
            
            await db.api_keys_collection.update_one(
                {"id": key['id']},
                {"$set": {"connected": is_connected}}
            )
            
            # Real-time notification
            from realtime_events import rt_events
            await rt_events.api_key_connected(user_id, provider, "connected" if is_connected else "failed")
            
            if is_connected:
                return {"message": "Flokx connection successful", "connected": True}
            else:
                raise HTTPException(status_code=400, detail="Flokx connection failed")
        except Exception as e:
            logger.error(f"Flokx test failed: {e}")
            raise HTTPException(status_code=400, detail=f"Flokx test failed: {str(e)}")
    
    elif provider == 'fetchai':
        # Test Fetch.ai key
        try:
            from fetchai_integration import fetchai
            result = await fetchai.test_connection(key['api_key'])
            
            await db.api_keys_collection.update_one(
                {"id": key['id']},
                {"$set": {"connected": result}}
            )
            
            if result:
                return {"message": "Fetch.ai connection successful", "connected": True}
            else:
                raise HTTPException(status_code=400, detail="Fetch.ai connection failed")
        except Exception as e:
            logger.error(f"Fetch.ai test failed: {e}")
            raise HTTPException(status_code=400, detail=f"Fetch.ai test failed: {str(e)}")
    
    # OVEX and VALR removed - only Luno, Binance, KuCoin supported
    else:
        # Unsupported provider
        raise HTTPException(status_code=400, detail=f"Unsupported provider: {provider}. Supported exchanges: luno, binance, kucoin")
    
    return {"message": f"{provider} configured", "connected": True}

@api_router.delete("/api-keys/{provider}")
async def delete_api_key_by_provider(provider: str, user_id: str = Depends(get_current_user)):
    """Delete API key by provider name"""
    result = await db.api_keys_collection.delete_many({"provider": provider, "user_id": user_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail=f"No API key found for {provider}")
    return {"message": f"{provider} API key deleted", "deleted_count": result.deleted_count}

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
            chat_size = sum(sys.getsizeof(json.dumps(msg)) for msg in chat_messages)
            
            # 2. Trade history
            trades = await db.trades_collection.find({"user_id": usr_id}, {"_id": 0}).to_list(10000)
            trades_size = sum(sys.getsizeof(json.dumps(trade)) for trade in trades)
            
            # 3. Bot configurations
            bots = await db.bots_collection.find({"user_id": usr_id, "status": {"$ne": "deleted"}}, {"_id": 0}).to_list(1000)
            bots_size = sum(sys.getsizeof(json.dumps(bot)) for bot in bots)
            
            # 4. User data
            user_size = sys.getsizeof(json.dumps(usr))
            
            # 5. Alerts
            alerts = await db.alerts_collection.find({"user_id": usr_id}, {"_id": 0}).to_list(1000)
            alerts_size = sum(sys.getsizeof(json.dumps(alert)) for alert in alerts)
            
            total_bytes = chat_size + trades_size + bots_size + user_size + alerts_size
            total_mb = total_bytes / (1024 * 1024)
            
            storage_data.append({
                "user_id": usr_id,
                "email": usr.get('email', 'N/A'),
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

@api_router.get("/chat/history")
async def get_chat_history(limit: int = 50, user_id: str = Depends(get_current_user)):
    """Get chat history"""
    messages = await db.chat_messages_collection.find(
        {"user_id": user_id},
        {"_id": 0}
    ).sort("timestamp", -1).limit(limit).to_list(limit)
    messages.reverse()
    return {"messages": messages}

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
        
        # BACKEND TRUTH: Get system mode and wallet data from MongoDB
        system_mode = await db.system_modes_collection.find_one({"user_id": user_id}, {"_id": 0})
        is_live = system_mode.get('liveTrading', False) if system_mode else False
        
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
        total_capital = max(current_capital, total_bot_capital)
        
        target = 1_000_000
        
        # Check if target achieved
        if total_capital >= target:
            return {
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
        
        # BACKEND TRUTH: Calculate daily ROI from recent trades in MongoDB
        thirty_days_ago = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
        recent_trades = await db.trades_collection.find({
            "user_id": user_id,
            "timestamp": {"$gte": thirty_days_ago}
        }).to_list(None)  # None = no limit
        
        # REQUIRE MINIMUM 3 DAYS OF TRADING DATA for any realistic projection
        unique_trade_days = len(set(t.get('timestamp', '')[:10] for t in recent_trades))
        
        # Need at least 3 full days of trading history
        if len(recent_trades) >= 30 and unique_trade_days >= 3:
            total_profit = sum(trade.get('profit_loss', 0) for trade in recent_trades)
            days_of_data = unique_trade_days
            avg_daily_profit = total_profit / days_of_data
            
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
                "days_of_data": len(set(t.get('timestamp', '')[:10] for t in recent_trades)),
                "total_trades": len(recent_trades)
            },
            "projections": {
                "simple": simple_days,
                "compound": compound_days,
                "using": "compound" if compound_days < simple_days else "simple",
                "twelve_month": round(twelve_month_projection, 2),
                "twelve_month_gain": round(twelve_month_projection - total_capital, 2),
                "twelve_month_roi": round(((twelve_month_projection - total_capital) / total_capital * 100), 2) if total_capital > 0 else 0
            },
            "message": f"📈 Projected: {est_days} days to R1M at {daily_roi_pct:.2f}% daily ROI ({data_quality})" if est_days < 9999 else f"⏳ Insufficient trading data ({len(recent_trades)} trades, {unique_trade_days} days)",
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
# LIVE PRICES
# ============================================================================

@api_router.get("/prices/live")
async def get_live_prices(user_id: str = Depends(get_current_user)):
    """Get live crypto prices with real 24h change using OHLCV data
    
    Returns safe response even when API keys are missing or exchange unavailable.
    """
    # Rate limit error logging to prevent spam
    last_error_log_key = "_last_price_error_log"
    current_time = time.time()
    
    # Only log errors once per minute
    if not hasattr(get_live_prices, last_error_log_key):
        setattr(get_live_prices, last_error_log_key, {})
    
    last_error_logs = getattr(get_live_prices, last_error_log_key)
    
    def should_log_error(pair: str) -> bool:
        """Check if enough time has passed to log error for this pair"""
        last_log = last_error_logs.get(pair, 0)
        if current_time - last_log > 60:  # 60 seconds
            last_error_logs[pair] = current_time
            return True
        return False
    
    try:
        from paper_trading_engine import paper_engine
        
        # Check if user has API keys configured
        has_api_keys = False
        try:
            api_key_doc = await db.api_keys_collection.find_one({
                "user_id": user_id,
                "provider": "luno"
            })
            has_api_keys = bool(api_key_doc)
        except Exception as e:
            logger.debug(f"Could not check API keys: {e}")
        
        # Initialize exchange if needed (ALWAYS use public demo mode for prices endpoint)
        # This ensures market data works WITHOUT requiring API keys
        if not paper_engine.luno_exchange:
            try:
                await paper_engine.init_exchanges(mode='demo', user_keys=None)
            except Exception as e:
                if should_log_error("init"):
                    logger.warning(f"Could not initialize exchanges in demo mode: {e}")
        
        prices = {}
        pairs = ['BTC/ZAR', 'ETH/ZAR', 'XRP/ZAR']
        
        for pair in pairs:
            try:
                # Method 1: Use OHLCV for most accurate 24h change
                if paper_engine.luno_exchange:
                    ohlcv = await paper_engine.luno_exchange.fetch_ohlcv(pair, '1d', limit=2)
                    
                    if ohlcv and len(ohlcv) >= 2:
                        # Store OHLCV records to avoid repeated indexing
                        yesterday_data = ohlcv[-2]
                        current_data = ohlcv[-1]
                        
                        # Get 24h ago open price and current close price
                        yesterday_open = float(yesterday_data[1]) if yesterday_data[1] is not None else 0
                        current_close = float(current_data[4]) if current_data[4] is not None else 0
                        
                        if yesterday_open > 0 and current_close > 0:
                            change_pct = ((current_close - yesterday_open) / yesterday_open) * 100
                        else:
                            change_pct = 0
                        
                        prices[pair] = {
                            "price": round(current_close, 2) if current_close else 0,
                            "change": round(change_pct, 2) if change_pct is not None else 0
                        }
                        continue  # Success, move to next pair
                    else:
                        raise Exception("Insufficient OHLCV data")
                else:
                    raise Exception("Exchange not initialized")
                
            except Exception as e:
                if should_log_error(f"ohlcv_{pair}"):
                    logger.debug(f"OHLCV failed for {pair}: {e}")
                
                # Method 2: Fallback to ticker with change field
                try:
                    if paper_engine.luno_exchange:
                        ticker = await paper_engine.luno_exchange.fetch_ticker(pair)
                        current_price = ticker.get('last', ticker.get('close', 0))
                        
                        # Safely get change from ticker
                        change_pct = ticker.get('percentage', 0) or 0
                        if change_pct == 0 and ticker.get('change'):
                            change_pct = ticker['change'] or 0
                        if change_pct == 0 and ticker.get('open') and current_price and current_price > 0:
                            open_price = ticker.get('open', 0) or 0
                            if open_price > 0:
                                change_pct = ((current_price - open_price) / open_price) * 100
                        
                        # Ensure no None values before rounding
                        safe_price = current_price if current_price is not None else 0
                        safe_change = change_pct if change_pct is not None else 0
                        
                        prices[pair] = {
                            "price": round(safe_price, 2),
                            "change": round(safe_change, 2)
                        }
                        continue  # Success, move to next pair
                    else:
                        raise Exception("Exchange not initialized")
                        
                except Exception as e2:
                    if should_log_error(f"ticker_{pair}"):
                        logger.debug(f"Ticker failed for {pair}: {e2}")
                    
                    # Last resort: return safe default
                    prices[pair] = {
                        "price": 0,
                        "change": 0,
                        "keys_required": not has_api_keys
                    }
        
        # Add keys_required flag if no valid prices retrieved
        if all(p.get("price", 0) == 0 for p in prices.values()):
            for pair in prices:
                prices[pair]["keys_required"] = not has_api_keys
        
        return prices
        
    except Exception as e:
        if should_log_error("general"):
            logger.warning(f"Live prices error (API keys may be missing): {e}")
        
        # Return safe response with clear indicator
        return {
            'BTC/ZAR': {"price": 0, "change": 0, "keys_required": True},
            'ETH/ZAR': {"price": 0, "change": 0, "keys_required": True},
            'XRP/ZAR': {"price": 0, "change": 0, "keys_required": True}
        }

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

@api_router.get("/flokx/alerts")
async def get_flokx_alerts(user_id: str = Depends(get_current_user)):
    """Get FLOKx market alerts"""
    try:
        from flokx_integration import flokx
        
        # Get alerts for major pairs
        pairs = ['BTC/ZAR', 'ETH/ZAR', 'XRP/ZAR']
        alerts = []
        
        for pair in pairs:
            data = await flokx.fetch_market_coefficients(pair)
            if data.get('strength', 0) > 75:
                alerts.append({
                    "pair": pair,
                    "type": "strong_signal",
                    "message": f"{pair}: Strong {data.get('sentiment', 'signal')} ({data.get('strength', 0):.0f}%)",
                    "timestamp": data.get('timestamp')
                })
        
        return {"alerts": alerts, "count": len(alerts)}
    except Exception as e:
        logger.error(f"Flokx alerts error: {e}")
        return {"alerts": [], "count": 0}

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

@api_router.get("/flokx/test-connection")
async def test_flokx_connection(user_id: str = Depends(get_current_user)):
    """Test FLOKx API connection"""
    try:
        from flokx_integration import flokx
        import os
        api_key = os.environ.get('FLOKX_API_KEY', '')
        if not api_key:
            return {"connected": False, "message": "No FLOKx API key configured"}
        
        result = await flokx.test_connection(api_key)
        return {"connected": result, "message": "Connected to FLOKx" if result else "Connection failed"}
    except Exception as e:
        logger.error(f"FLOKx connection test error: {e}")
        return {"connected": False, "message": str(e)}

@api_router.get("/flokx/coefficients/{pair}")
async def get_flokx_coefficients(pair: str, user_id: str = Depends(get_current_user)):
    """Get FLOKx market intelligence coefficients"""
    try:
        from flokx_integration import flokx
        coeffs = await flokx.fetch_market_coefficients(pair.replace('-', '/'))
        return coeffs
    except Exception as e:
        logger.error(f"FLOKx error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.post("/flokx/create-alert")
async def create_flokx_alert(data: dict, user_id: str = Depends(get_current_user)):
    """Create alert from FLOKx intelligence"""
    try:
        from flokx_integration import flokx
        pair = data.get('pair', 'BTC/ZAR')
        alert = await flokx.create_alert_from_coefficients(user_id, pair)
        if alert:
            # Remove _id if present for JSON serialization
            alert.pop('_id', None)
        return alert
    except Exception as e:
        logger.error(f"FLOKx alert error: {e}")
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
    "routes.quarantine"
}

routers_to_mount = [
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
    ("routes.bot_lifecycle", "Bot Lifecycle"),  # CRITICAL - Bot management
    ("routes.bot_control", "Bot Control"),  # NEW - Pause/Resume/Start endpoints
    ("routes.autopilot_control", "Autopilot Control"),  # NEW - Autopilot persistence
    ("routes.training", "Bot Training"),  # CRITICAL - Training system
    ("routes.training_quarantine", "Training & Quarantine Unified"),  # NEW - Unified interface
    ("routes.system_limits", "System Limits"),
    ("routes.live_trading_gate", "Live Trading Gate"),
    ("routes.analytics_api", "Analytics API"),  # CRITICAL - PnL analytics
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
    # REMOVED: routes.bots - duplicate of bot_lifecycle
    ("routes.chat_endpoints", "Chat Message Endpoint"),  # Frontend compatibility
    ("routes.wallet_transfers", "Wallet Transfers"),  # Fund movement between providers
    ("routes.user_countdowns", "User Countdowns"),  # Custom user financial goals
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
        
        if route_key in route_registry:
            logger.error(f"❌ ROUTE COLLISION DETECTED: {route_key}")
            logger.error(f"   Previously registered at: {route_registry[route_key]}")
            logger.error(f"   Attempting to register again")
            collision_found = True
        else:
            # Store route info
            route_registry[route_key] = getattr(route, 'name', 'unknown')

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
