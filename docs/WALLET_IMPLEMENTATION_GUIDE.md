# Wallet Architecture Implementation Guide

## Overview
This document provides a detailed implementation roadmap for the production-safe wallet architecture. This is identified as the **BIGGEST BLOCKER** for production deployment.

## Current State

### Existing Files
1. `backend/routes/wallet_endpoints.py` - Basic wallet endpoints
2. `backend/routes/wallet_hub.py` - Balance info & funding plans
3. `backend/routes/wallet_transfers.py` - Transfer operations (partial)
4. `backend/engines/wallet_manager.py` - Wallet management engine (likely exists)
5. `backend/jobs/wallet_balance_monitor.py` - Balance monitoring job

### Environment Variables (Added)
```bash
# Master controls
ENABLE_WITHDRAWALS=0  # Master switch
REQUIRE_2FA_FOR_WITHDRAWALS=1  # TOTP enforcement

# Approval thresholds
REQUIRE_ADMIN_APPROVAL_ABOVE_ZAR=10000

# Transaction limits
WITHDRAWAL_LIMIT_PER_TRANSACTION=50000
WITHDRAWAL_LIMIT_PER_DAY=100000
WITHDRAWAL_LIMIT_PER_MONTH=1000000

# Minimum reserves
MINIMUM_RESERVE_LUNO_ZAR=5000
MINIMUM_RESERVE_PER_EXCHANGE_ZAR=1000

# Emergency controls
EMERGENCY_STOP_ACTIVE=0
```

## Required Implementation

### 1. Transfer State Machine
**File:** `backend/models/transfer_job.py` (new)

```python
from enum import Enum
from datetime import datetime
from pydantic import BaseModel
from typing import Optional

class TransferState(str, Enum):
    REQUESTED = "requested"
    NEEDS_APPROVAL = "needs_approval"
    APPROVED = "approved"
    QUEUED = "queued"
    BROADCAST = "broadcast"
    CONFIRMED = "confirmed"
    FAILED = "failed"
    CANCELLED = "cancelled"

class TransferJob(BaseModel):
    id: str  # UUID
    user_id: str
    idempotency_key: str  # Critical for retry safety
    
    # Transfer details
    from_exchange: str  # "luno" or exchange name
    to_exchange: str  # exchange name or "luno"
    currency: str  # "ZAR", "BTC", "ETH", etc.
    amount: float
    
    # State management
    state: TransferState
    state_history: list  # [{state, timestamp, reason}]
    
    # Approval workflow
    requires_approval: bool
    approved_by: Optional[str] = None
    approved_at: Optional[datetime] = None
    approval_reason: Optional[str] = None
    
    # 2FA
    totp_verified: bool = False
    totp_verified_at: Optional[datetime] = None
    
    # Execution
    withdrawal_id: Optional[str] = None  # From ccxt.withdraw()
    txid: Optional[str] = None  # Blockchain transaction ID
    
    # Timestamps
    requested_at: datetime
    completed_at: Optional[datetime] = None
    
    # Error handling
    error_message: Optional[str] = None
    retry_count: int = 0
    max_retries: int = 3
```

**Database Collection:** `transfer_jobs`

### 2. Immutable Transfer Ledger
**File:** Update `backend/database.py`

```python
# Add to database collections
transfers_ledger_collection = db['transfers_ledger']  # Immutable audit log
```

**Schema for transfers_ledger:**
```json
{
  "id": "uuid",
  "transfer_job_id": "uuid",
  "event_type": "state_transition|approval|error|retry",
  "from_state": "requested",
  "to_state": "approved",
  "timestamp": "2026-02-01T19:00:00Z",
  "actor_id": "user_id or admin_id",
  "reason": "Admin approved transfer",
  "metadata": {}
}
```

### 3. Idempotency Enforcement
**File:** `backend/services/transfer_service.py` (new)

```python
async def create_transfer_request(
    user_id: str,
    from_exchange: str,
    to_exchange: str,
    currency: str,
    amount: float,
    idempotency_key: str,
    totp_code: Optional[str] = None
) -> TransferJob:
    """
    Create transfer request with idempotency
    
    Rules:
    1. Same idempotency_key always returns same result
    2. If transfer exists, return existing transfer
    3. If transfer completed, return completed transfer
    4. Never create duplicate transfers
    """
    
    # Check for existing transfer with this idempotency key
    existing = await db.transfer_jobs_collection.find_one({
        "user_id": user_id,
        "idempotency_key": idempotency_key
    })
    
    if existing:
        return TransferJob(**existing)
    
    # Validate ENABLE_WITHDRAWALS
    if not env_bool("ENABLE_WITHDRAWALS", False):
        raise HTTPException(
            status_code=403,
            detail="Withdrawals are currently disabled"
        )
    
    # Validate 2FA if required
    if env_bool("REQUIRE_2FA_FOR_WITHDRAWALS", True):
        if not totp_code:
            raise HTTPException(
                status_code=403,
                detail="2FA code required for withdrawals"
            )
        
        # Verify TOTP
        if not verify_totp(user_id, totp_code):
            raise HTTPException(
                status_code=403,
                detail="Invalid 2FA code"
            )
    
    # Check transaction limits
    validate_transaction_limits(user_id, amount)
    
    # Check if needs approval
    approval_threshold = float(os.getenv("REQUIRE_ADMIN_APPROVAL_ABOVE_ZAR", 10000))
    needs_approval = amount > approval_threshold
    
    # Create transfer job
    transfer = TransferJob(
        id=str(uuid.uuid4()),
        user_id=user_id,
        idempotency_key=idempotency_key,
        from_exchange=from_exchange,
        to_exchange=to_exchange,
        currency=currency,
        amount=amount,
        state=TransferState.NEEDS_APPROVAL if needs_approval else TransferState.APPROVED,
        state_history=[{
            "state": TransferState.REQUESTED,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "reason": "User initiated transfer"
        }],
        requires_approval=needs_approval,
        totp_verified=True if totp_code else False,
        totp_verified_at=datetime.now(timezone.utc) if totp_code else None,
        requested_at=datetime.now(timezone.utc)
    )
    
    # Save to database
    await db.transfer_jobs_collection.insert_one(transfer.dict())
    
    # Log to immutable ledger
    await log_transfer_event(
        transfer_job_id=transfer.id,
        event_type="state_transition",
        from_state=None,
        to_state=TransferState.REQUESTED,
        actor_id=user_id,
        reason="Transfer requested"
    )
    
    return transfer
```

### 4. Admin Approval Queue
**File:** `backend/routes/admin_endpoints.py` (enhance existing)

Add endpoints:
```python
@router.get("/transfers/pending")
async def get_pending_transfers(admin_id: str = Depends(get_admin_user)):
    """Get all transfers awaiting admin approval"""
    transfers = await db.transfer_jobs_collection.find({
        "state": TransferState.NEEDS_APPROVAL
    }).to_list(100)
    
    return {
        "success": True,
        "transfers": transfers,
        "count": len(transfers)
    }

@router.post("/transfers/{transfer_id}/approve")
async def approve_transfer(
    transfer_id: str,
    reason: str,
    admin_id: str = Depends(get_admin_user)
):
    """Approve a pending transfer"""
    transfer = await db.transfer_jobs_collection.find_one({"id": transfer_id})
    
    if not transfer:
        raise HTTPException(status_code=404, detail="Transfer not found")
    
    if transfer["state"] != TransferState.NEEDS_APPROVAL:
        raise HTTPException(status_code=400, detail="Transfer not in approval state")
    
    # Update transfer
    await db.transfer_jobs_collection.update_one(
        {"id": transfer_id},
        {
            "$set": {
                "state": TransferState.APPROVED,
                "approved_by": admin_id,
                "approved_at": datetime.now(timezone.utc),
                "approval_reason": reason
            },
            "$push": {
                "state_history": {
                    "state": TransferState.APPROVED,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "reason": f"Admin approved: {reason}"
                }
            }
        }
    )
    
    # Log to ledger
    await log_transfer_event(
        transfer_job_id=transfer_id,
        event_type="approval",
        from_state=TransferState.NEEDS_APPROVAL,
        to_state=TransferState.APPROVED,
        actor_id=admin_id,
        reason=reason
    )
    
    # Queue for execution
    await queue_transfer_for_execution(transfer_id)
    
    return {"success": True, "message": "Transfer approved"}

@router.post("/transfers/{transfer_id}/reject")
async def reject_transfer(
    transfer_id: str,
    reason: str,
    admin_id: str = Depends(get_admin_user)
):
    """Reject a pending transfer"""
    # Similar to approve but set state to CANCELLED
    pass
```

### 5. Real Transfer Execution with ccxt.withdraw()
**File:** `backend/jobs/transfer_executor.py` (new)

```python
import ccxt.async_support as ccxt

async def execute_transfer(transfer_id: str):
    """
    Execute approved transfer using ccxt.withdraw()
    
    Flow:
    1. Get transfer job
    2. Verify state is APPROVED
    3. Check reserves
    4. Get withdrawal address (whitelisted)
    5. Execute ccxt.withdraw()
    6. Update transfer job with withdrawal_id
    7. Monitor for confirmation
    """
    
    transfer = await db.transfer_jobs_collection.find_one({"id": transfer_id})
    
    if transfer["state"] != TransferState.APPROVED:
        raise ValueError(f"Transfer {transfer_id} not in approved state")
    
    # Check emergency stop
    if env_bool("EMERGENCY_STOP_ACTIVE", False):
        raise ValueError("Emergency stop active - all transfers blocked")
    
    # Check ENABLE_WITHDRAWALS
    if not env_bool("ENABLE_WITHDRAWALS", False):
        raise ValueError("Withdrawals disabled")
    
    # Check minimum reserves
    await validate_reserves(transfer["from_exchange"], transfer["currency"], transfer["amount"])
    
    # Get whitelisted address
    withdrawal_address = await get_whitelisted_address(
        user_id=transfer["user_id"],
        exchange=transfer["to_exchange"],
        currency=transfer["currency"]
    )
    
    if not withdrawal_address:
        raise ValueError("No whitelisted withdrawal address found")
    
    # Initialize exchange
    exchange = await get_exchange_instance(transfer["from_exchange"], transfer["user_id"])
    
    try:
        # Execute withdrawal
        result = await exchange.withdraw(
            code=transfer["currency"],
            amount=transfer["amount"],
            address=withdrawal_address["address"],
            tag=withdrawal_address.get("tag"),  # For XRP, XLM, etc.
            params=withdrawal_address.get("params", {})
        )
        
        # Update transfer job
        await db.transfer_jobs_collection.update_one(
            {"id": transfer_id},
            {
                "$set": {
                    "state": TransferState.BROADCAST,
                    "withdrawal_id": result["id"],
                    "txid": result.get("txid")
                },
                "$push": {
                    "state_history": {
                        "state": TransferState.BROADCAST,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "reason": f"Withdrawal broadcast: {result['id']}"
                    }
                }
            }
        )
        
        # Log to ledger
        await log_transfer_event(
            transfer_job_id=transfer_id,
            event_type="state_transition",
            from_state=TransferState.APPROVED,
            to_state=TransferState.BROADCAST,
            actor_id="system",
            reason=f"Withdrawal executed: {result['id']}",
            metadata=result
        )
        
        # Start monitoring for confirmation
        await monitor_transfer_confirmation(transfer_id)
        
    except Exception as e:
        # Handle error
        await handle_transfer_error(transfer_id, str(e))
```

### 6. Diagnostics Endpoints
**File:** `backend/routes/diagnostics.py` (enhance existing)

Add endpoints:
```python
@router.get("/wallet-status")
async def get_wallet_status(user_id: str = Depends(get_current_user)):
    """
    Get comprehensive wallet status
    
    Returns:
    - Balance per exchange
    - Pending transfers
    - Reserved funds
    - Available capital
    - Withdrawal limits (remaining)
    """
    pass

@router.get("/transfers")
async def get_transfers(
    user_id: str = Depends(get_current_user),
    limit: int = 50
):
    """
    Get transfer history with state details
    """
    transfers = await db.transfer_jobs_collection.find({
        "user_id": user_id
    }).sort("requested_at", -1).limit(limit).to_list(limit)
    
    return {
        "success": True,
        "transfers": transfers,
        "count": len(transfers)
    }
```

## Implementation Priority

### Phase 1: Foundation (Day 1)
1. ✅ Add environment variables to .env.example
2. Create `TransferJob` model
3. Create `transfer_jobs` collection
4. Create `transfers_ledger` collection
5. Implement idempotency enforcement

### Phase 2: State Machine (Day 2)
1. Implement transfer state transitions
2. Add state history tracking
3. Implement immutable ledger logging
4. Create transfer service with validation

### Phase 3: Approval Workflow (Day 2-3)
1. Implement admin approval queue
2. Add approval/rejection endpoints
3. Integrate with frontend admin panel
4. Add email notifications for pending approvals

### Phase 4: Execution (Day 3-4)
1. Implement ccxt.withdraw() integration
2. Add withdrawal address whitelisting
3. Implement reserve validation
4. Add transfer monitoring
5. Handle confirmation tracking

### Phase 5: Frontend & Testing (Day 4-5)
1. Build wallet UI components
2. Add 2FA input for transfers
3. Create admin approval UI
4. Write comprehensive tests
5. End-to-end testing

## Testing Checklist

### Unit Tests
- [ ] Idempotency prevents duplicates
- [ ] 2FA blocks withdrawals when required
- [ ] Limits enforced (per-transaction, daily, monthly)
- [ ] Emergency stop blocks transfers
- [ ] Reserved funds prevents insufficient balance withdrawals
- [ ] State transitions follow rules
- [ ] Admin approval workflow

### Integration Tests
- [ ] Full transfer flow (request → approval → execution → confirmation)
- [ ] Retry logic works correctly
- [ ] Error handling works
- [ ] Balance sync updates correctly
- [ ] Ledger events recorded correctly

### End-to-End Tests
- [ ] User requests transfer with 2FA
- [ ] Admin approves transfer
- [ ] Transfer executes successfully
- [ ] Balance updates on both exchanges
- [ ] Confirmation tracked correctly

## Security Considerations

1. **Never double-spend** - Idempotency key prevents duplicate transfers
2. **Always require 2FA** - TOTP verification before any withdrawal
3. **Enforce limits** - Per-transaction, daily, monthly caps
4. **Maintain reserves** - Never withdraw below minimum reserves
5. **Admin approval for large amounts** - Configurable threshold
6. **Emergency stop** - Single flag to halt all transfers
7. **Immutable audit trail** - transfers_ledger never modified, only appended
8. **Whitelist addresses only** - Never allow arbitrary withdrawal addresses
9. **Monitor confirmations** - Track until blockchain confirmed
10. **Rate limiting** - Prevent abuse with transfer rate limits

## Success Criteria

✅ **Wallet is production-safe when:**
1. All transfers go through state machine
2. Idempotency prevents duplicates
3. 2FA enforced for all withdrawals
4. Admin approval required for large amounts
5. Limits enforced server-side
6. Emergency stop works instantly
7. Reserved funds protected
8. Real-time balance sync working
9. ccxt.withdraw() integrated
10. Comprehensive tests passing
11. Frontend UI complete
12. Diagnostics endpoints working

---

**Estimated Total Effort:** 3-5 days (1 senior developer)

**Critical Path:** State machine → Approval workflow → Execution → Testing

**Risk:** High complexity, production-critical, requires careful testing
