# AI Chat Session Enhancement - Manual Testing Guide

## Prerequisites
- System running with backend and frontend
- MongoDB accessible
- OpenAI API key configured
- User account created

## Test Scenarios

### Test 1: First Login of the Day (Fresh Session)

**Steps:**
1. Clear browser localStorage:
   ```javascript
   localStorage.removeItem('lastChatSession');
   ```
2. Login to dashboard
3. Navigate to AI Chat panel
4. Wait for component to mount

**Expected Results:**
- ✅ Daily greeting appears automatically
- ✅ Message has green gradient background
- ✅ "Daily Report" badge visible with checkmark
- ✅ Contains yesterday's performance (if data exists)
- ✅ Shows current portfolio status
- ✅ Includes bot count and active status

**Backend Verification:**
```javascript
// Check MongoDB
db.chat_sessions_collection.findOne({user_id: "YOUR_USER_ID"})
// Should show last_greeting_at timestamp

db.chat_messages_collection.find({user_id: "YOUR_USER_ID", is_greeting: true})
// Should show greeting message
```

---

### Test 2: Recent Session (< 1 Hour)

**Steps:**
1. Complete Test 1 first
2. Send a few chat messages
3. Logout
4. Login again within 1 hour

**Expected Results:**
- ✅ No greeting shown
- ✅ Last 10 messages appear
- ✅ Previous conversation visible
- ✅ Can continue chatting seamlessly

**localStorage Check:**
```javascript
console.log(localStorage.getItem('lastChatSession'));
// Should show recent timestamp (< 1 hour ago)
```

---

### Test 3: Manual Clear UI

**Steps:**
1. Have some messages in chat
2. Click "Clear" button in header
3. Observe UI

**Expected Results:**
- ✅ All messages disappear from UI
- ✅ Input still works
- ✅ Can send new messages
- ✅ Refresh page → greeting appears again

**Backend Verification:**
```javascript
// Messages still in database
db.chat_messages_collection.count({user_id: "YOUR_USER_ID"})
// Should NOT be 0 (history preserved)
```

---

### Test 4: Already Greeted Today

**Steps:**
1. Get morning greeting (Test 1)
2. Clear localStorage
3. Refresh page or logout/login

**Expected Results:**
- ✅ Recent messages appear (not duplicate greeting)
- ✅ Last 10 messages shown
- ✅ Can continue conversation

**API Response Check:**
```bash
curl -X POST http://localhost:8000/api/ai/chat/greeting \
  -H "Authorization: Bearer YOUR_TOKEN"

# Response should include:
# "already_greeted": true,
# "messages": [...]
```

---

### Test 5: Context Preservation

**Steps:**
1. Ask AI: "How many bots do I have?"
2. Wait for response
3. Ask follow-up: "How many are active?"
4. Observe response

**Expected Results:**
- ✅ Second question understood in context of first
- ✅ AI doesn't ask "which bots?" again
- ✅ Response references previous question
- ✅ Conversation flows naturally

**Backend Log Check:**
```bash
# Check backend logs
tail -f backend.log | grep "AI Processing"

# Should show:
# - History loading (30 messages)
# - Context being passed to OpenAI
```

---

### Test 6: Session Timeout (1 Hour)

**Steps:**
1. Send a message
2. Note the timestamp in localStorage
3. Wait 1 hour (or manually set timestamp to 2 hours ago):
   ```javascript
   localStorage.setItem('lastChatSession', Date.now() - 7200000); // 2 hours ago
   ```
4. Refresh page

**Expected Results:**
- ✅ Fresh greeting appears
- ✅ Not duplicate (if already greeted today)
- ✅ Or new greeting (if new day)

---

### Test 7: Multiple Messages Same Session

**Steps:**
1. Start fresh session (clear localStorage)
2. Get greeting
3. Send 5 different messages
4. Check session timestamp updates

**Expected Results:**
- ✅ Each message updates localStorage timestamp
- ✅ Session stays "alive" while active
- ✅ Context preserved across all messages

**Check:**
```javascript
// Before sending message
const before = localStorage.getItem('lastChatSession');

// Send message, then check again
const after = localStorage.getItem('lastChatSession');

console.log(parseInt(after) > parseInt(before)); // Should be true
```

---

### Test 8: No OpenAI Key

**Steps:**
1. Remove OpenAI API key from user settings
2. Clear env OPENAI_API_KEY
3. Request greeting

**Expected Results:**
- ✅ Fallback greeting appears
- ✅ Message says "AI service not configured"
- ✅ Still shows performance summary
- ✅ Prompts to add API key in settings

---

### Test 9: Yesterday's Performance Data

**Steps:**
1. Ensure trades exist from yesterday
2. Request fresh greeting (clear localStorage, new day)
3. Check greeting content

**Expected Results:**
- ✅ "Yesterday's Performance" section visible
- ✅ Shows trade count
- ✅ Shows win rate
- ✅ Shows net profit
- ✅ Formatted with R currency

**Manual Data Check:**
```javascript
// MongoDB query for yesterday
const yesterday = new Date();
yesterday.setDate(yesterday.getDate() - 1);
yesterday.setHours(0,0,0,0);

db.trades_collection.find({
  user_id: "YOUR_USER_ID",
  created_at: {$gte: yesterday.toISOString()}
});
```

---

### Test 10: Greeting Styling

**Steps:**
1. Get fresh greeting
2. Inspect message in browser dev tools
3. Check CSS classes

**Expected Results:**
- ✅ Background: `bg-gradient-to-r from-green-50 to-blue-50`
- ✅ Border: `border-green-200`
- ✅ Badge visible: "Daily Report"
- ✅ CheckCircle icon rendered
- ✅ Timestamp shown

---

## API Testing

### Test Greeting Endpoint
```bash
# Get daily greeting
curl -X POST http://localhost:8000/api/ai/chat/greeting \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json"

# Expected: Greeting message or already_greeted response
```

### Test Chat with Context
```bash
# Send first message
curl -X POST http://localhost:8000/api/ai/chat \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "content": "How many bots do I have?",
    "request_action": false
  }'

# Send follow-up
curl -X POST http://localhost:8000/api/ai/chat \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "content": "How are they performing?",
    "request_action": false
  }'

# Response should reference "bots" from context
```

### Test History Loading
```bash
# Get chat history
curl -X GET "http://localhost:8000/api/ai/chat/history?limit=10" \
  -H "Authorization: Bearer YOUR_TOKEN"

# Should return last 10 messages including greeting
```

---

## Database Verification

### Check Session Tracking
```javascript
// MongoDB shell
db.chat_sessions_collection.find({}).pretty()

// Should have documents like:
{
  "user_id": "some_user_id",
  "last_greeting_at": "2024-01-15T08:00:00.000Z",
  "last_session_start": "2024-01-15T08:00:00.000Z"
}
```

### Check Message Storage
```javascript
// Find greeting messages
db.chat_messages_collection.find({
  is_greeting: true
}).sort({timestamp: -1}).limit(5).pretty()

// Check total messages
db.chat_messages_collection.count({user_id: "YOUR_USER_ID"})

// Should increase with each message sent
```

---

## Performance Testing

### Test 1: Context Loading Performance
```bash
# Add 100 messages to history
# Then measure greeting response time

# Should complete in < 3 seconds even with full history
```

### Test 2: Concurrent Greetings
```bash
# Simulate multiple users requesting greetings
# Should not deadlock or conflict

for i in {1..10}; do
  curl -X POST http://localhost:8000/api/ai/chat/greeting \
    -H "Authorization: Bearer USER_${i}_TOKEN" &
done
wait
```

---

## Edge Cases

### Case 1: Timezone Handling
- Test with different timezone users
- Verify "yesterday" correctly calculated
- Check greeting timing (once per day)

### Case 2: Empty History
- New user, no messages
- Should still get greeting
- No errors in console/logs

### Case 3: Very Long History
- User with 1000+ messages
- Should only load last 30 for context
- No performance degradation

### Case 4: Malformed localStorage
```javascript
// Set invalid timestamp
localStorage.setItem('lastChatSession', 'invalid');

// Refresh page
// Should handle gracefully, show greeting
```

---

## Success Criteria

✅ **All 10 test scenarios pass**
✅ **No console errors**
✅ **No backend errors in logs**
✅ **Context preserved across sessions**
✅ **Greeting shows once per day**
✅ **UI clears without losing backend history**
✅ **Session timeout works correctly**
✅ **Performance acceptable (< 3s response)**
✅ **Styling correct (green gradient)**
✅ **Yesterday's data accurate**

---

## Troubleshooting

### Problem: Greeting not appearing
**Check:**
- localStorage cleared?
- Over 1 hour since last session?
- OpenAI API key configured?
- Backend logs for errors

### Problem: Duplicate greetings
**Check:**
- `chat_sessions_collection` timestamp
- Timezone configuration
- localStorage timestamp

### Problem: Context not preserved
**Check:**
- Messages saved in `chat_messages_collection`
- History loading in backend logs
- OpenAI API receiving history

### Problem: Session timeout not working
**Check:**
- localStorage timestamp format
- 1-hour calculation (3600000ms)
- Browser localStorage enabled

---

## Cleanup After Testing

```javascript
// Clear localStorage
localStorage.clear();

// MongoDB cleanup (optional)
db.chat_sessions_collection.deleteMany({});
db.chat_messages_collection.deleteMany({});
```

---

**Testing Complete!** ✅

If all scenarios pass, the AI Chat Session Enhancement is working correctly.
