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
 * For non-ZAR bots (e.g. Binance/USDT), the native quote currency is
 * preferred as the primary display unit.  The ZAR *_display fields are
 * intentionally skipped so we never render "$52.63" as "R 52.63".
 *
 * Priority order:
 *  1. Raw value + quote_currency when quote_currency is non-ZAR
 *     (e.g. Binance: 52.63 USDT → "$52.63")
 *  2. Backend *_display field + display_currency when quote is ZAR or absent
 *     (e.g. Luno: daily_profit_target_display in ZAR → "R 25.00")
 *  3. Raw value + quote_currency as final fallback
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

  const quoteCurrency = String(entry.quote_currency || '').toUpperCase();
  const displayCurrency = String(entry.display_currency || 'ZAR').toUpperCase();

  // For non-ZAR bots (e.g. Binance/USDT): prefer native quote amount.
  // This prevents "$52.63 USDT" from being displayed as "R 1000.00 ZAR".
  if (quoteCurrency && quoteCurrency !== 'ZAR') {
    const rawValue = entry[field];
    if (rawValue != null) {
      return formatAmount(rawValue, quoteCurrency, opts);
    }
  }

  // ZAR bots (Luno) or missing quote_currency: prefer backend *_display field.
  const displayField = `${field}_display`;
  if (entry[displayField] != null) {
    return formatAmount(entry[displayField], displayCurrency, opts);
  }

  // Final fallback: raw value + whatever currency is available.
  const rawValue = entry[field];
  const rawCurrency = quoteCurrency || displayCurrency;
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
