import React from 'react';
import SectionHeader from '@/ui/components/SectionHeader';
import APIKeySettings from '../../../components/APIKeySettings';

export default function ApiSetupSection() {
  return (
    <section className="section active">
      <div className="card" style={{padding: '24px'}}>
        <SectionHeader
          title="🔑 API Setup"
          subtitle="Configure AI providers and exchange credentials with improved layout"
        />
        <APIKeySettings />
        <div style={{
          marginTop: '24px',
          padding: '18px',
          background: 'var(--glass)',
          borderRadius: '8px',
          border: '1px solid var(--line)',
          fontSize: '0.9rem',
          color: 'var(--muted)',
          lineHeight: '1.6'
        }}>
          <strong style={{color: 'var(--text)'}}>💡 Tip:</strong> All API keys are encrypted and stored securely.
          Test your credentials after saving to ensure proper configuration.
        </div>
      </div>
    </section>
  );
}
