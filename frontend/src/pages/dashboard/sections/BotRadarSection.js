import { useState, useEffect, useCallback } from 'react';
import realtimeClient from '../../../lib/realtime';

const RADAR_REFRESH_MS = 10000; // Refresh radar data every 10 seconds

/**
 * BotRadarSection — Bot Radar / Bot Map visualization
 *
 * Shows each bot's current position on a live price line:
 * entry → current → target → stop, with time-remaining and next-action info.
 * Supports bot_type filter: all / normal / scalper.
 */
export default function BotRadarSection({ axiosConfig }) {
  const [radarData, setRadarData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [selectedBot, setSelectedBot] = useState(null);
  const [typeFilter, setTypeFilter] = useState('all'); // all / normal / scalper

  const fetchRadar = useCallback(async () => {
    try {
      const res = await fetch('/api/radar/snapshot', {
        headers: axiosConfig?.headers || {},
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setRadarData(data);
      setError(null);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [axiosConfig]);

  useEffect(() => {
    fetchRadar();
    const interval = setInterval(fetchRadar, RADAR_REFRESH_MS);
    return () => clearInterval(interval);
  }, [fetchRadar]);

  useEffect(() => {
    const refreshFromCanonical = () => fetchRadar();
    const unsubs = [
      realtimeClient.on('bots_update', refreshFromCanonical),
      realtimeClient.on('bot_created', refreshFromCanonical),
      realtimeClient.on('bot_status_changed', refreshFromCanonical),
      realtimeClient.on('bot_updated', refreshFromCanonical),
      realtimeClient.on('bot_paused', refreshFromCanonical),
      realtimeClient.on('bot_resumed', refreshFromCanonical),
      realtimeClient.on('bot_quarantined', refreshFromCanonical),
      realtimeClient.on('bot_state_changed', refreshFromCanonical),
      realtimeClient.on('trade_opened', refreshFromCanonical),
      realtimeClient.on('trade_closed', refreshFromCanonical),
      realtimeClient.on('trade_executed', refreshFromCanonical),
      realtimeClient.on('analytics_update', refreshFromCanonical),
    ];
    return () => unsubs.forEach((unsub) => unsub && unsub());
  }, [fetchRadar]);

  if (loading) {
    return (
      <div className="radar-section">
        <h2>📡 Bot Radar</h2>
        <p className="radar-loading">Loading radar data...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="radar-section">
        <h2>📡 Bot Radar</h2>
        <p className="radar-error">Unable to load radar: {error}</p>
      </div>
    );
  }

  const radar = radarData?.radar || [];
  const filteredRadar = typeFilter === 'all'
    ? radar
    : radar.filter(e => (e.bot_type || 'normal') === typeFilter);
  const normalCount = radar.filter(e => (e.bot_type || 'normal') === 'normal').length;
  const scalperCount = radar.filter(e => (e.bot_type || 'normal') === 'scalper').length;

  const formatTime = (seconds) => {
    if (seconds == null) return '—';
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    return h > 0 ? `${h}h ${m}m` : `${m}m`;
  };

  const getActionColor = (action) => {
    switch (action) {
      case 'FORCE_EXIT': return '#ef4444';
      case 'STOP_EXIT': return '#f97316';
      case 'TRAIL_EXIT': return '#eab308';
      case 'TARGET_EXIT': return '#22c55e';
      case 'WARN_EXIT': return '#f59e0b';
      case 'HOLD': return '#3b82f6';
      default: return '#6b7280';
    }
  };

  const renderPriceBar = (entry) => {
    if (!entry.entry_price || !entry.current_price) return null;

    const prices = [entry.entry_price, entry.current_price];
    if (entry.target_price) prices.push(entry.target_price);
    if (entry.stop_price) prices.push(entry.stop_price);

    const min = Math.min(...prices) * 0.999;
    const max = Math.max(...prices) * 1.001;
    const range = max - min || 1;

    const pct = (p) => ((p - min) / range) * 100;

    return (
      <div className="radar-price-bar">
        {entry.stop_price && (
          <div
            className="radar-marker radar-stop"
            style={{ left: `${pct(entry.stop_price)}%` }}
            title={`SL: ${entry.stop_price}`}
          />
        )}
        <div
          className="radar-marker radar-entry"
          style={{ left: `${pct(entry.entry_price)}%` }}
          title={`Entry: ${entry.entry_price}`}
        />
        <div
          className="radar-marker radar-current"
          style={{ left: `${pct(entry.current_price)}%` }}
          title={`Current: ${entry.current_price}`}
        />
        {entry.target_price && (
          <div
            className="radar-marker radar-target"
            style={{ left: `${pct(entry.target_price)}%` }}
            title={`TP: ${entry.target_price}`}
          />
        )}
        {entry.trailing_stop_price && (
          <div
            className="radar-marker radar-trail"
            style={{ left: `${pct(entry.trailing_stop_price)}%` }}
            title={`Trail: ${entry.trailing_stop_price}`}
          />
        )}
      </div>
    );
  };

  const filterLabel = (f) => {
    if (f === 'all') return `All (${radar.length})`;
    if (f === 'normal') return `Normal (${normalCount})`;
    return `Scalper (${scalperCount})`;
  };

  return (
    <div className="radar-section">
      <div className="radar-header">
        <h2>📡 Bot Radar</h2>
        <div className="radar-summary">
          <span className="radar-stat">{radarData?.total_bots || 0} bots</span>
          <span className="radar-stat radar-active">{radarData?.bots_with_positions || 0} with positions</span>
        </div>
        <div className="radar-filters">
          {['all', 'normal', 'scalper'].map((f) => (
            <button
              key={f}
              className={`radar-filter-btn ${typeFilter === f ? 'radar-filter-active' : ''}`}
              onClick={() => setTypeFilter(f)}
            >
              {filterLabel(f)}
            </button>
          ))}
        </div>
      </div>

      {filteredRadar.length === 0 ? (
        <p className="radar-empty">No {typeFilter === 'all' ? '' : typeFilter + ' '}bots available.</p>
      ) : (
        <div className="radar-grid">
          {filteredRadar.map((entry) => (
            <div
              key={entry.bot_id}
              className={`radar-card ${selectedBot === entry.bot_id ? 'radar-card-selected' : ''}`}
              onClick={() => setSelectedBot(selectedBot === entry.bot_id ? null : entry.bot_id)}
            >
              <div className="radar-card-top">
                <span className="radar-bot-name">{entry.name}</span>
                {entry.bot_type === 'scalper' && <span className="radar-type-badge radar-scalper-badge">⚡ Scalper</span>}
                <span className="radar-exchange">{entry.exchange}</span>
                <span className="radar-symbol">{entry.symbol}</span>
                <span
                  className="radar-action-badge"
                  style={{ background: getActionColor(entry.next_action) }}
                >
                  {entry.next_action}
                </span>
              </div>

              {entry.side ? (
                <>
                  {renderPriceBar(entry)}
                  <div className="radar-card-metrics">
                    <div className="radar-metric">
                      <span className="radar-metric-label">Side</span>
                      <span className={`radar-metric-value ${entry.side === 'buy' ? 'radar-buy' : 'radar-sell'}`}>
                        {entry.side.toUpperCase()}
                      </span>
                    </div>
                    <div className="radar-metric">
                      <span className="radar-metric-label">Unrealized</span>
                      <span className={`radar-metric-value ${entry.unrealized_pnl >= 0 ? 'radar-profit' : 'radar-loss'}`}>
                        {entry.unrealized_pnl >= 0 ? '+' : ''}{Number(entry.unrealized_pnl).toFixed(2)}
                      </span>
                    </div>
                    <div className="radar-metric">
                      <span className="radar-metric-label">Remaining</span>
                      <span className="radar-metric-value">{formatTime(entry.remaining_hold_seconds)}</span>
                    </div>
                    <div className="radar-metric">
                      <span className="radar-metric-label">Realized Today</span>
                      <span className="radar-metric-value">{Number(entry.realized_pnl_today).toFixed(2)}</span>
                    </div>
                  </div>
                </>
              ) : (
                <div className="radar-no-position">No open position — waiting for signal</div>
              )}

              {/* Trade Intent Panel */}
              {selectedBot === entry.bot_id && (
                <div className="radar-intent-panel">
                  <h4>Trade Intent</h4>
                  <div className="radar-intent-row">
                    <span>Next Action:</span>
                    <span style={{ color: getActionColor(entry.next_action) }}>{entry.next_action_reason_text}</span>
                  </div>
                  <div className="radar-intent-row">
                    <span>Daily Target:</span>
                    <span>{entry.daily_profit_target === null || entry.daily_profit_target === undefined ? 'Not configured' : Number(entry.daily_profit_target).toFixed(2)}</span>
                  </div>
                  <div className="radar-intent-row">
                    <span>Trade Target:</span>
                    <span>{entry.trade_profit_target === null || entry.trade_profit_target === undefined ? 'Not configured' : Number(entry.trade_profit_target).toFixed(2)}</span>
                  </div>
                  <div className="radar-intent-row">
                    <span>Max Hold:</span>
                    <span>{formatTime(entry.max_hold_seconds)}</span>
                  </div>
                  {entry.entry_price && (
                    <>
                      <div className="radar-intent-row">
                        <span>Entry:</span>
                        <span>{entry.entry_price}</span>
                      </div>
                      <div className="radar-intent-row">
                        <span>TP / SL:</span>
                        <span>{entry.target_price || '—'} / {entry.stop_price || '—'}</span>
                      </div>
                      {entry.trailing_stop_price && (
                        <div className="radar-intent-row">
                          <span>Trailing Stop:</span>
                          <span>{entry.trailing_stop_price}</span>
                        </div>
                      )}
                    </>
                  )}
                  <div className="radar-intent-row">
                    <span>Market Regime:</span>
                    <span>{entry.market_regime || 'unknown'}</span>
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
