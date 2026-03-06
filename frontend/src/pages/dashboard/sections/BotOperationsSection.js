import SectionHeader from '@/ui/components/SectionHeader';
import BotManagementSection from './BotManagementSection';

export default function BotOperationsSection(props) {
  return (
    <section className="section active">
      <div className="card">
        <SectionHeader
          title="⚙️ Bot Operations"
          subtitle="Create, manage, and monitor all bots — normal and scalper — in one operations center."
        />
      </div>
      <BotManagementSection {...props} />
    </section>
  );
}
