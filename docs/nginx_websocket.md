# Nginx WebSocket Configuration for Amarktai Network

## Overview

This document provides the Nginx configuration required to properly proxy WebSocket connections for the Amarktai Network dashboard's real-time features.

## WebSocket Endpoint

The application exposes a primary WebSocket endpoint at `/api/ws` and a decision-trace socket at `/ws/decisions` that require special Nginx configuration to handle the WebSocket protocol upgrade.

## Nginx Configuration

### Basic WebSocket Proxy

Add the following location block to your Nginx server configuration:

```nginx
location /api/ws {
    proxy_pass http://backend;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    
    # WebSocket timeout settings
    proxy_read_timeout 86400s;
    proxy_send_timeout 86400s;
    
    # Disable buffering for WebSocket
    proxy_buffering off;
}
```

### Decision Trace WebSocket

```nginx
location /ws/ {
    proxy_pass http://backend;
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_read_timeout 86400s;
    proxy_send_timeout 86400s;
    proxy_buffering off;
}
```

### Complete Nginx Configuration Example

Here's a complete example with SSL and the backend API configuration:

```nginx
upstream backend {
    server 127.0.0.1:8000;
    keepalive 32;
}

server {
    listen 80;
    server_name yourdomain.com;
    
    # Redirect HTTP to HTTPS
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name yourdomain.com;
    
    # SSL Configuration
    ssl_certificate /path/to/ssl/certificate.crt;
    ssl_certificate_key /path/to/ssl/certificate.key;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;
    
    # Frontend static files
    location / {
        root /var/www/amarktai/frontend/build;
        try_files $uri $uri/ /index.html;
        
        # Cache static assets
        location ~* \.(js|css|png|jpg|jpeg|gif|ico|svg|woff|woff2|ttf|eot)$ {
            expires 1y;
            add_header Cache-Control "public, immutable";
        }
    }
    
    # API endpoints (REST)
    location /api/ {
        proxy_pass http://backend;
        proxy_http_version 1.1;
        proxy_set_header Connection "";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # Timeouts for long-running requests
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
    }
    
    # WebSocket endpoint (requires special handling)
    location /api/ws {
        proxy_pass http://backend;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # WebSocket-specific timeouts (24 hours)
        proxy_read_timeout 86400s;
        proxy_send_timeout 86400s;
        
        # Disable buffering
        proxy_buffering off;
    }
    
    # Health check endpoint
    location /api/health {
        proxy_pass http://backend;
        access_log off;
    }
}
```

## Configuration Explanations

### Critical Headers

1. **`Upgrade` and `Connection` headers**: Required for WebSocket protocol upgrade
   ```nginx
   proxy_set_header Upgrade $http_upgrade;
   proxy_set_header Connection "upgrade";
   ```

2. **`Host` header**: Preserves original host for proper routing
   ```nginx
   proxy_set_header Host $host;
   ```

3. **`X-Real-IP` and `X-Forwarded-For`**: Preserve client IP addresses
   ```nginx
   proxy_set_header X-Real-IP $remote_addr;
   proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
   ```

### Timeout Settings

WebSocket connections are long-lived, so timeouts must be set appropriately:

- **`proxy_read_timeout`**: 86400s (24 hours) - prevents timeout on idle connections
- **`proxy_send_timeout`**: 86400s (24 hours) - prevents timeout on sending data
- **`proxy_buffering off`**: Disables response buffering for real-time delivery

## Testing WebSocket Connection

### Using Browser Console

```javascript
const token = localStorage.getItem('token');
const ws = new WebSocket(`wss://yourdomain.com/api/ws?token=${token}`);

ws.onopen = () => console.log('Connected to WebSocket');
ws.onmessage = (event) => console.log('Message:', JSON.parse(event.data));
ws.onerror = (error) => console.error('WebSocket error:', error);
ws.onclose = () => console.log('WebSocket closed');
```

### Using wscat (Command Line)

```bash
# Install wscat
npm install -g wscat

# Test connection (replace TOKEN with actual JWT)
wscat -c "wss://yourdomain.com/api/ws?token=TOKEN"

# You should see connection established and can send/receive messages
```

### Using curl (for HTTP upgrade check)

```bash
curl -i -N \
  -H "Connection: Upgrade" \
  -H "Upgrade: websocket" \
  -H "Sec-WebSocket-Version: 13" \
  -H "Sec-WebSocket-Key: test" \
  https://yourdomain.com/api/ws?token=TOKEN
```

## Troubleshooting

### Issue: WebSocket connection fails with 404

**Solution**: Ensure the location block for `/api/ws` is defined **before** the general `/api/` location block in your Nginx config. Nginx uses the first matching location.

### Issue: Connection drops after 60 seconds

**Solution**: Increase `proxy_read_timeout` and `proxy_send_timeout` values:
```nginx
proxy_read_timeout 86400s;
proxy_send_timeout 86400s;
```

### Issue: "Connection: upgrade" header not working

**Solution**: Ensure you're using HTTP/1.1 for the proxy connection:
```nginx
proxy_http_version 1.1;
```

### Issue: WebSocket works locally but not through Nginx

**Checklist**:
1. Verify `Upgrade` and `Connection` headers are set
2. Check `proxy_http_version 1.1` is set
3. Verify SSL certificate is valid (for wss://)
4. Check Nginx error logs: `tail -f /var/log/nginx/error.log`
5. Verify backend WebSocket server is running and accessible

### Issue: High CPU usage with many WebSocket connections

**Solution**: Add keepalive connections to upstream:
```nginx
upstream backend {
    server 127.0.0.1:8000;
    keepalive 32;  # Reuse connections
}
```

## Monitoring WebSocket Connections

### Check active connections

```bash
# Using netstat
netstat -an | grep :8000 | grep ESTABLISHED | wc -l

# Using ss
ss -tn | grep :8000 | wc -l
```

### Nginx access log format for WebSocket

Add custom log format to track WebSocket connections:

```nginx
log_format websocket '$remote_addr - $remote_user [$time_local] '
                     '"$request" $status $body_bytes_sent '
                     '"$http_referer" "$http_user_agent" '
                     'upgrade=$http_upgrade connection=$http_connection';

access_log /var/log/nginx/websocket_access.log websocket;
```

## Security Considerations

1. **Authentication**: WebSocket endpoint requires JWT token via query parameter
2. **Rate Limiting**: Consider adding rate limiting for WebSocket connections:
   ```nginx
   limit_req_zone $binary_remote_addr zone=ws_limit:10m rate=10r/s;
   
   location /api/ws {
       limit_req zone=ws_limit burst=20;
       # ... rest of configuration
   }
   ```

3. **CORS**: Not applicable to WebSocket, but ensure your REST API CORS settings don't interfere

4. **SSL/TLS**: Always use `wss://` (WebSocket Secure) in production

## Performance Tuning

### Increase worker connections

```nginx
events {
    worker_connections 4096;  # Increase for many concurrent WebSocket connections
    use epoll;  # Efficient on Linux
}
```

### Adjust buffer sizes

```nginx
proxy_buffer_size 4k;
proxy_buffers 8 4k;
proxy_busy_buffers_size 8k;
```

## References

- [Nginx WebSocket Proxying](https://nginx.org/en/docs/http/websocket.html)
- [FastAPI WebSocket Documentation](https://fastapi.tiangolo.com/advanced/websockets/)
- [WebSocket Protocol Specification (RFC 6455)](https://tools.ietf.org/html/rfc6455)

## Support

For issues specific to the Amarktai Network WebSocket implementation, check:
- Backend logs: `/var/log/amarktai/backend.log`
- Nginx error logs: `/var/log/nginx/error.log`
- Browser console for client-side errors
