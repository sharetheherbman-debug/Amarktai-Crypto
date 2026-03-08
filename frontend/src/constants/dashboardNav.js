export const NAV = {
  OVERVIEW: 'overview',            // logo click only — not in nav
  WELCOME: 'welcome',              // AI chat page
  API_SETUP: 'api-setup',
  BOT_MANAGEMENT: 'bot-management',
  BOT_FLEET: 'bot-fleet',          // monitor + control only
  BOT_RADAR: 'bot-radar',          // standalone visual target-tracking section
  GROWTH_ENGINE: 'growth-engine',  // autopilot growth + reinvest engine
  SYSTEM_MODE: 'system-mode',
  ANALYTICS_METRICS: 'analytics-metrics', // intelligence terminal: decision trace, whale flow, market intelligence, AI analysis
  PROFITS_PERFORMANCE: 'profits-performance',
  LIVE_TRADES: 'live-trades',
  COUNTDOWN: 'countdown',
  WALLET_HUB: 'wallet-hub',
  PROFILE: 'profile',
  HIDDEN_ADMIN: 'hidden-admin',
};

export const NAV_LABELS = {
  [NAV.WELCOME]: '🤖 Welcome',
  [NAV.API_SETUP]: '🔑 API Setup',
  [NAV.BOT_MANAGEMENT]: '⚙️ Bot Management',
  [NAV.BOT_FLEET]: '🚀 Bot Fleet',
  [NAV.BOT_RADAR]: '📡 Bot Radar',
  [NAV.GROWTH_ENGINE]: '🌱 Growth Engine',
  [NAV.SYSTEM_MODE]: '🎛️ System Mode',
  [NAV.ANALYTICS_METRICS]: '📊 Analytics & Metrics',
  [NAV.PROFITS_PERFORMANCE]: '💹 Profits & Performance',
  [NAV.LIVE_TRADES]: '📡 Live Trades',
  [NAV.COUNTDOWN]: '⏱️ Countdown',
  [NAV.WALLET_HUB]: '💰 Wallet Hub',
  [NAV.PROFILE]: '👤 Profile',
  [NAV.HIDDEN_ADMIN]: '🔧 Admin',
};

export const BOT_TAB = {
  CREATE: 'create',
  NORMAL_BOTS: 'normal-bots',
  SCALPER_BOTS: 'scalper-bots',
  TRAINING_QUARANTINE: 'training-quarantine',
  SPAWN_STATUS: 'spawn-status',
};

export const PERF_TAB = {
  PROFITS: 'profits',
  METRICS: 'metrics',
};
