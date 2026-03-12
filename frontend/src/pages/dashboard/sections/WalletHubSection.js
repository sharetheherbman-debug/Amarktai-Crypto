import SectionHeader from '@/ui/components/SectionHeader';
import WalletHub from '../../../components/WalletHub';
import CurrencyConverter from '../../../components/CurrencyConverter';

export default function WalletHubSection({ balances, systemModes }) {
  const isPaperMode = systemModes.paperTrading && !systemModes.liveTrading;
  return (
    <section className="section active">
      <div className="card">
        <SectionHeader
          title="💰 Wallet Hub"
          subtitle="Master Luno balances, funding plans, and paper vs live separation."
        />
        <WalletHub isPaperMode={isPaperMode} />
      </div>
      <div className="card" style={{ marginTop: '16px' }}>
        <SectionHeader
          title="💱 Currency Converter"
          subtitle="Convert between ZAR, USD, GBP, EUR, USDT, BTC, ETH using live treasury rates."
        />
        <CurrencyConverter />
      </div>
    </section>
  );
}
