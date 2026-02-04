#!/bin/bash
# Setup environment file permissions for secure deployment
# Ensures .env files have correct permissions (600 - read/write owner only)

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "🔒 Setting up .env file permissions..."

# Function to secure a file
secure_file() {
    local file="$1"
    if [ -f "$file" ]; then
        echo "  Securing $file..."
        chmod 600 "$file"
        echo "    ✅ Permissions set to 600 (read/write owner only)"
        ls -l "$file"
    else
        echo "  ⚠️  $file not found - skipping"
    fi
}

# Secure .env files in project
secure_file "$PROJECT_ROOT/.env"
secure_file "$PROJECT_ROOT/backend/.env"

# Check for system-wide env file
if [ -f "/etc/amarktai/amarktai.env" ]; then
    echo "  Found system-wide config at /etc/amarktai/amarktai.env"
    echo "  Checking permissions..."
    
    # Check if we have permission to modify
    if [ -w "/etc/amarktai/amarktai.env" ]; then
        secure_file "/etc/amarktai/amarktai.env"
    else
        echo "  ⚠️  No write permission. Run with sudo to secure system files:"
        echo "      sudo $0"
    fi
else
    echo "  ℹ️  No system-wide config at /etc/amarktai/amarktai.env"
    echo "     To create one:"
    echo "       sudo mkdir -p /etc/amarktai"
    echo "       sudo cp deployment/etc-amarktai-env.template /etc/amarktai/amarktai.env"
    echo "       sudo chmod 600 /etc/amarktai/amarktai.env"
    echo "       sudo chown amarktai:amarktai /etc/amarktai/amarktai.env"
fi

echo ""
echo "✅ Environment file permissions configured!"
echo ""
echo "Security checklist:"
echo "  [✓] .env files have 600 permissions (read/write owner only)"
echo "  [ ] JWT_SECRET is set to a strong random value"
echo "  [ ] AMARKTAI_FERNET_KEY is set for API key encryption"
echo "  [ ] MongoDB has authentication enabled"
echo "  [ ] SMTP credentials are configured"
echo ""
echo "Generate secure keys:"
echo "  JWT_SECRET:           openssl rand -hex 32"
echo "  AMARKTAI_FERNET_KEY:  python3 -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
