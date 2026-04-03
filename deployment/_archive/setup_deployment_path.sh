#!/bin/bash
# Deployment Path Setup Script
# This script fixes the path mismatch between systemd service and actual code location

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "============================================"
echo "Amarktai Network - Deployment Path Setup"
echo "============================================"
echo ""
echo "Current repository location: $REPO_ROOT"
echo ""

# Check if systemd service expects /var/amarktai/app
EXPECTED_PATH="/var/amarktai/app"

echo "Systemd service expects code at: $EXPECTED_PATH"
echo ""

# Offer choices
echo "Choose deployment option:"
echo ""
echo "1) Quick Fix: Create symlink (fastest, recommended for development)"
echo "   - Creates /var/amarktai/app -> $REPO_ROOT symlink"
echo "   - No files copied, uses current location"
echo ""
echo "2) Production Install: Copy to /var/amarktai/app (recommended for production)"
echo "   - Copies all files to /var/amarktai/app"
echo "   - Proper isolation and ownership"
echo ""
echo "3) Update systemd to use current location"
echo "   - Modifies systemd service to point to $REPO_ROOT"
echo "   - Useful if you want to run from custom location"
echo ""
read -p "Enter choice (1, 2, or 3): " choice

case $choice in
  1)
    echo ""
    echo "Creating symlink..."
    
    # Check if /var/amarktai already exists
    if [ -L "$EXPECTED_PATH" ]; then
      echo "⚠️  Symlink already exists: $EXPECTED_PATH"
      ls -la "$EXPECTED_PATH"
      read -p "Remove and recreate? (y/n): " recreate
      if [ "$recreate" = "y" ]; then
        sudo rm "$EXPECTED_PATH"
      else
        echo "Keeping existing symlink"
        exit 0
      fi
    elif [ -d "$EXPECTED_PATH" ]; then
      echo "⚠️  Directory already exists: $EXPECTED_PATH"
      echo "Cannot create symlink over existing directory"
      echo "Please backup and remove it first, or choose option 2 or 3"
      exit 1
    fi
    
    # Create parent directory if needed
    sudo mkdir -p "$(dirname "$EXPECTED_PATH")"
    
    # Create symlink
    sudo ln -s "$REPO_ROOT" "$EXPECTED_PATH"
    
    echo "✅ Symlink created: $EXPECTED_PATH -> $REPO_ROOT"
    ls -la "$EXPECTED_PATH"
    
    # Set ownership
    sudo chown -h $USER:$USER "$EXPECTED_PATH"
    
    echo ""
    echo "✅ Deployment path setup complete!"
    echo "Service will now find code at $EXPECTED_PATH"
    ;;
    
  2)
    echo ""
    echo "Installing to $EXPECTED_PATH..."
    
    # Create directory
    sudo mkdir -p "$EXPECTED_PATH"
    
    # Copy files
    echo "Copying files..."
    sudo rsync -av --exclude='.git' --exclude='node_modules' --exclude='__pycache__' --exclude='.venv' \
      "$REPO_ROOT/" "$EXPECTED_PATH/"
    
    # Set ownership
    echo "Setting ownership..."
    sudo chown -R www-data:www-data "$EXPECTED_PATH"
    
    # Setup Python venv if needed
    if [ ! -d "$EXPECTED_PATH/backend/.venv" ]; then
      echo "Setting up Python virtual environment..."
      cd "$EXPECTED_PATH/backend"
      sudo -u www-data python3 -m venv .venv
      sudo -u www-data .venv/bin/pip install --upgrade pip
      sudo -u www-data .venv/bin/pip install -r requirements.txt
    fi
    
    echo ""
    echo "✅ Production installation complete!"
    echo "Code installed to: $EXPECTED_PATH"
    echo "Ownership: www-data:www-data"
    ;;
    
  3)
    echo ""
    echo "Updating systemd service to use current location..."
    
    SERVICE_FILE="$SCRIPT_DIR/amarktai-api.service"
    NEW_SERVICE_FILE="$SCRIPT_DIR/amarktai-api.service.local"
    
    # Create custom service file
    cat > "$NEW_SERVICE_FILE" << EOF
[Unit]
Description=Amarktai Network API Server
After=network.target mongodb.service
Wants=mongodb.service

[Service]
Type=simple
User=$USER
Group=$USER
WorkingDirectory=$REPO_ROOT/backend
Environment="PATH=$REPO_ROOT/backend/.venv/bin"
EnvironmentFile=$REPO_ROOT/backend/.env
ExecStart=$REPO_ROOT/backend/.venv/bin/uvicorn server:app --host 127.0.0.1 --port 8000
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
    
    echo "✅ Created custom service file: $NEW_SERVICE_FILE"
    echo ""
    echo "To use this service:"
    echo "  sudo cp $NEW_SERVICE_FILE /etc/systemd/system/amarktai-api.service"
    echo "  sudo systemctl daemon-reload"
    echo "  sudo systemctl restart amarktai-api"
    echo ""
    ;;
    
  *)
    echo "Invalid choice. Exiting."
    exit 1
    ;;
esac

echo ""
echo "============================================"
echo "Next steps:"
echo "============================================"
echo "1. Restart the service:"
echo "   sudo systemctl daemon-reload"
echo "   sudo systemctl restart amarktai-api"
echo ""
echo "2. Check service status:"
echo "   sudo systemctl status amarktai-api"
echo ""
echo "3. View logs:"
echo "   sudo journalctl -u amarktai-api -f"
echo ""
