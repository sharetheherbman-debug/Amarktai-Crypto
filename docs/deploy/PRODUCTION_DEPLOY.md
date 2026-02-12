# Production Deployment Guide

Complete guide for deploying Amarktai Network to Ubuntu 24.04 production environment.

## Prerequisites

- Ubuntu 24.04 LTS server
- Root or sudo access
- MongoDB instance (local or Atlas)
- API keys for supported exchanges

## Supported Exchanges (7 Only)

The system supports **exactly 7 exchanges** with enforced bot caps:

1. **Luno**: Max 5 bots (paper + live combined)
2. **Binance**: Max 10 bots (paper + live combined)
3. **KuCoin**: Max 10 bots (paper + live combined)
4. **Bybit**: Max 10 bots (paper + live combined)
5. **Kraken**: Max 10 bots (paper + live combined)
6. **Bitget**: Max 10 bots (paper + live combined)
7. **Gate.io**: Max 10 bots (paper + live combined)

**Auto-growth requirement:** >= R1000 realized profit per exchange before auto-spawn/mutate.

## Quick Start

```bash
# 1. Update system
sudo apt update && sudo apt upgrade -y

# 2. Install dependencies
sudo apt install -y python3.12 python3.12-venv python3-pip nginx redis-server git

# 3. Clone repository
cd /opt
sudo git clone https://github.com/sharetheherbman-debug/Amarktai-Network---Deployment.git amarktai
cd amarktai

# 4. Backend setup
cd backend
python3.12 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
deactivate

# 5. Configure environment
cp .env.example .env
# Edit .env with your settings

# 6. Create systemd service
sudo nano /etc/systemd/system/amarktai-backend.service
```

## MongoDB Indexes

Create required indexes to prevent errors:

```bash
cd /opt/amarktai/backend
source venv/bin/activate
python3 << 'ENDPYTHON'
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient

async def create_indexes():
    client = AsyncIOMotorClient("mongodb://localhost:27017")
    db = client.amarktai_network
    
    # Bots: unique id index (prevents null duplicate key errors)
    await db.bots.create_index("id", unique=True)
    await db.bots.create_index("user_id")
    await db.bots.create_index("exchange")
    
    # Users
    await db.users.create_index("id", unique=True)
    await db.users.create_index("email", unique=True)
    
    print("✅ Indexes created")
    
asyncio.run(create_indexes())
ENDPYTHON
deactivate
```

## Environment Variables

Key environment variables in `.env`:

```env
# MongoDB
MONGODB_URI=mongodb://localhost:27017
DB_NAME=amarktai_network

# Security
JWT_SECRET=<generate-strong-secret>
FERNET_KEY=<base64-encoded-fernet-key>

# Admin
ADMIN_EMAIL=amarktainetwork@gmail.com
ADMIN_PASSWORD_HASH=<bcrypt-hash>

# Trading
DEFAULT_PAPER_TRADING=true
DEFAULT_LIVE_TRADING=false

# Redis
REDIS_HOST=localhost
REDIS_PORT=6379

# Bot Rules (enforced automatically)
PROFIT_THRESHOLD_ZAR=1000
REINVEST_PERCENTAGE=80
```

Generate Fernet key:
```bash
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

## Systemd Service

Create `/etc/systemd/system/amarktai-backend.service`:

```ini
[Unit]
Description=Amarktai Network Backend API
After=network.target mongod.service redis.service

[Service]
Type=simple
User=www-data
WorkingDirectory=/opt/amarktai/backend
Environment="PATH=/opt/amarktai/backend/venv/bin"
ExecStart=/opt/amarktai/backend/venv/bin/uvicorn server:app --host 0.0.0.0 --port 8000 --workers 4
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

## Start Services

```bash
sudo systemctl daemon-reload
sudo systemctl enable amarktai-backend
sudo systemctl start amarktai-backend
sudo systemctl status amarktai-backend
```

## Verification

Run smoke tests:

```bash
cd /opt/amarktai
./scripts/smoke.sh
```

Test endpoints:

```bash
curl http://localhost:8000/api/health/ping
# Should return: {"status":"ok","message":"pong"}
```

## Critical Rules Enforced

1. **Bot Caps**: Luno max 5, others max 10 per exchange
2. **Profit Gating**: >= R1000 realized profit required per exchange
3. **Reinvestment**: 50% of realized profit when at cap
4. **Exchange Validation**: Only 7 exchanges accepted
5. **Unique Bot IDs**: Every bot has non-null unique UUID
6. **JSON Serialization**: No ObjectId errors in responses

## Support

- GitHub: https://github.com/sharetheherbman-debug/Amarktai-Network---Deployment/issues
- Email: amarktainetwork@gmail.com
