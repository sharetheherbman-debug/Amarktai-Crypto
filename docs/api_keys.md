# API Keys Management Documentation

## Overview

The Amarktai Network securely manages API keys for multiple service providers including AI services (OpenAI) and cryptocurrency exchanges (Luno, Binance, KuCoin, Bybit, Kraken, Bitget, Gate.io).

## Supported Providers

| Provider | Type | Required Fields | Purpose |
|----------|------|----------------|---------|
| **openai** | AI Service | `api_key` | AI chat and intelligence features |
| **luno** | Exchange | `api_key`, `api_secret` | South African crypto trading (BTC/ZAR) |
| **binance** | Exchange | `api_key`, `api_secret` | Global crypto trading |
| **kucoin** | Exchange | `api_key`, `api_secret`, `passphrase` | Crypto trading with passphrase |
| **bybit** | Exchange | `api_key`, `api_secret` | Derivatives and spot trading |
| **kraken** | Exchange | `api_key`, `api_secret` | US-based regulated exchange |
| **bitget** | Exchange | `api_key`, `api_secret`, `passphrase` | Global crypto and derivatives |
| **gate** | Exchange | `api_key`, `api_secret` | Wide altcoin selection |

## Security Architecture

### Encryption at Rest

All API keys are encrypted using **Fernet** (symmetric encryption) before storage in the database.

**Encryption Key**: Derived from either:
1. `API_KEY_ENCRYPTION_KEY` environment variable (recommended)
2. `JWT_SECRET` environment variable (fallback)

**Algorithm**: Fernet (AES-128 CBC with HMAC SHA256 for authentication)

### Implementation

```python
from cryptography.fernet import Fernet
import base64
import hashlib
import os

# Key derivation
def get_encryption_key():
    secret = os.getenv('API_KEY_ENCRYPTION_KEY') or os.getenv('JWT_SECRET')
    key = hashlib.sha256(secret.encode()).digest()
    return base64.urlsafe_b64encode(key)

cipher = Fernet(get_encryption_key())

# Encryption
def encrypt_api_key(plaintext: str) -> str:
    return cipher.encrypt(plaintext.encode()).decode()

# Decryption
def decrypt_api_key(ciphertext: str) -> str:
    return cipher.decrypt(ciphertext.encode()).decode()
```

### Masking in Responses

When returning API keys to the client, only the first and last few characters are shown:

**Format**: `{prefix}...{suffix}`

**Examples**:
- `sk-proj-abc123...xyz789` (OpenAI key)
- `binance-key-abc...789` (Binance key)
- `luno-key-abc...xyz` (Luno key)

**Implementation**:
```python
def mask_api_key(key: str, prefix_len: int = 8, suffix_len: int = 4) -> str:
    if len(key) <= prefix_len + suffix_len:
        return key[:3] + "..." + key[-2:]
    return key[:prefix_len] + "..." + key[-suffix_len:]
```

## API Endpoints

### Base Path

All API key endpoints are under: `/api/keys`

### 1. List All Providers with Status

**Endpoint**: `GET /api/keys/list`

**Authentication**: Required (JWT token)

**Response**:
```json
{
  "success": true,
  "keys": [
    {
      "provider": "openai",
      "display_name": "OpenAI",
      "type": "ai",
      "status": "test_ok",
      "status_display": "Test OK ✅",
      "icon": "🤖",
      "required_fields": ["api_key"],
      "created_at": "2024-01-20T10:30:00Z",
      "last_tested_at": "2024-01-20T15:45:00Z"
    },
    {
      "provider": "binance",
      "display_name": "Binance",
      "type": "exchange",
      "status": "not_configured",
      "status_display": "Not configured",
      "icon": "🟡",
      "required_fields": ["api_key", "api_secret"]
    }
  ]
}
```

**Status Values**:
- `not_configured` - No key saved
- `saved_untested` - Key saved but never tested
- `test_ok` - Last test passed
- `test_failed` - Last test failed

### 2. Get Specific Provider Keys

**Endpoint**: `GET /api/keys/{provider}`

**Authentication**: Required (JWT token)

**Response**:
```json
{
  "success": true,
  "provider": "binance",
  "api_key": "binance-key-abc...xyz",
  "api_secret": "secret-abc...xyz",
  "status": "test_ok",
  "last_tested_at": "2024-01-20T15:45:00Z"
}
```

**Note**: Keys are masked in responses. Never returns plaintext credentials.

### 3. Save/Update API Keys

**Endpoint**: `POST /api/keys/{provider}` or `POST /api/keys/save`

**Authentication**: Required (JWT token)

**Request Body**:
```json
{
  "provider": "binance",
  "api_key": "your-api-key",
  "api_secret": "your-api-secret",
  "passphrase": "optional-for-kucoin"
}
```

**Response**:
```json
{
  "success": true,
  "message": "Saved Binance API key",
  "provider": "binance",
  "status": "saved_untested",
  "status_display": "Saved (untested)"
}
```

**Validation**:
- Provider must be recognized (openai, luno, binance, kucoin, bybit, kraken, bitget, gate)
- Required fields for provider must be provided
- Keys are encrypted before storage
- Test status is reset when keys change

### 4. Test API Keys

**Endpoint**: `POST /api/keys/test`

**Authentication**: Required (JWT token)

**Request Body (Option 1 - Test saved keys)**:
```json
{
  "provider": "binance"
}
```

**Request Body (Option 2 - Test new keys before saving)**:
```json
{
  "provider": "binance",
  "api_key": "test-key",
  "api_secret": "test-secret"
}
```

**Success Response**:
```json
{
  "success": true,
  "message": "Binance key is valid",
  "provider": "binance",
  "status": "test_ok",
  "status_display": "Test OK ✅"
}
```

**Failure Response**:
```json
{
  "success": false,
  "message": "Test failed: Invalid API key",
  "provider": "binance",
  "status": "test_failed",
  "status_display": "Test Failed ❌"
}
```

**What Gets Tested**:
- **OpenAI**: Makes a test API call to verify key validity
- **Exchanges**: Tests authentication by fetching account balance or API permissions
- **Real Connectivity**: All tests make actual API calls to provider endpoints

### 5. Delete API Keys

**Endpoint**: `DELETE /api/keys/{provider}`

**Authentication**: Required (JWT token)

**Response**:
```json
{
  "success": true,
  "message": "Deleted Binance API key"
}
```

**Idempotent**: Returns success even if key doesn't exist

## Database Schema

### Collection: `api_keys_collection`

```json
{
  "user_id": "user-uuid",
  "provider": "binance",
  "api_key_encrypted": "gAAAA...encrypted-data...==",
  "api_secret_encrypted": "gAAAA...encrypted-data...==",
  "passphrase_encrypted": "gAAAA...encrypted-data...==",
  "created_at": "2024-01-20T10:30:00Z",
  "updated_at": "2024-01-20T15:45:00Z",
  "last_tested_at": "2024-01-20T15:45:00Z",
  "last_test_ok": true,
  "last_test_error": null,
  "status": "test_ok"
}
```

**Indexes**:
```javascript
db.api_keys_collection.createIndex({ "user_id": 1, "provider": 1 }, { unique: true })
db.api_keys_collection.createIndex({ "user_id": 1 })
```

## Provider-Specific Requirements

### OpenAI

**Required**: `api_key` only

**Format**: `sk-proj-...` or `sk-...`

**Test Method**: Makes a lightweight API call to OpenAI

**Notes**: 
- Supports both project and legacy API keys
- Used for AI chat and intelligence features

### Binance

**Required**: `api_key`, `api_secret`

**Permissions Needed**: 
- Read account information
- Read market data
- Trade (for live trading only)

**Test Method**: Fetches account information

**Notes**:
- API key must have IP whitelist configured (recommended)
- For paper trading, read-only permissions sufficient

### KuCoin

**Required**: `api_key`, `api_secret`, `passphrase`

**Unique Feature**: Requires passphrase created when generating API key

**Test Method**: Fetches account information with passphrase

**Notes**:
- Passphrase is required even for read-only operations
- Store passphrase securely - it's needed for all API calls

### Luno

**Required**: `api_key`, `api_secret`

**Supported Pairs**: BTC/ZAR, ETH/ZAR, XRP/ZAR (South African market)

**Test Method**: Fetches account balance

**Notes**:
- South African exchange
- Lower fees for maker orders
- Good for ZAR-denominated trading

### Bybit

**Required**: `api_key`, `api_secret`

**Supported**: Spot and derivatives trading

**Test Method**: Authenticates and fetches account data

**Notes**:
- Global exchange
- Low latency trading
- Popular for derivatives

### Kraken

**Required**: `api_key`, `api_secret`

**Supported**: Wide range of crypto pairs

**Test Method**: Authenticates and fetches account data

**Notes**:
- US-based regulated exchange
- Strong security reputation
- Good liquidity

### Bitget

**Required**: `api_key`, `api_secret`, `passphrase`

**Unique Feature**: Requires passphrase like KuCoin

**Test Method**: Authenticates with passphrase

**Notes**:
- Global exchange
- Copy trading features
- Growing liquidity

### Gate.io

**Required**: `api_key`, `api_secret`

**Supported**: Wide altcoin selection

**Test Method**: Authenticates and fetches account data

**Notes**:
- Altcoin specialist
- Deep order books for many pairs
- Good API documentation

## Usage Examples

### cURL Examples

**1. Save Binance API Keys**
```bash
curl -X POST https://yourdomain.com/api/keys/save \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "provider": "binance",
    "api_key": "your-binance-api-key",
    "api_secret": "your-binance-api-secret"
  }'
```

**2. Test Saved Keys**
```bash
curl -X POST https://yourdomain.com/api/keys/test \
  -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "provider": "binance"
  }'
```

**3. List All Providers**
```bash
curl -X GET https://yourdomain.com/api/keys/list \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

**4. Delete Keys**
```bash
curl -X DELETE https://yourdomain.com/api/keys/binance \
  -H "Authorization: Bearer YOUR_JWT_TOKEN"
```

### Python Examples

```python
import requests

API_BASE = "https://yourdomain.com/api"
TOKEN = "your-jwt-token"
headers = {"Authorization": f"Bearer {TOKEN}"}

# Save keys
response = requests.post(
    f"{API_BASE}/keys/save",
    headers=headers,
    json={
        "provider": "binance",
        "api_key": "your-api-key",
        "api_secret": "your-api-secret"
    }
)
print(response.json())

# Test keys
response = requests.post(
    f"{API_BASE}/keys/test",
    headers=headers,
    json={"provider": "binance"}
)
print(response.json())

# List all
response = requests.get(f"{API_BASE}/keys/list", headers=headers)
print(response.json())
```

### JavaScript (Frontend) Examples

```javascript
// Save API keys
const saveKeys = async (provider, apiKey, apiSecret, passphrase = null) => {
  const response = await fetch('/api/keys/save', {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${localStorage.getItem('token')}`,
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({
      provider,
      api_key: apiKey,
      api_secret: apiSecret,
      passphrase
    })
  });
  return response.json();
};

// Test keys
const testKeys = async (provider) => {
  const response = await fetch('/api/keys/test', {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${localStorage.getItem('token')}`,
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({ provider })
  });
  return response.json();
};

// Delete keys
const deleteKeys = async (provider) => {
  const response = await fetch(`/api/keys/${provider}`, {
    method: 'DELETE',
    headers: {
      'Authorization': `Bearer ${localStorage.getItem('token')}`
    }
  });
  return response.json();
};
```

## Security Best Practices

### For Users

1. **Never share API keys** - Treat them like passwords
2. **Use read-only keys for paper trading** - Reduce risk
3. **Enable IP whitelisting** - Restrict API access to your server IP
4. **Rotate keys regularly** - Change keys every 3-6 months
5. **Delete unused keys** - Remove keys for exchanges you're not using
6. **Monitor API activity** - Check exchange dashboards for unexpected activity

### For Developers

1. **Never log plaintext keys** - Always use masked versions
2. **Use environment variables** - Don't hardcode encryption keys
3. **Encrypt in transit** - Always use HTTPS
4. **Validate input** - Check provider names and required fields
5. **Rate limit test endpoint** - Prevent abuse of key testing
6. **Audit key access** - Log when keys are accessed or modified
7. **Implement 2FA** - Consider requiring 2FA for key operations

## Troubleshooting

### Issue: "422 Unprocessable Entity" when saving keys

**Cause**: Missing required fields for provider

**Solution**: Ensure all required fields are provided:
- OpenAI: `api_key` only
- Exchanges: `api_key` + `api_secret`
- KuCoin: `api_key` + `api_secret` + `passphrase`

### Issue: Test fails but keys are correct

**Possible Causes**:
1. **IP Whitelisting**: Your server IP not whitelisted on exchange
2. **Permissions**: API key doesn't have required permissions
3. **Rate Limiting**: Too many test requests
4. **Expired Key**: API key expired or was revoked
5. **Network Issues**: Server can't reach exchange API

**Debug Steps**:
1. Check backend logs for detailed error messages
2. Verify key permissions on exchange dashboard
3. Test keys directly using exchange's API documentation
4. Check firewall/network connectivity

### Issue: Keys not persisting after save

**Possible Causes**:
1. Database connection issue
2. Encryption key mismatch
3. User authentication issue

**Solution**: Check backend logs and verify:
- Database is connected
- `API_KEY_ENCRYPTION_KEY` or `JWT_SECRET` is set
- User is properly authenticated

## Real-time Updates

When API keys are saved, tested, or deleted, real-time events are emitted via WebSocket:

```javascript
// Listen for key events
ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  
  if (data.type === 'key_saved') {
    console.log(`Key saved for ${data.provider}`);
  } else if (data.type === 'key_tested') {
    console.log(`Key test ${data.success ? 'passed' : 'failed'} for ${data.provider}`);
  } else if (data.type === 'key_deleted') {
    console.log(`Key deleted for ${data.provider}`);
  }
};
```

## Compliance & Data Protection

### GDPR Compliance

- API keys are personal data and must be handled securely
- Users have the right to request deletion (DELETE endpoint)
- Encryption at rest protects against data breaches
- Access logs should be maintained for audit purposes

### Encryption Standards

- **Algorithm**: Fernet (AES-128 CBC + HMAC SHA256)
- **Key Derivation**: SHA-256 hash of secret
- **At Rest**: All keys encrypted in database
- **In Transit**: HTTPS/TLS 1.2+ required

## References

- [OpenAI API Documentation](https://platform.openai.com/docs/api-reference)
- [Binance API Documentation](https://binance-docs.github.io/apidocs/)
- [KuCoin API Documentation](https://docs.kucoin.com/)
- [Luno API Documentation](https://www.luno.com/en/developers/api)
- [Cryptography Fernet Documentation](https://cryptography.io/en/latest/fernet/)
