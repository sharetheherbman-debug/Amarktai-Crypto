/**
 * Exchange Configuration
 * 
 * Supported exchanges for the Amarktai trading system
 * Including bot caps and feature flags
 */

// Supported exchanges - EXACTLY 7 PLATFORMS
export const EXCHANGES = {
  LUNO: {
    id: 'luno',
    name: 'Luno',
    displayName: 'Luno',
    maxBots: 5,
    region: 'ZA', // South Africa
    icon: '🇿🇦',
    requiresSecret: true,
    requiresPassphrase: false,
    supported: true,
    quoteCurrency: 'ZAR',   // ZAR-native venue
    fundingCurrency: 'ZAR',
  },
  BINANCE: {
    id: 'binance',
    name: 'Binance',
    displayName: 'Binance',
    maxBots: 10,
    region: 'Global',
    icon: '🟡',
    requiresSecret: true,
    requiresPassphrase: false,
    supported: true,
    quoteCurrency: 'USDT',
    fundingCurrency: 'USDT',
  },
  KUCOIN: {
    id: 'kucoin',
    name: 'KuCoin',
    displayName: 'KuCoin',
    maxBots: 10,
    region: 'Global',
    icon: '🟢',
    requiresSecret: true,
    requiresPassphrase: true, // KuCoin requires passphrase
    supported: true,
    quoteCurrency: 'USDT',
    fundingCurrency: 'USDT',
  },
  BYBIT: {
    id: 'bybit',
    name: 'Bybit',
    displayName: 'Bybit',
    maxBots: 10,
    region: 'Global',
    icon: '🟠',
    requiresSecret: true,
    requiresPassphrase: false,
    supported: true,
    quoteCurrency: 'USDT',
    fundingCurrency: 'USDT',
  },
  KRAKEN: {
    id: 'kraken',
    name: 'Kraken',
    displayName: 'Kraken',
    maxBots: 10,
    region: 'Global',
    icon: '🟣',
    requiresSecret: true,
    requiresPassphrase: false,
    supported: true,
    quoteCurrency: 'USDT',
    fundingCurrency: 'USDT',
  },
  BITGET: {
    id: 'bitget',
    name: 'Bitget',
    displayName: 'Bitget',
    maxBots: 10,
    region: 'Global',
    icon: '🔵',
    requiresSecret: true,
    requiresPassphrase: true, // Bitget requires passphrase
    supported: true,
    quoteCurrency: 'USDT',
    fundingCurrency: 'USDT',
  },
  GATE: {
    id: 'gate',
    name: 'Gate.io',
    displayName: 'Gate.io',
    maxBots: 10,
    region: 'Global',
    icon: '⚪',
    requiresSecret: true,
    requiresPassphrase: false,
    supported: true,
    quoteCurrency: 'USDT',
    fundingCurrency: 'USDT',
  }
};

// Get list of all exchanges
export const getAllExchanges = () => {
  return Object.values(EXCHANGES);
};

// Get list of active/supported exchanges
export const getActiveExchanges = () => {
  return Object.values(EXCHANGES).filter(ex => ex.supported);
};

// Get list of South African exchanges
export const getSouthAfricanExchanges = () => {
  return Object.values(EXCHANGES).filter(ex => ex.region === 'ZA' && ex.supported);
};

// Get exchange by ID
export const getExchangeById = (id) => {
  const exchange = Object.values(EXCHANGES).find(ex => ex.id === id?.toLowerCase());
  return exchange || null;
};

// Get total bot cap
export const getTotalBotCap = () => {
  return getActiveExchanges().reduce((sum, ex) => sum + ex.maxBots, 0);
};

// Check if exchange is supported
export const isExchangeSupported = (exchangeId) => {
  const exchange = getExchangeById(exchangeId);
  return exchange ? exchange.supported : false;
};

// Get canonical quote currency for an exchange ID (matches backend EXCHANGE_QUOTE_MAP)
export const getExchangeQuoteCurrency = (exchangeId) => {
  const exchange = getExchangeById(exchangeId);
  return exchange?.quoteCurrency || 'USDT';
};

// Exchange list for dropdowns
export const getExchangeOptions = () => {
  return getAllExchanges().map(ex => ({
    value: ex.id,
    label: `${ex.icon} ${ex.displayName}`,
    disabled: false,
    exchange: ex
  }));
};

export default EXCHANGES;
