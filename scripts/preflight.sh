#!/bin/bash
# Preflight Check - Run before deployment
# Validates environment, dependencies, MongoDB, exchange registry

set -e

echo "========================================="
echo "Amarktai Network - Preflight Check"
echo "========================================="
echo ""

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

ERRORS=0
WARNINGS=0

# Function to check command
check_command() {
    if command -v $1 &> /dev/null; then
        echo -e "${GREEN}✓${NC} $1 is installed"
        return 0
    else
        echo -e "${RED}✗${NC} $1 is NOT installed"
        ((ERRORS++))
        return 1
    fi
}

# Function to check Python package
check_python_package() {
    if python3 -c "import $1" 2>/dev/null; then
        echo -e "${GREEN}✓${NC} Python package '$1' is installed"
        return 0
    else
        echo -e "${RED}✗${NC} Python package '$1' is NOT installed"
        ((ERRORS++))
        return 1
    fi
}

# 1. Check system commands
echo "1. Checking system commands..."
check_command python3
check_command pip3
check_command mongo || check_command mongosh
check_command node
check_command npm
echo ""

# 2. Check Python version
echo "2. Checking Python version..."
PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
REQUIRED_VERSION="3.8"
if [ "$(printf '%s\n' "$REQUIRED_VERSION" "$PYTHON_VERSION" | sort -V | head -n1)" = "$REQUIRED_VERSION" ]; then
    echo -e "${GREEN}✓${NC} Python $PYTHON_VERSION >= $REQUIRED_VERSION"
else
    echo -e "${RED}✗${NC} Python $PYTHON_VERSION < $REQUIRED_VERSION"
    ((ERRORS++))
fi
echo ""

# 3. Check Node version
echo "3. Checking Node.js version..."
NODE_VERSION=$(node --version 2>&1 | sed 's/v//')
REQUIRED_NODE="16.0.0"
if [ "$(printf '%s\n' "$REQUIRED_NODE" "$NODE_VERSION" | sort -V | head -n1)" = "$REQUIRED_NODE" ]; then
    echo -e "${GREEN}✓${NC} Node.js $NODE_VERSION >= $REQUIRED_NODE"
else
    echo -e "${RED}✗${NC} Node.js $NODE_VERSION < $REQUIRED_NODE"
    ((ERRORS++))
fi
echo ""

# 4. Check environment file
echo "4. Checking environment configuration..."
if [ -f ".env" ]; then
    echo -e "${GREEN}✓${NC} .env file exists"
    
    # Check critical variables
    source .env
    
    # Check JWT_SECRET
    if [ -z "$JWT_SECRET" ] || [ "$JWT_SECRET" = "your-secret-key-change-in-production-min-32-chars" ]; then
        echo -e "${YELLOW}⚠${NC}  JWT_SECRET not changed from default (SECURITY RISK)"
        ((WARNINGS++))
    else
        echo -e "${GREEN}✓${NC} JWT_SECRET is set"
    fi
    
    # Check MONGO_URL
    if [ -z "$MONGO_URL" ]; then
        echo -e "${RED}✗${NC} MONGO_URL not set"
        ((ERRORS++))
    else
        echo -e "${GREEN}✓${NC} MONGO_URL is set: $MONGO_URL"
    fi
    
    # Check DB_NAME
    if [ -z "$DB_NAME" ]; then
        echo -e "${RED}✗${NC} DB_NAME not set"
        ((ERRORS++))
    else
        echo -e "${GREEN}✓${NC} DB_NAME is set: $DB_NAME"
    fi
    
else
    echo -e "${RED}✗${NC} .env file not found"
    echo "  Copy .env.example to .env and configure"
    ((ERRORS++))
fi
echo ""

# 5. Check MongoDB connection
echo "5. Checking MongoDB connection..."
if [ ! -z "$MONGO_URL" ]; then
    # Try to connect
    if mongo "$MONGO_URL" --eval "db.adminCommand('ping')" --quiet &> /dev/null || \
       mongosh "$MONGO_URL" --eval "db.adminCommand('ping')" --quiet &> /dev/null; then
        echo -e "${GREEN}✓${NC} MongoDB is accessible"
    else
        echo -e "${RED}✗${NC} Cannot connect to MongoDB at $MONGO_URL"
        ((ERRORS++))
    fi
else
    echo -e "${YELLOW}⚠${NC}  Skipping MongoDB check (MONGO_URL not set)"
fi
echo ""

# 6. Check Python dependencies
echo "6. Checking Python dependencies..."
check_python_package fastapi
check_python_package motor
check_python_package pymongo
check_python_package ccxt
check_python_package pyotp
check_python_package pydantic
check_python_package uvicorn
echo ""

# 7. Check backend structure
echo "7. Checking backend structure..."
BACKEND_DIRS=("routes" "services" "engines" "utils" "config")
for dir in "${BACKEND_DIRS[@]}"; do
    if [ -d "backend/$dir" ]; then
        echo -e "${GREEN}✓${NC} backend/$dir exists"
    else
        echo -e "${RED}✗${NC} backend/$dir missing"
        ((ERRORS++))
    fi
done
echo ""

# 8. Python compilation check
echo "8. Checking Python compilation..."
if python3 -m py_compile backend/server.py 2>/dev/null; then
    echo -e "${GREEN}✓${NC} backend/server.py compiles"
else
    echo -e "${RED}✗${NC} backend/server.py has syntax errors"
    ((ERRORS++))
fi

if python3 -m py_compile backend/database.py 2>/dev/null; then
    echo -e "${GREEN}✓${NC} backend/database.py compiles"
else
    echo -e "${RED}✗${NC} backend/database.py has syntax errors"
    ((ERRORS++))
fi
echo ""

# 9. Check exchange registry
echo "9. Checking exchange registry..."
if [ -f "backend/exchange_limits.py" ]; then
    echo -e "${GREEN}✓${NC} Exchange limits file exists"
    
    # Check for required 7 exchanges
    REQUIRED_EXCHANGES=("luno" "binance" "kucoin" "bybit" "kraken" "bitget" "gate")
    EXCHANGE_COUNT=0
    
    for exchange in "${REQUIRED_EXCHANGES[@]}"; do
        if grep -q "\"$exchange\"" backend/exchange_limits.py; then
            echo -e "${GREEN}✓${NC} Exchange configured: $exchange"
            ((EXCHANGE_COUNT++))
        else
            echo -e "${RED}✗${NC} Exchange NOT configured: $exchange"
            ((ERRORS++))
        fi
    done
    
    # Verify exactly 7 exchanges (no more, no less)
    if [ $EXCHANGE_COUNT -eq 7 ]; then
        echo -e "${GREEN}✓${NC} Exactly 7 exchanges configured (production requirement)"
    else
        echo -e "${RED}✗${NC} Expected 7 exchanges, found $EXCHANGE_COUNT"
        ((ERRORS++))
    fi
    
    # Check for VALR/OVEX (should NOT exist)
    if grep -qi "valr\|ovex" backend/exchange_limits.py backend/platforms.py 2>/dev/null; then
        echo -e "${RED}✗${NC} VALR or OVEX found (must be removed)"
        ((ERRORS++))
    else
        echo -e "${GREEN}✓${NC} No VALR/OVEX references (correct)"
    fi
else
    echo -e "${RED}✗${NC} Exchange limits file (exchange_limits.py) not found"
    ((ERRORS++))
fi
echo ""

# 10. Check frontend
echo "10. Checking frontend..."
if [ -d "frontend" ]; then
    echo -e "${GREEN}✓${NC} frontend directory exists"
    
    if [ -f "frontend/package.json" ]; then
        echo -e "${GREEN}✓${NC} frontend/package.json exists"
    else
        echo -e "${YELLOW}⚠${NC}  frontend/package.json missing"
        ((WARNINGS++))
    fi
    
    if [ -d "frontend/node_modules" ]; then
        echo -e "${GREEN}✓${NC} frontend dependencies installed"
    else
        echo -e "${YELLOW}⚠${NC}  frontend dependencies not installed (run: cd frontend && npm install)"
        ((WARNINGS++))
    fi
else
    echo -e "${YELLOW}⚠${NC}  frontend directory not found"
    ((WARNINGS++))
fi
echo ""

# 11. Check wallet services
echo "11. Checking wallet services..."
WALLET_SERVICES=("backend/services/reserved_funds_service.py" "backend/services/balance_sync_service.py" "backend/services/transfer_state_machine.py" "backend/services/email_service.py")

for service in "${WALLET_SERVICES[@]}"; do
    if [ -f "$service" ]; then
        echo -e "${GREEN}✓${NC} $service exists"
        
        # Check if it compiles
        if python3 -m py_compile "$service" 2>/dev/null; then
            echo -e "${GREEN}✓${NC} $service compiles"
        else
            echo -e "${RED}✗${NC} $service has syntax errors"
            ((ERRORS++))
        fi
    else
        echo -e "${RED}✗${NC} $service missing"
        ((ERRORS++))
    fi
done

# Check wallet config vars
if [ -f ".env" ]; then
    source .env
    
    # Check REQUIRE_2FA_FOR_WITHDRAWALS
    if [ ! -z "$REQUIRE_2FA_FOR_WITHDRAWALS" ]; then
        echo -e "${GREEN}✓${NC} REQUIRE_2FA_FOR_WITHDRAWALS is set: $REQUIRE_2FA_FOR_WITHDRAWALS"
    else
        echo -e "${YELLOW}⚠${NC}  REQUIRE_2FA_FOR_WITHDRAWALS not set (will use default)"
        ((WARNINGS++))
    fi
    
    # Check WALLET_MAX_TRANSFER_ZAR_PER_TX
    if [ ! -z "$WALLET_MAX_TRANSFER_ZAR_PER_TX" ]; then
        echo -e "${GREEN}✓${NC} WALLET_MAX_TRANSFER_ZAR_PER_TX is set: $WALLET_MAX_TRANSFER_ZAR_PER_TX"
    else
        echo -e "${YELLOW}⚠${NC}  WALLET_MAX_TRANSFER_ZAR_PER_TX not set (will use default)"
        ((WARNINGS++))
    fi
    
    # Check WALLET_MAX_DAILY_WITHDRAWAL_ZAR
    if [ ! -z "$WALLET_MAX_DAILY_WITHDRAWAL_ZAR" ]; then
        echo -e "${GREEN}✓${NC} WALLET_MAX_DAILY_WITHDRAWAL_ZAR is set: $WALLET_MAX_DAILY_WITHDRAWAL_ZAR"
    else
        echo -e "${YELLOW}⚠${NC}  WALLET_MAX_DAILY_WITHDRAWAL_ZAR not set (will use default)"
        ((WARNINGS++))
    fi
    
    # Check WALLET_MIN_RESERVE_ZAR
    if [ ! -z "$WALLET_MIN_RESERVE_ZAR" ]; then
        echo -e "${GREEN}✓${NC} WALLET_MIN_RESERVE_ZAR is set: $WALLET_MIN_RESERVE_ZAR"
    else
        echo -e "${YELLOW}⚠${NC}  WALLET_MIN_RESERVE_ZAR not set (will use default)"
        ((WARNINGS++))
    fi
else
    echo -e "${YELLOW}⚠${NC}  Skipping wallet config check (.env not found)"
    ((WARNINGS++))
fi
echo ""

# Summary
echo "========================================="
echo "Preflight Check Summary"
echo "========================================="
if [ $ERRORS -eq 0 ] && [ $WARNINGS -eq 0 ]; then
    echo -e "${GREEN}✓ All checks passed!${NC}"
    echo ""
    echo "System is ready for deployment."
    exit 0
elif [ $ERRORS -eq 0 ]; then
    echo -e "${YELLOW}⚠ Checks passed with $WARNINGS warning(s)${NC}"
    echo ""
    echo "System can be deployed but review warnings."
    exit 0
else
    echo -e "${RED}✗ $ERRORS error(s), $WARNINGS warning(s)${NC}"
    echo ""
    echo "Fix errors before deployment."
    exit 1
fi
