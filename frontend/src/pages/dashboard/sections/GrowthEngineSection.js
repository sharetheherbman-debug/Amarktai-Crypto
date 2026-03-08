import { useState, useEffect, useCallback } from 'react';
import SectionHeader from '@/ui/components/SectionHeader';
import { get, notifyError } from '../../../lib/apiClient';
import { useRealtimeEvent } from '../../../hooks/useRealtime';

const REFRESH_MS = 30000;

function safeNum(v, fallback = 0) {
  const n = Number(v);
  return Number.isFinite(n) ? n : fallback;
}

function fmtZAR(v, digits = 2, fallback = 'R 0.00') {
  if (v == null) return fallback;
  const n = safeNum(v);
  return `R ${n.toLocaleString('en-ZA', { minimumFractionDigits: digits, maximumFractionDigits: digits })}`;
}

function StatusBadge({ active, label }) {
  const color = active ? 'var(--success)' : 'var(--muted)';
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: '5px',
      padding: '3px 10px', borderRadius: '20px',
      background: active ? 'rgba(16, 185, 129, 0.15)' : 'rgba(100,116,139,0.15)',
      border: `1px solid ${color}`,
      color, fontSize: '0.78rem', fontWeight: 600,
    }}>
      <span style={{ width: 7, height: 7, borderRadius: '50%', background: color, display: 'inline-block' }} />
      {label}
    </span>
  );
}

function PlatformGrowthCard({ platform, data, threshold }) {
  const profit = safeNum(data?.realized_profit_zar);
  const milestone = safeNum(data?.next_milestone);
  const target = milestone * safeNum(threshold);
  const progress = target > 0 ? Math.min((profit / target) * 100, 100) : 0;
  const spawned = safeNum(data?.total_spawned);
  const eligible = data?.eligible;

  return (
    <div style={{
      background: 'var(--glass)',
      border: '1px solid var(--line)',
      borderRadius: '12px',
      padding: '18px',
      display: 'flex',
      flexDirection: 'column',
      gap: '12px',
    }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <span style={{ fontWeight: 700, fontSize: '0.95rem', color: 'var(--text)' }}>
          {platform.charAt(0).toUpperCase() + platform.slice(1)}
        </span>
        <StatusBadge active={eligible} label={eligible ? 'Eligible' : 'Accumulating'} />
      </div>

      <div>
        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '6px' }}>
          <span style={{ color: 'var(--muted)', fontSize: '0.8rem' }}>Progress to Milestone {milestone}</span>
          <span style={{ color: 'var(--accent2)', fontSize: '0.8rem', fontWeight: 600 }}>{progress.toFixed(1)}%</span>
        </div>
        <div style={{ background: 'rgba(255,255,255,0.08)', borderRadius: '6px', height: '6px', overflow: 'hidden' }}>
          <div style={{
            height: '100%',
            borderRadius: '6px',
            width: `${progress}%`,
            background: eligible
              ? 'linear-gradient(90deg, var(--success), #34d399)'
              : 'linear-gradient(90deg, var(--accent2), #60a5fa)',
            transition: 'width 0.4s ease',
          }} />
        </div>
        <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: '5px' }}>
          <span style={{ color: 'var(--muted)', fontSize: '0.75rem' }}>{fmtZAR(profit)} realized</span>
          <span style={{ color: 'var(--muted)', fontSize: '0.75rem' }}>Target: {fmtZAR(target)}</span>
        </div>
      </div>

      <div style={{ display: 'flex', gap: '16px' }}>
        <div style={{ flex: 1, background: 'rgba(255,255,255,0.04)', borderRadius: '8px', padding: '10px', textAlign: 'center' }}>
          <div style={{ fontSize: '1.3rem', fontWeight: 800, color: 'var(--text)' }}>{spawned}</div>
          <div style={{ fontSize: '0.72rem', color: 'var(--muted)', marginTop: '2px' }}>Bots Spawned</div>
        </div>
        <div style={{ flex: 1, background: 'rgba(255,255,255,0.04)', borderRadius: '8px', padding: '10px', textAlign: 'center' }}>
          <div style={{ fontSize: '1.3rem', fontWeight: 800, color: eligible ? 'var(--success)' : 'var(--muted)' }}>
            {milestone}
          </div>
          <div style={{ fontSize: '0.72rem', color: 'var(--muted)', marginTop: '2px' }}>Next Milestone</div>
        </div>
        <div style={{ flex: 1, background: 'rgba(255,255,255,0.04)', borderRadius: '8px', padding: '10px', textAlign: 'center' }}>
          <div style={{ fontSize: '1.3rem', fontWeight: 800, color: 'var(--text)' }}>{fmtZAR(threshold, 0)}</div>
          <div style={{ fontSize: '0.72rem', color: 'var(--muted)', marginTop: '2px' }}>Threshold</div>
        </div>
      </div>
    </div>
  );
}

function ReinvestPlatformCard({ platform, data, minReinvest }) {
  const lastAmount = safeNum(data?.last_reinvest_amount);
  const totalReinvested = safeNum(data?.total_reinvested_zar);
  const lastDate = data?.last_reinvest_date;

  return (
    <div style={{
      background: 'var(--glass)',
      border: '1px solid var(--line)',
      borderRadius: '12px',
      padding: '18px',
      display: 'flex',
      flexDirection: 'column',
      gap: '10px',
    }}>
      <div style={{ fontWeight: 700, fontSize: '0.9rem', color: 'var(--text)' }}>
        {platform.charAt(0).toUpperCase() + platform.slice(1)}
      </div>
      <div style={{ display: 'flex', gap: '10px' }}>
        <div style={{ flex: 1, background: 'rgba(255,255,255,0.04)', borderRadius: '8px', padding: '10px', textAlign: 'center' }}>
          <div style={{ fontSize: '1.1rem', fontWeight: 700, color: 'var(--accent2)' }}>{fmtZAR(totalReinvested)}</div>
          <div style={{ fontSize: '0.72rem', color: 'var(--muted)', marginTop: '2px' }}>Total Reinvested</div>
        </div>
        <div style={{ flex: 1, background: 'rgba(255,255,255,0.04)', borderRadius: '8px', padding: '10px', textAlign: 'center' }}>
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

  // Sync with parent state updates
  useEffect(() => {
    if (autopilotGrowthStatus) setGrowthData(autopilotGrowthStatus);
  }, [autopilotGrowthStatus]);

  useEffect(() => {
    if (autopilotReinvestStatus) setReinvestData(autopilotReinvestStatus);
  }, [autopilotReinvestStatus]);

  // Subscribe to realtime heartbeat/system updates
  useRealtimeEvent('system_health', fetchData);

  const platforms = growthData?.platforms ? Object.keys(growthData.platforms) : [];
  const reinvestPlatforms = reinvestData?.platforms ? Object.keys(reinvestData.platforms) : [];
  const growthEnabled = growthData?.enabled;
  const reinvestEnabled = reinvestData?.enabled;
  const threshold = growthData?.profit_threshold_zar ?? 0;
  const minReinvest = reinvestData?.min_reinvest_zar ?? 0;

  const tabStyle = (active) => ({
    padding: '9px 20px',
    background: active ? 'linear-gradient(135deg, var(--accent2), #60a5fa)' : 'var(--glass)',
    border: `2px solid ${active ? 'var(--accent2)' : 'var(--line)'}`,
    borderRadius: '8px',
    color: active ? '#fff' : 'var(--text)',
    cursor: 'pointer',
    fontSize: '0.9rem',
    fontWeight: active ? 700 : 500,
    transition: 'all 0.2s',
    boxShadow: active ? '0 4px 12px rgba(74,144,226,0.3)' : 'none',
  });

  return (
    <section className="section active">
      <div className="card">
        <SectionHeader
          title="🌱 Growth Engine"
          subtitle="Autopilot profit milestone tracking and autonomous bot spawning."
        />

        {/* Status banner */}
        <div style={{
          display: 'flex', gap: '12px', flexWrap: 'wrap', marginBottom: '24px',
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
          <button style={tabStyle(activeTab === 'growth')} onClick={() => setActiveTab('growth')}>
            📈 Bot Spawning
          </button>
          <button style={tabStyle(activeTab === 'reinvest')} onClick={() => setActiveTab('reinvest')}>
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
                <div style={{ marginBottom: '16px' }}>
                  <p style={{ color: 'var(--muted)', fontSize: '0.85rem', marginBottom: '4px' }}>
                    The growth engine automatically spawns a new bot when realized profit crosses a milestone threshold.
                  </p>
                  <p style={{ color: 'var(--muted)', fontSize: '0.82rem' }}>
                    Milestone threshold: <strong style={{ color: 'var(--text)' }}>{fmtZAR(threshold)}</strong> per milestone
                  </p>
                </div>
                {platforms.length === 0 ? (
                  <div style={{ color: 'var(--muted)', padding: '24px', textAlign: 'center' }}>
                    No platform data available.
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
                <div style={{ marginBottom: '16px' }}>
                  <p style={{ color: 'var(--muted)', fontSize: '0.85rem', marginBottom: '4px' }}>
                    Daily reinvestment allocates realized profits back into active bots when the cap is reached.
                  </p>
                  <p style={{ color: 'var(--muted)', fontSize: '0.82rem' }}>
                    Minimum reinvest amount: <strong style={{ color: 'var(--text)' }}>{fmtZAR(minReinvest)}</strong>
                  </p>
                </div>
                {reinvestPlatforms.length === 0 ? (
                  <div style={{ color: 'var(--muted)', padding: '24px', textAlign: 'center' }}>
                    No reinvest data available.
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
                        minReinvest={minReinvest}
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
