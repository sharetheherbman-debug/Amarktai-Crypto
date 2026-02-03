# Frontend Deployment Guide - Build Versioning and Caching

## Build Process

The frontend build process automatically injects version information:

```bash
./scripts/build_frontend.sh
```

This creates:
- `build/version.json` with git SHA and build time
- Environment variables `REACT_APP_VERSION` and `REACT_APP_GIT_SHA` for the build

## Nginx Configuration for Cache Control

To prevent old dashboards from persisting, configure nginx to disable caching for `index.html`:

### /etc/nginx/sites-available/amarktai (or your site config)

```nginx
server {
    listen 80;
    server_name your-domain.com;
    
    root /var/amarktai/frontend;
    index index.html;
    
    # Disable cache for index.html to always fetch latest
    location = /index.html {
        add_header Cache-Control "no-cache, no-store, must-revalidate";
        add_header Pragma "no-cache";
        add_header Expires "0";
        try_files $uri =404;
    }
    
    # Allow caching for static assets (JS, CSS, images)
    location /static/ {
        add_header Cache-Control "public, max-age=31536000, immutable";
        try_files $uri =404;
    }
    
    # Version info endpoint (no cache)
    location = /version.json {
        add_header Cache-Control "no-cache, no-store, must-revalidate";
        add_header Pragma "no-cache";
        add_header Expires "0";
        try_files $uri =404;
    }
    
    # SPA routing - all other routes serve index.html
    location / {
        try_files $uri $uri/ /index.html;
    }
    
    # API proxy
    location /api/ {
        proxy_pass http://localhost:8000/api/;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_cache_bypass $http_upgrade;
    }
}
```

## Deployment Steps

1. **Build the frontend with version info:**
   ```bash
   cd /home/amarktai/Amarktai-Network---Deployment
   ./scripts/build_frontend.sh
   ```

2. **Backup existing frontend (optional):**
   ```bash
   sudo mv /var/amarktai/frontend /var/amarktai/frontend.backup.$(date +%Y%m%d_%H%M%S)
   ```

3. **Deploy new build:**
   ```bash
   sudo mkdir -p /var/amarktai/frontend
   sudo cp -r frontend/build/* /var/amarktai/frontend/
   sudo chown -R www-data:www-data /var/amarktai/frontend
   ```

4. **Verify deployment:**
   ```bash
   # Check version file
   curl http://localhost/version.json
   
   # Check backend build info
   curl http://localhost:8000/api/build/info
   
   # Should show matching git SHAs
   ```

5. **Test in browser:**
   - Open dashboard
   - Check footer for version badge showing commit hash
   - Verify it matches backend version

## Troubleshooting

### Old dashboard still showing after deployment

**Cause:** Browser cache or nginx cache serving old `index.html`

**Fix:**
1. Clear browser cache (Ctrl+Shift+R or Cmd+Shift+R)
2. Verify nginx cache control headers:
   ```bash
   curl -I http://your-domain.com/index.html | grep -i cache
   # Should show: Cache-Control: no-cache, no-store, must-revalidate
   ```
3. Restart nginx:
   ```bash
   sudo systemctl restart nginx
   ```

### Version badge not showing

**Cause:** VersionBadge component not enabled or build info endpoint not working

**Fix:**
1. Check frontend code has VersionBadge uncommented
2. Test backend endpoint:
   ```bash
   curl http://localhost:8000/api/build/info
   ```
3. Check browser console for errors

### Versions don't match between frontend and backend

**Cause:** Frontend or backend deployed from different commits

**Fix:**
1. Ensure both are built from same commit:
   ```bash
   git log -1 --oneline
   ```
2. Set BUILD_VERSION env var for backend:
   ```bash
   export BUILD_VERSION=$(git rev-parse HEAD)
   export BUILD_TIME=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
   ```
3. Rebuild both frontend and restart backend

## Environment Variables

### Frontend (build time)
- `REACT_APP_VERSION` - Git SHA (set by build script)
- `REACT_APP_GIT_SHA` - Git SHA (set by build script)
- `REACT_APP_BUILD_TIME` - Build timestamp

### Backend (runtime)
- `BUILD_VERSION` or `GIT_SHA` - Git commit hash
- `BUILD_TIME` - Build timestamp
- `ENVIRONMENT` - prod/staging/dev

Set these in your systemd service or deployment script.
