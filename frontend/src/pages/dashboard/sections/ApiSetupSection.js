import React, { useState, useEffect } from 'react';
import SectionHeader from '@/ui/components/SectionHeader';
import APIKeySettings from '../../../components/APIKeySettings';
import { apiClient } from '@/lib/apiClient';

function HuggingFaceStatusTile() {
  const [status, setStatus] = useState(null);

  useEffect(() => {
    apiClient.get('/hf/status')
      .then(r => setStatus(r.data))
      .catch(() => setStatus({ enabled: false, last_error: 'Unable to reach /api/hf/status' }));
  }, []);

  if (!status) return null;

  const color = status.enabled && !status.last_error ? 'var(--success)' : status.enabled ? 'var(--warning)' : 'var(--muted)';
  const icon = status.enabled && !status.last_error ? '✅' : status.enabled ? '⚠️' : '❌';

  return (
    <div style={{
      marginTop: '16px',
      padding: '14px 18px',
      background: 'var(--glass)',
      borderRadius: '8px',
      border: `1px solid ${color}`,
      display: 'flex',
      alignItems: 'center',
      gap: '12px',
      flexWrap: 'wrap'
    }}>
      <span style={{ fontSize: '1.4rem' }}>🤗</span>
      <div style={{ flex: 1 }}>
        <div style={{ fontWeight: 700, color: 'var(--text)', marginBottom: '2px' }}>
          {icon} HuggingFace Status
        </div>
        <div style={{ fontSize: '0.85rem', color }}>
          {status.enabled
            ? (status.last_error
              ? `Error: ${status.last_error}`
              : `Connected${status.latency_ms ? ` · ${status.latency_ms}ms` : ''}`)
            : 'Not configured — add your HuggingFace token in AI Keys above'}
        </div>
        {status.last_success_at && (
          <div style={{ fontSize: '0.78rem', color: 'var(--muted)', marginTop: '2px' }}>
            Last success: {new Date(status.last_success_at).toLocaleString()}
          </div>
        )}
      </div>
    </div>
  );
}

export default function ApiSetupSection() {
  return (
    <section className="section active">
      <div className="card">
        <SectionHeader
          title="🔑 API Setup"
          subtitle="Configure AI providers and exchange credentials with improved layout"
        />
        <APIKeySettings />
        <HuggingFaceStatusTile />
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
