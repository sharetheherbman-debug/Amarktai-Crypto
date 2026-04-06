// frontend/src/lib/api.js
// Single source of truth for same-origin API + WebSocket URLs.
// Contract:
//   - HTTP base path: /api  (reverse-proxied by Nginx)
//   - WS endpoint:    /api/ws
//
// Environment Variable Support:
//   - REACT_APP_API_BASE or REACT_APP_API_URL sets base (default: /api)
//   - If base already ends with /api, we don't append another /api
//   - If base is origin only (e.g., https://amarktai.online), we append /api

/**
 * Build API base URL from environment or default
 * Ensures we never create /api/api/ double paths
 */
function buildApiBase() {
  // Try environment variables first
  const envBase = process.env.REACT_APP_API_BASE || process.env.REACT_APP_API_URL;
  
  if (envBase) {
    // Normalize: remove trailing slash
    let base = envBase.replace(/\/$/, '');
    
    // If already ends with /api, use as-is
    if (base.endsWith('/api')) {
      return base;
    }
    
    // If it's just an origin (protocol://host:port), append /api
    if (base.match(/^https?:\/\/[^/]+$/)) {
      return `${base}/api`;
    }
    
    // Otherwise, assume it's already the full base path
    return base;
  }
  
  // Default: relative /api (works with Nginx reverse proxy)
  return '/api';
}

export const API_BASE = buildApiBase();

// Runtime guard: detect and warn about double /api/api/ paths
// Always log base URL (not just in development) so production logs confirm correct config
console.log(`[API Config] Base URL: ${API_BASE}`);

/**
 * Safe API URL builder - prevents /api/api/ double paths
 * @param {string} endpoint - Endpoint path (with or without leading slash)
 * @returns {string} Full API URL
 */
export function apiUrl(endpoint) {
  // Normalize endpoint
  const normalizedEndpoint = endpoint.startsWith('/') ? endpoint.slice(1) : endpoint;
  
  // Build URL
  const url = `${API_BASE}/${normalizedEndpoint}`;
  
  // Runtime guard: detect /api/api/ pattern
  if (url.includes('/api/api/')) {
    console.error(`❌ DETECTED /api/api/ DOUBLE PATH: ${url}`);
    console.error(`   Endpoint: ${endpoint}`);
    console.error(`   API_BASE: ${API_BASE}`);
    console.error(`   Fix: Remove /api prefix from endpoint`);
    
    // Fallback: fix the URL by removing duplicate /api
    const fixed = url.replace('/api/api/', '/api/');
    console.warn(`   Fallback to: ${fixed}`);
    return fixed;
  }
  
  return url;
}

export function wsUrl(path = "/api/ws") {
  const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${proto}//${window.location.host}${path}`;
}
