# Deployment Notes - System Hardening Update

## Overview
This update implements comprehensive system hardening with real-time trading capabilities, single source of truth metrics, and improved API key management.

## New Features

### 1. Test Infrastructure (Phase 0)
- **Test Runner**: `scripts/test.sh` - Prevents third-party pytest plugin auto-loading
- **Pytest Config**: `pytest.ini` - Comprehensive test configuration
- **Usage**: `./scripts/test.sh` or `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest`

### 2. Smoke Test Improvements (Phase 1)
- **Environment Variables**:
  - `SMOKE_BASE_URL`: Base URL for API (default: http://localhost:8000)
  - `SMOKE_EMAIL`: Email for authentication (default: test@amarktai.com)
  - `SMOKE_PASSWORD`: Password for authentication (default: test123)
- **Graceful Degradation**: Continues public tests if auth fails

### 3. Single Source of Truth Metrics (Phase 2)
- **New Service**: `backend/services/overview_service.py`
- **Endpoint**: `GET /api/overview/snapshot`
- **Returns**:
  - Profit metrics (total, today, gross PnL, net PnL)
  - Fee metrics (total fees, today fees)
  - Trade metrics (count, win rate)
  - Bot metrics by state (active, paused, training, quarantine)
  - Capital metrics (equity, required capital by platform)
  - Market prices (BTC/ZAR, ETH/ZAR, XRP/ZAR)
  - Daily loss lock state
  - Trading mode flags

### 4. Profit + Fees Normalization (Phase 3)
- **Canonical Fields**:
  - Profit: `net_pnl` (primary) → fallback `profit_loss`
  - Fees: `fee_amount` (primary) → fallback `fees` → fallback `fee`
- **Fixed**: Analytics endpoints now show correct fees (previously 0.00)
- **Updated Files**: `backend/routes/analytics_api.py`

### 5. Live Market Prices (Phase 4)
- **New Endpoint**: `GET /api/market/prices`
- **New File**: `backend/routes/market_api.py`
- **Features**:
  - BTC/ZAR, ETH/ZAR, XRP/ZAR prices
  - % change, timestamp, source
  - Luno authenticated/public ticker support
  - Auto-updates via realtime events

### 6. API Keys Management (Phase 5)
- **Verified Endpoints**:
  - `GET /api/keys/status` - Get key configuration status
  - `POST /api/keys/save` - Save encrypted keys
  - `POST /api/keys/test` - Test key validity
- **Supported**:
  - 7 Exchanges: luno, binance, kucoin, bybit, kraken, bitget, gate
  - 3 AI Providers: openai, fetchai, flokx
- **Statuses**: not_configured, configured_untested, configured_valid, configured_invalid

### 7. Real-Time System (Phase 6)
- **New Events** (9 total):
  - `trade_inserted` - New trade executed
  - `overview_updated` - Metrics changed
  - `bot_state_changed` - Bot status changed
  - `lock_triggered` - Daily loss lock activated
  - `lock_reset` - Daily loss lock reset
  - `wallet_updated` - Wallet balance changed
  - `price_update` - Market prices updated
  - `scheduler_heartbeat` - System heartbeat
  - `bot_spawned` - New bot created
- **Updated File**: `backend/realtime_events.py`

### 8. Countdown System (Phase 7)
- **New Endpoint**: `GET /api/metrics/trade-cadence`
- **New File**: `backend/routes/metrics_api.py`
- **Features**:
  - Requires >= 30 trades to start
  - Rolling average trade interval
  - ETA to next trade
  - Human-readable display

### 9. Wallet Required Capital (Phase 8)
- **New Endpoint**: `GET /api/wallet/required-capital`
- **Returns**:
  - Total required capital across all bots
  - Per-platform capital requirements
  - Based on initial_capital field

### 10. Bot Creation Contract (Phase 9)
- **Validation**: Rejects bots without valid platform
- **Valid Platforms**: luno, binance, kucoin, bybit, kraken, bitget, gate
- **Migration**: `backend/migrations/quarantine_invalid_platforms.py`
  - Quarantines existing bots with invalid platforms
  - Sets pause_reason=INVALID_PLATFORM
  - **Run**: `python backend/migrations/quarantine_invalid_platforms.py`

### 11. Bodyguard + Daily Loss (Phase 10)
- **Daily Loss**: Now uses REALIZED net PnL only (closed trades)
- **Paper Mode**: 
  - Never global permanent pause
  - Quarantines only offending bots
  - Auto-cooldown and resume
- **New Endpoint**: `POST /api/admin/reset-risk-lock` (idempotent)

### 12. Admin UI (Phase 11)
- **Verified**: All admin components use `color: 'var(--text)'` for white text
- **No Changes Needed**: Layout already correct

## Migration Steps

### 1. Before Deployment
```bash
# Backup database
mongodump --db amarktai_trading --out /backup/$(date +%Y%m%d)

# Pull latest code
git pull origin main

# Install dependencies (if needed)
cd backend
pip install -r requirements.txt
```

### 2. Run Migration
```bash
# Quarantine bots with invalid platforms
cd /home/runner/work/Amarktai-Network---Deployment/Amarktai-Network---Deployment
python backend/migrations/quarantine_invalid_platforms.py
```

### 3. Restart Services
```bash
# Restart backend
sudo systemctl restart amarktai-api

# Check status
sudo systemctl status amarktai-api

# View logs
sudo journalctl -u amarktai-api -f
```

### 4. Verify Deployment
```bash
# Run smoke tests
export SMOKE_BASE_URL=http://localhost:8000
export SMOKE_EMAIL=admin@amarktai.com
export SMOKE_PASSWORD=your-password
./scripts/smoke_test.py

# Or with defaults
./scripts/smoke_test.py http://localhost:8000 admin@amarktai.com your-password

# Run full test suite
./scripts/test.sh
```

## Testing

### Run All Tests
```bash
./scripts/test.sh
```

### Run Specific Test File
```bash
./scripts/test.sh tests/test_phases_3_11.py
```

### Run Smoke Tests
```bash
# Local
./scripts/smoke_test.py

# Production
./scripts/smoke_test.py https://your-domain.com admin@email.com password
```

## API Changes

### New Endpoints
1. `GET /api/overview/snapshot` - Complete metrics snapshot
2. `GET /api/market/prices` - Live market prices
3. `GET /api/metrics/trade-cadence` - Trade countdown
4. `GET /api/wallet/required-capital` - Required capital
5. `POST /api/admin/reset-risk-lock` - Reset daily loss lock

### Updated Endpoints
1. All analytics endpoints now use canonical fields (net_pnl, fee_amount)
2. Overview snapshot includes all new metrics

## Breaking Changes

### None
All changes are backward compatible. The canonical field normalization uses fallbacks to maintain compatibility with existing data.

## Performance Considerations

1. **Overview Snapshot**: Cached for 30 seconds to reduce DB load
2. **Market Prices**: Fetched from Luno with fallback to cached values
3. **Trade Cadence**: Only computed when >= 30 trades exist
4. **Realtime Events**: Use debouncing to prevent event spam

## Security

- **CodeQL Scan**: 0 vulnerabilities found
- **API Keys**: Encrypted with Fernet (per-user)
- **Admin Endpoints**: Require authentication
- **Migration**: Safe, idempotent operation

## Rollback Plan

If issues occur:

```bash
# Restore database
mongorestore --db amarktai_trading /backup/YYYYMMDD/amarktai_trading

# Revert code
git checkout <previous-commit-hash>

# Restart services
sudo systemctl restart amarktai-api
```

## Support

For issues or questions:
1. Check logs: `sudo journalctl -u amarktai-api -f`
2. Run smoke tests: `./scripts/smoke_test.py`
3. Check health: `curl http://localhost:8000/api/health/ping`

## Verification Checklist

- [ ] Database backup completed
- [ ] Migration ran successfully
- [ ] Backend service restarted
- [ ] Smoke tests pass
- [ ] Full test suite passes
- [ ] Overview snapshot returns all metrics
- [ ] Market prices update
- [ ] Fees display correctly
- [ ] Trade cadence works (if >= 30 trades)
- [ ] Required capital shows correct values
- [ ] Admin can reset risk lock
- [ ] Realtime events emit correctly

## Known Issues

None. All phases tested and verified.

## Future Enhancements

1. **Phase 4**: Enhance Luno price fetching with better caching
2. **Phase 6**: Add WebSocket reconnection metrics
3. **Phase 7**: Add countdown notifications
4. **Phase 8**: Add capital allocation recommendations

## Version

- **Release**: System Hardening v2.0
- **Date**: 2026-02-06
- **Branch**: copilot/test-stability-fixes
- **Commits**: 13 commits (00d0f16)
