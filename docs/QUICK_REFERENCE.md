# Production Audit: Quick Reference Guide

## 📋 Installation Checklist

```
┌─────────────────────────────────────────────────────┐
│  PRODUCTION-READY INSTALLATION                      │
└─────────────────────────────────────────────────────┘

✅ Step 1: Clone Repository
   sudo mkdir -p /var/amarktai
   cd /var/amarktai && sudo git clone <repo-url> app

✅ Step 2: Run Installation Script
   cd app/deployment && sudo ./install.sh

✅ Step 3: Configure Environment
   sudo nano backend/.env
   Required: JWT_SECRET, ENCRYPTION_KEY, MONGO_URI

✅ Step 4: Install Nginx SPA Config
   sudo cp deployment/nginx/amarktai-spa.conf /etc/nginx/sites-available/amarktai
   sudo ln -s /etc/nginx/sites-available/amarktai /etc/nginx/sites-enabled/
   sudo nginx -t && sudo systemctl reload nginx

✅ Step 5: Run Go-Live Audit
   ./scripts/go_live_audit.sh
   Expected: Exit code 0 = READY! 🚀
```

---

## 🔧 Quick Fixes

### SPA Routes 404
```bash
# Verify nginx config
sudo nginx -t

# Check site enabled
ls -l /etc/nginx/sites-enabled/amarktai

# Test routing
./scripts/test_spa_routing.sh
```

### API Keys 422 Error
```bash
# Now accepts multiple formats:
✅ provider OR exchange
✅ api_key OR apiKey OR key
✅ api_secret OR apiSecret OR secret
```

### Deleted Bots Still Show
```bash
# Backend now filters deleted bots
# GET /api/bots excludes status='deleted'
# Frontend auto-refreshes
```

---

## 🧪 Testing

```bash
# Run all tests
pytest tests/ -v

# Test specific areas
pytest tests/test_api_keys.py -v
pytest tests/test_bots_e2e.py -v
pytest tests/test_paper_trading.py -v

# Validate SPA routing
./scripts/test_spa_routing.sh

# Verify OpenAPI
./scripts/verify_openapi.sh
```

---

## 📊 Architecture Overview

```
┌──────────────────────────────────────────────────────┐
│                    NGINX (Port 80)                    │
│  ┌────────────────────────────────────────────────┐  │
│  │  SPA Routing: try_files $uri /index.html      │  │
│  │  Deep Links: /, /dashboard, /login, /bots     │  │
│  └────────────────────────────────────────────────┘  │
└───────────────────┬──────────────────────────────────┘
                    │
                    ├─► /api/* ──► Backend (Port 8000)
                    │              ├─► API Keys (backward compat)
                    │              ├─► Bots (filter deleted)
                    │              ├─► Realtime (SSE/WebSocket)
                    │              ├─► AI Chat (memory + greeting)
                    │              └─► Paper Trading (ledger)
                    │
                    └─► /* ──────► index.html (React SPA)
```

---

## 🔐 API Key Formats (All Supported)

```javascript
// ✅ Canonical format
{
  "provider": "binance",
  "api_key": "key123",
  "api_secret": "secret456"
}

// ✅ Legacy format (exchange field)
{
  "exchange": "binance",
  "api_key": "key123",
  "api_secret": "secret456"
}

// ✅ CamelCase format
{
  "provider": "binance",
  "apiKey": "key123",
  "apiSecret": "secret456"
}

// ✅ Short form
{
  "provider": "binance",
  "key": "key123",
  "secret": "secret456"
}
```

---

## 📈 Realtime Events

```
SSE Endpoint: /api/realtime/events

Events Published:
├─► heartbeat (5s interval)
├─► overview_update (15s interval)
│   └─► active_bots, total_profit, capital
├─► bot_update (on change)
│   └─► bot_created, bot_deleted, status_changed
├─► trade_update (on new trade)
│   └─► recent_trades, profit
└─► wallet_update (on balance change)
    └─► balances, transfers
```

---

## 🤖 AI Chat Commands

```
User: "show admin"
  └─► Response: Password gate prompt
      Action: show_admin_panel
      Requires: admin password

User: "hello" (on first login)
  └─► Response: Greeting + daily report
      Includes: yesterday's performance
               bot status, profit summary

User: "emergency stop"
  └─► Response: Confirmation required
      Action: stop_all_bots
      Requires: user confirmation
```

---

## 💰 Paper Trading Ledger

```javascript
// Every trade includes:
{
  "price_source": "LUNO_PUBLIC",    // Data source
  "mid_price": 50000.00,            // Mid-market price
  "spread": 0.15,                   // Bid-ask spread %
  "slippage_bps": 15,               // Slippage (basis points)
  "fee_rate": 0.001,                // 0.1% fee rate
  "fee_amount": 50.00,              // Actual fee charged
  "gross_pnl": 1000.00,             // Profit before fees
  "net_pnl": 899.00,                // Profit after fees
  "trading_mode": "paper"           // Marked as paper
}
```

**Fee Rates:**
- Binance: 0.1% maker/taker
- KuCoin: 0.1% maker/taker
- Luno: 0% maker, 0.1% taker

---

## 🎯 Go-Live Audit Results

```
Expected Output:
===============================================
   AUDIT SUMMARY
===============================================
Total Tests: 35
Passed: ✓ 35
Failed: ✗ 0
===============================================

✓ Backend tests passing
✓ Frontend built successfully
✓ SPA routing config created
✓ Environment configured
✓ All tests passing

RESULT: READY FOR GO-LIVE! 🚀
```

---

## 📁 New Files Added

```
deployment/nginx/
  └─► amarktai-spa.conf         # Production nginx config

scripts/
  ├─► test_spa_routing.sh       # Validate deep links
  ├─► verify_openapi.sh         # Check OpenAPI endpoint
  └─► go_live_audit.sh          # Complete audit script

tests/
  ├─► test_api_keys.py          # API contract tests
  ├─► test_bots_e2e.py          # Bot deletion E2E
  ├─► test_overview_realtime.py # Dashboard realtime
  ├─► test_chat.py              # AI chat tests
  └─► test_paper_trading.py     # Math validation

PRODUCTION_AUDIT_SUMMARY.md    # Complete documentation
```

---

## 🚨 Critical Changes

1. **Nginx Config**: SPA routing MUST be installed for deep links to work
2. **API Keys**: Now accept multiple formats (no breaking changes)
3. **Bot Deletion**: Soft-delete only, bots filtered from list
4. **Realtime**: WebSocket/SSE both working, dashboard shows real data
5. **Paper Trading**: Every trade has complete ledger for auditing

---

## 📞 Support

**Check Logs:**
```bash
sudo journalctl -u amarktai-api.service -f
```

**Verify Service:**
```bash
sudo systemctl status amarktai-api.service
```

**Test API:**
```bash
curl http://127.0.0.1:8000/api/health/ping
```

**Docs:**
- See `PRODUCTION_AUDIT_SUMMARY.md` for complete guide
- See `README.md` for troubleshooting section
- See test files for API usage examples

---

## ✅ Success Criteria Checklist

```
Production Ready Checklist:
├─ [✓] SPA deep links work (no 404s)
├─ [✓] API keys save/test without errors
├─ [✓] Bots delete correctly
├─ [✓] Overview shows real data
├─ [✓] Realtime updates working
├─ [✓] AI chat has memory
├─ [✓] Login greeting implemented
├─ [✓] Paper trading math correct
├─ [✓] Comprehensive tests pass
├─ [✓] Go-live audit exits 0
└─ [✓] All documentation complete

STATUS: READY FOR PRODUCTION! 🚀
```
