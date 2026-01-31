/**
 * Platform Utilities
 * 
 * Centralized platform management for all 7 supported exchanges:
 * - luno
 * - binance
 * - kucoin
 * - bybit
 * - kraken
 * - bitget
 * - gate
 */

import { API_BASE } from './api';

// Platform configuration with defaults
export const PLATFORMS = {
  luno: {
    id: 'luno',
    name: 'Luno',
    displayName: 'Luno',
    icon: '🇿🇦',
    color: '#3861FB',
    bot_limit: 5,
    supports_paper: true,
    supports_live: true
  },
  binance: {
    id: 'binance',
    name: 'Binance',
    displayName: 'Binance',
    icon: '🟡',
    color: '#F3BA2F',
    bot_limit: 10,
    supports_paper: true,
    supports_live: true
  },
  kucoin: {
    id: 'kucoin',
    name: 'KuCoin',
    displayName: 'KuCoin',
    icon: '🟢',
    color: '#23AF91',
    bot_limit: 10,
    supports_paper: true,
    supports_live: true
  },
  bybit: {
    id: 'bybit',
    name: 'Bybit',
    displayName: 'Bybit',
    icon: '🟠',
    color: '#F7A600',
    bot_limit: 10,
    supports_paper: true,
    supports_live: true
  },
  kraken: {
    id: 'kraken',
    name: 'Kraken',
    displayName: 'Kraken',
    icon: '🟣',
    color: '#5741D9',
    bot_limit: 10,
    supports_paper: true,
    supports_live: true
  },
  bitget: {
    id: 'bitget',
    name: 'Bitget',
    displayName: 'Bitget',
    icon: '🔵',
    color: '#00F0FF',
    bot_limit: 10,
    supports_paper: true,
    supports_live: true
  },
  gate: {
    id: 'gate',
    name: 'Gate.io',
    displayName: 'Gate.io',
    icon: '⚪',
    color: '#17E6A1',
    bot_limit: 10,
    supports_paper: true,
    supports_live: true
  }
};

// Platform list in display order
export const PLATFORM_LIST = ['luno', 'binance', 'kucoin', 'bybit', 'kraken', 'bitget', 'gate'];

/**
 * Fetch platforms from backend with their enabled status and limits
 */
export async function fetchPlatforms(token) {
  try {
    const response = await fetch(`${API_BASE}/system/platforms`, {
      headers: {
        'Authorization': `Bearer ${token}`
      }
    });

    if (!response.ok) {
      throw new Error(`Failed to fetch platforms: ${response.statusText}`);
    }

    const data = await response.json();
    
    // Merge backend data with static configuration
    const platforms = data.platforms || [];
    
    return platforms.map(platform => ({
      ...PLATFORMS[platform.name],
      ...platform,
      displayName: PLATFORMS[platform.name]?.displayName || platform.name
    }));
  } catch (error) {
    console.error('Error fetching platforms:', error);
    
    // Return default platform list with config from PLATFORMS constant
    return PLATFORM_LIST.map(id => ({
      ...PLATFORMS[id],
      enabled: true
    }));
  }
}

/**
 * Get platform display name
 */
export function getPlatformName(platformId) {
  return PLATFORMS[platformId]?.displayName || platformId;
}

/**
 * Get platform icon
 */
export function getPlatformIcon(platformId) {
  return PLATFORMS[platformId]?.icon || '🔷';
}

/**
 * Get platform color
 */
export function getPlatformColor(platformId) {
  return PLATFORMS[platformId]?.color || '#999999';
}

/**
 * Check if platform is valid
 */
export function isValidPlatform(platformId) {
  return PLATFORM_LIST.includes(platformId);
}

/**
 * Filter items by platform
 */
export function filterByPlatform(items, platform, platformKey = 'platform') {
  if (!platform || platform === 'all') {
    return items;
  }
  
  return items.filter(item => {
    const itemPlatform = typeof platformKey === 'function'
      ? platformKey(item)
      : item[platformKey];
    
    return itemPlatform === platform;
  });
}

/**
 * Group items by platform
 */
export function groupByPlatform(items, platformKey = 'platform') {
  const grouped = {};
  
  PLATFORM_LIST.forEach(platform => {
    grouped[platform] = [];
  });
  
  items.forEach(item => {
    const itemPlatform = typeof platformKey === 'function'
      ? platformKey(item)
      : item[platformKey];
    
    if (grouped[itemPlatform]) {
      grouped[itemPlatform].push(item);
    }
  });
  
  return grouped;
}

/**
 * Get platform statistics from items
 */
export function getPlatformStats(items, platformKey = 'platform') {
  const stats = {};
  
  PLATFORM_LIST.forEach(platform => {
    stats[platform] = {
      count: 0,
      platform: platform,
      displayName: getPlatformName(platform),
      icon: getPlatformIcon(platform),
      color: getPlatformColor(platform)
    };
  });
  
  items.forEach(item => {
    const itemPlatform = typeof platformKey === 'function'
      ? platformKey(item)
      : item[platformKey];
    
    if (stats[itemPlatform]) {
      stats[itemPlatform].count++;
    }
  });
  
  return stats;
}

export default {
  PLATFORMS,
  PLATFORM_LIST,
  fetchPlatforms,
  getPlatformName,
  getPlatformIcon,
  getPlatformColor,
  isValidPlatform,
  filterByPlatform,
  groupByPlatform,
  getPlatformStats
};
