#!/bin/bash
# Build script for frontend with version injection

set -e

echo "🏗️  Building Amarktai Frontend..."

# Get git SHA for version tagging
GIT_SHA=$(git rev-parse --short HEAD 2>/dev/null || echo "dev")
BUILD_TIME=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
VERSION_TAG=$(git describe --tags --exact-match 2>/dev/null || echo "unknown")

echo "   Version: $GIT_SHA"
echo "   Built at: $BUILD_TIME"

# Export as environment variables for React
export REACT_APP_GIT_SHA=$GIT_SHA
export REACT_APP_VERSION=$GIT_SHA
export REACT_APP_BUILD_TIME=$BUILD_TIME
export REACT_APP_BUILD_SHA=$GIT_SHA
export REACT_APP_BUILD_TIMESTAMP=$BUILD_TIME
export REACT_APP_VERSION_TAG=$VERSION_TAG

# Navigate to frontend directory
cd "$(dirname "$0")/../frontend"
rm -rf build

# Check if node_modules exists
if [ ! -d "node_modules" ]; then
    echo "📦 Installing dependencies..."
    npm install
fi

# Build the frontend
echo "🔨 Building..."
npm run build

echo "✅ Frontend build complete!"
echo "   Output: $(pwd)/build"
echo "   Files:"
ls -lh build/static/js/*.js 2>/dev/null | head -3 || echo "   (no JS files found)"

# Create a version.json file in build directory
cat > build/version.json <<EOF
{
  "version": "$GIT_SHA",
  "tag": "$VERSION_TAG",
  "built_at": "$BUILD_TIME",
  "frontend": true
}
EOF

echo "📝 Version file created: build/version.json"
cat build/version.json

echo ""
echo "🚀 Ready for deployment!"
echo "   To deploy: Copy the build/ directory to your web server"
echo "   To verify: curl https://your-domain.com/version.json"
