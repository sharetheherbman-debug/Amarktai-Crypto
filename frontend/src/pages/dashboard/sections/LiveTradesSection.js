import React from 'react';
import SectionHeader from '@/ui/components/SectionHeader';
import LiveTradesTable from '../../../components/LiveTradesTable';

export default function LiveTradesSection({
  recentTrades,
  bots = [],
  loadRecentTrades,
  tradesLoadError,
  tradesLoading,
}) {
  return (
    <section className="section active">
      <div className="card">
        <SectionHeader
          title="📊 Live Trades"
          subtitle="Real-time trade history with filters and updates"
        />
        
        <LiveTradesTable 
          trades={recentTrades}
          bots={bots}
          onRefresh={loadRecentTrades}
          loadError={tradesLoadError}
          isLoading={tradesLoading}
        />
      </div>
    </section>
  );
}
