import SectionHeader from '@/ui/components/SectionHeader';
import LiveTradesSection from './LiveTradesSection';
import BotRadarSection from './BotRadarSection';
import ExchangeStatusSection from './ExchangeStatusSection';

export default function TradingMonitorSection({
  axiosConfig,
  recentTrades,
  selectedTradeId,
  setSelectedTradeId,
  setTradeBotFilter,
  setTradeExchangeFilter,
  setTradePairFilter,
  tradeBotFilter,
  tradeExchangeFilter,
  tradePairFilter,
}) {
  return (
    <section className="section active">
      <div className="card">
        <SectionHeader
          title="📡 Trading Monitor"
          subtitle="Live operational trade feed, bot radar, and exchange health."
        />
      </div>
      <LiveTradesSection
        recentTrades={recentTrades}
        selectedTradeId={selectedTradeId}
        setSelectedTradeId={setSelectedTradeId}
        setTradeBotFilter={setTradeBotFilter}
        setTradeExchangeFilter={setTradeExchangeFilter}
        setTradePairFilter={setTradePairFilter}
        tradeBotFilter={tradeBotFilter}
        tradeExchangeFilter={tradeExchangeFilter}
        tradePairFilter={tradePairFilter}
      />
      <div style={{ marginTop: '16px' }}>
        <BotRadarSection axiosConfig={axiosConfig} />
      </div>
      <div style={{ marginTop: '16px' }}>
        <ExchangeStatusSection axiosConfig={axiosConfig} />
      </div>
    </section>
  );
}
