"""
Database module for Amarktai Network - MongoDB/Motor Implementation
Handles all database operations and provides stable collection API
"""

import os
import logging
from motor.motor_asyncio import AsyncIOMotorClient
from typing import Optional

logger = logging.getLogger(__name__)

# ============================================================================
# MongoDB Client and Database (Lazy Initialization)
# ============================================================================
client: Optional[AsyncIOMotorClient] = None
db = None

# ============================================================================
# Collection Globals - Initialized by setup_collections()
# ============================================================================
# Core collections
users_collection = None
bots_collection = None
trades_collection = None
api_keys_collection = None
alerts_collection = None
sessions_collection = None
system_config_collection = None

# System modes and chat
system_modes_collection = None
chat_messages_collection = None

# Lifecycle and monitoring
bot_lifecycle_collection = None
bot_metrics_collection = None
system_metrics_collection = None

# Training and quarantine
training_jobs_collection = None

# Advanced features
risk_profiles_collection = None
market_regimes_collection = None
learning_data_collection = None
learning_logs_collection = None
audit_logs_collection = None
notifications_collection = None
reports_collection = None
promotion_requests_collection = None
decisions_collection = None  # AI trading decisions and reasoning
reinvest_requests_collection = None  # Profit reinvestment requests

# Autopilot and detection
autopilot_actions_collection = None
rogue_detections_collection = None

# Emergency stop collection
emergency_stop_collection = None

# Financial tracking collections
wallet_balances_collection = None
capital_injections_collection = None
wallets_collection = None
ledger_collection = None
profits_collection = None
funding_plans_collection = None
wallet_transfers_collection = None  # Fund transfers between providers

# Orders and positions
orders_collection = None
positions_collection = None
balance_snapshots_collection = None
performance_metrics_collection = None

# User custom goals/countdowns
user_countdowns_collection = None

# Aliases for backward compatibility
wallet_balances = None  # Alias for wallet_balances_collection
capital_injections = None  # Alias for capital_injections_collection
audit_logs = None  # Alias for audit_logs_collection
funding_plans = None  # Alias for funding_plans_collection


# ============================================================================
# Database Connection Functions
# ============================================================================

async def connect():
    """
    Connect to MongoDB and initialize all collections
    This is the main entry point for database initialization
    """
    global client, db
    
    mongo_url = os.getenv('MONGO_URL', 'mongodb://localhost:27017')
    db_name = os.getenv('DB_NAME', 'amarktai_trading')
    
    logger.info(f"🔌 Connecting to MongoDB at {mongo_url}")
    
    try:
        client = AsyncIOMotorClient(mongo_url)
        db = client[db_name]
        
        # Test connection
        await client.admin.command('ping')
        logger.info(f"✅ MongoDB connection successful - database: {db_name}")
        
        # Setup all collections
        await setup_collections()
        
        # Initialize database (create indexes)
        await init_db()
        
        # Run startup baseline field repair for bots
        try:
            from migrations.repair_baseline_fields import repair_on_startup
            await repair_on_startup()
        except Exception as repair_error:
            logger.warning(f"Baseline field repair failed (non-critical): {repair_error}")
        
        logger.info("✅ All collections and indexes initialized")
        
    except Exception as e:
        logger.error(f"❌ MongoDB connection failed: {e}")
        raise


async def connect_db():
    """Alias for connect() - for backward compatibility"""
    await connect()


async def close_db():
    """Close MongoDB connection cleanly"""
    global client
    
    if client:
        logger.info("🔌 Closing MongoDB connection...")
        client.close()
        client = None
        logger.info("✅ MongoDB connection closed")


def get_database():
    """Get the database instance"""
    return db


# ============================================================================
# Collection Setup
# ============================================================================

async def setup_collections():
    """
    Initialize all collection globals
    Must be called after database connection is established
    """
    global users_collection, bots_collection, trades_collection
    global api_keys_collection, alerts_collection, sessions_collection
    global system_config_collection, system_modes_collection, chat_messages_collection
    global bot_lifecycle_collection, bot_metrics_collection, system_metrics_collection
    global training_jobs_collection
    global risk_profiles_collection, market_regimes_collection
    global learning_data_collection, learning_logs_collection, audit_logs_collection
    global notifications_collection, reports_collection, promotion_requests_collection
    global decisions_collection, reinvest_requests_collection
    global autopilot_actions_collection, rogue_detections_collection
    global emergency_stop_collection
    global wallet_balances_collection, capital_injections_collection
    global wallets_collection, ledger_collection, profits_collection, funding_plans_collection
    global wallet_transfers_collection
    global orders_collection, positions_collection, balance_snapshots_collection, performance_metrics_collection
    global user_countdowns_collection
    global wallet_balances, capital_injections, audit_logs, funding_plans
    
    if db is None:
        logger.warning("⚠️ Database not connected, cannot setup collections")
        return
    
    # Core collections
    users_collection = db.users
    bots_collection = db.bots
    trades_collection = db.trades
    api_keys_collection = db.api_keys
    alerts_collection = db.alerts
    sessions_collection = db.sessions
    system_config_collection = db.system_config
    
    # System modes and chat
    system_modes_collection = db.system_modes
    chat_messages_collection = db.chat_messages
    
    # Lifecycle and monitoring
    bot_lifecycle_collection = db.bot_lifecycle
    bot_metrics_collection = db.bot_metrics
    system_metrics_collection = db.system_metrics
    
    # Training and quarantine
    training_jobs_collection = db.training_jobs
    
    # Advanced features
    risk_profiles_collection = db.risk_profiles
    market_regimes_collection = db.market_regimes
    learning_data_collection = db.learning_data
    learning_logs_collection = db.learning_logs
    audit_logs_collection = db.audit_logs
    notifications_collection = db.notifications
    reports_collection = db.reports
    promotion_requests_collection = db.promotion_requests
    decisions_collection = db.decisions  # AI trading decisions
    reinvest_requests_collection = db.reinvest_requests  # Profit reinvestment requests
    
    # Autopilot and detection
    autopilot_actions_collection = db.autopilot_actions
    rogue_detections_collection = db.rogue_detections
    
    # Emergency stop
    emergency_stop_collection = db.emergency_stop
    
    # Financial tracking
    wallet_balances_collection = db.wallet_balances
    capital_injections_collection = db.capital_injections
    wallets_collection = db.wallets
    ledger_collection = db.ledger
    profits_collection = db.profits
    funding_plans_collection = db.funding_plans
    wallet_transfers_collection = db.wallet_transfers  # Fund transfers between providers
    
    # Orders and positions
    orders_collection = db.orders
    positions_collection = db.positions
    balance_snapshots_collection = db.balance_snapshots
    performance_metrics_collection = db.performance_metrics
    
    # User custom goals/countdowns
    user_countdowns_collection = db.user_countdowns
    
    # Aliases for backward compatibility
    wallet_balances = wallet_balances_collection
    capital_injections = capital_injections_collection
    audit_logs = audit_logs_collection
    funding_plans = funding_plans_collection
    
    logger.info("✅ All collection references initialized")


# ============================================================================
# Database Initialization (Indexes)
# ============================================================================

async def init_db():
    """
    Create database indexes for optimal performance
    Safe to call multiple times - MongoDB handles duplicate index creation
    """
    if db is None:
        logger.warning("⚠️ Database not connected, cannot create indexes")
        return
    
    try:
        logger.info("📊 Creating database indexes...")
        
        # User indexes
        if users_collection is not None:
            await users_collection.create_index("id", unique=True)
            await users_collection.create_index("email", unique=True)
        
        # Bot indexes
        if bots_collection is not None:
            await bots_collection.create_index("id", unique=True)
            await bots_collection.create_index("user_id")
            await bots_collection.create_index([("user_id", 1), ("status", 1)])
        
        # Trade indexes
        if trades_collection is not None:
            await trades_collection.create_index("id", unique=True)
            await trades_collection.create_index("bot_id")
            await trades_collection.create_index("user_id")
            await trades_collection.create_index("timestamp")
            await trades_collection.create_index([("bot_id", 1), ("timestamp", -1)])
        
        # API key indexes
        if api_keys_collection is not None:
            await api_keys_collection.create_index("id", unique=True)
            await api_keys_collection.create_index("user_id")
        
        # Alert indexes
        if alerts_collection is not None:
            await alerts_collection.create_index("user_id")
            await alerts_collection.create_index("timestamp")
        
        # Session indexes
        if sessions_collection is not None:
            await sessions_collection.create_index("user_id")
            await sessions_collection.create_index("created_at", expireAfterSeconds=86400)  # 24 hours
        
        # Bot lifecycle indexes
        if bot_lifecycle_collection is not None:
            await bot_lifecycle_collection.create_index("bot_id")
            await bot_lifecycle_collection.create_index("user_id")
            await bot_lifecycle_collection.create_index("timestamp")
        
        # Metrics indexes
        if bot_metrics_collection is not None:
            await bot_metrics_collection.create_index("bot_id")
            await bot_metrics_collection.create_index("timestamp")
        
        if system_metrics_collection is not None:
            await system_metrics_collection.create_index("timestamp")
        
        # Audit log indexes
        if audit_logs_collection is not None:
            await audit_logs_collection.create_index("user_id")
            await audit_logs_collection.create_index("action")
            await audit_logs_collection.create_index("timestamp")
        
        # Notification indexes
        if notifications_collection is not None:
            await notifications_collection.create_index("user_id")
            await notifications_collection.create_index("timestamp")
            await notifications_collection.create_index([("user_id", 1), ("read", 1)])
        
        # Financial tracking indexes
        if wallet_balances_collection is not None:
            await wallet_balances_collection.create_index("user_id")
            await wallet_balances_collection.create_index("timestamp")
        
        if capital_injections_collection is not None:
            await capital_injections_collection.create_index("bot_id")
            await capital_injections_collection.create_index("user_id")
            await capital_injections_collection.create_index("timestamp")
        
        logger.info("✅ Database indexes created successfully")
        
    except Exception as e:
        logger.error(f"❌ Error creating indexes: {e}")
        # Don't raise - indexes are optional for basic functionality


# ============================================================================
# Utility Functions
# ============================================================================

def is_connected() -> bool:
    """Check if database is connected"""
    return client is not None and db is not None


async def health_check() -> dict:
    """
    Perform a health check on the database connection
    Returns dict with status information
    """
    if not is_connected():
        return {
            "status": "disconnected",
            "error": "Database client not initialized"
        }
    
    try:
        # Ping the database
        await client.admin.command('ping')
        return {
            "status": "connected",
            "database": db.name
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e)
        }
