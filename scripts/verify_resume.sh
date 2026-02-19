#!/bin/bash
# Verification script for paper trading resume functionality
# Tests that bots can be resumed when paper trading is enabled

set -e  # Exit on error

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "=================================================="
echo "Paper Trading Resume Verification Script"
echo "=================================================="
echo ""

# Configuration from environment or defaults
API_URL="${API_URL:-http://localhost:8000}"
EMAIL="${TEST_USER_EMAIL:-test@example.com}"
PASSWORD="${TEST_USER_PASSWORD:-testpassword123}"

# Function to print colored output
print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

print_info() {
    echo -e "${YELLOW}ℹ $1${NC}"
}

# Function to make API calls
api_call() {
    local method=$1
    local endpoint=$2
    local data=$3
    local token=$4
    
    if [ -n "$token" ]; then
        if [ -n "$data" ]; then
            curl -s -X "$method" \
                -H "Content-Type: application/json" \
                -H "Authorization: Bearer $token" \
                -d "$data" \
                "$API_URL$endpoint"
        else
            curl -s -X "$method" \
                -H "Authorization: Bearer $token" \
                "$API_URL$endpoint"
        fi
    else
        if [ -n "$data" ]; then
            curl -s -X "$method" \
                -H "Content-Type: application/json" \
                -d "$data" \
                "$API_URL$endpoint"
        else
            curl -s -X "$method" \
                "$API_URL$endpoint"
        fi
    fi
}

# Step 1: Login
echo "Step 1: Logging in..."
LOGIN_RESPONSE=$(api_call POST "/api/auth/login" "{\"email\":\"$EMAIL\",\"password\":\"$PASSWORD\"}")

# Extract token (using jq if available, otherwise basic grep)
if command -v jq &> /dev/null; then
    TOKEN=$(echo "$LOGIN_RESPONSE" | jq -r '.access_token // .token // empty')
else
    TOKEN=$(echo "$LOGIN_RESPONSE" | grep -o '"access_token":"[^"]*"' | cut -d'"' -f4)
    if [ -z "$TOKEN" ]; then
        TOKEN=$(echo "$LOGIN_RESPONSE" | grep -o '"token":"[^"]*"' | cut -d'"' -f4)
    fi
fi

if [ -z "$TOKEN" ]; then
    print_error "Login failed. Could not extract token."
    echo "Response: $LOGIN_RESPONSE"
    exit 1
fi

print_success "Logged in successfully"
echo ""

# Step 2: Check system mode
echo "Step 2: Checking system mode..."
MODE_RESPONSE=$(api_call GET "/api/system/mode" "" "$TOKEN")
echo "$MODE_RESPONSE" | jq '.' 2>/dev/null || echo "$MODE_RESPONSE"
print_info "System mode retrieved"
echo ""

# Step 3: Check system status
echo "Step 3: Checking system status..."
STATUS_RESPONSE=$(api_call GET "/api/system/status" "" "$TOKEN")
echo "$STATUS_RESPONSE" | jq '.' 2>/dev/null || echo "$STATUS_RESPONSE"
print_info "System status retrieved"
echo ""

# Step 4: Get bots list
echo "Step 4: Fetching bots list..."
BOTS_RESPONSE=$(api_call GET "/api/bots" "" "$TOKEN")

# Extract first bot UUID
if command -v jq &> /dev/null; then
    BOT_ID=$(echo "$BOTS_RESPONSE" | jq -r '.bots[0].id // empty')
else
    BOT_ID=$(echo "$BOTS_RESPONSE" | grep -o '"id":"[^"]*"' | head -1 | cut -d'"' -f4)
fi

if [ -z "$BOT_ID" ]; then
    print_error "No bots found. Please create a bot first."
    exit 1
fi

print_success "Found bot: $BOT_ID"
echo ""

# Step 5: Try to resume the bot
echo "Step 5: Attempting to resume bot..."
RESUME_RESPONSE=$(api_call POST "/api/bots/$BOT_ID/resume" "" "$TOKEN")

# Check if resume was successful
if echo "$RESUME_RESPONSE" | grep -q '"success":true\|"status":"active"'; then
    print_success "Bot resumed successfully!"
    echo "$RESUME_RESPONSE" | jq '.' 2>/dev/null || echo "$RESUME_RESPONSE"
else
    print_error "Bot resume failed or returned an error"
    echo "$RESUME_RESPONSE" | jq '.' 2>/dev/null || echo "$RESUME_RESPONSE"
    
    # Check if it's a 409 error about paper trading disabled
    if echo "$RESUME_RESPONSE" | grep -q "Paper trading is disabled"; then
        print_error "Paper trading is disabled in environment or system mode"
        echo "Please set PAPER_TRADING=true or ENABLE_PAPER_TRADING=true in backend/.env"
        exit 1
    fi
fi

echo ""
echo "=================================================="
echo "Verification Summary"
echo "=================================================="
echo "API URL: $API_URL"
echo "Bot ID: $BOT_ID"
echo ""
print_success "All checks completed!"
echo ""
