import { useState, useEffect, useCallback, useMemo } from 'react';
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

  // Aggregate stats across all platforms
  const aggregateStats = useMemo(() => {
    if (!growthData?.platforms) return { totalSpawned: 0, eligiblePlatforms: 0, blockedPlatforms: 0 };
    const entries = Object.values(growthData.platforms);
    return {
      totalSpawned: entries.reduce((s, p) => s + safeNum(p?.milestones_spawned ?? p?.total_spawned), 0),
      eligiblePlatforms: entries.filter(p => p?.eligible).length,
      blockedPlatforms: entries.filter(p => !p?.eligible && (p?.blocked_reasons || []).some(r => r !== 'PROFIT_BELOW_THRESHOLD')).length,
    };
  }, [growthData]);

  // Determine overall growth engine operational status
  const growthStatus = useMemo(() => {
    if (!growthEnabled) return 'disabled';
    if (globalGrowthBlockers.length > 0) return 'blocked';
    if (aggregateStats.eligiblePlatforms > 0) return 'ready';
    return 'accumulating';
  }, [growthEnabled, globalGrowthBlockers, aggregateStats]);

  const STATUS_BADGE = {
    disabled: { label: 'Disabled', color: '#ef4444', bg: 'rgba(239,68,68,0.1)', border: 'rgba(239,68,68,0.3)' },
    blocked:  { label: 'Blocked', color: '#f59e0b', bg: 'rgba(245,158,11,0.1)', border: 'rgba(245,158,11,0.3)' },
    ready:    { label: 'Ready to Spawn', color: '#22c55e', bg: 'rgba(34,197,94,0.1)', border: 'rgba(34,197,94,0.3)' },
    accumulating: { label: 'Active — Accumulating', color: '#60a5fa', bg: 'rgba(96,165,250,0.1)', border: 'rgba(96,165,250,0.3)' },
  };

  return (
    <section className="section active">
      <div className="card">
        <SectionHeader
          title="🌱 Growth Engine"
          subtitle="Tracks realized profit milestones and autonomously spawns new bots."
        />

        {/* ── Engine Status Row ── */}
        <div style={{
          display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
          gap: '10px', marginBottom: '20px',
        }}>
          {/* Growth Engine status tile */}
          {(() => {
            const sd = STATUS_BADGE[growthStatus] || STATUS_BADGE.accumulating;
            return (
              <div style={{
                background: sd.bg, border: `1px solid ${sd.border}`,
                borderRadius: '10px', padding: '12px 14px',
                display: 'flex', flexDirection: 'column', gap: '4px',
              }}>
                <span style={{ fontSize: '0.72rem', color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Growth Engine</span>
                <span style={{ fontWeight: 700, fontSize: '0.9rem', color: sd.color }}>● {sd.label}</span>
              </div>
            );
          })()}
          {/* Reinvest status tile */}
          <div style={{
            background: reinvestEnabled ? 'rgba(96,165,250,0.1)' : 'rgba(100,116,139,0.08)',
            border: `1px solid ${reinvestEnabled ? 'rgba(96,165,250,0.3)' : 'var(--line)'}`,
            borderRadius: '10px', padding: '12px 14px',
            display: 'flex', flexDirection: 'column', gap: '4px',
          }}>
            <span style={{ fontSize: '0.72rem', color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Reinvest Engine</span>
            <span style={{ fontWeight: 700, fontSize: '0.9rem', color: reinvestEnabled ? '#60a5fa' : 'var(--muted)' }}>
              {reinvestEnabled ? '● Active' : '○ Disabled'}
            </span>
          </div>
          {/* Bots spawned tile */}
          <div style={{ background: 'var(--glass)', border: '1px solid var(--line)', borderRadius: '10px', padding: '12px 14px', display: 'flex', flexDirection: 'column', gap: '4px' }}>
            <span style={{ fontSize: '0.72rem', color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Bots Spawned</span>
            <span style={{ fontWeight: 800, fontSize: '1.1rem', color: 'var(--text)' }}>{aggregateStats.totalSpawned}</span>
          </div>
          {/* Threshold tile */}
          <div style={{ background: 'var(--glass)', border: '1px solid var(--line)', borderRadius: '10px', padding: '12px 14px', display: 'flex', flexDirection: 'column', gap: '4px' }}>
            <span style={{ fontSize: '0.72rem', color: 'var(--muted)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Milestone Threshold</span>
            <span style={{ fontWeight: 800, fontSize: '1.1rem', color: 'var(--accent2)' }}>{fmtZAR(threshold)}</span>
          </div>
          {/* Last updated */}
          {lastUpdated && (
            <div style={{ display: 'flex', alignItems: 'flex-end', justifyContent: 'flex-end' }}>
              <span style={{ color: 'var(--muted)', fontSize: '0.72rem' }}>
                ↻ {lastUpdated.toLocaleTimeString()}
              </span>
            </div>
          )}
        </div>

        {/* ── Tabs ── */}
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
                {/* Disabled state */}
                {!growthEnabled && (
                  <DisabledPanel title="Growth Engine" reasons={globalGrowthBlockers} />
                )}

                {/* Blocked state — engine enabled but guardrails blocking */}
                {growthEnabled && globalGrowthBlockers.length > 0 && (
                  <div style={{
                    background: 'rgba(245,158,11,0.07)', border: '1px solid rgba(245,158,11,0.3)',
                    borderRadius: '10px', padding: '14px 16px', marginBottom: '16px',
                  }}>
                    <div style={{ fontWeight: 700, color: '#f59e0b', fontSize: '0.88rem', marginBottom: '8px' }}>
                      ⚠ Growth Engine blocked — resolve these before auto-spawning can trigger:
                    </div>
                    <ul style={{ listStyle: 'none', padding: 0, margin: 0 }}>
                      {globalGrowthBlockers.map((r, i) => (
                        <li key={i} style={{ fontSize: '0.82rem', color: 'var(--muted)', padding: '3px 0' }}>
                          • {REASON_LABELS[r] || r}
                        </li>
                      ))}
                    </ul>
                    <div style={{ marginTop: '8px', fontSize: '0.78rem', color: 'var(--muted)' }}>
                      ℹ Enable Autopilot in System Mode and ensure your paper wallet has funds to unblock.
                    </div>
                  </div>
                )}

                {/* How it works */}
                <div style={{
                  background: 'rgba(96,165,250,0.05)', border: '1px solid rgba(96,165,250,0.15)',
                  borderRadius: '10px', padding: '12px 14px', marginBottom: '16px',
                  fontSize: '0.82rem', color: 'var(--muted)', lineHeight: '1.6',
                }}>
                  <strong style={{ color: 'var(--text)', display: 'block', marginBottom: '4px' }}>How it works</strong>
                  Each exchange tracks its own realized profit independently.
                  When profit crosses the milestone threshold ({fmtZAR(threshold)}),
                  a new bot is automatically seeded on that exchange.
                  Each subsequent milestone triggers another spawn.
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

                {/* How it works */}
                <div style={{
                  background: 'rgba(96,165,250,0.05)', border: '1px solid rgba(96,165,250,0.15)',
                  borderRadius: '10px', padding: '12px 14px', marginBottom: '16px',
                  fontSize: '0.82rem', color: 'var(--muted)', lineHeight: '1.6',
                }}>
                  <strong style={{ color: 'var(--text)', display: 'block', marginBottom: '4px' }}>How it works</strong>
                  Daily reinvestment runs once per day. When realized profit on an exchange
                  exceeds the minimum ({fmtZAR(minReinvest)}) and bots are near their capital cap,
                  profits are redistributed as additional capital to active bots.
                </div>

                {reinvestPlatforms.length === 0 ? (
                  <div style={{ color: 'var(--muted)', padding: '24px', textAlign: 'center' }}>
                    No reinvest data available yet. Profits will appear here once closed trades are recorded.
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
