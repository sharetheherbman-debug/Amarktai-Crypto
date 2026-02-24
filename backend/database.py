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

# Paper trading wallet ledger (Phase 4A)
paper_ledger_collection = None

# System modes and chat
system_modes_collection = None
chat_messages_collection = None
chat_sessions_collection = None

# Lifecycle and monitoring
bot_lifecycle_collection = None
bot_metrics_collection = None
system_metrics_collection = None
bot_runtime_state_collection = None

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
autopilot_milestones_collection = None
autopilot_reinvest_events_collection = None

# Emergency stop collection
emergency_stop_collection = None

# Financial tracking collections
wallet_balances_collection = None
capital_injections_collection = None
wallets_collection = None
ledger_collection = None
profits_collection = None
profit_ledger_collection = None
funding_plans_collection = None
wallet_transfers_collection = None  # Fund transfers between providers (legacy)

# Production-safe wallet transfer system
transfer_jobs_collection = None  # Transfer jobs with state machine
transfers_ledger_collection = None  # Immutable transfer event log

# Orders and positions
orders_collection = None
positions_collection = None
balance_snapshots_collection = None
performance_metrics_collection = None

# User custom goals/countdowns
user_countdowns_collection = None

# Market data snapshots
price_snapshots_collection = None

# Learning loop audit tables
learning_runs_collection = None
learning_changes_collection = None
learning_metrics_collection = None
strategy_versions_collection = None
bot_strategy_assignments_collection = None
action_audit_log_collection = None

# ChatOps memory and audit logs
user_memory_collection = None
chatops_actions_collection = None
chatops_confirmations_collection = None

# Aliases for backward compatibility
wallet_balances = None  # Alias for wallet_balances_collection
capital_injections = None  # Alias for capital_injections_collection
audit_logs = None  # Alias for audit_logs_collection
funding_plans = None  # Alias for funding_plans_collection


# ============================================================================
# Database Connection Functions
# ============================================================================

def _parse_mongo_config() -> tuple:
    """
    Resolve MongoDB URL and database name from environment variables.

    Priority (first match wins):
    1. MONGO_URI  – may embed the DB name as the path component, e.g.
       mongodb://host:27017/amarktai_trading
    2. MONGO_URL + MONGO_DB (or DB_NAME) – explicit separate variables
    3. Hardcoded defaults (localhost, amarktai_trading)

    Split-brain guard: if the resolved DB is "amarktai" but MONGO_DB/DB_NAME
    are not explicitly set to "amarktai", a WARNING is emitted because
    "amarktai_trading" is the authoritative production database.

    Returns:
        (mongo_url, db_name) – the connection URL and the resolved DB name.
    """
    mongo_uri = os.getenv("MONGO_URI", "").strip()
    if mongo_uri:
        # Extract DB name from the URI path if present, e.g. /amarktai_trading
        try:
            from urllib.parse import urlparse
            parsed = urlparse(mongo_uri)
            path_db = parsed.path.lstrip("/").split("?")[0].strip()
            if path_db:
                _log_effective_mongo(mongo_uri, path_db)
                return mongo_uri, path_db
        except Exception:
            pass
        # MONGO_URI set but no DB path – fall through to MONGO_DB/DB_NAME
        db_name = os.getenv("MONGO_DB", os.getenv("DB_NAME", "amarktai_trading"))
        _log_effective_mongo(mongo_uri, db_name)
        return mongo_uri, db_name

    mongo_url = os.getenv("MONGO_URL", "mongodb://localhost:27017")
    db_name = os.getenv("MONGO_DB", os.getenv("DB_NAME", "amarktai_trading"))
    _log_effective_mongo(mongo_url, db_name)
    return mongo_url, db_name


def _log_effective_mongo(mongo_url: str, db_name: str) -> None:
    """Log the effective MongoDB connection (host only, no credentials)."""
    try:
        from urllib.parse import urlparse
        parsed = urlparse(mongo_url)
        safe_host = f"{parsed.hostname}:{parsed.port or 27017}"
    except Exception:
        safe_host = "unknown"
    logger.info(f"Effective MongoDB: host={safe_host} db={db_name}")
    if db_name == "amarktai" and not os.getenv("ALLOW_AMARKTAI_DB"):
        logger.warning(
            "⚠️  Split-brain risk: resolved db='amarktai' but production db is "
            "'amarktai_trading'. Set MONGO_URI/MONGO_DB=amarktai_trading or set "
            "ALLOW_AMARKTAI_DB=1 to suppress this warning."
        )


async def connect():
    """
    Connect to MongoDB and initialize all collections
    This is the main entry point for database initialization
    """
    global client, db

    mongo_url, db_name = _parse_mongo_config()

    # Log safe identity (host only, no credentials) – _parse_mongo_config already
    # emits the canonical "Effective MongoDB: host=... db=..." line.
    try:
        from urllib.parse import urlparse
        parsed = urlparse(mongo_url)
        safe_host = f"{parsed.hostname}:{parsed.port or 27017}"
    except Exception:
        safe_host = "unknown"
    logger.info(f"🔌 Connecting to MongoDB host={safe_host}")

    try:
        client = AsyncIOMotorClient(mongo_url)
        db = client[db_name]
        
        # Test connection
        await client.admin.command('ping')
        logger.info(f"✅ MongoDB connection successful - database: {db_name}")
        
        # Setup all collections
        await setup_collections()
        
        # Deduplicate bots BEFORE creating the unique index so existing duplicates
        # don't cause IndexKeySpecsConflict failures.
        try:
            from migrations.deduplicate_bots import run_dedup_on_startup
            await run_dedup_on_startup()
        except Exception as dedup_error:
            logger.warning(f"Bot deduplication failed (non-critical): {dedup_error}")

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
    global system_config_collection, system_modes_collection, chat_messages_collection, chat_sessions_collection
    global bot_lifecycle_collection, bot_metrics_collection, system_metrics_collection
    global bot_runtime_state_collection
    global training_jobs_collection
    global risk_profiles_collection, market_regimes_collection
    global learning_data_collection, learning_logs_collection, audit_logs_collection
    global notifications_collection, reports_collection, promotion_requests_collection
    global decisions_collection, reinvest_requests_collection
    global autopilot_actions_collection, rogue_detections_collection
    global autopilot_milestones_collection, autopilot_reinvest_events_collection
    global emergency_stop_collection
    global wallet_balances_collection, capital_injections_collection
    global wallets_collection, ledger_collection, profits_collection, profit_ledger_collection, funding_plans_collection
    global wallet_transfers_collection
    global transfer_jobs_collection, transfers_ledger_collection  # Production-safe wallet transfers
    global orders_collection, positions_collection, balance_snapshots_collection, performance_metrics_collection
    global user_countdowns_collection
    global price_snapshots_collection
    global learning_runs_collection, learning_changes_collection, learning_metrics_collection
    global strategy_versions_collection, bot_strategy_assignments_collection, action_audit_log_collection
    global user_memory_collection, chatops_actions_collection, chatops_confirmations_collection
    global wallet_balances, capital_injections, audit_logs, funding_plans
    global paper_ledger_collection  # Phase 4A: Paper wallet ledger
    
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
    
    # Paper trading wallet ledger (Phase 4A)
    paper_ledger_collection = db.paper_ledger
    
    # System modes and chat
    system_modes_collection = db.system_modes
    chat_messages_collection = db.chat_messages
    chat_sessions_collection = db.chat_sessions
    
    # Lifecycle and monitoring
    bot_lifecycle_collection = db.bot_lifecycle
    bot_metrics_collection = db.bot_metrics
    system_metrics_collection = db.system_metrics
    bot_runtime_state_collection = db.bot_runtime_state
    
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
    autopilot_milestones_collection = db.autopilot_milestones
    autopilot_reinvest_events_collection = db.autopilot_reinvest_events
    
    # Emergency stop
    emergency_stop_collection = db.emergency_stop
    
    # Financial tracking
    wallet_balances_collection = db.wallet_balances
    capital_injections_collection = db.capital_injections
    wallets_collection = db.wallets
    ledger_collection = db.ledger
    profits_collection = db.profits
    profit_ledger_collection = db.profit_ledger
    funding_plans_collection = db.funding_plans
    wallet_transfers_collection = db.wallet_transfers  # Fund transfers between providers (legacy)
    
    # Production-safe wallet transfer system
    transfer_jobs_collection = db.transfer_jobs  # Transfer jobs with state machine
    transfers_ledger_collection = db.transfers_ledger  # Immutable transfer event log
    
    # Orders and positions
    orders_collection = db.orders
    positions_collection = db.positions
    balance_snapshots_collection = db.balance_snapshots
    performance_metrics_collection = db.performance_metrics
    
    # User custom goals/countdowns
    user_countdowns_collection = db.user_countdowns

    # Market data snapshots
    price_snapshots_collection = db.price_snapshots

    # Learning loop audit tables
    learning_runs_collection = db.learning_runs
    learning_changes_collection = db.learning_changes
    learning_metrics_collection = db.learning_metrics
    strategy_versions_collection = db.strategy_versions
    bot_strategy_assignments_collection = db.bot_strategy_assignments
    action_audit_log_collection = db.action_audit_log

    # ChatOps memory and audit logs
    user_memory_collection = db.user_memory
    chatops_actions_collection = db.chatops_actions
    chatops_confirmations_collection = db.chatops_confirmations
    
    # Aliases for backward compatibility
    wallet_balances = wallet_balances_collection
    capital_injections = capital_injections_collection
    audit_logs = audit_logs_collection
    funding_plans = funding_plans_collection
    
    logger.info("✅ All collection references initialized")


# ============================================================================
# Database Initialization (Indexes)
# ============================================================================

async def _safe_create_index(collection, keys, **kwargs):
    """
    Create an index idempotently.
    - If an identical index already exists: silently succeeds.
    - If an index with the same name but different spec exists (IndexKeySpecsConflict):
      logs a WARNING instead of crashing startup.
    """
    try:
        await collection.create_index(keys, **kwargs)
    except Exception as e:
        err_str = str(e)
        if "IndexKeySpecsConflict" in err_str or "already exists with different" in err_str or "already exists with a different" in err_str:
            logger.warning(f"⚠️ Index already exists with different spec (skipping): {e}")
        else:
            raise


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
            await _safe_create_index(users_collection, "id", unique=True)
            await _safe_create_index(users_collection, "email", unique=True)
        
        # Bot indexes
        if bots_collection is not None:
            await _safe_create_index(bots_collection, "id", unique=True)
            await _safe_create_index(bots_collection, "user_id")
            await _safe_create_index(bots_collection, [("user_id", 1), ("status", 1)])
            # Prevent duplicate named bots per user/exchange/mode (non-deleted only)
            await _safe_create_index(
                bots_collection,
                [("user_id", 1), ("exchange", 1), ("trading_mode", 1), ("name", 1)],
                unique=True,
                partialFilterExpression={"deleted_at": {"$exists": False}},
                name="uidx_bot_identity",
            )
        
        # Trade indexes
        if trades_collection is not None:
            await _safe_create_index(trades_collection, "id", unique=True, sparse=True)
            await _safe_create_index(trades_collection, "bot_id")
            await _safe_create_index(trades_collection, "user_id")
            await _safe_create_index(trades_collection, "timestamp")
            await _safe_create_index(trades_collection, [("bot_id", 1), ("timestamp", -1)])
        
        # API key indexes
        if api_keys_collection is not None:
            await _safe_create_index(api_keys_collection, "id", unique=True)
            await _safe_create_index(api_keys_collection, "user_id")
        
        # Alert indexes
        if alerts_collection is not None:
            await _safe_create_index(alerts_collection, "user_id")
            await _safe_create_index(alerts_collection, "timestamp")
        
        # Session indexes
        if sessions_collection is not None:
            await _safe_create_index(sessions_collection, "user_id")
            await _safe_create_index(sessions_collection, "created_at", expireAfterSeconds=86400)  # 24 hours

        # Chat indexes
        if chat_messages_collection is not None:
            await _safe_create_index(chat_messages_collection, "user_id")
            await _safe_create_index(chat_messages_collection, "timestamp")
        if chat_sessions_collection is not None:
            await _safe_create_index(chat_sessions_collection, "user_id", unique=True)
        if chatops_confirmations_collection is not None:
            await _safe_create_index(chatops_confirmations_collection, "confirmation_id", unique=True)
            await _safe_create_index(chatops_confirmations_collection, "user_id")
            await _safe_create_index(chatops_confirmations_collection, "expires_at")
        
        # Bot lifecycle indexes
        if bot_lifecycle_collection is not None:
            await _safe_create_index(bot_lifecycle_collection, "bot_id")
            await _safe_create_index(bot_lifecycle_collection, "user_id")
            await _safe_create_index(bot_lifecycle_collection, "timestamp")
        
        # Metrics indexes
        if bot_metrics_collection is not None:
            await _safe_create_index(bot_metrics_collection, "bot_id")
            await _safe_create_index(bot_metrics_collection, "timestamp")
        
        if system_metrics_collection is not None:
            await _safe_create_index(system_metrics_collection, "timestamp")
        
        # Audit log indexes
        if audit_logs_collection is not None:
            await _safe_create_index(audit_logs_collection, "user_id")
            await _safe_create_index(audit_logs_collection, "action")
            await _safe_create_index(audit_logs_collection, "timestamp")
        
        # Notification indexes
        if notifications_collection is not None:
            await _safe_create_index(notifications_collection, "user_id")
            await _safe_create_index(notifications_collection, "timestamp")
            await _safe_create_index(notifications_collection, [("user_id", 1), ("read", 1)])

        if autopilot_milestones_collection is not None:
            await _safe_create_index(
                autopilot_milestones_collection,
                [("user_id", 1), ("platform", 1), ("milestone_index", 1)],
                unique=True
            )
            await _safe_create_index(
                autopilot_milestones_collection,
                [("user_id", 1), ("platform", 1), ("triggered_at", -1)]
            )

        if autopilot_reinvest_events_collection is not None:
            await _safe_create_index(
                autopilot_reinvest_events_collection,
                [("user_id", 1), ("platform", 1), ("date_key", 1)],
                unique=True
            )
            await _safe_create_index(
                autopilot_reinvest_events_collection,
                [("user_id", 1), ("platform", 1), ("created_at", -1)]
            )
        
        # Financial tracking indexes
        if wallet_balances_collection is not None:
            await _safe_create_index(wallet_balances_collection, "user_id")
            await _safe_create_index(wallet_balances_collection, "timestamp")
        
        if capital_injections_collection is not None:
            await _safe_create_index(capital_injections_collection, "bot_id")
            await _safe_create_index(capital_injections_collection, "user_id")
            await _safe_create_index(capital_injections_collection, "timestamp")
        
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
