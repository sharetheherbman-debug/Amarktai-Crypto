import React from 'react';
import SectionHeader from '@/ui/components/SectionHeader';
import APIKeySettings from '../../../components/APIKeySettings';

export default function ApiSetupSection() {
  return (
    <section className="section active">
      <div className="card">
        <SectionHeader
          title="🔑 API Setup"
          subtitle="Configure AI providers and exchange credentials with improved layout"
        />
        <div style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(400px, 1fr))',
          gap: '20px',
          '@media (max-width: 900px)': {
            gridTemplateColumns: '1fr'
          }
        }}>
          <div className="api-setup-panel" style={{minHeight: '300px'}}>
            <APIKeySettings />
          </div>
        </div>
        <div style={{
          marginTop: '20px',
          padding: '16px',
          background: 'var(--glass)',
          borderRadius: '8px',
          border: '1px solid var(--line)',
          fontSize: '0.85rem',
          color: 'var(--muted)'
        }}>
          <strong style={{color: 'var(--text)'}}>💡 Tip:</strong> All API keys are encrypted and stored securely.
          Test your credentials after saving to ensure proper configuration.
        </div>
      </div>
    </section>
  );
}
