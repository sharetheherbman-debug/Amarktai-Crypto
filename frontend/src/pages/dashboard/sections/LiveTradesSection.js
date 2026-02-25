import React, { useState, useMemo } from 'react';
import SectionHeader from '@/ui/components/SectionHeader';
import LiveTradesTable from '../../../components/LiveTradesTable';

export default function LiveTradesSection({
  recentTrades,
  bots = [],
  loadRecentTrades,
  tradesLoadError,
  tradesLoading,
}) {
  const [closedTab, setClosedTab] = useState('all');

  const openTrades = useMemo(
    () => (recentTrades || []).filter(t => t.status === 'open' || t.status === 'pending'),
    [recentTrades]
  );

  const closedTrades = useMemo(
    () => (recentTrades || []).filter(t => t.status !== 'open' && t.status !== 'pending'),
    [recentTrades]
  );

  const filteredClosed = useMemo(() => {
    if (closedTab === 'wins') return closedTrades.filter(t => (t.pnl ?? t.profit_loss ?? t.pl ?? 0) >= 0);
    if (closedTab === 'losses') return closedTrades.filter(t => (t.pnl ?? t.profit_loss ?? t.pl ?? 0) < 0);
    return closedTrades;
  }, [closedTrades, closedTab]);

  const winCount = closedTrades.filter(t => (t.pnl ?? t.profit_loss ?? t.pl ?? 0) >= 0).length;
  const winRate = closedTrades.length > 0 ? ((winCount / closedTrades.length) * 100).toFixed(1) : '0.0';
  const netPL = closedTrades.reduce((sum, t) => sum + (t.pnl ?? t.profit_loss ?? t.pl ?? 0), 0);

  const tabStyle = (active) => ({
    padding: '4px 12px',
    borderRadius: '4px',
    border: 'none',
    cursor: 'pointer',
    fontSize: '0.8rem',
    fontWeight: active ? '600' : '400',
    background: active ? 'var(--accent)' : 'transparent',
    color: active ? '#fff' : 'var(--muted)',
  });

  return (
    <section className="section active">
      <div className="card">
        <SectionHeader
          title="📊 Live Trades"
          subtitle="Real-time trade history with filters and updates"
        />

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' }}>
          {/* Left: Open Trades */}
          <div>
            <div style={{ fontWeight: '600', marginBottom: '8px', color: 'var(--text)' }}>
              Open Trades <span style={{ color: 'var(--muted)', fontWeight: '400' }}>({openTrades.length})</span>
            </div>
            <LiveTradesTable
              trades={openTrades}
              bots={bots}
              onRefresh={loadRecentTrades}
              loadError={tradesLoadError}
              isLoading={tradesLoading}
            />
          </div>

          {/* Right: Closed Trades */}
          <div>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '8px' }}>
              <div style={{ fontWeight: '600', color: 'var(--text)' }}>
                Closed Trades
              </div>
              <div style={{ display: 'flex', gap: '4px' }}>
                {['all', 'wins', 'losses'].map(tab => (
                  <button key={tab} style={tabStyle(closedTab === tab)} onClick={() => setClosedTab(tab)}>
                    {tab.charAt(0).toUpperCase() + tab.slice(1)}
                  </button>
                ))}
              </div>
            </div>
            {/* Summary */}
            <div style={{ display: 'flex', gap: '16px', marginBottom: '8px', fontSize: '0.82rem', color: 'var(--muted)' }}>
              <span>Win Rate: <strong style={{ color: 'var(--success)' }}>{winRate}%</strong></span>
              <span>Count: <strong>{closedTrades.length}</strong></span>
              <span>Net P/L: <strong style={{ color: netPL >= 0 ? 'var(--success)' : 'var(--error)' }}>
                {netPL >= 0 ? '+' : ''}R{netPL.toFixed(2)}
              </strong></span>
            </div>
            <LiveTradesTable
              trades={filteredClosed}
              bots={bots}
              onRefresh={loadRecentTrades}
              loadError={tradesLoadError}
              isLoading={tradesLoading}
            />
          </div>
        </div>
      </div>
    </section>
  );
}

