import SectionHeader from '@/ui/components/SectionHeader';
import GlassCard from '@/ui/components/GlassCard';

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
  const formatted = Math.abs(num).toLocaleString('en-US', {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits
  });
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

export default function OverviewSection({
  user,
  aiStatus,
  autonomyStatus,
  botControlLoading,
  flokxAlerts,
  formatDate,
  handleResetBodyguardLock,
  handleResetDailyLossLock,
  handleResumeAllBots,
  learningStatus,
  livePrices,
  metrics,
  modeLabel,
  overviewData,
  riskStatus,
  systemModes,
}) {
  const aiKeyConfigured = aiStatus?.key_configured;
  const formatOverviewDate = (value) => {
    const formatted = formatDate(value);
    return formatted;
  };
  const resolveReason = (value, fallback) => {
    const reasonText = humanizeReason(value);
    return reasonText === NOT_AVAILABLE ? fallback : reasonText;
  };
  const pricePairs = [
    { label: 'XBTZAR', key: 'BTC/ZAR' },
    { label: 'ETHZAR', key: 'ETH/ZAR' },
    { label: 'XRPZAR', key: 'XRP/ZAR' }
  ];
  const formatLivePrice = (value) => {
    const numeric = Number(value);
    if (!Number.isFinite(numeric)) return NOT_AVAILABLE;
    return `R${numeric.toLocaleString('en-ZA', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  };
  const formatStatusValue = (value) => {
    if (value === null || value === undefined || value === '') return NOT_AVAILABLE;
    if (typeof value === 'boolean') return value ? 'Active' : 'Idle';
    if (typeof value === 'string') return humanizeReason(value);
    if (typeof value === 'object') {
      return value.status || value.state || value.mode || NOT_AVAILABLE;
    }
    return String(value);
  };
  const autonomyItems = [
    { label: 'Autopilot', value: systemModes.autopilot },
    { label: 'Scheduler', value: autonomyStatus?.scheduler || autonomyStatus?.scheduler_status },
    { label: 'Self-Healing', value: autonomyStatus?.self_healing || autonomyStatus?.bodyguard || riskStatus?.bodyguard_lock?.active },
    { label: 'Learning', value: learningStatus?.status || learningStatus?.mode || learningStatus?.active }
  ];
  const lastAlert = Array.isArray(flokxAlerts) && flokxAlerts.length > 0 ? flokxAlerts[0] : null;
  const lastEventTitle = lastAlert?.title || lastAlert?.pair || (riskStatus?.emergency_stop?.active ? 'Emergency stop engaged' : 'System stable');
  const lastEventDetail = lastAlert?.message || lastAlert?.detail || (riskStatus?.daily_loss_lock?.active ? 'Daily loss lock active' : 'No critical alerts');
  const lastEventTime = lastAlert?.timestamp ? new Date(lastAlert.timestamp).toLocaleString() : formatOverviewDate(overviewData.lastTradeTime);

  return (
    <section className="section active">
      <div className="card">
        <SectionHeader
          title="Overview"
          subtitle="System live view, autonomy status, and real-time pricing."
        />

        {/* Risk Status Banner */}
        {riskStatus?.emergency_stop?.active && (
          <div style={{
            padding: '16px',
            background: 'linear-gradient(135deg, #ef4444 0%, #b91c1c 100%)',
            border: '2px solid #b91c1c',
            borderRadius: '8px',
            marginBottom: '20px',
            color: 'white'
          }}>
            <div style={{fontSize: '1.1rem', fontWeight: 700, marginBottom: '8px'}}>
              🚨 Emergency Stop Active: Trading Disabled
            </div>
            <div style={{fontSize: '0.9rem', marginBottom: '8px'}}>
              <strong>Reason:</strong> {resolveReason(riskStatus.emergency_stop.reason, 'No specific reason provided.')}
            </div>
            {riskStatus.emergency_stop.next_action && (
              <div style={{fontSize: '0.85rem', color: 'rgba(255,255,255,0.9)'}}>
                Next action: {riskStatus.emergency_stop.next_action}
              </div>
            )}
          </div>
        )}
        {riskStatus?.daily_loss_lock?.active && (
          <div style={{
            padding: '16px',
            background: 'linear-gradient(135deg, #ef4444 0%, #dc2626 100%)',
            border: '2px solid #dc2626',
            borderRadius: '8px',
            marginBottom: '20px',
            color: 'white'
          }}>
            <div style={{fontSize: '1.1rem', fontWeight: 700, marginBottom: '8px'}}>
              🛡️ Daily Loss Lock Active: Bots Paused for Protection
            </div>
            <div style={{fontSize: '0.9rem', marginBottom: '8px'}}>
              <strong>Reason:</strong> {resolveReason(riskStatus.daily_loss_lock.reason, 'Risk threshold exceeded')}
            </div>
            <div style={{fontSize: '0.85rem', color: 'rgba(255,255,255,0.9)'}}>
              Locked at: {formatDate(riskStatus.daily_loss_lock.locked_at)}
            </div>
            {riskStatus.daily_loss_lock.next_action && (
              <div style={{fontSize: '0.85rem', color: 'rgba(255,255,255,0.9)'}}>
                Next action: {riskStatus.daily_loss_lock.next_action}
              </div>
            )}
            {user?.is_admin && (
              <div style={{marginTop: '12px', display: 'flex', gap: '10px'}}>
                <button
                  onClick={handleResetDailyLossLock}
                  style={{
                    padding: '10px 16px',
                    background: 'white',
                    color: '#dc2626',
                    border: 'none',
                    borderRadius: '6px',
                    fontWeight: 600,
                    cursor: 'pointer'
                  }}
                >
                  🔓 Reset Daily Loss Lock
                </button>
                <button
                  onClick={handleResumeAllBots}
                  disabled={botControlLoading['all']}
                  style={{
                    padding: '10px 16px',
                    background: 'rgba(255,255,255,0.2)',
                    color: 'white',
                    border: '1px solid white',
                    borderRadius: '6px',
                    fontWeight: 600,
                    cursor: botControlLoading['all'] ? 'wait' : 'pointer',
                    opacity: botControlLoading['all'] ? 0.6 : 1
                  }}
                >
                  {botControlLoading['all'] ? '⏳ Resuming...' : '▶️ Resume All Bots'}
                </button>
              </div>
            )}
            {!user?.is_admin && (
              <div style={{marginTop: '12px', fontSize: '0.85rem', fontStyle: 'italic'}}>
                Admin access required to reset risk lock
              </div>
            )}
          </div>
        )}

        {(riskStatus?.bodyguard_lock?.active || riskStatus?.quarantine_active?.active) && (
          <div style={{
            padding: '16px',
            background: 'linear-gradient(135deg, rgba(56, 189, 248, 0.25) 0%, rgba(34, 197, 94, 0.2) 100%)',
            border: '1px solid rgba(56, 189, 248, 0.35)',
            borderRadius: '8px',
            marginBottom: '20px',
            color: 'white'
          }}>
            <div style={{fontSize: '1.1rem', fontWeight: 700, marginBottom: '8px'}}>
              🛡️ Bodyguard/Quarantine Lock Active
            </div>
            {riskStatus?.bodyguard_lock?.active && (
              <div style={{fontSize: '0.9rem', marginBottom: '6px'}}>
                <strong>Bodyguard:</strong> {resolveReason(riskStatus.bodyguard_lock.reason, 'Bots paused by bodyguard')}
              </div>
            )}
            {riskStatus?.quarantine_active?.active && (
              <div style={{fontSize: '0.9rem', marginBottom: '6px'}}>
                <strong>Quarantine:</strong> {resolveReason(riskStatus.quarantine_active.reason, 'Bots quarantined for retraining')}
              </div>
            )}
            {user?.is_admin ? (
              <div style={{marginTop: '12px', display: 'flex', gap: '10px', flexWrap: 'wrap'}}>
                <button
                  onClick={handleResetBodyguardLock}
                  style={{
                    padding: '10px 16px',
                    background: 'white',
                    color: '#0b0d14',
                    border: 'none',
                    borderRadius: '6px',
                    fontWeight: 600,
                    cursor: 'pointer'
                  }}
                >
                  🔓 Reset Bodyguard Locks
                </button>
              </div>
            ) : (
              <div style={{marginTop: '12px', fontSize: '0.85rem', fontStyle: 'italic'}}>
                Admin access required to reset bodyguard locks
              </div>
            )}
          </div>
        )}

        {/* Totals Row */}
        <div className="overview-totals-row">
          <GlassCard className="overview-total-card">
            <span>Total Profit</span>
            <strong style={{color: safeNumber(overviewData.totalProfit, 0) >= 0 ? 'var(--success)' : 'var(--error)'}}>
              {formatZAR(overviewData.totalProfit)}
            </strong>
          </GlassCard>
          <GlassCard className="overview-total-card">
            <span>Today Profit</span>
            <strong style={{color: safeNumber(overviewData.totalProfit, 0) >= 0 ? 'var(--success)' : 'var(--error)'}}>
              {formatZAR(overviewData.totalProfit)}
            </strong>
          </GlassCard>
          <GlassCard className="overview-total-card">
            <span>Trades</span>
            <strong>{safeNumber(overviewData.todaysTrades, 0)}</strong>
          </GlassCard>
          <GlassCard className="overview-total-card">
            <span>Win Rate</span>
            <strong>{safeToFixed(overviewData.winRate, 1, '0.0')}%</strong>
          </GlassCard>
        </div>

        <div className="overview-grid">
          <div className="overview-left-col">
            <div className="overview-image-card">
              <img src="/assets/background.jpg" alt="Trading workspace" className="overview-image-asset" />
            </div>
          </div>
          <div className="overview-right-col">
            <GlassCard className="overview-card">
              <div className="overview-card-header">
                <h3>Live Prices</h3>
                <span className="overview-card-meta">Updated {metrics.lastUpdate}</span>
              </div>
              <div className="overview-price-list">
                {pricePairs.map(({ label, key }) => {
                  const entry = livePrices?.[key] || {};
                  const change = Number(entry.change || 0);
                  return (
                    <div key={label} className="overview-price-row">
                      <div>
                        <span>{label}</span>
                        <strong>{formatLivePrice(entry.price)}</strong>
                      </div>
                      <span className={`overview-price-change ${change >= 0 ? 'up' : 'down'}`}>
                        {change >= 0 ? '+' : ''}{safeToFixed(change, 2)}%
                      </span>
                    </div>
                  );
                })}
              </div>
            </GlassCard>

            <GlassCard className="overview-card">
              <div className="overview-card-header">
                <h3>Autonomy Status</h3>
                <span className="overview-card-meta">{aiKeyConfigured ? 'AI Connected' : 'AI Offline'}</span>
              </div>
              <div className="overview-status-list">
                {autonomyItems.map(item => (
                  <div key={item.label} className="overview-status-row">
                    <span>{item.label}</span>
                    <strong>{formatStatusValue(item.value)}</strong>
                  </div>
                ))}
              </div>
            </GlassCard>

            <GlassCard className="overview-card">
              <div className="overview-card-header">
                <h3>Last Notable Event</h3>
                <span className="overview-card-meta">{lastEventTime}</span>
              </div>
              <div className="overview-event">
                <strong>{lastEventTitle}</strong>
                <p>{lastEventDetail}</p>
              </div>
            </GlassCard>
          </div>
        </div>
      </div>
    </section>
  );
}
