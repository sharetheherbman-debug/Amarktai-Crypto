# Dashboard Routes Used

**Generated:** 2026-01-13  
**Purpose:** Complete list of all backend API endpoints used by the dashboard frontend

---

## Overview

This document lists all API endpoints called by the Amarktai Network dashboard (frontend), organized by category. Each endpoint includes:
- HTTP method
- Path
- Purpose
- Status (✅ exists, ⚠️ needs verification, ❌ missing)
- Authentication requirement

---

## Authentication & User Management

| Method | Path | Purpose | Auth | Status |
|--------|------|---------|------|--------|
| POST | `/api/auth/register` | Register new user | No | ✅ |
| POST | `/api/auth/login` | User login | No | ✅ |
| GET | `/api/auth/me` | Get current user profile | Yes | ⚠️ (ObjectId issue) |
| PUT | `/api/auth/profile` | Update user profile | Yes | ✅ |

---

## Bot Management

| Method | Path | Purpose | Auth | Status |
|--------|------|---------|------|--------|
| GET | `/api/bots` | List user's bots | Yes | ✅ |
| POST | `/api/bots` | Create single bot | Yes | ✅ |
| POST | `/api/bots/batch-create` | Batch create bots | Yes | ✅ |
| PUT | `/api/bots/{bot_id}` | Update bot settings | Yes | ✅ |
| DELETE | `/api/bots/{bot_id}` | Delete bot | Yes | ✅ |
| POST | `/api/bots/{bot_id}/{action}` | Bot lifecycle actions (pause/resume) | Yes | ✅ |
| POST | `/api/bots/uagent` | Create uAgent bot | Yes | ✅ |
| POST | `/api/bots/flokx` | Create Flokx bot | Yes | ✅ |
| POST | `/api/bots/evolve` | Trigger bot evolution | Yes | ✅ |
| GET | `/api/bots/eligible-for-promotion` | Check promotion eligibility | Yes | ✅ |
| POST | `/api/bots/confirm-live-switch` | Confirm live trading switch | Yes | ✅ |

---

## Trading & Positions

| Method | Path | Purpose | Auth | Status |
|--------|------|---------|------|--------|
| GET | `/api/trades/recent?limit=50` | Get recent trades | Yes | ✅ |
| GET | `/api/prices/live` | Get live market prices | Yes | ✅ |

---

## Portfolio & Metrics

| Method | Path | Purpose | Auth | Status |
|--------|------|---------|------|--------|
| GET | `/api/portfolio/summary` | Get portfolio summary/metrics | Yes | ✅ |
| GET | `/api/profits?period={period}` | Get profit data by period (daily/weekly/monthly) | Yes | ✅ |
| GET | `/api/metrics` | Get Prometheus metrics | Yes | ⚠️ (needs auth check) |
| GET | `/api/analytics/countdown-to-million` | Get countdown to R1M | Yes | ✅ |

---

## System Control

| Method | Path | Purpose | Auth | Status |
|--------|------|---------|------|--------|
| GET | `/api/system/mode` | Get system modes (paper/live/autopilot) | Yes | ✅ |
| PUT | `/api/system/mode` | Set system mode | Yes | ✅ |
| POST | `/api/system/emergency-stop` | Emergency stop all trading | Yes | ✅ |

---

## API Keys & Configuration

| Method | Path | Purpose | Auth | Status |
|--------|------|---------|------|--------|
| GET | `/api/api-keys` | List user's API keys | Yes | ✅ |
| POST | `/api/keys/save` | Save API key | Yes | ✅ |
| POST | `/api/keys/test` | Test API key connection | Yes | ✅ |
| DELETE | `/api/api-keys/{provider}` | Delete API key | Yes | ✅ |
| GET | `/api/user/api-keys/{service}` | Get specific service key | Yes | ✅ |
| POST | `/api/user/api-keys` | Save user API key | Yes | ✅ |
| DELETE | `/api/user/api-keys/{service}` | Delete service key | Yes | ✅ |
| GET | `/api/user/payment-config` | Get payment configuration | Yes | ✅ |
| POST | `/api/user/payment-config` | Update payment configuration | Yes | ✅ |
| POST | `/api/user/generate-wallet` | Generate wallet | Yes | ✅ |

---

## Wallet & Financial

| Method | Path | Purpose | Auth | Status |
|--------|------|---------|------|--------|
| GET | `/api/wallet/balances` | Get wallet balances | Yes | ✅ |
| GET | `/api/wallet/requirements` | Get wallet requirements | Yes | ✅ |
| GET | `/api/wallet/funding-plans?status=awaiting_deposit` | Get funding plans | Yes | ✅ |
| POST | `/api/wallet/funding-plans/{planId}/cancel` | Cancel funding plan | Yes | ✅ |
| GET | `/api/wallet/deposit-address` | Get deposit address | Yes | ✅ |

---

## AI & Chat

| Method | Path | Purpose | Auth | Status |
|--------|------|---------|------|--------|
| POST | `/api/chat` | Send chat message to AI | Yes | ✅ |
| GET | `/api/ai/chat/history` | Get chat history | Yes | ✅ |
| POST | `/api/ai/chat` | Send AI chat message | Yes | ✅ |
| GET | `/api/insights/daily` | Get AI-generated daily insights | Yes | ✅ |

---

## Machine Learning

| Method | Path | Purpose | Auth | Status |
|--------|------|---------|------|--------|
| GET | `/api/ml/predict/{pair}?timeframe={tf}` | ML-based price prediction | Yes | ✅ |
| GET | `/api/ml/sentiment/{pair}` | Sentiment analysis | Yes | ✅ |
| GET | `/api/ml/anomalies` | Detect anomalies | Yes | ✅ |

---

## Autonomous Systems

| Method | Path | Purpose | Auth | Status |
|--------|------|---------|------|--------|
| POST | `/api/autonomous/bodyguard/system-check` | Trigger bodyguard check | Yes | ✅ |
| POST | `/api/autonomous/learning/trigger` | Trigger learning system | Yes | ✅ |
| POST | `/api/autonomous/reinvest-profits` | Trigger profit reinvestment | Yes | ✅ |
| POST | `/api/autonomous/promote-bots` | Manually trigger bot promotion | Yes | ✅ |
| GET | `/api/autonomous/market-regime?pair={pair}` | Get market regime | Yes | ✅ |

---

## Advanced Features

| Method | Path | Purpose | Auth | Status |
|--------|------|---------|------|--------|
| GET | `/api/advanced/whale/summary` | Get whale flow summary | Yes | ⚠️ (needs verification) |
| GET | `/api/flokx/alerts` | Get Flokx alerts | Yes | ❌ (may not exist) |

---

## Admin Endpoints

| Method | Path | Purpose | Auth | Status |
|--------|------|---------|------|--------|
| GET | `/api/admin/storage` | Get storage data | Admin | ⚠️ (returns 403) |
| GET | `/api/admin/users` | List all users | Admin | ✅ |
| GET | `/api/admin/system-stats` | Get system statistics | Admin | ✅ |
| GET | `/api/admin/health-check` | Health check | Admin | ✅ |
| POST | `/api/admin/email-all-users` | Email all users | Admin | ✅ |
| DELETE | `/api/admin/users/{userId}` | Delete user | Admin | ✅ |
| PUT | `/api/admin/users/{userId}/block` | Block/unblock user | Admin | ✅ |
| PUT | `/api/admin/users/{userId}/password` | Change user password | Admin | ✅ |
| POST | `/api/admin/emergency-stop` | Emergency stop (admin) | Admin | ✅ |

---

## Real-time Connections

| Method | Path | Purpose | Auth | Status |
|--------|------|---------|------|--------|
| WS | `/api/ws?token={token}` | WebSocket connection for real-time updates | Yes | ✅ |
| WS | `/ws/decisions` | WebSocket for decision trace | Yes | ✅ |
| SSE | `/api/realtime/events` | Server-Sent Events for real-time updates | Yes | ⚠️ (conditional on ENABLE_REALTIME) |

---

## Health & System

| Method | Path | Purpose | Auth | Status |
|--------|------|---------|------|--------|
| GET | `/api/health/ping` | Health check ping | No | ✅ |
| GET | `/` | Root endpoint | No | ✅ |

---

## Summary Statistics

### Total Endpoints
- **Total:** 70+ endpoints
- **Core functionality:** 50+ endpoints
- **Admin only:** 8 endpoints
- **Real-time:** 3 connections (2 WS + 1 SSE)

### Authentication Distribution
- **Public (no auth):** 3 endpoints (register, login, health)
- **User authenticated:** 50+ endpoints
- **Admin only:** 8 endpoints

### Status Breakdown
- ✅ **Working:** 65+ endpoints
- ⚠️ **Needs verification:** 5 endpoints
- ❌ **Missing:** 1 endpoint (Flokx alerts)

---

## Critical Paths for Dashboard

### Essential for Dashboard Load
1. `POST /api/auth/login` → Get JWT token
2. `GET /api/auth/me` → Verify user session
3. `GET /api/bots` → Load user's bots
4. `GET /api/portfolio/summary` → Load metrics
5. `GET /api/system/mode` → Load system modes

### Essential for Bot Management
1. `POST /api/bots` → Create new bot
2. `PUT /api/bots/{bot_id}` → Update bot
3. `DELETE /api/bots/{bot_id}` → Delete bot
4. `POST /api/bots/{bot_id}/pause` → Pause bot
5. `POST /api/bots/{bot_id}/resume` → Resume bot

### Essential for Trading
1. `GET /api/trades/recent` → Show trade history
2. `GET /api/prices/live` → Current prices
3. `GET /api/wallet/balances` → Wallet balances

### Essential for Real-time
1. `WS /api/ws` or `SSE /api/realtime/events` → Live updates
2. Real-time bot status changes
3. Real-time trade notifications
4. Real-time profit updates

---

## Recommendations

### High Priority Fixes
1. **Fix `/api/auth/me`** - Critical for dashboard auth flow
2. **Verify `/api/advanced/whale/summary`** - Used by Intelligence section
3. **Implement `/api/flokx/alerts`** stub - Prevent 404 errors
4. **Enable SSE by default** - Better than WS for dashboard updates
5. **Fix admin permissions** - Ensure admin endpoints properly check role

### Medium Priority Enhancements
1. Add platform comparison aggregation endpoint
2. Enhanced performance metrics endpoint
3. Batch operations for bot management
4. More granular permission system

### Low Priority Nice-to-Haves
1. GraphQL endpoint for complex queries
2. Bulk data export endpoints
3. Webhook configuration endpoints
4. Advanced analytics endpoints

---

**End of Dashboard Routes Documentation**
