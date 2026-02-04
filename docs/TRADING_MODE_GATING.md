# Trading Mode Gating & Paper Funds Enforcement

This document describes the implementation of Phase 4A, 4B, and 4C requirements for trading mode gating and realistic paper funds enforcement.

## Overview

The system now enforces strict trading mode gates and realistic paper capital management to prevent unauthorized trading and ensure paper trading accuracy.

### Key Principles

1. **NO FREE MONEY**: All paper trading capital must be explicitly allocated
2. **STRICT MODE GATES**: Trading only executes when paper_trading=true OR live_trading=true
3. **NO BYPASSES**: Autopilot and all execution paths respect safety checks
4. **CLEAR AUDITING**: All gate checks are logged for compliance

## Phase 4A: Paper Trading Mode ✅

### Features

- **Initial Capital Requirement**: Paper bots MUST have initial_capital > 0
- **Paper Wallet Ledger**: Per-bot wallet with reserve/debit/credit system
- **Fund Reservation**: On bot creation, funds are reserved in paper ledger
- **Trade Validation**: Before each trade, wallet balance is checked
- **Realistic Accounting**: Trades debit/credit the paper wallet based on P&L
- **Fee Enforcement**: All fees and slippage are applied to wallet balance
- **Insufficient Funds Blocking**: Trades are blocked if paper wallet has insufficient funds

### Implementation

#### Paper Wallet Ledger Service

Location: `backend/services/paper_wallet_ledger.py`

```python
from services.paper_wallet_ledger import paper_wallet_ledger

# Reserve funds for new bot
success, msg = await paper_wallet_ledger.reserve_funds(user_id, bot_id, amount)

# Check balance
success, balance, msg = await paper_wallet_ledger.get_balance(bot_id)

# Check if bot can afford trade
can_trade, msg = await paper_wallet_ledger.can_trade(bot_id, trade_amount)

# Debit funds (for losses or costs)
success, msg = await paper_wallet_ledger.debit(bot_id, amount, reason)

# Credit funds (for profits)
success, msg = await paper_wallet_ledger.credit(bot_id, amount, reason)

# Release funds when bot is deleted
success, msg = await paper_wallet_ledger.release_funds(bot_id)
```

#### Integration Points

1. **Bot Creation** (`engines/bot_manager.py`):
   - Validates initial_capital > 0
   - Reserves funds in paper wallet ledger
   
2. **Paper Trading Engine** (`paper_trading_engine.py`):
   - Checks paper wallet balance before trade
   - Debits/credits wallet based on trade result
   - Blocks trades with insufficient funds

3. **Bot Deletion** (`engines/bot_manager.py`):
   - Releases paper wallet funds
   - Logs final balance

### Database Schema

Collection: `paper_ledger`

```json
{
  "user_id": "string",
  "bot_id": "string",
  "initial_balance": 1000.0,
  "current_balance": 1050.0,
  "reserved_at": "2024-01-01T00:00:00Z",
  "last_updated": "2024-01-01T12:00:00Z",
  "total_debits": 200.0,
  "total_credits": 250.0,
  "trade_count": 10,
  "status": "active"
}
```

## Phase 4B: Live Trading Mode ✅

### Features

- **API Key Validation**: Live trading requires valid API keys
- **Key Testing**: API keys must be tested successfully before use
- **Balance Check**: Recent balance check required
- **User Confirmation**: Live trading flag must be enabled
- **Autopilot Safety**: Autopilot respects all live trading gates

### Implementation

#### Trading Mode Validator Service

Location: `backend/services/trading_mode_validator.py`

```python
from services.trading_mode_validator import trading_mode_validator

# Validate bot can trade
can_trade, mode, reason = await trading_mode_validator.validate_bot_trading_mode(bot_id, bot_data)

# Validate paper trading
can_trade, mode, reason = await trading_mode_validator.validate_paper_trading(bot_data)

# Validate live trading
can_trade, mode, reason = await trading_mode_validator.validate_live_trading(bot_data)

# Check global gates
trading_allowed, reason = await trading_mode_validator.validate_global_trading_gates()

# Enforce gates (raises exception if not allowed)
await trading_mode_validator.enforce_trading_gates(bot_id, bot_data)
```

#### Live Trading Requirements

For live trading to be allowed, ALL of these must be true:

1. ✅ User's `liveTrading` flag is `true` in system_modes
2. ✅ User's `autopilot` flag is `true`
3. ✅ User's `emergencyStop` flag is `false`
4. ✅ API keys exist for the exchange
5. ✅ API keys have `tested=true` and `valid=true`
6. ✅ API keys have recent `last_balance_check`
7. ✅ Global `LIVE_TRADING` environment variable is `true`

If ANY requirement fails, trading is blocked with clear error message.

### Integration Points

1. **Trading Scheduler** (`trading_scheduler.py`):
   - Validates mode before each trade execution
   - Logs all gate checks
   
2. **Live Trading Gate Routes** (`routes/live_trading_gate.py`):
   - User eligibility checks
   - Live trading approval endpoint
   
3. **Autopilot Engine** (`autopilot_engine.py`):
   - Respects trading mode gates
   - Cannot bypass safety checks

## Phase 4C: Non-negotiable Guardrails ✅

### Features

- **Dual Mode Requirement**: At least ONE mode must be enabled
- **Global Gate Check**: Both PAPER_TRADING=false AND LIVE_TRADING=false blocks ALL trades
- **Scheduler Integration**: Trading scheduler enforces gates on every cycle
- **Autopilot Compliance**: Autopilot cannot bypass any safety checks
- **Clear Error Messages**: Detailed reasons when trading is blocked
- **Audit Logging**: All gate checks are logged for compliance

### Environment Variables

Required environment variables for trading:

```bash
# At least ONE must be true
PAPER_TRADING=1  # Enable paper trading globally
LIVE_TRADING=1   # Enable live trading globally

# Optional flags
ENABLE_TRADING=1      # Master trading switch
ENABLE_AUTOPILOT=1    # Enable autopilot features
```

### Error Messages

When trading is blocked, clear messages are provided:

- ❌ "Paper bots require initial_capital > 0"
- ❌ "Insufficient paper funds: R500.00 < R1000.00"
- ❌ "No API keys configured for binance"
- ❌ "Live trading not enabled for user"
- ❌ "Emergency stop is active"
- ❌ "No trading mode enabled (PAPER_TRADING=false AND LIVE_TRADING=false)"

## Testing

### Unit Tests

Location: `backend/tests/test_trading_mode_gating.py`

Run tests:
```bash
cd backend
pytest tests/test_trading_mode_gating.py -v
```

Test Coverage:
- ✅ Paper wallet fund reservation
- ✅ Balance checks
- ✅ Debit/credit operations
- ✅ Insufficient funds blocking
- ✅ Paper trading validation
- ✅ Live trading validation
- ✅ Emergency stop blocking
- ✅ API key validation
- ✅ Global gate checks
- ✅ Integration tests

### Manual Testing

1. **Test Paper Bot Creation**:
```bash
# Should succeed with capital > 0
curl -X POST http://localhost:8000/api/bots \
  -H "Authorization: Bearer TOKEN" \
  -d '{"name":"Test Bot","exchange":"binance","capital":1000}'

# Should fail with capital = 0
curl -X POST http://localhost:8000/api/bots \
  -H "Authorization: Bearer TOKEN" \
  -d '{"name":"Test Bot","exchange":"binance","capital":0}'
```

2. **Test Trading with Insufficient Funds**:
- Create bot with R500
- Let it execute trades until funds run out
- Verify trades are blocked with clear message

3. **Test Live Trading Gates**:
- Enable live trading without API keys
- Verify trading is blocked
- Add API keys
- Verify trading is allowed

## Monitoring

### Logs

All gate checks are logged for audit purposes:

```
✅ Trading gates passed for bot test_bot_001 in paper mode
⛔ test_bot_002 - Trading blocked: Insufficient paper funds: R100.00 < R500.00
⛔ Trading gate error for test_bot_003: No API keys configured for binance
✅ Paper wallet balance: R1234.56 after trade
```

### Metrics

Track these metrics for monitoring:

- Paper wallet balance by bot
- Total reserved paper funds
- Trades blocked due to insufficient funds
- Gate check failures by reason
- Live trading approval rate

## Security Considerations

### ToS Compliance

The system enforces ToS compliance by:
- ✅ No proxy rotation or IP masking
- ✅ No wash trading patterns
- ✅ Rate limiting on all exchanges
- ✅ Realistic trading patterns only
- ✅ Clear user attribution of all trades

### Capital Safety

Paper capital is protected:
- ✅ Cannot create "free money"
- ✅ All capital must be explicitly allocated
- ✅ Ledger tracks all movements
- ✅ Auditable trail of all transactions

### Live Trading Safety

Live trading requires multiple confirmations:
- ✅ User must explicitly enable live trading
- ✅ API keys must be tested and valid
- ✅ Recent balance check required
- ✅ Emergency stop can instantly halt trading

## Future Enhancements

### Planned Features

- [ ] UI for paper wallet management dashboard
- [ ] User confirmation dialog for live trading
- [ ] Advanced analytics on paper wallet performance
- [ ] Automated paper wallet top-ups
- [ ] Paper-to-live capital migration tools
- [ ] Enhanced audit reporting

### Potential Improvements

- [ ] Paper wallet interest/fees simulation
- [ ] Multi-currency paper wallet support
- [ ] Paper wallet sharing between bots
- [ ] Advanced risk management integration
- [ ] Real-time paper wallet monitoring UI

## Support

For issues or questions:
1. Check logs for detailed error messages
2. Verify environment variables are set correctly
3. Ensure database collections are initialized
4. Review audit logs for gate check history

## Change Log

### Version 1.0.0 (2024-01-XX)
- Initial implementation of Phase 4A, 4B, 4C
- Paper wallet ledger service
- Trading mode validator service
- Integration with bot creation and trading scheduler
- Comprehensive test suite
- Documentation

---

**Note**: This implementation is critical for production safety. Do not disable or bypass these checks unless you fully understand the implications.
