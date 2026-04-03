#!/bin/bash
# Amarktai Network - Fully Automated VPS Setup Script
# For Ubuntu 24.04 (Webdock VPS or similar)
# This script installs and configures everything needed for production deployment

set -e  # Exit on error

echo "🚀 Starting Amarktai Network VPS Setup..."
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if running as root
if [ "$EUID" -ne 0 ]; then 
    echo -e "${RED}❌ Please run as root or with sudo${NC}"
    exit 1
fi

echo -e "${GREEN}✅ Running with root privileges${NC}"

# ============================================================================
# 1. Update System
# ============================================================================
echo ""
echo "📦 Updating system packages..."
apt update && apt upgrade -y

# ============================================================================
# 2. Install Required Packages
# ============================================================================
echo ""
echo "📦 Installing required packages..."

# Install Python 3 (Ubuntu 24.04 comes with 3.12 by default)
apt install -y \
    python3 \
    python3-venv \
    python3-pip \
    nginx \
    git \
    curl \
    wget \
    docker.io \
    docker-compose

# Install Node.js 20.x from NodeSource (recommended for Ubuntu 24.04)
# Remove Ubuntu npm package if installed to avoid conflicts with NodeSource
echo "📦 Checking for Node.js installation..."

# Check if Ubuntu npm package is installed (causes conflicts)
if dpkg -l | grep -q "^ii.*npm.*ubuntu"; then
    echo -e "${YELLOW}⚠️  Removing Ubuntu npm package to avoid conflicts...${NC}"
    apt remove -y npm
    apt autoremove -y
fi

# Clean up broken state if exists
if dpkg -l | grep -E "^iF|^iU" | grep -q "nodejs\|npm"; then
    echo -e "${YELLOW}⚠️  Fixing broken package state...${NC}"
    dpkg --configure -a
    apt --fix-broken install -y
fi

# Install Node.js from NodeSource if not present or if Ubuntu version detected
if ! command -v node &> /dev/null || dpkg -l | grep -q "nodejs.*ubuntu"; then
    echo "📦 Installing Node.js 20.x from NodeSource..."
    # Remove any existing nodejs packages
    apt remove -y nodejs npm 2>/dev/null || true
    apt autoremove -y
    
    # Install from NodeSource
    curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
    apt install -y nodejs
    echo -e "${GREEN}✅ Node.js installed from NodeSource${NC}"
else
    NODE_VERSION=$(node --version)
    echo -e "${GREEN}✅ Node.js already installed: ${NODE_VERSION}${NC}"
fi

# 3. Install Yarn (if not already installed)
# ============================================================================
# 3. Install Yarn
# ============================================================================
echo ""
if ! command -v yarn &> /dev/null; then
    echo "📦 Installing Yarn..."
    npm install -g yarn
    echo -e "${GREEN}✅ Yarn installed${NC}"
else
    YARN_VERSION=$(yarn --version)
    echo -e "${GREEN}✅ Yarn already installed: ${YARN_VERSION}${NC}"
fi

# ============================================================================
# 4. Setup MongoDB (Docker)
# ============================================================================
echo ""
echo "🗄️ Setting up MongoDB..."
systemctl start docker
systemctl enable docker

# Check if MongoDB container already exists
if docker ps -a | grep -q amarktai-mongo; then
    echo "MongoDB container already exists, starting it..."
    docker start amarktai-mongo || true
else
    echo "Creating new MongoDB container..."
    docker run -d \
        --name amarktai-mongo \
        --restart always \
        -p 127.0.0.1:27017:27017 \
        -v amarktai-mongo-data:/data/db \
        mongo:7
fi

echo -e "${GREEN}✅ MongoDB started on 127.0.0.1:27017${NC}"

# ============================================================================
# 5. Create Application Directory and Setup Repository
# ============================================================================
echo ""
echo "📁 Setting up application directory..."
mkdir -p /var/amarktai/app
cd /var/amarktai/app

# Check if this is already a git repository
if [ -d ".git" ]; then
    echo "Repository already cloned, pulling latest changes..."
    git pull || echo "Warning: Could not pull latest changes"
else
    echo -e "${YELLOW}⚠️ Repository not cloned yet${NC}"
    echo "Please clone your repository to /var/amarktai/app"
    echo "Example: git clone YOUR_REPO_URL /var/amarktai/app"
    echo ""
    read -p "Have you cloned the repository? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo -e "${RED}❌ Please clone the repository and run this script again${NC}"
        exit 1
    fi
fi

# ============================================================================
# 6. Backend Setup
# ============================================================================
echo ""
echo "🐍 Setting up Python backend..."
cd /var/amarktai/app/backend

# Create virtual environment using system python3 (3.12 on Ubuntu 24.04)
if [ ! -d ".venv" ]; then
    python3 -m venv .venv
    echo -e "${GREEN}✅ Virtual environment created${NC}"
else
    echo -e "${YELLOW}⚠️ Virtual environment already exists${NC}"
# Create virtual environment
if [ ! -d ".venv" ]; then
    python3.11 -m venv .venv
fi

source .venv/bin/activate

# Install dependencies
pip install --upgrade pip
if [ -f "requirements.txt" ]; then
    pip install -r requirements.txt
    echo -e "${GREEN}✅ Python dependencies installed${NC}"
else
    echo -e "${RED}❌ requirements.txt not found${NC}"
    exit 1
fi

# Copy .env file if it doesn't exist
if [ ! -f .env ]; then
    echo ""
    echo -e "${YELLOW}⚠️ Creating .env file from example${NC}"
    if [ -f ../.env.example ]; then
        cp ../.env.example .env
    else
        echo -e "${RED}❌ .env.example not found!${NC}"
        echo "Creating minimal .env file..."
        cat > .env << 'EOF'
MONGO_URI=mongodb://127.0.0.1:27017
MONGO_DB_NAME=amarktai
JWT_SECRET=change-me-$(openssl rand -hex 32)
ADMIN_PASSWORD=change-me-$(openssl rand -base64 24)
OPENAI_API_KEY=
ENABLE_REALTIME=true
SMTP_ENABLED=false
MAX_BOTS=10
MAX_DAILY_LOSS_PERCENT=5
LOG_LEVEL=INFO
ENVIRONMENT=production
EOF
    fi
    echo -e "${RED}❌ CRITICAL: Edit /var/amarktai/app/backend/.env with your API keys!${NC}"
    echo "Required: OPENAI_API_KEY, JWT_SECRET (change defaults), ADMIN_PASSWORD"
fi

echo -e "${GREEN}✅ Backend setup complete${NC}"

# ============================================================================
# 7. Frontend Setup
# ============================================================================
echo ""
echo "⚛️ Setting up React frontend..."
cd /var/amarktai/app/frontend

# Install dependencies
if [ -f yarn.lock ]; then
    yarn install --frozen-lockfile
elif [ -f package-lock.json ]; then
    npm ci
else
    npm install
fi

# Build frontend
if [ -f yarn.lock ]; then
    yarn build
else
    npm run build
fi

echo -e "${GREEN}✅ Frontend build complete${NC}"

# ============================================================================
# 8. Setup Nginx
# ============================================================================
echo ""
echo "🌐 Setting up Nginx..."

# Copy nginx config
cp /var/amarktai/app/deployment/nginx/amarktai.conf /etc/nginx/sites-available/amarktai

# Enable site
ln -sf /etc/nginx/sites-available/amarktai /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default  # Remove default site

# Test nginx config
if nginx -t; then
    systemctl reload nginx
    echo -e "${GREEN}✅ Nginx configured and reloaded${NC}"
else
    echo -e "${RED}❌ Nginx configuration test failed!${NC}"
    exit 1
fi

# ============================================================================
# 9. Setup Systemd Service
# ============================================================================
echo ""
echo "🔧 Setting up systemd service..."
cp /var/amarktai/app/deployment/systemd/amarktai-api.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable amarktai-api
systemctl restart amarktai-api

# Wait for service to start
sleep 5

if systemctl is-active --quiet amarktai-api; then
    echo -e "${GREEN}✅ API service started successfully${NC}"
else
    echo -e "${RED}❌ API service failed to start!${NC}"
    echo "Check logs with: journalctl -u amarktai-api -n 50"
    exit 1
fi

# ============================================================================
# 10. Set Permissions
# ============================================================================
echo ""
echo "🔐 Setting permissions..."
chown -R www-data:www-data /var/amarktai/app
chmod -R 755 /var/amarktai/app

# ============================================================================
# 11. Setup Firewall (UFW)
# ============================================================================
echo ""
echo "🔥 Configuring firewall..."
ufw allow 22/tcp   # SSH
ufw allow 80/tcp   # HTTP
ufw allow 443/tcp  # HTTPS
ufw --force enable
echo -e "${GREEN}✅ Firewall configured${NC}"

# ============================================================================
# 12. Run Smoke Tests
# ============================================================================
echo ""
echo "🧪 Running smoke tests..."
cd /var/amarktai/app/deployment

if [ -f smoke_test.sh ]; then
    chmod +x smoke_test.sh
    if ./smoke_test.sh; then
        echo -e "${GREEN}✅ All smoke tests passed!${NC}"
    else
        echo -e "${YELLOW}⚠️ Some smoke tests failed - check the output above${NC}"
    fi
else
    echo -e "${YELLOW}⚠️ smoke_test.sh not found, skipping tests${NC}"
fi

# ============================================================================
# 13. Final Status Check
# ============================================================================
echo ""
echo "📊 System Status:"
echo ""
echo "=== Docker (MongoDB) ==="
docker ps | grep amarktai-mongo || echo "MongoDB container not running!"
echo ""
echo "=== Amarktai API Service ==="
systemctl status amarktai-api --no-pager | head -10
echo ""
echo "=== Nginx ==="
systemctl status nginx --no-pager | head -5
echo ""
echo "=== Backend Port Check ==="
ss -lntp | grep :8000 || echo "Backend not listening on port 8000!"
echo ""

# ============================================================================
# 14. Verification Commands
# ============================================================================
echo ""
echo -e "${GREEN}🎉 Amarktai Network VPS Setup Complete!${NC}"
echo ""
echo "=== Verification Commands ==="
echo "1. Check API service:"
echo "   systemctl status amarktai-api"
echo ""
echo "2. Check backend is listening:"
echo "   ss -lntp | grep :8000"
echo ""
echo "3. Test health endpoint:"
echo "   curl -i http://127.0.0.1:8000/api/health/ping"
echo ""
echo "4. Check OpenAPI schema:"
echo "   curl http://127.0.0.1:8000/openapi.json | jq '.paths | keys[]' | grep -E '^/api/(health|alerts|realtime)'"
echo ""
echo "5. Test SSE streaming (Ctrl+C to stop):"
echo "   curl -N http://127.0.0.1:8000/api/realtime/events"
echo ""
echo "=== Next Steps ==="
echo "1. Edit /var/amarktai/app/backend/.env with your API keys"
echo "2. Restart service: sudo systemctl restart amarktai-api"
echo "3. Optional: Setup SSL with certbot"
echo "   sudo apt install certbot python3-certbot-nginx"
echo "   sudo certbot --nginx -d yourdomain.com"
echo ""
echo "Access your app at: http://YOUR_SERVER_IP"
echo ""
