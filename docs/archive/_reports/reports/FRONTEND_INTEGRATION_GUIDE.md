# Frontend Integration Guide

**Version:** 1.0  
**Last Updated:** December 27, 2025  
**For:** Amarktai Network Frontend Developers

---

## Overview

This guide explains how the frontend should integrate with the backend API to maintain single source of truth and avoid client-side approximations.

---

## API Base URL

```javascript
// frontend/src/lib/api.js
export const API_BASE = process.env.REACT_APP_API_URL || 'http://localhost:8000/api';
```

**Production:** `https://your-domain.com/api`  
**Development:** `http://localhost:8000/api`

---

## Authentication

All API calls except `/auth/login` and `/auth/register` require JWT token:

```javascript
const token = localStorage.getItem('token');
const axiosConfig = {
  headers: {
    'Authorization': `Bearer ${token}`,
    'Content-Type': 'application/json'
  }
};

// Example
const response = await axios.get(`${API}/portfolio/summary`, axiosConfig);
```

---

## Core Dashboard Endpoints

### 1. Portfolio Summary (Ledger Truth)

**Endpoint:** `GET /api/portfolio/summary`

**Purpose:** Get comprehensive portfolio metrics from ledger

**Response:**
```json
{
  "equity": 15234.67,
  "realized_pnl": 2345.50,
  "unrealized_pnl": 123.45,
  "fees_total": 123.45,
  "net_pnl": 2345.50,
  "drawdown_current": 5.2,
  "drawdown_max": 12.8,
  "win_rate": null,
  "total_fills": 150,
  "total_volume": 45000.00,
  "data_source": "ledger",
  "phase": "1_read_only"
}
```

**Frontend Usage:**
```javascript
const loadPortfolioSummary = async () => {
  try {
    const response = await axios.get(`${API}/portfolio/summary`, axiosConfig);
    const data = response.data;
    
    setMetrics({
      equity: `R${data.equity.toFixed(2)}`,
      totalProfit: `R${data.net_pnl.toFixed(2)}`,
      realizedPnL: `R${data.realized_pnl.toFixed(2)}`,
      unrealizedPnL: `R${data.unrealized_pnl.toFixed(2)}`,
      fees: `R${data.fees_total.toFixed(2)}`,
      drawdownCurrent: `${data.drawdown_current.toFixed(2)}%`,
      drawdownMax: `${data.drawdown_max.toFixed(2)}%`,
      totalTrades: data.total_fills,
      totalVolume: `R${data.total_volume.toFixed(2)}`
    });
  } catch (error) {
    console.error('Failed to load portfolio summary:', error);
    toast.error('Failed to load portfolio data');
  }
};
```

**Update Required:**
- ❌ Current: Uses `/api/metrics` (line 566 in Dashboard.js)
- ✅ Should: Use `/api/portfolio/summary`

---

### 2. Profit Series (Time Series Data)

**Endpoint:** `GET /api/profits?period={period}`

**Parameters:**
- `period`: "daily" | "weekly" | "monthly"
- `limit` (optional): Number of periods (default 30)

**Response:**
```json
{
  "period": "daily",
  "limit": 30,
  "series": [
    {
      "date": "2025-12-27",
      "gross_pnl": 150.50,
      "fees": 12.50,
      "net_profit": 138.00,
      "trade_count": 5
    },
    // ... more days
  ],
  "data_source": "ledger",
  "phase": "1_read_only"
}
```

**Frontend Usage:**
```javascript
const loadProfitData = async (period = 'daily') => {
  try {
    const response = await axios.get(`${API}/profits?period=${period}`, axiosConfig);
    const series = response.data.series;
    
    // Format for Chart.js
    const chartData = {
      labels: series.map(item => item.date),
      datasets: [
        {
          label: 'Net Profit',
          data: series.map(item => item.net_profit),
          borderColor: 'rgb(75, 192, 192)',
          backgroundColor: 'rgba(75, 192, 192, 0.2)',
        },
        {
          label: 'Gross P&L',
          data: series.map(item => item.gross_pnl),
          borderColor: 'rgb(255, 99, 132)',
          backgroundColor: 'rgba(255, 99, 132, 0.2)',
        }
      ]
    };
    
    setProfitData(chartData);
  } catch (error) {
    console.error('Failed to load profit data:', error);
  }
};
```

**Update Required:**
- ❌ Current: Uses `/api/analytics/profit-history?period=${graphPeriod}` (line 670)
- ✅ Should: Use `/api/profits?period=${period}`

---

### 3. Countdown to Million

**Endpoint:** `GET /api/countdown/status?target={target}`

**Parameters:**
- `target` (optional): Target amount (default 1000000)

**Response:**
```json
{
  "current_equity": 15234.67,
  "target": 1000000,
  "remaining": 984765.33,
  "progress_pct": 1.52,
  "days_to_target_linear": 245,
  "days_to_target_compound": 198,
  "avg_daily_profit_30d": 138.50,
  "data_source": "ledger",
  "projection_model": "compound_5pct"
}
```

**Frontend Usage:**
```javascript
const loadCountdown = async () => {
  try {
    const response = await axios.get(`${API}/countdown/status`, axiosConfig);
    const data = response.data;
    
    setProjection({
      current: data.current_equity,
      target: data.target,
      remaining: data.remaining,
      progress: data.progress_pct,
      daysLinear: data.days_to_target_linear,
      daysCompound: data.days_to_target_compound,
      avgDailyProfit: data.avg_daily_profit_30d
    });
  } catch (error) {
    console.error('Failed to load countdown:', error);
  }
};
```

**Current Status:**
- ⚠️ Currently using `/api/analytics/countdown-to-million` (line 611)
- ✅ Can also use `/api/countdown/status` (canonical)
- Both work, but canonical is preferred for consistency

---

## API Key Management Endpoints

### 1. Test API Key

**Endpoint:** `POST /api/keys/test`

**Request Body:**
```json
{
  "provider": "exchange",
  "exchange": "binance",
  "api_key": "your_api_key_here",
  "api_secret": "your_api_secret_here"
}
```

**Response (Success):**
```json
{
  "success": true,
  "message": "✅ Binance API key validated successfully",
  "provider": "exchange",
  "exchange": "binance",
  "verified": true,
  "balance_info": {
    "BTC": 0.5,
    "USDT": 1000.00
  }
}
```

**Response (Error):**
```json
{
  "success": false,
  "message": "❌ Invalid API key or insufficient permissions",
  "error": "authentication_failed"
}
```

**Frontend Usage:**
```javascript
const testApiKey = async (provider, exchange, apiKey, apiSecret) => {
  try {
    const response = await axios.post(`${API}/keys/test`, {
      provider,
      exchange,
      api_key: apiKey,
      api_secret: apiSecret
    }, axiosConfig);
    
    if (response.data.success) {
      toast.success(response.data.message);
      return true;
    } else {
      toast.error(response.data.message);
      return false;
    }
  } catch (error) {
    toast.error('API key test failed: ' + error.response?.data?.detail);
    return false;
  }
};
```

**Update Required:**
- ❌ Current: Uses `/api/api-keys/${provider}/test` (line 1119)
- ✅ Should: Use `/api/keys/test`

---

### 2. Save API Key

**Endpoint:** `POST /api/keys/save`

**Request Body:**
```json
{
  "provider": "exchange",
  "exchange": "binance",
  "api_key": "your_api_key_here",
  "api_secret": "your_api_secret_here",
  "label": "Binance Main",
  "verified": true
}
```

**Response:**
```json
{
  "success": true,
  "message": "✅ API key saved successfully (encrypted)",
  "label": "Binance Main",
  "verified": true
}
```

**Frontend Usage:**
```javascript
const saveApiKey = async (provider, exchange, apiKey, apiSecret, label) => {
  try {
    // First test the key
    const testResult = await testApiKey(provider, exchange, apiKey, apiSecret);
    
    // Then save with verification status
    const response = await axios.post(`${API}/keys/save`, {
      provider,
      exchange,
      api_key: apiKey,
      api_secret: apiSecret,
      label: label || `${exchange} API Key`,
      verified: testResult
    }, axiosConfig);
    
    if (response.data.success) {
      toast.success('API key saved and encrypted');
      return true;
    }
  } catch (error) {
    toast.error('Failed to save API key');
    return false;
  }
};
```

**Update Required:**
- ❌ Current: Uses `/api/api-keys` (line 1105)
- ✅ Should: Use `/api/keys/save`

---

### 3. List API Keys (Optional)

**Endpoint:** `GET /api/keys/list`

**Response:**
```json
{
  "keys": [
    {
      "id": "key-123",
      "provider": "exchange",
      "exchange": "binance",
      "label": "Binance Main",
      "verified": true,
      "masked_key": "abc***xyz",
      "created_at": "2025-12-27T10:00:00Z"
    }
  ]
}
```

---

## Bot Lifecycle Endpoints

### 1. Pause Bot

**Endpoint:** `POST /api/bots/{bot_id}/pause` or `PUT /api/bots/{bot_id}/pause`

**Request Body:**
```json
{
  "reason": "User requested pause"
}
```

**Response:**
```json
{
  "success": true,
  "message": "Bot paused successfully",
  "bot": {
    "id": "bot-123",
    "name": "Alpha Bot",
    "status": "paused",
    "paused_at": "2025-12-27T14:30:00Z",
    "pause_reason": "User requested pause"
  }
}
```

---

### 2. Resume Bot

**Endpoint:** `POST /api/bots/{bot_id}/resume` or `PUT /api/bots/{bot_id}/resume`

**Response:**
```json
{
  "success": true,
  "message": "Bot resumed successfully",
  "bot": {
    "id": "bot-123",
    "name": "Alpha Bot",
    "status": "active"
  }
}
```

---

### 3. Stop Bot

**Endpoint:** `POST /api/bots/{bot_id}/stop`

**Response:**
```json
{
  "success": true,
  "message": "Bot stopped permanently",
  "bot": {
    "id": "bot-123",
    "status": "stopped"
  }
}
```

---

## Health & System Endpoints

### Health Ping

**Endpoint:** `GET /api/health/ping`

**Response:**
```json
{
  "status": "ok",
  "timestamp": "2025-12-27T14:30:00.000Z"
}
```

---

## Error Handling

### Standard Error Response

All endpoints return errors in this format:

```json
{
  "detail": "Error message here",
  "status_code": 400
}
```

### Frontend Error Handler

```javascript
const handleApiError = (error) => {
  if (error.response) {
    // Server responded with error status
    const message = error.response.data?.detail || 'An error occurred';
    toast.error(message);
    
    if (error.response.status === 401) {
      // Token expired or invalid
      localStorage.removeItem('token');
      navigate('/login');
    }
  } else if (error.request) {
    // Request made but no response
    toast.error('Server is not responding');
  } else {
    // Something else happened
    toast.error('Request failed: ' + error.message);
  }
};

// Usage
try {
  const response = await axios.get(`${API}/portfolio/summary`, axiosConfig);
  // Handle success
} catch (error) {
  handleApiError(error);
}
```

---

## Real-Time Updates

### WebSocket Connection

```javascript
const connectWebSocket = () => {
  const ws = new WebSocket('ws://localhost:8000/api/ws');
  
  ws.onopen = () => {
    console.log('✅ WebSocket connected');
    ws.send(JSON.stringify({
      type: 'authenticate',
      token: localStorage.getItem('token')
    }));
  };
  
  ws.onmessage = (event) => {
    const data = JSON.parse(event.data);
    
    switch (data.type) {
      case 'portfolio_update':
        // Refresh portfolio summary
        loadPortfolioSummary();
        break;
      case 'bot_status_change':
        // Refresh bot list
        loadBots();
        break;
      case 'trade_executed':
        // Add trade to list, update metrics
        loadProfitData();
        break;
    }
  };
  
  ws.onerror = (error) => {
    console.error('WebSocket error:', error);
  };
  
  ws.onclose = () => {
    console.log('WebSocket disconnected, reconnecting in 5s...');
    setTimeout(connectWebSocket, 5000);
  };
  
  return ws;
};
```

---

## Migration Checklist

### From Legacy to Canonical Endpoints

- [ ] **Line 566:** Change `/api/metrics` → `/api/portfolio/summary`
- [ ] **Line 670:** Change `/api/analytics/profit-history` → `/api/profits`
- [ ] **Line 611:** Optional: Change `/api/analytics/countdown-to-million` → `/api/countdown/status`
- [ ] **Line 1105:** Change `/api/api-keys` → `/api/keys/save`
- [ ] **Line 1119:** Change `/api/api-keys/${provider}/test` → `/api/keys/test`

### Testing After Migration

1. **Portfolio Summary**
   - Load dashboard
   - Verify equity displays correctly
   - Check realized/unrealized P&L
   - Verify drawdown percentages

2. **Profit Graph**
   - Switch between daily/weekly/monthly
   - Verify data loads
   - Check chart renders correctly

3. **API Keys**
   - Test API key with valid credentials
   - Test API key with invalid credentials
   - Save API key
   - Verify encryption

4. **Bot Control**
   - Pause bot
   - Resume bot
   - Stop bot
   - Verify status updates

---

## Best Practices

### 1. Always Use Backend Truth

❌ **Don't:**
```javascript
// Client-side calculation
const totalProfit = bots.reduce((sum, bot) => sum + bot.profit, 0);
```

✅ **Do:**
```javascript
// Server-side calculation
const response = await axios.get(`${API}/portfolio/summary`);
const totalProfit = response.data.net_pnl;
```

### 2. Handle Loading States

```javascript
const [loading, setLoading] = useState(true);

const loadData = async () => {
  setLoading(true);
  try {
    const response = await axios.get(`${API}/portfolio/summary`, axiosConfig);
    setMetrics(response.data);
  } catch (error) {
    handleApiError(error);
  } finally {
    setLoading(false);
  }
};
```

### 3. Cache Appropriately

```javascript
// Don't cache real-time data
const loadPortfolio = async () => {
  // Always fetch fresh data
  const response = await axios.get(`${API}/portfolio/summary`, axiosConfig);
  return response.data;
};

// Cache static data
const loadApiKeys = async () => {
  if (cachedKeys && Date.now() - cacheTime < 300000) { // 5 min
    return cachedKeys;
  }
  const response = await axios.get(`${API}/keys/list`, axiosConfig);
  cachedKeys = response.data;
  cacheTime = Date.now();
  return cachedKeys;
};
```

---

## Testing

### Integration Test Example

```javascript
// Test frontend calls correct endpoint
test('Dashboard loads portfolio summary from correct endpoint', async () => {
  // Mock axios
  axios.get = jest.fn().mockResolvedValue({
    data: {
      equity: 15000,
      realized_pnl: 2000,
      net_pnl: 1800
    }
  });
  
  render(<Dashboard />);
  
  await waitFor(() => {
    expect(axios.get).toHaveBeenCalledWith(
      'http://localhost:8000/api/portfolio/summary',
      expect.objectContaining({
        headers: expect.objectContaining({
          'Authorization': expect.stringContaining('Bearer')
        })
      })
    );
  });
});
```

---

## Support

For issues or questions:
1. Check [BACKEND_FRONTEND_PARITY_REPORT.md](./BACKEND_FRONTEND_PARITY_REPORT.md)
2. Review [PRODUCTION_READINESS_ASSESSMENT.md](./PRODUCTION_READINESS_ASSESSMENT.md)
3. Contact backend team

---

**Last Updated:** December 27, 2025  
**Maintained By:** Amarktai Network Development Team
