import React from 'react';
import SectionHeader from '@/ui/components/SectionHeader';
import PlatformSelector from '../../../components/PlatformSelector';
import TrainingQuarantineSection from '../../../components/Dashboard/TrainingQuarantineSection';
import { getBotStatus } from '../../../hooks/useDashboardData';
import { getPlatformDisplayName, getPlatformIcon, SUPPORTED_PLATFORMS } from '../../../constants/platforms';
import { getAllExchanges } from '../../../config/exchanges';

const NOT_AVAILABLE = 'Not available';

const safeToFixed = (value, digits = 2, fallback = '0.00') => {
  const num = Number(value);
  return Number.isFinite(num) ? num.toFixed(digits) : fallback;
};

const safeNumber = (value, fallback = 0) => {
  const num = Number(value);
  return Number.isFinite(num) ? num : fallback;
};

const formatZAR = (value, digits = 2, fallback = NOT_AVAILABLE) => {
  const num = Number(value);
  if (!Number.isFinite(num)) return fallback;
  const formatted = Math.abs(num).toLocaleString('en-US', { minimumFractionDigits: digits, maximumFractionDigits: digits });
  return `${num < 0 ? '-R' : 'R'}${formatted}`;
};

const toTitleCase = (value) => value.replace(/\w\S*/g, (word) =>
  word.charAt(0).toUpperCase() + word.slice(1).toLowerCase()
);

const humanizeReason = (reason) => {
  if (!reason) return NOT_AVAILABLE;
  const raw = String(reason).trim();
  if (!raw || raw === '-' || raw === '--') return NOT_AVAILABLE;
  const normalizedCode = raw.replace(/[-\s]+/g, '_').replace(/_+/g, '_').toUpperCase();
  const SPAWN_REASON_LABELS = {
    PROFIT_TOO_LOW: 'Profit too low',
    NOT_READY: 'Not ready',
    COOLDOWN_ACTIVE: 'Cooldown active',
    MAX_SPAWNS_REACHED: 'Daily limit reached',
    INSUFFICIENT_BALANCE: 'Insufficient balance',
    NOT_ENABLED: 'Not enabled',
    ELIGIBLE: 'Eligible'
  };
  if (SPAWN_REASON_LABELS[normalizedCode]) return SPAWN_REASON_LABELS[normalizedCode];
  if (!/[_-]/.test(raw) && /[a-z]/.test(raw)) return raw;
  return toTitleCase(raw.replace(/[-_]+/g, ' ').toLowerCase());
};

const formatReasonInline = (reason) => {
  const formatSpawnReason = (r) => {
    if (!r) return { title: NOT_AVAILABLE, details: '' };
    const raw = String(r).trim();
    const [codePart, detailPart] = raw.split('(');
    const title = humanizeReason(codePart);
    let details = detailPart ? detailPart.replace(')', '').trim() : '';
    return { title, details };
  };
  const info = formatSpawnReason(reason);
  if (!info.details) return info.title;
  return `${info.title} — ${info.details}`;
};

const formatDuration = (seconds) => {
  if (seconds === null || seconds === undefined || Number.isNaN(seconds)) return NOT_AVAILABLE;
  const totalSeconds = Math.max(0, Math.floor(seconds));
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const secs = totalSeconds % 60;
  if (hours > 0) return `${hours}h ${minutes}m`;
  if (minutes > 0) return `${minutes}m ${secs}s`;
  return `${secs}s`;
};

export default function BotManagementSection({
  autoSpawnStatus,
  autopilotReinvestStatus,
  botDetailTab,
  botManagementTab,
  botStatusFilter,
  bots,
  formatDate,
  handleCreateBot,
  handleCreateFlokxBot,
  handleCreateUAgent,
  handleDeleteBot,
  handleResumeBot,
  handleStartBot,
  handleToggleBotMode,
  platformFilter,
  selectedBotDetailId,
  setBotDetailTab,
  setBotManagementTab,
  setBotStatusFilter,
  setPlatformFilter,
  setSelectedBotDetailId,
  botSetup,
  setBotSetup,
  activeBotTab,
  setActiveBotTab,
  editingBotId,
  setEditingBotId,
  editingBotName,
  setEditingBotName,
  handleBotSetup,
  botControlLoading,
  handleRenameBotSubmit,
}) {
  const matchesStatusFilter = (bot) => {
    const status = getBotStatus(bot);
    if (botStatusFilter === 'active') return status === 'active';
    if (botStatusFilter === 'paused') return ['paused', 'paused_ready', 'paused_by_user'].includes(status);
    if (botStatusFilter === 'training') return status?.includes('train') || bot?.training_complete === false;
    if (botStatusFilter === 'quarantined') return status?.includes('quarantine') || bot?.quarantine_active || bot?.in_quarantine;
    return true;
  };

  const filteredBots = bots.filter(bot =>
    (platformFilter === 'all' || bot.exchange === platformFilter) && matchesStatusFilter(bot)
  );

  const resolvedSelectedBotId = filteredBots.some(bot => bot.id === selectedBotDetailId)
    ? selectedBotDetailId
    : null;

  const selectedBot = resolvedSelectedBotId ? filteredBots.find(bot => bot.id === resolvedSelectedBotId) : null;
  const selectedBotMode = selectedBot?.trading_mode || selectedBot?.mode || 'paper';
  const selectedIsLive = selectedBotMode === 'live';
  const selectedStatus = selectedBot ? getBotStatus(selectedBot) : null;
  const selectedStatusLabel = selectedBot ? humanizeReason(selectedStatus) : NOT_AVAILABLE;
  const selectedPauseReason = selectedBot?.paused_reason_message || selectedBot?.paused_reason;
  const selectedPauseReasonDisplay = selectedPauseReason ? formatReasonInline(selectedPauseReason) : NOT_AVAILABLE;
  const selectedExchangeLabel = selectedBot?.exchange
    ? getPlatformDisplayName(selectedBot.exchange)
    : NOT_AVAILABLE;

  const formatPercentValue = (value, digits = 1) => {
    const num = Number(value);
    return Number.isFinite(num) ? `${num.toFixed(digits)}%` : NOT_AVAILABLE;
  };

  const formatDetailValue = (value) => {
    if (value === null || value === undefined || value === '') return NOT_AVAILABLE;
    if (typeof value === 'boolean') return value ? 'Yes' : 'No';
    if (typeof value === 'number') return Number.isFinite(value) ? value.toLocaleString('en-ZA') : NOT_AVAILABLE;
    if (typeof value === 'object') {
      try {
        return JSON.stringify(value);
      } catch (error) {
        return NOT_AVAILABLE;
      }
    }
    return String(value);
  };

  const botDetailSections = selectedBot ? {
    overview: [
      { label: 'Status', value: selectedStatusLabel },
      { label: 'Mode', value: selectedIsLive ? 'Live' : 'Paper' },
      { label: 'Exchange', value: selectedExchangeLabel },
      { label: 'Pair', value: selectedBot.pair || selectedBot.symbol || selectedBot.market || NOT_AVAILABLE },
      { label: 'Last Trade', value: formatDate(selectedBot.last_trade_time || selectedBot.last_trade_at || selectedBot.last_trade_timestamp) },
      { label: 'Training Complete', value: formatDetailValue(selectedBot.training_complete) }
    ],
    performance: [
      { label: 'Current Capital', value: formatZAR(selectedBot.current_capital) },
      { label: 'Profit', value: formatZAR(selectedBot.profit ?? selectedBot.profit_loss ?? selectedBot.pnl) },
      { label: 'Trades', value: safeNumber(selectedBot.trades_count, 0) },
      { label: 'Win Rate', value: formatPercentValue(selectedBot.win_rate ?? selectedBot.win_rate_pct ?? selectedBot.winRate) },
      { label: 'ROI', value: formatPercentValue(selectedBot.roi ?? selectedBot.roi_pct) }
    ],
    risk: [
      { label: 'Risk Mode', value: selectedBot.risk_mode || selectedBot.risk_profile || selectedBot.riskLevel || NOT_AVAILABLE },
      { label: 'Risk State', value: selectedBot.risk_state || selectedBot.risk_level || NOT_AVAILABLE },
      { label: 'Pause Reason', value: selectedPauseReasonDisplay },
      { label: 'Quarantine', value: formatDetailValue(selectedBot.quarantine_active ?? selectedBot.in_quarantine) }
    ],
    trades: [
      { label: 'Last Trade', value: formatDate(selectedBot.last_trade_time || selectedBot.last_trade_at || selectedBot.last_trade_timestamp) },
      { label: 'Last Trade P/L', value: formatZAR(selectedBot.last_trade_profit ?? selectedBot.last_trade_pnl ?? selectedBot.last_trade_pl) },
      { label: 'Last Trade Price', value: formatZAR(selectedBot.last_trade_price) },
      { label: 'Avg Trade Duration', value: selectedBot.avg_trade_duration ? formatDuration(selectedBot.avg_trade_duration) : NOT_AVAILABLE }
    ],
    settings: [
      { label: 'Strategy', value: selectedBot.strategy || selectedBot.strategy_preset || selectedBot.strategy_name || NOT_AVAILABLE },
      { label: 'Risk Profile', value: selectedBot.risk_profile || NOT_AVAILABLE },
      { label: 'Bot ID', value: selectedBot.id || NOT_AVAILABLE },
      { label: 'Created At', value: formatDate(selectedBot.created_at) }
    ]
  } : null;

  const selectedStatusTone = selectedBot
    ? (selectedStatus === 'active' ? 'ok' : (['paused', 'paused_ready'].includes(selectedStatus) ? 'paused' : 'warn'))
    : 'warn';
  const selectedIsPaused = selectedBot ? ['paused', 'paused_ready'].includes(selectedStatus) : false;
  const selectedCanStart = selectedBot ? ['stopped', 'inactive', 'unknown'].includes(selectedStatus) : false;

  const renderBotDetailGrid = (items) => (
    <div className="bot-detail-grid">
      {items.map((item) => (
        <div key={item.label} className="bot-detail-item">
          <span>{item.label}</span>
          <strong>{item.value}</strong>
        </div>
      ))}
    </div>
  );

  return (
    <section className="section active">
      <div className="card">
        <SectionHeader
          title="🤖 Bot Management"
          subtitle="Track active bots, pause states, and drill into detailed bot telemetry."
        />
        <div className="bot-filter-row">
          {[
            { id: 'all', label: 'All' },
            { id: 'active', label: 'Active' },
            { id: 'paused', label: 'Paused' },
            { id: 'training', label: 'Training' },
            { id: 'quarantined', label: 'Quarantined' }
          ].map(filter => (
            <button
              key={filter.id}
              type="button"
              className={`bot-filter-chip ${botStatusFilter === filter.id ? 'active' : ''}`}
              onClick={() => setBotStatusFilter(filter.id)}
            >
              {filter.label}
            </button>
          ))}
        </div>
        <div className="bot-tabs">
          <button
            className={`bot-tab ${botManagementTab === 'creation' ? 'active' : ''}`}
            onClick={() => setBotManagementTab('creation')}
          >
            Overview
          </button>
          <button
            className={`bot-tab ${botManagementTab === 'training_quarantine' ? 'active' : ''}`}
            onClick={() => setBotManagementTab('training_quarantine')}
          >
            Training & Quarantine
          </button>
          <button
            className={`bot-tab ${botManagementTab === 'spawn' ? 'active' : ''}`}
            onClick={() => setBotManagementTab('spawn')}
          >
            Spawn Status
          </button>
        </div>

        {botManagementTab === 'creation' && (
          <div className="bot-container">
            <div className="bot-left">
              <div className="bot-form-stack">
                <div className="bot-management-section">
                  <div className="bot-section-header">
                    <h2>🤖 Create a New Bot</h2>
                  </div>
                  <div className="bot-form-card">
                    <h3>Bot Configuration</h3>
                    <form onSubmit={handleCreateBot}>
                      <div className="bot-form-grid">
                        <div>
                          <label htmlFor="bot-name">Bot Name</label>
                          <input id="bot-name" name="bot-name" placeholder="My Trading Bot" type="text" required />
                        </div>
                        <div>
                          <label htmlFor="bot-budget">Budget (Min R1000)</label>
                          <input
                            id="bot-budget"
                            name="bot-budget"
                            type="number"
                            min="1000"
                            step="100"
                            defaultValue="1000"
                            required
                          />
                        </div>
                        <div>
                          <label htmlFor="bot-exchange">Exchange Platform</label>
                          <select id="bot-exchange" name="bot-exchange" defaultValue="luno">
                            {getAllExchanges().map(exchange => (
                              <option
                                key={exchange.id}
                                value={exchange.id}
                                disabled={exchange.comingSoon}
                              >
                                {exchange.icon} {exchange.displayName}
                              </option>
                            ))}
                          </select>
                        </div>
                        <div>
                          <label htmlFor="bot-risk">Risk Mode</label>
                          <select id="bot-risk" name="bot-risk">
                            <option value="safe">Safe</option>
                            <option value="balanced">Balanced</option>
                            <option value="aggressive">Aggressive</option>
                          </select>
                        </div>
                        <div>
                          <label htmlFor="bot-strategy">Strategy Preset</label>
                          <select id="bot-strategy" name="bot-strategy" defaultValue="adaptive">
                            <option value="adaptive">Adaptive Core</option>
                            <option value="trend">Trend Follow</option>
                            <option value="mean_reversion">Mean Reversion</option>
                            <option value="scalping">Scalping</option>
                          </select>
                        </div>
                        <div>
                          <button type="submit">Create Bot (7 Day Learning)</button>
                        </div>
                      </div>
                    </form>
                  </div>
                </div>

                <div className="bot-management-section">
                  <div className="bot-section-header">
                    <h2>🔮 Fetch.ai uAgents</h2>
                  </div>
                  <div className="bot-form-card">
                    <h3>Deploy Custom Agent</h3>
                    <form onSubmit={handleCreateUAgent}>
                      <div className="bot-form-grid">
                        <div>
                          <label htmlFor="uagent-name">uAgent Name</label>
                          <input id="uagent-name" name="uagent-name" placeholder="Custom Agent" type="text" required />
                        </div>
                        <div>
                          <label htmlFor="uagent-strategy">Strategy</label>
                          <select id="uagent-strategy" name="uagent-strategy" defaultValue="adaptive">
                            <option value="adaptive">Adaptive</option>
                            <option value="trend">Trend</option>
                            <option value="mean_reversion">Mean Reversion</option>
                          </select>
                        </div>
                        <div>
                          <label htmlFor="uagent-file">Upload File (.py)</label>
                          <input id="uagent-file" name="uagent-file" type="file" accept=".py" required />
                        </div>
                        <div>
                          <button type="submit">Deploy uAgent</button>
                        </div>
                      </div>
                    </form>
                  </div>
                </div>

                <div className="bot-management-section">
                  <div className="bot-section-header">
                    <h2>🎯 FlokX Alert Bot</h2>
                  </div>
                  <div className="bot-form-card">
                    <h3>Configure Alert Bot</h3>
                    <form onSubmit={handleCreateFlokxBot}>
                      <div className="bot-form-grid">
                        <div>
                          <label htmlFor="flokx-name">Bot Name</label>
                          <input id="flokx-name" name="flokx-name" placeholder="FlokX Sentinel" type="text" required />
                        </div>
                        <div>
                          <label htmlFor="flokx-signal">Signal Type</label>
                          <select id="flokx-signal" name="flokx-signal" defaultValue="momentum">
                            <option value="momentum">Momentum</option>
                            <option value="breakout">Breakout</option>
                            <option value="mean_reversion">Mean Reversion</option>
                          </select>
                        </div>
                        <div>
                          <label htmlFor="flokx-risk">Risk Level</label>
                          <select id="flokx-risk" name="flokx-risk" defaultValue="balanced">
                            <option value="safe">Safe</option>
                            <option value="balanced">Balanced</option>
                            <option value="aggressive">Aggressive</option>
                          </select>
                        </div>
                        <div>
                          <button type="submit">Create FlokX Bot</button>
                        </div>
                      </div>
                    </form>
                  </div>
                </div>
              </div>
            </div>

            <div className="bot-right">
              <div className="bot-summary-header">
                <div>
                  <h3 style={{margin: 0}}>Bot Fleet</h3>
                  <p>Monitor live status and drill into full bot detail.</p>
                </div>
                <PlatformSelector
                  value={platformFilter}
                  onChange={setPlatformFilter}
                  includeAll={true}
                />
              </div>
              <div className="bot-list">
                {filteredBots.length === 0 ? (
                  <p className="bot-empty">No bots available.</p>
                ) : (
                  filteredBots.map(bot => {
                    const botMode = bot.trading_mode || bot.mode || 'paper';
                    const isLive = botMode === 'live';
                    const botStatus = getBotStatus(bot);
                    const statusLabel = humanizeReason(botStatus);
                    const isActive = botStatus === 'active';
                    const isPaused = ['paused', 'paused_ready'].includes(botStatus);
                    const statusTone = isActive ? 'ok' : (isPaused ? 'paused' : 'warn');
                    const isExpanded = resolvedSelectedBotId === bot.id;

                    return (
                      <div key={bot.id} className={`bot-list-item-wrapper ${isExpanded ? 'expanded' : ''}`}>
                        <button
                          type="button"
                          className={`bot-list-item ${isExpanded ? 'active' : ''}`}
                          onClick={() => {
                            setSelectedBotDetailId(isExpanded ? null : bot.id);
                            setBotDetailTab('overview');
                          }}
                        >
                          <div className="bot-list-main">
                            <strong>{bot.name || 'Bot'}</strong>
                            <span className="bot-list-meta">
                              {getPlatformDisplayName(bot.exchange) || NOT_AVAILABLE} • {isLive ? 'Live' : 'Paper'}
                            </span>
                          </div>
                          <span className={`bot-status-pill ${statusTone}`}>{statusLabel}</span>
                        </button>
                        {/* Accordion detail dropdown */}
                        {isExpanded && selectedBot && (
                          <div className="bot-accordion-body">
                            <div className="bot-detail-header">
                              <div>
                                <span>
                                  {selectedExchangeLabel} • {selectedIsLive ? 'Live' : 'Paper'} • {selectedStatusLabel}
                                </span>
                              </div>
                              <span className={`bot-status-pill ${selectedStatusTone}`}>{selectedStatusLabel}</span>
                            </div>
                            {selectedPauseReasonDisplay !== NOT_AVAILABLE && (
                              <div className="bot-detail-alert">
                                <strong>Pause reason:</strong> {selectedPauseReasonDisplay}
                              </div>
                            )}
                            <div className="bot-detail-tabs">
                              {['overview', 'performance', 'risk', 'trades', 'settings'].map(tab => (
                                <button
                                  key={tab}
                                  type="button"
                                  className={`bot-detail-tab ${botDetailTab === tab ? 'active' : ''}`}
                                  onClick={() => setBotDetailTab(tab)}
                                >
                                  {tab}
                                </button>
                              ))}
                            </div>
                            <div className="bot-detail-body">
                              {botDetailTab === 'overview' && renderBotDetailGrid(botDetailSections.overview)}
                              {botDetailTab === 'performance' && renderBotDetailGrid(botDetailSections.performance)}
                              {botDetailTab === 'risk' && renderBotDetailGrid(botDetailSections.risk)}
                              {botDetailTab === 'trades' && renderBotDetailGrid(botDetailSections.trades)}
                              {botDetailTab === 'settings' && (
                                <div className="bot-detail-settings">
                                  {renderBotDetailGrid(botDetailSections.settings)}
                                  <div className="bot-detail-raw">
                                    {Object.entries(selectedBot).map(([key, value]) => (
                                      <div key={key} className="bot-detail-row">
                                        <span className="bot-detail-key">{toTitleCase(key.replace(/_/g, ' '))}</span>
                                        <span className="bot-detail-value">{formatDetailValue(value)}</span>
                                      </div>
                                    ))}
                                  </div>
                                </div>
                              )}
                            </div>
                            <div className="bot-detail-actions">
                              {selectedIsPaused && (
                                <button onClick={() => handleResumeBot(selectedBot.id)}>
                                  ▶ Resume
                                </button>
                              )}
                              {!selectedIsPaused && selectedCanStart && (
                                <button onClick={() => handleStartBot(selectedBot.id)}>
                                  🚀 Start
                                </button>
                              )}
                              <button onClick={() => handleToggleBotMode(selectedBot.id, selectedBotMode)}>
                                {selectedIsLive ? 'Switch to Paper' : 'Switch to Live'}
                              </button>
                              <button className="danger" onClick={() => handleDeleteBot(selectedBot.id)}>
                                Delete
                              </button>
                            </div>
                          </div>
                        )}
                      </div>
                    );
                  })
                )}
              </div>
            </div>
          </div>
        )}

        {botManagementTab === 'training_quarantine' && (
          <TrainingQuarantineSection />
        )}

        {botManagementTab === 'spawn' && (
          <div style={{display: 'grid', gap: '16px'}}>
            <div className="bot-form-card">
              <h3>Auto-Spawn Status</h3>
              {autoSpawnStatus ? (
                <>
                  <div style={{fontSize: '0.8rem', color: 'var(--muted)'}}>
                    Mode: {autoSpawnStatus.trading_mode?.toUpperCase() || 'PAPER'} • Threshold: {formatZAR(autoSpawnStatus.profit_threshold, 0)} • Cooldown: {safeNumber(autoSpawnStatus.cooldown_minutes, 0)} min • Max/day: {safeNumber(autoSpawnStatus.max_spawns_per_day, 0)}
                  </div>
                  <div style={{display: 'grid', gap: '8px', marginTop: '12px'}}>
                    {SUPPORTED_PLATFORMS.map(exchange => {
                      const reason = autoSpawnStatus.reason_per_exchange?.[exchange];
                      const profit = autoSpawnStatus.current_profit_per_exchange?.[exchange];
                      const spawns = autoSpawnStatus.spawn_count_today_per_exchange?.[exchange];
                      const lastSpawn = autoSpawnStatus.last_spawn_time_per_exchange?.[exchange];
                      return (
                        <div key={`spawn-${exchange}`} style={{padding: '10px', borderRadius: '8px', background: 'var(--panel)'}}>
                          <div style={{fontSize: '0.85rem', color: 'var(--text)'}}>
                            {getPlatformIcon(exchange)} {getPlatformDisplayName(exchange)} • {formatReasonInline(reason)}
                          </div>
                          <div style={{fontSize: '0.75rem', color: 'var(--muted)'}}>
                            Profit: {formatZAR(profit)} • Spawns today: {safeNumber(spawns, 0)} • Last: {formatDate(lastSpawn)}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </>
              ) : (
                <div style={{color: 'var(--muted)', fontSize: '0.85rem'}}>Auto-spawn status unavailable.</div>
              )}
            </div>

            {autopilotReinvestStatus && (
              <div className="bot-form-card">
                <h3>Autopilot Reinvest</h3>
                <div style={{fontSize: '0.8rem', color: 'var(--muted)'}}>
                  Minimum reinvest: {formatZAR(autopilotReinvestStatus.min_reinvest_zar ?? 100, 0)} • {autopilotReinvestStatus.enabled ? 'Enabled' : 'Disabled'}
                </div>
                <div style={{display: 'grid', gap: '8px', marginTop: '12px'}}>
                  {SUPPORTED_PLATFORMS.map(exchange => {
                    const status = autopilotReinvestStatus.platforms?.[exchange] || {};
                    const reasonFlags = [];
                    if (!autopilotReinvestStatus.enabled) {
                      reasonFlags.push('Autopilot Reinvest Disabled');
                    }
                    if (status.blocked_reasons?.includes('AUTOPILOT_OFF_FOR_USER')) {
                      reasonFlags.push('Autopilot Off For User');
                    }
                    if (Number.isFinite(status.bots_current) && Number.isFinite(status.bots_max) && status.bots_current < status.bots_max) {
                      reasonFlags.push('Bots Not Maxed');
                    }
                    const reasonLine = reasonFlags.length > 0 ? reasonFlags.join(' • ') : (status.eligible ? 'Eligible' : 'Check guardrails');
                    return (
                      <div key={`reinvest-${exchange}`} style={{padding: '10px', borderRadius: '8px', background: 'var(--panel)'}}>
                        <div style={{fontSize: '0.85rem', color: 'var(--text)'}}>
                          {getPlatformIcon(exchange)} {getPlatformDisplayName(exchange)} • {reasonLine}
                        </div>
                        <div style={{fontSize: '0.75rem', color: 'var(--muted)'}}>
                          Last Reinvest: {formatDate(status.last_reinvest_date)} • Amount: {formatZAR(status.last_reinvest_amount)} • Next run: {formatDate(status.next_run)}
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </section>
  );
}
