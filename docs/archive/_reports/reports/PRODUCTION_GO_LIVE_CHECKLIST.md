# Production Go-Live Checklist

This checklist ensures the Amarktai Network Adaptive Paper Trading System is ready for production deployment.

## Pre-Deployment Configuration

### 1. Environment Variables ⚙️

All environment variables must be set in `.env` file:

#### Database & Security (Required)
- [ ] `MONGO_URL` - MongoDB connection string
- [ ] `JWT_SECRET` - Generate with: `openssl rand -hex 32`
- [ ] `ADMIN_PASSWORD` - Admin access password

#### AI Integration (Required for AI features)
- [ ] `OPENAI_API_KEY` - OpenAI API key for GPT-4

#### SMTP Email Configuration (Optional but Recommended)
- [ ] `SMTP_HOST` - SMTP server (default: smtp.gmail.com)
- [ ] `SMTP_PORT` - SMTP port (default: 587)
- [ ] `SMTP_USER` - SMTP username/email
- [ ] `SMTP_PASSWORD` - SMTP password or app-specific password
- [ ] `SMTP_FROM_EMAIL` - From email address
- [ ] `DAILY_REPORT_TIME` - Time for daily reports (default: "08:00" UTC)

#### Trading Limits Configuration
- [ ] `MAX_TRADES_PER_BOT_DAILY` - Bot daily trade limit (default: 50)
- [ ] `MAX_TRADES_PER_USER_DAILY` - User daily trade limit (default: 500)
- [ ] `BURST_LIMIT_ORDERS_PER_EXCHANGE` - Burst limit (default: 10)
- [ ] `BURST_LIMIT_WINDOW_SECONDS` - Burst window (default: 10)

#### Circuit Breaker Thresholds
- [ ] `MAX_DRAWDOWN_PERCENT` - Max drawdown % (default: 0.20 = 20%)
- [ ] `MAX_DAILY_LOSS_PERCENT` - Max daily loss % (default: 0.10 = 10%)
- [ ] `MAX_CONSECUTIVE_LOSSES` - Max consecutive losses (default: 5)
- [ ] `MAX_ERRORS_PER_HOUR` - Max errors per hour (default: 10)

#### Fee Coverage Configuration
- [ ] `MIN_EDGE_BPS` - Minimum edge in basis points (default: 10.0)
- [ ] `SAFETY_MARGIN_BPS` - Safety margin (default: 5.0)
- [ ] `SLIPPAGE_BUFFER_BPS` - Slippage buffer (default: 10.0)

#### Daily Reinvestment Configuration
- [ ] `REINVEST_THRESHOLD` - Minimum profit to reinvest (default: 500)
- [ ] `REINVEST_TOP_N` - Number of top bots to allocate to (default: 3)
- [ ] `REINVEST_PERCENTAGE` - Percentage of profits to reinvest (default: 80)
- [ ] `DAILY_REINVEST_TIME` - Time for reinvestment (default: "02:00" UTC)

### 2. Database Setup 🗄️

- [ ] MongoDB 4.4+ is installed and running
- [ ] Database name is configured in `MONGO_URL`
- [ ] Database is accessible from application server
- [ ] Required collections will be auto-created:
  - `users`, `bots`, `trades`, `api_keys`
  - `fills_ledger` (immutable trade records)
  - `ledger_events` (funding, allocations)
  - `pending_orders` (idempotency tracking)
  - `circuit_breaker_state` (trip history)
  - `system_modes`, `alerts`, `chat_messages`

### 3. System Dependencies 📦

- [ ] Python 3.11+ installed
- [ ] Node.js 18+ installed (for frontend, if applicable)
- [ ] All Python dependencies installed: `pip install -r backend/requirements.txt`
- [ ] Virtual environment activated

### 4. SSL/TLS Configuration 🔒

- [ ] SSL certificate obtained (Let's Encrypt recommended)
- [ ] Certificate configured in nginx or reverse proxy
- [ ] HTTPS enforced for production traffic
- [ ] HTTP to HTTPS redirect configured

### 5. Firewall & Network 🔥

- [ ] Port 8000 (backend API) is accessible
- [ ] Port 80 (HTTP) and 443 (HTTPS) open
- [ ] MongoDB port (27017) restricted to localhost only
- [ ] SSH port (22) accessible for management

## System Verification

### 6. Core Functionality Tests ✅

Run these tests before going live:

```bash
# Run all verification tests
cd backend
python -m pytest tests/test_adaptive_trading_verification.py -v

# Run specific test suites
python -m pytest tests/test_ledger_phase1.py -v
python -m pytest tests/test_order_pipeline_phase2.py -v
python -m pytest tests/test_bot_lifecycle.py -v
```

### 7. Endpoint Health Checks 🏥

Verify all critical endpoints respond:

```bash
# Set your API URL
export API_URL="http://localhost:8000"

# Health check
curl $API_URL/api/health/ping

# Portfolio endpoints
curl -H "Authorization: Bearer $TOKEN" $API_URL/api/portfolio/summary
curl -H "Authorization: Bearer $TOKEN" $API_URL/api/profits?period=daily
curl -H "Authorization: Bearer $TOKEN" $API_URL/api/countdown/status

# Ledger endpoints
curl -H "Authorization: Bearer $TOKEN" $API_URL/api/ledger/reconcile
curl -H "Authorization: Bearer $TOKEN" $API_URL/api/ledger/verify-integrity

# Limits endpoints
curl -H "Authorization: Bearer $TOKEN" $API_URL/api/limits/config
curl -H "Authorization: Bearer $TOKEN" $API_URL/api/limits/usage

# Circuit breaker
curl -H "Authorization: Bearer $TOKEN" $API_URL/api/circuit-breaker/status

# Reports
curl -X POST -H "Authorization: Bearer $TOKEN" $API_URL/api/reports/daily/send-test
```

### 8. Ledger Integrity Verification 📊

- [ ] Run ledger reconciliation for existing users
- [ ] Verify integrity checks pass
- [ ] Check equity calculations match expected values
- [ ] Confirm unrealized PnL uses current mark prices
- [ ] Validate FIFO matching produces correct realized PnL

### 9. Order Pipeline Testing 🚧

- [ ] Submit test order through 4-gate pipeline
- [ ] Verify idempotency prevents duplicates
- [ ] Confirm fee coverage rejects unprofitable trades
- [ ] Test trade limiter enforces daily limits
- [ ] Trigger circuit breaker and verify auto-pause

### 10. Bot Lifecycle Verification 🤖

- [ ] Create test bot
- [ ] Start bot and verify status changes
- [ ] Pause bot and verify trading stops
- [ ] Resume bot and verify trading resumes
- [ ] Stop bot permanently
- [ ] Verify all state changes persist in database

### 11. Daily Reinvestment System 💰

- [ ] Check reinvestment scheduler is running
- [ ] Verify configuration via `/api/admin/reinvest/status`
- [ ] Manually trigger reinvestment cycle
- [ ] Confirm allocations recorded in `ledger_events`
- [ ] Verify top performers receive allocations
- [ ] Check daily reports are sent

### 12. AI Command Router 🧠

- [ ] Test AI chat with simple commands
- [ ] Verify bot lifecycle commands work
- [ ] Test emergency stop requires confirmation
- [ ] Confirm portfolio summary displays correctly
- [ ] Verify admin-only commands are restricted

## Security Hardening

### 13. Authentication & Authorization 🔐

- [ ] JWT secret is strong (32+ characters, randomly generated)
- [ ] Password hashing uses bcrypt
- [ ] Admin endpoints require proper authorization
- [ ] API key encryption is enabled
- [ ] Session timeouts are configured

### 14. Rate Limiting & Protection 🛡️

- [ ] Burst protection is active (10 orders/10 seconds)
- [ ] Daily trade limits are enforced
- [ ] Circuit breaker thresholds are appropriate
- [ ] Fee coverage checks are active
- [ ] Idempotency prevents duplicate orders

### 15. Data Protection 📁

- [ ] Database backups are configured
- [ ] Backup restoration tested
- [ ] Sensitive data is encrypted at rest
- [ ] API keys are never logged
- [ ] PII is handled according to regulations

## Monitoring & Alerting

### 16. System Monitoring 👀

- [ ] Application logs are accessible
- [ ] Log rotation is configured
- [ ] Error rates are monitored
- [ ] Performance metrics are tracked
- [ ] Disk space alerts are configured

### 17. Trading Monitoring 📈

- [ ] Daily reports are being sent
- [ ] Circuit breaker trips are logged
- [ ] Reconciliation reports are reviewed
- [ ] Trade execution rates are monitored
- [ ] Profit/loss tracking is accurate

### 18. Alerting Configuration 🚨

- [ ] Email alerts for circuit breaker trips
- [ ] Reconciliation discrepancy alerts
- [ ] High error rate notifications
- [ ] System health degradation alerts
- [ ] Daily report delivery confirmation

## Documentation

### 19. API Documentation 📚

- [ ] All endpoints documented in README
- [ ] Request/response examples provided
- [ ] Authentication requirements specified
- [ ] Rate limits documented
- [ ] Error codes explained

### 20. Operations Manual 📖

- [ ] Deployment procedure documented
- [ ] Common troubleshooting steps provided
- [ ] Emergency procedures outlined
- [ ] Contact information updated
- [ ] Rollback procedure documented

## Post-Deployment

### 21. Smoke Tests 💨

Run immediately after deployment:

```bash
# Quick smoke test
./deployment/smoke_test.sh

# Verify all services are running
systemctl status amarktai-api
systemctl status mongodb
systemctl status nginx

# Check logs for errors
journalctl -u amarktai-api -n 100
tail -f /var/log/nginx/error.log
```

### 22. Initial Monitoring 📊

First 24 hours after deployment:

- [ ] Monitor error rates (should be < 1%)
- [ ] Verify trades are executing
- [ ] Check daily reinvestment runs successfully
- [ ] Confirm daily reports are sent
- [ ] Review circuit breaker activity
- [ ] Validate ledger reconciliation
- [ ] Monitor system resource usage

### 23. User Acceptance 👥

- [ ] Create test user account
- [ ] Create and run test bots
- [ ] Execute sample trades
- [ ] Verify portfolio calculations
- [ ] Test AI chat functionality
- [ ] Confirm email notifications work
- [ ] Validate mobile responsiveness

## Sign-Off

- [ ] Development team sign-off
- [ ] QA team sign-off
- [ ] Operations team sign-off
- [ ] Security review complete
- [ ] Product owner approval

---

## Emergency Contacts

- **On-Call Engineer**: [Contact Info]
- **DevOps Lead**: [Contact Info]
- **Product Owner**: [Contact Info]

## Rollback Procedure

If critical issues are discovered:

1. Stop the application: `systemctl stop amarktai-api`
2. Restore database backup: `mongorestore --drop /path/to/backup`
3. Revert code: `git checkout <previous-commit>`
4. Restart application: `systemctl start amarktai-api`
5. Notify stakeholders

## Success Criteria

✅ All checklist items completed
✅ No critical errors in first 24 hours
✅ Daily reinvestment executes successfully
✅ Circuit breakers function correctly
✅ Ledger reconciliation shows < 1% discrepancy
✅ User acceptance tests pass

---

**Go-Live Date**: _____________
**Deployment By**: _____________
**Approved By**: _____________
