import React, { useState } from 'react';
import SectionHeader from '@/ui/components/SectionHeader';
import BotManagementSection from './BotManagementSection';
import BotFleetSection from './BotFleetSection';
import BotRadarSection from './BotRadarSection';

const OPS_TAB = {
  FLEET: 'fleet',
  CREATE: 'create',
  RADAR: 'radar',
};

const tabStyle = (active) => ({
  padding: '10px 22px',
  background: active
    ? 'linear-gradient(135deg, rgba(96,130,182,0.9) 0%, rgba(96,130,182,0.7) 100%)'
    : 'rgba(255,255,255,0.04)',
  border: active ? '2px solid rgba(96,130,182,0.8)' : '2px solid rgba(255,255,255,0.08)',
  borderRadius: '10px',
  color: active ? '#fff' : 'var(--muted)',
  cursor: 'pointer',
  fontSize: '0.95rem',
  fontWeight: active ? '700' : '600',
  transition: 'all 0.25s',
  boxShadow: active ? '0 4px 14px rgba(96,130,182,0.35)' : 'none',
});

export default function BotOperationsCenter({
  axiosConfig,
  bots,
  botManagementTab,
  handleBulkCreateBots,
  handleCreateBot,
  handleCreateScalperBot,
  handleCreateUAgent,
  setBotManagementTab,
  formatDate,
  handleDeleteBot,
  handleResumeBot,
  handleStartBot,
  handlePauseBot,
  handleRestartBot,
  handleToggleBotMode,
  botControlLoading,
  selectedBotDetailId,
  setSelectedBotDetailId,
  botDetailTab,
  setBotDetailTab,
  botStatusFilter,
  setBotStatusFilter,
  platformFilter,
  setPlatformFilter,
  editingBotId,
  setEditingBotId,
  editingBotName,
  setEditingBotName,
  handleRenameBotSubmit,
}) {
  const [opsTab, setOpsTab] = useState(OPS_TAB.FLEET);

  const botStats = (bots || []).reduce((acc, b) => {
    const st = (b.status || b.state || '').toLowerCase();
    const bt = (b.bot_type || 'normal').toLowerCase();
    acc.total++;
    if (['active', 'running', 'trading'].includes(st)) acc.active++;
    if (b.has_open_position || b.open_position) acc.inPosition++;
    if (bt === 'normal') acc.normal++;
    if (bt === 'scalper') acc.scalper++;
    return acc;
  }, { total: 0, active: 0, inPosition: 0, normal: 0, scalper: 0 });

  return (
    <section className="section active">
      <div className="card" style={{ background: 'rgba(96,130,182,0.13)', borderRadius: '16px', padding: '24px', border: '1px solid rgba(96,130,182,0.25)' }}>
        <SectionHeader
          title="🚀 Bot Operations Center"
          subtitle="Manage, monitor, and deploy your trading bots from one unified view."
        />

        {/* Summary row */}
        <div style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(120px, 1fr))',
          gap: '12px',
          marginBottom: '20px',
        }}>
          {[
            { label: 'Total', value: botStats.total, color: 'var(--text)' },
            { label: 'Active', value: botStats.active, color: 'var(--success)' },
            { label: 'In Position', value: botStats.inPosition, color: 'var(--accent2)' },
            { label: 'Normal', value: botStats.normal, color: 'var(--text)' },
            { label: 'Scalper', value: botStats.scalper, color: '#f59e0b' },
          ].map(s => (
            <div key={s.label} style={{
              background: 'rgba(255,255,255,0.04)',
              borderRadius: '10px',
              padding: '14px 16px',
              textAlign: 'center',
              border: '1px solid rgba(255,255,255,0.06)',
            }}>
              <div style={{ fontSize: '1.4rem', fontWeight: 700, color: s.color }}>{s.value}</div>
              <div style={{ fontSize: '0.82rem', color: 'var(--muted)', marginTop: '4px' }}>{s.label}</div>
            </div>
          ))}
        </div>

        {/* Tab selector */}
        <div style={{ display: 'flex', gap: '10px', marginBottom: '24px', flexWrap: 'wrap' }}>
          <button onClick={() => setOpsTab(OPS_TAB.FLEET)} style={tabStyle(opsTab === OPS_TAB.FLEET)}>
            🚀 Fleet & Control
          </button>
          <button onClick={() => setOpsTab(OPS_TAB.CREATE)} style={tabStyle(opsTab === OPS_TAB.CREATE)}>
            ⚙️ Create Bot
          </button>
          <button onClick={() => setOpsTab(OPS_TAB.RADAR)} style={tabStyle(opsTab === OPS_TAB.RADAR)}>
            📡 Radar
          </button>
        </div>
      </div>

      {/* Tab content */}
      {opsTab === OPS_TAB.FLEET && (
        <BotFleetSection
          bots={bots}
          formatDate={formatDate}
          handleDeleteBot={handleDeleteBot}
          handleResumeBot={handleResumeBot}
          handleStartBot={handleStartBot}
          handlePauseBot={handlePauseBot}
          handleRestartBot={handleRestartBot}
          handleToggleBotMode={handleToggleBotMode}
          botControlLoading={botControlLoading}
          selectedBotDetailId={selectedBotDetailId}
          setSelectedBotDetailId={setSelectedBotDetailId}
          botDetailTab={botDetailTab}
          setBotDetailTab={setBotDetailTab}
          botStatusFilter={botStatusFilter}
          setBotStatusFilter={setBotStatusFilter}
          platformFilter={platformFilter}
          setPlatformFilter={setPlatformFilter}
          editingBotId={editingBotId}
          setEditingBotId={setEditingBotId}
          editingBotName={editingBotName}
          setEditingBotName={setEditingBotName}
          handleRenameBotSubmit={handleRenameBotSubmit}
          axiosConfig={axiosConfig}
          embedded={true}
        />
      )}

      {opsTab === OPS_TAB.CREATE && (
        <BotManagementSection
          axiosConfig={axiosConfig}
          botManagementTab={botManagementTab}
          handleBulkCreateBots={handleBulkCreateBots}
          handleCreateBot={handleCreateBot}
          handleCreateScalperBot={handleCreateScalperBot}
          handleCreateUAgent={handleCreateUAgent}
          setBotManagementTab={setBotManagementTab}
          embedded={true}
        />
      )}

      {opsTab === OPS_TAB.RADAR && (
        <BotRadarSection axiosConfig={axiosConfig} embedded={true} />
      )}
    </section>
  );
}
