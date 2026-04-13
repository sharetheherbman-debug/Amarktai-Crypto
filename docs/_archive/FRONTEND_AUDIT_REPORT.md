# FINAL FRONTEND STRUCTURE + FUNCTION AUDIT
## Amarktai Network — Complete Frontend State Before Final Update
**Date:** 2026-03-07  
**Auditor:** Copilot Coding Agent  
**Scope:** Full frontend audit — Landing, Login, Register, Dashboard (shell, nav, sections, hooks, realtime, auth, graphs)  
**Purpose:** Complete, exact written audit sufficient for a final single frontend implementation pass  

---

## 1. Executive Summary

The Amarktai frontend is a single-page React application with a solid structural foundation but a significant **wiring gap** between the architecture that was designed and the one that is actually rendered. 

**Key summary facts:**
- **27 dashboard section files** exist across `pages/dashboard/sections/`
- **Only 12 are directly imported in `Dashboard.js`** — 15 are dead/unreachable from the main nav
- **4 are wrapper-only** (PerformanceSection, BotOperationsSection, TradingMonitorSection, ProfileControlsSection) — these composite many of the 15 dead sections inside themselves, but are themselves not in the nav
- **3 powerful panels** (BotRadarSection, CoinStatsPanel, HuggingFacePanel) **are only reachable via PerformanceSection**, which IS in the nav, making them accessible but deeply nested and unannounced in the nav label
- **2 separate chat systems** exist: `AiChatSection.js` (currently rendered in WelcomeSection via `useDashboardState`) and `AIChatPanel.js` (components/ — standalone, not rendered anywhere in the current app)
- **2 separate SystemModes components** exist: `pages/dashboard/sections/SystemModeSection.js` (rendered) and `components/Dashboard/SystemModesSection.js` (dead)
- **3 separate `:root` CSS definitions** conflict: `styles/theme.css` (blue gradient), `DashboardV3.css` (now overridden), and `index.css` — the last one loaded wins
- **Mobile navigation** consists only of a logo button and a "Logout" button — the entire sidebar nav is inaccessible on mobile
- **4 pages** (About, Features, Privacy, Terms) have full implementations but are routed to nowhere — not in `App.js`
- The **useDashboardState hook is 3,246 lines** and does everything — all API calls, all state, all WebSocket handling, all event handling — making it a critical single point of failure

The dashboard is functional but fragmented. The design system is 90% coherent (dark terminal aesthetic, blue `#3B82F6` brand accent) with minor CSS variable collision between `theme.css` and `DashboardV3.css`. The final frontend pass must focus on: completing the nav, making dead sections accessible, fixing mobile, and wiring the remaining 15 section files into the live render tree.

---

## 2. Landing Page Audit

### File: `frontend/src/pages/Landing.js` + `Landing.css` + `Auth.css`

**Composition:**
- `NeuralBackground` animated particles canvas  
- Neural vignette overlay div  
- Hero section: badge, logo image, wordmark (`Amarkt<span>AI</span> Crypto`), tagline, CTA buttons  
- Stats bar: 4 stats (7 Exchanges, 4 AI Providers, 24/7, ∞ Scalable)  
- Feature cards: 3 cards (Neural AI Core, Multi-Exchange Engine, Fully Autonomous) using Lucide icons  
- `SiteFooter` at bottom  

**Branding:**
- `AI` is rendered inline as `<span className="wordmark-ai">AI</span>` styled in `Landing.css` — NOT using the `Brand.js` component  
- `SiteFooter` renders correctly with blue `AI` using inline span style  
- Logo: `/assets/logo.png` (hero size)  

**State:** Stateless (no hooks, no API calls)

**What is correct:**
- Design matches the premium dark terminal aesthetic
- CTA buttons navigate to `/login` and `/register` correctly
- Stats are accurate (7 exchanges, 4 AI providers)
- `NeuralBackground` applies to all public pages consistently

**What is still inconsistent:**
- The Landing `wordmark-ai` style is separate from `Brand.js`. The `Brand.js` component is only used in the Dashboard topbar. Any future wordmark changes must be made in two places.
- `Landing.js` does not use `Auth.css` (`import './Auth.css'` is in Login and Register, not Landing), but `Landing.css` is imported in all three public pages (Landing, Login, Register), creating shared styling concerns

**What the Dashboard must inherit:**
- Same dark `#020409` background
- Same blue `#3B82F6` for `AI` text
- Same particle/vignette system already applied
- Same Inter font stack

---

## 3. Login Page Audit

### File: `frontend/src/pages/Login.js`

**Composition:**
- `NeuralBackground` + vignette  
- `StepDots` component (2-step indicator)  
- Two-step form: Step 1 = email, Step 2 = password  
- Eye/EyeOff toggle for password visibility  
- ArrowLeft back button  
- `SiteFooter`  

**API:** `post('/auth/login', { email, password })` → stores `token` and `user.id` in `localStorage`

**State:** Local only (`useState`, no global hooks)

**What is correct:**
- Stepwise flow is clean and polished
- Toast validation matches landing page style
- Input uses shadcn `Input` component from `@/components/ui/input`

**What is inconsistent:**
- Uses `import { post } from '../lib/apiClient'` — correct authenticated client
- Register.js uses `import { post } from '@/lib/apiClient'` (different alias) — functionally identical but inconsistent path style

**No blockers** on Login page for go-live.

---

## 4. Register Page Audit

### File: `frontend/src/pages/Register.js`

**Composition:**
- `NeuralBackground` + vignette  
- `StepDots` with 4 steps: Name, Email, Password, Access Code  
- Multi-step form with password/confirm visibility toggles  
- Invite code required on step 4  
- `SiteFooter`  

**API:** `post('/auth/register', { first_name, email, password, invite_code })`

**State:** Local only

**What is correct:**
- 4-step registration is gated behind invite code (appropriate for beta access control)
- Password match validation and minimum 6-char validation

**What is inconsistent:**
- Does not use the `Brand.js` component for the wordmark — uses the same inline wordmark pattern from Landing.css
- `StepDots` component is defined locally in both `Login.js` and `Register.js` — it is duplicated (identical in both files, not shared)

**Missing:** No "Registration closed" state or explicit message if invite codes are not yet available.

---

## 5. Dashboard Shell Audit

### File: `frontend/src/pages/Dashboard.js` (867 lines)
### CSS: `DashboardV3.css` (imported in Dashboard.js), `styles/theme.css` (imported in index.js)

**Shell Structure:**
```
<div class="app">
  <aside class="sidebar">          ← Desktop only, always visible
    <img logo>                     ← Click = OVERVIEW
    <nav>                          ← 9-10 anchor links
  </aside>
  <header class="topbar">          ← Desktop only
    <div class="topbar-brand">
      <Brand />                    ← "AmarktAI" with blue AI
    </div>
    <div class="top-actions">
      <Badge> MODE</Badge>         ← Paper/Live mode badge
      <Badge> REALTIME</Badge>     ← WS status badge
      <Badge> Risk</Badge>         ← Risk level badge
      <button>Logout</button>
    </div>
  </header>
  <div class="mobile-topbar">      ← Mobile only
    Logo button → OVERVIEW
    "Overview" button → OVERVIEW
    "Logout" button
  </div>
  <main class="main">              ← Active section renders here
    {activeSection === NAV.xxx && <XSection />}
  </main>
  <SiteFooter />
</div>
```

**Key shell observations:**

1. **Sidebar logo click** → `showSection(NAV.OVERVIEW)` — routes to Overview which is NOT in the nav items (it's the logo-click-only destination). This is intentional but means Overview has no nav link.

2. **The topbar Brand** uses `<Brand />` component correctly — this is the only place `Brand.js` is used in the dashboard.

3. **Three badge statuses in topbar:**
   - Mode badge: `modeLabel` / `modeTone` from useDashboardState
   - Realtime badge: `realtimeLabel` / `realtimeTone` — WebSocket connection state
   - Risk badge: `riskLabel` / `riskTone` — from `/api/risk/status`

4. **Mobile topbar is critically limited:** Only shows "Overview" and "Logout". The full nav (9 items) is desktop-only. Mobile users cannot access Bot Management, System Mode, Profits, Live Trades, Countdown, Wallet Hub, Profile, or Admin sections. This is a **critical usability blocker for mobile users**.

5. **Bot Promotion Modal** is rendered inline in Dashboard.js — not in a separate component. It appears when `showPromotionModal && eligibleBots.length > 0`, checked every 5 minutes via polling.

6. **Emergency Confirm Modal** uses the shared `<ModalConfirm>` component from `@/ui/components/ModalConfirm` — correctly follows the design system.

7. **`renderAdmin()` and `renderProfile()` functions** are defined in Dashboard.js but are never called — they are vestigial render helpers from before the current section-based approach. The actual rendering happens in the `{activeSection === ...}` conditional blocks in the `<main>` element.

**CSS system problems:**

| File | `:root` vars defined | Load order |
|------|---------------------|------------|
| `index.css` (Tailwind + shadcn vars) | Tailwind token vars (`--background`, `--foreground`, etc.) | 1st |
| `styles/theme.css` | App color tokens (`--bg`, `--panel`, `--text`, etc. — deep blue gradient) | 2nd |
| `ui/global.css` | Layout/typography utils | 3rd |
| `DashboardV3.css` | **Re-declares all color tokens** (`--bg: #020409`, `--accent2`, etc.) | 4th (wins) |

The **last-wins cascade** means `DashboardV3.css`'s simpler flat-black `--bg: #020409` overrides `theme.css`'s deep blue gradient `--bg: radial-gradient(...)`. The Dashboard uses the flat-black version. The `theme.css` file is effectively dead for all color tokens — only its layout-specific vars survive if they don't conflict. This is a **latent confusion risk**: developers editing `theme.css` will not see their changes in the dashboard.

---

## 6. Dashboard Navigation Audit

### Source: `constants/dashboardNav.js` + Dashboard.js sidebar rendering

**Current NAV constant:**
```
NAV.OVERVIEW         → logo click only (not in sidebar nav)
NAV.WELCOME          → 🤖 Welcome
NAV.API_SETUP        → 🔑 API Setup
NAV.BOT_MANAGEMENT   → ⚙️ Bot Management
NAV.SYSTEM_MODE      → 🎛️ System Mode
NAV.PROFITS_PERFORMANCE → 💹 Profits & Performance
NAV.LIVE_TRADES      → 📡 Live Trades
NAV.COUNTDOWN        → ⏱️ Countdown
NAV.WALLET_HUB       → 💰 Wallet Hub
NAV.PROFILE          → 👤 Profile
NAV.HIDDEN_ADMIN     → 🔧 Admin (only visible when showAdmin=true)
```

**Admin visibility mechanism:** `showAdmin` state is `false` by default each session. The only way to set it to `true` is via the AI chat command "show admin" + admin password verification via `/api/admin/unlock`. There is no `user.is_admin` check — any user who knows the command phrase and has the admin password can show the admin panel. This is a **security concern** (social engineering risk) but it provides obscurity through the non-obvious unlock mechanism.

**Sections NOT reachable from nav:**

| Section | Status | Reason |
|---------|--------|--------|
| `OverviewSection` | Reachable via logo click only | No nav link |
| `BotRadarSection` | Reachable inside PerformanceSection | Nested under 💹, no own nav |
| `CoinStatsPanel` | Reachable inside PerformanceSection | Nested, no own nav |
| `HuggingFacePanel` | Reachable inside PerformanceSection | Nested, no own nav |
| `TruthConsoleSection` | Reachable inside AdminTruthSection | Nested under Admin |
| `ScalperBotsPanel` | Reachable inside BotManagementSection | Nested tab |
| `ExchangeStatusSection` | Dead — only in TradingMonitorSection | TradingMonitorSection not in nav |
| `MetricsWithTabsSection` | Reachable via renderMetricsWithTabs pass to PerformanceSection | Nested |
| `HomeSection` | Dead | Not imported or rendered |
| `BotOperationsSection` | Dead | Not imported or rendered |
| `TradingMonitorSection` | Dead | Not imported or rendered |
| `ProfileControlsSection` | Dead | Not imported or rendered |
| `WalletTreasurySection` | Dead — duplicates WalletHubSection | Not imported or rendered |
| `AiCommandSection` | Dead | Not imported or rendered |
| `AiChatSection` | Rendered inside WelcomeSection | No own nav entry |

**BOT_TAB constants** (defined in `dashboardNav.js`) are imported in `BotManagementSection.js` but only partially used — the `BOT_TAB.SPAWN_STATUS` value is referenced but the tab management uses string literals `'scalper'`, `'training'`, `'spawn'` directly in JSX. The constants file defines `CREATE`, `NORMAL_BOTS`, `SCALPER_BOTS`, `TRAINING_QUARANTINE`, `SPAWN_STATUS` but these are not all used consistently.

**What the final nav structure should be:**

The current nav is correct in its 9 visible items. The issue is not the nav itself, but:
1. Overview should optionally be reachable via a "Home" nav item, not just logo click
2. ExchangeStatusSection has no home — it belongs in either Bot Management or a dedicated "Exchanges" view
3. TradingMonitorSection is a superior composite of Live Trades + BotRadar + Exchange Status but is unused
4. The mobile nav needs a hamburger/drawer or bottom tab bar

---

## 7. Dashboard Section-by-Section Audit

### 7.1 Overview Section
**File:** `pages/dashboard/sections/OverviewSection.js` (327 lines)  
**Nav:** Logo click only — not in sidebar nav  
**Rendered:** YES — `{activeSection === NAV.OVERVIEW}`

**Contains:**
- `SectionHeader` with title and subtitle
- Status summary cards: AI Key Configured, Self-Healing, Emergency Stop
- Live price ticker row (3 pairs: XBTZAR, ETHZAR, XRPZAR)
- Metrics grid: Total Profit, Active Bots, Mode, Risk Level
- Recent event row: last trade time, daily loss lock, bodyguard status
- Auto-spawn status with reason and progress
- Risk lock reset buttons (Bodyguard / Daily Loss Lock)
- "Resume All Bots" button

**State props consumed:** `user`, `aiStatus`, `autonomyStatus`, `botControlLoading`, `formatDate`, `handleResetBodyguardLock`, `handleResetDailyLossLock`, `handleResumeAllBots`, `learningStatus`, `livePrices`, `metrics`, `modeLabel`, `overviewData`, `riskStatus`, `systemModes`

**Backend endpoints (via parent hook):** `/api/overview/snapshot`, `/api/risk/status`, `/api/prices/live`

**What is correct:** Dense information display, uses GlassCard design system, all data is live-connected

**What is broken/missing:**
- `modeLabel` and `systemModes` are both passed but Overview section renders `systemModes.paperTrading ? 'PAPER' : 'LIVE'` — it has its own internal mode resolution, not using `modeLabel` prop
- `autonomyStatus` — the component checks `autonomyStatus?.self_healing || autonomyStatus?.bodyguard || riskStatus?.bodyguard_lock?.active`. Three different paths to the same flag. If the API changes one field name, the check silently shows wrong state
- `overviewData.lastTradeTime` can be `null` and renders as "Not available" with no additional context

**Should be kept, enhanced:** This is the system health dashboard. It should become the canonical "Home" / health terminal. Needs a nav link.

---

### 7.2 Welcome (AI Chat) Section
**File:** `pages/dashboard/sections/WelcomeSection.js` (58 lines — thin wrapper)  
**File (actual content):** `pages/dashboard/sections/AiChatSection.js` (164 lines)  
**Nav:** 🤖 Welcome  
**Rendered:** YES

**Contains:**
- `SectionHeader` with personalized "Welcome, {first_name}" title
- `AiChatSection` embedded directly

**AiChatSection contents:**
- Chat toolbar: Load History, Clear History, AI Tools toggle
- AI Tools panel (collapsible): 5 buttons — Trigger Learning, Evolve Bots, Get Insights, Predict Price, Reinvest Profits
- Message feed: user/assistant message bubbles
- Input box with send button
- "Analytics" toggle (`showAnalytics`) — sets a local state but renders nothing conditional on it (dead toggle)

**Chat API flow:**
1. All messages are first saved to `POST /api/ai/chat` with `log_only: true` (logging only)
2. Admin commands ("show admin", "hide admin") are intercepted and handled with `POST /api/admin/unlock`
3. All other messages go to `POST /api/chat/message` for AI processing
4. Response handling: checks for `OPENAI_KEY_MISSING` error code, renders error state if OpenAI key missing

**What is broken/misleading:**
- The `showAnalytics` local state in `AiChatSection` is set by a button but nothing in the return JSX uses it as a conditional. This is dead state.
- `WelcomeSection` takes 12 props that it passes directly to `AiChatSection` — it adds no logic of its own. The wrapper adds no value beyond the `SectionHeader`. All the WelcomeSection logic is actually in `AiChatSection`.
- There is also `components/AIChatPanel.js` (526 lines) — a completely separate, standalone AI chat implementation that is **not rendered anywhere in the current app**. It has its own state, session checking, and message history management. This is dead code that duplicates the active `AiChatSection`.

**Recommendation:** Remove `WelcomeSection` wrapper, render `AiChatSection` directly with its own `SectionHeader`. Archive `components/AIChatPanel.js`.

---

### 7.3 API Setup Section
**File:** `pages/dashboard/sections/ApiSetupSection.js` (20 lines — thin wrapper)  
**File (actual content):** `components/APIKeySettings.js` (240+ lines)  
**Nav:** 🔑 API Setup  
**Rendered:** YES

**Contains:**
- `SectionHeader` with title and subtitle
- `api-setup-split` div layout
- `APIKeySettings` component (self-contained)

**APIKeySettings component:**
- Reads provider config from `constants/platforms.js` — 7 exchanges + 4 AI = 11 providers
- Fetches `GET /api/keys/status` on mount and re-fetches after any save/test/delete
- For each provider: expand/collapse panel, input fields per provider, Save / Test / Delete buttons
- Status badges: configured, not_configured, testing, error
- Handles `unsupportedProviders` — backend can mark providers as unsupported
- Listens for realtime events (`api_key_saved`, `api_key_tested`, `api_key_deleted`) via `realtimeClient.on()`

**What is correct:**
- `APIKeySettings` is self-contained and independently data-fetching (does not depend on `useDashboardState`)
- Provider list matches the canonical 11 providers (7 exchanges + 4 AI)
- Realtime refresh on key events is correctly wired

**What is broken:**
- `ApiSetupSection.js` passes NO props to `APIKeySettings` — the component manages everything itself. The prop-passthrough system used by other sections is absent here. This is actually clean, but inconsistent with the dashboard pattern.
- `ApiSetupSection.js` layout div `api-setup-panel` with `api-setup-split` wrapper has no CSS definition in `DashboardV3.css` (the class names are undefined — may fallback to block display silently)

---

### 7.4 Bot Management Section
**File:** `pages/dashboard/sections/BotManagementSection.js` (584 lines)  
**Nav:** ⚙️ Bot Management  
**Rendered:** YES

**Contains (via 4 tabs):**
- Tab 0 (default): Bot creation form + list of all bots
- Tab `scalper`: Scalper Bots — renders `ScalperBotsPanel` (which calls `/api/scalper/caps` and `/api/scalper/summary`)
- Tab `training`: Training & Quarantine — renders `TrainingQuarantineSection` (which calls `/api/training/history` and `/api/quarantine/status`)
- Tab `spawn`: Auto-Spawn Status — displays `autoSpawnStatus` data (from `/api/diagnostics/auto-spawn`)

**Subcomponents:**
- `PlatformSelector` — custom dropdown for exchange selection
- `ScalperBotsPanel` — scalper-specific panel (from `pages/dashboard/sections/`)
- `TrainingQuarantineSection` — from `components/Dashboard/` (NOT from sections/)

**Bot creation form (tab 0):**
- Name, exchange (PlatformSelector), initial capital, risk mode
- Submits via `handleCreateBot` (delegated to `useDashboardState`)

**Bot list (tab 0):**
- Filter by status (all/active/paused/stopped/training/quarantine)
- Filter by exchange (platformFilter from parent)
- Bot cards with status badges, P&L, capital, actions (Start/Pause/Resume/Delete)
- Expandable bot detail drawer (tabs: overview, history, strategy)
- Bot rename (inline edit)
- Bot mode toggle (paper/live)

**What is correct:** Bot list is comprehensive, bot detail is well-structured

**What is broken/misleading:**
- `botManagementTab` state is used as `'scalper'`, `'training'`, `'spawn'` but the `BOT_TAB` constants define these differently (`BOT_TAB.SCALPER_BOTS`, `BOT_TAB.TRAINING_QUARANTINE`, `BOT_TAB.SPAWN_STATUS`). The section uses string literals, making the constants file drift silently.
- `ScalperBotsPanel` uses raw `fetch()` with headers from `axiosConfig`, not `apiClient`. This bypasses the retry/401 logic.
- `TrainingQuarantineSection` from `components/Dashboard/` has its own internal polling (`setInterval(fetchData, 10000)`) that runs independently of `useDashboardState` — double data fetching during active use.

---

### 7.5 System Mode Section
**File:** `pages/dashboard/sections/SystemModeSection.js` (154 lines)  
**Nav:** 🎛️ System Mode  
**Rendered:** YES

**Contains:**
- 3 toggleable mode cards: Paper Trading, Live Trading, Autopilot
- Risk Profile dropdown (safe/balanced/risky)
- Paper Reset button + modal (only visible in paper mode)

**Paper Reset flow:**
- User must type "RESET PAPER MODE" (exact phrase)
- `handlePaperReset` in `useDashboardState` calls `POST /api/system/paper-reset`
- Note: the modal confirmation phrase does NOT require a password (unlike `/api/system/reset-paper` which requires `PAPER_RESET_PASSWORD`)
- This means any logged-in user can reset their own paper data just by typing a phrase

**What is correct:** Mode toggle cards are clear, risk profile dropdown is clean

**What is broken:**
- `handleEmergencyStop` is NOT passed to SystemModeSection (it's in the prop list but absent from the Dashboard.js rendering of SystemModeSection). Emergency stop is in ProfileSection instead.
- The `paperResetChecking`, `paperResetValid` props are accepted but never used in the component JSX — vestigial props
- There is also `components/Dashboard/SystemModesSection.js` — a completely separate, legacy implementation with `window.confirm()` dialogs, not used anywhere

**Also duplicated:**
- `WalletTreasurySection.js` is identical to `WalletHubSection.js` except for the title ("💰 Wallet & Treasury" vs "💰 Wallet Hub"). Same WalletHub component, same props, same layout. Pure dead duplicate.

---

### 7.6 Profits & Performance Section
**File:** `pages/dashboard/sections/PerformanceSection.js` (21 lines — wrapper)  
**File (profit chart):** `pages/dashboard/sections/ProfitsSection.js` (835 lines)  
**Nav:** 💹 Profits & Performance  
**Rendered:** YES

**PerformanceSection wraps:**
1. `ProfitsSection` — profit tabs/charts
2. `BotRadarSection` — bot position radar
3. `CoinStatsPanel` — CoinStats market data
4. `HuggingFacePanel` — HuggingFace AI integration

**ProfitsSection contains (5 tabs):**
- `metrics`: Metrics dashboard (renders `MetricsWithTabsSection` via `renderMetricsWithTabs` prop passed from Dashboard.js)
- `profit-history`: Line chart of profit over time (Chart.js Line)
- `equity`: Equity curve chart (needs `equityData`)
- `drawdown`: Drawdown analysis chart
- `win-rate`: Win rate over time with bot breakdown

**Charts used:** `react-chartjs-2` Line chart — registered in Dashboard.js with ChartJS.register()

**BotRadarSection:**
- Polls `GET /api/radar/snapshot` every 10 seconds
- Shows each bot as a position on a line: entry → current → target → stop
- Supports bot_type filter: all/normal/scalper
- Renders as HTML table rows with progress bars — NO actual radar/chart visualization
- Despite being called "Bot Radar" it is a table, not a radar chart

**CoinStatsPanel:**
- Uses `process.env.REACT_APP_API_URL || ''` for API base (not `apiClient`) — raw `fetch()` calls
- Tabs: News, Markets
- Polls `/api/coinstats/status` every 60 seconds
- Only loads news/markets if `status.configured === true`
- Uses `${API}/api/coinstats/news` — note the double `/api/` risk if `REACT_APP_API_URL` ends with `/api`

**HuggingFacePanel:**
- Same pattern as CoinStatsPanel — raw `fetch()`, same double-API path risk
- Calls `${API}/api/huggingface/status`, `/api/huggingface/test`
- If `REACT_APP_API_URL = 'https://example.com/api'`, the URL becomes `https://example.com/api/api/huggingface/status` — broken

**What is missing:**
- `MetricsWithTabsSection` has `DecisionTrace`, `WhaleFlowHeatmap`, `PrometheusMetrics` tabs but none of these components perform well if their respective backends are unavailable — they show spinners indefinitely or silent empty states
- `ProfitsSection` receives `renderMetricsWithTabs` as a **function prop** from Dashboard.js — this is an anti-pattern. The MetricsWithTabsSection should be imported directly

---

### 7.7 Live Trades Section
**File:** `pages/dashboard/sections/LiveTradesSection.js` (152 lines)  
**Nav:** 📡 Live Trades  
**Rendered:** YES

**Contains:**
- 3 filter dropdowns: exchange, bot, pair (derived from `recentTrades`)
- Trade list (capped at 40 items from `recentTrades.slice(0, 40)`)
- Trade detail panel (shows selected trade data)
- Empty state if no trades

**Data source:** `recentTrades` from `useDashboardState` — loaded via `GET /api/trades/recent?limit=50` and updated via WebSocket `trade_executed` events

**What is correct:** Filtering is reactive and efficient

**What is broken:**
- Shows last 40 of the fetched 50 trades — the `slice(0, 40)` cap is arbitrary and doesn't explain to the user why some trades may not appear
- No pagination or "load more" — after 50 trades the user cannot see older history
- Trade detail panel renders raw field names that may not be user-friendly (e.g., `symbol` shown as `trade.symbol`, `type` as `trade.type`)

---

### 7.8 Countdown Section
**File:** `pages/dashboard/sections/CountdownSection.js` (496 lines)  
**Nav:** ⏱️ Countdown  
**Rendered:** YES

**Contains:**
- "Road to R1,000,000" progress ring/bar
- Progress stats: Current Equity, Goal (R1M), Remaining, Days Remaining, Required Daily Rate
- Milestone tracker (R30K, R100K, R250K, R500K, R1M)
- Current mode badge (Paper/Live)
- Custom countdowns panel: list of user-defined countdown goals with add/delete
- Add Countdown form (label + target amount)

**Data:** `countdown` from `useDashboardState` (loaded from `/api/analytics/countdown-to-million`), `customCountdowns` from `/api/countdowns`

**What is correct:** The milestone tracker and progress ring are visually excellent

**What is broken:**
- Progress uses `countdownData.progress_pct` — if backend returns `null`, the progress ring shows 0% with no explanation
- `daysRemaining` calculation uses `if (daysRemaining && daysRemaining < 9999)` — the 9999 sentinel value is undefined anywhere in the frontend and is a magic number

---

### 7.9 Wallet Hub Section
**File:** `pages/dashboard/sections/WalletHubSection.js` (17 lines — wrapper)  
**File (actual content):** `components/WalletHub.js`  
**Nav:** 💰 Wallet Hub  
**Rendered:** YES

**WalletHubSection passes:** `balances`, `systemModes` → derives `isPaperMode` → passes to `WalletHub`

**WalletHub component:**
- Completely self-contained: fetches its own data on mount
- Loads from: `/api/wallet/balances`, `/api/wallet/requirements`, `/api/wallet/funding-plans?status=awaiting_deposit`, `/api/wallet/paper`
- Displays: paper wallet balances table, live wallet balances, requirements, funding plans
- Paper wallet paper deposit form (inject capital in paper mode)
- Listens for realtime `wallet` events via `useLastUpdate('wallet')`

**What is correct:** WalletHub correctly separates paper vs live wallet views

**What is broken:**
- `WalletHub` ignores the `balances` and `systemModes` props passed from `WalletHubSection` — it fetches everything itself. The parent passes `balances` that never get used.
- `WalletTreasurySection.js` (dead) is identical to `WalletHubSection.js` — same component, different title string only.

---

### 7.10 Profile Section
**File:** `pages/dashboard/sections/ProfileSection.js` (100 lines)  
**Nav:** 👤 Profile  
**Rendered:** YES

**Contains:**
- Profile form: First Name, Email, Display Currency, New Password
- Account info grid: Status, Member Since, Total Bots, Active Bots
- Emergency Stop button (red zone)

**API:** Submits profile via `PUT /api/auth/profile`, Emergency Stop via `handleEmergencyStop`

**What is missing:**
- The Emergency Stop modal (`ModalConfirm`) is in Dashboard.js and triggered by `handleEmergencyStop` → sets `showEmergencyConfirm = true`. This works correctly but the user interaction path is: Profile page → click Emergency Stop → confirm modal appears at top level. The modal is not rendered in ProfileSection — it lives in Dashboard.js.

**What is duplicated:**
- `ProfileControlsSection.js` (dead) includes ProfileSection + SystemModeSection + ApiSetupSection all in one mega-wrapper. It would have been the full "Settings" page. It is not used.

---

### 7.11 Hidden Admin Section
**File:** `pages/dashboard/sections/AdminTruthSection.js` (20 lines — wrapper)  
**File (bulk):** `pages/dashboard/sections/AdminPanelSection.js` (1,051 lines)  
**File (truth):** `pages/dashboard/sections/TruthConsoleSection.js` (205 lines)  
**Nav:** 🔧 Admin (hidden unless `showAdmin=true`)  
**Rendered:** YES (conditional on `showAdmin`)

**AdminTruthSection wraps:**
1. `AdminPanelSection` — God Mode admin panel
2. `TruthConsoleSection` — Truth Kernel subsystem status

**AdminPanelSection contains:**
- System health dashboard
- User management (list, block, delete, force logout, email all)
- Bot management (all bots across all users)
- Emergency override per-user
- API key migration
- Admin health check
- Storage stats

**TruthConsoleSection:**
- Fetches `GET /api/admin/truth/summary` via raw `fetch()` (not `apiClient`)
- Lists all subsystems with PASS/FAIL/WARN status
- Expandable per-subsystem details
- Handles `403 Forbidden` gracefully (shows "Admin access required")

**What is broken:**
- `AdminPanelSection` uses `const axios = apiClient` and raw axios calls, plus imports `apiClient` — mixed API client usage
- `showAdmin` is always false until the AI chat "show admin" + password unlock flow. There is no `user.is_admin` nav visibility check — any user who discovers the chat command can attempt to unlock admin.
- `TruthConsoleSection` uses raw `fetch('/api/admin/truth/summary', ...)` — bypasses `apiClient` interceptors and JWT auto-injection via headers prop

---

### 7.12 BotRadarSection (Inside PerformanceSection)
**File:** `pages/dashboard/sections/BotRadarSection.js` (265 lines)  
**Nav:** Inside 💹 Profits & Performance (no own nav item)

**Calls:** `GET /api/radar/snapshot` every 10 seconds  
**Renders:** Table of bot positions with progress bars (NOT a chart)  
**Bot type filter:** all/normal/scalper

**Critical issue:** Despite the name "Bot Radar" suggesting a chart visualization, it renders as a table. The CSS file `styles/radar-exchange.css` defines radar-section styles as a table layout. There is no Recharts, D3, or Chart.js usage here.

---

### 7.13 CoinStatsPanel (Inside PerformanceSection)
**File:** `pages/dashboard/sections/CoinStatsPanel.js` (165 lines)

**Uses raw `fetch()`** with `process.env.REACT_APP_API_URL || ''` as base  
**Risk:** Double `/api/` path if `REACT_APP_API_URL` contains `/api`  
**Tabs:** News (crypto news items), Markets (ticker data)  
**Only loads if** `status.configured === true` (CoinStats key present)

---

### 7.14 HuggingFacePanel (Inside PerformanceSection)
**File:** `pages/dashboard/sections/HuggingFacePanel.js` (201 lines)

**Same raw `fetch()` pattern as CoinStatsPanel**  
**Same double `/api/` risk**  
**Shows:** HuggingFace model status, test button, sentiment output  
**Only active if** HuggingFace API key configured

---

### 7.15 MetricsWithTabsSection (Inside ProfitsSection)
**File:** `pages/dashboard/sections/MetricsWithTabsSection.js` (101 lines)  
**Rendered:** YES — but passed as a `renderMetricsWithTabs` function prop, not directly imported

**Tabs:**
- Decision Trace → `components/DecisionTrace.js` (fetches `/api/advanced/decisions/recent`)
- Whale Flow → `components/WhaleFlowHeatmap.js` (fetches `/api/whale/flow`) — renders a Bar chart
- System Metrics → `components/PrometheusMetrics.js` (fetches `/api/metrics/prometheus`)

**Design inconsistency:** `MetricsWithTabsSection` uses inline `style={{}}` for tab buttons — hand-rolled tab UI instead of the `@/ui` design system components used elsewhere.

---

### 7.16 Dead Sections Summary

The following sections exist in `pages/dashboard/sections/` but are **never imported or rendered** in the current application:

| Section | Lines | Content | What to do |
|---------|-------|---------|------------|
| `HomeSection.js` | 29 | OverviewSection + countdown summary mini-card | Replace `OverviewSection` as landing home |
| `BotOperationsSection.js` | 16 | Wrapper around `BotManagementSection` | Delete — no added value |
| `TradingMonitorSection.js` | 45 | Live Trades + BotRadar + ExchangeStatus | Excellent composite — activate as `NAV.LIVE_TRADES` |
| `ProfileControlsSection.js` | 73 | Profile + SystemMode + ApiSetup | Delete — overcrowded |
| `AiCommandSection.js` | 65 | AiChat + CoinStats + HuggingFace | Partially useful — could be the Welcome section |
| `WalletTreasurySection.js` | 17 | Identical to WalletHubSection | Delete |

---

## 8. Dashboard State / Hook / Data Flow Audit

### Source: `hooks/useDashboardState.js` (3,246 lines)

**useDashboardState is the single mega-hook** for the entire dashboard. It owns:
- All API state (`bots`, `metrics`, `balances`, `systemModes`, `overviewData`, `recentTrades`, `countdown`, etc.)
- All action handlers (`handleCreateBot`, `handleDeleteBot`, `handlePaperReset`, `handleSendMessage`, etc.)
- WebSocket management (`wsRef`, `sseRef`, `setupRealTimeConnections`)
- All intervals (`setInterval` for live prices, bot eligibility, projection, etc.)
- Admin state (`showAdmin`, `adminAction`, `allUsers`, `adminBots`)

**Second hook:** `hooks/useDashboardData.js` (separate file) — defines `useDashboardData`, `getBotStatus`, and `normalizeLivePrices`. BUT:
- `useDashboardData` is NOT used in `Dashboard.js` — only in `BotManagementSection.js` where `getBotStatus` is imported
- The hook duplicates much of what `useDashboardState` does (users, bots, metrics, systemModes)
- It represents an earlier version of the dashboard state management that was never fully replaced

**Data duplication in state:**
- `metrics` (from `loadMetrics` → `/api/overview/snapshot`) vs `overviewData` (from `loadOverviewData` → `/api/overview/snapshot`) — **both call the same endpoint**. `metrics` is a formatted string object (`totalProfit: 'R123.45'`), `overviewData` is raw numbers. Both are derived from the same backend call but the hook calls the endpoint twice.
- `balances` (from `loadWalletBalances` → `/api/wallet/balances`) vs `WalletHub` component loading its own `/api/wallet/balances` — **same endpoint loaded twice** when WalletHub section is active.
- `systemModes` (loaded via `loadSystemModes`) vs `WalletHubSection` receiving `systemModes` as prop but `WalletHub` internally calling `/api/wallet/paper` independently

**Polling intervals active simultaneously:**
| Interval | Period | Endpoint(s) |
|----------|--------|-------------|
| Live prices | 4–5 seconds | `/api/prices/live` |
| Overview + risk | 10 seconds | `/api/overview/snapshot`, `/api/risk/status` |
| Realtime status check | 10 seconds | `/api/diagnostics/realtime` |
| Projection calculation | 60 seconds | (local computation) |
| Bot eligibility check | 5 minutes | `/api/bots/eligible-for-promotion` |

Plus WebSocket connection (primary) with 5-second reconnect delays (max 5 attempts), and SSE is disabled (comment says "Only use WebSocket (SSE disabled due to auth issues)").

**Front-end state drift risks:**
1. `metrics.totalProfit` (string, from `loadMetrics`) and `overviewData.total_profit` (number, from `loadOverviewData`) can diverge if one endpoint call succeeds and the other fails
2. After paper reset: `POST /api/system/paper-reset` → `refreshAllDashboardData()` fires immediately, but collections are still being deleted on the backend — the refresh may capture partially-cleared data
3. WebSocket `overview_update` and `overview_updated` are two separate event types that BOTH update `metrics` and `overviewData` with slightly different field names (`portfolio_value` vs `total_profit`)

---

## 9. Frontend Realtime / Sync Audit

### Source: `hooks/useDashboardState.js` + `lib/realtime.js` + `hooks/useRealtime.js`

**Two parallel realtime systems exist:**

| System | File | Used by |
|--------|------|---------|
| Direct WebSocket in useDashboardState | `wsRef.current = new WebSocket(...)` in `setupRealTimeConnections()` | Main dashboard state |
| `RealtimeClient` class | `lib/realtime.js` | `WalletHub`, `DecisionTrace`, `WhaleFlowHeatmap`, `APIKeySettings` via hooks |

**Both systems connect to the same WebSocket endpoint** (`/api/ws?token=...`). The dashboard therefore establishes **TWO separate WebSocket connections** to the same server simultaneously. This means:
- Double message processing for the same backend events
- Both connections attempt reconnect independently on disconnect
- `lib/realtime.js` has its own reconnect (up to `maxReconnectAttempts = 5`, exponential backoff) AND `useDashboardState` has its own reconnect (5 attempts, fixed 5-second delay)

**SSE is disabled:** The comment in `useDashboardState` reads "Only use WebSocket (SSE disabled due to auth issues)". The `sseRef` is allocated but never connected. SSE-related connection status (`sse: 'Connected'`) is reported based on WebSocket status, not actual SSE.

**Reconnect behavior:**
- When WS disconnects, `useDashboardState` attempts reconnect up to 5 times at 5-second intervals
- After 5 failures: `console.log('❌ Max reconnect attempts reached')` — NO alert to user, NO badge update, NO fallback
- The realtime badge in the topbar will show "WS Disconnected" based on `connectionStatus.ws` but won't trigger any user-facing alert after max reconnects

**WebSocket events handled in `handleRealTimeUpdate`:**
`connection`, `ping`, `metrics`, `bot_status`, `balance`, `live_prices`, `prices_update`, `overview_update`, `bots_update`, `trades_update`, `notification`, `chat_response`, `trade_executed`, `profit_update`, `overview_updated`, `bot_status_changed`, `system_mode_update`, `bot_created`, `bot_updated`, `bot_paused`, `bot_resumed`, `bot_deleted`, `bot_promoted`, `api_key_update`, `paper_reset`, `force_refresh`

**Auth expiry behavior (CRITICAL GAP from previous audit):**
- `apiClient.js` fires `window.dispatchEvent(new CustomEvent('auth:unauthorized'))` on 401
- **No component listens for this event**
- Background polling every 4–10 seconds will silently get 401s after token expiry
- Only inline `if (err.response?.status === 401) navigate('/login')` in `useDashboardState` at line 1158 handles it for specific calls
- General polling (`loadLivePrices`, `loadOverviewData`, etc.) does NOT check for 401 and will silently fail

---

## 10. Frontend Auth / API Client Audit

### Source: `lib/apiClient.js`, `lib/api.js`

**apiClient.js:** Axios instance with:
- Base URL: `API_BASE` from `lib/api.js` (defaults to `/api`)
- 30-second timeout
- JWT auto-injection on every request via request interceptor
- Retry logic: 3 retries on timeout, network error, 408, 429, 500-504 (exponential backoff)
- 401 handler: logs, dispatches `auth:unauthorized` event (unhandled), does NOT redirect
- Error normalization: `notifyError()` helper that calls `toast.error()`

**API URL system:** `lib/api.js` builds `API_BASE`:
- If `REACT_APP_API_BASE` or `REACT_APP_API_URL` ends with `/api` → use as-is
- If it's origin only → append `/api`
- Default → `/api` (relative, correct for nginx proxy)

**CoinStats/HuggingFace panels bypass apiClient entirely.** They use raw `fetch()` with:
```js
const API = process.env.REACT_APP_API_URL || '';
fetch(`${API}/api/coinstats/status`, { headers })
```
If `REACT_APP_API_URL = 'https://amarktai.online/api'`, the URL becomes `https://amarktai.online/api/api/coinstats/status` — **double `/api/` bug** in production.

**Mixed API client usage in sections:**
| Component | API client used |
|-----------|----------------|
| Most sections | `apiClient` via `get()`, `post()` wrappers |
| `ScalperBotsPanel` | raw `fetch()` |
| `BotRadarSection` | raw `fetch()` |
| `ExchangeStatusSection` | raw `fetch()` |
| `TruthConsoleSection` | raw `fetch()` |
| `CoinStatsPanel` | raw `fetch()` with wrong base URL |
| `HuggingFacePanel` | raw `fetch()` with wrong base URL |
| `WalletHub` | `apiClient` via `get()`, `post()` — correct |
| `AdminPanelSection` | `apiClient` aliased as `axios` |

**Authentication for admin panel:** `showAdmin` is hidden by default. The unlock flow requires:
1. User types "show admin" in chat
2. System asks for password
3. User types admin password
4. `POST /api/admin/unlock` is called with `{ password: userInput }`
5. On success: `setShowAdmin(true)`, auto-navigates to Admin section, auto-hides after 1 hour

This is a valid security mechanism but relies entirely on a non-obvious UI flow. Any user who finds the chat command gains access to the admin unlock attempt interface.

---

## 11. Dead / Duplicate / Legacy Frontend Audit

### Dead pages (implemented but not routed in `App.js`):
| File | Content | Status |
|------|---------|--------|
| `pages/About.js` | Uses `PublicPageLayout` | Not routed — unreachable |
| `pages/Features.js` | Uses `PublicPageLayout` | Not routed — unreachable |
| `pages/Privacy.js` | Uses `PublicPageLayout` | Not routed — unreachable |
| `pages/Terms.js` | Uses `PublicPageLayout` | Not routed — unreachable |

### Dead components (defined, exported, never imported in active render tree):
| File | Content | Status |
|------|---------|--------|
| `components/AIChatPanel.js` | 526-line standalone AI chat | Dead — replaced by `AiChatSection.js` |
| `components/ComparisonGraphs.js` | Profit/ROI/trades chart | Dead — superseded by `ProfitsSection.js` |
| `components/WalletOverview.js` | Simple wallet display | Dead — replaced by `WalletHub.js` |
| `components/AdminApproval.js` | User approval UI | Dead |
| `components/PlatformPanel.js` | Exchange tiles | Dead |
| `components/Dashboard/LivePricesTicker.js` | Price ticker row | Dead — tickers live in `OverviewSection` |
| `components/Dashboard/MetricsOverview.js` | Metrics card grid | Dead — replaced by `OverviewSection` |
| `components/Dashboard/BotQuarantineSection.js` | Quarantine list | Dead — replaced by `TrainingQuarantineSection` |
| `components/Dashboard/BotTrainingSection.js` | Training list | Dead — replaced by `TrainingQuarantineSection` |
| `components/Dashboard/SystemModesSection.js` | Mode toggles | Dead — replaced by `SystemModeSection.js` |
| `components/Dashboard/CreateBotSection.js` | Bot creation form | Dead — form is in `BotManagementSection.js` |
| `hooks/useDashboardData.js` | Old data hook | Partially dead — only `getBotStatus` and `normalizeLivePrices` are used |
| `components/VersionBadge.js` | Version display | Dead |
| `components/PublicNav.js` | Public site nav | Dead (used by `PublicPageLayout` which is used only by unrouted pages) |

### Duplicate CSS definition conflict:
| Problem | Files |
|---------|-------|
| Two `:root` color systems | `styles/theme.css` (blue gradient, used first) and `DashboardV3.css` (flat black, wins) |
| `StepDots` component | Defined identically in `Login.js` and `Register.js` |
| Wordmark rendering | Inline span in `Landing.js`, `Login.css`/`Register.css` vs `Brand.js` in Dashboard |

---

## 12. Final Frontend Blocker List

### CRITICAL

| # | Blocker | Files | Why it matters |
|---|---------|-------|----------------|
| C1 | **Mobile nav is non-functional** — only "Overview" and "Logout" on mobile | `Dashboard.js` mobile-topbar | Mobile users cannot access 9 of 11 nav sections |
| C2 | **auth:unauthorized event dispatched but unhandled** — token expiry silently freezes dashboard | `lib/apiClient.js`, `hooks/useDashboardState.js` | After JWT expires, background polls continue firing 401s; user never redirected to login |
| C3 | **Double WebSocket connections** — both `useDashboardState` WS and `realtimeClient` from `lib/realtime.js` connect simultaneously | `hooks/useDashboardState.js`, `lib/realtime.js` | Server sees 2 connections per user; events processed twice |
| C4 | **CoinStatsPanel and HuggingFacePanel use wrong API base** — `REACT_APP_API_URL || ''` creates `/api/api/` double path in production | `sections/CoinStatsPanel.js`, `sections/HuggingFacePanel.js` | Both panels broken in production if `REACT_APP_API_URL` contains `/api` |

### HIGH

| # | Blocker | Files | Why it matters |
|---|---------|-------|----------------|
| H1 | **Overview section has no nav link** — only accessible via logo click | `Dashboard.js`, `dashboardNav.js` | Users don't know to click logo for the health dashboard |
| H2 | **15 section files are dead or unreachable** — represents ~3,000 lines of code that could mislead maintenance | 15 files in `sections/` | Code drift, maintenance confusion, wasted implementation |
| H3 | **`renderAdmin()` and `renderProfile()` dead render functions** | `Dashboard.js` lines 272–396 | Dead code in main dashboard file |
| H4 | **BotRadarSection uses raw `fetch()`** bypassing JWT retry/auth logic | `sections/BotRadarSection.js` | Radar silently fails on 401 or network errors |
| H5 | **`TruthConsoleSection` uses raw `fetch()`** bypassing apiClient | `sections/TruthConsoleSection.js` | Admin truth panel silently fails on 401 |
| H6 | **`ScalperBotsPanel` uses raw `fetch()`** | `sections/ScalperBotsPanel.js` | Scalper panel breaks on token expiry |
| H7 | **Two `:root` CSS blocks conflict** — `DashboardV3.css` silently overrides `theme.css` | `DashboardV3.css`, `styles/theme.css` | `theme.css` changes have no effect on dashboard |
| H8 | **`metrics` and `overviewData` both fetch from `/api/overview/snapshot`** — same endpoint called twice | `hooks/useDashboardState.js` | Double backend calls on every 10s poll cycle |
| H9 | **`renderMetricsWithTabs` passed as function prop** — anti-pattern | `Dashboard.js`, `sections/ProfitsSection.js`, `sections/PerformanceSection.js` | Unnecessary re-render risk; breaks component independence |
| H10 | **SSE reported as "Connected" based on WS status** — SSE is disabled | `hooks/useDashboardState.js` lines 779–781 | `connectionStatus.sse` badge is misleading |

### MEDIUM

| # | Blocker | Files | Why it matters |
|---|---------|-------|----------------|
| M1 | **`StepDots` component duplicated** in Login and Register | `pages/Login.js`, `pages/Register.js` | Code duplication, inconsistency risk |
| M2 | **`WalletHub` ignores `balances` prop** from parent | `sections/WalletHubSection.js`, `components/WalletHub.js` | Prop interface misleads; parent data never used |
| M3 | **4 public pages (About, Features, Privacy, Terms) not routed** | `App.js` | Pages implemented but inaccessible; dead code risk |
| M4 | **`api-setup-split` and `api-setup-panel` CSS classes undefined** | `sections/ApiSetupSection.js` | Potential layout regression |
| M5 | **Bot Management uses string literals instead of BOT_TAB constants** | `sections/BotManagementSection.js` | Constants drift silently |
| M6 | **`WalletTreasurySection.js` is identical to `WalletHubSection.js`** | Both wallet section files | Dead duplicate |

### LOW

| # | Blocker | Files | Why it matters |
|---|---------|-------|----------------|
| L1 | **`showAnalytics` state in AiChatSection** — set but never used | `sections/AiChatSection.js` | Dead state |
| L2 | **`paperResetChecking` and `paperResetValid` props unused** in `SystemModeSection` | `sections/SystemModeSection.js` | Prop interface misleading |
| L3 | **BotRadarSection is a table, not a chart** | `sections/BotRadarSection.js` | Name misleads; missing actual visualization |
| L4 | **MetricsWithTabsSection uses inline styles** not `@/ui` design system | `sections/MetricsWithTabsSection.js` | Visual inconsistency |
| L5 | **Multiple `humanizeReason()` utility functions** defined in OverviewSection and BotManagementSection | Both files | Should be a shared utility |

---

## 13. Recommended Final Frontend Structure

### Final page structure:
```
/ → Landing
/login → Login (2-step)
/register → Register (4-step)
/dashboard → Dashboard (authenticated)
/about → About (add to App.js)
/features → Features (add to App.js)
/privacy → Privacy (add to App.js)
/terms → Terms (add to App.js)
* → redirect /
```

### Final dashboard shell:
```
<div class="app">
  <aside class="sidebar">           ← Desktop
    <Brand /> (or logo)             ← Click = OVERVIEW / HOME
    <nav>...</nav>
  </aside>
  <header class="topbar">          ← Desktop
    <Brand />
    <StatusBadges />               ← Mode, Realtime, Risk
    <Logout />
  </header>
  <MobileHeader />                  ← Mobile: hamburger + logo + logout
  <MobileDrawerNav />               ← Mobile: full nav in slide-in drawer
  <main class="main">
    {sections}
  </main>
  <SiteFooter />
</div>
```

### Final nav structure (10 items + hidden admin):
```
NAV.HOME (Overview + Countdown mini)   ← logo click AND nav item
NAV.WELCOME (AI Chat)
NAV.API_SETUP
NAV.BOT_MANAGEMENT
NAV.SYSTEM_MODE
NAV.PROFITS_PERFORMANCE (Performance + Radar + Market Intelligence)
NAV.LIVE_TRADES (Live Trades + Exchange Status)
NAV.COUNTDOWN
NAV.WALLET_HUB
NAV.PROFILE
NAV.HIDDEN_ADMIN (chat-unlock only)
```

### Final section placement:
| Nav Item | Renders |
|----------|---------|
| HOME | `HomeSection` (OverviewSection + countdown bar) |
| AI Chat | `WelcomeSection` → directly render `AiChatSection` |
| API Setup | `ApiSetupSection` → `APIKeySettings` |
| Bot Management | `BotManagementSection` (bots + scalper tab + training tab + spawn tab) |
| System Mode | `SystemModeSection` |
| Profits & Performance | `PerformanceSection` (ProfitsSection + BotRadar + CoinStats + HuggingFace) |
| Live Trades | `TradingMonitorSection` (LiveTrades + BotRadar + Exchange Status) |
| Countdown | `CountdownSection` |
| Wallet Hub | `WalletHubSection` |
| Profile | `ProfileSection` |
| Admin | `AdminTruthSection` (AdminPanel + TruthConsole) |

**Note:** BotRadarSection currently appears in BOTH PerformanceSection and TradingMonitorSection. In the final pass, choose one location — recommend: Live Trades section alongside ExchangeStatusSection.

### Final branding rules:
1. `Brand.js` is the canonical "AmarktAI" text renderer — all instances must use it
2. `AI` = blue `#3B82F6`, bold weight 800
3. Landing page wordmark must be refactored to use `Brand.js` or a consistent class
4. `SiteFooter.js` correctly uses inline span — acceptable as-is
5. `DashboardV3.css` is the canonical CSS for dashboard color tokens — `theme.css` should either be updated to match or removed and its unique vars (only `--panel`, `--panelBorder`, `--bg` gradient) consolidated into `DashboardV3.css`

---

## 14. Final Frontend Repo Update Scope

This section lists exactly what the final frontend pass must do:

### Files to change:

**`App.js`**
- Add routes for `/about`, `/features`, `/privacy`, `/terms`
- Add `auth:unauthorized` event listener that calls `navigate('/login')`

**`hooks/useDashboardState.js`**
- Remove duplicate `loadOverviewData` + `loadMetrics` calls to the same endpoint
- Consolidate into one unified `loadDashboardSnapshot` function
- Fix 401 handling in all polling `setInterval` callbacks
- Remove dead `renderAdmin()` and `renderProfile()` functions (they're in Dashboard.js, not here — add note)

**`pages/Dashboard.js`**
- Remove dead `renderAdmin()`, `renderProfile()`, `renderMetricsWithTabs()`, `renderWelcome()`, etc. render functions that are not called
- Pass `renderMetricsWithTabs` properly (remove the function-prop anti-pattern — import MetricsWithTabsSection directly in PerformanceSection)
- Add mobile drawer/hamburger navigation
- Add `NAV.HOME` or make Overview a proper nav item (not just logo click)

**`constants/dashboardNav.js`**
- Add `NAV.HOME` (or rename `NAV.OVERVIEW` to make it nav-accessible)
- Update `NAV_LABELS` accordingly

**`pages/dashboard/sections/PerformanceSection.js`**
- Import `MetricsWithTabsSection` directly instead of receiving it as `renderMetricsWithTabs` prop

**`pages/dashboard/sections/CoinStatsPanel.js` and `HuggingFacePanel.js`**
- Replace `process.env.REACT_APP_API_URL || ''` with `import { API_BASE } from '../../../lib/api'`
- Use `apiClient` / `get()` helper instead of raw `fetch()`

**`pages/dashboard/sections/BotRadarSection.js`**
- Replace raw `fetch()` with `import { get } from '../../../lib/apiClient'`

**`pages/dashboard/sections/ScalperBotsPanel.js`**
- Replace raw `fetch()` with `import { get } from '../../../lib/apiClient'`

**`pages/dashboard/sections/ExchangeStatusSection.js`**
- Replace raw `fetch()` with `import { get } from '../../../lib/apiClient'`

**`pages/dashboard/sections/TruthConsoleSection.js`**
- Replace raw `fetch()` with `import { get } from '../../../lib/apiClient'`

**`pages/dashboard/sections/WelcomeSection.js`**
- Remove unnecessary wrapper — move `SectionHeader` into `AiChatSection.js` directly
- Remove `WelcomeSection.js`

**`pages/dashboard/sections/AiChatSection.js`**
- Remove dead `showAnalytics` state and button

**`pages/dashboard/sections/BotManagementSection.js`**
- Replace string literal tab values with `BOT_TAB` constants

**`pages/Dashboard.js` or create `lib/formatUtils.js`**
- Consolidate duplicate `humanizeReason()`, `safeToFixed()`, `formatZAR()`, `safeNumber()` utilities that appear in 6+ files

### Files to delete:
- `components/AIChatPanel.js` (dead — replaced by AiChatSection)
- `components/ComparisonGraphs.js` (dead — replaced by ProfitsSection charts)
- `components/WalletOverview.js` (dead)
- `components/AdminApproval.js` (dead)
- `components/PlatformPanel.js` (dead)
- `components/Dashboard/LivePricesTicker.js` (dead)
- `components/Dashboard/MetricsOverview.js` (dead)
- `components/Dashboard/BotQuarantineSection.js` (dead)
- `components/Dashboard/BotTrainingSection.js` (dead)
- `components/Dashboard/SystemModesSection.js` (dead)
- `components/Dashboard/CreateBotSection.js` (dead)
- `pages/dashboard/sections/WalletTreasurySection.js` (duplicate of WalletHubSection)
- `pages/dashboard/sections/BotOperationsSection.js` (no added value)
- `pages/dashboard/sections/ProfileControlsSection.js` (overcrowded, unused)
- `pages/dashboard/sections/HomeSection.js` (move its logic into OverviewSection directly)
- `pages/dashboard/sections/AiCommandSection.js` (dead composite)
- `hooks/useDashboardData.js` (partially dead — keep only `getBotStatus` and `normalizeLivePrices` as utils in `lib/`)

### Files to keep as-is:
- `components/APIKeySettings.js` — self-contained, correct
- `components/WalletHub.js` — self-contained, correct
- `components/Brand.js` — canonical
- `components/SiteFooter.js` — correct
- `components/ErrorBoundary.js` — correct
- `components/NeuralBackground.js` — correct
- `components/DecisionTrace.js` — good, keep
- `components/WhaleFlowHeatmap.js` — good, keep
- `components/PrometheusMetrics.js` — good, keep
- `lib/apiClient.js` — correct, but add 401→login redirect
- `lib/api.js` — correct
- `lib/realtime.js` — keep but deconflict with useDashboardState WS
- `hooks/useRealtime.js` — keep
- All sections actively rendered (`ApiSetupSection`, `BotManagementSection`, `CountdownSection`, `LiveTradesSection`, `OverviewSection`, `ProfileSection`, `SystemModeSection`, `WalletHubSection`, `AdminPanelSection`, `AdminTruthSection`, `TruthConsoleSection`, `ScalperBotsPanel`, `BotRadarSection`, `ExchangeStatusSection`, `MetricsWithTabsSection`, `ProfitsSection`, `CoinStatsPanel`, `HuggingFacePanel`)

### CSS to standardize:
- Remove `:root` from `styles/theme.css` OR remove `:root` from `DashboardV3.css` — keep only one canonical token definition
- Recommended: keep `DashboardV3.css` as canonical (it's the one that actually applies), add any unique vars from `theme.css` into it, delete the conflicting block from `theme.css`
- Define `.api-setup-split` and `.api-setup-panel` CSS classes

### Auth/Realtime sync fixes required:
1. Add `window.addEventListener('auth:unauthorized', () => window.location.href = '/login')` in `App.js` or `apiClient.js`
2. Deconflict dual WebSocket: either use only `useDashboardState` WS OR only `realtimeClient`, not both
3. Fix SSE badge to reflect actual SSE state (or remove SSE badge since SSE is disabled)
4. Add mobile drawer nav in Dashboard.js

---

*End of Frontend Audit Report.*  
*This report is complete and sufficient for planning one final frontend repo update pass.*
