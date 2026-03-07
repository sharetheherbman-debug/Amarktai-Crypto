import React from 'react';
import SectionHeader from '@/ui/components/SectionHeader';

export default function BotFleetSection({
  bots = [],
  formatDate,
  handleDeleteBot,
  handleResumeBot,
  handleStartBot,
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
  axiosConfig,
}) {
  return (
    <section className="section active" id="bot-fleet">
      <SectionHeader title="🚀 Bot Fleet" subtitle="Monitor and manage your active bots" />
      <div className="card">
        <p style={{ color: 'var(--muted)' }}>
          Bot Fleet section — detailed fleet monitoring coming soon.
        </p>
        {bots.length === 0 && (
          <p style={{ color: 'var(--muted)', marginTop: 12 }}>No bots deployed yet.</p>
        )}
        {bots.length > 0 && (
          <p style={{ color: 'var(--text)', marginTop: 12 }}>
            {bots.length} bot{bots.length !== 1 ? 's' : ''} in fleet.
          </p>
        )}
      </div>
    </section>
  );
}
