import { useState, useEffect, useCallback } from 'react';

/**
 * ScalperBotsPanel — Scalper bot management subsection
 *
 * Shows scalper cap usage per exchange, list of scalper bots,
 * profit routing mode, and EV check results.
 * Reads from /api/scalper/caps, /api/scalper/summary.
 */
export default function ScalperBotsPanel({ axiosConfig }) {
  const [caps, setCaps] = useState(null);
  const [summary, setSummary] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const fetchData = useCallback(async () => {
    try {
      const headers = axiosConfig?.headers || {};
      const [capsRes, summaryRes] = await Promise.all([
        fetch('/api/scalper/caps', { headers }),
        fetch('/api/scalper/summary', { headers }),
      ]);
      if (capsRes.ok) setCaps(await capsRes.json());
      if (summaryRes.ok) setSummary(await summaryRes.json());
      setError(null);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [axiosConfig]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  if (loading) {
    return <div className="scalper-panel"><p style={{ color: '#9ca3af' }}>Loading scalper data...</p></div>;
  }

  if (error) {
    return <div className="scalper-panel"><p style={{ color: '#ef4444' }}>Error: {error}</p></div>;
  }

  const perExchange = caps?.per_exchange || {};
  const routing = summary?.profit_routing || {};
  const thresholds = caps?.thresholds || {};

  return (
    <div className="scalper-panel">
      <div className="scalper-header">
        <h3>⚡ Scalper Bots</h3>
        <span className="scalper-global-count">
          {caps?.global_current || 0} / {caps?.global_cap || 32} global
        </span>
        <button className="scalper-refresh-btn" onClick={fetchData} title="Refresh">↻</button>
      </div>

      {/* Summary Tiles */}
      <div className="scalper-tiles">
        <div className="scalper-tile">
          <span className="scalper-tile-label">Active</span>
          <span className="scalper-tile-value">{summary?.scalper_active || 0}</span>
        </div>
        <div className="scalper-tile">
          <span className="scalper-tile-label">Paused</span>
          <span className="scalper-tile-value">{summary?.scalper_paused || 0}</span>
        </div>
        <div className="scalper-tile">
          <span className="scalper-tile-label">PnL</span>
          <span className={`scalper-tile-value ${(summary?.scalper_realized_pnl || 0) >= 0 ? 'scalper-profit' : 'scalper-loss'}`}>
            {(summary?.scalper_realized_pnl || 0).toFixed(2)}
          </span>
        </div>
        <div className="scalper-tile">
          <span className="scalper-tile-label">Capital</span>
          <span className="scalper-tile-value">{(summary?.scalper_total_capital || 0).toFixed(2)}</span>
        </div>
      </div>

      {/* Profit Routing */}
      <div className="scalper-routing">
        <h4>Profit Routing</h4>
        <div className="scalper-routing-row">
          <span className="scalper-routing-badge scalper-growth">
            SCALPER_GROWTH: {routing.SCALPER_GROWTH || 0}
          </span>
          <span className="scalper-routing-badge scalper-return">
            RETURN_TO_MAIN: {routing.RETURN_TO_MAIN || 0}
          </span>
        </div>
      </div>

      {/* Per-Exchange Caps */}
      <div className="scalper-caps-grid">
        <h4>Per-Exchange Caps</h4>
        <div className="scalper-exchange-grid">
          {Object.entries(perExchange).map(([exchange, info]) => (
            <div key={exchange} className={`scalper-exchange-card ${info.available <= 0 ? 'scalper-full' : ''}`}>
              <span className="scalper-ex-name">{exchange}</span>
              <span className="scalper-ex-count">{info.current} / {info.cap}</span>
              <span className="scalper-ex-avail">
                {info.available > 0 ? `${info.available} available` : 'FULL'}
              </span>
            </div>
          ))}
        </div>
      </div>

      {/* EV Thresholds */}
      <div className="scalper-thresholds">
        <h4>EV Thresholds</h4>
        <div className="scalper-threshold-grid">
          <div className="scalper-threshold-item">
            <span>Min EV</span><span>{thresholds.ev_min_bps || 10} bps</span>
          </div>
          <div className="scalper-threshold-item">
            <span>Max Spread</span><span>{thresholds.spread_max_bps || 50} bps</span>
          </div>
          <div className="scalper-threshold-item">
            <span>Max Hold</span><span>{thresholds.max_hold_seconds || 300}s</span>
          </div>
          <div className="scalper-threshold-item">
            <span>Cooldown</span><span>{thresholds.cooldown_seconds || 5}s</span>
          </div>
        </div>
      </div>
    </div>
  );
}
