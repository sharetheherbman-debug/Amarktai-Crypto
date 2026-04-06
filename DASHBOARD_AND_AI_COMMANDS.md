# Amarktai Dashboard Functions & AI Commands Reference

## Dashboard Sections

The dashboard is divided into the following navigable sections:

| Section Key | Label | Icon |
|-------------|-------|------|
| `welcome` | Welcome / AI Chat | 🚀 |
| `overview` | Overview (default) | 📊 |
| `api` | API Setup | 🔑 |
| `bots` | Bot Management | 🤖 |
| `system` | System Mode | 🎮 |
| `graphs` | Profits & Performance | 💹 |
| `trades` | Live Trades | 📊 |
| `countdown` | Countdown Timers | ⏱️ |
| `wallet` | Wallet Hub | 💰 |
| `profile` | Profile | 👤 |
| `admin` | Admin Panel _(admin only)_ | 🔧 |
| `fetchai` | Fetch.AI Integration | 🤖 |
| `flokx` | Flokx Alerts | 📡 |

---

## Dashboard Functions (useDashboardState)

### Authentication & Navigation
| Function | Description |
|----------|-------------|
| `handleLogout()` | Sign out the current user and redirect to login |
| `showSection(name)` | Navigate to a dashboard section by key |

### Chat / AI Interface
| Function | Description |
|----------|-------------|
| `handleSendMessage()` | Send a natural-language message to the AI brain |
| `handleChatKeyDown(event)` | Handle Enter/Shift+Enter in the chat input |
| `handleClearChatHistory()` | Clear the AI chat history for the current session |
| `loadChatHistory()` | Load the user's past AI chat messages from the server |

### Bot Management
| Function | Description |
|----------|-------------|
| `handleCreateBot(e)` | Create a new trading bot with configured parameters |
| `handleCreateUAgent(e)` | Create a new Fetch.ai uAgent bot |
| `handleCreateFlokxBot(e)` | Create a new Flokx-integrated bot |
| `handleDeleteBot(botId)` | Delete a bot permanently |
| `handleStartBot(botId)` | Activate (start) a bot |
| `handleResumeBot(botId)` | Resume a paused bot |
| `handleResumeAllBots()` | Resume all paused bots with risk checks |
| `handleToggleBotMode(botId, currentMode)` | Toggle a bot between paper and live trading modes |
| `handleToggleBotPause(botId, currentStatus)` | Toggle a bot between active and paused states |
| `handleBotSetup()` | Submit the new-bot setup form |
| `handleSaveBotName(botId)` | Rename a bot |
| `handleRenameBotSubmit()` | Submit the bot rename form |
| `handleChangeRiskMode(botId, newRiskMode)` | Change the risk mode for a specific bot |
| `handleChangeBotMode(botId, newMode)` | Change a bot's trading mode (admin) |
| `handleChangeBotExchange(botId, newExchange)` | Change a bot's exchange (admin) |

### System Mode & Risk
| Function | Description |
|----------|-------------|
| `handleEmergencyStop()` | Trigger emergency stop on all bots |
| `executeEmergencyStop()` | Execute confirmed emergency stop |
| `handlePaperReset(confirmPhrase)` | Reset paper trading balances |
| `handleRiskProfileChange(newProfile)` | Change the user's global risk profile |
| `handleResetDailyLossLock()` | Reset daily loss lock for all bots |
| `handleResetBodyguardLock()` | Reset the AI bodyguard safety lock |
| `toggleSystemMode(mode)` | Toggle a system mode flag on/off |

### AI Tools
| Function | Description |
|----------|-------------|
| `handleTriggerLearning()` | Manually trigger the AI learning loop |
| `handleEvolveBots()` | Trigger genetic algorithm bot evolution |
| `handleGetInsights()` | Request AI-generated trading insights |
| `handlePredictPrice()` | Request an AI price prediction |
| `handleReinvestProfits()` | Trigger profit reinvestment cycle |
| `handleTriggerBodyguard()` | Manually trigger the AI bodyguard check |

### Profile & API Keys
| Function | Description |
|----------|-------------|
| `handleProfileChange(field, value)` | Update a profile field |
| `handleProfileSave()` | Save updated profile to server |
| `handleChangePassword(userId)` | Change user password |
| `handleSaveApiKey(provider)` | Save an exchange API key |
| `handleTestApiKey(provider)` | Test an exchange API key connection |
| `handleDeleteApiKey(provider)` | Delete a saved exchange API key |
| `handleMigrateApiKeys()` | Migrate API keys to new storage format |

### Countdown Timers
| Function | Description |
|----------|-------------|
| `addCustomCountdown()` | Add a custom countdown timer |
| `deleteCustomCountdown(id)` | Remove a custom countdown timer |

### Wallet
| Function | Description |
|----------|-------------|
| `handleSendMessage()` | (AI-assisted transfers via chat) |

### Admin Functions _(admin only)_
| Function | Description |
|----------|-------------|
| `loadAdminUsers()` | Load all users into the admin panel |
| `loadAdminBots()` | Load all bots across all users |
| `handleUserSelection(userId)` | Select a user in the admin panel |
| `handleEmailAllUsers()` | Send a broadcast email to all users |
| `handleDeleteUser(userId)` | Delete a user account |
| `handleDeleteUserAdmin(userId)` | Admin-delete a user with full cleanup |
| `handleBlockUser(userId, isBlocked)` | Block or unblock a user |
| `handleToggleBlockUser(userId, currentStatus)` | Toggle user block status |
| `handleResetPassword(userId)` | Reset a user's password |
| `handleForceLogout(userId)` | Force-logout a user from all sessions |
| `updateGlobalEmergencyOverride(value)` | Set global emergency override flag |
| `updateUserEmergencyOverride(userId, value)` | Set per-user emergency override |
| `clearUserEmergencyOverride(userId)` | Clear per-user emergency override |

### Data Loaders (called automatically and on-demand)
| Function | Description |
|----------|-------------|
| `loadRecentTrades()` | Load recent trade feed |
| `loadFlokxAlerts()` | Load Flokx market alerts |
| `loadChatHistory()` | Load AI chat history |
| `loadAdminUsers()` | Load admin user list |
| `loadAdminBots()` | Load admin bot list |
| `confirmLiveSwitch(funded, confirm)` | Confirm transition to live trading |

---

## AI Commands Reference

All AI commands are issued via the natural-language chat panel (`Welcome` section) or the AI Tools panel.

### How to Use
- Type a natural-language command in the chat, e.g. *"pause all bots"*, *"show my performance"*, *"switch to paper mode"*
- For destructive actions, the AI will request a **confirmation phrase** before executing
- Some commands use quick-action buttons in the AI Tools panel

---

### Read-Only Commands (no confirmation needed)

| Action Name | Natural Language Examples | What It Does |
|-------------|---------------------------|--------------|
| `get_system_status` | "What's the system status?", "Health check" | Returns system health, active modes, uptime |
| `get_system_mode` | "What mode am I in?", "Show current mode" | Returns paper/live/autopilot mode |
| `get_overview_snapshot` | "Overview", "Show me the dashboard summary" | Portfolio snapshot: bots, capital, PnL |
| `get_performance_summary` | "How am I doing?", "Performance this week", "Show stats" | 7-day performance: trades, wins, losses, net PnL |
| `get_risk_status` | "Risk status", "Am I risk-locked?", "Show risk" | Daily loss lock, bodyguard lock status |
| `list_bots` | "List my bots", "Show all bots", "Bot status" | All bots with status, mode, and capital |
| `get_wallet_status` | "Wallet balance", "Show my funds", "How much capital?" | Exchange balances and funding status |
| `get_autonomy_status` | "Autonomy status", "Is autopilot running?" | Autonomy subsystem state (paused/active) |
| `get_bodyguard_status` | "Bodyguard status", "Is bodyguard active?" | AI bodyguard lock/trigger state |
| `get_learning_status` | "Learning status", "Is AI learning?" | Learning loop active/paused state |
| `diagnostics_realtime` | "Diagnostics", "System diagnostics", "Realtime status" | Live diagnostics: bots, connections, errors |
| `report_last_errors` | "Show errors", "What went wrong?", "Last errors" | Last known errors from all subsystems |
| `open_admin_tools` | "Open admin", "Admin tools" | Unlocks admin panel for current session |
| `get_portfolio_summary` | "Portfolio summary", "Show equity", "What's my PnL?" | Full portfolio: equity, realized PnL, fees, drawdown, win rate |
| `get_win_rate` | "Win rate", "What's my win rate?", "Win rate this month" | Win rate and trade count for a period (today/7d/30d/all) |
| `get_drawdown` | "Drawdown", "What's my drawdown?", "Max drawdown" | Current and maximum drawdown percentages |
| `get_countdown` | "Countdown to goal", "How long to reach my target?", "Days to R10k" | Countdown to profit target with days-to-target estimate |
| `predict_price` | "Predict BTC price", "Price prediction for ETH/ZAR" | ML price prediction for a trading pair |

### Action Commands (confirmation required)

| Action Name | Confirmation Phrase | Natural Language Examples | What It Does |
|-------------|---------------------|---------------------------|--------------|
| `start_bot` | Reply with confirmation_id | "Start bot [name]", "Activate [bot]" | Sets bot status to active |
| `pause_bot` | Reply with confirmation_id | "Pause bot [name]", "Stop [bot] temporarily" | Pauses a specific bot |
| `resume_bot` | Reply with confirmation_id | "Resume bot [name]", "Restart [bot]" | Resumes a paused bot |
| `stop_bot` | Reply with confirmation_id | "Stop bot [name]", "Kill [bot]" | Stops a bot (requires restart to reactivate) |
| `pause_all_bots` | Reply with confirmation_id | "Pause all bots", "Halt trading" | Pauses every active bot |
| `resume_all_bots` | Reply with confirmation_id | "Resume all bots", "Restart all trading" | Resumes all paused bots (with risk checks) |
| `emergency_stop` | `CONFIRM EMERGENCY STOP` | "Emergency stop", "Kill everything", "STOP NOW" | Activates emergency stop: pauses all bots immediately |
| `set_system_mode` | `CONFIRM LIVE TRADING` | "Switch to live", "Go live", "Enable paper mode" | Switches system trading mode |
| `switch_mode` | `CONFIRM LIVE TRADING` | "Switch to paper", "Paper mode", "Go to autopilot" | Alias for set_system_mode |
| `toggle_autopilot` | `CONFIRM AUTOPILOT` | "Enable autopilot", "Turn on autopilot", "Disable autopilot" | Toggles the autopilot subsystem |
| `reset_risk_locks` | `RESET RISK LOCKS` | "Reset risk locks", "Clear daily loss lock", "Unlock risk" | Resets all active risk locks |
| `transfer_funds` | `CONFIRM TRANSFER` | "Transfer 500 USDT from Binance to Luno" | Executes an inter-exchange transfer |
| `pause_autonomy_subsystem` | `CONFIRM AUTONOMY PAUSE` | "Pause autopilot", "Stop autonomy", "Pause learning" | Pauses an autonomy subsystem |
| `resume_autonomy_subsystem` | `CONFIRM AUTONOMY RESUME` | "Resume autopilot", "Resume autonomy" | Resumes a paused autonomy subsystem |
| `run_autonomy_cycle_now` | `CONFIRM AUTONOMY RUN` | "Run autonomy now", "Trigger autopilot cycle" | Triggers immediate autonomy cycle |
| `enable_learning_loop` | Reply with confirmation_id | "Enable learning", "Start learning loop" | Enables the AI self-learning loop (admin only) |
| `disable_learning_loop` | Reply with confirmation_id | "Disable learning", "Stop learning loop" | Disables the AI self-learning loop (admin only) |
| `set_risk_mode` | None (no confirmation) | "Set risk to safe", "Switch to risky mode" | Changes risk profile for user or bot |
| `create_bot` | None (no confirmation) | "Create a bot on Binance", "Make a new paper bot called Alpha" | Creates a new trading bot |
| `delete_bot` | `CONFIRM DELETE BOT` | "Delete bot Alpha", "Remove bot [name]" | Permanently deletes a bot (soft delete, preserves history) |
| `trigger_reinvestment` | Reply with confirmation_id | "Reinvest profits", "Trigger reinvestment cycle" | Triggers manual profit reinvestment cycle |
| `evolve_bots` | Reply with confirmation_id | "Evolve bots", "Run genetic algorithm", "Improve bot strategies" | Runs genetic algorithm evolution to improve bot parameters |

### AI Quick-Action Buttons (AI Tools Panel)
These functions are accessible via the **🧠 AI Tools** button in the Welcome section:

| Button | Underlying Handler | Description |
|--------|--------------------|-------------|
| 🎓 Trigger Learning | `handleTriggerLearning()` | Manually kick off the AI self-learning cycle |
| 🧬 Evolve Bots | `handleEvolveBots()` | Run genetic algorithm to evolve bot strategies |
| 🔍 Get Insights | `handleGetInsights()` | Get AI-generated trading insights and recommendations |
| 📈 Predict Price | `handlePredictPrice()` | Request an AI price prediction for configured pairs |
| 💰 Reinvest Profits | `handleReinvestProfits()` | Trigger profit reinvestment into active bots |

---

## Confirmation Flow

For destructive or financial actions, the AI follows a two-step confirmation flow:

1. **Request**: User sends a command (e.g. "emergency stop")
2. **Challenge**: AI responds with a `confirmation_id` and optionally a required phrase
3. **Confirm**: User replies with the `confirmation_id` (and phrase if required)
4. **Execute**: Action is performed and result returned

Example:
```
User: "switch to live trading"
AI:   "⚠️ This will enable LIVE TRADING with real funds. Reply with confirmation_id 'abc123' and phrase: CONFIRM LIVE TRADING"
User: "abc123 CONFIRM LIVE TRADING"  
AI:   "✅ System mode switched to live."
```

---

## Go-Live Checklist

### Environment Variables Required
```env
MONGO_URL=mongodb://127.0.0.1:27017
JWT_SECRET=<minimum 32 chars, use: openssl rand -hex 32>
ADMIN_PASSWORD=<strong password>

# Optional but recommended
OPENAI_API_KEY=<key for AI chat intelligence>
SMTP_HOST=<smtp host for email alerts>
SMTP_USER=<smtp username>
SMTP_PASSWORD=<smtp password>
ENABLE_PAPER_TRADING=true
ENABLE_LIVE_TRADING=false   # set true when ready for live
```

### Backend Health Checks
- `GET /api/health` → `{"status": "healthy"}`
- `GET /api/system/status` → system flags confirmed
- `GET /api/bots` → returns bot list (authenticated)

### Frontend Build
```bash
cd frontend
npm install
npm run build   # Should complete with 0 errors
```

### Running Tests
```bash
# All tests (requires PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 to block broken web3 pytest plugin)
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 python -m pytest tests/ -p asyncio -v
```
