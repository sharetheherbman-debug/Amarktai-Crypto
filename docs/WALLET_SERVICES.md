# Wallet Services Documentation

This document describes the two critical wallet services implemented for the Amarktai Network.

## 1. Reserved Funds Tracking Service

**Location:** `backend/services/reserved_funds_service.py`

### Purpose
Atomic tracking of reserved funds per user + exchange + currency to prevent over-allocation of capital when spawning bots.

### Key Features
- **Atomic Operations:** Uses MongoDB `$inc` for concurrency-safe updates
- **Available Balance Calculation:** `available = balance - reserved`
- **Reserve & Release:** Tracks funds when bots are spawned/stopped
- **Integration:** Used by `bot_spawner.py`, `bot_manager.py`, and `autopilot_production.py`

### API Methods

#### `reserve_funds(user_id, exchange, currency, amount, bot_id=None)`
Atomically reserves funds when a bot is spawned.
- Checks if sufficient available funds exist
- Increments reserved amount using `$inc`
- Logs reservation in ledger collection
- Returns `(success: bool, message: str)`

#### `release_funds(user_id, exchange, currency, amount, bot_id=None)`
Atomically releases funds when a bot is stopped/deleted.
- Decrements reserved amount using `$inc`
- Ensures reserved doesn't go negative
- Logs release in ledger collection
- Returns `(success: bool, message: str)`

#### `get_available_balance(user_id, exchange, currency='ZAR')`
Calculates available balance = balance - reserved.
- Returns `float` (available balance)

#### `check_available_funds(user_id, exchange, currency, required_amount)`
Checks if sufficient funds are available before spawning.
- Returns `(has_sufficient_funds: bool, available_balance: float)`

#### `get_reserved_summary(user_id)`
Gets summary of all reserved funds across exchanges.
- Returns dict with reserved funds by exchange and currency

#### `reconcile_reserved_funds(user_id)`
Reconciles reserved funds with actual active bots.
- Detects discrepancies between expected and actual reserved amounts
- Returns dict with reconciliation results

### Database Schema

**Collection:** `wallet_balances_collection`

Document structure:
```python
{
    "user_id": str,
    "exchange": str,  # 'luno', 'binance', etc.
    "currency": str,  # 'ZAR', 'USDT', etc.
    "balance": float,
    "reserved": float,  # NEW: Reserved funds (atomic tracking)
    "created_at": str (ISO),
    "last_updated": str (ISO)
}
```

**Ledger:** All reserve/release operations are logged in `ledger_collection` for audit trails.

### Integration Points

1. **bot_spawner.py** - Checks available funds before spawning, reserves funds on spawn
2. **bot_manager.py** - Checks available funds before creating, reserves on create, releases on delete
3. **autopilot_production.py** - Indirectly via bot_manager.create_bot()

### Example Usage

```python
from services.reserved_funds_service import reserved_funds_service

# Check if user has enough available funds
has_funds, available = await reserved_funds_service.check_available_funds(
    user_id, 'binance', 'USDT', 1000.0
)

if has_funds:
    # Reserve funds when spawning bot
    success, msg = await reserved_funds_service.reserve_funds(
        user_id, 'binance', 'USDT', 1000.0, bot_id
    )
    
    if success:
        # Create bot...
        pass
else:
    print(f"Insufficient funds: {available} available")

# Release funds when stopping bot
success, msg = await reserved_funds_service.release_funds(
    user_id, 'binance', 'USDT', 1000.0, bot_id
)
```

---

## 2. Balance Sync Service

**Location:** `backend/services/balance_sync_service.py`

### Purpose
Real-time balance fetching from all 7 exchanges using CCXT, storing snapshots, detecting deposits/withdrawals, and emitting realtime events.

### Key Features
- **Multi-Exchange Support:** All 7 platforms (luno, binance, kucoin, bybit, kraken, bitget, gate)
- **Background Sync:** Runs every 5 minutes automatically
- **Snapshot Storage:** Stores balance snapshots in `balance_snapshots_collection`
- **Change Detection:** Detects deposits/withdrawals by comparing snapshots
- **Realtime Events:** Emits `wallet_balance_updated` WebSocket events
- **Error Handling:** Gracefully handles missing API keys and CCXT errors

### API Methods

#### `fetch_exchange_balance(user_id, exchange, api_key, api_secret, passphrase=None)`
Fetches balance from a single exchange.
- Uses CCXT to fetch real balance
- Returns dict with balances or error

#### `fetch_all_balances(user_id)`
Fetches balances from all exchanges for a user.
- Runs fetches concurrently for speed
- Returns dict with all exchange balances
- Gracefully handles errors per exchange

#### `store_balance_snapshot(user_id, balance_data)`
Stores balance snapshot in database.
- Saves to `balance_snapshots_collection`
- Returns `bool` (success)

#### `detect_balance_changes(user_id, current_balances, previous_balances=None)`
Detects deposits/withdrawals by comparing snapshots.
- Compares current vs previous balances
- Returns list of detected changes (deposits/withdrawals)

#### `sync_user_balances(user_id)`
Main orchestration method - syncs balances for a single user.
- Fetches all balances
- Detects changes
- Stores snapshot
- Emits realtime event
- Returns dict with sync results

#### `sync_all_users()`
Syncs balances for all users with API keys.
- Called by background task every 5 minutes
- Returns dict with sync summary

#### `start_background_sync()` / `stop_background_sync()`
Starts/stops the background sync task.

### Database Schema

**Collection:** `balance_snapshots_collection`

Document structure:
```python
{
    "user_id": str,
    "exchanges": {
        "binance": {
            "balances": {
                "USDT": {"free": 100.0, "used": 0.0, "total": 100.0},
                "BTC": {"free": 0.5, "used": 0.0, "total": 0.5}
            },
            "timestamp": str (ISO),
            "status": "success"
        },
        "luno": {
            "error": "API key missing",
            "timestamp": str (ISO),
            "status": "failed"
        }
    },
    "timestamp": str (ISO),
    "successful_syncs": int,
    "failed_syncs": int
}
```

### Integration Points

1. **server.py** - Starts background sync on startup, stops on shutdown
2. **WebSocket Manager** - Emits `wallet_balance_updated` events to connected clients
3. **Frontend** - Receives realtime balance updates via WebSocket

### Realtime Events

Event type: `wallet_balance_updated`

Payload:
```python
{
    "type": "wallet_balance_updated",
    "exchanges": {...},  # Balance data by exchange
    "changes": [        # Detected changes
        {
            "exchange": "binance",
            "currency": "USDT",
            "type": "deposit",
            "amount": 100.0,
            "previous_balance": 1000.0,
            "current_balance": 1100.0
        }
    ],
    "timestamp": str (ISO),
    "message": "💰 Wallet balances updated"
}
```

### Configuration

- **Sync Interval:** 5 minutes (300 seconds) - configurable via `sync_interval` property
- **Supported Platforms:** Imported from `config.platforms.SUPPORTED_PLATFORMS`
- **CCXT IDs:** Mapped via `config.platforms.get_platform_config()`

### Example Usage

```python
from services.balance_sync_service import balance_sync_service

# Manual sync for a single user
result = await balance_sync_service.sync_user_balances(user_id)

if result['success']:
    print(f"Synced {result['successful_syncs']} exchanges")
    print(f"Detected {result['changes_detected']} changes")
    
    for change in result['changes']:
        print(f"{change['type'].upper()}: {change['amount']} {change['currency']} on {change['exchange']}")

# Background sync is started automatically on server startup
# Runs every 5 minutes and syncs all users
```

### Error Handling

The service handles errors gracefully:
- **Missing API Keys:** Skips exchanges without API keys
- **Invalid API Keys:** Logs error and continues with other exchanges
- **CCXT Errors:** Catches and logs, continues with other exchanges
- **Rate Limits:** Small delay between user syncs to avoid rate limits

---

## Testing

### Reserved Funds Service

```python
# Test reserve/release cycle
from services.reserved_funds_service import reserved_funds_service

user_id = "test_user_123"
exchange = "binance"
currency = "USDT"
amount = 1000.0

# Reserve
success, msg = await reserved_funds_service.reserve_funds(
    user_id, exchange, currency, amount
)
assert success, f"Failed to reserve: {msg}"

# Check available
available = await reserved_funds_service.get_available_balance(
    user_id, exchange, currency
)
print(f"Available after reserve: {available}")

# Release
success, msg = await reserved_funds_service.release_funds(
    user_id, exchange, currency, amount
)
assert success, f"Failed to release: {msg}"
```

### Balance Sync Service

```python
# Test manual sync
from services.balance_sync_service import balance_sync_service

result = await balance_sync_service.sync_user_balances(user_id)

print(f"Success: {result['success']}")
print(f"Successful syncs: {result['successful_syncs']}")
print(f"Failed syncs: {result['failed_syncs']}")
print(f"Changes detected: {result['changes_detected']}")

for change in result['changes']:
    print(f"{change['type']}: {change['amount']} {change['currency']} on {change['exchange']}")
```

---

## Monitoring & Maintenance

### Reserved Funds Reconciliation

Run periodic reconciliation to detect discrepancies:

```python
from services.reserved_funds_service import reserved_funds_service

result = await reserved_funds_service.reconcile_reserved_funds(user_id)

if result['has_discrepancies']:
    print(f"⚠️ Found {len(result['discrepancies'])} discrepancies")
    for disc in result['discrepancies']:
        print(f"{disc['exchange']}: expected {disc['expected']}, actual {disc['actual']}")
```

### Balance Sync Logs

Check logs for sync status:

```bash
grep "Balance sync" /var/log/amarktai/backend.log
```

Expected output:
```
2024-01-15 10:00:00 [INFO] balance_sync_service: 🔄 Starting balance sync for 5 users
2024-01-15 10:00:05 [INFO] balance_sync_service: ✅ Balance sync completed: 5 successful, 0 failed
2024-01-15 10:00:05 [INFO] balance_sync_service: 💰 Detected deposit for user abc12345: 100.00 USDT on binance
```

---

## Database Indexes

Recommended indexes for optimal performance:

```python
# Reserved funds tracking
await db.wallet_balances_collection.create_index([
    ("user_id", 1),
    ("exchange", 1),
    ("currency", 1)
], unique=True)

# Balance snapshots
await db.balance_snapshots_collection.create_index([
    ("user_id", 1),
    ("timestamp", -1)
])

# Ledger (for reserved funds audit trail)
await db.ledger_collection.create_index([
    ("user_id", 1),
    ("timestamp", -1)
])
await db.ledger_collection.create_index("type")
```

---

## Security Considerations

1. **API Keys:** Balance sync service handles encrypted API keys (assumes encryption in storage)
2. **Rate Limits:** Services implement delays to avoid exchange rate limits
3. **Atomic Operations:** Reserved funds uses MongoDB atomic operations to prevent race conditions
4. **Audit Trail:** All reserve/release operations logged in ledger collection
5. **Error Isolation:** Errors in one exchange don't affect others

---

## Future Enhancements

1. **Reserved Funds:**
   - Add support for multiple currencies per exchange
   - Implement auto-reconciliation on discrepancies
   - Add alerts for low available funds

2. **Balance Sync:**
   - Add WebSocket streams for real-time balance updates (exchange-native)
   - Implement historical balance tracking and charts
   - Add alerts for large deposits/withdrawals
   - Support for futures/margin balances

---

## Support

For issues or questions:
1. Check logs in `/var/log/amarktai/backend.log`
2. Review database collections for data integrity
3. Run reconciliation tools for reserved funds
4. Contact system administrator
