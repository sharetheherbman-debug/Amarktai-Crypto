# Go-Live Documentation

## Wallet Balance Limitations

### Overview
The Amarktai Network platform provides wallet balance tracking for both paper and live trading modes. However, there are known limitations in the current implementation.

### Known Limitations

#### 1. Multi-Currency Conversion
**Issue:** Live readiness balance calculation uses 1:1 conversion for all currencies.

**Location:** `backend/routes/live_readiness.py:99`

**Details:**
```python
# Current implementation assumes USD or 1:1 conversion
total_balance_usd += data.get('total', 0)
```

**Impact:**
- Balance totals in live readiness checks may be inaccurate for non-USD currencies
- Affects: BTC, ETH, ZAR, and other non-USD balances
- Only impacts the aggregate "total balance" calculation
- Individual currency balances remain accurate

**Mitigation:**
- Individual currency balances are tracked correctly per exchange
- Paper trading uses separate ledger tracking (not affected)
- Live trading validates balances at execution time (accurate)
- This only affects the diagnostic/display value in live readiness checks

**Future Enhancement:**
- Implement proper currency-to-USD conversion using exchange rate feeds
- Add real-time price data integration for accurate conversions
- Estimated effort: 2-4 hours implementation + testing

#### 2. Paper Wallet Balances
**Issue:** Paper wallet balances are tracked separately from live balances.

**Details:**
- Paper mode uses `paper_ledger` collection for balance tracking
- Live mode queries actual exchange balances via CCXT
- No automatic reconciliation between paper and live balances

**Mitigation:**
- This is by design for safety - paper and live are intentionally separate
- Use the "Start Fresh" feature to reset paper balances
- Live balances always reflect actual exchange holdings

#### 3. Balance Refresh Frequency
**Issue:** Exchange balances are cached and refreshed periodically.

**Details:**
- **Paper balances:** Updated immediately on each paper trade
- **Live balances:** Fetched from exchanges every 5 minutes via `balance_sync_service`
- **Manual refresh:** Available via wallet UI "Refresh" button

**Mitigation:**
- For live trading, balances are re-fetched before each trade execution
- Critical operations always use fresh balance data
- UI may show slightly stale values between syncs (max 5 minutes)

**Configuration:**
```python
# In backend/services/balance_sync_service.py
SYNC_INTERVAL = 300  # 5 minutes (default)
```

### Best Practices

#### For Development/Testing
1. Use paper trading mode to avoid balance discrepancies
2. Verify paper balances with `/api/wallet/status` endpoint
3. Reset paper balances regularly with "Start Fresh" feature

#### For Production/Live Trading
1. Verify live API keys are working: `GET /api/live/readiness/{exchange}`
2. Check actual exchange balances match UI before trading
3. Monitor balance sync service logs for errors
4. Use manual refresh button before critical operations

### API Endpoints

#### Check Wallet Status
```bash
curl -X GET http://localhost:8000/api/wallet/status \
  -H "Authorization: ******"
```

Returns:
```json
{
  "paper_balances": { "ZAR": 100000, ... },
  "live_balances": { ... },
  "required_funding": { ... },
  "funding_status": "ok" | "shortfall" | "paper_mode"
}
```

#### Check Live Readiness (includes balance check)
```bash
curl -X GET http://localhost:8000/api/live/readiness \
  -H "Authorization: ******"
```

Returns per-exchange status including balance validation.

### Troubleshooting

#### Issue: Balances show as zero
**Solution:**
1. Check if balance sync service is running: `journalctl -u amarktai-backend | grep "Balance Sync"`
2. Verify API keys are valid: `GET /api/keys/status`
3. Check exchange is reachable (not in maintenance)
4. Manually trigger sync via UI refresh button

#### Issue: Paper and live balances don't match
**This is expected behavior - they are intentionally separate:**
- Paper balances: For simulation/testing
- Live balances: Actual exchange holdings
- No automatic reconciliation between modes

#### Issue: Live readiness shows wrong total balance
**This is a known limitation:**
- Affects only the aggregated total display
- Individual currency balances are accurate
- Does not impact trading operations
- See "Multi-Currency Conversion" limitation above

### Monitoring

Check balance sync health:
```bash
# Backend logs
journalctl -u amarktai-backend | grep -i "balance"

# Should see every 5 minutes:
# "💰 Balance Sync Service started"
# "Balance sync completed for user_id: ..."
```

Check for sync errors:
```bash
journalctl -u amarktai-backend | grep -i "balance.*error"
```

### Environment Variables

No special configuration required. Balance sync starts automatically if:
- `ENABLE_CCXT=true` (default)
- User has valid API keys configured

### Support

If you encounter balance-related issues not covered here:
1. Check backend logs for errors
2. Verify API key connectivity
3. Confirm exchange is operational
4. Report issue with specific exchange + currency details

---

**Last Updated:** 2026-02-19  
**Version:** 1.0  
**Related Files:**
- `backend/routes/wallet_endpoints.py`
- `backend/routes/live_readiness.py`
- `backend/services/balance_sync_service.py`
- `backend/engines/wallet_manager.py`
