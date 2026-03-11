import React, { useState } from 'react';
import SectionHeader from '@/ui/components/SectionHeader';
import AdminPanelSection from './AdminPanelSection';
import TruthConsoleSection from './TruthConsoleSection';

const ADMIN_TAB = {
  OPERATIONS: 'operations',
  TRUTH: 'truth',
};

const tabStyle = (active) => ({
  padding: '12px 24px',
  background: active
    ? 'linear-gradient(135deg, rgba(96,130,182,0.9) 0%, rgba(96,130,182,0.7) 100%)'
    : 'rgba(255,255,255,0.04)',
  border: active ? '2px solid rgba(96,130,182,0.8)' : '2px solid rgba(255,255,255,0.08)',
  borderRadius: '10px',
  color: active ? '#fff' : 'var(--muted)',
  cursor: 'pointer',
  fontSize: '1rem',
  fontWeight: active ? '700' : '600',
  transition: 'all 0.25s',
  boxShadow: active ? '0 4px 14px rgba(96,130,182,0.35)' : 'none',
});

export default function AdminTruthSection({ axiosConfig, ...adminProps }) {
  const [adminTab, setAdminTab] = useState(ADMIN_TAB.OPERATIONS);

  return (
    <section className="section active">
      <div className="card" style={{
        background: 'rgba(96,130,182,0.10)',
        borderRadius: '16px',
        padding: '28px',
        border: '1px solid rgba(96,130,182,0.25)',
      }}>
        <SectionHeader
          title="🔧 Admin Console"
          subtitle="System operations, user management, and truth verification."
        />

        {/* Tab selector */}
        <div style={{ display: 'flex', gap: '12px', flexWrap: 'wrap' }}>
          <button onClick={() => setAdminTab(ADMIN_TAB.OPERATIONS)} style={tabStyle(adminTab === ADMIN_TAB.OPERATIONS)}>
            ⚙️ Operations & Control
          </button>
          <button onClick={() => setAdminTab(ADMIN_TAB.TRUTH)} style={tabStyle(adminTab === ADMIN_TAB.TRUTH)}>
            🔍 Truth & Audit
          </button>
        </div>
      </div>

      {/* Tab content */}
      {adminTab === ADMIN_TAB.OPERATIONS && (
        <AdminPanelSection {...adminProps} axiosConfig={axiosConfig} />
      )}
      {adminTab === ADMIN_TAB.TRUTH && (
        <div style={{ marginTop: '4px' }}>
          <TruthConsoleSection axiosConfig={axiosConfig} />
        </div>
      )}
    </section>
  );
}
