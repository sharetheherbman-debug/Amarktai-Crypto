import SectionHeader from '@/ui/components/SectionHeader';
import WalletHub from '../../../components/WalletHub';

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
    </section>
  );
}
