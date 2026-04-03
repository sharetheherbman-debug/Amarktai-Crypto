#!/usr/bin/env bash
#
# install.sh - Plug-and-play deployment script for Amarktai Network
#
# This script provides a complete installation on Ubuntu 24.04:
# 1. Installs OS dependencies (Python 3.12, build tools, etc.)
# 2. Creates Python venv and installs requirements
# 3. Validates Python syntax with compileall
# 4. Installs and configures systemd service
# 5. Starts the service and validates health
# 6. Downloads OpenAPI spec and verifies routes
#
# CANONICAL VPS LAYOUT:
# - Repo clone: /var/amarktai/app
# - Backend: /var/amarktai/app/backend
# - Env file: /var/amarktai/app/backend/.env
# - Service user: www-data
# - Systemd service: amarktai-api.service

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# CANONICAL VPS PATHS
VPS_ROOT="/var/amarktai/app"
BACKEND_DIR="$VPS_ROOT/backend"
DEPLOYMENT_DIR="$VPS_ROOT/deployment"
SERVICE_USER="www-data"
LOG_DIR="/var/log/amarktai"

# Get script directory and source project root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
PROJECT_ROOT="$VPS_ROOT"  # Use VPS_ROOT as the project root after setup

log_info() {
    echo -e "${BLUE}ℹ️  $1${NC}"
}

log_success() {
    echo -e "${GREEN}✅ $1${NC}"
}

log_warning() {
    echo -e "${YELLOW}⚠️  $1${NC}"
}

log_error() {
    echo -e "${RED}❌ $1${NC}"
    exit 1
}

log_section() {
    echo ""
    echo -e "${BLUE}========================================${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}========================================${NC}"
}

# Check if running as root (needed for apt and systemctl)
if [ "$EUID" -ne 0 ]; then 
    log_error "Please run as root (use sudo)"
fi

log_section "Amarktai Network - Installation"
log_info "Source directory: $SOURCE_ROOT"
log_info "VPS deployment root: $VPS_ROOT"
log_info "Backend directory: $BACKEND_DIR"

# ============================================================================
# 0. Setup VPS Directory Structure
# ============================================================================
log_section "0. Setting Up VPS Directory Structure"

# If we're not already in the VPS location, copy files there
if [ "$SOURCE_ROOT" != "$VPS_ROOT" ]; then
    log_info "Creating VPS directory structure..."
    mkdir -p /var/amarktai
    mkdir -p "$LOG_DIR"
    
    if [ -d "$VPS_ROOT" ]; then
        log_warning "VPS directory $VPS_ROOT already exists"
    else
        log_info "Copying repository to $VPS_ROOT..."
        cp -r "$SOURCE_ROOT" "$VPS_ROOT"
        log_success "Repository copied to $VPS_ROOT"
    fi
else
    log_info "Already running from VPS location: $VPS_ROOT"
    mkdir -p "$LOG_DIR"
fi

# Set PROJECT_ROOT to VPS_ROOT now that we've copied
PROJECT_ROOT="$VPS_ROOT"

log_success "VPS directory structure ready"
log_info "Log directory: $LOG_DIR"

# ============================================================================
# 1. Install OS Dependencies
# ============================================================================
log_section "1. Installing OS Dependencies"

log_info "Updating package lists..."
apt-get update -qq

log_info "Installing Python 3.12 and development tools..."
apt-get install -y -qq \
    python3.12 \
    python3.12-venv \
    python3.12-dev \
    python3-pip \
    build-essential \
    curl \
    git \
    nginx \
    redis-server \
    docker.io \
    docker-compose \
    || log_error "Failed to install OS dependencies"

log_success "OS dependencies installed"

# Start Redis if not running
log_info "Starting Redis server..."
systemctl enable redis-server || true
systemctl start redis-server || true

# ============================================================================
# 1.5. Setup MongoDB via Docker
# ============================================================================
log_section "1.5. Setting Up MongoDB via Docker"

# Secure password storage directory
SECRETS_DIR="/etc/amarktai"
MONGO_PASSWORD_FILE="$SECRETS_DIR/mongo_password"

# Generate random password if not already stored
if [ ! -f "$MONGO_PASSWORD_FILE" ]; then
    log_info "Generating MongoDB password..."
    mkdir -p "$SECRETS_DIR"
    chmod 700 "$SECRETS_DIR"  # Restrict directory access
    chown root:root "$SECRETS_DIR"
    
    openssl rand -hex 16 > "$MONGO_PASSWORD_FILE"
    chmod 600 "$MONGO_PASSWORD_FILE"
    chown root:root "$MONGO_PASSWORD_FILE"
    log_success "MongoDB password stored securely in $MONGO_PASSWORD_FILE"
fi

MONGO_PASSWORD=$(cat "$MONGO_PASSWORD_FILE")

# Check if MongoDB is already running
if docker ps | grep -q amarktai-mongo; then
    log_info "MongoDB container already running"
else
    log_info "Starting MongoDB container (bound to 127.0.0.1 only)..."
    docker run -d \
        --name amarktai-mongo \
        --restart unless-stopped \
        -p 127.0.0.1:27017:27017 \
        -v amarktai-mongo-data:/data/db \
        -e MONGO_INITDB_ROOT_USERNAME=amarktai \
        -e MONGO_INITDB_ROOT_PASSWORD="$MONGO_PASSWORD" \
        mongo:7.0 \
        || log_warning "MongoDB container failed to start (may already exist)"
    
    log_info "Waiting for MongoDB to be ready..."
    sleep 5
    
    # Save connection string to .env if not already present
    if [ -f "$BACKEND_DIR/.env" ]; then
        if ! grep -q "^MONGO_URL=" "$BACKEND_DIR/.env"; then
            echo "" >> "$BACKEND_DIR/.env"
            echo "# MongoDB connection (auto-generated during installation)" >> "$BACKEND_DIR/.env"
            echo "MONGO_URL=mongodb://amarktai:$MONGO_PASSWORD@localhost:27017" >> "$BACKEND_DIR/.env"
            log_success "MongoDB connection string added to .env"
        fi
    fi
    
    log_success "MongoDB started on 127.0.0.1:27017 (localhost only)"
    log_info "MongoDB password stored in: $MONGO_PASSWORD_FILE (chmod 600)"
fi

log_success "Database services ready"

# ============================================================================
# 2. Create Virtual Environment and Install Python Dependencies
# ============================================================================
log_section "2. Setting Up Python Environment"

if [ ! -d "$BACKEND_DIR/.venv" ]; then
    log_info "Creating virtual environment..."
    python3.12 -m venv "$BACKEND_DIR/.venv" || log_error "Failed to create venv"
    log_success "Virtual environment created"
else
    log_info "Virtual environment already exists"
fi

log_info "Activating virtual environment..."
source "$BACKEND_DIR/.venv/bin/activate"

log_info "Upgrading pip..."
python -m pip install --upgrade pip -q

log_info "Installing Python dependencies from requirements.txt..."
if [ -f "$BACKEND_DIR/requirements.txt" ]; then
    python -m pip install -r "$BACKEND_DIR/requirements.txt" -q || log_error "Failed to install requirements"
    log_success "Python dependencies installed"
else
    log_error "requirements.txt not found in $BACKEND_DIR"
fi

# ============================================================================
# 3. Validate Python Syntax
# ============================================================================
log_section "3. Validating Python Syntax"

log_info "Running compileall on backend directory..."
if python -m compileall "$BACKEND_DIR" -q; then
    log_success "All Python files have valid syntax"
else
    log_error "Python syntax errors found - fix before continuing"
fi

# ============================================================================
# 4. Configure Environment
# ============================================================================
log_section "4. Configuring Environment"

if [ ! -f "$BACKEND_DIR/.env" ]; then
    if [ -f "$PROJECT_ROOT/.env.example" ]; then
        log_info "Copying .env.example to backend/.env..."
        cp "$PROJECT_ROOT/.env.example" "$BACKEND_DIR/.env"
        log_warning "Please edit $BACKEND_DIR/.env with your configuration"
    else
        log_warning "No .env.example found - you'll need to create .env manually"
    fi
else
    log_info ".env file already exists"
fi

# ============================================================================
# 5. Install Systemd Service
# ============================================================================
log_section "5. Installing Systemd Service"

# Ensure www-data user exists (should exist by default on Ubuntu)
if ! id -u www-data > /dev/null 2>&1; then
    log_error "www-data user not found - this is unusual on Ubuntu"
fi

# Set ownership of VPS directory
log_info "Setting ownership of $VPS_ROOT to $SERVICE_USER..."
chown -R "$SERVICE_USER:$SERVICE_USER" "$VPS_ROOT"
chmod 755 "$VPS_ROOT"
chmod 755 "$BACKEND_DIR"

# Create service file
SERVICE_FILE="/etc/systemd/system/amarktai-api.service"
log_info "Creating systemd service file at $SERVICE_FILE..."

cat > "$SERVICE_FILE" <<EOF
[Unit]
Description=Amarktai Network API
After=network.target docker.service
Wants=docker.service

[Service]
Type=simple
User=$SERVICE_USER
Group=$SERVICE_USER
WorkingDirectory=$BACKEND_DIR
Environment="PATH=$BACKEND_DIR/.venv/bin"
EnvironmentFile=$BACKEND_DIR/.env
ExecStart=$BACKEND_DIR/.venv/bin/uvicorn server:app --host 127.0.0.1 --port 8000
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal
SyslogIdentifier=amarktai-api

# Resource Limits
MemoryMax=2G
CPUQuota=150%

[Install]
WantedBy=multi-user.target
EOF

log_success "Systemd service file created"

# Reload systemd
log_info "Reloading systemd daemon..."
systemctl daemon-reload || log_error "Failed to reload systemd"

# Enable service to start on boot
log_info "Enabling service to start on boot..."
systemctl enable amarktai-api.service || log_error "Failed to enable service"

log_success "Systemd service installed and enabled"

# ============================================================================
# 6. Start Service and Validate
# ============================================================================
log_section "6. Starting Service"

log_info "Starting amarktai-api service..."
systemctl start amarktai-api.service || log_error "Failed to start service"

log_info "Waiting for service to be ready (30 seconds)..."
sleep 30

# Check if service is running
if systemctl is-active --quiet amarktai-api.service; then
    log_success "Service is running"
else
    log_error "Service failed to start - check logs with: journalctl -u amarktai-api.service -n 50"
fi

# ============================================================================
# 7. Health Check
# ============================================================================
log_section "7. Running Health Checks"

log_info "Checking /api/health/ping endpoint..."
if curl -s -f http://127.0.0.1:8000/api/health/ping > /dev/null 2>&1; then
    log_success "/api/health/ping is responding"
else
    # Try alternative health endpoint
    if curl -s -f http://127.0.0.1:8000/api/health > /dev/null 2>&1; then
        log_success "/api/health is responding"
    else
        log_warning "Health endpoint not responding yet - service may still be starting up"
    fi
fi

# ============================================================================
# 8. Verify OpenAPI Routes
# ============================================================================
log_section "8. Verifying OpenAPI Routes"

log_info "Downloading /openapi.json..."
if OPENAPI_JSON=$(curl -s -f http://127.0.0.1:8000/openapi.json 2>/dev/null); then
    log_success "OpenAPI spec downloaded"
    
    # Check for required routes
    REQUIRED_ROUTES=(
        "/api/auth/login"
        "/api/health/ping"
        "/api/platforms"
        "/api/system/ping"
    )
    
    for route in "${REQUIRED_ROUTES[@]}"; do
        if echo "$OPENAPI_JSON" | grep -q "$route"; then
            log_success "Route found: $route"
        else
            log_warning "Route not found: $route"
        fi
    done
    
    # Check for admin endpoints
    if echo "$OPENAPI_JSON" | grep -q "/api/admin"; then
        log_success "Admin endpoints mounted"
    else
        log_warning "Admin endpoints not found in OpenAPI spec"
    fi
else
    log_warning "Could not download OpenAPI spec - service may still be starting"
fi

# ============================================================================
# 9. Run Smoke Tests
# ============================================================================
log_section "9. Running Smoke Tests"

if [ -f "$PROJECT_ROOT/tools/smoke_test.sh" ]; then
    log_info "Running comprehensive smoke tests..."
    
    # Set environment for smoke test
    export API_BASE_URL="http://127.0.0.1:8000"
    export INVITE_CODE="${INVITE_CODE:-AMARKTAI2024}"
    
    if bash "$PROJECT_ROOT/tools/smoke_test.sh"; then
        log_success "Smoke tests PASSED ✅"
    else
        log_error "Smoke tests FAILED ❌"
        log_warning "Installation completed but system validation failed"
        log_warning "Check smoke test output above for details"
    fi
else
    log_warning "Smoke test script not found - skipping validation"
fi

# ============================================================================
# FINAL REPORT
# ============================================================================
log_section "Installation Complete"

echo ""
log_success "Amarktai Network installation successful!"
echo ""
log_info "Service Status:"
echo "  • Service: amarktai-api.service"
echo "  • Status: $(systemctl is-active amarktai-api.service)"
echo "  • Listening: http://127.0.0.1:8000"
echo ""
log_info "Useful Commands:"
echo "  • Check status: sudo systemctl status amarktai-api.service"
echo "  • View logs: sudo journalctl -u amarktai-api.service -f"
echo "  • Restart: sudo systemctl restart amarktai-api.service"
echo "  • Stop: sudo systemctl stop amarktai-api.service"
echo ""
log_info "Next Steps:"
echo "  1. Configure Nginx reverse proxy (see deployment/nginx-amarktai.conf)"
echo "  2. Set up SSL certificates (Let's Encrypt recommended)"
echo "  3. Update JWT_SECRET and other secrets in .env"
echo "  4. Set ENCRYPTION_KEY for API key encryption in .env"
echo "  5. Update MONGO_URL if using custom MongoDB setup"
echo ""
log_info "Required .env Variables:"
echo "  • MONGO_URL - MongoDB connection string"
echo "  • REDIS_URL - Redis connection string (optional)"
echo "  • JWT_SECRET - Secret for JWT token signing"
echo "  • ENCRYPTION_KEY - Fernet key for API key encryption"
echo "  • INVITE_CODE - Code required for user registration"
echo "  • ENABLE_TRADING - Enable live trading (default: false)"
echo ""
log_success "Installation complete! 🚀"
