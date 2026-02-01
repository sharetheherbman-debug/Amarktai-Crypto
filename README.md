# Amarktai Network - Autonomous Trading Platform

**Production-ready AI-powered cryptocurrency trading system** supporting paper and live trading across 7 major exchanges.

[![Production Ready](https://img.shields.io/badge/status-production%20ready-brightgreen)]()
[![Real-time](https://img.shields.io/badge/realtime-WebSocket%20%2B%20SSE-blue)]()
[![Platforms](https://img.shields.io/badge/platforms-7%20exchanges-orange)]()
[![ToS Safe](https://img.shields.io/badge/ToS-compliant-success)]()

---

## 🚀 **Quick Start**

### Fresh Installation (Ubuntu 24.04)
```bash
# See docs/INSTALL.md for complete 30-minute guide
./scripts/preflight.sh  # Pre-deployment checks
./scripts/verify.sh     # Post-deployment verification
```

### Production Deployment
- **Installation Guide**: [`docs/INSTALL.md`](docs/INSTALL.md)
- **Deliverables & Status**: [`docs/DELIVERABLES.md`](docs/DELIVERABLES.md)
- **Systemd Service**: [`docs/examples/amarktai.service`](docs/examples/amarktai.service)
- **Nginx Config**: [`docs/examples/nginx.conf`](docs/examples/nginx.conf)

---

## ✨ **Key Features - Production-Ready**

### 🤖 **Multi-Exchange Trading**
- **7 Fully Supported Exchanges**: Luno, Binance, KuCoin, Bybit, Kraken, Bitget, Gate.io
- **Paper Trading**: 7-day requirement with realistic simulation
- **Live Trading**: Auto-promotion after criteria met (win rate, drawdown, edge gate)
- **65 Bots Maximum**: Distributed across exchanges (5+10+10+10+10+10+10)
- **Auto-Spawn**: New bot every R1000 realized profit

### 📊 **Real-Time Analytics** 
- **Equity Tracking**: Live P&L curves with realized/unrealized profits
- **Execution Quality**: Latency p50/p95, reject rate, slippage monitoring
- **Drawdown Analysis**: Maximum drawdown, current underwater periods
- **Win Rate Statistics**: Comprehensive trade performance metrics
- **Real-Time Updates**: WebSocket + SSE for instant dashboard updates

### 💰 **Wallet Architecture (Production-Safe)**
- **Transfer State Machine**: requested → approved → queued → broadcast → confirmed
- **Idempotency Keys**: Prevent double-send
- **2FA/TOTP**: Required for withdrawals (REQUIRE_2FA_FOR_WITHDRAWALS)
- **Admin Approval**: Large transfers need approval
- **Reserved Funds**: Prevents double-spending
- **Balance Sync**: All 7 exchanges
- **Real CCXT API**: No simulation, actual withdrawals

### 🧠 **Profit-Core + Super Brain (ToS-Safe)**
- **Edge Gate**: Rejects trades if EV < fees + spread + slippage + buffer
- **Bot Coordination**: Dibs & pivot system prevents conflicts
- **Market Regime**: Trending/mean-reversion/high-vol/low-vol detection
- **Self-Healing**: Watchdog, backoff, circuit breakers
- **Treasury**: Sweep excess capital, reinvest to top 5 performers

### 🤖 **AI-Powered Intelligence**
- **AI Chat Assistant**: Natural language trading commands
- **Daily Reports**: Automated performance summaries
- **Content Filtering**: Secure admin access protection
- **Chat History**: On-demand previous conversation loading

### 🎯 **Custom Goals & Dreams**
- **Financial Countdowns**: Track progress to custom targets
- **Real-Time Progress**: Live updates on days remaining
- **Multiple Goals**: Up to 2 custom targets per user

### 🔐 **Security & Compliance**
- **ToS-Safe**: No proxy rotation, IP masking, wash trades, or detection avoidance
- **API Key Encryption**: Fernet symmetric encryption
- **JWT Authentication**: Secure token-based auth
- **2FA/TOTP**: Two-factor authentication
- **Audit Logging**: Immutable transfer ledger
- **Emergency Stop**: Global kill switch

---

## 📖 **Documentation**

### **Getting Started**
| Document | Description |
|----------|-------------|
| **[INSTALL.md](docs/INSTALL.md)** | 📦 Fresh Ubuntu 24.04 installation (~30 minutes) |
| **[DELIVERABLES.md](docs/DELIVERABLES.md)** | ✅ Production readiness checklist & verification |

### **Deployment**
| Document | Description |
|----------|-------------|
| **[Systemd Service](docs/examples/amarktai.service)** | Production systemd configuration |
| **[Nginx Config](docs/examples/nginx.conf)** | WebSocket + SSE reverse proxy |
| **[DEPLOYMENT.md](docs/DEPLOYMENT.md)** | Detailed deployment guide |

### **Reference**
| Document | Description |
|----------|-------------|
| **[API Contract](docs/api_contract.md)** | Complete API documentation |
| **[Complete Feature List](docs/COMPLETE_FEATURE_LIST.md)** | All features and capabilities |
| **[Single Source of Truth](docs/AMARKTAI_SINGLE_SOURCE_OF_TRUTH.md)** | Architecture & operations |

---

## 🚀 Quick Start

### Option 1: Fresh Install (Recommended)

See **[`docs/INSTALL.md`](docs/INSTALL.md)** for complete step-by-step guide.

```bash
# Quick verification after install
./scripts/preflight.sh  # Pre-deployment checks
./scripts/verify.sh     # Post-deployment tests
```

### Option 2: Development Setup

```bash
# 1. Clone repository
git clone <repository-url>
cd Amarktai-Network---Deployment

# 2. Backend setup
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 3. Configure environment
cp .env.example .env
nano .env  # Edit configuration

# 4. Frontend setup
cd ../frontend
npm install
npm run dev

# 5. Start backend
cd ../backend
python -m uvicorn server:app --reload
```

---

## 🛠️ **Scripts & Tools**

### **Pre-Deployment**
```bash
./scripts/preflight.sh  # Check system requirements, dependencies, MongoDB
```

### **Post-Deployment**
```bash
./scripts/verify.sh  # Test all critical endpoints
```

### **Monitoring**
```bash
# System health
curl http://localhost:8000/api/diagnostics/health-detail

# Wallet status
curl http://localhost:8000/api/diagnostics/wallet-status

# Execution quality
curl http://localhost:8000/api/execution-quality/status

# Treasury status
curl http://localhost:8000/api/treasury/status
```

---

## 🔒 **Security Checklist**

Before production deployment:

- [ ] Changed `JWT_SECRET` from default
- [ ] Set `AMARKTAI_FERNET_KEY` for API key encryption
- [ ] Configured firewall (UFW or iptables)
- [ ] Setup SSL/HTTPS with Let's Encrypt
- [ ] MongoDB not exposed externally
- [ ] Created non-root user for application
- [ ] Set `.env` file permissions to 600
- [ ] Reviewed and enabled 2FA for withdrawals

---

## 📊 **System Limits**

| Resource | Limit | Configurable |
|----------|-------|--------------|
| Total bots | 65 | `MAX_TOTAL_BOTS` |
| Bots per exchange | 5-10 | Per exchange config |
| Max capital per bot | 10,000 ZAR | `BOT_MAX_CAPITAL_ZAR` |
| Paper training days | 7 | `PAPER_TRAINING_DAYS` |
| Min win rate (promote) | 52% | `MIN_WIN_RATE` |
| Min trades (promote) | 25 | `MIN_TRADES_FOR_PROMOTION` |

---

## 🌐 **Supported Exchanges**

| Exchange | Status | Max Bots | Features |
|----------|--------|----------|----------|
| **Luno** | ✅ Primary | 5 | ZAR support, zero fees |
| **Binance** | ✅ | 10 | Global liquidity |
| **KuCoin** | ✅ | 10 | Wide coin selection |
| **Bybit** | ✅ | 10 | Low latency |
| **Kraken** | ✅ | 10 | Regulated, secure |
| **Bitget** | ✅ | 10 | Copy trading |
| **Gate.io** | ✅ | 10 | Altcoin specialist |

**Total:** 65 bots maximum across all exchanges

---

## 🔍 **Diagnostics Endpoints**

### System Health
- `GET /api/diagnostics/system-health` - DB, collections, services
- `GET /api/diagnostics/health-detail` - Self-healing, circuit breakers
- `GET /api/diagnostics/realtime` - WebSocket/SSE status

### Trading
- `GET /api/diagnostics/paper-status` - Paper trading status
- `GET /api/diagnostics/autopilot-check` - Autopilot readiness
- `GET /api/diagnostics/auto-spawn` - Auto-spawn diagnostics
- `GET /api/diagnostics/regime` - Market regime detection

### Wallet
- `GET /api/diagnostics/wallet-status` - Balances, transfers
- `GET /api/diagnostics/transfers` - Transfer state distribution

### Performance
- `GET /api/execution-quality/status` - Latency, reject rate, slippage
- `GET /api/execution-quality/history` - Time-series metrics
- `GET /api/treasury/status` - Treasury balance, top performers

---

## 📞 **Support**

### Troubleshooting
```bash
# View logs
sudo journalctl -u amarktai -f

# Check service status
sudo systemctl status amarktai

# Run diagnostics
curl http://localhost:8000/api/diagnostics/system-health | jq
```

### Emergency Procedures
```bash
# Activate emergency stop
curl -X POST http://localhost:8000/api/emergency-stop/activate

# Stop service
sudo systemctl stop amarktai

# Database backup
mongodump --db amarktai_trading --out /backup/$(date +%Y%m%d)
```

---

## 📄 **License**

MIT License - See LICENSE file for details

---

## 🎯 **Status**

✅ **Production-Ready**
- All critical features implemented
- ToS-compliant (no violations)
- Security hardened
- Comprehensive documentation
- Automated deployment

**Last Updated:** 2026-02-01
cd /var/amarktai/app/deployment && sudo ./verify.sh

# Run API smoke tests
cd /var/amarktai/app && ./scripts/smoke_api.sh

# Test SPA routing (deep links work)
cd /var/amarktai/app && ./scripts/test_spa_routing.sh

# Run complete go-live audit
cd /var/amarktai/app && ./scripts/go_live_audit.sh
```

### Endpoint Doctor Script (Recommended)

The new **endpoint_doctor.sh** script provides comprehensive API endpoint testing:

```bash
cd /var/amarktai/app/backend/scripts
./endpoint_doctor.sh http://127.0.0.1:8000 YOUR_JWT_TOKEN
```

**What it tests:**
- ✅ Health & ping endpoints
- ✅ System status, mode, and since-last-login endpoint
- ✅ API keys management (save, test, delete lifecycle)
- ✅ Bots management (create, list, delete with soft-delete verification)
- ✅ Trades & portfolio endpoints
- ✅ Platform/exchange configuration (luno, binance, kucoin enabled)

**Expected output**: All critical endpoints return correct status codes and JSON shapes.

**Exit codes:**
- `0` = All tests passed ✅
- `1` = Some tests failed ❌
- `2` = All tests skipped (no authentication)

### Go-Live Audit Script

The comprehensive go-live audit script validates everything:

```bash
cd /var/amarktai/app
./scripts/go_live_audit.sh
```

This script checks:
- ✅ Environment setup (Python, Node.js, dependencies)
- ✅ Frontend build succeeds
- ✅ Backend tests pass (API keys, bots, overview, chat, paper trading)
- ✅ API endpoints respond correctly
- ✅ SPA routing works (deep links)
- ✅ Configuration is complete

**Expected output**: All tests pass, exit code 0 = ready for go-live! 🚀

---

## ✅ **Production Readiness Checklist**

### All Features Implemented & Working
- [x] **5 Platforms Fully Functional**: Luno, Binance, KuCoin, OVEX, VALR
- [x] **Paper Trading**: Realistic fees, slippage, real market data
- [x] **Live Trading**: Full API integration, order management
- [x] **Real-Time Updates**: WebSocket + SSE working behind nginx
- [x] **Equity Tracking**: Live P&L charts with real data
- [x] **Drawdown Analysis**: Maximum DD, underwater periods
- [x] **Win Rate Stats**: Comprehensive trade performance
- [x] **Wallet Transfers**: Internal fund movement ledger
- [x] **AI Chat**: Welcome messages, history loading, content filters
- [x] **Custom Countdowns**: User financial goals with real-time updates
- [x] **Admin Panel**: User/bot selection, scoped actions
- [x] **50+ API Endpoints**: All documented and tested

### No Placeholders or Mock Data
- [x] **Zero "Coming Soon" Messages**: All features implemented
- [x] **No Mock Data**: Everything uses real database
- [x] **All Charts Functional**: Display actual trading data
- [x] **Complete UI**: No disabled sections or placeholders

### Security & Production Features
- [x] **Authentication**: JWT-based with 2FA support (optional)
- [x] **Authorization**: Role-based admin access
- [x] **Content Filters**: AI chat blocks admin hints
- [x] **Audit Logging**: Complete trail of admin actions
- [x] **Rate Limiting**: Configured in nginx
- [x] **SSL/TLS**: Ready for HTTPS deployment
- [x] **Data Isolation**: User-scoped queries everywhere

### Performance & Scalability
- [x] **Database Indexes**: Auto-created on 70+ collections
- [x] **WebSocket Pooling**: Supports 1000+ concurrent connections
- [x] **Lazy Loading**: Charts load on-demand
- [x] **Pagination**: All list endpoints support pagination
- [x] **Caching**: Static assets cached for 1 year

### Documentation & Testing
- [x] **API Contract**: Complete endpoint documentation
- [x] **Nginx Config**: Production-ready configuration
- [x] **Deployment Guide**: Step-by-step instructions
- [x] **Smoke Tests**: Automated API testing script
- [x] **README**: Comprehensive feature overview

---

## 🎯 Key Features

- ✅ **Autonomous Trading**: AI-powered bots with autopilot mode
- ✅ **Multi-Exchange**: Luno, Binance, KuCoin support
- ✅ **Safety First**: Paper trading, emergency stop, ledger-based accounting
- ✅ **Production Ready**: Systemd service, Nginx config, health monitoring
- ✅ **Single Source of Truth**: Unified autopilot, no duplicate engines

---

## 🔒 Safety Constraints

- ❌ **No automatic fund transfers** between exchanges (hard-blocked)
- ✅ **Paper mode**: Allocation ledger (no real funds moved)
- ✅ **Live mode**: Balance checks only (no transfers)
- ✅ **Bot spawning**: Requires verified profit >= 1000 ZAR
- ✅ **Emergency stop**: Halts all trading immediately

---

## 📚 Documentation

- **[Complete Deployment Guide](docs/AMARKTAI_SINGLE_SOURCE_OF_TRUTH.md)** ← START HERE
- [Quick Start](docs/QUICK_START.md) - Basic getting started
- [Environment Variables](.env.example) - All configuration options
- [API Documentation](http://127.0.0.1:8000/docs) - Interactive API docs (after deployment)
- [Production Features](docs/PRODUCTION_FEATURES_IMPLEMENTATION.md) - All implemented features
- [Go Live Guide](docs/GO_LIVE.md) - Production launch checklist

**Archived docs:** See `docs/archive/` for historical reference

---

## 🛠️ System Requirements

- **OS**: Ubuntu 24.04 LTS
- **Python**: 3.12+
- **Node.js**: 18+ (for frontend)
- **Database**: MongoDB 7.0 (Docker)
- **Cache**: Redis (optional)
- **Web Server**: Nginx (reverse proxy)

---

## 📦 Architecture

```
Nginx (80/443) → FastAPI (127.0.0.1:8000) → MongoDB (127.0.0.1:27017)
                                          → Redis (127.0.0.1:6379)
```

**Canonical VPS Layout:**
```
/var/amarktai/app/          # Repository root
├── backend/                # FastAPI application
│   ├── .venv/              # Python virtual environment
│   └── .env                # Environment config
├── frontend/               # React application  
└── deployment/             # Deployment scripts
    ├── install.sh          # Main installer
    ├── verify.sh           # Verification script
    ├── amarktai-api.service  # Systemd service
    └── nginx-amarktai.conf   # Nginx config
```

---

## 🚦 Trading Modes

**Paper Trading** (safe for testing):
```bash
PAPER_TRADING=1
LIVE_TRADING=0
AUTOPILOT_ENABLED=0  # Optional
```

**Live Trading** (requires API keys):
```bash
PAPER_TRADING=0
LIVE_TRADING=1
AUTOPILOT_ENABLED=0  # Optional
```

**Autopilot** (autonomous bot management):
```bash
AUTOPILOT_ENABLED=1
# Plus either PAPER_TRADING=1 or LIVE_TRADING=1
```

---

## 📞 Support

For detailed troubleshooting and operational procedures:
- **[Complete Documentation](docs/AMARKTAI_SINGLE_SOURCE_OF_TRUTH.md)**
- Check service logs: `sudo journalctl -u amarktai-api.service -f`
- Run verification: `cd deployment && sudo ./verify.sh`

---

## 🔧 Troubleshooting

### SPA Deep Links Return 404

**Problem**: Routes like `/dashboard`, `/login`, `/register` return 404 errors.

**Solution**: 
1. Verify nginx SPA config is installed:
   ```bash
   ls -l /etc/nginx/sites-enabled/amarktai
   ```
2. Check nginx config has `try_files $uri $uri/ /index.html;` in location / block
3. Test nginx config: `sudo nginx -t`
4. Reload nginx: `sudo systemctl reload nginx`
5. Run SPA routing test: `./scripts/test_spa_routing.sh`

### API Keys Save/Test Fails with 422 Error

**Problem**: Frontend shows "Unprocessable Entity" when saving API keys.

**Solution**:
- API now accepts multiple field formats:
  - `provider` OR `exchange`
  - `api_key` OR `apiKey` OR `key`
  - `api_secret` OR `apiSecret` OR `secret`
- Check request payload in browser DevTools
- Verify backend logs: `sudo journalctl -u amarktai-api.service -n 50`

### Deleted Bots Still Appear in List

**Problem**: After deleting a bot, it still shows in the bots list.

**Solution**:
- Bots are soft-deleted (status='deleted')
- GET /api/bots now filters out deleted bots automatically
- Frontend should re-fetch bot list after deletion
- Verify with: `curl http://localhost:8000/api/bots -H "Authorization: Bearer YOUR_TOKEN"`

### Overview Tiles Show Placeholders or Zero

**Problem**: Dashboard overview shows placeholder data instead of real values.

**Solution**:
- Verify realtime SSE connection: `curl http://localhost:8000/api/realtime/events`
- Check trades exist in database: `mongo amarktai --eval "db.trades.count()"`
- Verify bots have profit data: `mongo amarktai --eval "db.bots.find({}, {total_profit: 1})"`
- Enable SSE in frontend and subscribe to overview_update events

### Go-Live Audit Script Fails

**Problem**: `./scripts/go_live_audit.sh` reports failures.

**Solution**:
1. Check error logs: `/tmp/go_live_audit_*.log`
2. Fix specific failing tests:
   - **Frontend build fails**: Check Node.js version (need 18+), run `npm install`
   - **Backend tests fail**: Check Python version (need 3.12+), install deps: `pip install -r requirements.txt`
   - **API tests fail**: Ensure backend is running on port 8000
3. Re-run after fixes: `./scripts/go_live_audit.sh`

---

## 🚀 Deployment Verification

After deploying to production, verify the deployment with these commands:

### 1. Check Build Version

```bash
# Backend build info (unauthenticated endpoint)
curl https://your-domain.com/api/build/info

# Expected response:
{
  "version": "abc1234",
  "built_at": "2026-01-29T...",
  "backend_path": "/path/to/backend",
  "env": "production",
  "api_base": "/api",
  ...
}
```

### 2. Run Smoke Tests

```bash
# From repository root
python3 smoke_test.py

# Or with custom URL
API_BASE_URL=https://your-domain.com python3 smoke_test.py
```

The smoke test validates:
- ✅ Health check endpoint
- ✅ Build info (unauthenticated)
- ✅ Authentication system
- ✅ Wallet routes (no collisions)
- ✅ Unified profit metrics
- ✅ Overview metrics consistency

### 3. Verify Wallet Routes

```bash
# Check wallet routes are registered correctly
curl https://your-domain.com/api/wallet/balances \
  -H "Authorization: Bearer YOUR_TOKEN"

# Should return wallet balances, NOT a 404 or 500
```

### 4. Verify Profit Metrics Consistency

```bash
# Get unified metrics from accounting service
curl https://your-domain.com/api/profits/metrics \
  -H "Authorization: Bearer YOUR_TOKEN"

# Expected response:
{
  "success": true,
  "metrics": {
    "net_realised_pnl_zar": 1234.56,
    "executed_trades_count": 42,
    "total_fees_zar": 12.34,
    ...
  },
  "data_source": "accounting_service"
}

# Verify Overview uses same metrics
curl https://your-domain.com/api/overview \
  -H "Authorization: Bearer YOUR_TOKEN"

# Should include:
# "data_source": "accounting_service"
# "net_realised_pnl_zar": <same as above>
```

### 5. Check Frontend Version Badge

- Open the application in a browser
- Look for version badge in footer or header
- Verify it matches the backend version from /api/build/info

### 6. Monitor Logs

```bash
# Check for route collisions on startup
sudo journalctl -u amarktai-api.service -n 100 | grep -i "wallet\|collision"

# Should see:
# ✅ "WALLET ROUTES REGISTERED"
# ✅ "Route collision check passed"
# ❌ NOT "ROUTE COLLISION DETECTED" or "FATAL"
```

---

## ⚖️ License

See LICENSE file for details.

---

**Quick Links:**
- [📖 Full Documentation](docs/AMARKTAI_SINGLE_SOURCE_OF_TRUTH.md)
- [🔧 Installation Script](deployment/install.sh)
- [✅ Verification Script](deployment/verify.sh)
- [🌐 Nginx Config](deployment/nginx-amarktai.conf)
- [⚙️ Systemd Service](deployment/amarktai-api.service)
