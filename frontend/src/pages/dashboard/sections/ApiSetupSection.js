import SectionHeader from '@/ui/components/SectionHeader';
import APIKeySettings from '../../../components/APIKeySettings';

export default function ApiSetupSection() {
  return (
    <section className="section active">
      <div className="card">
        <SectionHeader
          title="🔑 API Setup"
          subtitle="Manage provider credentials and run key tests from a single command center view."
        />
        <div className="api-setup-split">
          <div className="api-setup-panel">
            <APIKeySettings />
          </div>
        </div>
      </div>
    </section>
  );
}
