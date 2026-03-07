// ARCHIVED: This file is not mounted in the dashboard and exists only for reference.
// Canonical section for this functionality lives elsewhere.
import SectionHeader from '@/ui/components/SectionHeader';
import OverviewSection from './OverviewSection';
import { NAV } from '../../../constants/dashboardNav';

export default function HomeSection({ countdown, showSection, ...overviewProps }) {
  const target = countdown?.target_amount;
  const current = countdown?.current_amount;
  const pct = (target && current) ? Math.min(100, (current / target) * 100).toFixed(1) : null;

  return (
    <div>
      <OverviewSection {...overviewProps} />
      {countdown && (
        <section className="section active subsection-gap">
          <div className="card countdown-summary-card" onClick={() => showSection(NAV.COUNTDOWN)}>
            <SectionHeader title="⏱️ Countdown Progress" subtitle="Click to open full Countdown section." />
            <div className="countdown-progress-row">
              <div className="countdown-progress-track">
                <div className="countdown-progress-fill" style={{ width: `${pct ?? 0}%` }} />
              </div>
              <span className="countdown-progress-pct">{pct ?? '—'}%</span>
            </div>
            {countdown.label && <p className="countdown-progress-label">{countdown.label}</p>}
          </div>
        </section>
      )}
    </div>
  );
}
