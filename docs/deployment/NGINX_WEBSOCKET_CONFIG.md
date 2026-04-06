# Nginx WebSocket Configuration Guide

## Overview

Required nginx configuration for WebSocket support in Amarktai Network.

## Required Configuration

### WebSocket Upgrade Headers

Add to your nginx location block:

```nginx
location /api/ws {
    proxy_pass http://127.0.0.1:8000/api/ws;
    
    # WebSocket upgrade (REQUIRED)
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    
    # Headers
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    
    # Timeouts (90s minimum, 300s recommended)
    proxy_read_timeout 300s;
    proxy_send_timeout 300s;
    proxy_connect_timeout 90s;
    
    # No buffering
    proxy_buffering off;
}

location ~ ^/api/(sse|realtime)/ {
    proxy_pass http://127.0.0.1:8000;
    
    # SSE headers
    proxy_http_version 1.1;
    proxy_set_header Connection "";
    
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    
    proxy_read_timeout 300s;
    proxy_send_timeout 300s;
    
    # No buffering (CRITICAL for SSE)
    proxy_buffering off;
    proxy_cache off;
    chunked_transfer_encoding on;
}

location /api/ {
    proxy_pass http://127.0.0.1:8000/api/;
    
    # Include WebSocket support
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    
    proxy_read_timeout 90s;
    proxy_send_timeout 90s;
}
```

## Testing

### Browser Console Test

```javascript
const ws = new WebSocket('wss://your-domain.com/api/ws?token=YOUR_JWT_TOKEN');
ws.onopen = () => console.log('✅ Connected');
ws.onmessage = (e) => console.log('📨', JSON.parse(e.data));
ws.send(JSON.stringify({ type: 'ping', timestamp: Date.now() }));
```

### Expected Logs

```
101 Switching Protocols  # Success
499 Client Closed        # Normal close
502 Bad Gateway          # Backend down
504 Gateway Timeout      # Increase timeouts
```

## Troubleshooting

| Problem | Solution |
|---------|----------|
| Connects then closes | Add upgrade headers, increase timeouts |
| 502 Bad Gateway | Check backend is running on port 8000 |
| Works locally not nginx | Verify SSL (wss://), reload nginx |

## Key Points

1. **Upgrade headers are REQUIRED** - Without them, WebSocket won't work
2. **Timeouts: 90s minimum, 300s recommended** - Connections are persistent
3. **Buffering must be OFF** - Especially for SSE
4. **Use wss:// for SSL sites** - Not ws://

---

Last Updated: 2026-02-16
