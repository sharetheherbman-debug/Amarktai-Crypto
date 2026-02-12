# Amarktai Network - Autonomous Trading Platform

**Production-ready AI-powered cryptocurrency trading system** supporting paper and live trading across 7 major exchanges.

> 📚 **Companion Docs:** [DEPLOY.md](DEPLOY.md) | [VERIFICATION.md](VERIFICATION.md) | [ACCEPTANCE_TESTS.md](ACCEPTANCE_TESTS.md)

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
- **Auto-Spawn**: New bot every R1000 realized profit per exchange

### 📊 **Real-Time Analytics** 
- **Equity Tracking**: Live P&L curves with realized/unrealized profits
- **Execution Quality**: Latency p50/p95, reject rate, slippage monitoring
- **Drawdown Analysis**: Maximum drawdown, current underwater periods
- **Win Rate Statistics**: Comprehensive trade performance metrics
- **Real-Time Updates**: WebSocket + SSE for instant dashboard updates

### 💰 **Wallet Architecture (Production-Safe)**
- ✅ **Transfer State Machine**: requested → approved → queued → broadcast → confirmed
- ✅ **Idempotency Keys**: Prevent duplicate transfers
- ✅ **2FA/TOTP Enforcement**: Required for withdrawals (configurable via REQUIRE_2FA_FOR_WITHDRAWALS)
- ✅ **Admin Approval Workflows**: Large transfers require manual approval
- ✅ **Reserved Funds Tracking**: Prevents double-spending with capital allocation ledger
- ✅ **Balance Sync**: Real-time balance fetching for all 7 exchanges
- ✅ **Real CCXT Withdrawals**: Actual exchange API withdrawals (no simulation in live mode)
- ✅ **Safety Limits**: Transaction, daily, and monthly withdrawal limits
- ✅ **Emergency Stop Integration**: Blocks all transfers when emergency stop is active
- ✅ **Immutable Audit Trail**: transfers_ledger with complete transaction history

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

### **Testing**
```bash
# Run all tests (prevents plugin auto-loading issues)
./scripts/test.sh

# Run specific test file
./scripts/test.sh tests/test_bots_e2e.py

# Run with pytest directly (requires PYTEST_DISABLE_PLUGIN_AUTOLOAD=1)
export PYTEST_DISABLE_PLUGIN_AUTOLOAD=1
python -m pytest -q --maxfail=25 --disable-warnings
```

**Note:** The test runner disables third-party pytest plugin auto-loading to prevent crashes from web3/ethereum plugins.

### **Pre-Deployment**
```bash
./scripts/preflight.sh  # Check system requirements, dependencies, MongoDB
```

### **Post-Deployment**
```bash
./scripts/verify.sh  # Test all critical endpoints
```

### **Production Smoke Test** 🆕
Quick production readiness verification (<2 minutes):

```bash
# Test production deployment
./scripts/smoke_prod.sh https://amarktai.online AMARKTAI2024

# Test local deployment
./scripts/smoke_prod.sh http://localhost:8000 AMARKTAI2024
```

**What it tests:**
- ✅ Health check endpoint
- ✅ User registration with invite header
- ✅ Login and token generation
- ✅ System status (feature flags, trading modes)
- ✅ API keys endpoint authentication
- ✅ WebSocket diagnostics and configuration
- ✅ Verifies no /api/api/ double path bugs
- ✅ Optional: Live WebSocket connection test

**Exit codes:**
- `0` - All tests passed ✅
- `1` - One or more tests failed ❌

See [`docs/GO_LIVE_GUIDE.md`](docs/GO_LIVE_GUIDE.md) for complete deployment guide.

### **Section Smoke Test (Go-Live Gate)** 🆕
Run section-by-section checks (auth, system, wallet, analytics, realtime, admin):

```bash
# With existing token
./scripts/smoke_sections.sh https://amarktai.online "$TOKEN"

# Or provide login credentials (optional)
EMAIL="admin@example.com" PASSWORD="YourPassword" ./scripts/smoke_sections.sh https://amarktai.online
```

Expected output: PASS/FAIL per section with a non-zero exit code if any critical check fails.

### **Go Live Verification (VPS)** 🆕
Run the go-live scripts directly on the VPS (defaults to `http://127.0.0.1:8000`):

```bash
export AMK_EMAIL="user@example.com"
export AMK_PASSWORD="your-password"
export AMK_ADMIN_EMAIL="admin@example.com"
export AMK_ADMIN_PASSWORD="admin-password"

./scripts/go_live_verify.sh
./scripts/go_live_smoke.sh http://127.0.0.1:8000
./scripts/contract_test.sh http://127.0.0.1:8000 "$AMK_EMAIL" "$AMK_PASSWORD" "$AMK_ADMIN_EMAIL" "$AMK_ADMIN_PASSWORD"
./scripts/smoke_ai_chat.sh http://127.0.0.1:8000
```

### **Go Live Audit (Paper Mode)** 🆕
Run the single-command audit (backend checks + frontend build). Requires login credentials:

```bash
export AMARKTAI_EMAIL="user@example.com"
export AMARKTAI_PASSWORD="your-password"
export BASE_URL="http://127.0.0.1:8000"

./scripts/go_live_audit.sh
```

### **Audit & Parity Verification**
Generate machine-checkable inventories and verify frontend/backend parity:

```bash
python3 scripts/audit_endpoints.py
python3 scripts/audit_frontend_calls.py
python3 scripts/verify_parity.py
```

Artifacts are written to `artifacts/`. A run is **PASS** when the script exits `0`
and prints `PASS` in the parity report.

### **Canonical Frontend Endpoints**
The dashboard is aligned to these backend routes:
- Bots: `GET /api/bots`, `GET /api/bots/status`
- Admin storage: `GET /api/admin/storage`
- AI chat: `POST /api/ai/chat`, `GET /api/ai/chat/history`, `POST /api/ai/chat/greeting`

---

## ✅ Go-Live Checklist
- [ ] Run `./scripts/smoke_sections.sh <BASE_URL> <TOKEN>` and confirm all sections PASS
- [ ] Confirm `/api/diagnostics/realtime` returns 200 and WebSocket connects to `/api/ws?token=...`
- [ ] Verify Admin panel loads counts, system modes, scheduler status, and per-exchange breakdowns
- [ ] Confirm Bodyguard config via `.env` (paper thresholds higher, live stricter) and reset endpoint works
- Countdown: `GET /api/analytics/countdown-to-million`, `GET/POST/DELETE /api/countdowns`

### **VPS Smoke Tests (User/Admin/Realtime)**
Run smoke checks against a deployed VPS (requires `jq` and backend Python deps):

```bash
./scripts/smoke_user.sh https://amarktai.online user@example.com password
./scripts/smoke_admin.sh https://amarktai.online admin@example.com password
./scripts/smoke_realtime.sh https://amarktai.online user@example.com password
```

Each script prints `PASS` on success and returns a non-zero exit code on failure.
For test environments with self-signed certificates, set `AMARKTAI_WS_INSECURE=1`
before running `smoke_realtime.sh` to disable TLS verification.

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
- `GET /api/diagnostics/ws` - **WebSocket configuration and readiness** 🆕

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

**Last Updated:** 2026-02-10

---

## 📖 **Documentation**

### **Deployment & Verification**
| Document | Description |
|----------|-------------|
| **[DEPLOY.md](DEPLOY.md)** | 🚀 Complete deployment guide (env vars, clean deploy, troubleshooting) |
| **[VERIFICATION.md](VERIFICATION.md)** | ✅ Post-deployment verification checks |
| **[ACCEPTANCE_TESTS.md](ACCEPTANCE_TESTS.md)** | 🧪 Acceptance test criteria for go-live |

### **Additional Docs**
| Document | Description |
|----------|-------------|
| **[docs/INSTALL.md](docs/INSTALL.md)** | 📦 Fresh Ubuntu 24.04 installation (~30 minutes) |
| **[docs/DELIVERABLES.md](docs/DELIVERABLES.md)** | ✅ Production readiness checklist |
| **[Systemd Service](docs/examples/amarktai.service)** | Production systemd configuration |
| **[Nginx Config](docs/examples/nginx.conf)** | WebSocket + SSE reverse proxy |

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

## 🚀 Go Live Checklist

Before deploying to production with live trading and wallet transfers:

### Infrastructure Prerequisites
- [ ] Ubuntu 24.04 LTS VPS with at least 2GB RAM
- [ ] MongoDB 7.0+ installed and secured
- [ ] Redis installed (optional but recommended)
- [ ] SSL/HTTPS certificate configured (Let's Encrypt)
- [ ] Firewall configured (UFW: allow 80, 443, block 8000)
- [ ] Non-root user created for application
- [ ] Systemd service configured and enabled

### Security Prerequisites
- [ ] Changed `JWT_SECRET` from default (32+ chars, randomly generated)
- [ ] Set `AMARKTAI_FERNET_KEY` for API key encryption
- [ ] MongoDB not exposed externally (bind to 127.0.0.1 only)
- [ ] `.env` file permissions set to 600
- [ ] Admin password changed from default
- [ ] All API keys encrypted in database
- [ ] 2FA/TOTP configured and tested

### Wallet Prerequisites (CRITICAL)
- [ ] **Transfer State Machine**: Verified `transfer_jobs` collection working
- [ ] **Idempotency**: Tested duplicate prevention with same idempotency key
- [ ] **2FA Enforcement**: Set `REQUIRE_2FA_FOR_WITHDRAWALS=true` in .env
- [ ] **Admin Approval**: Tested approval workflow for large transfers
- [ ] **Reserved Funds**: Capital allocation ledger preventing over-allocation
- [ ] **Balance Sync**: All 7 exchanges returning real-time balances
- [ ] **Safety Limits**: Transaction/daily/monthly limits configured
- [ ] **Emergency Stop**: Verified it blocks ALL transfers immediately
- [ ] **Withdrawal Testing**: Small test withdrawal completed successfully on each exchange
- [ ] **Audit Trail**: `transfers_ledger` recording all transactions immutably

### Trading Prerequisites
- [ ] API keys configured for all 7 exchanges you plan to use
- [ ] Keys tested via `/api/keys/test` endpoint
- [ ] Paper trading tested for 7+ days with profitable results
- [ ] Live trading gates understood (win rate, drawdown, profit thresholds)
- [ ] Emergency stop tested and verified working
- [ ] Rate limits configured appropriately
- [ ] Bot allocation limits verified (5 for Luno, 10 for others)

### Monitoring Prerequisites
- [ ] All diagnostics endpoints tested and returning expected data
- [ ] Health checks passing (`/api/diagnostics/system-health`)
- [ ] Wallet status endpoint working (`/api/diagnostics/wallet-status`)
- [ ] Log rotation configured
- [ ] Backup strategy in place for MongoDB
- [ ] Alert system configured (email/webhook for critical events)

### Testing Prerequisites
- [ ] All preflight checks passed (`./scripts/preflight.sh`)
- [ ] All verification tests passed (`./scripts/verify.sh`)
- [ ] Compliance checks passed (`./scripts/compliance_checks.sh`)
- [ ] Route collision checks passed (no wallet route conflicts)
- [ ] Frontend build successful and deployed
- [ ] WebSocket/SSE connections working through nginx
- [ ] No 404s on route refresh (SPA routing working)

### Documentation Prerequisites
- [ ] Read and understood wallet implementation guide
- [ ] Reviewed emergency procedures
- [ ] Team trained on admin approval workflow
- [ ] Incident response plan documented
- [ ] Rollback procedure tested

### Configuration Prerequisites
- [ ] `PAPER_TRADING=0` (disabled for live mode)
- [ ] `LIVE_TRADING=1` (enabled for real trades)
- [ ] `AUTOPILOT_ENABLED=0` initially (enable after monitoring)
- [ ] `REQUIRE_2FA_FOR_WITHDRAWALS=true` (enforce 2FA)
- [ ] `ENABLE_TRADING=true` (master switch)
- [ ] `ENABLE_CCXT=true` (exchange connections)
- [ ] Transfer limits appropriate for your risk tolerance

### Final Verification
```bash
# 1. Run all automated checks
./scripts/preflight.sh
./scripts/verify.sh
./scripts/compliance_checks.sh

# 2. Test small wallet transfer
curl -X POST https://your-domain.com/api/wallet/transfers \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "from_exchange": "binance",
    "to_exchange": "luno",
    "currency": "BTC",
    "amount": 0.0001,
    "idempotency_key": "test-transfer-001",
    "totp_code": "123456"
  }'

# 3. Verify transfer appears in ledger
curl https://your-domain.com/api/diagnostics/transfers \
  -H "Authorization: Bearer YOUR_TOKEN"

# 4. Test emergency stop
curl -X POST https://your-domain.com/api/system/emergency-stop \
  -H "Authorization: Bearer YOUR_TOKEN"

# 5. Verify all operations blocked
# 6. Resume and verify normal operations
```

**REMEMBER:** Start with small amounts and gradually increase as confidence builds. Monitor closely for the first 72 hours.

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
