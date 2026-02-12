#!/bin/bash
# Deploy Frontend Script
# Builds and deploys the frontend for production.
#
# Usage: ./scripts/deploy_frontend.sh [DOMAIN]
# Example: ./scripts/deploy_frontend.sh amarktai.com

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
FRONTEND_DIR="${PROJECT_ROOT}/frontend"
BUILD_DIR="${FRONTEND_DIR}/build"
RUN_USER="${SUDO_USER:-$(whoami)}"
NODE_CMD_PREFIX=""
if [ "$(id -u)" = "0" ] && [ -n "${SUDO_USER:-}" ]; then
    NODE_CMD_PREFIX="sudo -u ${RUN_USER}"
fi
DOMAIN="${1:-amarktai.com}"

echo "=== Frontend Deployment ==="
echo "Project root: $PROJECT_ROOT"
echo "Frontend dir: $FRONTEND_DIR"
echo "Domain: $DOMAIN"
echo ""

# Step 1: Navigate to frontend directory
cd "$FRONTEND_DIR"

# Step 2: Clean install
if [ ! -f "package.json" ]; then
    echo "❌ package.json not found in $FRONTEND_DIR - wrong directory?"
    exit 1
fi

echo "Step 1/4: Cleaning node_modules and build..."
if [ -d "$BUILD_DIR" ]; then
    sudo chown -R "$RUN_USER":"$RUN_USER" "$BUILD_DIR" 2>/dev/null || true
    chmod -R u+rwX "$BUILD_DIR" 2>/dev/null || true
fi
rm -rf node_modules
rm -rf "$BUILD_DIR"
echo "✅ Cleaned"

echo ""
echo "Step 2/4: Installing dependencies (npm ci)..."
$NODE_CMD_PREFIX npm ci
if [ $? -ne 0 ]; then
    echo "❌ npm ci failed!"
    exit 1
fi
echo "✅ Dependencies installed"

# Step 3: Build
echo ""
echo "Step 3/4: Building frontend (npm run build)..."
$NODE_CMD_PREFIX npm run build
if [ $? -ne 0 ]; then
    echo "❌ npm run build failed!"
    exit 1
fi
echo "✅ Build completed"

# Step 4: Verify build output
echo ""
echo "Step 4/4: Verifying build output..."

if [ ! -d "$BUILD_DIR" ]; then
    echo "❌ Build directory not found: $BUILD_DIR"
    exit 1
fi

sudo chown -R "$RUN_USER":"$RUN_USER" "$BUILD_DIR" 2>/dev/null || true

# Check index.html exists
if [ ! -f "$BUILD_DIR/index.html" ]; then
    echo "❌ index.html not found in build directory"
    exit 1
fi
echo "  ✅ index.html exists"

# Check JS bundle exists
JS_BUNDLE=$(find "$BUILD_DIR/static/js" -name "main.*.js" 2>/dev/null | head -1)
if [ -z "$JS_BUNDLE" ]; then
    echo "❌ No main.*.js bundle found in build/static/js/"
    exit 1
fi

JS_SIZE=$(stat -f%z "$JS_BUNDLE" 2>/dev/null || stat -c%s "$JS_BUNDLE" 2>/dev/null || echo "0")
echo "  ✅ JS bundle: $(basename "$JS_BUNDLE") (${JS_SIZE} bytes)"

if [ "$JS_SIZE" -lt 51200 ]; then
    echo "  ⚠️  WARNING: JS bundle is smaller than 50KB (${JS_SIZE} bytes). May indicate build issue."
fi

# Check asset-manifest.json exists
if [ ! -f "$BUILD_DIR/asset-manifest.json" ]; then
    echo "  ⚠️  asset-manifest.json not found"
else
    echo "  ✅ asset-manifest.json exists"
fi

# Check index.html references /static/js/
if grep -q "/static/js/" "$BUILD_DIR/index.html"; then
    echo "  ✅ index.html references /static/js/"
else
    echo "  ⚠️  index.html does not reference /static/js/ - check build config"
fi

echo ""
echo "=== Build Verification Complete ==="
echo ""

# Optional: Verify live deployment if domain is accessible
if [ -n "$DOMAIN" ]; then
    echo "=== Live Deployment Verification ==="
    
    MAX_RETRIES=3
    RETRY_DELAY=5
    
    for attempt in $(seq 1 $MAX_RETRIES); do
        echo "Attempt $attempt/$MAX_RETRIES..."
        
        # Check index page contains /static/js/
        INDEX_CONTENT=$(curl -s --connect-timeout 10 "https://${DOMAIN}/" 2>/dev/null || echo "")
        if echo "$INDEX_CONTENT" | grep -q "/static/js/"; then
            echo "  ✅ https://${DOMAIN}/ contains /static/js/"
            
            # Extract and check JS bundle
            JS_URL=$(echo "$INDEX_CONTENT" | grep -oP '/static/js/main\.[^"]+\.js' | head -1 || echo "")
            if [ -n "$JS_URL" ]; then
                HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 10 "https://${DOMAIN}${JS_URL}" 2>/dev/null || echo "000")
                if [ "$HTTP_CODE" = "200" ]; then
                    REMOTE_SIZE=$(curl -sI --connect-timeout 10 "https://${DOMAIN}${JS_URL}" 2>/dev/null | grep -i content-length | awk '{print $2}' | tr -d '\r' || echo "0")
                    echo "  ✅ JS bundle accessible: ${JS_URL} (HTTP ${HTTP_CODE}, ~${REMOTE_SIZE} bytes)"
                else
                    echo "  ❌ JS bundle returned HTTP ${HTTP_CODE}: ${JS_URL}"
                fi
            fi
            
            # Check asset-manifest.json
            MANIFEST_CODE=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout 10 "https://${DOMAIN}/asset-manifest.json" 2>/dev/null || echo "000")
            if [ "$MANIFEST_CODE" = "200" ]; then
                echo "  ✅ asset-manifest.json accessible (HTTP ${MANIFEST_CODE})"
            else
                echo "  ⚠️  asset-manifest.json returned HTTP ${MANIFEST_CODE}"
            fi
            
            echo ""
            echo "✅ Live deployment verification passed!"
            exit 0
        else
            echo "  ⚠️  index page does not contain /static/js/ references yet"
            if [ "$attempt" -lt "$MAX_RETRIES" ]; then
                echo "  Retrying in ${RETRY_DELAY}s..."
                sleep $RETRY_DELAY
            fi
        fi
    done
    
    echo "❌ Live deployment verification failed after $MAX_RETRIES attempts"
    exit 1
fi

echo "✅ Frontend deployment complete (local build verified)"
