/**
 * Platform Constants - Single Source of Truth
 * Defines supported exchanges, AI providers, market data providers, and enrichers.
 *
 * Provider hierarchy:
 *   Exchanges:        luno, binance, kucoin, bybit, kraken, bitget, gate
 *   AI Providers:     openai, huggingface, fetchai
 *   Market Data:      cryptocompare (PRIMARY), coingecko (SECONDARY), coinranking (TERTIARY)
 *   Enrichers:        glassnode, etherscan, whale_alert, lunarcrush, cryptopanic
 *   Legacy fallback:  coinstats (deprecated — hidden by default, fallback-only)
 */

// ─── Exchanges ──────────────────────────────────────────────────────────────

export const SUPPORTED_PLATFORMS = ['luno', 'binance', 'kucoin', 'bybit', 'kraken', 'bitget', 'gate'];

// ─── AI Providers (canonical) ───────────────────────────────────────────────

export const SUPPORTED_AI_PROVIDERS = ['openai', 'huggingface', 'fetchai'];

// ─── Market Data Providers (canonical, ordered by priority) ─────────────────

export const MARKET_DATA_PROVIDERS = ['cryptocompare', 'coingecko', 'coinranking'];

// ─── Intelligence Enrichers (optional, not pricing sources) ─────────────────

export const INTELLIGENCE_ENRICHERS = ['glassnode', 'etherscan', 'whale_alert', 'lunarcrush', 'cryptopanic'];

// ─── Legacy Providers (deprecated, fallback-only) ───────────────────────────

export const LEGACY_PROVIDERS = ['coinstats'];

// ─── Aggregated lists ───────────────────────────────────────────────────────

export const ALL_PROVIDERS = [
  ...SUPPORTED_PLATFORMS,
  ...SUPPORTED_AI_PROVIDERS,
  ...MARKET_DATA_PROVIDERS,
  ...INTELLIGENCE_ENRICHERS,
  ...LEGACY_PROVIDERS,
];

// ─── Provider type enum ─────────────────────────────────────────────────────

export const PROVIDER_TYPES = {
  EXCHANGE: 'exchange',
  AI: 'ai_provider',
  MARKET_DATA: 'market_data',
  ENRICHER: 'enricher',
  LEGACY: 'legacy',
};

// ─── Platform / Provider Configuration ──────────────────────────────────────

export const PLATFORM_CONFIG = {
  // ── Exchanges ────────────────────────────────────────────────────────────
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
    supportsPaper: true,
    supportsLive: true,
    type: PROVIDER_TYPES.EXCHANGE,
    requiredKeyFields: ['api_key', 'api_secret'],
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
    type: PROVIDER_TYPES.EXCHANGE,
    requiredKeyFields: ['api_key', 'api_secret'],
  },
  kucoin: {
    id: 'kucoin',
    name: 'KuCoin',
    displayName: 'KuCoin',
    icon: '🟢',
    color: '#23AF91',
    maxBots: 10,
    region: 'Global',
    requiresPassphrase: true,
    enabled: true,
    supportsPaper: true,
    supportsLive: true,
    type: PROVIDER_TYPES.EXCHANGE,
    requiredKeyFields: ['api_key', 'api_secret', 'passphrase'],
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
    type: PROVIDER_TYPES.EXCHANGE,
    requiredKeyFields: ['api_key', 'api_secret'],
  },
  bitget: {
    id: 'bitget',
    name: 'Bitget',
    displayName: 'Bitget',
    icon: '🔵',
    color: '#00F0FF',
    maxBots: 10,
    region: 'Global',
    requiresPassphrase: true,
    enabled: true,
    supportsPaper: true,
    supportsLive: true,
    type: PROVIDER_TYPES.EXCHANGE,
    requiredKeyFields: ['api_key', 'api_secret', 'passphrase'],
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
    type: PROVIDER_TYPES.EXCHANGE,
    requiredKeyFields: ['api_key', 'api_secret'],
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
    type: PROVIDER_TYPES.EXCHANGE,
    requiredKeyFields: ['api_key', 'api_secret'],
  },

  // ── AI Providers ─────────────────────────────────────────────────────────
  openai: {
    id: 'openai',
    name: 'OpenAI',
    displayName: 'OpenAI',
    icon: '🤖',
    color: '#10A37F',
    type: PROVIDER_TYPES.AI,
    enabled: true,
    requiredKeyFields: ['api_key'],
    helpText: 'Powers AI chat, strategy selection, and market analysis.',
  },
  huggingface: {
    id: 'huggingface',
    name: 'Hugging Face',
    displayName: 'Hugging Face',
    icon: '🤗',
    color: '#FFD21E',
    type: PROVIDER_TYPES.AI,
    enabled: true,
    requiredKeyFields: ['api_key'],
    helpText: 'Provides sentiment analysis and ML-based market predictions.',
  },
  fetchai: {
    id: 'fetchai',
    name: 'Fetch.ai',
    displayName: 'Fetch.ai',
    icon: '🔮',
    color: '#3B82F6',
    type: PROVIDER_TYPES.AI,
    enabled: true,
    requiredKeyFields: ['api_key'],
    helpText: 'Autonomous agent framework for decentralized intelligence.',
  },

  // ── Market Data Providers ────────────────────────────────────────────────
  cryptocompare: {
    id: 'cryptocompare',
    name: 'CryptoCompare',
    displayName: 'CryptoCompare',
    icon: '📈',
    color: '#2196F3',
    type: PROVIDER_TYPES.MARKET_DATA,
    enabled: true,
    priority: 1,
    requiredKeyFields: ['api_key'],
    helpText: 'Primary market data provider — prices, OHLCV, metadata.',
    capabilities: ['prices', 'ohlcv', 'metadata'],
  },
  coingecko: {
    id: 'coingecko',
    name: 'CoinGecko',
    displayName: 'CoinGecko',
    icon: '🦎',
    color: '#8DC63F',
    type: PROVIDER_TYPES.MARKET_DATA,
    enabled: true,
    priority: 2,
    requiredKeyFields: ['api_key'],
    helpText: 'Secondary market data provider — broad coverage, free tier available.',
    capabilities: ['prices', 'ohlcv', 'metadata', 'market_cap'],
  },
  coinranking: {
    id: 'coinranking',
    name: 'Coinranking',
    displayName: 'Coinranking',
    icon: '🏆',
    color: '#0052FF',
    type: PROVIDER_TYPES.MARKET_DATA,
    enabled: true,
    priority: 3,
    requiredKeyFields: ['api_key'],
    helpText: 'Tertiary market data provider — additional fallback coverage.',
    capabilities: ['prices', 'metadata'],
  },

  // ── Intelligence Enrichers ───────────────────────────────────────────────
  glassnode: {
    id: 'glassnode',
    name: 'Glassnode',
    displayName: 'Glassnode',
    icon: '🔬',
    color: '#00BFA5',
    type: PROVIDER_TYPES.ENRICHER,
    enabled: true,
    requiredKeyFields: ['api_key'],
    helpText: 'On-chain analytics — active addresses, exchange flows, NUPL.',
    capabilities: ['on_chain'],
  },
  etherscan: {
    id: 'etherscan',
    name: 'Etherscan',
    displayName: 'Etherscan',
    icon: '🔎',
    color: '#21325B',
    type: PROVIDER_TYPES.ENRICHER,
    enabled: true,
    requiredKeyFields: ['api_key'],
    helpText: 'Ethereum blockchain explorer — large transfers, token events.',
    capabilities: ['on_chain', 'whale_flow'],
  },
  whale_alert: {
    id: 'whale_alert',
    name: 'Whale Alert',
    displayName: 'Whale Alert',
    icon: '🐋',
    color: '#1A73E8',
    type: PROVIDER_TYPES.ENRICHER,
    enabled: true,
    requiredKeyFields: ['api_key'],
    helpText: 'Real-time large crypto transfer alerts across blockchains.',
    capabilities: ['whale_flow'],
  },
  lunarcrush: {
    id: 'lunarcrush',
    name: 'LunarCrush',
    displayName: 'LunarCrush',
    icon: '🌙',
    color: '#7C4DFF',
    type: PROVIDER_TYPES.ENRICHER,
    enabled: true,
    requiredKeyFields: ['api_key'],
    helpText: 'Social sentiment scores and community engagement metrics.',
    capabilities: ['sentiment'],
  },
  cryptopanic: {
    id: 'cryptopanic',
    name: 'CryptoPanic',
    displayName: 'CryptoPanic',
    icon: '📰',
    color: '#FF5722',
    type: PROVIDER_TYPES.ENRICHER,
    enabled: true,
    requiredKeyFields: ['api_key'],
    helpText: 'Crypto news aggregator — headlines, regulatory alerts.',
    capabilities: ['news', 'sentiment'],
  },

  // ── Legacy / Deprecated (fallback-only, hidden from default UI) ──────────
  // DEPRECATED: CoinStats is retained only as an optional legacy fallback.
  // It must NOT be used as the canonical market intelligence source.
  coinstats: {
    id: 'coinstats',
    name: 'CoinStats',
    displayName: 'CoinStats (Legacy)',
    icon: '📊',
    color: '#F59E0B',
    type: PROVIDER_TYPES.LEGACY,
    enabled: false,
    deprecated: true,
    fallbackOnly: true,
    hidden: true,
    requiredKeyFields: ['api_key'],
    helpText: 'Legacy market data fallback — deprecated, use CryptoCompare instead.',
    capabilities: ['prices', 'news'],
  },
};

// Total bot capacity (exchanges only)
export const TOTAL_BOT_CAPACITY = SUPPORTED_PLATFORMS.reduce(
  (sum, id) => sum + (PLATFORM_CONFIG[id]?.maxBots || 0), 0
);

// ─── Utility Functions ──────────────────────────────────────────────────────

export function getPlatformConfig(platformId) {
  return PLATFORM_CONFIG[platformId?.toLowerCase()] || null;
}

export function isValidPlatform(platformId) {
  return ALL_PROVIDERS.includes(platformId?.toLowerCase());
}

export function isAIProvider(providerId) {
  return SUPPORTED_AI_PROVIDERS.includes(providerId?.toLowerCase());
}

export function isMarketDataProvider(providerId) {
  return MARKET_DATA_PROVIDERS.includes(providerId?.toLowerCase());
}

export function isEnricher(providerId) {
  return INTELLIGENCE_ENRICHERS.includes(providerId?.toLowerCase());
}

export function isLegacyProvider(providerId) {
  return LEGACY_PROVIDERS.includes(providerId?.toLowerCase());
}

export function getEnabledPlatforms() {
  return SUPPORTED_PLATFORMS.filter(p => PLATFORM_CONFIG[p]?.enabled);
}

export function getPlatformDisplayName(platformId) {
  const config = getPlatformConfig(platformId);
  return config?.displayName || platformId?.toUpperCase() || 'Unknown';
}

export function getMaxBots(platformId) {
  const config = getPlatformConfig(platformId);
  return config?.maxBots || 0;
}

export function getPlatformIcon(platformId) {
  const config = getPlatformConfig(platformId);
  return config?.icon || '🔷';
}

export function getPlatformColor(platformId) {
  const config = getPlatformConfig(platformId);
  return config?.color || '#999999';
}

export function getPlatformOptions() {
  return SUPPORTED_PLATFORMS.map(id => {
    const config = PLATFORM_CONFIG[id];
    return {
      value: id,
      label: `${config.icon} ${config.displayName} (Max ${config.maxBots} bots)`,
      ...config,
    };
  });
}

/** Get providers grouped by type for the API Setup / Provider Control UI. */
export function getProvidersByType() {
  return {
    exchanges: SUPPORTED_PLATFORMS.map(id => PLATFORM_CONFIG[id]),
    ai: SUPPORTED_AI_PROVIDERS.map(id => PLATFORM_CONFIG[id]),
    marketData: MARKET_DATA_PROVIDERS.map(id => PLATFORM_CONFIG[id]),
    enrichers: INTELLIGENCE_ENRICHERS.map(id => PLATFORM_CONFIG[id]),
    legacy: LEGACY_PROVIDERS.map(id => PLATFORM_CONFIG[id]),
  };
}

/** Get all canonical (non-legacy) providers that can have API keys. */
export function getCanonicalProviders() {
  return [
    ...SUPPORTED_PLATFORMS,
    ...SUPPORTED_AI_PROVIDERS,
    ...MARKET_DATA_PROVIDERS,
    ...INTELLIGENCE_ENRICHERS,
  ];
}

export default {
  SUPPORTED_PLATFORMS,
  SUPPORTED_AI_PROVIDERS,
  MARKET_DATA_PROVIDERS,
  INTELLIGENCE_ENRICHERS,
  LEGACY_PROVIDERS,
  ALL_PROVIDERS,
  PROVIDER_TYPES,
  PLATFORM_CONFIG,
  TOTAL_BOT_CAPACITY,
  getPlatformConfig,
  isValidPlatform,
  isAIProvider,
  isMarketDataProvider,
  isEnricher,
  isLegacyProvider,
  getEnabledPlatforms,
  getPlatformDisplayName,
  getMaxBots,
  getPlatformIcon,
  getPlatformColor,
  getPlatformOptions,
  getProvidersByType,
  getCanonicalProviders,
};
