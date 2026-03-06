import SectionHeader from '@/ui/components/SectionHeader';
import AdminPanelSection from './AdminPanelSection';
import TruthConsoleSection from './TruthConsoleSection';

export default function AdminTruthSection({ axiosConfig, ...adminProps }) {
  return (
    <section className="section active">
      <div className="card">
        <SectionHeader
          title="🔧 Admin & Truth"
          subtitle="Admin operations, system truth verification, and emergency overrides."
        />
      </div>
      <AdminPanelSection {...adminProps} axiosConfig={axiosConfig} />
      <div style={{ marginTop: '16px' }}>
        <TruthConsoleSection axiosConfig={axiosConfig} />
      </div>
    </section>
  );
}
