# Production Deployment Guide - Go Live Tonight

> 🚀 **Quick deployment guide for production go-live**

## 📋 Pre-Deployment Checklist

### 1. Environment Variables

Create `.env` file with these required variables:

```bash
# Database
MONGO_URI=mongodb://localhost:27017/amarktai
REDIS_URL=redis://localhost:6379

# Security
JWT_SECRET=<generate-strong-secret>
AMARKTAI_FERNET_KEY=<generate-fernet-key>
ADMIN_PASSWORD=<admin-password>

# Email (Gmail SMTP)
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=amarktainetwork@gmail.com
SMTP_PASSWORD=<gmail-app-password>
FROM_EMAIL=amarktainetwork@gmail.com
FROM_NAME="Amarktai Network"

# AI/OpenAI
OPENAI_API_KEY=<openai-key>

# System
ENVIRONMENT=production
ENABLE_DANGEROUS_ADMIN=false

# Optional
REQUIRE_2FA_FOR_WITHDRAWALS=false
```

### 2. Generate Secrets

```bash
# Generate JWT secret
python3 -c "import secrets; print(secrets.token_urlsafe(32))"

# Generate Fernet key for API key encryption
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

---

## 🔧 Deployment Steps

### Step 1: Run Migrations

```bash
# Ensure all bots have proper IDs
cd scripts/migrations
python3 ensure_bot_ids.py
```

### Step 2: Clamp Bot Caps (Optional - First Run)

```bash
# Check what would be clamped (dry run)
python3 scripts/clamp_bot_caps.py

# Execute clamping
python3 scripts/clamp_bot_caps.py --execute
```

### Step 3: Bootstrap Admin User

```bash
cd scripts
export AMK_ADMIN_EMAIL=amarktainetwork@gmail.com
export AMK_ADMIN_PASS=<admin-password>
python3 bootstrap_admin.py
```

### Step 4: Start Services

```bash
# Backend (from backend directory)
cd backend
uvicorn server:app --host 0.0.0.0 --port 8000 --reload

# Frontend (from frontend directory)
cd frontend
npm run build  # Build for production
# Serve with nginx or:
npx serve -s dist -l 3000
```

### Step 5: Verify Deployment

```bash
# Run smoke tests
cd scripts
./smoke.sh

# Check endpoints
curl http://localhost:8000/api/health
curl http://localhost:8000/api/platforms
```

---

## 🌐 Nginx Configuration

```nginx
server {
    listen 80;
    server_name amarktai.online www.amarktai.online;
    
    # Frontend static files
    location / {
        root /var/www/amarktai/frontend/dist;
        try_files $uri $uri/ /index.html;
    }
    
    # Backend API
    location /api/ {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
    
    # WebSocket
    location /ws {
        proxy_pass http://localhost:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

---

## 🔐 Security Hardening

### 1. Set Proper File Permissions

```bash
# Backend .env
chmod 600 backend/.env

# Scripts
chmod +x scripts/*.sh
chmod +x scripts/migrations/*.py
```

### 2. Admin Access

- Admin password should be strong (12+ characters, mixed case, numbers, symbols)
- Store ADMIN_PASSWORD in environment, not in code
- Use `show admin` command in chat to unlock admin panel
- Admin session expires after 24 hours

### 3. API Keys Encryption

- All API keys are encrypted using Fernet symmetric encryption
- Never commit AMARKTAI_FERNET_KEY to source control
- Rotate keys periodically using admin panel

---

## 📊 Post-Deployment Verification

### 1. Check System Health

```bash
# Admin overview
curl -H "Authorization: Bearer <token>" http://localhost:8000/api/admin/overview

# Overview snapshot
curl -H "Authorization: Bearer <token>" http://localhost:8000/api/overview/snapshot

# API keys status
curl -H "Authorization: Bearer <token>" http://localhost:8000/api/keys/status
```

### 2. Verify Bot Caps

```python
# Should show exactly these caps:
# luno: 5 bots max
# binance: 10 bots max
# kucoin: 10 bots max
# bybit: 10 bots max
# kraken: 10 bots max
# bitget: 10 bots max
# gate: 10 bots max
```

### 3. Test Real-Time Updates

- Open dashboard
- Create a bot
- Verify WebSocket updates in browser console
- Check that overview updates in real-time

---

## 🛠 Admin Tools

### Factory Reset (DANGEROUS)

```bash
# Only keeps admin account, deletes everything else
python3 scripts/factory_reset_keep_admin.py \
    --email amarktainetwork@gmail.com \
    --confirm
```

### Clamp Bot Caps

```bash
# Enforce bot caps across all users
python3 scripts/clamp_bot_caps.py --execute
```

### User Reset

```bash
# Via API (requires admin token)
curl -X POST \
    -H "Authorization: Bearer <admin-token>" \
    http://localhost:8000/api/admin/users/<user-id>/reset
```

---

## 🎯 Monitoring

### Key Metrics to Watch

1. **Bot Count Per Exchange**
   - Endpoint: `/api/overview/snapshot`
   - Field: `per_exchange_bots`

2. **System Mode**
   - Paper Trading: Safe for testing
   - Live Trading: Real money
   - Autopilot: Auto-spawn enabled

3. **Profit Tracking**
   - Daily: Starts at Monday 00:00 UTC
   - Weekly: Last 7 days
   - Monthly: From day 1 of month

4. **Errors/Warnings**
   - Check `errors_warnings_count` in snapshot
   - Review admin panel for details

---

## 🚨 Troubleshooting

### Issue: Can't Login as Admin

**Solution:**
```bash
# Recreate admin user
cd scripts
export AMK_ADMIN_EMAIL=amarktainetwork@gmail.com
export AMK_ADMIN_PASS=<new-password>
python3 bootstrap_admin.py
```

### Issue: Bot Creation Fails with 500 Error

**Solution:**
```bash
# Run bot ID migration
python3 scripts/migrations/ensure_bot_ids.py
```

### Issue: API Keys Status Shows "Not Configured" But Keys Exist

**Solution:**
- Check that `AMARKTAI_FERNET_KEY` is set correctly
- Run key migration if needed
- Test endpoint: `POST /api/keys/{provider}/test`

### Issue: WebSocket Not Connecting

**Solution:**
- Check nginx WebSocket config
- Verify Redis is running
- Check firewall allows WebSocket connections

---

## 📞 Support

- **Email**: amarktainetwork@gmail.com
- **Documentation**: See [docs/INDEX.md](INDEX.md)
- **Issues**: Create GitHub issue

---

## ✅ Go-Live Checklist

- [ ] All environment variables set
- [ ] Migrations run successfully
- [ ] Admin user created
- [ ] Bot caps verified (5 for Luno, 10 for others)
- [ ] API keys encrypted properly
- [ ] Nginx configured and running
- [ ] SSL certificate installed (Let's Encrypt)
- [ ] WebSocket connections working
- [ ] Real-time updates functional
- [ ] Email sending works
- [ ] Smoke tests pass
- [ ] Monitoring dashboard accessible
- [ ] Admin panel accessible and functional
- [ ] Backups configured

---

**🎉 Ready for Production!**

Once all checks pass, you're ready to go live. Monitor the system closely for the first 24 hours.
