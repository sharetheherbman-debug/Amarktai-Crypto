# Bot Pause Diagnosis and Resolution Guide

## Problem Statement
All bots are paused and unable to trade. Paper trading should run reliably without live exchange keys.

## Root Causes

### 1. Emergency Stop Active
- **Location**: `system_modes` collection in database
- **Check**: Field `emergencyStop` is set to `true`
- **Resolution**: Use emergency resume endpoint:
  ```bash
  curl -X POST https://www.amarktai.online/api/system/emergency-resume \
    -H "Authorization: Bearer YOUR_JWT_TOKEN"
  ```

### 2. Trading Mode Disabled
- **Config**: `ENABLE_PAPER_TRADING` or `ENABLE_LIVE_TRADING` environment variables
- **Default**: Paper trading ON, Live trading OFF
- **Check**: Verify in backend logs on startup:
  ```
  📊 Paper Trading: ON
  🔴 Live Trading: OFF
  ```
- **Resolution**: Ensure `ENABLE_PAPER_TRADING=true` in environment

### 3. Bodyguard Drawdown Lock
- **Field**: `paused_by_bodyguard=true` in bot document
- **Cause**: Bot exceeded maximum drawdown threshold
- **Resolution**: Bot will auto-resume when drawdown recovers, or use resume endpoint:
  ```bash
  curl -X POST https://www.amarktai.online/api/bots/{bot_id}/resume \
    -H "Authorization: Bearer YOUR_JWT_TOKEN"
  ```

### 4. Bot Quarantine
- **Field**: `status=quarantined` in bot document
- **Cause**: Bot in training/failure mode
- **Resolution**: Complete paper trading requirements to exit quarantine

### 5. Manual Pause
- **Fields**: `paused_by_user=true` or `paused_by_system=true`
- **Resolution**: Use unpause endpoint:
  ```bash
  curl -X POST https://www.amarktai.online/api/bots/{bot_id}/unpause \
    -H "Authorization: Bearer YOUR_JWT_TOKEN"
  ```

## Diagnostic Commands

### Check System Mode
```bash
curl https://www.amarktai.online/api/system/mode \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

Expected response (for paper trading):
```json
{
  "mode": "paper",
  "paperTrading": true,
  "liveTrading": false,
  "autopilot": false,
  "emergencyStop": false
}
```

### Check Bot Status
```bash
curl https://www.amarktai.online/api/bots \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

Look for these fields in bot objects:
- `status`: should be "active" (not "quarantined" or "paused")
- `paused_by_bodyguard`: should be false
- `paused_by_user`: should be false
- `paused_by_system`: should be false

### Check Real-Time Connection
```bash
curl https://www.amarktai.online/api/diagnostics/realtime \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

Expected response:
```json
{
  "success": true,
  "ws_connected": 1,
  "ws_total_connections": 1,
  "last_event_type": "heartbeat",
  "manager_type": "ConnectionManager"
}
```

## Safe Resume Procedure

1. **Check emergency stop status**:
   ```bash
   curl https://www.amarktai.online/api/system/mode -H "Authorization: Bearer $TOKEN"
   ```

2. **If emergency stop is active, disable it**:
   ```bash
   curl -X POST https://www.amarktai.online/api/system/emergency-resume -H "Authorization: Bearer $TOKEN"
   ```

3. **Resume individual bots**:
   ```bash
   # Get bot IDs
   curl https://www.amarktai.online/api/bots -H "Authorization: Bearer $TOKEN" | jq -r '.[].bot_id'
   
   # Resume each bot
   curl -X POST https://www.amarktai.online/api/bots/BOT_ID/resume -H "Authorization: Bearer $TOKEN"
   ```

4. **Verify bots are running**:
   ```bash
   curl https://www.amarktai.online/api/bots -H "Authorization: Bearer $TOKEN" | jq '.[] | {bot_id, status, paused_by_bodyguard, paused_by_user}'
   ```

## Environment Configuration

Required environment variables for paper trading:
```bash
ENABLE_PAPER_TRADING=true
ENABLE_LIVE_TRADING=false
ENABLE_REALTIME=true
```

These should be set in the backend environment (e.g., in systemd service file or `.env`).

## Notes

- Paper trading does NOT require exchange API keys
- Paper bots execute trades internally against public price feeds
- Paper trades update the ledger and trades endpoints
- Live trading requires valid exchange API keys
- Emergency stop blocks ALL trading (paper and live)
