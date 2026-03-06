import SectionHeader from '@/ui/components/SectionHeader';
import WalletHub from '../../../components/WalletHub';

export default function WalletTreasurySection({ balances, systemModes }) {
  const isPaperMode = systemModes.paperTrading && !systemModes.liveTrading;
  return (
    <section className="section active">
      <div className="card">
        <SectionHeader
          title="💰 Wallet & Treasury"
          subtitle="Capital visibility, balances, and treasury state."
        />
        <WalletHub isPaperMode={isPaperMode} />
      </div>
    </section>
  );
}
