#!/bin/bash

# Deploy Changed Files Script
# Pulls latest changes, runs tests, rsyncs only changed backend files
# Restarts service and validates health, rolls back if health check fails

set -e

# Configuration
REMOTE_USER="${DEPLOY_USER:-amarktai}"
REMOTE_HOST="${DEPLOY_HOST:-localhost}"
REMOTE_PATH="${DEPLOY_PATH:-/var/amarktai/app}"
SERVICE_NAME="amarktai-api"
BACKUP_DIR="/var/amarktai/backups"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo "🚀 Amarktai Network - Deploy Changed Files"
echo "==========================================="
echo ""

# Step 1: Pull latest changes
echo -e "${YELLOW}Step 1: Pulling latest changes...${NC}"
git fetch origin
CURRENT_COMMIT=$(git rev-parse HEAD)
git pull origin $(git rev-parse --abbrev-ref HEAD)
NEW_COMMIT=$(git rev-parse HEAD)

if [ "$CURRENT_COMMIT" == "$NEW_COMMIT" ]; then
    echo -e "${GREEN}✅ Already up to date${NC}"
else
    echo -e "${GREEN}✅ Updated from $CURRENT_COMMIT to $NEW_COMMIT${NC}"
fi

# Step 2: Run backend tests
echo ""
echo -e "${YELLOW}Step 2: Running backend tests...${NC}"
cd backend

if [ -f "venv/bin/activate" ]; then
    source venv/bin/activate
else
    echo -e "${RED}❌ Virtual environment not found${NC}"
    exit 1
fi

# Run tests
if [ -f "tests/test_api_structure.py" ]; then
    python -m pytest tests/test_api_structure.py -v
    if [ $? -ne 0 ]; then
        echo -e "${RED}❌ Tests failed - aborting deployment${NC}"
        exit 1
    fi
    echo -e "${GREEN}✅ Tests passed${NC}"
else
    echo -e "${YELLOW}⚠️  No tests found, skipping...${NC}"
fi

cd ..

# Step 3: Get list of changed files
echo ""
echo -e "${YELLOW}Step 3: Identifying changed files...${NC}"

if [ "$CURRENT_COMMIT" != "$NEW_COMMIT" ]; then
    CHANGED_FILES=$(git diff --name-only $CURRENT_COMMIT $NEW_COMMIT -- backend/)
    
    if [ -z "$CHANGED_FILES" ]; then
        echo -e "${GREEN}✅ No backend files changed${NC}"
        exit 0
    fi
    
    echo "Changed files:"
    echo "$CHANGED_FILES"
else
    echo -e "${YELLOW}⚠️  No new commits, deploying all backend files${NC}"
    CHANGED_FILES=""
fi

# Step 4: Create backup
echo ""
echo -e "${YELLOW}Step 4: Creating backup...${NC}"

if [ "$REMOTE_HOST" != "localhost" ]; then
    # Remote deployment
    ssh ${REMOTE_USER}@${REMOTE_HOST} "mkdir -p ${BACKUP_DIR}"
    BACKUP_NAME="backup_$(date +%Y%m%d_%H%M%S).tar.gz"
    
    ssh ${REMOTE_USER}@${REMOTE_HOST} "cd ${REMOTE_PATH} && tar -czf ${BACKUP_DIR}/${BACKUP_NAME} backend/ || true"
    echo -e "${GREEN}✅ Backup created: ${BACKUP_NAME}${NC}"
else
    # Local deployment
    mkdir -p ${BACKUP_DIR}
    BACKUP_NAME="backup_$(date +%Y%m%d_%H%M%S).tar.gz"
    cd ${REMOTE_PATH} && tar -czf ${BACKUP_DIR}/${BACKUP_NAME} backend/ || true
    echo -e "${GREEN}✅ Backup created: ${BACKUP_NAME}${NC}"
fi

# Step 5: Rsync changed files
echo ""
echo -e "${YELLOW}Step 5: Deploying files...${NC}"

if [ "$REMOTE_HOST" != "localhost" ]; then
    # Remote rsync
    if [ -n "$CHANGED_FILES" ]; then
        # Deploy only changed files
        for file in $CHANGED_FILES; do
            echo "Syncing $file..."
            rsync -avz "$file" ${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_PATH}/"$file"
        done
    else
        # Deploy entire backend directory
        rsync -avz --exclude='venv/' --exclude='__pycache__/' --exclude='*.pyc' backend/ ${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_PATH}/backend/
    fi
else
    # Local deployment (same machine)
    if [ -n "$CHANGED_FILES" ]; then
        for file in $CHANGED_FILES; do
            echo "Copying $file..."
            cp -r "$file" ${REMOTE_PATH}/"$file"
        done
    else
        rsync -avz --exclude='venv/' --exclude='__pycache__/' --exclude='*.pyc' backend/ ${REMOTE_PATH}/backend/
    fi
fi

echo -e "${GREEN}✅ Files deployed${NC}"

# Step 6: Restart service
echo ""
echo -e "${YELLOW}Step 6: Restarting service...${NC}"

if [ "$REMOTE_HOST" != "localhost" ]; then
    ssh ${REMOTE_USER}@${REMOTE_HOST} "sudo systemctl restart ${SERVICE_NAME}"
else
    sudo systemctl restart ${SERVICE_NAME}
fi

# Wait for service to start
sleep 5

echo -e "${GREEN}✅ Service restarted${NC}"

# Step 7: Health check
echo ""
echo -e "${YELLOW}Step 7: Running health check...${NC}"

MAX_RETRIES=5
RETRY_COUNT=0
HEALTH_OK=false

while [ $RETRY_COUNT -lt $MAX_RETRIES ]; do
    if [ "$REMOTE_HOST" != "localhost" ]; then
        HEALTH_RESPONSE=$(ssh ${REMOTE_USER}@${REMOTE_HOST} "curl -s http://localhost:8000/api/health/ping || echo 'FAIL'")
    else
        HEALTH_RESPONSE=$(curl -s http://localhost:8000/api/health/ping || echo "FAIL")
    fi
    
    if echo "$HEALTH_RESPONSE" | grep -q "ok"; then
        HEALTH_OK=true
        break
    fi
    
    RETRY_COUNT=$((RETRY_COUNT + 1))
    echo "Health check attempt $RETRY_COUNT/$MAX_RETRIES..."
    sleep 3
done

if [ "$HEALTH_OK" = true ]; then
    echo -e "${GREEN}✅ Health check passed${NC}"
    echo ""
    echo -e "${GREEN}🎉 Deployment successful!${NC}"
    exit 0
else
    echo -e "${RED}❌ Health check failed after $MAX_RETRIES attempts${NC}"
    
    # Rollback
    echo ""
    echo -e "${YELLOW}Rolling back to previous version...${NC}"
    
    if [ "$REMOTE_HOST" != "localhost" ]; then
        ssh ${REMOTE_USER}@${REMOTE_HOST} "cd ${REMOTE_PATH} && tar -xzf ${BACKUP_DIR}/${BACKUP_NAME}"
        ssh ${REMOTE_USER}@${REMOTE_HOST} "sudo systemctl restart ${SERVICE_NAME}"
    else
        cd ${REMOTE_PATH} && tar -xzf ${BACKUP_DIR}/${BACKUP_NAME}
        sudo systemctl restart ${SERVICE_NAME}
    fi
    
    echo -e "${YELLOW}⚠️  Rolled back to backup: ${BACKUP_NAME}${NC}"
    exit 1
fi
