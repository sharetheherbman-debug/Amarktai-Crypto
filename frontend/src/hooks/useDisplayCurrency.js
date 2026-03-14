/**
 * useDisplayCurrency — User Display Currency Preference Hook
 * ==========================================================
 *
 * Loads and persists the user's preferred display currency (ZAR/USD/GBP/EUR)
 * from the backend /api/user/settings endpoint.
 *
 * Returned API:
 *   displayCurrency   — current ISO code ("ZAR", "USD", "GBP", "EUR")
 *   setDisplayCurrency(code) — save a new preference (optimistic + persisted)
 *   loading           — true while the initial fetch is in flight
 *   error             — string when the last save failed, null otherwise
 *   currencySymbol    — shorthand symbol for the current currency ("R", "$", "£", "€")
 *
 * Usage:
 *   const { displayCurrency, setDisplayCurrency, currencySymbol } = useDisplayCurrency();
 */

import { useState, useEffect, useCallback } from 'react';
import { get, put } from '../lib/apiClient';

// ── Constants ─────────────────────────────────────────────────────────────────

export const SUPPORTED_DISPLAY_CURRENCIES = ['ZAR', 'USD', 'GBP', 'EUR'];

export const CURRENCY_SYMBOLS = {
  ZAR: 'R',
  USD: '$',
  GBP: '£',
  EUR: '€',
};

export const CURRENCY_LABELS = {
  ZAR: 'ZAR – South African Rand',
  USD: 'USD – US Dollar',
  GBP: 'GBP – British Pound',
  EUR: 'EUR – Euro',
};

const DEFAULT_CURRENCY = 'ZAR';
const STORAGE_KEY = 'amarktai_display_currency';

// ── Hook ──────────────────────────────────────────────────────────────────────

export function useDisplayCurrency() {
  // Initialise from localStorage for instant paint (avoids flicker on reload)
  const [displayCurrency, setLocalCurrency] = useState(() => {
    try {
      const stored = localStorage.getItem(STORAGE_KEY);
      return SUPPORTED_DISPLAY_CURRENCIES.includes(stored) ? stored : DEFAULT_CURRENCY;
    } catch {
      return DEFAULT_CURRENCY;
    }
  });

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // ── Load preference from backend on mount ─────────────────────────────────
  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const settings = await get('/user/settings');
        const pref = settings?.display_currency;
        if (!cancelled && SUPPORTED_DISPLAY_CURRENCIES.includes(pref)) {
          setLocalCurrency(pref);
          try { localStorage.setItem(STORAGE_KEY, pref); } catch { /* ignore */ }
        }
      } catch {
        // Non-fatal: fall back to localStorage value already set above
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    load();
    return () => { cancelled = true; };
  }, []);

  // ── Persist a new preference ───────────────────────────────────────────────
  const setDisplayCurrency = useCallback(async (code) => {
    const newCode = String(code || DEFAULT_CURRENCY).toUpperCase();
    if (!SUPPORTED_DISPLAY_CURRENCIES.includes(newCode)) {
      setError(`Unsupported currency: ${newCode}`);
      return;
    }

    // Optimistic update
    const prev = displayCurrency;
    setLocalCurrency(newCode);
    try { localStorage.setItem(STORAGE_KEY, newCode); } catch { /* ignore */ }
    setError(null);

    try {
      await put('/user/settings', { display_currency: newCode });
    } catch (err) {
      // Rollback on failure
      setLocalCurrency(prev);
      try { localStorage.setItem(STORAGE_KEY, prev); } catch { /* ignore */ }
      setError(err?.message || 'Failed to save display currency preference.');
    }
  }, [displayCurrency]);

  return {
    displayCurrency,
    setDisplayCurrency,
    loading,
    error,
    currencySymbol: CURRENCY_SYMBOLS[displayCurrency] || displayCurrency,
    isZAR: displayCurrency === 'ZAR',
  };
}

export default useDisplayCurrency;
