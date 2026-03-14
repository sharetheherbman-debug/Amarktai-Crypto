/**
 * DisplayCurrencySelector — User Display Currency Preference Picker
 * =================================================================
 *
 * Compact dropdown pill that lets the user choose their preferred
 * display currency (ZAR / USD / GBP / EUR).  Changes are saved
 * immediately to the backend via useDisplayCurrency hook.
 *
 * Props:
 *   displayCurrency     — current ISO code string (from useDisplayCurrency)
 *   setDisplayCurrency  — setter from useDisplayCurrency
 *   error               — optional error string from useDisplayCurrency
 *   compact             — when true, shows only the symbol (e.g. "R") instead of code
 *   className           — extra CSS classes for the wrapper
 *
 * Usage:
 *   import DisplayCurrencySelector from '@/components/DisplayCurrencySelector';
 *   import useDisplayCurrency from '@/hooks/useDisplayCurrency';
 *
 *   const { displayCurrency, setDisplayCurrency, error } = useDisplayCurrency();
 *
 *   <DisplayCurrencySelector
 *     displayCurrency={displayCurrency}
 *     setDisplayCurrency={setDisplayCurrency}
 *     error={error}
 *   />
 */

import React, { useState } from 'react';
import {
  SUPPORTED_DISPLAY_CURRENCIES,
  CURRENCY_SYMBOLS,
  CURRENCY_LABELS,
} from '../hooks/useDisplayCurrency';

// ── Inline styles (no new CSS file — uses existing design tokens) ─────────────

const styles = {
  wrapper: {
    position: 'relative',
    display: 'inline-flex',
    alignItems: 'center',
  },
  select: {
    appearance: 'none',
    background: 'transparent',
    border: '1px solid rgba(255,255,255,0.15)',
    borderRadius: '6px',
    color: 'inherit',
    cursor: 'pointer',
    fontSize: '0.8rem',
    fontWeight: 600,
    letterSpacing: '0.02em',
    padding: '4px 24px 4px 8px',
    outline: 'none',
    transition: 'border-color 0.15s',
  },
  chevron: {
    pointerEvents: 'none',
    position: 'absolute',
    right: '6px',
    fontSize: '0.65rem',
    opacity: 0.6,
  },
  error: {
    fontSize: '0.72rem',
    color: '#f87171',
    marginTop: '2px',
    display: 'block',
  },
};

export default function DisplayCurrencySelector({
  displayCurrency = 'ZAR',
  setDisplayCurrency,
  error = null,
  compact = false,
  className = '',
}) {
  const [busy, setBusy] = useState(false);

  const handleChange = async (e) => {
    if (!setDisplayCurrency) return;
    setBusy(true);
    try {
      await setDisplayCurrency(e.target.value);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className={`display-currency-selector ${className}`} style={styles.wrapper}>
      <select
        value={displayCurrency}
        onChange={handleChange}
        disabled={busy}
        style={styles.select}
        title="Select your display currency"
        aria-label="Display currency preference"
      >
        {SUPPORTED_DISPLAY_CURRENCIES.map((code) => (
          <option key={code} value={code}>
            {compact
              ? `${CURRENCY_SYMBOLS[code]} ${code}`
              : CURRENCY_LABELS[code]}
          </option>
        ))}
      </select>
      <span style={styles.chevron} aria-hidden="true">▾</span>
      {error && <span style={styles.error}>{error}</span>}
    </div>
  );
}
