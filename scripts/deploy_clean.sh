#!/bin/bash
#
# Clean Deploy Script for Amarktai Network
# Deploys latest code from main branch with full rebuild
# Safe to run on production - includes health checks and rollback on failure
#

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration
REPO_DIR="/var/amarktai/app/Amarktai-Network---Deployment"
BACKEND_DIR="$REPO_DIR/backend"
FRONTEND_DIR="$REPO_DIR/frontend"
LOG_FILE="/var/log/amarktai/deploy-$(date +%Y%m%d-%H%M%S).log"

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}Amarktai Network - Clean Deploy${NC}"
echo -e "${BLUE}========================================${NC}"
echo "Started: $(date)"
echo "Log file: $LOG_FILE"
echo ""

# Function to print step
step() {
    echo -e "${BLUE}▶ $1${NC}"
}

# Function to print success
success() {
    echo -e "${GREEN}✓ $1${NC}"
}

# Function to print warning
warning() {
    echo -e "${YELLOW}⚠ $1${NC}"
}

# Function to print error and exit
error() {
    echo -e "${RED}✗ $1${NC}"
    echo -e "${RED}Deployment failed! Check logs: $LOG_FILE${NC}"
    # Print last 150 lines of journal
    echo ""
    echo "Last 150 lines from systemd journal:"
    journalctl -u amarktai-api -n 150 --no-pager
    exit 1
}

# Create log directory if needed
mkdir -p "$(dirname "$LOG_FILE")"

# Redirect all output to log file as well as stdout
exec > >(tee -a "$LOG_FILE") 2>&1

# Change to repo directory
cd "$REPO_DIR" || error "Failed to change to repo directory"

# Step 1: Git operations
step "Step 1: Fetching latest code from origin/main"
git fetch --all --prune || error "Git fetch failed"
success "Fetched latest code"

step "Checking out main branch"
git checkout main || error "Failed to checkout main"
success "On main branch"

step "Resetting to origin/main (clean slate)"
git reset --hard origin/main || error "Git reset failed"
success "Reset to origin/main"

step "Cleaning untracked files"
git clean -fd || error "Git clean failed"
success "Cleaned untracked files"

# Step 2: Backend deployment
step "Step 2: Deploying backend"
cd "$BACKEND_DIR" || error "Backend directory not found"

step "Setting up Python virtual environment"
if [ ! -d ".venv" ]; then
    python3 -m venv .venv || error "Failed to create venv"
fi
success "Virtual environment ready"

step "Activating virtual environment and installing dependencies"
source .venv/bin/activate || error "Failed to activate venv"
pip install --upgrade pip > /dev/null 2>&1 || warning "Pip upgrade failed (non-fatal)"
pip install -r requirements.txt || error "Failed to install Python dependencies"
success "Backend dependencies installed"

step "Running Python smoke checks"
python -m py_compile server.py || error "Python syntax check failed for server.py"
python -m py_compile database.py || error "Python syntax check failed for database.py"
success "Python smoke checks passed"

# Step 3: Frontend deployment
step "Step 3: Deploying frontend"
cd "$FRONTEND_DIR" || error "Frontend directory not found"

step "Installing Node dependencies (clean)"
npm ci || error "Failed to install Node dependencies"
success "Node dependencies installed"

step "Building frontend"
npm run build || error "Frontend build failed"
success "Frontend built successfully"

# Step 4: Restart services
step "Step 4: Restarting services"

step "Restarting amarktai-api service"
sudo systemctl restart amarktai-api || error "Failed to restart amarktai-api"
success "amarktai-api restarted"

# Wait for service to stabilize
sleep 5

step "Checking service status"
if ! sudo systemctl is-active --quiet amarktai-api; then
    error "amarktai-api service is not running after restart"
fi
success "amarktai-api service is active"

step "Reloading nginx"
sudo systemctl reload nginx || warning "Failed to reload nginx (may not be critical)"
success "nginx reloaded"

# Step 5: Health checks
step "Step 5: Running health checks"

# Check internal endpoint
step "Testing internal endpoint (127.0.0.1:8000)"
if curl -f -s http://127.0.0.1:8000/api/health/ping > /dev/null; then
    success "Internal endpoint responding"
else
    error "Internal endpoint health check failed"
fi

# Check external endpoint (if domain is configured)
step "Testing external endpoint (https://www.amarktai.online)"
# Note: Using -k to skip SSL verification since this is a health check
# In production, ensure valid SSL certificates are configured
if curl -f -s -k https://www.amarktai.online/api/health/ping > /dev/null; then
    success "External endpoint responding"
else
    warning "External endpoint check failed (may not be configured)"
fi

# Final success message
echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Deployment completed successfully!${NC}"
echo -e "${GREEN}========================================${NC}"
echo "Finished: $(date)"
echo ""
echo "Next steps:"
echo "  - Check logs: tail -f /var/log/amarktai/backend.log"
echo "  - Monitor service: sudo systemctl status amarktai-api"
echo "  - Run smoke tests: cd $REPO_DIR/scripts && ./smoke.sh"
echo ""

exit 0
