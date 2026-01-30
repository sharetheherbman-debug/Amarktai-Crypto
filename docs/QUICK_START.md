# Quick Start - Production Deployment

## 🚀 Deploy Amarktai Network in 5 Minutes

### Prerequisites
- Ubuntu 24.04 Server (fresh install)
- Root/sudo access
- 2GB+ RAM, 20GB+ disk

### Step 1: Clone Repository
```bash
git clone https://github.com/sharetheherbman-debug/Amarktai-Network---Deployment.git
cd Amarktai-Network---Deployment
```

### Step 2: One-Command Install
```bash
sudo bash deployment/install.sh
```

**What it does:**
- Installs Python 3.12, Node.js, Nginx, Redis, Docker
- Sets up MongoDB with secure random password
- Creates virtual environment and installs dependencies
- Validates Python syntax
- Configures systemd service
- Runs comprehensive smoke tests
- Reports PASS/FAIL status

**Expected time:** 5-10 minutes

### Step 3: Verify Installation
```bash
# Check service status
sudo systemctl status amarktai-api.service

# Run smoke tests manually
bash tools/smoke_test.sh
```

**Expected output:**
```
═══════════════════════════════════════
   SMOKE TEST RESULT: ✅ PASS
═══════════════════════════════════════
```

### Step 4: Configure Environment (Optional)
```bash
# Edit .env for custom settings
nano backend/.env
```

**Critical variables:**
- `MONGO_URL` - Auto-generated, check console output for password
- `JWT_SECRET` - Generate: `openssl rand -hex 32`
- `ENCRYPTION_KEY` - Generate: `python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`
- `INVITE_CODE` - Default: AMARKTAI2024

### Step 5: Setup Nginx & SSL (Optional)
```bash
# Copy nginx config
sudo cp deployment/nginx-amarktai.conf /etc/nginx/sites-available/amarktai
sudo ln -s /etc/nginx/sites-available/amarktai /etc/nginx/sites-enabled/

# Update server_name in config
sudo nano /etc/nginx/sites-available/amarktai

# Test and reload
sudo nginx -t
sudo systemctl reload nginx

# Install SSL certificate
sudo apt install certbot python3-certbot-nginx
sudo certbot --nginx -d your-domain.com
```

### Step 6: Create First Admin User
```bash
# 1. Register via API (change values)
curl -X POST http://localhost:8000/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "email": "admin@example.com",
    "password": "YourSecurePassword123!",
    "first_name": "Admin",
    "invite_code": "AMARKTAI2024"
  }'

# 2. Set admin flag in MongoDB
docker exec -it amarktai-mongo mongosh -u amarktai -p <PASSWORD>
use amarktai_trading
db.users.updateOne(
  { "email": "admin@example.com" },
  { $set: { "is_admin": true } }
)
exit
```

### Step 7: Access Dashboard
Open browser and navigate to:
- Local: `http://localhost:8000`
- With Nginx: `https://your-domain.com`

---

## 🔧 Common Commands

### Service Management
```bash
# Start service
sudo systemctl start amarktai-api

# Stop service
sudo systemctl stop amarktai-api

# Restart service
sudo systemctl restart amarktai-api

# Check status
sudo systemctl status amarktai-api

# View logs
sudo journalctl -u amarktai-api -f
```

### Database Access
```bash
# Connect to MongoDB
docker exec -it amarktai-mongo mongosh -u amarktai -p <PASSWORD>

# List databases
show dbs

# Use amarktai database
use amarktai_trading

# List collections
show collections

# Query users
db.users.find()
```

### Testing
```bash
# Run smoke tests
bash tools/smoke_test.sh

# Test health endpoint
curl http://localhost:8000/api/health/ping

# Test platform registry
curl http://localhost:8000/api/platforms
```

---

## 🆘 Troubleshooting

### Service won't start
```bash
# Check logs
sudo journalctl -u amarktai-api -n 100

# Common issues:
# - MongoDB not running: docker ps | grep amarktai-mongo
# - Missing .env: ls -la backend/.env
# - Port 8000 in use: sudo netstat -tlnp | grep 8000
```

### MongoDB connection failed
```bash
# Check container
docker ps | grep amarktai-mongo

# View logs
docker logs amarktai-mongo

# Restart if needed
docker restart amarktai-mongo
```

### Smoke tests fail
```bash
# Wait for service to fully start
sleep 30

# Check if service is running
sudo systemctl is-active amarktai-api

# Run tests with verbose output
bash -x tools/smoke_test.sh
```

### Can't access dashboard
```bash
# Check if service is listening
sudo netstat -tlnp | grep 8000

# Test locally
curl http://localhost:8000/api/health/ping

# Check nginx config
sudo nginx -t

# Check firewall
sudo ufw status
```

---

## 📋 Post-Installation Checklist

- [ ] Service is running: `sudo systemctl status amarktai-api`
- [ ] Smoke tests pass: `bash tools/smoke_test.sh`
- [ ] Health endpoint responds: `curl http://localhost:8000/api/health/ping`
- [ ] Platform registry returns 5 platforms: `curl http://localhost:8000/api/platforms`
- [ ] .env configured with secure secrets
- [ ] MongoDB password saved securely
- [ ] First admin user created
- [ ] Nginx configured (optional)
- [ ] SSL certificates installed (optional)
- [ ] Firewall configured (80, 443 open)

---

## 🔐 Security Best Practices

1. **Change default secrets:**
   ```bash
   # Generate new JWT secret
   openssl rand -hex 32
   
   # Generate new encryption key
   python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
   ```

2. **Save MongoDB password:**
   - Password is printed during installation
   - Store in password manager
   - Update MONGO_URL in .env if needed

3. **Change invite code:**
   ```bash
   # Edit .env
   nano backend/.env
   # Set: INVITE_CODE=YourNewSecretCode123
   ```

4. **Setup firewall:**
   ```bash
   sudo ufw allow 22/tcp
   sudo ufw allow 80/tcp
   sudo ufw allow 443/tcp
   sudo ufw enable
   ```

5. **Enable automatic security updates:**
   ```bash
   sudo apt install unattended-upgrades
   sudo dpkg-reconfigure -plow unattended-upgrades
   ```

---

## 🎯 Next Steps

1. **Test paper trading:**
   - Configure user API keys for exchanges
   - Create bots in paper mode
   - Monitor for 7 days

2. **Enable live trading (when ready):**
   ```bash
   nano backend/.env
   # Set: ENABLE_TRADING=true
   sudo systemctl restart amarktai-api
   ```

3. **Enable autopilot (when confident):**
   ```bash
   nano backend/.env
   # Set: ENABLE_AUTOPILOT=true
   sudo systemctl restart amarktai-api
   ```

4. **Monitor system:**
   - Check logs daily: `sudo journalctl -u amarktai-api --since today`
   - Review bot performance
   - Verify bodyguard is working

---

## 📚 Documentation

- **Full deployment guide:** `DEPLOYMENT_GUIDE.md`
- **Production summary:** `PRODUCTION_SUMMARY.md`
- **Cleanup documentation:** `CLEAN_REPO_RULES.md`
- **Environment variables:** `.env.example`

---

## ✅ System is Ready!

If all smoke tests pass, your Amarktai Network is **production-ready** and can accept users.

**Support:** Check logs first, then review documentation for detailed troubleshooting.
