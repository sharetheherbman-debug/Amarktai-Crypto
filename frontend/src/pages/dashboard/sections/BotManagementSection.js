import React from 'react';
import SectionHeader from '@/ui/components/SectionHeader';
import TrainingQuarantineSection from '../../../components/Dashboard/TrainingQuarantineSection';
import ScalperBotsPanel from './ScalperBotsPanel';
import { getPlatformDisplayName, getPlatformIcon, SUPPORTED_PLATFORMS } from '../../../constants/platforms';
import { getAllExchanges } from '../../../config/exchanges';

const NOT_AVAILABLE = 'Not available';

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

const humanizeReason = (reason) => {
  if (!reason) return NOT_AVAILABLE;
  const raw = String(reason).trim();
  if (!raw || raw === '-' || raw === '--') return NOT_AVAILABLE;
  const toTitleCase = (value) => value.replace(/\w\S*/g, (word) =>
    word.charAt(0).toUpperCase() + word.slice(1).toLowerCase()
  );
  const normalizedCode = raw.replace(/[-\s]+/g, '_').replace(/_+/g, '_').toUpperCase();
  const SPAWN_REASON_LABELS = {
    PROFIT_TOO_LOW: 'Profit too low', NOT_READY: 'Not ready', COOLDOWN_ACTIVE: 'Cooldown active',
    MAX_SPAWNS_REACHED: 'Daily limit reached', INSUFFICIENT_BALANCE: 'Insufficient balance',
    NOT_ENABLED: 'Not enabled', ELIGIBLE: 'Eligible',
  };
  if (SPAWN_REASON_LABELS[normalizedCode]) return SPAWN_REASON_LABELS[normalizedCode];
  if (!/[_-]/.test(raw) && /[a-z]/.test(raw)) return raw;
  return toTitleCase(raw.replace(/[-_]+/g, ' ').toLowerCase());
};

const formatReasonInline = (reason) => {
  if (!reason) return NOT_AVAILABLE;
  const raw = String(reason).trim();
  const [codePart, detailPart] = raw.split('(');
  const title = humanizeReason(codePart);
  const details = detailPart ? detailPart.replace(')', '').trim() : '';
  return details ? `${title} — ${details}` : title;
};

export default function BotManagementSection({
  autoSpawnStatus,
  autopilotReinvestStatus,
  axiosConfig,
  botManagementTab,
  formatDate,
  handleCreateBot,
  handleCreateUAgent,
  setBotManagementTab,
  handleBotSetup,
  botSetup,
  setBotSetup,
}) {
  return (
    <section className="section active">
      <div className="card">
        <SectionHeader
          title="🤖 Bot Management"
          subtitle="Create and deploy trading bots. Use Bot Fleet to monitor and control them."
        />
        <div className="bot-tabs">
          <button
            className={`bot-tab ${botManagementTab === 'creation' ? 'active' : ''}`}
            onClick={() => setBotManagementTab('creation')}
          >
            🤖 Normal Bot Creator
          </button>
          <button
            className={`bot-tab ${botManagementTab === 'scalper' ? 'active' : ''}`}
            onClick={() => setBotManagementTab('scalper')}
          >
            ⚡ Scalper Bot Creator
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

        {botManagementTab === 'scalper' && (
          <ScalperBotsPanel axiosConfig={axiosConfig || { headers: {} }} />
        )}

        {botManagementTab === 'creation' && (
          <div>
            <div className="bot-form-stack">
              <div className="bot-form-card">
                <h3>🤖 Normal Bot Creator</h3>
                <p style={{color: 'var(--muted)', fontSize: '0.85rem', marginBottom: '12px'}}>
                  Standard trading bot with a 7-day learning period. Starts in paper mode automatically.
                </p>
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
                    {/* Hidden field ensures bot_type is always sent as 'normal' */}
                    <input type="hidden" name="bot-type" value="normal" />
                    <div>
                      <button type="submit">Create Bot (7 Day Learning)</button>
                    </div>
                  </div>
                </form>
              </div>

              <div className="bot-form-card">
                <h3>Fetch.ai uAgents</h3>
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
            <p style={{ color: 'var(--muted)', fontSize: '0.82rem', marginTop: '12px' }}>
              💡 To monitor and control your bots, go to <strong>Bot Fleet</strong> in the sidebar.
              To create a ⚡ Scalper Bot, use the <strong>Scalper Bots</strong> tab above.
            </p>
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
