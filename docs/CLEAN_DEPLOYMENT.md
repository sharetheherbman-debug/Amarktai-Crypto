# Clean Deployment Guide

## Overview
This guide provides step-by-step instructions for deploying the Amarktai Network from a clean repository state without server-side patching.

## Prerequisites
- Ubuntu 24.04 LTS
- Python 3.10+
- Node.js 18+ (for frontend)
- MongoDB (running and accessible)
- Nginx (for reverse proxy)

## Deployment Steps

### 1. Pull Latest Code

```bash
cd /opt/amarktai-network
git pull origin main
```

### 2. Verify Repository Integrity

Run the verification script to ensure all Python files compile correctly:

```bash
./scripts/verify_repo.sh
```

Expected output:
```
✅ Repository verification PASSED
All Python files compile successfully.
```

### 3. Backend Setup

#### Create Virtual Environment (if not exists)

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
```

#### Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Environment Configuration

Copy and configure environment variables:

```bash
cp .env.example .env
# Edit .env with your configuration
nano .env
```

Required variables:
- `MONGO_URI` - MongoDB connection string
- `JWT_SECRET` - Secret for JWT token generation
- `ENCRYPTION_KEY` - Fernet encryption key for API keys
- `OPENAI_API_KEY` (optional) - For AI features

### 5. Pre-deployment Checks

#### Verify Python Syntax

```bash
./scripts/verify_repo.sh
```

#### Check Database Connection

```bash
cd backend
source .venv/bin/activate
python3 -c "from database import connect; import asyncio; asyncio.run(connect()); print('✅ Database connected')"
```

### 6. Restart Services

#### Restart Backend Service

```bash
sudo systemctl restart amarktai-api
```

#### Check Service Status

```bash
sudo systemctl status amarktai-api
```

#### View Logs

```bash
sudo journalctl -u amarktai-api -f
```

### 7. Run Smoke Tests

Run the smoke test suite to verify all critical endpoints:

```bash
./scripts/smoke.sh
```

For production server:
```bash
BASE_URL=https://your-domain.com ./scripts/smoke.sh
```

Expected output:
```
✅ ALL SMOKE TESTS PASSED
System is ready for deployment.
```

### 8. Frontend Build (if needed)

If frontend changes were made:

```bash
cd frontend
npm install
npm run build
```

Copy build to Nginx serve directory:
```bash
sudo cp -r build/* /var/www/amarktai/
```

### 9. Reload Nginx

```bash
sudo nginx -t  # Test configuration
sudo systemctl reload nginx
```

## Verification Checklist

After deployment, verify:

- [ ] Backend service is running (`systemctl status amarktai-api`)
- [ ] Health endpoint responds: `curl http://localhost:8000/api/health/ping`
- [ ] Frontend loads in browser
- [ ] Login functionality works
- [ ] API Keys page loads and shows all 10 providers
- [ ] No errors in logs (`journalctl -u amarktai-api -n 100`)

## Critical Endpoints to Test

1. **Health Check**: `GET /api/health/ping` → Should return `{"status":"pong"}`
2. **Providers List**: `GET /api/keys/providers` → Should return 10 providers
3. **OpenAPI Schema**: `GET /openapi.json` → Should include `/api/keys/test`

## Supported Exchanges

The system supports exactly **7 exchanges**:
1. Luno
2. Binance
3. KuCoin
4. Bybit
5. Kraken
6. Bitget
7. Gate.io

Plus **3 AI providers**:
- OpenAI
- Flokx AI
- Fetch.ai

**Total: 10 providers**

## Troubleshooting

### Router Mount Failure

If you see "Critical router mount failure: API Keys (Unified)":

1. Check imports in `backend/routes/keys.py`
2. Verify `backend/services/provider_registry.py` exists and imports correctly
3. Check encryption helpers in `backend/routes/api_key_management.py`

### Route Collision

If routes are not working as expected:

1. Check route order in `backend/routes/keys.py`:
   - `/save` should come before `/{provider}`
   - `/test` should come before `/{provider}`
2. Run tests: `cd tests && pytest test_api_keys.py -v`

### Python Compilation Errors

If `verify_repo.sh` fails:

1. Check the specific file mentioned in error
2. Fix syntax errors
3. Re-run verification
4. Do NOT proceed with deployment until all files compile

## Rollback Procedure

If deployment fails:

```bash
# 1. Stop the service
sudo systemctl stop amarktai-api

# 2. Checkout previous working commit
git log --oneline | head -10  # Find last known good commit
git checkout <commit-hash>

# 3. Restart service
sudo systemctl start amarktai-api

# 4. Verify
./scripts/smoke.sh
```

## Monitoring

After deployment, monitor:

```bash
# Real-time logs
sudo journalctl -u amarktai-api -f

# Recent errors
sudo journalctl -u amarktai-api --since "5 minutes ago" --no-pager | grep -i error

# Service status
watch -n 2 'systemctl status amarktai-api'
```

## Support

For issues:
1. Check logs: `sudo journalctl -u amarktai-api -n 100`
2. Run verification: `./scripts/verify_repo.sh`
3. Run smoke tests: `./scripts/smoke.sh`
4. Review recent commits: `git log --oneline -10`

## Next Steps

After successful deployment:

1. Bootstrap admin user (if first deployment):
   ```bash
   python3 backend/scripts/bootstrap_admin.py
   ```

2. Configure API keys for exchanges (via UI at `/settings`)

3. Enable real-time features in `.env`:
   ```
   ENABLE_REALTIME=true
   ```

4. Monitor system health via dashboard
