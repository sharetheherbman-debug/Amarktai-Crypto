#!/bin/bash
# Amarktai Network - Systemd Service Installer
# For Ubuntu 24.04 LTS
# Run as: sudo bash tools/systemd_install.sh

set -e  # Exit on error

echo "⚙️  Amarktai Network - Systemd Service Installer"
echo "================================================"

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

# Get actual user (when using sudo)
ACTUAL_USER="${SUDO_USER:-$USER}"

echo "✅ Running as root, actual user: $ACTUAL_USER"

# Configuration
APP_DIR="/var/amarktai/app"
BACKEND_DIR="$APP_DIR/backend"
VENV_DIR="/var/amarktai/venv"
SERVICE_NAME="amarktai-api"
SERVICE_FILE="/etc/systemd/system/$SERVICE_NAME.service"

# Check if backend is set up
echo ""
echo "🔍 Checking prerequisites..."
if [ ! -d "$BACKEND_DIR" ]; then
    echo -e "${RED}❌ Backend directory not found: $BACKEND_DIR${NC}"
    echo "Run backend_setup.sh first"
    exit 1
fi

if [ ! -d "$VENV_DIR" ]; then
    echo -e "${RED}❌ Virtual environment not found: $VENV_DIR${NC}"
    echo "Run backend_setup.sh first"
    exit 1
fi

if [ ! -f "$BACKEND_DIR/.env" ]; then
    echo -e "${YELLOW}⚠️  .env file not found in $BACKEND_DIR${NC}"
    echo "Service will fail to start without configuration"
fi

echo "✅ Prerequisites met"

# Create systemd service file
echo ""
echo "📝 Creating systemd service file..."
cat > "$SERVICE_FILE" << EOF
[Unit]
Description=Amarktai Network API
Documentation=https://github.com/amarktainetwork-blip/Amarktai-Crypto
After=network.target mongodb.service

[Service]
Type=simple
User=$ACTUAL_USER
WorkingDirectory=$BACKEND_DIR
Environment="PATH=$VENV_DIR/bin"
EnvironmentFile=$BACKEND_DIR/.env

# Start command
ExecStart=$VENV_DIR/bin/python -m uvicorn server:app --host 127.0.0.1 --port 8000 --log-level info

# Restart policy
Restart=always
RestartSec=5
TimeoutStopSec=60

# Security hardening
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=$APP_DIR /var/amarktai/logs
ProtectKernelTunables=true
ProtectControlGroups=true
RestrictRealtime=true

# Logging
StandardOutput=journal
StandardError=journal
SyslogIdentifier=$SERVICE_NAME

[Install]
WantedBy=multi-user.target
EOF

echo "✅ Service file created: $SERVICE_FILE"

# Reload systemd
echo ""
echo "🔄 Reloading systemd..."
systemctl daemon-reload
echo "✅ Systemd reloaded"

# Enable service
echo ""
echo "🔧 Enabling service..."
systemctl enable $SERVICE_NAME
echo "✅ Service enabled (will start on boot)"

# Ask to start service now
echo ""
read -p "Start service now? [Y/n] " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Nn]$ ]]; then
    echo "🚀 Starting service..."
    systemctl start $SERVICE_NAME
    
    # Wait a bit for service to start
    sleep 3
    
    # Check status
    if systemctl is-active --quiet $SERVICE_NAME; then
        echo -e "${GREEN}✅ Service is running${NC}"
    else
        echo -e "${RED}❌ Service failed to start${NC}"
        echo "Check logs: sudo journalctl -u $SERVICE_NAME -n 50"
        exit 1
    fi
fi

# Summary
echo ""
echo "================================================"
echo -e "${GREEN}✅ Systemd service installed!${NC}"
echo "================================================"
echo ""
echo "Service management commands:"
echo "  Start:   sudo systemctl start $SERVICE_NAME"
echo "  Stop:    sudo systemctl stop $SERVICE_NAME"
echo "  Restart: sudo systemctl restart $SERVICE_NAME"
echo "  Status:  sudo systemctl status $SERVICE_NAME"
echo "  Logs:    sudo journalctl -u $SERVICE_NAME -f"
echo ""
echo "Service details:"
echo "  Name: $SERVICE_NAME"
echo "  File: $SERVICE_FILE"
echo "  User: $ACTUAL_USER"
echo "  Port: 8000 (127.0.0.1)"
echo ""
echo "Next steps:"
echo "1. Configure nginx reverse proxy"
echo "2. Run health check: bash tools/health_check.sh"
echo ""
