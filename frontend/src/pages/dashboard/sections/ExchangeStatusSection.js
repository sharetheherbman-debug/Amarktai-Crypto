// ARCHIVED: Only referenced by dead TradingMonitorSection. Not mounted.
import { useState, useEffect, useCallback } from 'react';

/**
 * ExchangeStatusSection — Exchange tiles for all 7 exchanges
 *
 * Shows configured/not configured, last tested, pass/fail, error reason
 * for Luno, Binance, KuCoin, Bybit, Kraken, Bitget, Gate.io
 */
export default function ExchangeStatusSection({ axiosConfig }) {
  const [exchanges, setExchanges] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const fetchStatus = useCallback(async () => {
    try {
      const res = await fetch('/api/exchanges/status', {
        headers: axiosConfig?.headers || {},
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setExchanges(data.exchanges || []);
      setError(null);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [axiosConfig]);

  useEffect(() => {
    fetchStatus();
  }, [fetchStatus]);

  const getExchangeEmoji = (name) => {
    const emojis = {
      luno: '🇿🇦', binance: '🔶', kucoin: '🟢',
      bybit: '🟡', kraken: '🐙', bitget: '🔵', gate: '🚪',
    };
    return emojis[name] || '💱';
  };

  if (loading) {
    return (
      <div className="exchange-status-section">
        <h3>🔗 Exchange Status</h3>
        <p>Loading exchange status...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="exchange-status-section">
        <h3>🔗 Exchange Status</h3>
        <p className="exchange-error">Unable to load: {error}</p>
      </div>
    );
  }

  return (
    <div className="exchange-status-section">
      <h3>🔗 Exchange Status</h3>
      <div className="exchange-tiles">
        {exchanges.map((ex) => (
          <div key={ex.exchange} className={`exchange-tile ${ex.configured ? 'exchange-configured' : 'exchange-not-configured'}`}>
            <div className="exchange-tile-header">
              <span className="exchange-emoji">{getExchangeEmoji(ex.exchange)}</span>
              <span className="exchange-name">{ex.exchange}</span>
            </div>
            <div className="exchange-tile-status">
              {ex.configured ? (
                <span className="exchange-badge exchange-badge-ok">Configured</span>
              ) : (
                <span className="exchange-badge exchange-badge-pending">Not Configured</span>
              )}
            </div>
            <div className="exchange-tile-detail">
              <span className="exchange-quote">Quote: {ex.default_quote}</span>
              {ex.test_passed != null && (
                <span className={`exchange-test ${ex.test_passed ? 'test-pass' : 'test-fail'}`}>
                  {ex.test_passed ? '✓ Passed' : '✗ Failed'}
                </span>
              )}
              {ex.error_reason && (
                <span className="exchange-error-reason" title={ex.error_reason}>⚠ Error</span>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
