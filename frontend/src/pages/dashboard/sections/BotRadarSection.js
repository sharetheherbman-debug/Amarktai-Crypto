import { useState, useEffect, useCallback, useRef } from 'react';
import realtimeClient from '../../../lib/realtime';

const RADAR_REFRESH_MS = 10000;

/**
 * BotRadarSection — Clean, practical trading-status panel
 *
 * Shows each bot's current state: name, exchange, type, status,
 * position info, equity, action, and human-readable decision summary.
 */
export default function BotRadarSection({ axiosConfig, embedded = false }) {
  const [radarData, setRadarData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [selectedBot, setSelectedBot] = useState(null);
  const [typeFilter, setTypeFilter] = useState('all');
  const refreshTimeoutRef = useRef(null);

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
    const refreshFromCanonical = () => {
      if (refreshTimeoutRef.current) return;
      refreshTimeoutRef.current = setTimeout(() => {
        refreshTimeoutRef.current = null;
        fetchRadar();
      }, 250);
    };
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
    return () => {
      if (refreshTimeoutRef.current) {
        clearTimeout(refreshTimeoutRef.current);
        refreshTimeoutRef.current = null;
      }
      unsubs.forEach((unsub) => unsub && unsub());
    };
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
  const formatZAR = (value) => {
    const num = Number(value);
    if (!Number.isFinite(num)) return '—';
    const prefix = num >= 0 ? 'R' : '-R';
    return `${prefix}${Math.abs(num).toLocaleString('en-ZA', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
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

  const getStatusInfo = (entry) => {
    if (entry.has_open_position) return { label: 'In Position', color: '#3b82f6' };
    if (!entry.eligible_to_trade || !entry.runnable) return { label: 'Blocked', color: '#ef4444' };
    return { label: 'Ready', color: '#22c55e' };
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
          <div className="radar-marker radar-stop" style={{ left: `${pct(entry.stop_price)}%` }} title={`SL: ${entry.stop_price}`} />
        )}
        <div className="radar-marker radar-entry" style={{ left: `${pct(entry.entry_price)}%` }} title={`Entry: ${entry.entry_price}`} />
        <div className="radar-marker radar-current" style={{ left: `${pct(entry.current_price)}%` }} title={`Current: ${entry.current_price}`} />
        {entry.target_price && (
          <div className="radar-marker radar-target" style={{ left: `${pct(entry.target_price)}%` }} title={`TP: ${entry.target_price}`} />
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
          <span className="radar-stat radar-active">{radarData?.bots_with_positions || 0} in position</span>
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
          {filteredRadar.map((entry) => {
            const status = getStatusInfo(entry);
            const equity = entry.capital_summary?.total_equity ?? entry.capital_allocated ?? 0;
            const isExpanded = selectedBot === entry.bot_id;
            return (
              <div
                key={entry.bot_id}
                className={`radar-card ${isExpanded ? 'radar-card-selected' : ''}`}
                onClick={() => setSelectedBot(isExpanded ? null : entry.bot_id)}
                style={{ cursor: 'pointer' }}
              >
                {/* Card Header: Name, Type Badge, Exchange, Status */}
                <div className="radar-card-top">
                  <span className="radar-bot-name" style={{ fontSize: '1rem', fontWeight: 600 }}>{entry.name}</span>
                  {entry.bot_type === 'scalper' && <span className="radar-type-badge radar-scalper-badge">⚡ Scalper</span>}
                  <span className="radar-exchange" style={{ opacity: 0.7 }}>{entry.exchange}</span>
                  <span className="radar-symbol">{entry.symbol}</span>
                  <span style={{
                    display: 'inline-block',
                    padding: '2px 10px',
                    borderRadius: '12px',
                    fontSize: '0.78rem',
                    fontWeight: 600,
                    background: `${status.color}22`,
                    color: status.color,
                  }}>
                    {status.label}
                  </span>
                  {entry.has_open_position && (
                    <span
                      className="radar-action-badge"
                      style={{ background: getActionColor(entry.next_action), fontSize: '0.78rem' }}
                    >
                      {entry.next_action}
                    </span>
                  )}
                </div>

                {/* Position Info or Waiting State */}
                {entry.has_open_position ? (
                  <>
                    {renderPriceBar(entry)}
                    <div className="radar-card-metrics" style={{ gap: '16px', padding: '8px 0' }}>
                      <div className="radar-metric">
                        <span className="radar-metric-label">Side</span>
                        <span className={`radar-metric-value ${entry.side === 'buy' ? 'radar-buy' : 'radar-sell'}`}>
                          {(entry.side || '').toUpperCase()}
                        </span>
                      </div>
                      <div className="radar-metric">
                        <span className="radar-metric-label">Unrealized P/L</span>
                        <span className={`radar-metric-value ${entry.unrealized_pnl >= 0 ? 'radar-profit' : 'radar-loss'}`}>
                          {formatZAR(entry.unrealized_pnl)}
                        </span>
                      </div>
                      <div className="radar-metric">
                        <span className="radar-metric-label">Hold Timer</span>
                        <span className="radar-metric-value">{formatTime(entry.remaining_hold_seconds)}</span>
                      </div>
                      <div className="radar-metric">
                        <span className="radar-metric-label">Total Equity</span>
                        <span className="radar-metric-value">{formatZAR(equity)}</span>
                      </div>
                    </div>
                  </>
                ) : (
                  <div className="radar-no-position" style={{ padding: '12px 0', fontSize: '0.9rem' }}>
                    <div style={{ marginBottom: '4px' }}>
                      {entry.next_action_reason_text || 'No open position — waiting for signal'}
                    </div>
                    <div style={{ opacity: 0.6, fontSize: '0.82rem' }}>
                      Equity: {formatZAR(equity)}
                      {entry.market_regime && entry.market_regime !== 'unknown' &&
                        ` · Regime: ${entry.market_regime}`
                      }
                    </div>
                  </div>
                )}

                {/* Expanded Details — only useful info */}
                {isExpanded && (
                  <div className="radar-intent-panel" style={{ borderTop: '1px solid rgba(255,255,255,0.08)', paddingTop: '12px', marginTop: '8px' }}>
                    <h4 style={{ fontSize: '0.9rem', marginBottom: '8px' }}>Details</h4>
                    <div className="radar-intent-row">
                      <span>Current Action:</span>
                      <span style={{ color: getActionColor(entry.next_action) }}>{entry.next_action_reason_text}</span>
                    </div>
                    {entry.daily_profit_target != null && (
                      <div className="radar-intent-row">
                        <span>Daily Target ({entry.daily_target_pct ?? '—'}%):</span>
                        <span>{formatZAR(entry.daily_profit_target)}</span>
                      </div>
                    )}
                    {entry.trade_profit_target != null && (
                      <div className="radar-intent-row">
                        <span>Trade Target ({entry.trade_target_pct ?? '—'}%):</span>
                        <span>{formatZAR(entry.trade_profit_target)}</span>
                      </div>
                    )}
                    {entry.target_source && (
                      <div className="radar-intent-row">
                        <span>Target Source:</span>
                        <span style={{ textTransform: 'capitalize' }}>{entry.target_source.replace('_', ' ')}</span>
                      </div>
                    )}
                    <div className="radar-intent-row">
                      <span>Total Equity:</span>
                      <span>{formatZAR(equity)}</span>
                    </div>
                    {entry.has_open_position && (
                      <>
                        <div className="radar-intent-row">
                          <span>Max Hold:</span>
                          <span>{formatTime(entry.max_hold_seconds)}</span>
                        </div>
                        {entry.entry_price && (
                          <div className="radar-intent-row">
                            <span>Entry / TP / SL:</span>
                            <span>{entry.entry_price} / {entry.target_price || '—'} / {entry.stop_price || '—'}</span>
                          </div>
                        )}
                      </>
                    )}
                    {entry.market_regime && entry.market_regime !== 'unknown' && (
                      <div className="radar-intent-row">
                        <span>Market Regime:</span>
                        <span>{entry.market_regime}</span>
                      </div>
                    )}
                    {!entry.eligible_to_trade && (entry.not_eligible_reasons || []).length > 0 && (
                      <div className="radar-intent-row">
                        <span>Blocked:</span>
                        <span>{(entry.not_eligible_reasons || []).join(', ')}</span>
                      </div>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
