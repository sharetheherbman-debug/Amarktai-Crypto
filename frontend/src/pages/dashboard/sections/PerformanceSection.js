import ProfitsSection from './ProfitsSection';

export default function PerformanceSection({ ...performanceProps }) {
  return (
    <section className="section active">
      <ProfitsSection {...performanceProps} />
    </section>
  );
}
