/**
 * CurrencyConverter — Canonical Currency / Crypto Conversion Widget
 * =================================================================
 * Uses the backend /api/wallet/converter endpoint (which delegates to
 * fx_normalizer as single source of truth) to convert between:
 *   ZAR, USD, GBP, EUR, USDT, BUSD, USDC, BTC, ETH
 *
 * This component must NOT implement its own FX logic. All conversion
 * is delegated to the backend to guarantee consistency with bot-funding
 * and treasury calculations.
 */

import React, { useState, useCallback } from 'react';
import { post } from '../lib/apiClient';

const SUPPORTED_CURRENCIES = ['ZAR', 'USD', 'GBP', 'EUR', 'USDT', 'BUSD', 'USDC', 'BTC', 'ETH'];

const CURRENCY_LABELS = {
  ZAR: 'ZAR – South African Rand',
  USD: 'USD – US Dollar',
  GBP: 'GBP – British Pound',
  EUR: 'EUR – Euro',
  USDT: 'USDT – Tether (USD)',
  BUSD: 'BUSD – Binance USD',
  USDC: 'USDC – USD Coin',
  BTC: 'BTC – Bitcoin',
  ETH: 'ETH – Ethereum',
};

const CURRENCY_SYMBOLS = {
  ZAR: 'R',
  USD: '$',
  GBP: '£',
  EUR: '€',
  USDT: '$',
  BUSD: '$',
  USDC: '$',
  BTC: '₿',
  ETH: 'Ξ',
};

function formatOutput(amount, currency) {
  if (amount == null || !Number.isFinite(Number(amount))) return '—';
  const num = Number(amount);
  const isCrypto = currency === 'BTC' || currency === 'ETH';
  const digits = isCrypto ? 8 : 2;
  const sym = CURRENCY_SYMBOLS[currency] || '';
  const formatted = Math.abs(num).toLocaleString('en-ZA', {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
  if (sym && !isCrypto) {
    return `${sym}${formatted}`;
  }
  return `${formatted} ${currency}`;
}

export default function CurrencyConverter({ className = '' }) {
  const [amount, setAmount] = useState('1000');
  const [fromCurrency, setFromCurrency] = useState('ZAR');
  const [toCurrency, setToCurrency] = useState('USDT');
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const handleConvert = useCallback(async () => {
    const numAmount = parseFloat(amount);
    if (!Number.isFinite(numAmount) || numAmount < 0) {
      setError('Please enter a valid positive amount.');
      return;
    }
    if (fromCurrency === toCurrency) {
      setResult({
        input_amount: numAmount,
        input_currency: fromCurrency,
        output_amount: numAmount,
        output_currency: toCurrency,
        effective_rate: 1,
        rate_source: 'identity',
        via_zar_amount: fromCurrency === 'ZAR' ? numAmount : null,
      });
      setError(null);
      return;
    }

    setLoading(true);
    setError(null);
    try {
      const data = await post('/wallet/converter', {
        amount: numAmount,
        from_currency: fromCurrency,
        to_currency: toCurrency,
      });
      setResult(data);
    } catch (err) {
      setError(err?.message || 'Conversion failed. Please try again.');
      setResult(null);
    } finally {
      setLoading(false);
    }
  }, [amount, fromCurrency, toCurrency]);

  const handleSwap = () => {
    setFromCurrency(toCurrency);
    setToCurrency(fromCurrency);
    setResult(null);
  };

  return (
    <div className={`currency-converter ${className}`} style={styles.container}>
      <div style={styles.header}>
        <span style={styles.icon}>💱</span>
        <span style={styles.title}>Currency Converter</span>
        <span style={styles.subtitle}>Rates from treasury FX engine</span>
      </div>

      <div style={styles.inputRow}>
        <div style={styles.inputGroup}>
          <label style={styles.label}>Amount</label>
          <input
            type="number"
            min="0"
            step="any"
            value={amount}
            onChange={(e) => { setAmount(e.target.value); setResult(null); }}
            style={styles.amountInput}
            placeholder="Enter amount"
          />
        </div>

        <div style={styles.inputGroup}>
          <label style={styles.label}>From</label>
          <select
            value={fromCurrency}
            onChange={(e) => { setFromCurrency(e.target.value); setResult(null); }}
            style={styles.select}
          >
            {SUPPORTED_CURRENCIES.map((cur) => (
              <option key={cur} value={cur}>{CURRENCY_LABELS[cur] || cur}</option>
            ))}
          </select>
        </div>

        <button onClick={handleSwap} style={styles.swapBtn} title="Swap currencies" aria-label="Swap currencies">
          ⇌
        </button>

        <div style={styles.inputGroup}>
          <label style={styles.label}>To</label>
          <select
            value={toCurrency}
            onChange={(e) => { setToCurrency(e.target.value); setResult(null); }}
            style={styles.select}
          >
            {SUPPORTED_CURRENCIES.map((cur) => (
              <option key={cur} value={cur}>{CURRENCY_LABELS[cur] || cur}</option>
            ))}
          </select>
        </div>

        <button
          onClick={handleConvert}
          disabled={loading}
          style={{ ...styles.convertBtn, ...(loading ? styles.convertBtnDisabled : {}) }}
        >
          {loading ? '...' : 'Convert'}
        </button>
      </div>

      {error && (
        <div style={styles.errorBox}>⚠ {error}</div>
      )}

      {result && !error && (
        <div style={styles.resultBox}>
          <div style={styles.resultMain}>
            <span style={styles.resultInputAmount}>
              {formatOutput(result.input_amount, result.input_currency)}
            </span>
            <span style={styles.resultArrow}> = </span>
            <span style={styles.resultOutputAmount}>
              {formatOutput(result.output_amount, result.output_currency)}
            </span>
          </div>

          <div style={styles.resultMeta}>
            {result.effective_rate != null && (
              <span style={styles.metaTag}>
                Rate: 1 {result.input_currency} = {Number(result.effective_rate).toLocaleString('en-ZA', { maximumSignificantDigits: 6 })} {result.output_currency}
              </span>
            )}
            {result.via_zar_amount != null && result.input_currency !== 'ZAR' && result.output_currency !== 'ZAR' && (
              <span style={styles.metaTag}>
                Via ZAR: {formatOutput(result.via_zar_amount, 'ZAR')}
              </span>
            )}
            {result.rate_source && (
              <span style={{ ...styles.metaTag, ...styles.metaTagSource }}>
                Source: {result.rate_source}
              </span>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

// ── Inline styles (matches existing dashboard dark-theme patterns) ──────────
const styles = {
  container: {
    background: 'rgba(255,255,255,0.04)',
    border: '1px solid rgba(255,255,255,0.1)',
    borderRadius: '12px',
    padding: '20px 24px',
    marginBottom: '16px',
  },
  header: {
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
    marginBottom: '16px',
    flexWrap: 'wrap',
  },
  icon: { fontSize: '1.25rem' },
  title: {
    fontWeight: 700,
    fontSize: '1rem',
    color: '#e2e8f0',
  },
  subtitle: {
    fontSize: '0.75rem',
    color: '#64748b',
    marginLeft: '4px',
  },
  inputRow: {
    display: 'flex',
    alignItems: 'flex-end',
    gap: '12px',
    flexWrap: 'wrap',
  },
  inputGroup: {
    display: 'flex',
    flexDirection: 'column',
    gap: '4px',
  },
  label: {
    fontSize: '0.72rem',
    color: '#94a3b8',
    textTransform: 'uppercase',
    letterSpacing: '0.05em',
  },
  amountInput: {
    background: 'rgba(255,255,255,0.06)',
    border: '1px solid rgba(255,255,255,0.15)',
    borderRadius: '8px',
    color: '#f1f5f9',
    padding: '8px 12px',
    fontSize: '0.95rem',
    width: '140px',
    outline: 'none',
  },
  select: {
    background: 'rgba(30,41,59,0.95)',
    border: '1px solid rgba(255,255,255,0.15)',
    borderRadius: '8px',
    color: '#f1f5f9',
    padding: '8px 10px',
    fontSize: '0.85rem',
    minWidth: '180px',
    cursor: 'pointer',
    outline: 'none',
  },
  swapBtn: {
    background: 'rgba(99,102,241,0.15)',
    border: '1px solid rgba(99,102,241,0.4)',
    borderRadius: '8px',
    color: '#a5b4fc',
    fontSize: '1.25rem',
    padding: '8px 10px',
    cursor: 'pointer',
    alignSelf: 'flex-end',
    lineHeight: 1,
  },
  convertBtn: {
    background: 'linear-gradient(135deg, #6366f1, #8b5cf6)',
    border: 'none',
    borderRadius: '8px',
    color: '#fff',
    fontWeight: 700,
    fontSize: '0.9rem',
    padding: '8px 20px',
    cursor: 'pointer',
    alignSelf: 'flex-end',
    letterSpacing: '0.03em',
  },
  convertBtnDisabled: {
    opacity: 0.5,
    cursor: 'not-allowed',
  },
  errorBox: {
    marginTop: '12px',
    background: 'rgba(239,68,68,0.12)',
    border: '1px solid rgba(239,68,68,0.4)',
    borderRadius: '8px',
    color: '#fca5a5',
    padding: '10px 14px',
    fontSize: '0.85rem',
  },
  resultBox: {
    marginTop: '14px',
    background: 'rgba(16,185,129,0.08)',
    border: '1px solid rgba(16,185,129,0.3)',
    borderRadius: '10px',
    padding: '14px 18px',
  },
  resultMain: {
    display: 'flex',
    alignItems: 'center',
    flexWrap: 'wrap',
    gap: '4px',
    marginBottom: '8px',
  },
  resultInputAmount: {
    fontSize: '1.15rem',
    fontWeight: 700,
    color: '#e2e8f0',
  },
  resultArrow: {
    fontSize: '1.15rem',
    color: '#64748b',
    margin: '0 4px',
  },
  resultOutputAmount: {
    fontSize: '1.25rem',
    fontWeight: 800,
    color: '#34d399',
  },
  resultMeta: {
    display: 'flex',
    flexWrap: 'wrap',
    gap: '8px',
  },
  metaTag: {
    fontSize: '0.75rem',
    color: '#94a3b8',
    background: 'rgba(255,255,255,0.05)',
    borderRadius: '5px',
    padding: '3px 8px',
  },
  metaTagSource: {
    color: '#64748b',
    fontStyle: 'italic',
  },
};
