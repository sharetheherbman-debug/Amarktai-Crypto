import ProfitsSection from './ProfitsSection';

export default function PerformanceSection({ axiosConfig, renderMetricsWithTabs, ...performanceProps }) {
  return (
    <section className="section active">
      <ProfitsSection {...performanceProps} />
      {renderMetricsWithTabs && (
        <div className="subsection-gap">
          {renderMetricsWithTabs()}
        </div>
      )}
    </section>
  );
}
