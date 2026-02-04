# Deployment Checklist

## Required Environment Variables

### Core System
- `MONGO_URL` - MongoDB connection string (required)
- `DB_NAME` - Database name (default: `amarktai_trading`)
- `JWT_SECRET` - JWT signing secret (MUST change from default in production)
- `ENCRYPTION_KEY` - Fernet encryption key for API keys (required)
- `AMARKTAI_FERNET_KEY` - Alternative encryption key (optional, takes priority)
- `FERNET_KEY` - Legacy encryption key (optional)

### Email Configuration (Required for Reports & Welcome Emails)
- `SMTP_HOST` - SMTP server (default: `smtp.gmail.com`)
- `SMTP_PORT` - SMTP port (default: `587`)
- `SMTP_USER` - SMTP username/email (required for emails)
- `SMTP_PASSWORD` - SMTP password (required for emails)
- `FROM_EMAIL` - From email address (optional, defaults to SMTP_USER)
- `FROM_NAME` - From name (default: `Amarktai Network`)

### Email Features
- `ENABLE_EMAIL_REPORTS` - Enable daily email reports (default: `true`)
- `REPORT_TIMES` - Report times in HH:MM format, comma-separated (default: `08:00,18:00`)
  - Times are in Africa/Johannesburg timezone

### AI Configuration
- `OPENAI_API_KEY` - OpenAI API key for AI features (required for AI)
- `AI_MODEL_SYSTEM_BRAIN` - Model for system brain (default: `gpt-4o`)
- `AI_MODEL_TRADE_DECISION` - Model for trade decisions (default: `gpt-4o`)
- `AI_MODEL_REPORTING` - Model for reports (default: `gpt-4`)
- `AI_MODEL_CHATOPS` - Model for chat (default: `gpt-4o`)

### Trading Feature Flags
- `ENABLE_TRADING` - Enable trading system (default: `true`)
- `ENABLE_PAPER_TRADING` - Enable paper trading (default: `true`)
- `ENABLE_LIVE_TRADING` - Enable live trading (default: `false` - USE WITH CAUTION)
- `ENABLE_AUTOPILOT` - Enable autopilot bot management (default: `true`)
- `ENABLE_CCXT` - Enable CCXT price feeds (default: `true`)

### System Feature Flags
- `ENABLE_BODYGUARD` - Enable AI bodyguard protection (default: `true`)
- `ENABLE_REALTIME` - Enable real-time WebSocket/SSE (default: `true`)
- `ENABLE_SELF_LEARNING` - Enable self-learning (default: `true`)
- `ENABLE_SELF_HEALING` - Enable self-healing (default: `true`)
- `ENABLE_SCHEDULERS` - Enable background schedulers (default: `true`)

### Bot Spawning & Reinvestment
- `BOT_SPAWN_PROFIT_ZAR` - Per-exchange profit required to spawn new bot (default: `1000`)
- `NEW_BOT_SEED_CAPITAL_ZAR` - Capital allocated to new bots (default: `500`)
- `REINVEST_THRESHOLD_ZAR` - Profit threshold for reinvestment (default: `300`)
- `MAX_TOTAL_BOTS` - Maximum total bots across all exchanges (default: `65`)
  - MUST equal sum of per-exchange bot allocations (5+10+10+10+10+10+10)
- `TOP_PERFORMERS_COUNT` - Number of top performers for reinvestment (default: `3`)
- `ENABLE_PER_EXCHANGE_BOT_SPAWN` - Enable per-exchange spawn gating (default: `true`)
- `ENABLE_OVERALL_PROFIT_THRESHOLD` - Enable global profit threshold (default: `false`)
- `OVERALL_PROFIT_THRESHOLD_ZAR` - Global profit threshold if enabled (default: `5000`)

### Trading Limits
- `MAX_TRADES_PER_BOT_PER_DAY` - Max trades per bot per day (default: `1000`)
- `MAX_TRADES_PER_USER_PER_DAY` - Max trades per user per day (default: `3000`)
- `PAPER_TRAINING_DAYS` - Days required in paper mode before live promotion (default: `7`)
- `LIVE_MIN_TRAINING_HOURS` - Hours new bots must train before trading (default: `24`)

### Risk Management
- `MAX_DAILY_LOSS_PERCENT` - Max daily loss percentage (default: `0.15` = 15%)
- `MAX_DRAWDOWN_PERCENT` - Max drawdown percentage (default: `0.25` = 25%)
- `MAX_ERRORS_PER_HOUR` - Error budget for self-healing (default: `20`)

### Wallet Transfer Security
- `REQUIRE_EMAIL_CONFIRMATION` - Require email confirmation for withdrawals (default: `true`)
- `REQUIRE_WHITELISTED_ADDRESS` - Require whitelisted addresses (default: `true`)
- `REQUIRE_2FA_FOR_WITHDRAWALS` - Require 2FA for withdrawals (default: `false`)
- `WALLET_MAX_TRANSFER_ZAR_PER_TX` - Max per transaction (default: `50000`)
- `WALLET_MAX_TRANSFER_ZAR_PER_DAY` - Max per day (default: `200000`)
- `WALLET_MAX_TRANSFER_ZAR_PER_MONTH` - Max per month (default: `2000000`)
- `REQUIRE_ADMIN_APPROVAL_ABOVE_ZAR` - Require admin approval above amount (default: `100000`)

### Optional Integrations
- `FETCHAI_API_KEY` - Fetch.ai integration (optional)
- `FLOKX_API_KEY` - FLOKx integration (optional)
- `ENABLE_UAGENTS` - Enable uAgents framework (default: `false`)
- `PAYMENT_AGENT_ENABLED` - Enable payment agent (default: `false`)

## Supported Exchanges (Immutable)

The system supports EXACTLY 7 exchanges:
1. **luno** - 5 bots max
2. **binance** - 10 bots max
3. **kucoin** - 10 bots max
4. **bybit** - 10 bots max
5. **kraken** - 10 bots max
6. **bitget** - 10 bots max
7. **gate** - 10 bots max

**Total Capacity:** 65 bots

Any other exchange name will trigger a startup validation error.

## Service Expectations

### Database
- MongoDB 4.4+ required
- Must be accessible at `MONGO_URL`
- Automatic connection pooling enabled
- Automatic index creation on startup

### Email Service
- SMTP server must support TLS/STARTTLS on configured port
- Test email endpoint: `POST /api/notifications/test-email` (admin only)
- Daily reports sent at times specified in `REPORT_TIMES` (Africa/Johannesburg TZ)

### Real-time Features
- WebSocket endpoint: `ws://[host]/api/ws`
- SSE endpoint: `GET /api/realtime/stream`
- Supports JWT authentication via query param or header
- Ping/pong keepalive every 30 seconds

### Background Services
- Trading scheduler (if `ENABLE_SCHEDULERS=true`)
- Email scheduler (if `ENABLE_EMAIL_REPORTS=true`)
- Bot quarantine service
- Balance sync service (every 5 minutes)
- Self-healing service (if `ENABLE_SELF_HEALING=true`)
- Reinvestment service

## Pre-Deployment Validation

1. **Configuration Check:**
   ```bash
   # Server will fail fast on startup if configuration invalid
   # Check logs for: "✅ Configuration validation passed"
   ```

2. **Database Connectivity:**
   ```bash
   # Test MongoDB connection
   mongosh $MONGO_URL --eval "db.adminCommand('ping')"
   ```

3. **Email Configuration:**
   ```bash
   # Test SMTP credentials
   curl -X POST http://localhost:8000/api/notifications/test-email \
     -H "Authorization: Bearer [admin_token]"
   ```

4. **Exchange Validation:**
   ```bash
   # Verify all 7 exchanges are configured correctly
   # Check logs for: "✅ Supported exchanges: luno, binance, kucoin, bybit, kraken, bitget, gate"
   ```

## Post-Deployment Verification

1. **Health Check:**
   ```bash
   curl http://localhost:8000/api/health
   ```

2. **Configuration Info:**
   ```bash
   curl http://localhost:8000/api/system/info
   ```

3. **WebSocket Connection:**
   ```bash
   # Test WebSocket connectivity
   wscat -c "ws://localhost:8000/api/ws?token=[jwt_token]"
   ```

4. **Email Reports:**
   - Verify scheduled reports sent at configured times
   - Check email logs for delivery status

## Security Checklist

- [ ] Changed `JWT_SECRET` from default
- [ ] Set strong `ENCRYPTION_KEY` (Fernet key format)
- [ ] Configured SMTP with secure credentials
- [ ] Set `ENABLE_LIVE_TRADING=false` until ready
- [ ] Enabled `REQUIRE_EMAIL_CONFIRMATION=true` for withdrawals
- [ ] Enabled `REQUIRE_WHITELISTED_ADDRESS=true` for withdrawals
- [ ] Set appropriate withdrawal limits
- [ ] Configured admin approval thresholds
- [ ] Reviewed and set appropriate `MAX_DAILY_LOSS_PERCENT`
- [ ] Reviewed and set appropriate `MAX_DRAWDOWN_PERCENT`

## Production Readiness

### Minimal Configuration
```bash
# Required for basic operation
MONGO_URL=mongodb://user:pass@host:27017/
DB_NAME=amarktai_trading
JWT_SECRET=<generate_strong_secret>
ENCRYPTION_KEY=<generate_fernet_key>
ENABLE_TRADING=true
ENABLE_PAPER_TRADING=true
```

### Production Configuration
```bash
# Full production setup
MONGO_URL=mongodb://user:pass@prod-host:27017/?replicaSet=rs0
DB_NAME=amarktai_trading
JWT_SECRET=<strong_production_secret>
ENCRYPTION_KEY=<strong_fernet_key>
OPENAI_API_KEY=<openai_key>

# Email
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=alerts@amarktai.online
SMTP_PASSWORD=<app_password>
FROM_EMAIL=alerts@amarktai.online
FROM_NAME=Amarktai Network
ENABLE_EMAIL_REPORTS=true
REPORT_TIMES=08:00,18:00

# Trading
ENABLE_TRADING=true
ENABLE_PAPER_TRADING=true
ENABLE_LIVE_TRADING=false  # Enable carefully
ENABLE_AUTOPILOT=true
BOT_SPAWN_PROFIT_ZAR=1000
REINVEST_THRESHOLD_ZAR=300

# Safety
MAX_DAILY_LOSS_PERCENT=0.15
MAX_DRAWDOWN_PERCENT=0.25
REQUIRE_EMAIL_CONFIRMATION=true
REQUIRE_WHITELISTED_ADDRESS=true
```

## Troubleshooting

### Configuration Validation Fails
- Check logs for specific error message
- Verify all required env variables are set
- Ensure `MAX_TOTAL_BOTS=65` matches sum of exchange allocations
- Verify exchange names match exactly: luno, binance, kucoin, bybit, kraken, bitget, gate

### Email Not Sending
- Test SMTP credentials manually
- Check `SMTP_USER` and `SMTP_PASSWORD` are set
- Verify `ENABLE_EMAIL_REPORTS=true`
- Check email service logs for errors
- Use test email endpoint to verify configuration

### WebSocket Connection Issues
- Verify `ENABLE_REALTIME=true`
- Check JWT token is valid
- Ensure firewall allows WebSocket connections
- Check for proxy/reverse proxy WebSocket support

### Bot Spawning Not Working
- Verify `ENABLE_AUTOPILOT=true`
- Check per-exchange profit meets `BOT_SPAWN_PROFIT_ZAR` threshold
- Verify exchange has not reached bot limit
- Check `ENABLE_TRADING=true` or `ENABLE_PAPER_TRADING=true`
- Review spawn gating logs in application logs

## Support

For issues or questions:
- Review application logs for detailed error messages
- Check startup logs for configuration validation
- Verify all environment variables are correctly set
- Ensure database connectivity before starting application
