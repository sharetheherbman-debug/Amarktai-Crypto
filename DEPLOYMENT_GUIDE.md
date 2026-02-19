# Deployment & Verification Guide

## Files Changed

### Backend Changes
1. **backend/routes/bot_lifecycle.py** - Fixed env parsing to use `env_bool()` for paper/live trading flags
2. **backend/routes/bot_control.py** - Added feature flags check to resume endpoint
3. **backend/routes/diagnostics.py** - Fixed autopilot env check to use `env_bool()`
4. **backend/routes/system_status.py** - Updated to use unified feature flags service
5. **backend/core/feature_flags.py** - NEW: Unified feature flags with precedence rules
6. **backend/utils/env_utils.py** - (Already existed) Provides `env_bool()` function

### Frontend Changes
1. **frontend/src/pages/Landing.js** - Updated logo to 200px, added "AI" branding, improved copy
2. **frontend/src/pages/Login.js** - Updated logo to 200px, added "AI" branding
3. **frontend/src/pages/Register.js** - Updated logo to 200px, added "AI" branding
4. **frontend/src/pages/Dashboard.js** - Updated logo to 200px, added "AI" branding
5. **frontend/src/components/AuthLayout.js** - Updated video source to new file
6. **frontend/src/components/AuthLayout.css** - New 4-color gradient, lighter overlay, branding styles
7. **frontend/public/assets/final-logo-v2.png** - NEW: Logo asset
8. **frontend/public/assets/amarktai-network-final.mp4** - NEW: Video asset

### Test & Scripts
1. **tests/test_feature_flags_resume.py** - NEW: Comprehensive tests for feature flags and resume
2. **scripts/verify_resume.sh** - NEW: Verification script with curl commands

---

## VPS Deployment Commands

### 1. Update Backend Service

```bash
# Navigate to backend directory
cd /home/amarktai/Amarktai-Network---Deployment/backend

# Pull latest changes
git pull origin copilot/fix-paper-trading-bot-resume

# Install any new dependencies (if needed)
pip install -r requirements.txt

# Restart backend service
sudo systemctl restart amarktai-backend

# Check service status
sudo systemctl status amarktai-backend

# View logs for any errors
sudo journalctl -u amarktai-backend -f -n 50
```

### 2. Update and Rebuild Frontend

```bash
# Navigate to frontend directory
cd /home/amarktai/Amarktai-Network---Deployment/frontend

# Pull latest changes (if not already done)
git pull origin copilot/fix-paper-trading-bot-resume

# Install any new dependencies
npm install

# Build production bundle
npm run build

# Copy build to nginx serve directory (adjust path as needed)
sudo cp -r build/* /var/www/amarktai/html/

# Restart nginx
sudo systemctl restart nginx

# Check nginx status
sudo systemctl status nginx
```

### 3. Verify Environment Variables

```bash
# Check backend .env file has correct settings
cd /home/amarktai/Amarktai-Network---Deployment/backend
cat .env | grep -E "PAPER_TRADING|LIVE_TRADING|ENABLE_"

# Should show something like:
# PAPER_TRADING=true
# ENABLE_PAPER_TRADING=true
# LIVE_TRADING=false
# ENABLE_LIVE_TRADING=false
# ENABLE_TRADING=true
# ENABLE_AUTOPILOT=false
```

---

## Verification Checklist

### Backend API Verification

#### 1. Check System Mode
```bash
curl -X GET "http://localhost:8000/api/system/mode" \
  -H "Authorization: Bearer YOUR_TOKEN_HERE" \
  | jq '.'
```

**Expected Response:**
```json
{
  "success": true,
  "mode": "paper",
  "paperTrading": true,
  "liveTrading": false,
  "autopilot": false,
  "updated_at": "2024-XX-XXTXX:XX:XX",
  "updated_by": "user_id"
}
```

#### 2. Check System Status (NEW - with effective flags)
```bash
curl -X GET "http://localhost:8000/api/system/status" \
  -H "Authorization: Bearer YOUR_TOKEN_HERE" \
  | jq '.feature_flags, .trading_mode_flags'
```

**Expected Response:**
```json
{
  "feature_flags": {
    "enable_trading": true,
    "enable_schedulers": false,
    "enable_autopilot": false,
    "enable_ccxt": true,
    "enable_paper_trading": true,
    "enable_live_trading": false
  },
  "trading_mode_flags": {
    "paper_trading": true,
    "live_trading": false,
    "effective_mode": "paper",
    "reasons": {
      "paper_trading": "Enabled",
      "live_trading": "Disabled in environment (ENV hard limit)",
      "autopilot": "Disabled in system mode (user preference)"
    }
  }
}
```

#### 3. Get Bots List
```bash
curl -X GET "http://localhost:8000/api/bots" \
  -H "Authorization: Bearer YOUR_TOKEN_HERE" \
  | jq '.bots[0]'
```

**Extract bot ID from response** (use it in next step)

#### 4. Resume Bot (CRITICAL TEST)
```bash
# Replace BOT_UUID with actual bot ID from step 3
curl -X POST "http://localhost:8000/api/bots/BOT_UUID/resume" \
  -H "Authorization: Bearer YOUR_TOKEN_HERE" \
  -H "Content-Type: application/json" \
  | jq '.'
```

**Expected Success Response:**
```json
{
  "success": true,
  "bot_id": "bot_uuid",
  "status": "active",
  "message": "Bot resumed successfully"
}
```

**If paper trading is disabled, you'll get:**
```json
{
  "detail": "Cannot resume bot: Disabled in environment (ENV hard limit)"
}
```

#### 5. Check Bot Status Changed to Active
```bash
curl -X GET "http://localhost:8000/api/bots/BOT_UUID/status" \
  -H "Authorization: Bearer YOUR_TOKEN_HERE" \
  | jq '.'
```

**Expected Response:**
```json
{
  "bot_id": "bot_uuid",
  "status": "active",
  "is_active": true,
  "is_paused": false,
  ...
}
```

### Frontend UI Verification

#### Visual Checks (Browser)

1. **Landing Page** (`/`)
   - [ ] Logo displays at 200x200px
   - [ ] "AI" in "Amarktai" is blue (#3b82f6)
   - [ ] Background gradient shows 4 colors (purple→blue→teal→dark)
   - [ ] Video overlay is lighter (not too dark)
   - [ ] "Welcome to" is close to brand name
   - [ ] Headline reads: "Advanced AI-Powered Trading Platform"
   - [ ] Subheader reads: "Real-Time Intelligence • Autonomous Decision-Making • 24/7 Market Analysis"

2. **Login Page** (`/login`)
   - [ ] Logo displays at 200x200px
   - [ ] "AI" in "Amarktai" is blue
   - [ ] Same gradient and lighter overlay

3. **Register Page** (`/register`)
   - [ ] Logo displays at 200x200px
   - [ ] "AI" in "Amarktai" is blue
   - [ ] Same gradient and lighter overlay

4. **Dashboard** (`/dashboard`)
   - [ ] Logo in sidebar is 200x200px
   - [ ] "AI" in top bar brand name is blue
   - [ ] Dashboard functionality still works

### Using the Verification Script

```bash
# Set environment variables
export API_URL="http://localhost:8000"
export TEST_USER_EMAIL="your-email@example.com"
export TEST_USER_PASSWORD="your-password"

# Run verification script
cd /home/amarktai/Amarktai-Network---Deployment
./scripts/verify_resume.sh
```

**Expected Output:**
```
==================================================
Paper Trading Resume Verification Script
==================================================

Step 1: Logging in...
✓ Logged in successfully

Step 2: Checking system mode...
{
  "success": true,
  "mode": "paper",
  "paperTrading": true,
  ...
}

Step 3: Checking system status...
{
  "success": true,
  "feature_flags": { ... },
  "trading_mode_flags": { ... }
}

Step 4: Fetching bots list...
✓ Found bot: bot_uuid_here

Step 5: Attempting to resume bot...
✓ Bot resumed successfully!

==================================================
Verification Summary
==================================================
API URL: http://localhost:8000
Bot ID: bot_uuid_here

✓ All checks completed!
```

---

## Running Tests

```bash
# Navigate to project root
cd /home/amarktai/Amarktai-Network---Deployment

# Run the new feature flags tests
pytest tests/test_feature_flags_resume.py -v

# Expected output:
# test_feature_flags_resume.py::TestFeatureFlags::test_get_env_flags_with_canonical_names PASSED
# test_feature_flags_resume.py::TestFeatureFlags::test_get_env_flags_with_legacy_names PASSED
# test_feature_flags_resume.py::TestFeatureFlags::test_env_bool_truthy_values PASSED
# test_feature_flags_resume.py::TestEffectiveFlags::test_effective_flags_env_hard_limit PASSED
# test_feature_flags_resume.py::TestBotResume::test_can_resume_paper_bot_when_enabled PASSED
# test_feature_flags_resume.py::TestBotResume::test_cannot_resume_paper_bot_when_disabled PASSED
```

---

## Troubleshooting

### Issue: Bot still cannot resume with 409 error

**Check 1: Environment variables**
```bash
cd /home/amarktai/Amarktai-Network---Deployment/backend
grep -E "PAPER_TRADING|ENABLE_PAPER_TRADING" .env
```

Should show at least one of:
- `PAPER_TRADING=true` or `PAPER_TRADING=1`
- `ENABLE_PAPER_TRADING=true` or `ENABLE_PAPER_TRADING=1`

**Check 2: System mode in database**
```bash
# Connect to MongoDB and check system_modes collection
mongo amarktai_trading
db.system_modes.find().pretty()
```

Should show `paperTrading: true`

**Fix:** If either is wrong, set in .env and restart backend:
```bash
echo "PAPER_TRADING=true" >> .env
sudo systemctl restart amarktai-backend
```

### Issue: Frontend not showing updated logo or branding

**Check 1: Assets copied**
```bash
ls -la /var/www/amarktai/html/assets/ | grep -E "final-logo-v2|amarktai-network-final"
```

**Check 2: Browser cache**
- Hard refresh: Ctrl+Shift+R (Windows/Linux) or Cmd+Shift+R (Mac)
- Or clear browser cache

**Fix:** Rebuild and redeploy frontend:
```bash
cd /home/amarktai/Amarktai-Network---Deployment/frontend
npm run build
sudo cp -r build/* /var/www/amarktai/html/
```

---

## Summary

This update resolves the critical paper trading resume bug by:

1. **Fixing env parsing** - Now accepts "true", "1", "yes", "on" (not just "1")
2. **Unifying feature flags** - Single source of truth with clear precedence rules
3. **Improving consistency** - System status and mode endpoints now aligned
4. **Adding comprehensive tests** - Full test coverage for resume scenarios
5. **Polishing UI** - Professional branding with logo, gradient, and "AI" styling

All changes are backward-compatible and maintain existing safety guardrails.
