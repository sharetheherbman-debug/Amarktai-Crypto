# AI Command Router - Complete Command Reference

**Version:** 2.0 - Production Grade  
**Last Updated:** December 2025

This document provides a comprehensive reference for all AI commands supported by the Amarktai Network AI Command Router.

---

## Table of Contents

- [Overview](#overview)
- [Command Syntax](#command-syntax)
- [Confirmation Levels](#confirmation-levels)
- [Bot Lifecycle Commands](#bot-lifecycle-commands)
- [Portfolio & Analytics Commands](#portfolio--analytics-commands)
- [System Health Commands](#system-health-commands)
- [Emergency Commands](#emergency-commands)
- [Admin Commands](#admin-commands)
- [Tool Registry](#tool-registry)
- [Synonym Support](#synonym-support)
- [Examples](#examples)

---

## Overview

The AI Command Router allows you to control your entire trading dashboard through natural language commands. It features:

- **Fuzzy Matching**: Type bot names approximately - "Alpha" matches "AlphaBot"
- **Synonym Support**: Use natural phrases - "stop", "freeze", "hold" all mean pause
- **Multi-Command**: Execute multiple commands - "pause alpha and beta"
- **Risk-Based Confirmation**: Different confirmation levels based on action risk
- **Structured Output**: Consistent JSON response format
- **Tool Registry**: AI can call system features directly

---

## Command Syntax

### Basic Structure

```
<action> <target> [parameters]
```

### Examples

```
pause bot Alpha
show portfolio
get profits
emergency stop
```

### Multi-Command

```
pause alpha and beta
stop bot1, bot2, and bot3
```

---

## Confirmation Levels

Commands have different confirmation requirements based on risk:

| Level | Description | Example | Confirmation Required |
|-------|-------------|---------|----------------------|
| **None** | Safe info commands | `show portfolio` | ❌ No |
| **Optional** | Bot lifecycle | `pause bot alpha` | ⚠️ Optional |
| **Required** | Trade-impacting | `reinvest` | ✅ Yes |
| **Double** | Emergency actions | `emergency stop` | ✅✅ Double confirm |
| **Typed Phrase** | Critical changes | `enable live trading` | ✅ Type exact phrase |

### Confirmation Process

**For Optional/Required:**
```
User: "pause bot alpha"
AI: "⚠️ This action requires confirmation. Confirm to proceed."
User: "confirm"
AI: "✅ Bot 'Alpha' paused successfully"
```

**For Double Confirmation:**
```
User: "emergency stop"
AI: "⚠️ This is a CRITICAL action. Type exactly: 'CONFIRM EMERGENCY STOP' to confirm."
User: "CONFIRM EMERGENCY STOP"
AI: "🚨 EMERGENCY STOP ACTIVATED - All trading halted"
```

---

## Bot Lifecycle Commands

### Start/Resume Bot

**Synonyms:** `start`, `activate`, `resume`, `enable`, `unpause`, `restart`, `continue`

```
start bot <name>
resume bot <name>
activate <name>
```

**Example:**
```
User: "start bot Alpha"
AI: {
  "ok": true,
  "command": "start_bot",
  "message": "✅ Bot 'Alpha' started successfully",
  "data": {
    "bot_id": "bot-123",
    "bot_name": "Alpha",
    "status": "active"
  }
}
```

**Confirmation:** Optional

---

### Pause Bot

**Synonyms:** `pause`, `stop`, `freeze`, `hold`, `disable`, `halt`

```
pause bot <name>
stop bot <name>
freeze <name>
hold bot <name>
```

**Example:**
```
User: "pause bot Beta"
AI: {
  "ok": true,
  "command": "pause_bot",
  "message": "⏸️ Bot 'Beta' paused",
  "data": {
    "bot_id": "bot-456",
    "bot_name": "Beta",
    "status": "paused",
    "since": "2025-12-27T14:30:00Z"
  }
}
```

**Confirmation:** Optional

---

### Stop Bot (Permanent)

**Synonyms:** `kill`, `terminate`, `delete`, `remove`, `destroy`

```
kill bot <name>
terminate bot <name>
delete <name>
```

**Example:**
```
User: "kill bot Gamma"
AI: "⚠️ This action requires confirmation. Confirm to proceed."
User: "confirm"
AI: {
  "ok": true,
  "command": "stop_bot",
  "message": "🛑 Bot 'Gamma' stopped permanently",
  "data": {
    "bot_id": "bot-789",
    "bot_name": "Gamma",
    "status": "stopped"
  }
}
```

**Confirmation:** Required (permanent action)

---

### Bulk Operations

```
pause all bots
resume all bots
stop all
start all
```

**Example:**
```
User: "pause all bots"
AI: {
  "ok": true,
  "command": "pause_all",
  "message": "⏸️ Paused 5 bot(s)",
  "data": {
    "count": 5
  }
}
```

**Confirmation:** Optional

---

### Multi-Bot Commands

```
pause alpha and beta
stop bot1, bot2, and bot3
resume alpha and gamma
```

**Example:**
```
User: "pause alpha and beta"
AI: {
  "multi_command": true,
  "results": [
    { "ok": true, "command": "pause_bot", "message": "⏸️ Bot 'Alpha' paused", ... },
    { "ok": true, "command": "pause_bot", "message": "⏸️ Bot 'Beta' paused", ... }
  ],
  "message": "Executed 2 commands"
}
```

**Confirmation:** Optional (for each bot)

---

### Bot Status

```
status of bot <name>
show bot <name>
info on <name>
```

**Example:**
```
User: "status of bot Alpha"
AI: {
  "ok": true,
  "command": "bot_status",
  "message": "📊 Status for bot 'Alpha'",
  "data": {
    "name": "Alpha",
    "status": "active",
    "current_capital": 1250.50,
    "total_profit": 250.50,
    "trades_count": 45,
    "win_rate": 67.5
  }
}
```

**Confirmation:** None

---

## Portfolio & Analytics Commands

### Portfolio Summary

**Synonyms:** `show`, `display`, `get`, `fetch`, `retrieve`

```
show portfolio
get portfolio
display summary
show balance
```

**Example:**
```
User: "show portfolio"
AI: {
  "ok": true,
  "command": "get_portfolio_summary",
  "message": "📊 Portfolio summary retrieved successfully",
  "data": {
    "equity": 15234.67,
    "realized_pnl": 2345.50,
    "fees_total": 123.45,
    "net_pnl": 2222.05,
    "drawdown_current": 5.2,
    "drawdown_max": 12.8,
    "total_bots": 8,
    "active_bots": 5
  }
}
```

**Confirmation:** None

---

### Profit Series

```
show profits
get profits
display profit history
```

**Example:**
```
User: "show profits"
AI: {
  "ok": true,
  "command": "get_profit_series",
  "message": "💰 Profit series retrieved for period: daily",
  "data": {
    "labels": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
    "values": [120.50, 150.30, -50.20, 200.10, 180.40, 220.60, 190.80],
    "total": 1011.50
  }
}
```

**Confirmation:** None

---

### Countdown Status

```
show countdown
get countdown status
progress to million
```

**Example:**
```
User: "show countdown"
AI: {
  "ok": true,
  "command": "get_countdown_status",
  "message": "Countdown status retrieved",
  "data": {
    "current_capital": 15234.67,
    "target": 1000000,
    "remaining": 984765.33,
    "progress_pct": 1.52,
    "days_remaining": 245
  }
}
```

**Confirmation:** None

---

## System Health Commands

### Health Status

```
show health
get system health
display health status
```

**Example:**
```
User: "show health"
AI: {
  "ok": true,
  "command": "get_health_status",
  "message": "System health status retrieved",
  "data": {
    "circuit_breaker": {
      "status": "ok",
      "tripped": false
    },
    "error_rate": 0.02,
    "uptime": "99.9%"
  }
}
```

**Confirmation:** None

---

### Active Alerts

```
show alerts
get alerts
display warnings
show warnings
```

**Example:**
```
User: "show alerts"
AI: {
  "ok": true,
  "command": "get_alerts",
  "message": "Retrieved 3 active alerts",
  "data": {
    "alerts": [
      {
        "id": "alert-1",
        "severity": "warning",
        "message": "Bot Alpha has 3 consecutive losses",
        "created_at": "2025-12-27T14:00:00Z"
      },
      {
        "id": "alert-2",
        "severity": "info",
        "message": "Daily profit target achieved",
        "created_at": "2025-12-27T12:30:00Z"
      }
    ]
  }
}
```

**Confirmation:** None

---

### Error Rate

```
show error rate
get errors
display error count
```

**Confirmation:** None

---

### Circuit Breaker Investigation

```
why did circuit breaker trip
why circuit breaker triggered
show circuit breaker reason
```

**Confirmation:** None

---

## Emergency Commands

### Emergency Stop

**Critical Command** - Stops ALL trading immediately

```
emergency stop
halt all
stop everything
```

**Example:**
```
User: "emergency stop"
AI: "⚠️ This is a CRITICAL action. Type exactly: 'CONFIRM EMERGENCY STOP' to confirm."
User: "CONFIRM EMERGENCY STOP"
AI: {
  "ok": true,
  "command": "emergency_stop",
  "message": "🚨 EMERGENCY STOP ACTIVATED - All trading halted",
  "data": {
    "bots_paused": 8,
    "trading_disabled": true,
    "timestamp": "2025-12-27T14:30:00Z"
  }
}
```

**Confirmation:** Double (must type exact phrase)

---

## Admin Commands

### Reinvest Profits

**Paper mode only** - Triggers manual reinvestment cycle

```
reinvest
trigger reinvest
run reinvest
```

**Example:**
```
User: "reinvest"
AI: "⚠️ This action requires confirmation. Confirm to proceed."
User: "confirm"
AI: {
  "ok": true,
  "command": "trigger_reinvestment",
  "message": "✅ Reinvestment cycle triggered successfully",
  "data": {
    "reinvested_amount": 500.00,
    "new_bot_allocations": {
      "Alpha": 200.00,
      "Beta": 300.00
    }
  }
}
```

**Confirmation:** Required

---

### Send Test Report

**Admin only** - Sends test email report

```
send test report
test email
test report
```

**Example:**
```
User: "send test report"
AI: {
  "ok": true,
  "command": "send_test_report",
  "message": "✅ Test report sent successfully",
  "data": {
    "sent": true,
    "recipient": "user@example.com"
  }
}
```

**Confirmation:** Optional  
**Permission:** Admin only

---

## Tool Registry

The AI can call these tools directly:

| Tool Name | Description | Parameters | Confirmation |
|-----------|-------------|------------|--------------|
| `get_portfolio_summary` | Get current portfolio summary | None | None |
| `get_profit_series` | Get profit time series | `period` (optional) | None |
| `get_countdown_status` | Get countdown to R1M | None | None |
| `pause_bot` | Pause a trading bot | `bot_id`, `reason` | Optional |
| `resume_bot` | Resume a paused bot | `bot_id` | Optional |
| `stop_bot` | Stop bot permanently | `bot_id` | Required |
| `trigger_reinvestment` | Trigger reinvestment | None | Required |
| `emergency_stop` | Emergency stop all | None | Double |
| `get_health_status` | Get system health | None | None |
| `get_alerts` | Get active alerts | None | None |
| `send_test_report` | Send test report | None | Optional (admin) |

---

## Synonym Support

The AI understands natural language variations:

### Action Synonyms

- **pause**: stop, freeze, hold, disable, halt
- **resume**: start, continue, unpause, enable, activate, restart
- **stop** (permanent): kill, terminate, delete, remove, destroy
- **show**: display, get, fetch, retrieve, list

### Target Synonyms

- **bot**: agent, trader, trading bot, algo

### Examples

All of these mean the same thing:
```
"pause bot Alpha"
"stop bot Alpha"
"freeze Alpha"
"hold bot Alpha"
"disable Alpha"
"halt bot Alpha"
```

---

## Examples

### Example 1: Daily Workflow

```
User: "show portfolio"
AI: [Shows portfolio with R15,234.67 equity, 5 active bots]

User: "show profits"
AI: [Shows last 7 days profits: Total R1,011.50]

User: "show health"
AI: [System healthy, no issues]

User: "start bot Alpha"
AI: [Confirms optional action, starts bot]
```

---

### Example 2: Bot Management

```
User: "pause bot Beta"
AI: [Pauses bot Beta]

User: "status of bot Beta"
AI: [Shows Beta is paused since 2025-12-27T14:30:00Z]

User: "resume bot Beta"
AI: [Resumes bot Beta]
```

---

### Example 3: Emergency Situation

```
User: "show alerts"
AI: [Shows 5 alerts: 3 consecutive losses, high drawdown warning]

User: "show health"
AI: [Circuit breaker status: OK, but approaching limits]

User: "emergency stop"
AI: [Requires typing "CONFIRM EMERGENCY STOP"]

User: "CONFIRM EMERGENCY STOP"
AI: [All trading halted, 8 bots paused]
```

---

### Example 4: Multi-Bot Operations

```
User: "pause alpha and beta"
AI: [Pauses both Alpha and Beta bots]

User: "pause all bots"
AI: [Pauses all 8 active bots]

User: "resume all bots"
AI: [Resumes all 8 paused bots]
```

---

### Example 5: Fuzzy Matching

```
User: "pause Alph"  (typo)
AI: [Fuzzy matches to "Alpha", pauses Alpha bot]

User: "status of Bet"  (partial name)
AI: [Fuzzy matches to "Beta", shows Beta status]
```

---

## Dashboard Feature Coverage

Every dashboard section can be controlled via AI commands:

| Dashboard Feature | Backend Endpoint | AI Command | Status |
|-------------------|------------------|------------|--------|
| Profit Graph | `/api/profits` | `show profits` | ✅ |
| Countdown | `/api/countdown/status` | `show countdown` | ✅ |
| Portfolio | `/api/portfolio/summary` | `show portfolio` | ✅ |
| Bot Lifecycle | `/api/bots/{id}/pause` | `pause bot alpha` | ✅ |
| Bot Status | `/api/bots/{id}/status` | `status of bot alpha` | ✅ |
| Reinvest | `/api/autonomous/reinvest-profits` | `reinvest` | ✅ |
| Health | `/api/health` | `show health` | ✅ |
| Alerts | `/api/alerts` | `show alerts` | ✅ |
| Reports | `/api/reports/daily/send-test` | `send test report` | ✅ |

---

## Response Format

All commands return a standardized JSON response:

### Success Response

```json
{
  "ok": true,
  "command": "pause_bot",
  "message": "✅ Bot 'Alpha' paused successfully",
  "data": {
    "bot_id": "bot-123",
    "bot_name": "Alpha",
    "status": "paused",
    "since": "2025-12-27T14:30:00Z"
  },
  "meta": {},
  "timestamp": "2025-12-27T14:30:00.123Z"
}
```

### Error Response

```json
{
  "ok": false,
  "command": "pause_bot",
  "message": "❌ Bot 'Unknown' not found",
  "error_code": "BOT_NOT_FOUND",
  "meta": {},
  "timestamp": "2025-12-27T14:30:00.123Z"
}
```

### Confirmation Required

```json
{
  "ok": false,
  "command": "emergency_stop",
  "message": "⚠️ This is a CRITICAL action. Type exactly: 'CONFIRM EMERGENCY STOP' to confirm.",
  "requires_confirmation": true,
  "confirmation_level": "double",
  "timestamp": "2025-12-27T14:30:00.123Z"
}
```

---

## Best Practices

1. **Use Natural Language**: The AI understands synonyms and variations
2. **Fuzzy Matching**: Bot names don't need to be exact
3. **Confirm Dangerous Actions**: Always confirm emergency/critical actions
4. **Check Status First**: Use `show health` and `show alerts` before making changes
5. **Multi-Command**: Batch operations on multiple bots for efficiency
6. **Use Portfolio View**: Start with `show portfolio` to understand system state

---

## Error Handling

Common error codes:

| Error Code | Meaning | Solution |
|------------|---------|----------|
| `BOT_NOT_FOUND` | Bot name not matched | Check bot name or use `show portfolio` |
| `PERMISSION_DENIED` | Admin command without admin rights | Contact admin |
| `TOOL_NOT_FOUND` | Unknown tool requested | Check command syntax |
| `EXECUTION_ERROR` | Command execution failed | Check logs, try again |
| `CONFIRMATION_REQUIRED` | Action needs confirmation | Confirm the action |

---

## Future Enhancements

Planned features:

- [ ] Voice command support
- [ ] Scheduled commands ("pause bot Alpha at 5pm")
- [ ] Conditional commands ("pause if drawdown > 10%")
- [ ] Command history and replay
- [ ] Custom command aliases
- [ ] Multi-language support

---

## Support

For issues with AI commands:

1. Check this documentation
2. Try `show health` and `show alerts`
3. Use exact confirmation phrases for critical actions
4. Contact support if command not recognized

---

**End of Command Reference**
