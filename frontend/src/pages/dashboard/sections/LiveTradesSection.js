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

      {/* Content Area */}
      <div style={{ display: 'grid', gridTemplateColumns: selectedTrade && viewMode === 'feed' ? '1fr 380px' : '1fr', gap: '16px' }}>
        {/* Feed / Table */}
        <div style={{
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
                        <td style={{ padding: '8px 12px', color: 'var(--text)' }}>{formatZAR(trade.price || trade.avg_price)}</td>
                        <td style={{ padding: '8px 12px', color: 'var(--muted)' }}>{trade.size || trade.quantity || NA}</td>
                        <td style={{ padding: '8px 12px', fontWeight: 700, color: pl >= 0 ? '#22c55e' : '#ef4444' }}>{formatZAR(pl)}</td>
                        <td style={{ padding: '8px 12px', color: 'var(--muted)' }}>{formatZAR(trade.fees || trade.fee)}</td>
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

        {/* Detail Panel (Feed view only) */}
        {selectedTrade && viewMode === 'feed' && (
          <div style={{
            background: 'var(--glass)',
            border: '1px solid var(--line)',
            borderRadius: '14px',
            padding: '20px',
            position: 'sticky',
            top: 0,
            alignSelf: 'start',
          }}>
            <div style={{ marginBottom: '16px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '4px' }}>
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

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
              {[
                { label: 'Side', value: (selectedTrade.side || selectedTrade.action || 'Trade').toString().toUpperCase(), color: getSideColor(selectedTrade.side || selectedTrade.action) },
                { label: 'Price', value: formatZAR(selectedTrade.price || selectedTrade.avg_price) },
                { label: 'Size', value: selectedTrade.size || selectedTrade.quantity || NA },
                { label: 'P/L', value: formatZAR(selectedTrade.profit_loss), color: (Number(selectedTrade.profit_loss) || 0) >= 0 ? '#22c55e' : '#ef4444' },
                { label: 'Fees', value: formatZAR(selectedTrade.fees || selectedTrade.fee) },
                { label: 'Slippage', value: selectedTrade.slippage || NA },
              ].map(({ label, value, color }) => (
                <div key={label} style={{
                  background: 'rgba(10, 14, 26, 0.5)',
                  border: '1px solid var(--line)',
                  borderRadius: '10px',
                  padding: '10px 12px',
                }}>
                  <div style={{ fontSize: '0.72rem', color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: '4px' }}>{label}</div>
                  <div style={{ fontSize: '0.95rem', fontWeight: 700, color: color || 'var(--text)' }}>{value}</div>
                </div>
              ))}
            </div>

            {(selectedTrade.reason || selectedTrade.decision_trace) && (
              <div style={{
                marginTop: '14px',
                padding: '12px',
                background: 'rgba(59, 130, 246, 0.06)',
                border: '1px solid var(--line)',
                borderRadius: '10px',
              }}>
                <div style={{ fontSize: '0.72rem', color: 'var(--muted)', textTransform: 'uppercase', marginBottom: '4px' }}>Decision Trace</div>
                <div style={{ fontSize: '0.85rem', color: 'var(--text)', lineHeight: '1.5' }}>
                  {selectedTrade.reason || selectedTrade.decision_trace}
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </section>
  );
}
