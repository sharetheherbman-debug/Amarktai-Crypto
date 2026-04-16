import { useState, useMemo } from 'react';
import SectionHeader from '@/ui/components/SectionHeader';
import { getPlatformDisplayName } from '../../../constants/platforms';

const NA = '—';
const formatZAR = (value, digits = 2) => {
  const num = Number(value);
  if (!Number.isFinite(num)) return NA;
  const formatted = Math.abs(num).toLocaleString('en-US', { minimumFractionDigits: digits, maximumFractionDigits: digits });
  return `${num < 0 ? '-R' : 'R'}${formatted}`;
};

const pill = (active) => ({
  padding: '6px 14px',
  fontSize: '0.78rem',
  fontWeight: 600,
  background: active ? 'rgba(59, 130, 246, 0.18)' : 'transparent',
  color: active ? '#3B82F6' : 'var(--muted)',
  border: '1px solid',
  borderColor: active ? 'rgba(59, 130, 246, 0.35)' : 'var(--line)',
  borderRadius: '999px',
  cursor: 'pointer',
  transition: 'all 0.15s ease',
});

const selectStyle = {
  background: 'rgba(10, 14, 26, 0.9)',
  color: 'var(--text)',
  border: '1px solid var(--line)',
  borderRadius: '8px',
  padding: '7px 12px',
  fontSize: '0.82rem',
  cursor: 'pointer',
  minWidth: '120px',
};

const modePillStyle = (isLive) => ({
  display: 'inline-block',
  padding: '2px 8px',
  borderRadius: '999px',
  fontSize: '0.68rem',
  fontWeight: 700,
  background: isLive ? 'rgba(34, 197, 94, 0.12)' : 'rgba(59, 130, 246, 0.12)',
  color: isLive ? '#22c55e' : '#3B82F6',
  border: `1px solid ${isLive ? 'rgba(34, 197, 94, 0.3)' : 'rgba(59, 130, 246, 0.3)'}`,
  textTransform: 'uppercase',
  letterSpacing: '0.04em',
});

const isLiveTrade = (trade) => {
  const mode = (trade.trading_mode || trade.mode || '').toLowerCase();
  return mode === 'live';
};

export default function LiveTradesSection({
  recentTrades = [],
  realtimeConnected = false,
  selectedTradeId,
  setSelectedTradeId,
  setTradeBotFilter,
  setTradeExchangeFilter,
  setTradePairFilter,
  tradeBotFilter,
  tradeExchangeFilter,
  tradePairFilter,
}) {
  const [viewMode, setViewMode] = useState('feed'); // feed | table

  const exchanges = useMemo(() => Array.from(new Set(recentTrades.map(t => t.exchange?.toLowerCase()).filter(Boolean))), [recentTrades]);
  const botsList = useMemo(() => Array.from(new Set(recentTrades.map(t => t.bot_name).filter(Boolean))), [recentTrades]);
  const pairsList = useMemo(() => Array.from(new Set(recentTrades.map(t => t.symbol).filter(Boolean))), [recentTrades]);

  const filteredTrades = useMemo(() => recentTrades.filter((t) => {
    if (tradeExchangeFilter !== 'all' && t.exchange?.toLowerCase() !== tradeExchangeFilter) return false;
    if (tradeBotFilter !== 'all' && t.bot_name !== tradeBotFilter) return false;
    if (tradePairFilter !== 'all' && t.symbol !== tradePairFilter) return false;
    return true;
  }), [recentTrades, tradeExchangeFilter, tradeBotFilter, tradePairFilter]);

  const selectedTrade = filteredTrades.find(t => t.id === selectedTradeId) || null;

  // Summary stats — wins/losses only counted for CLOSED trades; open positions shown separately
  const stats = useMemo(() => {
    const closedTrades = filteredTrades.filter(t => (t.status || '').toLowerCase() === 'closed');
    const openTrades = filteredTrades.filter(t => (t.status || '').toLowerCase() === 'open');
    const wins = closedTrades.filter(t => t.is_profitable || (Number(t.profit_loss) || 0) > 0).length;
    const losses = closedTrades.length - wins;
    const totalPL = filteredTrades.reduce((s, t) => s + (Number(t.profit_loss) || 0), 0);
    return { total: filteredTrades.length, closed: closedTrades.length, open: openTrades.length, wins, losses, totalPL };
  }, [filteredTrades]);

  // Last trade timestamp
  const lastTradeAt = recentTrades.length > 0 ? recentTrades[0]?.timestamp : null;

  const formatTime = (ts) => {
    if (!ts) return NA;
    try {
      return new Date(ts).toLocaleTimeString('en-ZA', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
    } catch {
      return NA;
    }
  };
  const formatDateTime = (ts) => {
    if (!ts) return NA;
    try {
      return new Date(ts).toLocaleString('en-ZA');
    } catch {
      return NA;
    }
  };

  const getSideColor = (side) => {
    const s = (side || '').toLowerCase();
    if (s === 'buy') return '#22c55e';
    if (s === 'sell') return '#ef4444';
    return 'var(--muted)';
  };

  return (
    <section className="section active">
      {/* Header Bar */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '12px', marginBottom: '12px' }}>
        <SectionHeader title="📡 Live Trades" subtitle="Real-time execution monitor" />
        <div style={{ display: 'flex', gap: '6px', alignItems: 'center' }}>
          {/* Live connection status */}
          <div style={{
            display: 'flex', alignItems: 'center', gap: '6px',
            padding: '5px 12px', borderRadius: '999px',
            background: realtimeConnected ? 'rgba(34, 197, 94, 0.1)' : 'rgba(245, 158, 11, 0.1)',
            border: `1px solid ${realtimeConnected ? 'rgba(34, 197, 94, 0.3)' : 'rgba(245, 158, 11, 0.3)'}`,
            fontSize: '0.75rem', fontWeight: 600,
            color: realtimeConnected ? '#22c55e' : '#f59e0b',
          }}>
            <span style={{
              width: 7, height: 7, borderRadius: '50%',
              background: realtimeConnected ? '#22c55e' : '#f59e0b',
              boxShadow: realtimeConnected ? '0 0 0 2px rgba(34,197,94,0.25)' : 'none',
              animation: realtimeConnected ? 'pulse 2s infinite' : 'none',
              display: 'inline-block', flexShrink: 0,
            }} />
            {realtimeConnected ? 'Live' : 'Reconnecting'}
          </div>
          <button style={pill(viewMode === 'feed')} onClick={() => setViewMode('feed')}>Feed</button>
          <button style={pill(viewMode === 'table')} onClick={() => setViewMode('table')}>Table</button>
        </div>
      </div>

      {/* Last update strip */}
      {lastTradeAt && (
        <div style={{ fontSize: '0.75rem', color: 'var(--muted)', marginBottom: '12px' }}>
          Last trade: <span style={{ color: 'var(--text)' }}>{formatDateTime(lastTradeAt)}</span>
        </div>
      )}

      {/* Stats Strip */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))',
        gap: '10px',
        marginBottom: '16px',
      }}>
        {[
          { label: 'Total Trades', value: stats.total, color: '#3B82F6' },
          { label: 'Open Positions', value: stats.open, color: '#f59e0b' },
          { label: 'Wins', value: stats.wins, color: '#22c55e' },
          { label: 'Losses', value: stats.losses, color: '#ef4444' },
          { label: 'Net P/L', value: formatZAR(stats.totalPL), color: stats.totalPL >= 0 ? '#22c55e' : '#ef4444' },
        ].map(({ label, value, color }) => (
          <div key={label} style={{
            background: 'var(--glass)',
            border: '1px solid var(--line)',
            borderRadius: '12px',
            padding: '14px 16px',
            textAlign: 'center',
          }}>
            <div style={{ fontSize: '0.75rem', color: 'var(--muted)', marginBottom: '4px', textTransform: 'uppercase', letterSpacing: '0.05em' }}>{label}</div>
            <div style={{ fontSize: '1.15rem', fontWeight: 700, color }}>{value}</div>
          </div>
        ))}
      </div>

      {/* Filters */}
      <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap', marginBottom: '16px' }}>
        <select style={selectStyle} value={tradeExchangeFilter} onChange={(e) => setTradeExchangeFilter(e.target.value)}>
          <option value="all">All Exchanges</option>
          {exchanges.map(ex => <option key={ex} value={ex}>{getPlatformDisplayName(ex)}</option>)}
        </select>
        <select style={selectStyle} value={tradeBotFilter} onChange={(e) => setTradeBotFilter(e.target.value)}>
          <option value="all">All Bots</option>
          {botsList.map(b => <option key={b} value={b}>{b}</option>)}
        </select>
        <select style={selectStyle} value={tradePairFilter} onChange={(e) => setTradePairFilter(e.target.value)}>
          <option value="all">All Pairs</option>
          {pairsList.map(p => <option key={p} value={p}>{p}</option>)}
        </select>
      </div>

      {/* Content Area — wrap on narrow screens so the detail panel never
           squashes the feed below ~340 px.  On wide desktop both panels sit
           side-by-side; below ~780 px the detail card drops below the feed. */}
      <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'flex-start', gap: '16px', minHeight: 0 }}>
        {/* Feed / Table */}
        <div style={{
          flex: '1 1 340px',
          minWidth: '300px',
          background: 'var(--glass)',
          border: '1px solid var(--line)',
          borderRadius: '14px',
          overflow: 'hidden',
        }}>
          {filteredTrades.length === 0 ? (
            <div style={{ padding: '48px 24px', textAlign: 'center', color: 'var(--muted)' }}>
              <div style={{ fontSize: '2.2rem', marginBottom: '12px' }}>
                {realtimeConnected ? '📡' : '🔌'}
              </div>
              {recentTrades.length === 0 ? (
                <>
                  <p style={{ fontSize: '0.95rem', color: 'var(--text)', marginBottom: '6px' }}>
                    {realtimeConnected ? 'Watching for trades…' : 'Connecting to live feed…'}
                  </p>
                  <p style={{ fontSize: '0.82rem' }}>
                    Trades will appear here as soon as your bots execute.
                  </p>
                </>
              ) : (
                <>
                  <p style={{ fontSize: '0.95rem', color: 'var(--text)', marginBottom: '6px' }}>No trades match your filters.</p>
                  <p style={{ fontSize: '0.82rem' }}>Try clearing the exchange, bot, or pair filter.</p>
                </>
              )}
            </div>
          ) : viewMode === 'table' ? (
            /* Table View */
            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.82rem' }}>
                <thead>
                  <tr style={{ background: 'rgba(59, 130, 246, 0.06)', borderBottom: '1px solid var(--line)' }}>
                    {['Time', 'Bot', 'Pair', 'Exchange', 'Mode', 'Side', 'Price', 'Size', 'P/L', 'Fees'].map(h => (
                      <th key={h} style={{ padding: '10px 12px', color: 'var(--muted)', fontWeight: 600, textAlign: 'left', whiteSpace: 'nowrap' }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {filteredTrades.slice(0, 60).map((trade, idx) => {
                    const pl = Number(trade.profit_loss) || 0;
                    return (
                      <tr
                        key={trade.id || idx}
                        onClick={() => setSelectedTradeId(trade.id)}
                        style={{
                          borderBottom: '1px solid var(--line)',
                          cursor: 'pointer',
                          background: selectedTradeId === trade.id ? 'rgba(59, 130, 246, 0.08)' : 'transparent',
                          transition: 'background 0.15s',
                        }}
                      >
                        <td style={{ padding: '8px 12px', whiteSpace: 'nowrap', color: 'var(--muted)' }}>{formatTime(trade.timestamp)}</td>
                        <td style={{ padding: '8px 12px', fontWeight: 600, color: 'var(--text)' }}>{trade.bot_name || 'Bot'}</td>
                        <td style={{ padding: '8px 12px', color: 'var(--text)' }}>{trade.symbol || NA}</td>
                        <td style={{ padding: '8px 12px', color: 'var(--muted)' }}>{getPlatformDisplayName(trade.exchange?.toLowerCase())}</td>
                        <td style={{ padding: '8px 12px' }}>
                          <span style={modePillStyle(isLiveTrade(trade))}>
                            {isLiveTrade(trade) ? 'Live' : 'Paper'}
                          </span>
                        </td>
                        <td style={{ padding: '8px 12px' }}>
                          <span style={{ color: getSideColor(trade.side || trade.action), fontWeight: 700, textTransform: 'uppercase', fontSize: '0.78rem' }}>
                            {(trade.side || trade.action || 'TRADE').toString().toUpperCase()}
                          </span>
                        </td>
                        <td style={{ padding: '8px 12px', color: 'var(--text)' }}>{formatZAR(trade.entry_price || trade.price || trade.avg_price)}</td>
                        <td style={{ padding: '8px 12px', color: 'var(--muted)' }}>{trade.size || trade.quantity || trade.qty || trade.amount || NA}</td>
                        <td style={{ padding: '8px 12px', fontWeight: 700, color: pl >= 0 ? '#22c55e' : '#ef4444' }}>{formatZAR(pl)}</td>
                        <td style={{ padding: '8px 12px', color: 'var(--muted)' }}>{formatZAR(trade.fees || trade.fee || trade.fee_total || trade.fee_amount)}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          ) : (
            /* Feed View */
            <div style={{ maxHeight: '520px', overflowY: 'auto', padding: '8px' }}>
              {filteredTrades.slice(0, 50).map((trade, idx) => {
                const pl = Number(trade.profit_loss) || 0;
                const isSelected = selectedTradeId === trade.id;
                const side = (trade.side || trade.action || 'trade').toString().toUpperCase();
                return (
                  <div
                    key={trade.id || idx}
                    onClick={() => setSelectedTradeId(trade.id)}
                    style={{
                      display: 'grid',
                      gridTemplateColumns: '1fr auto',
                      gap: '12px',
                      padding: '12px 14px',
                      marginBottom: '4px',
                      borderRadius: '10px',
                      cursor: 'pointer',
                      background: isSelected ? 'rgba(59, 130, 246, 0.12)' : 'rgba(10, 14, 26, 0.4)',
                      border: '1px solid',
                      borderColor: isSelected ? 'rgba(59, 130, 246, 0.3)' : 'transparent',
                      transition: 'all 0.15s ease',
                    }}
                  >
                    <div>
                      <div style={{ display: 'flex', gap: '8px', alignItems: 'center', marginBottom: '4px', flexWrap: 'wrap' }}>
                        <span style={{ fontWeight: 700, color: 'var(--text)', fontSize: '0.9rem' }}>{trade.bot_name || 'Bot'}</span>
                        <span style={{
                          fontSize: '0.72rem',
                          fontWeight: 700,
                          padding: '2px 8px',
                          borderRadius: '999px',
                          background: `${getSideColor(side)}18`,
                          color: getSideColor(side),
                          textTransform: 'uppercase',
                        }}>{side}</span>
                        <span style={modePillStyle(isLiveTrade(trade))}>
                          {isLiveTrade(trade) ? 'LIVE' : 'PAPER'}
                        </span>
                        <span style={{ color: 'var(--muted)', fontSize: '0.78rem' }}>{trade.symbol || ''}</span>
                      </div>
                      <div style={{ display: 'flex', gap: '12px', fontSize: '0.78rem', color: 'var(--muted)' }}>
                        <span>{getPlatformDisplayName(trade.exchange?.toLowerCase())}</span>
                        <span>{formatTime(trade.timestamp)}</span>
                      </div>
                    </div>
                    <div style={{ textAlign: 'right' }}>
                      <div style={{ fontWeight: 700, fontSize: '0.95rem', color: pl >= 0 ? '#22c55e' : '#ef4444' }}>{formatZAR(pl)}</div>
                      <div style={{ fontSize: '0.75rem', color: 'var(--muted)' }}>{formatZAR(trade.price || trade.avg_price)}</div>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {/* Detail Panel (Feed view only)
             Width: 380px flex-basis, shrinks if container is tight, wraps below the
             feed when viewport is narrow.  Never collapses below 280px.            */}
        {selectedTrade && viewMode === 'feed' && (
          <div style={{
            flex: '0 1 380px',
            minWidth: '280px',
            width: '100%',
            maxWidth: '420px',
            background: 'var(--glass)',
            border: '1px solid var(--line)',
            borderRadius: '14px',
            padding: '20px',
            position: 'sticky',
            top: 0,
            alignSelf: 'start',
            maxHeight: 'calc(100vh - 80px)',
            overflowY: 'auto',
            boxSizing: 'border-box',
          }}>
            <div style={{ marginBottom: '16px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '4px', flexWrap: 'wrap' }}>
                <h3 style={{ fontSize: '1.1rem', fontWeight: 700, color: 'var(--text)', margin: 0 }}>
                  {selectedTrade.symbol || NA}
                </h3>
                <span style={modePillStyle(isLiveTrade(selectedTrade))}>
                  {isLiveTrade(selectedTrade) ? 'LIVE' : 'PAPER'}
                </span>
              </div>
              <p style={{ color: 'var(--muted)', fontSize: '0.85rem' }}>
                {selectedTrade.bot_name || 'Bot'} • {getPlatformDisplayName(selectedTrade.exchange?.toLowerCase())}
              </p>
              <p style={{ color: 'var(--muted)', fontSize: '0.78rem', marginTop: '2px' }}>
                {formatDateTime(selectedTrade.timestamp)}
              </p>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(110px, 1fr))', gap: '10px' }}>
              {[
                { label: 'Side', value: (selectedTrade.side || selectedTrade.action || 'Trade').toString().toUpperCase(), color: getSideColor(selectedTrade.side || selectedTrade.action) },
                { label: 'Price', value: formatZAR(selectedTrade.entry_price || selectedTrade.price || selectedTrade.avg_price) },
                { label: 'Size', value: selectedTrade.size || selectedTrade.quantity || selectedTrade.qty || selectedTrade.amount || NA },
                { label: 'P/L', value: formatZAR(selectedTrade.profit_loss ?? selectedTrade.net_profit_loss ?? selectedTrade.net_pnl), color: (Number(selectedTrade.profit_loss ?? selectedTrade.net_profit_loss ?? 0) || 0) >= 0 ? '#22c55e' : '#ef4444' },
                { label: 'Fees', value: formatZAR(selectedTrade.fees || selectedTrade.fee || selectedTrade.fee_total || selectedTrade.fee_amount) },
                { label: 'Slippage', value: (selectedTrade.slippage != null || selectedTrade.slippage_cost != null) ? formatZAR(selectedTrade.slippage ?? selectedTrade.slippage_cost) : NA },
              ].map(({ label, value, color }) => (
                <div key={label} style={{
                  background: 'rgba(10, 14, 26, 0.5)',
                  border: '1px solid var(--line)',
                  borderRadius: '10px',
                  padding: '10px 12px',
                  minWidth: 0,
                }}>
                  <div style={{ fontSize: '0.68rem', color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: '4px', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{label}</div>
                  <div style={{ fontSize: '0.88rem', fontWeight: 700, color: color || 'var(--text)', wordBreak: 'break-word', overflowWrap: 'anywhere' }}>{value}</div>
                </div>
              ))}
            </div>

            {(selectedTrade.reason != null || selectedTrade.decision_trace != null) && (() => {
              const raw = selectedTrade.reason != null ? selectedTrade.reason : selectedTrade.decision_trace;
              // Human-readable recursive renderer for decision trace fields.
              // Nested objects expand as indented sub-tables instead of raw JSON blobs.
              const SKIP_KEYS = new Set(['top_candidates']); // large/irrelevant arrays
              const LABEL_MAP = {
                expectancy_estimate: 'Expectancy (ZAR)',
                cost_estimate: 'Est. Cost %',
                regime: 'Market Regime',
                playbook: 'Strategy',
                chosen_pair: 'Chosen Pair',
                evaluated_pairs_count: 'Pairs Evaluated',
                take_profit_pct: 'Take Profit %',
                stop_loss_pct: 'Stop Loss %',
                time_exit_minutes: 'Max Hold (min)',
                hard_max_hold_seconds: 'Hard Exit (s)',
                next_exit_reason: 'Next Exit',
              };
              const fmtLabel = (k) => LABEL_MAP[k] || k.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
              const fmtVal = (v) => {
                if (v == null) return '—';
                if (typeof v === 'boolean') return v ? 'Yes' : 'No';
                if (typeof v === 'number') return Number.isInteger(v) ? String(v) : v.toFixed(4);
                return String(v);
              };
              const renderValue = (v, depth = 0) => {
                if (v == null) return <span style={{ color: 'var(--muted)' }}>—</span>;
                if (typeof v !== 'object' || Array.isArray(v)) return <span>{fmtVal(v)}</span>;
                // Nested object: render as indented key-value block
                const entries = Object.entries(v).filter(([k]) => !SKIP_KEYS.has(k));
                if (entries.length === 0) return <span style={{ color: 'var(--muted)' }}>—</span>;
                return (
                  <table style={{ width: '100%', borderCollapse: 'collapse', marginLeft: depth > 0 ? 8 : 0 }}>
                    <tbody>
                      {entries.map(([k2, v2]) => (
                        <tr key={k2}>
                          <td style={{ padding: '2px 8px 2px 0', color: 'var(--muted)', whiteSpace: 'nowrap', verticalAlign: 'top', fontWeight: 600, fontSize: '0.78rem' }}>{fmtLabel(k2)}</td>
                          <td style={{ padding: '2px 0', color: 'var(--text)', wordBreak: 'break-word', fontSize: '0.78rem' }}>{renderValue(v2, depth + 1)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                );
              };
              const renderTrace = () => {
                if (raw == null) return null;
                if (typeof raw === 'string') return <span>{raw}</span>;
                if (typeof raw !== 'object') return <span>{String(raw)}</span>;
                const entries = Object.entries(raw).filter(([k]) => !SKIP_KEYS.has(k));
                return (
                  <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.82rem' }}>
                    <tbody>
                      {entries.map(([k, v]) => (
                        <tr key={k} style={{ borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
                          <td style={{ padding: '3px 8px 3px 0', color: 'var(--muted)', whiteSpace: 'nowrap', verticalAlign: 'top', fontWeight: 600 }}>{fmtLabel(k)}</td>
                          <td style={{ padding: '3px 0', color: 'var(--text)', wordBreak: 'break-word' }}>
                            {renderValue(v)}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                );
              };
              return (
                <details style={{ marginTop: '14px' }}>
                  <summary style={{
                    cursor: 'pointer',
                    padding: '8px 12px',
                    background: 'rgba(59, 130, 246, 0.06)',
                    border: '1px solid var(--line)',
                    borderRadius: '10px',
                    fontSize: '0.72rem',
                    color: 'var(--muted)',
                    textTransform: 'uppercase',
                    letterSpacing: '0.05em',
                    userSelect: 'none',
                  }}>
                    Decision Trace ▸ expand
                  </summary>
                  <div style={{
                    marginTop: '4px',
                    padding: '12px',
                    background: 'rgba(59, 130, 246, 0.04)',
                    border: '1px solid var(--line)',
                    borderRadius: '0 0 10px 10px',
                    borderTop: 'none',
                  }}>
                    {renderTrace()}
                  </div>
                </details>
              );
            })()}
          </div>
        )}
      </div>
    </section>
  );
}
