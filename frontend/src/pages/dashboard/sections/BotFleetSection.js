import React, { useState, useMemo, useCallback } from 'react';
import SectionHeader from '@/ui/components/SectionHeader';
import { getPlatformDisplayName } from '../../../constants/platforms';
import { getBotStatus } from '../../../hooks/useDashboardData';
import ScalperBotsPanel from './ScalperBotsPanel';

/* ── helpers ──────────────────────────────────────────────── */

function safeNum(v, fallback = 0) {
  const n = Number(v);
  return Number.isFinite(n) ? n : fallback;
}

function fmtZAR(v, digits = 2, fallback = 'R 0.00') {
  if (v == null) return fallback;
  const n = safeNum(v);
  return `R ${n.toLocaleString('en-ZA', { minimumFractionDigits: digits, maximumFractionDigits: digits })}`;
}

function fmtPct(v, fallback = '—') {
  const n = safeNum(v);
  return v == null ? fallback : `${n.toFixed(1)}%`;
}

function statusColor(status) {
  switch (status) {
    case 'active': case 'running': return 'var(--success)';
    case 'paused': return '#f59e0b';
    case 'training': return 'var(--accent2)';
    case 'quarantined': return 'var(--error)';
    case 'stopped': case 'inactive': return 'var(--muted)';
    default: return 'var(--muted)';
  }
}

function statusLabel(status) {
  switch (status) {
    case 'active': case 'running': return 'Active';
    case 'paused': return 'Paused';
    case 'training': return 'Training';
    case 'quarantined': return 'Quarantined';
    case 'stopped': return 'Stopped';
    case 'inactive': return 'Inactive';
    default: return status || 'Unknown';
  }
}

function modeLabel(bot) {
  const m = (bot.trading_mode || bot.mode || '').toLowerCase();
  return m === 'live' ? 'LIVE' : 'PAPER';
}

function modeColor(bot) {
  return modeLabel(bot) === 'LIVE' ? 'var(--success)' : 'var(--accent2)';
}

/* ── shared inline styles ─────────────────────────────────── */

const S = {
  tab: (active) => ({
    padding: '8px 20px',
    border: 'none',
    borderBottom: active ? '2px solid var(--accent2)' : '2px solid transparent',
    background: 'transparent',
    color: active ? 'var(--accent2)' : 'var(--muted)',
    cursor: 'pointer',
    fontWeight: active ? 600 : 400,
    fontSize: 14,
    transition: 'color .15s, border-color .15s',
  }),
  chip: (active) => ({
    padding: '4px 12px',
    borderRadius: 20,
    border: `1px solid ${active ? 'var(--accent2)' : 'var(--line)'}`,
    background: active ? 'rgba(96,165,250,0.15)' : 'transparent',
    color: active ? 'var(--accent2)' : 'var(--muted)',
    cursor: 'pointer',
    fontSize: 12,
    fontWeight: 500,
    transition: 'all .15s',
  }),
  card: {
    background: 'var(--glass)',
    border: '1px solid var(--line)',
    borderRadius: 'var(--radius-md, 14px)',
    padding: 16,
    cursor: 'pointer',
    transition: 'border-color .15s, box-shadow .15s',
  },
  cardSelected: {
    borderColor: 'var(--accent2)',
    boxShadow: '0 0 0 1px var(--accent2)',
  },
  pill: (color) => ({
    display: 'inline-block',
    padding: '2px 10px',
    borderRadius: 12,
    fontSize: 11,
    fontWeight: 600,
    color,
    background: `${color}22`,
    letterSpacing: 0.3,
  }),
  btn: (variant = 'default') => {
    const base = {
      padding: '6px 14px',
      borderRadius: 8,
      border: '1px solid var(--line)',
      cursor: 'pointer',
      fontSize: 13,
      fontWeight: 500,
      transition: 'all .15s',
    };
    if (variant === 'primary') return { ...base, background: 'var(--accent2)', color: '#fff', borderColor: 'var(--accent2)' };
    if (variant === 'success') return { ...base, background: 'rgba(34,197,94,0.15)', color: 'var(--success)', borderColor: 'var(--success)' };
    if (variant === 'danger') return { ...base, background: 'rgba(239,68,68,0.12)', color: 'var(--error)', borderColor: 'var(--error)' };
    if (variant === 'warning') return { ...base, background: 'rgba(245,158,11,0.12)', color: '#f59e0b', borderColor: '#f59e0b' };
    return { ...base, background: 'transparent', color: 'var(--text)' };
  },
  detailRow: {
    display: 'flex',
    justifyContent: 'space-between',
    padding: '6px 0',
    borderBottom: '1px solid var(--line)',
    fontSize: 13,
  },
  detailLabel: { color: 'var(--muted)', fontWeight: 400 },
  detailValue: { color: 'var(--text)', fontWeight: 500, textAlign: 'right' },
};

/* ── status filter options ────────────────────────────────── */

const STATUS_FILTERS = [
  { value: 'all', label: 'All' },
  { value: 'active', label: 'Active' },
  { value: 'paused', label: 'Paused' },
  { value: 'training', label: 'Training' },
  { value: 'quarantined', label: 'Quarantined' },
  { value: 'stopped', label: 'Stopped' },
];

const FLEET_TABS = [
  { key: 'normal', label: '🤖 Normal Bots' },
  { key: 'scalper', label: '⚡ Scalper Bots' },
  { key: 'uagent', label: '🌐 uAgents' },
];

const DETAIL_TABS = [
  { key: 'overview', label: 'Overview' },
  { key: 'performance', label: 'Performance' },
  { key: 'controls', label: 'Controls' },
];

/* ── component ────────────────────────────────────────────── */

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
  const [fleetTab, setFleetTab] = useState('normal');
  const [confirmDelete, setConfirmDelete] = useState(null);

  /* derive unique platforms from bots */
  const platforms = useMemo(() => {
    const set = new Set(bots.map((b) => (b.exchange || '').toLowerCase()).filter(Boolean));
    return ['all', ...Array.from(set).sort()];
  }, [bots]);

  /* filtered bots — always exclude deleted/ghost bots regardless of filter */
  const filteredBots = useMemo(() => {
    return bots.filter((bot) => {
      const st = getBotStatus(bot);
      // Exclude deleted/ghost bots from all fleet views
      if (st === 'deleted' || bot.deleted_at || bot.deleted === true || bot.is_deleted === true) return false;
      // Partition by tab — normal tab shows non-scalper non-uagent bots; uagent tab shows uagent bots
      if (fleetTab === 'normal') {
        const bt = (bot.bot_type || '').toLowerCase();
        if (bt === 'scalper' || bt === 'uagent') return false;
      }
      if (fleetTab === 'uagent') {
        if ((bot.bot_type || '').toLowerCase() !== 'uagent') return false;
      }
      if (botStatusFilter && botStatusFilter !== 'all' && st !== botStatusFilter) return false;
      if (platformFilter && platformFilter !== 'all' && (bot.exchange || '').toLowerCase() !== platformFilter) return false;
      return true;
    });
  }, [bots, botStatusFilter, platformFilter, fleetTab]);

  const selectedBot = useMemo(() => {
    if (!selectedBotDetailId) return null;
    return bots.find((b) => b.id === selectedBotDetailId) || null;
  }, [bots, selectedBotDetailId]);

  /* callbacks */
  const selectBot = useCallback((id) => {
    setSelectedBotDetailId(id === selectedBotDetailId ? null : id);
    if (setBotDetailTab) setBotDetailTab('overview');
    setConfirmDelete(null);
  }, [selectedBotDetailId, setSelectedBotDetailId, setBotDetailTab]);

  const startRename = useCallback((bot) => {
    setEditingBotId(bot.id);
    setEditingBotName(bot.name || '');
  }, [setEditingBotId, setEditingBotName]);

  const cancelRename = useCallback(() => {
    setEditingBotId(null);
    setEditingBotName('');
  }, [setEditingBotId, setEditingBotName]);

  const submitRename = useCallback((e) => {
    e.preventDefault();
    if (handleRenameBotSubmit) handleRenameBotSubmit();
  }, [handleRenameBotSubmit]);

  /* ── detail sections for selected bot ───────────────────── */
  const detailSections = useMemo(() => {
    if (!selectedBot) return null;
    const st = getBotStatus(selectedBot);
    return {
      overview: [
        { label: 'Bot ID', value: selectedBot.id || '—' },
        { label: 'Name', value: selectedBot.name || '—' },
        { label: 'Exchange', value: getPlatformDisplayName(selectedBot.exchange) },
        { label: 'Status', value: statusLabel(st), color: statusColor(st) },
        { label: 'Mode', value: modeLabel(selectedBot), color: modeColor(selectedBot) },
        { label: 'Created', value: formatDate && selectedBot.created_at ? formatDate(selectedBot.created_at) : '—' },
        { label: 'Training', value: selectedBot.training_complete ? '✅ Complete' : '🔄 In Progress' },
        { label: 'Quarantine', value: selectedBot.quarantine_active || selectedBot.in_quarantine ? '⚠️ Active' : '✅ Clear' },
        ...(selectedBot.paused_reason_message ? [{ label: 'Paused Reason', value: selectedBot.paused_reason_message }] : []),
      ],
      performance: [
        { label: 'Capital', value: fmtZAR(selectedBot.current_capital) },
        { label: 'Profit', value: fmtZAR(selectedBot.profit), color: safeNum(selectedBot.profit) >= 0 ? 'var(--success)' : 'var(--error)' },
        { label: 'Win Rate', value: fmtPct(selectedBot.win_rate) },
        { label: 'Total Trades', value: safeNum(selectedBot.total_trades).toString() },
        { label: 'ROI', value: selectedBot.current_capital ? fmtPct((safeNum(selectedBot.profit) / safeNum(selectedBot.current_capital, 1)) * 100) : '—' },
      ],
    };
  }, [selectedBot, formatDate]);

  /* ── render ─────────────────────────────────────────────── */

  return (
    <section className="section active" id="bot-fleet">
      <SectionHeader
        title="🚀 Bot Fleet"
        subtitle={`Monitor and manage your deployed bots — ${filteredBots.length} displayed (ghost bots excluded)`}
      />

      {/* Fleet Tabs */}
      <div style={{ display: 'flex', gap: 0, borderBottom: '1px solid var(--line)', marginBottom: 16 }}>
        {FLEET_TABS.map((t) => (
          <button key={t.key} style={S.tab(fleetTab === t.key)} onClick={() => setFleetTab(t.key)}>
            {t.label}
          </button>
        ))}
      </div>

      {/* Scalper Tab */}
      {fleetTab === 'scalper' && <ScalperBotsPanel axiosConfig={axiosConfig} />}

      {/* uAgents Tab */}
      {fleetTab === 'uagent' && (
        <>
          {filteredBots.length === 0 ? (
            <div style={{ color: 'var(--muted)', textAlign: 'center', padding: '40px 0', fontSize: 14 }}>
              No uAgents deployed yet. Create one in <strong>Bot Management → Fetch.ai / uAgents</strong>.
            </div>
          ) : (
            <div style={{ display: 'grid', gap: 10, gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))' }}>
              {filteredBots.map((bot) => {
                const st = getBotStatus(bot);
                const isSelected = selectedBotDetailId === bot.id;
                return (
                  <div
                    key={bot.id}
                    style={{ ...S.card, ...(isSelected ? S.cardSelected : {}) }}
                    onClick={() => selectBot(bot.id)}
                  >
                    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6 }}>
                      <span style={{ fontWeight: 600, fontSize: 14 }}>{bot.name || 'Unnamed uAgent'}</span>
                      <span style={S.pill(statusColor(st))}>{statusLabel(st)}</span>
                    </div>
                    <div style={{ fontSize: 12, color: 'var(--muted)' }}>
                      Exchange: {getPlatformDisplayName(bot.exchange)} • Mode: <span style={{ color: modeColor(bot) }}>{modeLabel(bot)}</span>
                    </div>
                    <div style={{ fontSize: 12, color: 'var(--muted)', marginTop: 4 }}>
                      Capital: {fmtZAR(bot.current_capital)} • P&amp;L: <span style={{ color: safeNum(bot.profit) >= 0 ? 'var(--success)' : 'var(--error)' }}>{fmtZAR(bot.profit)}</span>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </>
      )}

      {/* Normal Bots Tab */}
      {fleetTab === 'normal' && (
        <>
          {/* ── Filters ────────────────────────────────────── */}
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginBottom: 12 }}>
            <span style={{ color: 'var(--muted)', fontSize: 12, lineHeight: '28px', marginRight: 4 }}>Status:</span>
            {STATUS_FILTERS.map((f) => (
              <button
                key={f.value}
                style={S.chip(botStatusFilter === f.value)}
                onClick={() => setBotStatusFilter(f.value)}
              >
                {f.label}
              </button>
            ))}
          </div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginBottom: 20 }}>
            <span style={{ color: 'var(--muted)', fontSize: 12, lineHeight: '28px', marginRight: 4 }}>Platform:</span>
            {platforms.map((p) => (
              <button
                key={p}
                style={S.chip(platformFilter === p)}
                onClick={() => setPlatformFilter(p)}
              >
                {p === 'all' ? 'All' : getPlatformDisplayName(p)}
              </button>
            ))}
          </div>

          {/* ── Fleet summary bar ──────────────────────────── */}
          <div style={{
            display: 'flex', flexWrap: 'wrap', gap: 16, marginBottom: 20,
            padding: '10px 16px', background: 'var(--glass)', border: '1px solid var(--line)',
            borderRadius: 'var(--radius-sm, 10px)',
          }}>
            {[
              { label: 'Total', value: filteredBots.length },
              { label: 'Active', value: filteredBots.filter((b) => { const s = getBotStatus(b); return s === 'active' || s === 'running'; }).length, color: 'var(--success)' },
              { label: 'Paused', value: filteredBots.filter((b) => getBotStatus(b) === 'paused').length, color: '#f59e0b' },
              { label: 'Training', value: filteredBots.filter((b) => getBotStatus(b) === 'training').length, color: 'var(--accent2)' },
            ].map((m) => (
              <div key={m.label} style={{ display: 'flex', gap: 6, alignItems: 'center', fontSize: 13 }}>
                <span style={{ color: 'var(--muted)' }}>{m.label}:</span>
                <span style={{ color: m.color || 'var(--text)', fontWeight: 600 }}>{m.value}</span>
              </div>
            ))}
          </div>

          {/* ── Bot Grid + Detail panel ────────────────────── */}
          {filteredBots.length === 0 ? (
            <div style={{ textAlign: 'center', padding: 40, color: 'var(--muted)' }}>
              {bots.length === 0 ? 'No bots deployed yet. Create one in Bot Management.' : 'No bots match current filters.'}
            </div>
          ) : (
            <div style={{ display: 'flex', gap: 20, flexWrap: 'wrap' }}>
              {/* Bot cards column */}
              <div style={{ flex: '1 1 380px', minWidth: 320, display: 'flex', flexDirection: 'column', gap: 10 }}>
                {filteredBots.map((bot) => {
                  const st = getBotStatus(bot);
                  const isSelected = bot.id === selectedBotDetailId;
                  return (
                    <div
                      key={bot.id}
                      style={{ ...S.card, ...(isSelected ? S.cardSelected : {}) }}
                      onClick={() => selectBot(bot.id)}
                      role="button"
                      tabIndex={0}
                      onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') selectBot(bot.id); }}
                    >
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
                        <span style={{ color: 'var(--text)', fontWeight: 600, fontSize: 14 }}>
                          {bot.name || `Bot ${bot.id?.slice(-6) || '?'}`}
                        </span>
                        <span style={S.pill(statusColor(st))}>{statusLabel(st)}</span>
                      </div>
                      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 12, fontSize: 12 }}>
                        <span style={{ color: 'var(--muted)' }}>
                          {getPlatformDisplayName(bot.exchange)}
                        </span>
                        <span style={{ color: modeColor(bot), fontWeight: 600 }}>
                          {modeLabel(bot)}
                        </span>
                        <span style={{ color: safeNum(bot.profit) >= 0 ? 'var(--success)' : 'var(--error)' }}>
                          {fmtZAR(bot.profit)}
                        </span>
                        <span style={{ color: 'var(--muted)' }}>
                          Cap: {fmtZAR(bot.current_capital)}
                        </span>
                        <span style={{ color: 'var(--muted)' }}>
                          WR: {fmtPct(bot.win_rate)}
                        </span>
                      </div>
                    </div>
                  );
                })}
              </div>

              {/* Detail panel */}
              {selectedBot && detailSections && (
                <div style={{
                  flex: '1 1 360px', minWidth: 300, maxWidth: 480,
                  background: 'var(--glass)', border: '1px solid var(--line)',
                  borderRadius: 'var(--radius-md, 14px)', padding: 20,
                  alignSelf: 'flex-start', position: 'sticky', top: 16,
                }}>
                  {/* Detail header */}
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
                    {editingBotId === selectedBot.id ? (
                      <form onSubmit={submitRename} style={{ display: 'flex', gap: 6, flex: 1 }}>
                        <input
                          type="text"
                          value={editingBotName}
                          onChange={(e) => setEditingBotName(e.target.value)}
                          style={{
                            flex: 1, padding: '4px 8px', borderRadius: 6,
                            border: '1px solid var(--line)', background: 'var(--surface, rgba(12,19,44,0.74))',
                            color: 'var(--text)', fontSize: 14, outline: 'none',
                          }}
                          autoFocus
                        />
                        <button type="submit" style={S.btn('primary')}>Save</button>
                        <button type="button" style={S.btn()} onClick={cancelRename}>✕</button>
                      </form>
                    ) : (
                      <>
                        <h3 style={{ color: 'var(--text)', margin: 0, fontSize: 16 }}>
                          {selectedBot.name || `Bot ${selectedBot.id?.slice(-6)}`}
                        </h3>
                        <button style={{ ...S.btn(), padding: '4px 8px', fontSize: 12 }} onClick={() => startRename(selectedBot)} title="Rename bot">
                          ✏️
                        </button>
                      </>
                    )}
                    <button
                      style={{ ...S.btn(), padding: '4px 8px', fontSize: 12, marginLeft: 4 }}
                      onClick={() => selectBot(null)}
                      title="Close detail"
                    >
                      ✕
                    </button>
                  </div>

                  {/* Detail tabs */}
                  <div style={{ display: 'flex', gap: 0, borderBottom: '1px solid var(--line)', marginBottom: 14 }}>
                    {DETAIL_TABS.map((t) => (
                      <button
                        key={t.key}
                        style={S.tab((botDetailTab || 'overview') === t.key)}
                        onClick={() => setBotDetailTab(t.key)}
                      >
                        {t.label}
                      </button>
                    ))}
                  </div>

                  {/* Overview tab */}
                  {(botDetailTab || 'overview') === 'overview' && (
                    <div>
                      {detailSections.overview.map((row) => (
                        <div key={row.label} style={S.detailRow}>
                          <span style={S.detailLabel}>{row.label}</span>
                          <span style={{ ...S.detailValue, ...(row.color ? { color: row.color } : {}) }}>{row.value}</span>
                        </div>
                      ))}
                    </div>
                  )}

                  {/* Performance tab */}
                  {(botDetailTab || 'overview') === 'performance' && (
                    <div>
                      {detailSections.performance.map((row) => (
                        <div key={row.label} style={S.detailRow}>
                          <span style={S.detailLabel}>{row.label}</span>
                          <span style={{ ...S.detailValue, ...(row.color ? { color: row.color } : {}) }}>{row.value}</span>
                        </div>
                      ))}
                    </div>
                  )}

                  {/* Controls tab */}
                  {(botDetailTab || 'overview') === 'controls' && (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                      {(() => {
                        const st = getBotStatus(selectedBot);
                        const loading = botControlLoading;
                        return (
                          <>
                            {st === 'paused' && handleResumeBot && (
                              <button style={S.btn('success')} disabled={loading} onClick={() => handleResumeBot(selectedBot.id)}>
                                {loading ? '...' : '▶ Resume Bot'}
                              </button>
                            )}
                            {(st === 'stopped' || st === 'inactive') && handleStartBot && (
                              <button style={S.btn('success')} disabled={loading} onClick={() => handleStartBot(selectedBot.id)}>
                                {loading ? '...' : '▶ Start Bot'}
                              </button>
                            )}
                            {(st === 'active' || st === 'running') && (
                              <span style={{ color: 'var(--success)', fontSize: 13 }}>✅ Bot is running</span>
                            )}
                            {handleToggleBotMode && (
                              <button
                                style={S.btn(modeLabel(selectedBot) === 'PAPER' ? 'success' : 'warning')}
                                disabled={loading}
                                onClick={() => handleToggleBotMode(selectedBot.id)}
                              >
                                {loading ? '...' : `Switch to ${modeLabel(selectedBot) === 'LIVE' ? 'Paper' : 'Live'} Mode`}
                              </button>
                            )}
                            <div style={{ borderTop: '1px solid var(--line)', paddingTop: 10, marginTop: 4 }}>
                              {confirmDelete === selectedBot.id ? (
                                <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                                  <span style={{ color: 'var(--error)', fontSize: 13 }}>Confirm delete?</span>
                                  <button
                                    style={S.btn('danger')}
                                    disabled={loading}
                                    onClick={() => { handleDeleteBot(selectedBot.id); setConfirmDelete(null); setSelectedBotDetailId(null); }}
                                  >
                                    Yes, Delete
                                  </button>
                                  <button style={S.btn()} onClick={() => setConfirmDelete(null)}>Cancel</button>
                                </div>
                              ) : (
                                <button style={S.btn('danger')} onClick={() => setConfirmDelete(selectedBot.id)}>
                                  🗑 Delete Bot
                                </button>
                              )}
                            </div>
                          </>
                        );
                      })()}
                    </div>
                  )}
                </div>
              )}
            </div>
          )}
        </>
      )}
    </section>
  );
}
