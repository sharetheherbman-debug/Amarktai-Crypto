import { useState, useEffect, useCallback } from 'react';
import SectionHeader from '@/ui/components/SectionHeader';
import { get, notifyError } from '../../../lib/apiClient';
import { useRealtimeEvent } from '../../../hooks/useRealtime';

const REFRESH_MS = 30000;

// Human-readable labels for backend reason codes
const REASON_LABELS = {
  AUTOPILOT_GROWTH_DISABLED:    'Growth Engine is disabled (ENABLE_AUTOPILOT_GROWTH env var)',
  AUTOPILOT_REINVEST_DISABLED:  'Reinvest Engine is disabled (ENABLE_AUTOPILOT_REINVEST env var)',
  AUTOPILOT_DISABLED:           'Autopilot is globally disabled',
  TRADING_MODE_DISABLED:        'No trading mode is enabled (PAPER_TRADING / LIVE_TRADING)',
  AUTOPILOT_OFF_FOR_USER:       'Autopilot is turned off in your profile',
  DAILY_LOSS_LOCK_ACTIVE:       'Daily loss limit reached — unlock via Risk panel',
  AUTOPILOT_MODE_DISABLED:      'System mode is not set to Autopilot',
  EMERGENCY_STOP_ACTIVE:        'Emergency stop is active',
  BODYGUARD_LOCK_ACTIVE:        'AI Bodyguard has paused one or more bots',
  MAX_BOTS_REACHED:             'Maximum bots for this platform already reached',
  API_KEYS_MISSING:             'No API keys configured for this exchange',
  API_KEYS_INVALID:             'API keys exist but failed validation — re-test in API Setup',
  INSUFFICIENT_AVAILABLE_FUNDS: 'Insufficient paper wallet funds for bot spawn',
  PROFIT_BELOW_THRESHOLD:       'Profit has not yet reached the milestone threshold',
};

function safeNum(v, fallback = 0) {
  const n = Number(v);
  return Number.isFinite(n) ? n : fallback;
}

function fmtZAR(v, digits = 2, fallback = 'R 0.00') {
  if (v == null) return fallback;
  const n = safeNum(v);
  return `R ${n.toLocaleString('en-ZA', { minimumFractionDigits: digits, maximumFractionDigits: digits })}`;
}

// Inline style helpers reused across sub-components (keeps visual language consistent
// with other dashboard sections that also use const-style inline helpers)
const S = {
  badge: (active) => ({
    display: 'inline-flex', alignItems: 'center', gap: '5px',
    padding: '3px 10px', borderRadius: '20px',
    background: active ? 'rgba(16,185,129,0.15)' : 'rgba(100,116,139,0.15)',
    border: `1px solid ${active ? 'var(--success)' : 'var(--muted)'}`,
    color: active ? 'var(--success)' : 'var(--muted)',
    fontSize: '0.78rem', fontWeight: 600,
  }),
  dot: (active) => ({
    width: 7, height: 7, borderRadius: '50%',
    background: active ? 'var(--success)' : 'var(--muted)',
    display: 'inline-block',
  }),
  tab: (active) => ({
    padding: '9px 20px',
    background: active ? 'linear-gradient(135deg, var(--accent2), #60a5fa)' : 'var(--glass)',
    border: `2px solid ${active ? 'var(--accent2)' : 'var(--line)'}`,
    borderRadius: '8px',
    color: active ? '#fff' : 'var(--text)',
    cursor: 'pointer', fontSize: '0.9rem',
    fontWeight: active ? 700 : 500,
    transition: 'all 0.2s',
    boxShadow: active ? '0 4px 12px rgba(74,144,226,0.3)' : 'none',
  }),
  statBox: {
    flex: 1, background: 'rgba(255,255,255,0.04)',
    borderRadius: '8px', padding: '10px', textAlign: 'center',
  },
  reasonItem: {
    display: 'flex', alignItems: 'flex-start', gap: '8px',
    padding: '6px 0',
    borderBottom: '1px solid rgba(255,255,255,0.05)',
    fontSize: '0.83rem', color: 'var(--muted)',
  },
};

function StatusBadge({ active, label }) {
  return (
    <span style={S.badge(active)}>
      <span style={S.dot(active)} />
      {label}
    </span>
  );
}

/** Panel shown when an engine is disabled — lists every reason clearly. */
function DisabledPanel({ title, reasons }) {
  const labelledReasons = (reasons || []).map(r => REASON_LABELS[r] || r);
  return (
    <div style={{
      background: 'rgba(239,68,68,0.06)', border: '1px solid rgba(239,68,68,0.25)',
      borderRadius: '10px', padding: '16px', marginBottom: '16px',
    }}>
      <div style={{ fontWeight: 700, color: '#ef4444', fontSize: '0.88rem', marginBottom: '10px' }}>
        ⛔ {title} is currently disabled
      </div>
      {labelledReasons.length === 0 ? (
        <p style={{ color: 'var(--muted)', fontSize: '0.82rem', margin: 0 }}>
          Enable the feature flag on the server to activate this engine.
        </p>
      ) : (
        <ul style={{ listStyle: 'none', padding: 0, margin: 0 }}>
          {labelledReasons.map((r, i) => (
            <li key={i} style={S.reasonItem}>
              <span style={{ color: '#ef4444', flexShrink: 0 }}>•</span>
              {r}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function PlatformGrowthCard({ platform, data, threshold }) {
  const profit = safeNum(data?.realized_profit_zar);
  const nextThreshold = safeNum(data?.next_threshold_zar ?? (safeNum(data?.next_milestone) * safeNum(threshold)));
  const progress = nextThreshold > 0 ? Math.min((profit / nextThreshold) * 100, 100) : 0;
  const spawned = safeNum(data?.milestones_spawned ?? data?.total_spawned);
  const eligible = data?.eligible;
  const blocked = (data?.blocked_reasons || []).filter(r => r !== 'PROFIT_BELOW_THRESHOLD');

  return (
    <div style={{
      background: 'var(--glass)', border: '1px solid var(--line)',
      borderRadius: '12px', padding: '18px',
      display: 'flex', flexDirection: 'column', gap: '12px',
    }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <span style={{ fontWeight: 700, fontSize: '0.95rem', color: 'var(--text)' }}>
          {platform.charAt(0).toUpperCase() + platform.slice(1)}
        </span>
        <StatusBadge active={eligible} label={eligible ? 'Eligible' : blocked.length > 0 ? 'Blocked' : 'Accumulating'} />
      </div>

      <div>
        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '6px' }}>
          <span style={{ color: 'var(--muted)', fontSize: '0.8rem' }}>Progress to next milestone</span>
          <span style={{ color: 'var(--accent2)', fontSize: '0.8rem', fontWeight: 600 }}>{progress.toFixed(1)}%</span>
        </div>
        <div style={{ background: 'rgba(255,255,255,0.08)', borderRadius: '6px', height: '6px', overflow: 'hidden' }}>
          <div style={{
            height: '100%', borderRadius: '6px', width: `${progress}%`,
            background: eligible
              ? 'linear-gradient(90deg, var(--success), #34d399)'
              : 'linear-gradient(90deg, var(--accent2), #60a5fa)',
            transition: 'width 0.4s ease',
          }} />
        </div>
        <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: '5px' }}>
          <span style={{ color: 'var(--muted)', fontSize: '0.75rem' }}>{fmtZAR(profit)} realized</span>
          <span style={{ color: 'var(--muted)', fontSize: '0.75rem' }}>Target: {fmtZAR(nextThreshold)}</span>
        </div>
      </div>

      <div style={{ display: 'flex', gap: '8px' }}>
        <div style={S.statBox}>
          <div style={{ fontSize: '1.3rem', fontWeight: 800, color: 'var(--text)' }}>{spawned}</div>
          <div style={{ fontSize: '0.72rem', color: 'var(--muted)', marginTop: '2px' }}>Bots Spawned</div>
        </div>
        <div style={S.statBox}>
          <div style={{ fontSize: '1.3rem', fontWeight: 800, color: 'var(--text)' }}>{fmtZAR(threshold, 0)}</div>
          <div style={{ fontSize: '0.72rem', color: 'var(--muted)', marginTop: '2px' }}>Threshold</div>
        </div>
      </div>

      {blocked.length > 0 && (
        <div style={{ fontSize: '0.78rem', color: '#f59e0b' }}>
          ⚠ {blocked.map(r => REASON_LABELS[r] || r).join(' • ')}
        </div>
      )}
    </div>
  );
}

function ReinvestPlatformCard({ platform, data }) {
  const lastAmount = safeNum(data?.last_reinvest_amount);
  const totalReinvested = safeNum(data?.total_reinvested_zar);
  const lastDate = data?.last_reinvest_date;

  return (
    <div style={{
      background: 'var(--glass)', border: '1px solid var(--line)',
      borderRadius: '12px', padding: '18px',
      display: 'flex', flexDirection: 'column', gap: '10px',
    }}>
      <div style={{ fontWeight: 700, fontSize: '0.9rem', color: 'var(--text)' }}>
        {platform.charAt(0).toUpperCase() + platform.slice(1)}
      </div>
      <div style={{ display: 'flex', gap: '10px' }}>
        <div style={S.statBox}>
          <div style={{ fontSize: '1.1rem', fontWeight: 700, color: 'var(--accent2)' }}>{fmtZAR(totalReinvested)}</div>
          <div style={{ fontSize: '0.72rem', color: 'var(--muted)', marginTop: '2px' }}>Total Reinvested</div>
        </div>
        <div style={S.statBox}>
          <div style={{ fontSize: '1.1rem', fontWeight: 700, color: 'var(--text)' }}>{fmtZAR(lastAmount)}</div>
          <div style={{ fontSize: '0.72rem', color: 'var(--muted)', marginTop: '2px' }}>Last Reinvest</div>
        </div>
      </div>
      {lastDate && (
        <div style={{ fontSize: '0.75rem', color: 'var(--muted)' }}>
          Last run: {new Date(lastDate).toLocaleString()}
        </div>
      )}
    </div>
  );
}

export default function GrowthEngineSection({ autopilotGrowthStatus, autopilotReinvestStatus }) {
  const [growthData, setGrowthData] = useState(autopilotGrowthStatus || null);
  const [reinvestData, setReinvestData] = useState(autopilotReinvestStatus || null);
  const [loading, setLoading] = useState(!autopilotGrowthStatus);
  const [lastUpdated, setLastUpdated] = useState(null);
  const [activeTab, setActiveTab] = useState('growth');

  const fetchData = useCallback(async () => {
    try {
      const [gRes, rRes] = await Promise.all([
        get('/autopilot/growth/status'),
        get('/autopilot/reinvest/status'),
      ]);
      setGrowthData(gRes);
      setReinvestData(rRes);
      setLastUpdated(new Date());
    } catch (err) {
      notifyError(err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, REFRESH_MS);
    return () => clearInterval(interval);
  }, [fetchData]);

  useEffect(() => { if (autopilotGrowthStatus) setGrowthData(autopilotGrowthStatus); }, [autopilotGrowthStatus]);
  useEffect(() => { if (autopilotReinvestStatus) setReinvestData(autopilotReinvestStatus); }, [autopilotReinvestStatus]);

  useRealtimeEvent('system_health', fetchData);

  const platforms = growthData?.platforms ? Object.keys(growthData.platforms) : [];
  const reinvestPlatforms = reinvestData?.platforms ? Object.keys(reinvestData.platforms) : [];
  const growthEnabled = growthData?.enabled;
  const reinvestEnabled = reinvestData?.enabled;
  const threshold = growthData?.profit_threshold_zar ?? 0;
  const minReinvest = reinvestData?.min_reinvest_zar ?? 0;

  // Collect global blocking reasons from the first platform's response (feature-level reasons
  // like AUTOPILOT_GROWTH_DISABLED apply to all platforms, not just one)
  const globalGrowthBlockers = platforms.length > 0
    ? (growthData.platforms[platforms[0]]?.blocked_reasons || [])
        .filter(r => ['AUTOPILOT_GROWTH_DISABLED','AUTOPILOT_DISABLED','TRADING_MODE_DISABLED',
                      'AUTOPILOT_OFF_FOR_USER','DAILY_LOSS_LOCK_ACTIVE','AUTOPILOT_MODE_DISABLED',
                      'EMERGENCY_STOP_ACTIVE','BODYGUARD_LOCK_ACTIVE'].includes(r))
    : (growthEnabled === false ? ['AUTOPILOT_GROWTH_DISABLED'] : []);

  return (
    <section className="section active">
      <div className="card">
        <SectionHeader
          title="🌱 Growth Engine"
          subtitle="Autopilot profit milestone tracking and autonomous bot spawning."
        />

        {/* Status banner */}
        <div style={{
          display: 'flex', gap: '12px', flexWrap: 'wrap', marginBottom: '20px',
          padding: '14px 16px',
          background: 'rgba(255,255,255,0.03)',
          border: '1px solid var(--line)',
          borderRadius: '10px',
          alignItems: 'center',
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <span style={{ color: 'var(--muted)', fontSize: '0.82rem' }}>Growth Engine:</span>
            <StatusBadge active={growthEnabled} label={growthEnabled ? 'Active' : 'Disabled'} />
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <span style={{ color: 'var(--muted)', fontSize: '0.82rem' }}>Reinvest Engine:</span>
            <StatusBadge active={reinvestEnabled} label={reinvestEnabled ? 'Active' : 'Disabled'} />
          </div>
          {lastUpdated && (
            <span style={{ color: 'var(--muted)', fontSize: '0.75rem', marginLeft: 'auto' }}>
              Updated {lastUpdated.toLocaleTimeString()}
            </span>
          )}
        </div>

        {/* Tabs */}
        <div style={{ display: 'flex', gap: '10px', marginBottom: '20px', flexWrap: 'wrap' }}>
          <button style={S.tab(activeTab === 'growth')} onClick={() => setActiveTab('growth')}>
            📈 Bot Spawning
          </button>
          <button style={S.tab(activeTab === 'reinvest')} onClick={() => setActiveTab('reinvest')}>
            🔄 Profit Reinvest
          </button>
        </div>

        {loading ? (
          <div style={{ color: 'var(--muted)', padding: '32px', textAlign: 'center' }}>
            Loading growth engine data…
          </div>
        ) : (
          <>
            {activeTab === 'growth' && (
              <div>
                {/* Show disabled panel when feature flag is off */}
                {!growthEnabled && (
                  <DisabledPanel title="Growth Engine" reasons={globalGrowthBlockers} />
                )}

                {growthEnabled && globalGrowthBlockers.length > 0 && (
                  <div style={{
                    background: 'rgba(245,158,11,0.07)', border: '1px solid rgba(245,158,11,0.3)',
                    borderRadius: '10px', padding: '14px 16px', marginBottom: '16px',
                    fontSize: '0.83rem', color: '#f59e0b',
                  }}>
                    ⚠ Growth Engine is active but currently blocked:
                    <ul style={{ listStyle: 'none', padding: '6px 0 0 0', margin: 0 }}>
                      {globalGrowthBlockers.map((r, i) => (
                        <li key={i}>• {REASON_LABELS[r] || r}</li>
                      ))}
                    </ul>
                  </div>
                )}

                <div style={{ marginBottom: '14px' }}>
                  <p style={{ color: 'var(--muted)', fontSize: '0.85rem', margin: '0 0 4px 0' }}>
                    Automatically spawns a new bot when realized profit crosses a milestone threshold.
                  </p>
                  <p style={{ color: 'var(--muted)', fontSize: '0.82rem', margin: 0 }}>
                    Milestone threshold: <strong style={{ color: 'var(--text)' }}>{fmtZAR(threshold)}</strong>
                  </p>
                </div>

                {platforms.length === 0 ? (
                  <div style={{ color: 'var(--muted)', padding: '24px', textAlign: 'center' }}>
                    No platform data available yet.
                  </div>
                ) : (
                  <div style={{
                    display: 'grid',
                    gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))',
                    gap: '14px',
                  }}>
                    {platforms.map(platform => (
                      <PlatformGrowthCard
                        key={platform}
                        platform={platform}
                        data={growthData.platforms[platform]}
                        threshold={threshold}
                      />
                    ))}
                  </div>
                )}
              </div>
            )}

            {activeTab === 'reinvest' && (
              <div>
                {!reinvestEnabled && (
                  <DisabledPanel
                    title="Reinvest Engine"
                    reasons={['AUTOPILOT_REINVEST_DISABLED']}
                  />
                )}

                <div style={{ marginBottom: '14px' }}>
                  <p style={{ color: 'var(--muted)', fontSize: '0.85rem', margin: '0 0 4px 0' }}>
                    Daily reinvestment allocates realized profits back into active bots when the cap is reached.
                  </p>
                  <p style={{ color: 'var(--muted)', fontSize: '0.82rem', margin: 0 }}>
                    Minimum reinvest: <strong style={{ color: 'var(--text)' }}>{fmtZAR(minReinvest)}</strong>
                  </p>
                </div>

                {reinvestPlatforms.length === 0 ? (
                  <div style={{ color: 'var(--muted)', padding: '24px', textAlign: 'center' }}>
                    No reinvest data available yet.
                  </div>
                ) : (
                  <div style={{
                    display: 'grid',
                    gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))',
                    gap: '14px',
                  }}>
                    {reinvestPlatforms.map(platform => (
                      <ReinvestPlatformCard
                        key={platform}
                        platform={platform}
                        data={reinvestData.platforms[platform]}
                      />
                    ))}
                  </div>
                )}
              </div>
            )}
          </>
        )}
      </div>
    </section>
  );
}
