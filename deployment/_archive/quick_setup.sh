#!/bin/bash

# Quick Setup Script for Amarktai Network
# Automates initial deployment on Ubuntu 24.04

set -e

echo "🚀 Amarktai Network - Quick Setup"
echo "=================================="
echo ""

# Color codes
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

# Check if running as root
if [ "$EUID" -ne 0 ]; then 
    echo -e "${RED}Please run as root (use sudo)${NC}"
    exit 1
fi

# Get the actual user who called sudo
ACTUAL_USER=${SUDO_USER:-$USER}
REPO_DIR="/var/www/amarktai"

echo "Installing as user: $ACTUAL_USER"
echo "Repository location: $REPO_DIR"
echo ""

# Step 1: Install system dependencies
echo -e "${YELLOW}Step 1: Installing system dependencies...${NC}"
apt-get update
apt-get install -y python3 python3-pip python3-venv nginx mongodb git curl

# Enable and start MongoDB
systemctl enable mongod
systemctl start mongod
echo -e "${GREEN}✅ System dependencies installed${NC}"
echo ""

# Step 2: Check if repo already exists
if [ ! -d "$REPO_DIR" ]; then
    echo -e "${YELLOW}Step 2: Cloning repository...${NC}"
    mkdir -p /var/www
    cd /var/www
    
    # If this script is running from the repo, copy it
    if [ -f "$(pwd)/deployment/quick_setup.sh" ]; then
        cp -r "$(pwd)" "$REPO_DIR"
        chown -R $ACTUAL_USER:$ACTUAL_USER "$REPO_DIR"
    else
        echo -e "${RED}Repository not found. Please clone manually:${NC}"
        echo "  cd /var/www"
        echo "  git clone <repository-url> amarktai"
        exit 1
    fi
else
    echo -e "${GREEN}Repository already exists at $REPO_DIR${NC}"
fi

cd "$REPO_DIR"
echo -e "${GREEN}✅ Repository ready${NC}"
echo ""

# Step 3: Setup environment file
echo -e "${YELLOW}Step 3: Setting up environment...${NC}"
if [ ! -f ".env" ]; then
    if [ -f ".env.example" ]; then
        cp .env.example .env
        echo -e "${YELLOW}⚠️  .env file created from template${NC}"
        echo -e "${YELLOW}⚠️  IMPORTANT: Edit .env and configure:${NC}"
        echo "    - MONGO_URL (if not localhost)"
        echo "    - JWT_SECRET (MUST change!)"
        echo "    - OPENAI_API_KEY (for AI features)"
        echo "    - SMTP credentials (for email alerts)"
        echo ""
        echo -e "${RED}Press Enter after editing .env...${NC}"
        read -p ""
    else
        echo -e "${RED}No .env.example found!${NC}"
        exit 1
    fi
else
    echo -e "${GREEN}.env file already exists${NC}"
fi
echo ""

# Step 4: Install Python backend
echo -e "${YELLOW}Step 4: Installing Python backend...${NC}"
cd backend

# Create virtual environment
if [ ! -d "venv" ]; then
    sudo -u $ACTUAL_USER python3 -m venv venv
fi

# Install dependencies
sudo -u $ACTUAL_USER bash -c "source venv/bin/activate && pip install --upgrade pip && pip install -r requirements.txt"
echo -e "${GREEN}✅ Python backend installed${NC}"
echo ""

# Step 5: Setup systemd service
echo -e "${YELLOW}Step 5: Setting up systemd service...${NC}"
cd "$REPO_DIR"

if [ -f "deployment/amarktai-api.service" ]; then
    # Update service file with actual paths
    sed -i "s|/var/www/amarktai|$REPO_DIR|g" deployment/amarktai-api.service
    sed -i "s|User=.*|User=$ACTUAL_USER|g" deployment/amarktai-api.service
    
    cp deployment/amarktai-api.service /etc/systemd/system/
    systemctl daemon-reload
    systemctl enable amarktai-api
    echo -e "${GREEN}✅ Systemd service configured${NC}"
else
    echo -e "${YELLOW}⚠️  No systemd service file found${NC}"
fi
echo ""

# Step 6: Configure Nginx
echo -e "${YELLOW}Step 6: Configuring Nginx...${NC}"

if [ -f "deployment/nginx-amarktai.conf" ]; then
    # Update nginx config with actual paths
    sed -i "s|/var/www/amarktai|$REPO_DIR|g" deployment/nginx-amarktai.conf
    
    cp deployment/nginx-amarktai.conf /etc/nginx/sites-available/amarktai
    ln -sf /etc/nginx/sites-available/amarktai /etc/nginx/sites-enabled/amarktai
    
    # Test nginx config
    nginx -t
    
    if [ $? -eq 0 ]; then
        systemctl reload nginx
        echo -e "${GREEN}✅ Nginx configured${NC}"
    else
        echo -e "${RED}❌ Nginx configuration failed${NC}"
        exit 1
    fi
else
    echo -e "${YELLOW}⚠️  No nginx config file found${NC}"
fi
echo ""

# Step 7: Build frontend (if exists)
echo -e "${YELLOW}Step 7: Building frontend...${NC}"
if [ -f "deployment/build_frontend.sh" ]; then
    sudo -u $ACTUAL_USER bash deployment/build_frontend.sh
    echo -e "${GREEN}✅ Frontend built${NC}"
else
    echo -e "${YELLOW}⚠️  No frontend build script found${NC}"
fi
echo ""

# Step 8: Start services
echo -e "${YELLOW}Step 8: Starting services...${NC}"
systemctl start amarktai-api

# Wait a moment for service to start
sleep 3

# Check service status
if systemctl is-active --quiet amarktai-api; then
    echo -e "${GREEN}✅ Backend service started${NC}"
else
    echo -e "${RED}❌ Backend service failed to start${NC}"
    echo "Check logs with: sudo journalctl -u amarktai-api -n 50"
    exit 1
fi
echo ""

# Step 9: Run smoke tests
echo -e "${YELLOW}Step 9: Running smoke tests...${NC}"
if [ -f "deployment/smoke_test.sh" ]; then
    sudo -u $ACTUAL_USER bash deployment/smoke_test.sh
    echo -e "${GREEN}✅ Smoke tests passed${NC}"
else
    echo -e "${YELLOW}⚠️  No smoke test script found${NC}"
fi
echo ""

# Final summary
echo "=================================="
echo -e "${GREEN}🎉 Setup Complete!${NC}"
echo "=================================="
echo ""
echo "Services status:"
echo "  Backend:  http://localhost:8000"
echo "  Frontend: http://localhost (via Nginx)"
echo ""
echo "Useful commands:"
echo "  - Check backend: sudo systemctl status amarktai-api"
echo "  - View logs: sudo journalctl -u amarktai-api -f"
echo "  - Restart: sudo systemctl restart amarktai-api"
echo "  - Test API: curl http://localhost:8000/api/health/ping"
echo ""
echo -e "${YELLOW}Next steps:${NC}"
echo "  1. Edit .env with your configuration"
echo "  2. Add exchange API keys via the dashboard"
echo "  3. Configure email alerts (optional)"
echo "  4. Review DEPLOYMENT.md for advanced configuration"
echo ""
echo -e "${GREEN}Happy trading! 🚀${NC}"
