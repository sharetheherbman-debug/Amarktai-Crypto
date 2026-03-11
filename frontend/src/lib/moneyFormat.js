/**
 * moneyFormat.js — Canonical Money Display Utility
 * =================================================
 * Single source of truth for all user-facing monetary amounts.
 *
 * Rules enforced here:
 *  1. Only prepend "R" when the currency is confirmed ZAR.
 *  2. Only prepend "$" when the currency is confirmed USD/USDT.
 *  3. Never infer currency from the exchange name in this module.
 *  4. Use display_value + display_currency from backend payloads when available.
 *  5. For legacy fields without explicit currency, the caller must pass the
 *     currency explicitly or accept the safe fallback label.
 *
 * DO NOT create another money formatter anywhere else.
 * Import these functions instead.
 */

const NOT_AVAILABLE = '—';

// ── Symbol map (ISO 4217 + crypto quote currencies) ────────────────────────
const CURRENCY_SYMBOL = {
  ZAR: 'R',
  USD: '$',
  USDT: '$',
  USDC: '$',
  BUSD: '$',
  EUR: '€',
  GBP: '£',
  BTC: '₿',
};

/**
 * Format a monetary amount with the correct currency symbol.
 *
 * @param {number|string|null|undefined} value  - The numeric amount
 * @param {string} currency                     - ISO currency code (e.g. "ZAR", "USDT")
 * @param {object} opts
 * @param {number}  [opts.digits=2]             - Decimal digits
 * @param {string}  [opts.fallback]             - String to return when value is not finite
 * @returns {string}
 */
export function formatAmount(value, currency = 'ZAR', opts = {}) {
  const { digits = 2, fallback = NOT_AVAILABLE } = opts;
  const num = Number(value);
  if (!Number.isFinite(num)) return fallback;

  const cur = String(currency || 'ZAR').toUpperCase();
  const symbol = CURRENCY_SYMBOL[cur];
  const absFormatted = Math.abs(num).toLocaleString('en-ZA', {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });

  if (symbol) {
    return `${num < 0 ? '-' : ''}${symbol}${absFormatted}`;
  }
  // Unknown currency: show value + code (e.g. "0.001234 BTC")
  const rawFormatted = Math.abs(num).toLocaleString('en-ZA', {
    minimumFractionDigits: digits,
    maximumFractionDigits: Math.max(digits, 6),
  });
  return `${num < 0 ? '-' : ''}${rawFormatted} ${cur}`;
}

/**
 * Format a ZAR amount (shorthand for formatAmount(value, 'ZAR')).
 *
 * @param {number|string|null|undefined} value
 * @param {number} [digits=2]
 * @param {string} [fallback='—']
 * @returns {string}
 */
export function formatZAR(value, digits = 2, fallback = NOT_AVAILABLE) {
  return formatAmount(value, 'ZAR', { digits, fallback });
}

/**
 * Render a canonical display-currency money object from a backend payload.
 *
 * Prefers backend-provided display fields:
 *   entry.daily_profit_target_display  (ZAR-normalized value)
 *   entry.display_currency             ("ZAR")
 *
 * Falls back to raw value + quote_currency if display fields are absent.
 *
 * @param {object} entry      - Radar/bot entry from API
 * @param {string} field      - Base field name (e.g. "daily_profit_target")
 * @param {object} [opts]
 * @param {number} [opts.digits=2]
 * @param {string} [opts.fallback]
 * @returns {string}
 */
export function formatEntryAmount(entry, field, opts = {}) {
  if (!entry || !field) return opts.fallback || NOT_AVAILABLE;

  // Prefer backend-normalized display value
  const displayField = `${field}_display`;
  const displayCurrency = entry.display_currency || 'ZAR';
  if (entry[displayField] != null) {
    return formatAmount(entry[displayField], displayCurrency, opts);
  }

  // Fall back to raw value + quote_currency
  const rawValue = entry[field];
  const rawCurrency = entry.quote_currency || displayCurrency;
  return formatAmount(rawValue, rawCurrency, opts);
}

/**
 * Get the currency symbol for a given currency code.
 *
 * @param {string} currency
 * @returns {string}
 */
export function getCurrencySymbol(currency) {
  return CURRENCY_SYMBOL[String(currency || 'ZAR').toUpperCase()] || String(currency || '').toUpperCase();
}

export default { formatAmount, formatZAR, formatEntryAmount, getCurrencySymbol };
