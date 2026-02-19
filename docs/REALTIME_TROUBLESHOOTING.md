# Real-Time WebSocket Troubleshooting Guide

## Problem Statement
Dashboard doesn't update in real-time. WebSocket connection appears to hang, ws_connected stays 0, and live updates don't appear.

## Architecture Overview

### Backend WebSocket Stack
- **Endpoint**: `/api/ws` (wss:// in production, ws:// in development)
- **Authentication**: JWT token via query param (`?token=xxx`) or Authorization header
- **Manager**: `websocket_manager_redis.py` - Handles connections with Redis pub/sub support
- **Broadcaster**: `services/realtime_broadcaster.py` - Sends periodic updates every 5 seconds
- **Events**: `realtime_events.py` - Event bus for system-wide event emission

### Frontend WebSocket Stack
- **Client**: `lib/realtime.js` - Singleton WebSocket client with fallback chain
- **Protocol Detection**: Auto-detects `wss://` for HTTPS, `ws://` for HTTP
- **Connection URL**: `wss://www.amarktai.online/api/ws?token=JWT_TOKEN`
- **Fallback Chain**: WebSocket → SSE → Polling
- **Keep-Alive**: Ping/pong every 20 seconds

## Diagnostic Checklist

### 1. Check Backend Broadcaster is Running

The broadcaster must be started by the lifecycle manager:

```bash
# Check backend logs
sudo journalctl -u amarktai-backend -n 100 | grep -i "realtime\|broadcaster"
```

Expected log messages:
```
📡 Realtime broadcaster started (interval=5s)
✅ Started 12 subsystems with 6 background tasks
```

### 2. Verify ENABLE_REALTIME Flag

Check environment configuration:
```bash
# Check systemd service file
sudo cat /etc/systemd/system/amarktai-backend.service | grep ENABLE_REALTIME

# Or check .env file
grep ENABLE_REALTIME /var/amarktai/app/Amarktai-Network---Deployment/backend/.env
```

Expected value:
```
ENABLE_REALTIME=true
```

### 3. Test WebSocket Connection

Using `wscat` (install: `npm install -g wscat`):

```bash
# Get JWT token first
TOKEN="your_jwt_token_here"

# Test WebSocket connection
wscat -c "wss://www.amarktai.online/api/ws?token=$TOKEN"
```

Expected output:
```
Connected (press CTRL+C to quit)
< {"type":"heartbeat","timestamp":"2024-02-18T21:50:00.000Z","source":"realtime_broadcaster"}
< {"type":"prices_update","data":{...}}
< {"type":"overview_update","data":{...}}
```

### 4. Check Diagnostics Endpoint

```bash
curl https://www.amarktai.online/api/diagnostics/realtime \
  -H "Authorization: Bearer $TOKEN" | jq
```

Expected response:
```json
{
  "success": true,
  "ws_connected": 1,
  "ws_total_connections": 1,
  "sse_supported": false,
  "last_event_type": "heartbeat",
  "last_event_time": "2024-02-18T21:50:00.000Z",
  "connection_count": 1,
  "manager_type": "ConnectionManager",
  "timestamp": "2024-02-18T21:50:05.000Z"
}
```

**Key indicators**:
- `ws_connected > 0`: You have an active WebSocket connection
- `ws_connected === 0`: No WebSocket connection (check frontend)
- `last_event_type`: Should show recent events like "heartbeat", "overview_update", etc.

### 5. Check Frontend WebSocket URL

Open browser DevTools Console and look for:
```
🔌 Connecting to WebSocket: wss://www.amarktai.online/api/ws?token=***
✅ WebSocket connected
```

**Common issues**:
- URL shows `ws://` instead of `wss://` on HTTPS site (protocol mismatch)
- URL shows `/ws` instead of `/api/ws` (wrong path)
- Token is invalid or expired (authentication failure)

### 6. Verify Nginx Reverse Proxy

Check Nginx configuration for WebSocket support:

```bash
sudo cat /etc/nginx/sites-enabled/amarktai | grep -A 10 "location /api/ws"
```

Required configuration:
```nginx
location /api/ws {
    proxy_pass http://127.0.0.1:8000;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_read_timeout 86400;
}
```

**Key settings**:
- `proxy_http_version 1.1`: Required for WebSocket
- `Upgrade` and `Connection` headers: Required for WebSocket handshake
- `proxy_read_timeout 86400`: Prevent premature connection close

Test Nginx config:
```bash
sudo nginx -t
sudo systemctl reload nginx
```

## Common Issues and Resolutions

### Issue 1: ws_connected stays 0

**Symptoms**: Diagnostics endpoint shows `ws_connected: 0`, dashboard shows "Realtime: Polling"

**Causes**:
1. Frontend not connecting to WebSocket
2. WebSocket connection rejected by backend (auth failure)
3. Nginx not configured for WebSocket upgrade

**Resolution**:
1. Check browser console for WebSocket connection errors
2. Verify JWT token is valid and not expired
3. Check Nginx configuration for WebSocket support
4. Verify backend logs for connection rejection messages

### Issue 2: Connection drops after a few seconds

**Symptoms**: WebSocket connects but quickly disconnects

**Causes**:
1. Token expired
2. Nginx timeout too short
3. Backend broadcaster stopped

**Resolution**:
1. Refresh JWT token
2. Increase `proxy_read_timeout` in Nginx
3. Check backend logs for broadcaster errors

### Issue 3: No events received

**Symptoms**: WebSocket connected but no messages received

**Causes**:
1. Broadcaster not started
2. ENABLE_REALTIME=false
3. No active data to broadcast

**Resolution**:
1. Check broadcaster logs: `sudo journalctl -u amarktai-backend | grep broadcaster`
2. Verify ENABLE_REALTIME=true in environment
3. Create test bot or trade to trigger events

### Issue 4: Events delayed or batched

**Symptoms**: Updates appear in bursts instead of real-time

**Causes**:
1. Broadcaster interval too high
2. Network latency
3. Frontend polling fallback active

**Resolution**:
1. Check `REALTIME_BROADCAST_INTERVAL` (default: 5s)
2. Verify WebSocket is active (not falling back to polling)
3. Check network latency with ping test

## Verification Commands

### Quick Health Check
```bash
# Check all components in one command
curl -s https://www.amarktai.online/api/diagnostics/realtime \
  -H "Authorization: Bearer $TOKEN" | jq '{
    ws_connected,
    last_event_type,
    manager_type
  }'
```

Expected output:
```json
{
  "ws_connected": 1,
  "last_event_type": "heartbeat",
  "manager_type": "ConnectionManager"
}
```

### Test Event Emission
```bash
# Trigger a test event by updating system stats
curl -X POST https://www.amarktai.online/api/admin/system/refresh \
  -H "Authorization: Bearer $TOKEN"
```

This should trigger events visible in WebSocket connection.

## Production Environment Details

- **Production URL**: https://www.amarktai.online
- **WebSocket URL**: wss://www.amarktai.online/api/ws
- **Backend**: FastAPI + Uvicorn (port 8000)
- **Reverse Proxy**: Nginx with WebSocket support
- **Broadcaster Interval**: 5 seconds (configurable via REALTIME_BROADCAST_INTERVAL)
- **Keep-Alive**: Frontend sends ping every 20 seconds

## Additional Resources

- Backend WebSocket route: `backend/routes/websocket.py`
- WebSocket manager: `backend/websocket_manager_redis.py`
- Realtime broadcaster: `backend/services/realtime_broadcaster.py`
- Frontend client: `frontend/src/lib/realtime.js`
- Lifecycle manager: `backend/services/lifecycle.py` (line 119-126)
