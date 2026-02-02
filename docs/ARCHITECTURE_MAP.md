# Architecture Map

**Last Updated**: 2026-01-27  
**Purpose**: Single source of truth for canonical modules and deprecated files

## 🏗️ Canonical Modules by Domain

### 1. Authentication & Authorization

**Canonical**: `backend/routes/auth.py`
- **Endpoints**: 
  - `POST /api/auth/register` - User registration with invite code support
  - `POST /api/auth/login` - User login
  - `GET /api/auth/me` - Get current user profile
  - `GET /api/auth/profile` - Alias to /auth/me (backward compatible)
  - `PUT /api/auth/profile` - Update user profile
- **Features**: JWT token generation, password hashing, email normalization, auto-migration from legacy hash fields

**Supporting**: `backend/auth.py`
- Core authentication utilities (token creation/verification, password hashing)

---

### 2. Real-Time Events & Streaming

**Canonical SSE Endpoint**: `backend/routes/realtime.py`
- **Endpoint**: `GET /api/realtime/events`
- **Features**: 
  - Server-Sent Events with auth required
  - Heartbeat every 5 seconds
  - Real-time dashboard updates (bots, trades, profits)
  - Proper headers for Nginx (X-Accel-Buffering: no)

**Supporting Modules**:
- `backend/websocket_manager.py` - WebSocket connection management (alternative transport)
- `backend/realtime_events.py` - Event bus for broadcasting to connected clients
- `backend/services/realtime_service.py` - Service layer wrapper

**Alternative Implementation** (optional):
- `backend/websocket_manager_redis.py` - Redis-backed WebSocket for multi-instance deployments

**Deprecated**:
- None (all implementations are valid for different use cases)

**Note**: WebSocket and SSE are complementary, not duplicates. SSE is preferred for unidirectional server-to-client streaming. WebSocket is for bidirectional communication.

---

### 3. Bot Lifecycle & CRUD

**Canonical Routes**: `backend/routes/bot_lifecycle.py`
- **Endpoints**:
  - `GET /api/bots/status` - List all bots with detailed status
  - `POST /api/bots/{bot_id}/start` - Start/resume bot
  - `POST /api/bots/{bot_id}/stop` - Stop/pause bot
  - `POST /api/bots/{bot_id}/pause` - Pause bot with cooldown
  - `POST /api/bots/{bot_id}/resume` - Resume bot after cooldown
  - `DELETE /api/bots/{bot_id}` - Delete bot

**Bot Creation**: `backend/server.py` (lines 341-377)
- **Endpoint**: `POST /api/bots`
- **Validation**: Uses `backend/validators/bot_validator.py`
- **Features**: 
  - Exchange validation
  - Capital validation
  - API key checks (live mode only)
  - Funding plan creation if insufficient balance
  - Bot name uniqueness check
  - Exchange bot limit enforcement

**Business Logic**: `backend/bot_lifecycle.py`
- Paper training period enforcement (7 days)
- Auto-promotion logic
- Lifecycle stage management

**Engine**: `backend/engines/bot_manager.py`
- Bot creation/deletion/status management
- Integration with bot spawner

**Deprecated**:
- `backend/routes/bots.py` - Early implementation (only GET /bots, basic start/stop)
  - **Status**: Legacy - use `bot_lifecycle.py` for new code
  - **Action**: Keep for backward compatibility, but prefer bot_lifecycle.py

---

### 4. Trading Gates & Safety

**Canonical**: `backend/services/system_gate.py`
- **Purpose**: Master gatekeeper - enforces all trading conditions
- **Checks**:
  - Trading mode flags (PAPER_TRADING, LIVE_TRADING)
  - Autopilot enabled flag
  - System health status
  - Emergency stop
  - Circuit breaker status

**Pre-Order Validation**: `backend/services/live_gate_service.py`
- **Purpose**: Pre-trade validation before order execution
- **Checks**:
  - API keys configured for exchange
  - Bot status is active
  - Trading mode matches bot configuration
  - Exchange-specific validations

**Utility Functions**: `backend/utils/trading_gates.py`
- **Purpose**: Basic env var checks
- **Status**: Deprecated - use system_gate.py instead
- **Action**: Migrate callers to system_gate.py

**Route Endpoint**: `backend/routes/live_trading_gate.py`
- **Purpose**: HTTP endpoint wrapper for gate checks
- **Status**: Valid - provides API access to gate status

---

### 5. API Key Management

**Canonical**: `backend/routes/api_keys_canonical.py`
- **Endpoints**:
  - `GET /api/keys` - List all user API keys (masked)
  - `POST /api/keys` - Add new API key
  - `PUT /api/keys/{key_id}` - Update API key
  - `DELETE /api/keys/{key_id}` - Delete API key
  - `POST /api/keys/{key_id}/test` - Test API key validity
- **Features**:
  - 8 provider support (OpenAI, Flokx, FetchAI, Luno, Binance, KuCoin, Bybit, Kraken, Bitget, Gate.io)
  - Encryption/decryption with Fernet
  - Provider registry integration
  - API key testing before storage

**Supporting**: `backend/services/keys_service.py`
- Core key management business logic

**Provider Registry**: `backend/services/provider_registry.py`
- Defines supported providers and their configurations

**Deprecated**:
- `backend/routes/api_keys.py` - Basic implementation (no encryption/testing)
  - **Status**: Deprecated
  - **Action**: Remove or mark as archived
- `backend/routes/api_key_management.py` - Full implementation but superseded
  - **Status**: Deprecated (use api_keys_canonical.py)
  - **Action**: Remove or mark as archived
- `backend/routes/user_api_keys.py` - User-specific variant
  - **Status**: May be needed for user-specific payment configs
  - **Action**: Review and consolidate if possible

---

### 6. Analytics & Profits

**Canonical**: `backend/routes/analytics_api.py`
- **Purpose**: Single source of truth for dashboards
- **Endpoints**:
  - `GET /api/analytics/overview` - Dashboard overview
  - `GET /api/analytics/performance` - Performance metrics
  - `GET /api/analytics/trades` - Trade history
  - `GET /api/analytics/bots` - Bot analytics
- **Features**: Uses metrics_service for calculations

**Profit Service**: `backend/routes/profits.py`
- **Purpose**: Profit calculation endpoints
- **Endpoints**:
  - `GET /api/profits` - Get user profits
  - `GET /api/profits/realized` - Realized profits only
  - `GET /api/profits/unrealized` - Unrealized P&L
- **Features**: Uses profit_service business logic

**Business Logic**: `backend/services/profit_service.py`
- Core profit calculation logic
- Ledger integration
- Realized vs unrealized P&L

**Status**: Both analytics_api and profits routes are valid. Analytics is single source of truth for dashboards. Profits provides specialized profit calculations.

---

### 7. Order Execution Pipeline

**Canonical**: `backend/services/order_pipeline.py`
- **Purpose**: 4-gate order validation pipeline
- **Gates**:
  1. System Gate (trading mode, health checks)
  2. Capital Gate (sufficient funds)
  3. Risk Gate (position sizing, stop loss)
  4. Idempotency Gate (duplicate prevention)

**Validation**: `backend/services/order_validation.py`
- Pre-trade validation logic
- Fee coverage checks
- Minimum edge requirements

**Route**: `backend/routes/order_endpoints.py`
- HTTP endpoints for order submission

---

### 8. Trading Engines

**Paper Trading**: `backend/paper_trading_engine.py`
- Simulated trading with realistic modeling
- Fee/slippage/spread simulation
- Virtual balance tracking

**Live Trading**: `backend/engines/trading_engine_live.py` / `trading_engine_production.py`
- Real exchange integration via CCXT
- Order execution with error handling
- Position tracking

**Autopilot**: `backend/engines/autopilot_production.py`
- Autonomous bot spawning
- Profit reinvestment
- Bot promotion management

---

## 🚫 Deprecated Files

### Archived Implementations
Location: `backend/_archive/`

- `backend/_archive/platform_constants.py` - Old platform definitions
- `backend/_archive/routes/trades.py` - Early trade route implementation

**Status**: Not imported, kept for reference only

### Recommended Actions

1. **API Keys**: Consolidate to `api_keys_canonical.py`
   - Remove: `api_keys.py`, `api_key_management.py`
   - Review: `user_api_keys.py` for unique payment features

2. **Bot CRUD**: Standardize on `bot_lifecycle.py`
   - Deprecate: `routes/bots.py` (keep for backward compat if needed)

3. **Trading Gates**: Migrate to `system_gate.py`
   - Remove: `utils/trading_gates.py` after migration

---

## 📋 Configuration Files

### Platform Configuration
**Canonical**: `backend/config/platforms.py`
- Defines 7 supported exchanges: Luno, Binance, KuCoin, Bybit, Kraken, Bitget, Gate.io
- Bot capacity limits per platform
- Total system capacity (65 bots)

### Environment Configuration
**Files**:
- `.env.example` - Template for environment variables (root and backend/)
- `backend/config.py` - Application configuration loader

**Critical Variables**:
- `PAPER_TRADING` / `LIVE_TRADING` - Trading mode gates
- `AUTOPILOT_ENABLED` - Autonomous bot management
- `JWT_SECRET` - Token signing key
- `MONGO_URL` / `DB_NAME` - Database connection
- `ENCRYPTION_KEY` - API key encryption

---

## 🔍 Finding Canonical Implementations

### Rules of Thumb

1. **Routes**: Look in `backend/routes/` for endpoint definitions
2. **Business Logic**: Look in `backend/services/` for reusable logic
3. **Engines**: Look in `backend/engines/` for autonomous systems
4. **Validation**: Look in `backend/validators/` for input validation
5. **Utilities**: Look in `backend/utils/` for helper functions

### Naming Conventions

- `*_canonical.py` - Explicitly marked as canonical
- `*_production.py` - Production-ready implementation
- `*_legacy.py` - Deprecated, kept for backward compatibility
- Files in `_archive/` - Not imported, archived for reference

---

## 🚀 Frontend Architecture

### API Client
**Canonical**: `frontend/src/lib/api.js`
- Base URL configuration
- WebSocket URL generation
- Single source of truth for API configuration

### Real-Time Client
**Canonical**: `frontend/src/lib/realtime.js`
- WebSocket connection management
- Event subscription system
- Automatic reconnection

**Hook**: `frontend/src/hooks/useRealtime.js`
- React hook for real-time features
- Event listeners
- Connection status

### Main Dashboard
**File**: `frontend/src/pages/Dashboard.js`
- Central dashboard UI
- Bot management
- Analytics display
- AI chat integration

---

## 📝 Migration Guide

### If You Need to...

**Add a new endpoint**:
1. Add to appropriate route file in `backend/routes/`
2. Register in `backend/server.py` router list
3. Update this document

**Modify authentication**:
1. Update `backend/routes/auth.py`
2. Update `backend/auth.py` if needed for utilities
3. Test with `scripts/verify_auth_contract.py`

**Change bot lifecycle**:
1. Update `backend/routes/bot_lifecycle.py` for endpoints
2. Update `backend/bot_lifecycle.py` for business logic
3. Update `backend/validators/bot_validator.py` for validation

**Add real-time events**:
1. Use `backend/realtime_events.py` event bus
2. Emit from relevant services/routes
3. Subscribe in frontend via `useRealtime` hook

**Modify trading gates**:
1. Update `backend/services/system_gate.py` for system-level checks
2. Update `backend/services/live_gate_service.py` for pre-order checks
3. Test with trading gate demo scripts

---

## 🔄 Continuous Updates

This document should be updated whenever:
- New canonical modules are introduced
- Files are deprecated or archived
- Major refactoring occurs
- Module responsibilities change

**Maintainer**: Development team  
**Review Frequency**: Monthly or on major releases
