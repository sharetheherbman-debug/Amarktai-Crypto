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
      <div className="subsection-gap">
        <BotRadarSection axiosConfig={axiosConfig} />
      </div>
      <div className="subsection-gap">
        <ExchangeStatusSection axiosConfig={axiosConfig} />
      </div>
    </section>
  );
}
