# Deployment Guide - Amarktai Network

## Production Deployment Checklist

### Required Environment Variables

#### Critical - Encryption Keys
```bash
# API Key Encryption (REQUIRED for production)
# Generate with: python3 -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'
AMARKTAI_FERNET_KEY=<your-fernet-key>
# OR (fallback):
FERNET_KEY=<your-fernet-key>

# JWT Authentication
JWT_SECRET=<your-jwt-secret>
```

#### MongoDB Configuration
```bash
# MongoDB Connection String
MONGO_URL=mongodb://username:password@localhost:27017/amarktai
```

### MongoDB Directory Setup (Native MongoDB)

If you're using native MongoDB (not Docker), you **MUST** create the required directories before starting the service:

```bash
# Create MongoDB directories
sudo mkdir -p /var/lib/mongodb
sudo mkdir -p /var/log/mongodb
sudo touch /var/log/mongodb/mongod.log

# Set ownership to mongodb user
sudo chown -R mongodb:mongodb /var/lib/mongodb
sudo chown -R mongodb:mongodb /var/log/mongodb

# Set permissions
sudo chmod 755 /var/lib/mongodb
sudo chmod 755 /var/log/mongodb
sudo chmod 644 /var/log/mongodb/mongod.log
```

**Note:** These directories are referenced in `/etc/mongod.conf`:
- `storage.dbPath: /var/lib/mongodb`
- `systemLog.path: /var/log/mongodb/mongod.log`

### Quick Start (Ubuntu 24.04 VPS)

#### 1. Clone Repository
```bash
git clone https://github.com/amarktainetwork-blip/Amarktai-Crypto.git
cd Amarktai-Crypto
```

#### 2. Create Virtual Environment
```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

#### 3. Generate Encryption Key
```bash
# Generate Fernet key for API key encryption
python3 -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'
# Copy the output to your .env file as AMARKTAI_FERNET_KEY
```

#### 4. Configure Environment
```bash
# Copy example .env
cp .env.example .env

# Edit .env and set:
# - AMARKTAI_FERNET_KEY (from step 3)
# - JWT_SECRET (random string)
# - MONGO_URL (your MongoDB connection string)
nano .env
cd ..
```

#### 5. Build Frontend
```bash
# Install Node.js dependencies and build
cd frontend
npm install
npm run build
cd ..
```

#### 6. Setup MongoDB (if using native MongoDB)
```bash
# Install MongoDB
sudo apt-get update
sudo apt-get install -y mongodb-org

# Create required directories (CRITICAL!)
sudo mkdir -p /var/lib/mongodb /var/log/mongodb
sudo chown -R mongodb:mongodb /var/lib/mongodb /var/log/mongodb
sudo chmod 755 /var/lib/mongodb /var/log/mongodb

# Start MongoDB
sudo systemctl enable mongod
sudo systemctl start mongod
sudo systemctl status mongod
```

#### 6. Run Preflight Checks
```bash
# Run doctor script to verify everything is ready
./scripts/doctor.sh
```

**Expected:** `✅ PERFECT HEALTH - GO-LIVE READY!` or minimal warnings

#### 7. Start the API
```bash
# Using systemd (production)
sudo systemctl start amarktai-api
sudo systemctl status amarktai-api

# OR using uvicorn directly (development)
cd backend
source .venv/bin/activate
uvicorn server:app --host 127.0.0.1 --port 8000
```

#### 8. Verify Deployment
```bash
# Test health endpoint
curl http://127.0.0.1:8000/api/health/ping

# Run smoke test
./scripts/smoke_local.sh
```

Expected output: `✅ SMOKE TEST PASSED`

### Troubleshooting

#### Error: "No module named 'routes.api_key_management'"
**Solution:** Ensure `routes/api_key_management.py` exists and exports `encrypt_api_key` and `decrypt_api_key` functions.

```bash
# Verify import works
cd backend
python3 -c "from routes.api_key_management import encrypt_api_key, decrypt_api_key"
```

#### Error: "Critical router mount failure: API Keys (Unified)"
**Cause:** The `routes.keys` module cannot import encryption functions from `routes.api_key_management`.

**Solution:** 
1. Verify `routes/api_key_management.py` exists
2. Run preflight check: `./scripts/doctor.sh`
3. Check logs: `journalctl -u amarktai-api -n 50`

#### Error: "NonExistentPath: Data directory /var/lib/mongodb not found"
**Cause:** MongoDB directories don't exist or have wrong permissions.

**Solution:**
```bash
# Create directories
sudo mkdir -p /var/lib/mongodb /var/log/mongodb
sudo chown -R mongodb:mongodb /var/lib/mongodb /var/log/mongodb
sudo chmod 755 /var/lib/mongodb /var/log/mongodb

# Restart MongoDB
sudo systemctl restart mongod
```

#### Error: "Port 8000 already in use"
**Solution:**
```bash
# Find process using port 8000
sudo lsof -i :8000

# Kill the process (replace PID)
sudo kill <PID>
```

### Deployment Verification Commands

After deployment, verify with these commands:

```bash
# 1. Run preflight checks
./scripts/doctor.sh

# 2. Check MongoDB is running
sudo systemctl status mongod

# 3. Check API service is running
sudo systemctl status amarktai-api

# 4. Test health endpoint
curl http://127.0.0.1:8000/api/health/ping

# 5. Run full smoke test
./scripts/smoke_local.sh
```

### Production Hardening

1. **Set strong encryption keys** - Never use defaults in production
2. **MongoDB security** - Enable authentication, use strong passwords
3. **Firewall** - Only expose port 443 (nginx), keep 8000 internal
4. **SSL/TLS** - Configure nginx with Let's Encrypt certificates
5. **Monitoring** - Set up logging and alerting for errors

### Architecture

- **API Server**: FastAPI on uvicorn (127.0.0.1:8000)
- **Web Server**: Nginx (proxy to API, serves frontend)
- **Database**: MongoDB (27017)
- **Process Manager**: systemd (amarktai-api.service)

### Files and Locations

```
/var/amarktai/app/               # Application root
├── backend/
│   ├── .venv/                   # Python virtual environment
│   ├── .env                     # Environment configuration
│   ├── server.py                # FastAPI application
│   └── routes/
│       ├── api_key_management.py  # Encryption utilities
│       └── keys.py              # API keys router
├── frontend/                    # React frontend
└── deployment/
    ├── amarktai-api.service     # Systemd service file
    └── nginx-amarktai.conf      # Nginx configuration

/var/lib/mongodb/                # MongoDB data directory
/var/log/mongodb/                # MongoDB logs
/var/log/amarktai/               # Application logs
```

### Support

For issues or questions:
1. Check logs: `journalctl -u amarktai-api -f`
2. Run diagnostics: `./scripts/doctor.sh`
3. Review this guide's troubleshooting section
