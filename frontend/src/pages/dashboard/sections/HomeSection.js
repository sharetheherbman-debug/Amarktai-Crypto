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
        <section className="section active" style={{ marginTop: '16px' }}>
          <div className="card" style={{ cursor: 'pointer' }} onClick={() => showSection(NAV.COUNTDOWN)}>
            <SectionHeader title="⏱️ Countdown Progress" subtitle="Click to open full Countdown section." />
            <div style={{ display: 'flex', alignItems: 'center', gap: '16px', padding: '8px 0' }}>
              <div style={{ flex: 1 }}>
                <div style={{ background: 'rgba(255,255,255,0.08)', borderRadius: '8px', height: '12px', overflow: 'hidden' }}>
                  <div style={{ width: `${pct ?? 0}%`, height: '100%', background: 'linear-gradient(90deg, #3B82F6, #06B6D4)', borderRadius: '8px', transition: 'width 0.5s ease' }} />
                </div>
              </div>
              <span style={{ fontSize: '0.9rem', color: '#3B82F6', fontWeight: 700 }}>{pct ?? '—'}%</span>
            </div>
            {countdown.label && <p style={{ fontSize: '0.8rem', color: 'rgba(255,255,255,0.5)', marginTop: '4px' }}>{countdown.label}</p>}
          </div>
        </section>
      )}
    </div>
  );
}
