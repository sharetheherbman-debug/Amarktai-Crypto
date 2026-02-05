# Phases 10-12 Implementation Guide

This document provides detailed implementation guidance for the final three phases.

---

## PHASE 10 - AI TOOLS BUTTONS FUNCTIONALITY

### Requirements
Wire up all AI tool buttons with real-time status updates and proper error handling.

### Backend Endpoints Needed

```python
# POST /api/ai/bodyguard/run
# GET  /api/ai/bodyguard/status

# POST /api/ai/learn/run
# GET  /api/ai/learn/status

# POST /api/bots/evolve
# GET  /api/bots/evolve/status

# GET  /api/ai/insights

# GET  /api/ml/predict?symbol={symbol}&platform={platform}

# POST /api/profits/reinvest

# GET  /api/system/health (already exists)

# POST /api/admin/email/broadcast (admin only)
```

### Frontend Implementation

Update Dashboard.js to:
1. Subscribe to `ai_tasks` real-time event
2. Show loading state while task is running
3. Display results when complete
4. Handle "not configured" errors gracefully

Example:
```javascript
const handleAIBodyguard = async () => {
  setAiTaskLoading('bodyguard');
  try {
    const result = await post('/ai/bodyguard/run', {});
    toast.success(`Bodyguard check complete: ${result.checks_passed}/${result.total_checks} passed`);
  } catch (error) {
    if (error.message.includes('not configured')) {
      toast.error('AI Bodyguard not configured. Please configure OpenAI API key.');
    } else {
      toast.error(`Bodyguard check failed: ${error.message}`);
    }
  } finally {
    setAiTaskLoading(null);
  }
};

// Subscribe to real-time status updates
useRealtimeEvent('ai_tasks', (task) => {
  if (task.task_type === 'bodyguard_check' && task.status === 'completed') {
    toast.success('Bodyguard check complete');
    setAiTaskLoading(null);
  }
}, []);
```

### AI Tools to Implement

1. **AI Bodyguard** - System health check
2. **Email Users** - Admin broadcast (admin only)
3. **Learning System** - Trigger AI learning
4. **Evolve Bots** - Genetic algorithm bot evolution
5. **Insights** - Daily AI insights
6. **Predict** - ML price prediction
7. **Reinvest Profits** - Automatic profit reinvestment
8. **System Health** - Overall system status

---

## PHASE 11 - ADMIN PASSWORD GATING

### Requirements
Implement secure admin panel toggling with backend password verification.

### Backend Endpoint Needed

```python
# routes/admin_endpoints.py

@router.post("/admin/unlock")
async def unlock_admin_panel(
    password: str = Body(..., embed=True),
    current_user: User = Depends(get_current_user)
):
    """
    Verify admin password and return unlock token
    Password should be stored in environment variable ADMIN_PASSWORD
    """
    import os
    from datetime import datetime, timedelta
    import jwt
    
    admin_password = os.getenv('ADMIN_PASSWORD', 'default_change_me')
    
    if password != admin_password:
        raise HTTPException(status_code=403, detail="Invalid admin password")
    
    # Generate short-lived admin unlock token (1 hour)
    unlock_token = jwt.encode(
        {
            "user_id": current_user.id,
            "admin_unlocked": True,
            "exp": datetime.utcnow() + timedelta(hours=1)
        },
        os.getenv('JWT_SECRET'),
        algorithm="HS256"
    )
    
    return {
        "status": "success",
        "message": "Admin panel unlocked",
        "unlock_token": unlock_token,
        "expires_in": 3600
    }
```

### Frontend Implementation

Update Dashboard.js ChatSection:

```javascript
const handleShowAdmin = async () => {
  // Prompt for password
  const password = prompt('Enter admin password:');
  if (!password) return;
  
  try {
    const result = await post('/admin/unlock', { password });
    
    // Store unlock state in memory only (not localStorage)
    setShowAdmin(true);
    sessionStorage.setItem('adminPanelVisible', 'true');
    sessionStorage.setItem('adminUnlockToken', result.unlock_token);
    
    toast.success('Admin panel unlocked');
    
    // Auto-hide after 1 hour
    setTimeout(() => {
      setShowAdmin(false);
      sessionStorage.removeItem('adminPanelVisible');
      sessionStorage.removeItem('adminUnlockToken');
      toast.info('Admin session expired');
    }, 3600000);
  } catch (error) {
    toast.error('Invalid admin password');
  }
};

const handleHideAdmin = async () => {
  // Prompt for password again
  const password = prompt('Enter admin password to hide:');
  if (!password) return;
  
  try {
    await post('/admin/unlock', { password });
    setShowAdmin(false);
    sessionStorage.removeItem('adminPanelVisible');
    sessionStorage.removeItem('adminUnlockToken');
    toast.success('Admin panel hidden');
  } catch (error) {
    toast.error('Invalid admin password');
  }
};

// Handle chat commands
const handleChatMessage = async (message) => {
  const lowerMessage = message.toLowerCase().trim();
  
  if (lowerMessage === 'show admin') {
    await handleShowAdmin();
    return;
  }
  
  if (lowerMessage === 'hide admin') {
    await handleHideAdmin();
    return;
  }
  
  // ... rest of chat handling
};
```

### Security Considerations

1. Password stored in environment variable `ADMIN_PASSWORD`
2. Unlock state in sessionStorage (cleared on refresh)
3. Short-lived unlock token (1 hour)
4. Backend verification required for unlock
5. Admin-only endpoints check unlock token

---

## PHASE 12 - CHAT MEMORY >= 30 DAYS

### Requirements
Implement persistent chat history with 30+ day retention.

### Backend Database Schema

```python
# models/chat_message.py

from datetime import datetime
from pydantic import BaseModel

class ChatMessage(BaseModel):
    id: str
    user_id: str
    role: str  # 'user' | 'assistant' | 'system'
    content: str
    timestamp: datetime
    metadata: dict = {}
    
class ChatSummary(BaseModel):
    id: str
    user_id: str
    period_start: datetime
    period_end: datetime
    summary: str
    message_count: int
```

### Backend Endpoints Needed

```python
# routes/ai_chat.py

@router.get("/chat/history")
async def get_chat_history(
    days: int = 30,
    limit: int = 100,
    current_user: User = Depends(get_current_user)
):
    """
    Get chat history for the past N days
    """
    from datetime import datetime, timedelta
    
    cutoff_date = datetime.utcnow() - timedelta(days=days)
    
    messages = await db.chat_messages.find({
        "user_id": current_user.id,
        "timestamp": {"$gte": cutoff_date}
    }).sort("timestamp", -1).limit(limit).to_list()
    
    return {
        "status": "success",
        "messages": messages,
        "count": len(messages),
        "days": days
    }

@router.post("/chat/message")
async def save_chat_message(
    role: str,
    content: str,
    metadata: dict = {},
    current_user: User = Depends(get_current_user)
):
    """
    Save a chat message to history
    """
    message = {
        "id": str(uuid.uuid4()),
        "user_id": current_user.id,
        "role": role,
        "content": content,
        "timestamp": datetime.utcnow(),
        "metadata": metadata
    }
    
    await db.chat_messages.insert_one(message)
    
    return {
        "status": "success",
        "message": message
    }

@router.get("/chat/summary")
async def get_chat_summary(
    days: int = 30,
    current_user: User = Depends(get_current_user)
):
    """
    Get AI-generated summary of chat history
    """
    # Implement AI summarization of chat history
    pass

@router.delete("/chat/history")
async def clear_chat_history(
    current_user: User = Depends(get_current_user)
):
    """
    Clear all chat history for user
    """
    result = await db.chat_messages.delete_many({
        "user_id": current_user.id
    })
    
    return {
        "status": "success",
        "deleted_count": result.deleted_count
    }
```

### Frontend Implementation

Update AIChatPanel.js or Dashboard.js:

```javascript
// Load chat history on component mount
useEffect(() => {
  loadChatHistory();
}, []);

const loadChatHistory = async () => {
  try {
    const data = await get('/chat/history?days=30&limit=100');
    const messages = data.messages.reverse(); // Oldest first
    setChatMessages(messages);
  } catch (error) {
    console.error('Failed to load chat history:', error);
  }
};

// Save messages to backend
const sendChatMessage = async (content) => {
  // Save user message
  await post('/chat/message', {
    role: 'user',
    content: content,
    metadata: { timestamp: new Date().toISOString() }
  });
  
  // Add to local state
  setChatMessages(prev => [...prev, {
    role: 'user',
    content: content,
    timestamp: new Date()
  }]);
  
  // Send to AI and get response
  try {
    const response = await post('/chat', { content });
    
    // Save assistant message
    await post('/chat/message', {
      role: 'assistant',
      content: response.message,
      metadata: { timestamp: new Date().toISOString() }
    });
    
    // Add to local state
    setChatMessages(prev => [...prev, {
      role: 'assistant',
      content: response.message,
      timestamp: new Date()
    }]);
  } catch (error) {
    console.error('Chat error:', error);
    toast.error('Failed to send message');
  }
};
```

### Command Registry

Document all supported commands:

```javascript
const CHAT_COMMANDS = {
  // System commands
  'show admin': {
    description: 'Show admin panel',
    requiresConfirmation: true,
    requiresPassword: true
  },
  'hide admin': {
    description: 'Hide admin panel',
    requiresConfirmation: true,
    requiresPassword: true
  },
  
  // Trading commands
  'emergency stop': {
    description: 'Stop all bots immediately',
    requiresConfirmation: true,
    dangerous: true
  },
  'enable live trading': {
    description: 'Enable live trading mode',
    requiresConfirmation: true,
    dangerous: true
  },
  'enable autopilot': {
    description: 'Enable autonomous trading',
    requiresConfirmation: true,
    dangerous: true
  },
  
  // Bot commands
  'create bot': {
    description: 'Create a new trading bot',
    requiresConfirmation: false
  },
  'stop bot [name]': {
    description: 'Stop a specific bot',
    requiresConfirmation: true
  },
  
  // Financial commands
  'reinvest profits': {
    description: 'Reinvest accumulated profits',
    requiresConfirmation: true
  },
  
  // Info commands
  'help': {
    description: 'Show this command list',
    requiresConfirmation: false
  },
  'status': {
    description: 'Show system status',
    requiresConfirmation: false
  }
};
```

### Database Cleanup

Set up automatic cleanup of old messages:

```python
# Scheduled task (runs daily)
async def cleanup_old_chat_messages():
    """
    Delete chat messages older than 30 days
    """
    from datetime import datetime, timedelta
    
    cutoff_date = datetime.utcnow() - timedelta(days=30)
    
    result = await db.chat_messages.delete_many({
        "timestamp": {"$lt": cutoff_date}
    })
    
    print(f"Cleaned up {result.deleted_count} old chat messages")
```

---

## Integration with Dashboard.js

### Import Components

```javascript
import LiveTradesPanel from '../components/LiveTradesPanel';
import PlatformPanel from '../components/PlatformPanel';
import ComparisonGraphs from '../components/ComparisonGraphs';
import { useRealtimeConnection, useRealtimeEvent } from '../hooks/useRealtime';
```

### Add Real-Time Connection

```javascript
// Initialize real-time connection
const token = localStorage.getItem('token');
const realtimeConnection = useRealtimeConnection(token);

// Display connection status
const renderConnectionStatus = () => (
  <div className="connection-status">
    <Badge variant={realtimeConnection.connected ? 'default' : 'destructive'}>
      {realtimeConnection.mode === 'ws' ? '🟢 WebSocket' : '🟡 Polling'}
    </Badge>
    {realtimeConnection.rtt && (
      <span className="text-xs text-muted-foreground ml-2">
        RTT: {realtimeConnection.rtt}ms
      </span>
    )}
  </div>
);
```

### Add Live Trades Section

```javascript
const renderLiveTrades = () => (
  <div className="live-trades-section" style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem', height: '600px' }}>
    <LiveTradesPanel platformFilter={platformFilter} />
    <PlatformPanel platformFilter={platformFilter} bots={bots} balances={balances} />
  </div>
);
```

### Add Graphs Section

```javascript
const renderGraphs = () => (
  <div className="graphs-section">
    <ComparisonGraphs platformFilter={platformFilter} />
  </div>
);
```

---

## Testing Checklist

### Phase 10 - AI Tools
- [ ] Each AI tool shows loading state
- [ ] Results display correctly
- [ ] "Not configured" errors handled gracefully
- [ ] Real-time status updates work
- [ ] Admin-only tools require admin access

### Phase 11 - Admin Gating
- [ ] "show admin" prompts for password
- [ ] Correct password unlocks panel
- [ ] Incorrect password shows error
- [ ] "hide admin" requires password
- [ ] Panel hidden on refresh (session only)
- [ ] Admin unlock expires after 1 hour

### Phase 12 - Chat Memory
- [ ] Chat history loads on mount
- [ ] Messages saved to backend
- [ ] History persists across sessions
- [ ] Old messages (>30 days) cleaned up
- [ ] Chat summary works
- [ ] Command registry displayed on "help"

---

## Environment Variables Required

```bash
# Admin password (Phase 11)
ADMIN_PASSWORD=your_secure_password_here

# JWT secret (for unlock tokens)
JWT_SECRET=your_jwt_secret_here

# OpenAI API key (for AI tools, Phase 10)
OPENAI_API_KEY=sk-your-key-here

# Database (for chat persistence, Phase 12)
MONGODB_URI=mongodb://localhost:27017
DB_NAME=amarktai_production
```

---

## Final Integration Steps

1. Implement backend endpoints for Phases 10-12
2. Update Dashboard.js with new components
3. Test real-time connections
4. Test all AI tools
5. Test admin gating
6. Test chat persistence
7. Run full build: `npm run build`
8. Deploy and verify in production

---

**End of Implementation Guide**
