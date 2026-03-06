import SectionHeader from '@/ui/components/SectionHeader';
import ProfitsSection from './ProfitsSection';

export default function PerformanceSection(props) {
  return (
    <section className="section active">
      <div className="card">
        <SectionHeader
          title="💹 Performance"
          subtitle="Profit graphs, equity curves, drawdown analysis, and system metrics."
        />
      </div>
      <ProfitsSection {...props} />
    </section>
  );
}
