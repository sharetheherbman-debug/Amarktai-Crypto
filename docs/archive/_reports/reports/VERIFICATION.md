# Manual Verification Steps

This document provides curl commands to manually verify all new endpoints and features.

## Prerequisites

```bash
# Set your auth token
export AUTH_TOKEN="your-jwt-token-here"
export API_URL="http://localhost:8000"
```

## 1. Health and System Checks

### Health Ping
```bash
curl -X GET "$API_URL/api/health/ping"
# Expected: {"status":"ok","timestamp":"..."}
```

### Health Indicators
```bash
curl -X GET "$API_URL/api/health/indicators"
# Expected: Full health status with API, DB, WebSocket, SSE indicators
```

## 2. Trade Budget System

### Get All System Limits
```bash
curl -X GET "$API_URL/api/system/limits" \
  -H "Authorization: Bearer $AUTH_TOKEN"
# Expected: Exchange budgets, bot budgets, utilization percentages
```

### Get Exchange-Specific Limits
```bash
curl -X GET "$API_URL/api/system/limits/exchange/binance" \
  -H "Authorization: Bearer $AUTH_TOKEN"
# Expected: Binance-specific budget info and all bots on that exchange
```

### Get Bot-Specific Limits
```bash
# Replace {bot_id} with actual bot ID
curl -X GET "$API_URL/api/system/limits/bot/{bot_id}" \
  -H "Authorization: Bearer $AUTH_TOKEN"
# Expected: Bot's daily budget, remaining trades, utilization
```

## 3. Bot Lifecycle Management

### Start a Bot
```bash
curl -X POST "$API_URL/api/bots/{bot_id}/start" \
  -H "Authorization: Bearer $AUTH_TOKEN"
# Expected: {"success":true,"message":"Bot ... started successfully"}
```

### Pause a Bot
```bash
curl -X POST "$API_URL/api/bots/{bot_id}/pause" \
  -H "Authorization: Bearer $AUTH_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"reason":"Manual pause for testing"}'
# Expected: {"success":true,"message":"Bot ... paused successfully"}
```

### Resume a Bot
```bash
curl -X POST "$API_URL/api/bots/{bot_id}/resume" \
  -H "Authorization: Bearer $AUTH_TOKEN"
# Expected: {"success":true,"message":"Bot ... resumed successfully"}
```

### Stop a Bot
```bash
curl -X POST "$API_URL/api/bots/{bot_id}/stop" \
  -H "Authorization: Bearer $AUTH_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"reason":"Manual stop for maintenance"}'
# Expected: {"success":true,"message":"Bot ... stopped successfully"}
```

### Get Detailed Bot Status
```bash
curl -X GET "$API_URL/api/bots/{bot_id}/status" \
  -H "Authorization: Bearer $AUTH_TOKEN"
# Expected: Comprehensive status including cooldown, performance metrics
```

### Pause All Bots
```bash
curl -X POST "$API_URL/api/bots/pause-all" \
  -H "Authorization: Bearer $AUTH_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"reason":"System maintenance"}'
# Expected: {"success":true,"paused_count":N}
```

### Resume All Bots
```bash
curl -X POST "$API_URL/api/bots/resume-all" \
  -H "Authorization: Bearer $AUTH_TOKEN"
# Expected: {"success":true,"resumed_count":N}
```

## 4. Live Trading Gate (7-Day Learning)

### Start Paper Learning Period
```bash
curl -X POST "$API_URL/api/system/start-paper-learning" \
  -H "Authorization: Bearer $AUTH_TOKEN"
# Expected: {"success":true,"started_at":"...","required_days":7}
```

### Check Live Eligibility
```bash
curl -X GET "$API_URL/api/system/live-eligibility" \
  -H "Authorization: Bearer $AUTH_TOKEN"
# Expected: Detailed eligibility status, requirements, current progress
```

### Request Live Trading Activation
```bash
curl -X POST "$API_URL/api/system/request-live" \
  -H "Authorization: Bearer $AUTH_TOKEN"
# Expected: Success if eligible, or reasons for denial with statistics
```

## 5. Analytics API (Single Source of Truth)

### Get PnL Timeseries
```bash
# 7-day hourly data
curl -X GET "$API_URL/api/analytics/pnl_timeseries?range=7d&interval=1h" \
  -H "Authorization: Bearer $AUTH_TOKEN"
# Expected: Array of datapoints with timestamps, cumulative_pnl, period_pnl

# 30-day daily data
curl -X GET "$API_URL/api/analytics/pnl_timeseries?range=30d&interval=1d" \
  -H "Authorization: Bearer $AUTH_TOKEN"
```

### Get Capital Breakdown
```bash
curl -X GET "$API_URL/api/analytics/capital_breakdown" \
  -H "Authorization: Bearer $AUTH_TOKEN"
# Expected: funded_capital, current_capital, unrealized_pnl, realized_pnl
```

### Get Performance Summary
```bash
# Today's performance
curl -X GET "$API_URL/api/analytics/performance_summary?period=today" \
  -H "Authorization: Bearer $AUTH_TOKEN"

# Last 30 days
curl -X GET "$API_URL/api/analytics/performance_summary?period=30d" \
  -H "Authorization: Bearer $AUTH_TOKEN"
# Expected: Win rate, profit factor, average win/loss, total PnL
```

## 6. OpenAPI Schema Validation

### Check for No Duplicate Routes
```bash
curl -X GET "$API_URL/openapi.json" | jq '.paths | keys[]' | grep -E '/api/auth/auth|/api/api/'
# Expected: No output (no duplicates)
```

### List All Bot Endpoints
```bash
curl -X GET "$API_URL/openapi.json" | jq '.paths | keys[]' | grep '/api/bots'
# Expected: /api/bots/{bot_id}/start, /stop, /pause, /resume, /status, etc.
```

### List All System Endpoints
```bash
curl -X GET "$API_URL/openapi.json" | jq '.paths | keys[]' | grep '/api/system'
# Expected: /api/system/limits, /request-live, /live-eligibility, etc.
```

## 7. Real-time Features

### WebSocket Connection Test
```bash
# Use wscat or similar WebSocket client
wscat -c "ws://localhost:8000/api/ws?token=$AUTH_TOKEN"
# Expected: Connection established, real-time messages on bot status changes
```

### SSE Stream Test
```bash
curl -N "$API_URL/api/realtime/events?token=$AUTH_TOKEN"
# Expected: Stream of server-sent events
```

## 8. Deployment Script Test

### Test Changed Files Deployment
```bash
cd /path/to/repo
./deployment/deploy_changed_files.sh
# Expected: 
# - Pulls latest changes
# - Runs tests
# - Deploys only changed files
# - Restarts service
# - Validates health
# - Rolls back if health check fails
```

## 9. Backend Tests

### Run API Structure Tests
```bash
cd backend
source venv/bin/activate
python -m pytest tests/test_api_structure.py -v
# Expected: All tests pass
# - test_no_duplicate_auth_paths
# - test_health_ping_exists
# - test_system_limits_endpoint
# - test_bot_lifecycle_endpoints_exist
# - test_analytics_pnl_timeseries
# - test_live_gate_endpoints
```

## 10. Budget Compliance Verification

### Verify Budget Decrements
```bash
# Get initial budget
curl -X GET "$API_URL/api/system/limits/bot/{bot_id}" \
  -H "Authorization: Bearer $AUTH_TOKEN" | jq '.limits.remaining_today'
# Note the remaining count

# Execute a trade (via your trading mechanism)

# Check budget again
curl -X GET "$API_URL/api/system/limits/bot/{bot_id}" \
  -H "Authorization: Bearer $AUTH_TOKEN" | jq '.limits.remaining_today'
# Expected: Count decreased by 1
```

### Verify Paused Bots Don't Trade
```bash
# Pause a bot
curl -X POST "$API_URL/api/bots/{bot_id}/pause" \
  -H "Authorization: Bearer $AUTH_TOKEN"

# Wait for trading cycle (check logs)
# Expected: Scheduler skips paused bot

# Verify trade count unchanged
curl -X GET "$API_URL/api/bots/{bot_id}/status" \
  -H "Authorization: Bearer $AUTH_TOKEN" | jq '.performance.trades_today'
```

## 11. Live Gate Validation

### Verify 7-Day Gate Blocks Live
```bash
# As new user, request live immediately
curl -X POST "$API_URL/api/system/request-live" \
  -H "Authorization: Bearer $AUTH_TOKEN"
# Expected: {"success":false,"reasons":["Paper trading period incomplete: 0/7 days"]}

# After 7 days with good performance
curl -X POST "$API_URL/api/system/request-live" \
  -H "Authorization: Bearer $AUTH_TOKEN"
# Expected: {"success":true} if all criteria met
```

## Success Criteria

✅ All health endpoints return 200  
✅ Trade limits API returns budget data  
✅ Bot lifecycle operations work (start/stop/pause/resume)  
✅ Live gate enforces 7-day requirement  
✅ Analytics API provides timeseries data  
✅ No duplicate /api/auth/auth/* paths  
✅ Deployment script completes successfully  
✅ Tests pass with 0 failures  
✅ Budget decrements on trade execution  
✅ Paused bots are skipped by scheduler  

## Troubleshooting

### If endpoints return 404:
```bash
# Check if routers are mounted
curl "$API_URL/openapi.json" | jq '.paths | keys[]' | grep -E 'system|analytics|bots'
```

### If budget not decrementing:
```bash
# Check trade_budget_manager logs
sudo journalctl -u amarktai-api -f | grep budget
```

### If live gate not working:
```bash
# Check user's paper_learning_start_ts
# Via MongoDB shell or API
```

## Notes

- Replace `{bot_id}` with actual bot IDs from your database
- Ensure you have a valid JWT token in `$AUTH_TOKEN`
- All endpoints require authentication except `/api/health/ping`
- WebSocket and SSE require token in query parameter

## 12. AI Chat System

### Send AI Chat Message
```bash
curl -X POST "$API_URL/api/ai/chat" \
  -H "Authorization: Bearer $AUTH_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "content": "How are my bots performing?",
    "request_action": false
  }'
# Expected: AI response with system state summary
```

### Get Chat History
```bash
curl -X GET "$API_URL/api/ai/chat/history?limit=50" \
  -H "Authorization: Bearer $AUTH_TOKEN"
# Expected: List of chat messages
```

### Execute AI Action
```bash
curl -X POST "$API_URL/api/ai/action/execute" \
  -H "Authorization: Bearer $AUTH_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "action": "get_limits",
    "params": {}
  }'
# Expected: Action execution result
```

## 13. Two-Factor Authentication (2FA)

### Enroll in 2FA
```bash
curl -X POST "$API_URL/api/auth/2fa/enroll" \
  -H "Authorization: Bearer $AUTH_TOKEN"
# Expected: QR code (base64), secret for manual entry
```

### Verify 2FA Enrollment
```bash
curl -X POST "$API_URL/api/auth/2fa/verify" \
  -H "Authorization: Bearer $AUTH_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "code": "123456"
  }'
# Expected: {"success":true,"message":"2FA has been successfully enabled"}
```

### Check 2FA Status
```bash
curl -X GET "$API_URL/api/auth/2fa/status" \
  -H "Authorization: Bearer $AUTH_TOKEN"
# Expected: {"enabled":true/false,"enrolled_at":"..."}
```

### Disable 2FA
```bash
curl -X POST "$API_URL/api/auth/2fa/disable" \
  -H "Authorization: Bearer $AUTH_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "code": "123456",
    "password": "your_password"
  }'
# Expected: {"success":true,"message":"2FA has been disabled"}
```

## 14. Genetic Algorithm / Bot DNA Evolution

### Evolve Bots
```bash
curl -X POST "$API_URL/api/genetic/evolve" \
  -H "Authorization: Bearer $AUTH_TOKEN"
# Expected: {"success":true,"evolved_count":N,"generation":M}
```

### Get Evolution Status
```bash
curl -X GET "$API_URL/api/genetic/status" \
  -H "Authorization: Bearer $AUTH_TOKEN"
# Expected: DNA diversity metrics, generation info
```

### Manual Bot Mutation
```bash
curl -X POST "$API_URL/api/genetic/mutate/{bot_id}" \
  -H "Authorization: Bearer $AUTH_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "mutation_strength": 0.15
  }'
# Expected: Mutated bot details
```

### Create Offspring via Crossover
```bash
curl -X POST "$API_URL/api/genetic/crossover" \
  -H "Authorization: Bearer $AUTH_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "parent1_id": "bot_id_1",
    "parent2_id": "bot_id_2",
    "name": "Evolved Bot",
    "apply_mutation": true
  }'
# Expected: New bot created from parent DNA
```

### Enable Auto-Evolution
```bash
curl -X POST "$API_URL/api/genetic/auto-evolve/enable" \
  -H "Authorization: Bearer $AUTH_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "interval_hours": 24,
    "min_bots": 10
  }'
# Expected: {"success":true,"message":"Automatic evolution enabled"}
```

## Additional Success Criteria

✅ AI chat responds with system context  
✅ 2FA enrollment generates QR code  
✅ 2FA verification enables protection  
✅ Genetic algorithm evolves weak bots  
✅ Bot DNA crossover creates offspring  
✅ Frontend components render correctly  
