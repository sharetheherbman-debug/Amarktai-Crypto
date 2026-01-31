/**
 * Platform Constants - Single Source of Truth
 * Defines the 7 supported exchanges + 3 AI providers for the entire system
 */

// Supported exchanges (in display order) - EXACTLY 7 EXCHANGES
export const SUPPORTED_PLATFORMS = ['luno', 'binance', 'kucoin', 'bybit', 'kraken', 'bitget', 'gate'];

// Supported AI providers - EXACTLY 3 PROVIDERS
export const SUPPORTED_AI_PROVIDERS = ['openai', 'flokx', 'fetchai'];

// All supported providers (exchanges + AI)
export const ALL_PROVIDERS = [...SUPPORTED_PLATFORMS, ...SUPPORTED_AI_PROVIDERS];

// Platform display configuration
export const PLATFORM_CONFIG = {
  luno: {
    id: 'luno',
    name: 'Luno',
    displayName: 'Luno',
    icon: '🇿🇦',
    color: '#3861FB',
    maxBots: 5,
    region: 'ZA',
    requiresPassphrase: false,
    enabled: true,
    supportsPaper: true,  // Can run paper trading without keys
    supportsLive: true,   // Can run live trading with keys
    requiredKeyFields: ['api_key', 'api_secret']  // Required credentials
  },
  binance: {
    id: 'binance',
    name: 'Binance',
    displayName: 'Binance',
    icon: '🟡',
    color: '#F3BA2F',
    maxBots: 10,
    region: 'Global',
    requiresPassphrase: false,
    enabled: true,
    supportsPaper: true,
    supportsLive: true,
    requiredKeyFields: ['api_key', 'api_secret']
  },
  kucoin: {
    id: 'kucoin',
    name: 'KuCoin',
    displayName: 'KuCoin',
    icon: '🟢',
    color: '#23AF91',
    maxBots: 10,
    region: 'Global',
    requiresPassphrase: true,  // KuCoin requires passphrase
    enabled: true,
    supportsPaper: true,
    supportsLive: true,
    requiredKeyFields: ['api_key', 'api_secret', 'passphrase']  // KuCoin needs passphrase
  },
  bybit: {
    id: 'bybit',
    name: 'Bybit',
    displayName: 'Bybit',
    icon: '🟠',
    color: '#F7A600',
    maxBots: 10,
    region: 'Global',
    requiresPassphrase: false,
    enabled: true,
    supportsPaper: true,
    supportsLive: true,
    requiredKeyFields: ['api_key', 'api_secret']
  },
  bitget: {
    id: 'bitget',
    name: 'Bitget',
    displayName: 'Bitget',
    icon: '🔵',
    color: '#00F0FF',
    maxBots: 10,
    region: 'Global',
    requiresPassphrase: true,  // Bitget requires passphrase
    enabled: true,
    supportsPaper: true,
    supportsLive: true,
    requiredKeyFields: ['api_key', 'api_secret', 'passphrase']  // Bitget needs passphrase
  },
  kraken: {
    id: 'kraken',
    name: 'Kraken',
    displayName: 'Kraken',
    icon: '🟣',
    color: '#5741D9',
    maxBots: 10,
    region: 'Global',
    requiresPassphrase: false,
    enabled: true,
    supportsPaper: true,
    supportsLive: true,
    requiredKeyFields: ['api_key', 'api_secret']
  },
  gate: {
    id: 'gate',
    name: 'Gate.io',
    displayName: 'Gate.io',
    icon: '⚪',
    color: '#17E6A1',
    maxBots: 10,
    region: 'Global',
    requiresPassphrase: false,
    enabled: true,
    supportsPaper: true,
    supportsLive: true,
    requiredKeyFields: ['api_key', 'api_secret']
  },
  // AI Providers
  openai: {
    id: 'openai',
    name: 'OpenAI',
    displayName: 'OpenAI',
    icon: '🤖',
    color: '#10A37F',
    type: 'ai_provider',
    enabled: true,
    requiredKeyFields: ['api_key']
  },
  flokx: {
    id: 'flokx',
    name: 'FlokX',
    displayName: 'FlokX AI',
    icon: '🧠',
    color: '#6366F1',
    type: 'ai_provider',
    enabled: true,
    requiredKeyFields: ['api_key']
  },
  fetchai: {
    id: 'fetchai',
    name: 'Fetch.ai',
    displayName: 'Fetch.ai',
    icon: '🔮',
    color: '#3B82F6',
    type: 'ai_provider',
    enabled: true,
    requiredKeyFields: ['api_key']
  }
};

// Total bot capacity
export const TOTAL_BOT_CAPACITY = Object.values(PLATFORM_CONFIG).reduce((sum, p) => sum + p.maxBots, 0);  // 65

/**
 * Get configuration for a specific platform
 */
export function getPlatformConfig(platformId) {
  return PLATFORM_CONFIG[platformId?.toLowerCase()] || null;
}

/**
 * Check if platform ID is valid (exchange or AI provider)
 */
export function isValidPlatform(platformId) {
  return ALL_PROVIDERS.includes(platformId?.toLowerCase());
}

/**
 * Check if provider is an AI provider
 */
export function isAIProvider(providerId) {
  return SUPPORTED_AI_PROVIDERS.includes(providerId?.toLowerCase());
}

/**
 * Get list of enabled platforms
 */
export function getEnabledPlatforms() {
  return SUPPORTED_PLATFORMS.filter(p => PLATFORM_CONFIG[p].enabled);
}

/**
 * Get display name for platform
 */
export function getPlatformDisplayName(platformId) {
  const config = getPlatformConfig(platformId);
  return config?.displayName || platformId?.toUpperCase() || 'Unknown';
}

/**
 * Get max bots allowed for platform
 */
export function getMaxBots(platformId) {
  const config = getPlatformConfig(platformId);
  return config?.maxBots || 0;
}

/**
 * Get platform icon
 */
export function getPlatformIcon(platformId) {
  const config = getPlatformConfig(platformId);
  return config?.icon || '🔷';
}

/**
 * Get platform color
 */
export function getPlatformColor(platformId) {
  const config = getPlatformConfig(platformId);
  return config?.color || '#999999';
}

/**
 * Get platform options for dropdowns
 */
export function getPlatformOptions() {
  return SUPPORTED_PLATFORMS.map(id => {
    const config = PLATFORM_CONFIG[id];
    return {
      value: id,
      label: `${config.icon} ${config.displayName} (Max ${config.maxBots} bots)`,
      ...config
    };
  });
}

export default {
  SUPPORTED_PLATFORMS,
  SUPPORTED_AI_PROVIDERS,
  ALL_PROVIDERS,
  PLATFORM_CONFIG,
  TOTAL_BOT_CAPACITY,
  getPlatformConfig,
  isValidPlatform,
  isAIProvider,
  getEnabledPlatforms,
  getPlatformDisplayName,
  getMaxBots,
  getPlatformIcon,
  getPlatformColor,
  getPlatformOptions
};
