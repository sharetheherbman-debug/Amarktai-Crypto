# Deployment Guide for Go-Live

## Prerequisites

1. **Server Requirements**
   - Ubuntu 20.04+ or similar Linux distribution
   - Python 3.10+
   - Node.js 20+
   - MongoDB 6.0+
   - Nginx (for frontend serving)

2. **Required Environment Variables**
   - `AMARKTAI_FERNET_KEY`: 32-byte base64-encoded encryption key (CRITICAL)
   - `ADMIN_PASSWORD`: Admin panel password (change from default)
   - `JWT_SECRET`: Secret for JWT token signing
   - `MONGODB_URI`: MongoDB connection string
   - `ENVIRONMENT`: Set to "production"

## Deployment Steps

### 1. Backend Deployment

```bash
# Navigate to backend directory
cd backend

# Install Python dependencies
pip3 install -r requirements.txt

# Verify environment variables are set
python3 -c "import os; print('✅ Encryption key:', 'SET' if os.getenv('AMARKTAI_FERNET_KEY') else '❌ NOT SET')"

# Run preflight checks
python3 preflight.py

# Start backend server (production)
# Option A: Using systemd (recommended)
sudo systemctl start amarktai-backend
sudo systemctl enable amarktai-backend

# Option B: Using screen/tmux
screen -S backend -dm python3 server.py

# Verify backend is running
curl http://localhost:8000/api/system/ping
```

### 2. Frontend Deployment

```bash
# Build frontend
./scripts/build_frontend.sh

# The build output will be in frontend/build/

# Copy to nginx web root
sudo cp -r frontend/build/* /var/www/amarktai/html/

# Or use the provided deployment script
./scripts/deploy_frontend.sh

# Verify deployment
curl http://localhost/version.json
# Should return: {"version": "<git-sha>", "built_at": "...", "frontend": true}
```

### 3. Nginx Configuration

Create or update `/etc/nginx/sites-available/amarktai`:

```nginx
server {
    listen 80;
    server_name your-domain.com;
    
    # Frontend static files
    root /var/www/amarktai/html;
    index index.html;
    
    # SPA routing - all routes serve index.html
    location / {
        try_files $uri $uri/ /index.html;
    }
    
    # API proxy to backend
    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_cache_bypass $http_upgrade;
        
        # SSE/WebSocket support
        proxy_buffering off;
        proxy_read_timeout 300s;
        proxy_send_timeout 300s;
    }
    
    # WebSocket endpoint
    location /ws {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_read_timeout 86400;
    }
}
```

Enable site and reload nginx:

```bash
sudo ln -s /etc/nginx/sites-available/amarktai /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

### 4. SSL/TLS Setup (Production)

```bash
# Install certbot
sudo apt-get install certbot python3-certbot-nginx

# Get SSL certificate
sudo certbot --nginx -d your-domain.com

# Auto-renewal
sudo certbot renew --dry-run
```

### 5. Verification

Run the comprehensive verification script:

```bash
# Set credentials for testing
export AMK_EMAIL="your-admin-email@example.com"
export AMK_PASSWORD="your-admin-password"
export API_BASE="https://your-domain.com"  # Or http://localhost:8000 for local

# Run verification
./scripts/verify_go_live_now.sh
```

Expected output:
```
🔥 AMARKTAI GO-LIVE VERIFICATION
=================================
Test 1: System Ping
✅ PASS: System ping
Test 2: Login
✅ PASS: Login successful
Test 3: Exchanges Registry
✅ PASS: Exchange registry has 7 exchanges
Test 4: Providers List
✅ PASS: Providers list has 10 providers
Test 5: Keys Status
✅ PASS: Keys status endpoint working
Test 6: Keys List
✅ PASS: Keys list endpoint working
Test 7: Live Prices
✅ PASS: Live prices endpoint working
Test 8: SSE Realtime Events
✅ PASS: SSE realtime events working
Test 9: Build Info
✅ PASS: Build info endpoint working
Test 10: AI Chat Greeting
✅ PASS: AI chat greeting working
Test 11: AI Chat History
✅ PASS: AI chat history working
Test 12: Dashboard Overview
✅ PASS: Dashboard overview working

SUMMARY: 12 passed, 0 failed
✅ ALL TESTS PASSED - READY FOR GO-LIVE
```

## Post-Deployment Checklist

- [ ] Backend health endpoint responding: `curl /api/system/ping`
- [ ] Frontend version badge shows correct build hash
- [ ] All 7 exchanges listed in /api/system/platforms
- [ ] All 10 providers listed in /api/keys/providers
- [ ] Admin panel hidden by default (requires "show admin" + password)
- [ ] API key management working (save/test/delete)
- [ ] Realtime events working (WebSocket or SSE fallback)
- [ ] Live prices displaying in overview
- [ ] Timestamps showing correctly (no "Invalid Date")
- [ ] Dashboard section headers are white
- [ ] SSL certificate valid (production only)
- [ ] Monitoring/logging configured
- [ ] Database backups enabled
- [ ] Admin password changed from default

## Rollback Procedure

If deployment fails:

```bash
# Stop new backend
sudo systemctl stop amarktai-backend

# Restore previous frontend
sudo cp -r /var/www/amarktai/html.backup/* /var/www/amarktai/html/

# Reload nginx
sudo systemctl reload nginx

# Start previous backend version
# (Restore from git tag or backup)
```

## Monitoring

Essential metrics to monitor:

1. Backend health: `GET /api/system/ping`
2. System stats: `GET /api/admin/stats` (requires admin auth)
3. Database connection status
4. CPU/Memory usage
5. Error logs: `/var/log/amarktai/backend.log`
6. Nginx access/error logs

## Support Channels

- Issues: GitHub Issues
- Emergency: [Contact admin]
- Documentation: `/docs/` directory

## Supported Exchanges (7)

1. **Luno** - South African exchange
2. **Binance** - Global
3. **KuCoin** - Global (requires passphrase)
4. **Bybit** - Global
5. **Kraken** - Global
6. **Bitget** - Global (requires passphrase)
7. **Gate.io** - Global

## Supported AI Providers (3)

1. **OpenAI** - GPT models
2. **FlokX** - Custom AI
3. **Fetch.ai** - Agent-based AI

## API Key Status States

- `not_configured`: No key saved
- `saved_untested`: Key saved but never tested
- `test_ok`: Key tested successfully
- `test_failed`: Key test failed

## Common Issues

### 1. Backend won't start
- Check `AMARKTAI_FERNET_KEY` is set
- Verify MongoDB is running: `sudo systemctl status mongod`
- Check logs: `journalctl -u amarktai-backend -n 100`

### 2. Frontend shows old version
- Clear browser cache: Ctrl+Shift+R
- Check version badge in footer
- Verify version.json: `curl https://your-domain.com/version.json`

### 3. Admin panel won't unlock
- Verify password matches `ADMIN_PASSWORD` env var
- Check backend logs for auth errors
- Ensure user has typed "show admin" in chat first

### 4. Realtime events not working
- Check WebSocket connection in browser DevTools
- Verify SSE fallback: `curl -N /api/realtime/events`
- Check firewall allows WebSocket connections

### 5. API keys not saving
- Verify encryption key is set
- Check MongoDB write permissions
- Review backend error logs

## Version Control

Current deployment uses git-based versioning:
- Backend SHA displayed in `/api/build/info`
- Frontend SHA in `version.json` and footer badge
- Both should match for clean deployments

## Backup Strategy

**Critical data to backup:**

1. MongoDB database (daily)
   ```bash
   mongodump --out=/backup/mongo/$(date +%Y%m%d)
   ```

2. Environment variables (.env file)
3. Nginx configuration
4. SSL certificates
5. User uploads/data

**Backup retention:** 
- Daily: Keep 7 days
- Weekly: Keep 4 weeks
- Monthly: Keep 12 months
