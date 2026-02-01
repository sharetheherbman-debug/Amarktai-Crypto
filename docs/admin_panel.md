# Admin Panel Documentation

## Overview

The Amarktai Network Admin Panel provides comprehensive administrative control over users, bots, and system resources. It features **role-based access control (RBAC)**, complete audit logging, and powerful override capabilities for system management.

### Key Features

- **User Management**: View, block, reset passwords, delete users
- **Bot Override**: Change mode, pause/resume, restart, change exchange
- **System Monitoring**: VPS resources, process health, audit logs
- **Security**: Admin password protection, force logout, session management
- **Audit Trail**: Complete logging of all admin actions

---

## Authentication & RBAC

### Admin Role Requirement

All admin endpoints require `role == "admin"` or `is_admin == true`:

```python
# Database user structure
{
  "id": "user_uuid",
  "email": "admin@amarktai.com",
  "role": "admin",  # OR
  "is_admin": true,
  "created_at": "2024-01-15T10:00:00Z"
}
```

### Unlock Admin Panel

Admin panel requires password authentication:

```bash
POST /api/admin/unlock
Content-Type: application/json
Authorization: Bearer {user_token}

{
  "password": "Ashmor12@"
}
```

**Response:**
```json
{
  "success": true,
  "message": "Admin panel unlocked",
  "unlock_token": "dGhpc19pc19hX3Rva2Vu...",
  "expires_in": 3600
}
```

### Environment Configuration

```bash
# .env file
ADMIN_PASSWORD=Ashmor12@  # Default if not set
```

### Security Notes

- Password check is **case-insensitive** and **whitespace-tolerant**
- Unlock token valid for **1 hour**
- All admin actions are **audit logged** with IP address
- Failed unlock attempts are logged as security warnings

---

## User Management

### Get All Users

```bash
GET /api/admin/users
Authorization: Bearer {admin_token}
```

**Response:**
```json
{
  "users": [
    {
      "user_id": "user123",
      "username": "John Doe",
      "email": "john@example.com",
      "role": "user",
      "is_active": true,
      "created_at": "2024-01-01T00:00:00Z",
      "last_seen": "2024-01-15T10:30:00Z",
      "api_keys": {
        "openai": false,
        "luno": true,
        "binance": true,
        "kucoin": false,
      },
      "bots_summary": {
        "total": 5,
        "by_exchange": {
          "luno": 3,
          "binance": 2
        },
        "by_mode": {
          "paper": 4,
          "live": 1
        }
      },
      "resource_usage": {
        "trades_last_24h": 45,
        "total_trades": 1250
      }
    }
  ],
  "total_count": 1
}
```

### Get User Details

```bash
GET /api/admin/users/{user_id}
Authorization: Bearer {admin_token}
```

**Response:**
```json
{
  "user": {
    "id": "user123",
    "email": "john@example.com",
    "first_name": "John",
    "role": "user",
    "is_active": true,
    "created_at": "2024-01-01T00:00:00Z"
  },
  "bots": [
    {
      "id": "bot123",
      "name": "BTC Scalper",
      "exchange": "luno",
      "mode": "paper",
      "status": "active",
      "current_capital": 1050.0,
      "total_profit": 50.0
    }
  ],
  "recent_trades": [
    {
      "id": "trade123",
      "bot_id": "bot123",
      "symbol": "BTC/ZAR",
      "side": "buy",
      "quantity": 0.001,
      "price": 1000000,
      "pnl": 25.0,
      "timestamp": "2024-01-15T10:30:00Z"
    }
  ],
  "audit_logs": [
    {
      "event_type": "bot_created",
      "timestamp": "2024-01-15T09:00:00Z"
    }
  ],
  "stats": {
    "total_bots": 5,
    "total_trades": 1250,
    "total_profit": 250.0
  }
}
```

### Block User

```bash
POST /api/admin/users/{user_id}/block
Content-Type: application/json
Authorization: Bearer {admin_token}

{
  "reason": "Suspicious trading activity detected"
}
```

**Response:**
```json
{
  "success": true,
  "user_id": "user123",
  "is_active": false,
  "message": "User blocked. 5 bots paused."
}
```

**Effects:**
- User cannot log in
- All active bots are paused
- Audit log entry created
- User sees "Account blocked" message

### Unblock User

```bash
POST /api/admin/users/{user_id}/unblock
Authorization: Bearer {admin_token}
```

**Response:**
```json
{
  "success": true,
  "user_id": "user123",
  "is_active": true,
  "message": "User unblocked"
}
```

### Reset User Password

```bash
POST /api/admin/users/{user_id}/reset-password
Authorization: Bearer {admin_token}
```

**Response:**
```json
{
  "success": true,
  "new_password": "Kj8#mP2qL9xZ",
  "message": "Password reset successfully. Email sent (if configured).",
  "user_id": "user123"
}
```

**Password Generation:**
- 12 characters (random secure)
- Mixed case + numbers + symbols
- At least 1 uppercase, 1 lowercase, 1 digit, 1 symbol
- User flagged `must_change_password: true`

**Security:**
- Password hashed with bcrypt before storage
- Admin sees plaintext password (share securely with user)
- Audit log created (password NOT logged)

### Delete User

```bash
DELETE /api/admin/users/{user_id}
Content-Type: application/json
Authorization: Bearer {admin_token}

{
  "confirm": true
}
```

**Response:**
```json
{
  "success": true,
  "deleted": {
    "user": 1,
    "bots": 5,
    "trades": 1250,
    "api_keys": 3
  },
  "message": "User user123 and all associated data deleted"
}
```

**Safety:**
- Admin cannot delete themselves
- Requires `confirm: true` flag
- Cascading delete: user → bots → trades → API keys → alerts
- Audit trail preserved

### Force Logout User

```bash
POST /api/admin/users/{user_id}/logout
Authorization: Bearer {admin_token}
```

**Response:**
```json
{
  "success": true,
  "message": "User forcefully logged out",
  "user_id": "user123",
  "sessions_deleted": 3
}
```

**Effects:**
- All user sessions invalidated
- User must re-login
- `force_logout: true` flag set (checked during auth)

---

## Bot Override

### Get All Bots (Admin View)

```bash
GET /api/admin/bots?mode=paper&user_id=user123
Authorization: Bearer {admin_token}
```

**Query Parameters:**
- `mode` (optional): Filter by "paper" or "live"
- `user_id` (optional): Filter by specific user

**Response:**
```json
{
  "bots": [
    {
      "bot_id": "bot123",
      "name": "BTC Scalper",
      "user_id": "user123",
      "username": "John",
      "email": "john@example.com",
      "exchange": "luno",
      "mode": "paper",
      "status": "active",
      "pause_reason": null,
      "paused_at": null,
      "current_capital": 1050.0,
      "profit_loss": 50.0
    }
  ],
  "total": 1
}
```

### Change Bot Mode

```bash
POST /api/admin/bots/{bot_id}/mode
Content-Type: application/json
Authorization: Bearer {admin_token}

{
  "mode": "live"
}
```

**Allowed Values:** `"paper"` or `"live"`

**Response:**
```json
{
  "success": true,
  "bot_id": "bot123",
  "mode": "live",
  "message": "Bot mode changed to live"
}
```

**Effects:**
- Bot switches between paper trading and live trading
- Audit log entry created
- Realtime event emitted to user
- All future trades use new mode

### Pause Bot

```bash
POST /api/admin/bots/{bot_id}/pause
Content-Type: application/json
Authorization: Bearer {admin_token}

{
  "reason": "Admin intervention - manual review required"
}
```

**Response:**
```json
{
  "success": true,
  "bot_id": "bot123",
  "status": "paused",
  "message": "Bot paused by admin"
}
```

### Resume Bot

```bash
POST /api/admin/bots/{bot_id}/resume
Authorization: Bearer {admin_token}
```

**Response:**
```json
{
  "success": true,
  "bot_id": "bot123",
  "status": "active",
  "message": "Bot resumed"
}
```

### Restart Bot

```bash
POST /api/admin/bots/{bot_id}/restart
Authorization: Bearer {admin_token}
```

**Response:**
```json
{
  "success": true,
  "bot_id": "bot123",
  "message": "Bot restarted - clearing state and redeploying"
}
```

**Effects:**
- Bot state cleared
- Positions closed (if any)
- Bot reinitialized with fresh config
- Audit log entry created

### Change Bot Exchange

```bash
POST /api/admin/bots/{bot_id}/exchange
Content-Type: application/json
Authorization: Bearer {admin_token}

{
  "exchange": "binance"
}
```


**Response:**
```json
{
  "success": true,
  "bot_id": "bot123",
  "exchange": "binance",
  "message": "Bot exchange changed to binance"
}
```

**Effects:**
- Bot switches to new exchange
- Trading pairs updated to match exchange
- Bot paused briefly during transition
- User notified of change

### Override Bot to Live (Bypass Training)

```bash
POST /api/admin/bots/{bot_id}/override-live
Authorization: Bearer {admin_token}
```

**Response:**
```json
{
  "success": true,
  "message": "Bot 'BTC Scalper' promoted to live trading (admin override)",
  "bot_id": "bot123",
  "overridden_by": "admin_uuid",
  "timestamp": "2024-01-15T10:30:00Z"
}
```

**Use Case:**
- Testing live mode without waiting for 7-day paper trading
- Promoting high-performing bots early
- Emergency override for special scenarios

**Security:**
- Requires admin role
- Audit log entry with severity "warning"
- Bot flagged `admin_override: true`

---

## System Monitoring

### Get System Stats

```bash
GET /api/admin/system-stats
Authorization: Bearer {admin_token}
```

**Response:**
```json
{
  "users": {
    "total": 100,
    "active": 95,
    "blocked": 5
  },
  "bots": {
    "total": 450,
    "active": 400,
    "live": 50,
    "paper": 400
  },
  "trades": {
    "total": 125000,
    "live": 5000,
    "paper": 120000
  },
  "profit": {
    "total": 125000.50
  },
  "vps_resources": {
    "cpu": {
      "usage_percent": 45.2,
      "count": 4,
      "load_average": {
        "1min": 1.25,
        "5min": 1.50,
        "15min": 1.30
      }
    },
    "memory": {
      "total_gb": 8.0,
      "used_gb": 5.2,
      "free_gb": 2.8,
      "usage_percent": 65.0
    },
    "disk": {
      "total_gb": 100.0,
      "used_gb": 45.5,
      "free_gb": 54.5,
      "usage_percent": 45.5
    }
  },
  "timestamp": "2024-01-15T10:30:00Z"
}
```

### Get System Resources

```bash
GET /api/admin/system/resources
Authorization: Bearer {admin_token}
```

**Response:**
```json
{
  "disk": {
    "total": 107374182400,
    "used": 48847474688,
    "free": 58526707712,
    "percent": 45.5
  },
  "inodes": {
    "total": "26214400",
    "used": "256000",
    "free": "25958400",
    "percent": "1%"
  },
  "memory": {
    "total": 8589934592,
    "available": 3221225472,
    "used": 5368709120,
    "percent": 62.5
  },
  "load": {
    "1min": 1.25,
    "5min": 1.50,
    "15min": 1.30
  },
  "timestamp": "2024-01-15T10:30:00Z"
}
```

### Get Process Health

```bash
GET /api/admin/system/processes
Authorization: Bearer {admin_token}
```

**Response:**
```json
{
  "status": "healthy",
  "processes": {
    "python": [
      {
        "pid": 1234,
        "status": "running",
        "cpu_percent": 15.2,
        "memory_percent": 8.5
      }
    ],
    "nginx": [
      {
        "pid": 5678,
        "status": "running",
        "cpu_percent": 2.1,
        "memory_percent": 1.2
      }
    ],
    "mongod": [
      {
        "pid": 9012,
        "status": "running",
        "cpu_percent": 5.8,
        "memory_percent": 12.3
      }
    ]
  },
  "timestamp": "2024-01-15T10:30:00Z"
}
```

### Get System Logs

```bash
GET /api/admin/system/logs?lines=200&log_file=backend
Authorization: Bearer {admin_token}
```

**Query Parameters:**
- `lines` (default: 200): Number of lines to return
- `log_file` (default: "backend"): "backend", "nginx", "error"

**Response:**
```json
{
  "log_file": "backend",
  "path": "/var/log/amarktai/backend.log",
  "lines": [
    "[2024-01-15 10:30:00] INFO: Bot bot123 created",
    "[2024-01-15 10:30:15] WARNING: Rate limit approaching",
    "[2024-01-15 10:30:30] ERROR: Trade execution failed"
  ],
  "total_lines": 200,
  "timestamp": "2024-01-15T10:30:00Z"
}
```

**Security:**
- Logs are **sanitized** to remove secrets
- API keys replaced with `***REDACTED***`
- Passwords replaced with `***REDACTED***`
- Bearer tokens replaced with `Bearer ***REDACTED***`

### Get Audit Events

```bash
GET /api/admin/audit/events?limit=100&user_id=user123&event_type=bot_created
Authorization: Bearer {admin_token}
```

**Query Parameters:**
- `limit` (default: 100): Max events to return
- `user_id` (optional): Filter by user
- `event_type` (optional): Filter by event type

**Response:**
```json
{
  "events": [
    {
      "admin_id": "admin123",
      "admin_username": "admin@amarktai.com",
      "action": "block_user",
      "target_type": "user",
      "target_id": "user123",
      "details": {
        "reason": "Suspicious activity",
        "bots_paused": 5
      },
      "timestamp": "2024-01-15T10:30:00Z",
      "ip_address": "192.168.1.100"
    }
  ],
  "total": 1,
  "filters": {
    "user_id": "user123",
    "event_type": null,
    "limit": 100
  }
}
```

### Get User Storage Usage

```bash
GET /api/admin/user-storage
Authorization: Bearer {admin_token}
```

**Response:**
```json
{
  "users": [
    {
      "user_id": "user123",
      "email": "john@example.com",
      "name": "John",
      "storage_bytes": 52428800,
      "storage_mb": 50.0,
      "storage_gb": 0.049
    }
  ],
  "total_storage_bytes": 52428800,
  "total_storage_mb": 50.0,
  "total_storage_gb": 0.049,
  "user_count": 1,
  "timestamp": "2024-01-15T10:30:00Z"
}
```

---

## API Endpoints Reference

### Authentication Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/admin/unlock` | Unlock admin panel with password |
| POST | `/api/admin/change-password` | Change admin password |

### User Management Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/admin/users` | Get all users with details |
| GET | `/api/admin/users/{user_id}` | Get specific user details |
| POST | `/api/admin/users/{user_id}/block` | Block user |
| POST | `/api/admin/users/{user_id}/unblock` | Unblock user |
| POST | `/api/admin/users/{user_id}/reset-password` | Reset user password |
| DELETE | `/api/admin/users/{user_id}` | Delete user (requires confirm) |
| POST | `/api/admin/users/{user_id}/logout` | Force logout user |
| GET | `/api/admin/users/{user_id}/api-keys` | Get API key status |

### Bot Management Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/admin/bots` | Get all bots (admin view) |
| GET | `/api/admin/bots/eligible-for-live` | Get bots eligible for live |
| POST | `/api/admin/bots/{bot_id}/mode` | Change bot trading mode |
| POST | `/api/admin/bots/{bot_id}/pause` | Pause bot |
| POST | `/api/admin/bots/{bot_id}/resume` | Resume bot |
| POST | `/api/admin/bots/{bot_id}/restart` | Restart bot |
| POST | `/api/admin/bots/{bot_id}/exchange` | Change bot exchange |
| POST | `/api/admin/bots/{bot_id}/override-live` | Override bot to live mode |

### System Monitoring Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/admin/stats` | Get system statistics |
| GET | `/api/admin/system-stats` | Get extended system stats |
| GET | `/api/admin/system/resources` | Get VPS resource usage |
| GET | `/api/admin/system/processes` | Get process health |
| GET | `/api/admin/system/logs` | Get system logs (sanitized) |
| GET | `/api/admin/audit/events` | Get audit trail |
| GET | `/api/admin/user-storage` | Get per-user storage usage |

---

## Security Considerations

### Admin Password Security

1. **Environment Variable**: Store in `.env` file, never in code
2. **Case-Insensitive**: Reduces brute-force complexity
3. **Whitespace Tolerant**: Prevents accidental lockouts
4. **Token Expiry**: 1 hour validity
5. **Audit Logging**: All failed attempts logged

### RBAC Enforcement

```python
# Every admin endpoint checks role
async def require_admin(current_user: str = Depends(get_current_user)) -> str:
    user = await db.users_collection.find_one({"id": current_user})
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    is_admin = user.get('is_admin', False) or user.get('role') == 'admin'
    
    if not is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    
    return current_user
```

### Audit Logging

All admin actions logged with:
- Admin ID and username
- Action performed
- Target (user/bot)
- Details (reason, changes)
- Timestamp (UTC)
- IP address

```python
audit_doc = {
    "admin_id": "admin123",
    "admin_username": "admin@amarktai.com",
    "action": "block_user",
    "target_type": "user",
    "target_id": "user123",
    "details": {"reason": "Suspicious activity", "bots_paused": 5},
    "timestamp": "2024-01-15T10:30:00Z",
    "ip_address": "192.168.1.100"
}
```

### Rate Limiting

Consider implementing rate limiting for admin endpoints:

```python
from slowapi import Limiter

limiter = Limiter(key_func=get_remote_address)

@router.post("/users/{user_id}/block")
@limiter.limit("10/minute")  # Max 10 blocks per minute
async def block_user(...):
    ...
```

---

## Usage Examples

### cURL Examples

#### Block User
```bash
curl -X POST http://localhost:8000/api/admin/users/user123/block \
  -H "Authorization: Bearer YOUR_ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"reason": "Suspicious trading activity"}'
```

#### Change Bot Mode
```bash
curl -X POST http://localhost:8000/api/admin/bots/bot123/mode \
  -H "Authorization: Bearer YOUR_ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"mode": "live"}'
```

#### Get System Stats
```bash
curl http://localhost:8000/api/admin/system-stats \
  -H "Authorization: Bearer YOUR_ADMIN_TOKEN"
```

### Python Examples

```python
import requests

class AdminClient:
    def __init__(self, base_url, admin_token):
        self.base_url = base_url
        self.headers = {
            "Authorization": f"Bearer {admin_token}",
            "Content-Type": "application/json"
        }
    
    def get_all_users(self):
        response = requests.get(
            f"{self.base_url}/api/admin/users",
            headers=self.headers
        )
        return response.json()
    
    def block_user(self, user_id, reason):
        response = requests.post(
            f"{self.base_url}/api/admin/users/{user_id}/block",
            headers=self.headers,
            json={"reason": reason}
        )
        return response.json()
    
    def change_bot_mode(self, bot_id, mode):
        response = requests.post(
            f"{self.base_url}/api/admin/bots/{bot_id}/mode",
            headers=self.headers,
            json={"mode": mode}
        )
        return response.json()

# Usage
admin = AdminClient("http://localhost:8000", "your_admin_token")
users = admin.get_all_users()
print(f"Total users: {users['total_count']}")
```

### JavaScript Examples

```javascript
class AdminAPI {
  constructor(baseURL, adminToken) {
    this.baseURL = baseURL;
    this.token = adminToken;
  }
  
  async getAllUsers() {
    const response = await fetch(`${this.baseURL}/api/admin/users`, {
      headers: {
        'Authorization': `Bearer ${this.token}`
      }
    });
    return response.json();
  }
  
  async blockUser(userId, reason) {
    const response = await fetch(
      `${this.baseURL}/api/admin/users/${userId}/block`,
      {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${this.token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ reason })
      }
    );
    return response.json();
  }
  
  async changeBotMode(botId, mode) {
    const response = await fetch(
      `${this.baseURL}/api/admin/bots/${botId}/mode`,
      {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${this.token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ mode })
      }
    );
    return response.json();
  }
}

// Usage
const admin = new AdminAPI('http://localhost:8000', 'your_admin_token');
const users = await admin.getAllUsers();
console.log(`Total users: ${users.total_count}`);
```

---

## Common Admin Tasks

### Task 1: Find and Block Suspicious User

```bash
# 1. Get all users
curl http://localhost:8000/api/admin/users \
  -H "Authorization: Bearer $ADMIN_TOKEN" | jq

# 2. Check specific user details
curl http://localhost:8000/api/admin/users/user123 \
  -H "Authorization: Bearer $ADMIN_TOKEN"

# 3. Block user if suspicious
curl -X POST http://localhost:8000/api/admin/users/user123/block \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"reason": "Abnormal trading patterns detected"}'
```

### Task 2: Promote High-Performing Bot to Live

```bash
# 1. Find eligible bots
curl http://localhost:8000/api/admin/bots/eligible-for-live \
  -H "Authorization: Bearer $ADMIN_TOKEN" | jq

# 2. Review bot performance
curl http://localhost:8000/api/bots/bot123 \
  -H "Authorization: Bearer $USER_TOKEN"

# 3. Override to live mode
curl -X POST http://localhost:8000/api/admin/bots/bot123/override-live \
  -H "Authorization: Bearer $ADMIN_TOKEN"
```

### Task 3: Investigate System Performance Issue

```bash
# 1. Check VPS resources
curl http://localhost:8000/api/admin/system/resources \
  -H "Authorization: Bearer $ADMIN_TOKEN"

# 2. Check process health
curl http://localhost:8000/api/admin/system/processes \
  -H "Authorization: Bearer $ADMIN_TOKEN"

# 3. Review recent logs
curl "http://localhost:8000/api/admin/system/logs?lines=500" \
  -H "Authorization: Bearer $ADMIN_TOKEN"

# 4. Check audit trail for anomalies
curl "http://localhost:8000/api/admin/audit/events?limit=100" \
  -H "Authorization: Bearer $ADMIN_TOKEN"
```

### Task 4: Reset User After Lockout

```bash
# 1. Reset password
curl -X POST http://localhost:8000/api/admin/users/user123/reset-password \
  -H "Authorization: Bearer $ADMIN_TOKEN"

# 2. Force logout (clear sessions)
curl -X POST http://localhost:8000/api/admin/users/user123/logout \
  -H "Authorization: Bearer $ADMIN_TOKEN"

# 3. Unblock if blocked
curl -X POST http://localhost:8000/api/admin/users/user123/unblock \
  -H "Authorization: Bearer $ADMIN_TOKEN"
```

---

## Troubleshooting

### Issue: "Admin access required"

**Cause**: User doesn't have admin role

**Solution:**
```python
# Grant admin role via MongoDB
await db.users_collection.update_one(
    {"email": "admin@example.com"},
    {"$set": {"role": "admin", "is_admin": True}}
)
```

### Issue: "Invalid admin password"

**Cause**: Password mismatch or env variable not set

**Solution:**
```bash
# Check environment variable
echo $ADMIN_PASSWORD

# Update .env file
ADMIN_PASSWORD=Ashmor12@

# Restart backend
systemctl restart amarktai-api
```

### Issue: Audit logs not appearing

**Cause**: Audit logger not initialized or collection missing

**Solution:**
```python
# Check audit logger
from engines.audit_logger import audit_logger

# Test logging
await audit_logger.log_event(
    event_type="test_event",
    user_id="test_user",
    details={"test": "data"}
)

# Check MongoDB collection
db.audit_logs.find().limit(5)
```

### Issue: Can't delete user

**Cause**: Missing `confirm: true` flag

**Solution:**
```bash
# Include confirm flag in request
curl -X DELETE http://localhost:8000/api/admin/users/user123 \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"confirm": true}'
```

---

## Best Practices

1. **Always Log Admin Actions**: Review audit trail regularly
2. **Use Least Privilege**: Only grant admin to trusted users
3. **Secure Admin Password**: Use strong, unique password
4. **Monitor Resource Usage**: Set up alerts for high CPU/memory
5. **Regular Backups**: Backup before bulk user/bot operations
6. **Test in Staging**: Test admin operations in non-production first
7. **Document Changes**: Note reason for all major admin actions

---

## See Also

- [Paper Trading System](paper_trading.md)
- [Bot Quarantine System](bot_quarantine.md)
- [Deployment Guide](../DEPLOYMENT_GUIDE.md)
- [Security Best Practices](../DEPLOYMENT_GUIDE.md#security)
