# Amarktai Crypto - Production Deployment Guide

## Critical Environment Variables

### Required for Production

#### `AMARKTAI_FERNET_KEY` (REQUIRED)
**Purpose:** Encryption key for API keys storage

**How to generate:**
```bash
python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'
```

**Example:**
```
AMARKTAI_FERNET_KEY=kJzX8vR3QmL9pN2wY5sT7uV0xC4bA6dE8fG1hI3jK5lM7nO9qP2rS4tU6vW8xY0z=
```

**⚠️ CRITICAL:** 
- Must be set before starting the application in production
- Must be a valid base64-encoded 32-byte Fernet key
- Never derive from JWT_SECRET (old method, deprecated)
- Keep secret and secure (add to `.gitignore`, use environment management)

#### `JWT_SECRET` (REQUIRED)
**Purpose:** JSON Web Token signing secret

**How to generate:**
```bash
openssl rand -hex 32
```

**Example:**
```
JWT_SECRET=a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6q7r8s9t0u1v2w3x4y5z6
```

### Database Configuration

```bash
MONGO_URL=mongodb://localhost:27017
DB_NAME=amarktai_trading
```

### Feature Flags

```bash
# Environment mode
ENVIRONMENT=production  # or "development"

# Scheduler control
ENABLE_SCHEDULERS=true  # Enable background jobs

# Realtime events
ENABLE_REALTIME=true  # Enable WebSocket/SSE

# Dangerous admin operations (default: false)
ENABLE_DANGEROUS_ADMIN=false  # Set true to enable full system wipes
```

### Trading Configuration

```bash
# System mode
DEFAULT_SYSTEM_MODE=testing  # paper trading mode

# Bot limits
MAX_TOTAL_BOTS=65  # Global bot limit across all exchanges

# Exchange allocation (per exchange)
# luno: 5, binance: 10, kucoin: 10, bybit: 10, kraken: 10, bitget: 10, gate: 10
```

## Migration Guide: JWT_SECRET-derived to AMARKTAI_FERNET_KEY

If you have existing API keys encrypted with the old JWT_SECRET-derived method, follow this migration:

### Step 1: Generate New Key
```bash
python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'
```

### Step 2: Set Environment Variable
Add to your `.env` or environment:
```
AMARKTAI_FERNET_KEY=<generated_key_here>
```

### Step 3: Run Migration (Admin Only)
```bash
# Via API call (requires admin JWT token)
curl -X POST http://localhost:8000/api/admin/migrate-api-keys \
  -H "Authorization: Bearer <admin_token>" \
  -H "Content-Type: application/json"
```

Or via Python:
```python
import requests

response = requests.post(
    "http://localhost:8000/api/admin/migrate-api-keys",
    headers={"Authorization": f"Bearer {admin_token}"}
)
print(response.json())
```

### Step 4: Verify Migration
```bash
# Check API keys still work
curl -X GET http://localhost:8000/api/keys/list \
  -H "Authorization: Bearer <user_token>"
```

## New Endpoints

### Risk Management

```bash
# Get daily loss lock status
GET /api/risk/daily-loss-lock
Authorization: Bearer <token>

# Reset daily loss lock (admin only)
POST /api/risk/daily-loss-lock/reset
Authorization: Bearer <token>
Content-Type: application/json
{
  "confirmation": "RESET_RISK_LOCK"
}

# Resume all bots
POST /api/bots/resume-all
Authorization: Bearer <token>
```

### Dashboard Overview

```bash
# Get consolidated dashboard stats
GET /api/dashboard/overview
Authorization: Bearer <token>

# Returns:
# - total_profit, daily/weekly/monthly profit
# - active/paused/training bot counts
# - system mode flags
# - bodyguard lock status
# - last trade time, win rate
```

### Admin Operations

```bash
# Start Fresh - Wipe paper trading data
POST /api/admin/start-fresh
Authorization: Bearer <admin_token>
Content-Type: application/json
{
  "confirm_phrase": "DELETE_ALL_PAPER_DATA",
  "scope": "paper_only",
  "also_reset_risk_locks": true
}

# Migrate API keys encryption
POST /api/admin/migrate-api-keys
Authorization: Bearer <admin_token>
```

## Smoke Testing

Run comprehensive smoke tests:

```bash
# Set test credentials
export API_BASE_URL=http://localhost:8000
export TEST_EMAIL=test@amarktai.com
export TEST_PASSWORD=testpass123

# Run tests
python scripts/smoke_test_comprehensive.py
```

Tests verify:
- ✅ System status
- ✅ Authentication
- ✅ Platform list (exactly 7 exchanges)
- ✅ API key save/list flow
- ✅ Dashboard overview
- ✅ Bots status
- ✅ Risk management
- ✅ No max_orders_per_day errors

## Supported Exchanges (Exactly 7)

The system supports exactly these 7 exchanges:

1. **Luno** - South African primary (5 bots max)
2. **Binance** - Global (10 bots max)
3. **KuCoin** - Global (10 bots max)
4. **Bybit** - Global derivatives (10 bots max)
5. **Kraken** - US-based (10 bots max)
6. **Bitget** - Global (10 bots max)
7. **Gate.io** - Global (10 bots max)

**Total capacity:** 65 bots

⚠️ **VALR and OVEX are NOT supported** (archived with warnings)

## Deployment Checklist

### Pre-Deployment

- [ ] Generate and set `AMARKTAI_FERNET_KEY`
- [ ] Set `JWT_SECRET`
- [ ] Configure MongoDB connection
- [ ] Set `ENVIRONMENT=production`
- [ ] Review feature flags
- [ ] Set `ENABLE_DANGEROUS_ADMIN=false` (unless needed)

### Initial Deployment

- [ ] Deploy backend with new environment variables
- [ ] Deploy frontend with updated branding
- [ ] Run database migrations (if any)
- [ ] Verify system status: `GET /api/system/status`

### Post-Deployment

- [ ] Run smoke tests
- [ ] Migrate API keys (if upgrading from old version)
- [ ] Verify all 7 exchanges appear in platform list
- [ ] Test bot creation/pause/resume
- [ ] Verify dashboard overview displays correctly
- [ ] Monitor logs for errors

### Verification Commands

```bash
# System status
curl http://localhost:8000/api/system/status

# Platform list (should return 7)
curl http://localhost:8000/api/system/platforms \
  -H "Authorization: Bearer <token>"

# Dashboard overview
curl http://localhost:8000/api/dashboard/overview \
  -H "Authorization: Bearer <token>"
```

## Troubleshooting

### Error: "Missing AMARKTAI_FERNET_KEY in production mode"

**Solution:** Set the environment variable:
```bash
export AMARKTAI_FERNET_KEY=$(python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')
```

### Error: "Invalid FERNET_KEY format"

**Cause:** The key is not a valid base64-encoded 32-byte Fernet key

**Solution:** Regenerate the key:
```bash
python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'
```

### Error: "'max_orders_per_day' KeyError"

**Cause:** Missing exchange limits configuration

**Solution:** This should be fixed in the latest version. Verify `backend/exchange_limits.py` includes all required fields.

### Daily Loss Lock Active

**Resolution:**
1. Admin logs in
2. Navigate to Risk Management
3. Click "Reset Daily Loss Lock" (requires confirmation)
4. Click "Resume All Bots"

Or via API:
```bash
# Reset lock
curl -X POST http://localhost:8000/api/risk/daily-loss-lock/reset \
  -H "Authorization: Bearer <admin_token>" \
  -H "Content-Type: application/json" \
  -d '{"confirmation": "RESET_RISK_LOCK"}'

# Resume bots
curl -X POST http://localhost:8000/api/bots/resume-all \
  -H "Authorization: Bearer <admin_token>"
```

## Security Best Practices

1. **Never commit secrets to Git**
   - Add `.env` to `.gitignore`
   - Use environment variable management (AWS Secrets Manager, etc.)

2. **Rotate keys periodically**
   - Generate new `AMARKTAI_FERNET_KEY`
   - Migrate keys using admin endpoint
   - Update deployment

3. **Restrict admin access**
   - Only set `is_admin=true` for trusted users
   - Monitor admin actions in audit logs
   - Keep `ENABLE_DANGEROUS_ADMIN=false` unless needed

4. **Monitor logs**
   - Watch for authentication failures
   - Monitor API key access patterns
   - Alert on unusual trading activity

## Support

For issues or questions:
- Check logs: `tail -f logs/amarktai.log`
- Run diagnostics: `GET /api/diagnostics`
- Review audit trail: `GET /api/admin/audit/events` (admin only)

---

**© 2026 Amarktai Crypto — Part of the Amarktai Network**
