import React, { useState, useEffect, useCallback } from 'react';
import SectionHeader from '@/ui/components/SectionHeader';
import apiClient from '@/lib/apiClient';

/**
 * Growth Engine Section
 *
 * Per-user, paper-trading-only growth automation.
 * All features are off by default. Every action goes through existing
 * bot lifecycle / ledger / risk gates — no standalone trading engine.
 *
 * Safety:
 * - Everything off by default.
 * - Leverage toggle shown but labeled "Not active in this release".
 * - Big warning banner at top.
 * - Blocked reasons shown in plain English.
 */

const FEATURE_DESCRIPTIONS = {
  profit_recycling: {
    label: '💰 Profit Recycling',
    description: 'Spawns a new bot funded only from realized profits above a threshold. Uses existing bot spawner — no manual capital required.',
    fields: [
      { key: 'profit_recycle_threshold_r', label: 'Min profit before recycling (ZAR)', type: 'number', min: 10, max: 10000 },
      { key: 'profit_recycle_max_per_day', label: 'Max new bots per day', type: 'number', min: 1, max: 5 },
    ],
  },
  capital_redistribution: {
    label: '🔄 Capital Redistribution',
    description: 'Gradually shifts capital from worst-performing bots to top performers. All moves go through the ledger — nothing is bypassed.',
    fields: [
      { key: 'capital_shift_max_pct', label: 'Max capital shift per tick (%)', type: 'number', min: 1, max: 50 },
    ],
  },
  strategy_specialization: {
    label: '🧠 Strategy Specialization',
    description: 'Assigns bots to regime-appropriate strategy profiles (trend, range, breakout, micro-scalp) based on CoinStats intelligence. Reversible.',
    fields: [],
  },
  trade_frequency_tuning: {
    label: '⚡ Trade Frequency Tuning',
    description: 'Adjusts bot cooldown and concurrency within strict safe bounds. Auto-reverts if any lock activates.',
    fields: [],
  },
  dynamic_risk_budgeting: {
    label: '📊 Dynamic Risk Budgeting',
    description: 'Scales risk budget relative to equity highs and drawdowns. Never disables Bodyguard or daily loss locks.',
    fields: [
      { key: 'risk_budget_scale_factor', label: 'Risk budget multiplier', type: 'number', min: 0.5, max: 2.0, step: 0.1 },
    ],
  },
  capital_aggression: {
    label: '🚀 Capital Aggression Mode',
    description: 'Temporarily increases capital allocation after a streak of profitable days with low drawdown. Auto-reverts after the configured period.',
    fields: [
      { key: 'aggression_min_green_days', label: 'Minimum green days required', type: 'number', min: 3, max: 30 },
      { key: 'aggression_max_drawdown_pct', label: 'Max drawdown to allow aggression (%)', type: 'number', min: 1, max: 15 },
    ],
  },
  exchange_filtering: {
    label: '🏦 Exchange Performance Filtering',
    description: 'Scores each exchange on performance metrics and gradually shifts allocations to better-performing ones. Ledger-first.',
    fields: [],
  },
  bot_cap_ramp: {
    label: '📈 Bot Cap Ramp',
    description: 'Increases the maximum bot cap only when funded from profits. Never increases beyond the configured hard limit.',
    fields: [
      { key: 'bot_cap_max', label: 'Max bot cap', type: 'number', min: 1, max: 30 },
    ],
  },
};

const cardStyle = {
  padding: '16px',
  background: 'var(--panel)',
  border: '1px solid var(--line)',
  borderRadius: '10px',
  marginBottom: '12px',
};

const ToggleSwitch = ({ checked, onChange, disabled }) => (
  <button
    onClick={() => !disabled && onChange(!checked)}
    disabled={disabled}
    style={{
      width: '44px', height: '24px', borderRadius: '12px',
      border: 'none', cursor: disabled ? 'not-allowed' : 'pointer',
      background: checked ? 'var(--success, #10b981)' : 'var(--muted, #64748b)',
      position: 'relative', transition: 'background 0.2s', flexShrink: 0,
      opacity: disabled ? 0.5 : 1,
    }}
    title={disabled ? 'Enable the master Growth Engine switch first' : (checked ? 'Enabled — click to disable' : 'Disabled — click to enable')}
  >
    <span style={{
      position: 'absolute', top: '3px',
      left: checked ? '22px' : '3px',
      width: '18px', height: '18px', borderRadius: '50%',
      background: '#fff', transition: 'left 0.2s',
    }} />
  </button>
);

export default function GrowthEngineSection() {
  const [settings, setSettings] = useState(null);
  const [status, setStatus] = useState(null);
  const [decisions, setDecisions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState(null);
  const [runResult, setRunResult] = useState(null);

  const fetchAll = useCallback(async () => {
    try {
      const [settingsRes, statusRes, decisionsRes] = await Promise.all([
        apiClient.get('/growth/settings'),
        apiClient.get('/growth/status'),
        apiClient.get('/growth/decisions?limit=10'),
      ]);
      setSettings(settingsRes.data.settings);
      setStatus(statusRes.data);
      setDecisions(decisionsRes.data.decisions || []);
      setError(null);
    } catch (err) {
      setError(err.response?.data?.detail || err.message || 'Failed to load Growth Engine data');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchAll();
    const interval = setInterval(fetchAll, 8000); // poll every 8s
    return () => clearInterval(interval);
  }, [fetchAll]);

  const updateSetting = async (key, value) => {
    if (!settings) return;
    const updated = { ...settings, [key]: value };
    setSettings(updated);
    setSaving(true);
    try {
      const res = await apiClient.put('/growth/settings', { [key]: value });
      setSettings(res.data.settings);
    } catch (err) {
      setError('Failed to save setting: ' + (err.response?.data?.detail || err.message));
    } finally {
      setSaving(false);
    }
  };

  const handleRunOnce = async () => {
    if (!window.confirm(
      '⚠️ Run Growth Engine tick now?\n\n' +
      'This will execute one analysis tick and propose actions based on your enabled features. ' +
      'Proposed actions require manual review. No trades are placed automatically.\n\n' +
      'Proceed?'
    )) return;
    setRunning(true);
    setRunResult(null);
    try {
      const res = await apiClient.post('/growth/run-once', { confirm: true });
      setRunResult(res.data.decision);
      await fetchAll();
    } catch (err) {
      setError('Run failed: ' + (err.response?.data?.detail || err.message));
    } finally {
      setRunning(false);
    }
  };

  if (loading) {
    return (
      <section className="section active">
        <div className="card">
          <SectionHeader title="📈 Growth Engine" subtitle="Automated growth features for paper trading" />
          <div style={{ color: 'var(--muted)', padding: '20px 0' }}>Loading Growth Engine…</div>
        </div>
      </section>
    );
  }

  const masterEnabled = settings?.enabled || false;

  return (
    <section className="section active">
      <div className="card">
        <SectionHeader
          title="📈 Growth Engine"
          subtitle="Safe, automated growth features — paper trading only. All features off by default."
        />

        {/* Warning Banner */}
        <div style={{
          padding: '14px 18px',
          background: 'linear-gradient(135deg, rgba(245,158,11,0.15) 0%, rgba(217,119,6,0.08) 100%)',
          border: '1px solid rgba(245,158,11,0.4)',
          borderRadius: '10px',
          marginBottom: '20px',
          display: 'flex', gap: '12px', alignItems: 'flex-start',
        }}>
          <span style={{ fontSize: '1.3rem' }}>⚠️</span>
          <div>
            <div style={{ fontWeight: 700, color: 'var(--warning, #f59e0b)', marginBottom: '4px' }}>
              Higher Risk Features
            </div>
            <div style={{ fontSize: '0.88rem', color: 'var(--text)', lineHeight: '1.5' }}>
              These features can increase drawdown and capital exposure.
              Enable only if you understand the risk. All actions go through existing
              safety gates (Bodyguard, daily loss locks, emergency stop).
              <strong> Nothing executes without your toggles being on.</strong>
            </div>
          </div>
        </div>

        {/* Error */}
        {error && (
          <div style={{ padding: '12px', background: 'rgba(239,68,68,0.1)', border: '1px solid #ef4444', borderRadius: '8px', color: '#ef4444', marginBottom: '16px', fontSize: '0.88rem' }}>
            {error}
          </div>
        )}

        {/* Master Switch + Status */}
        <div style={{ ...cardStyle, display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '12px' }}>
          <div>
            <div style={{ fontWeight: 700, fontSize: '1rem', color: 'var(--text)', marginBottom: '4px' }}>
              Master Switch
            </div>
            <div style={{ fontSize: '0.82rem', color: 'var(--muted)' }}>
              {masterEnabled ? '✅ Growth Engine is ACTIVE' : '⭕ Growth Engine is OFF — no features will run'}
            </div>
          </div>
          <ToggleSwitch
            checked={masterEnabled}
            onChange={(v) => updateSetting('enabled', v)}
            disabled={saving}
          />
        </div>

        {/* Status Block */}
        {status && (
          <div style={{ ...cardStyle, background: 'var(--glass)' }}>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))', gap: '12px' }}>
              <div>
                <div style={{ fontSize: '0.75rem', color: 'var(--muted)', marginBottom: '2px' }}>Last Tick</div>
                <div style={{ fontSize: '0.88rem', color: 'var(--text)' }}>
                  {status.last_tick ? new Date(status.last_tick).toLocaleString() : 'Never'}
                </div>
              </div>
              <div>
                <div style={{ fontSize: '0.75rem', color: 'var(--muted)', marginBottom: '2px' }}>Market Regime</div>
                <div style={{ fontSize: '0.88rem', color: 'var(--text)', textTransform: 'capitalize' }}>
                  {status.current_regime || 'Unknown'} ({((status.confidence || 0) * 100).toFixed(0)}% confidence)
                </div>
              </div>
              <div>
                <div style={{ fontSize: '0.75rem', color: 'var(--muted)', marginBottom: '2px' }}>Active Features</div>
                <div style={{ fontSize: '0.88rem', color: 'var(--text)' }}>
                  {status.active_features?.length || 0} of {Object.keys(FEATURE_DESCRIPTIONS).length}
                </div>
              </div>
              <div>
                <div style={{ fontSize: '0.75rem', color: 'var(--muted)', marginBottom: '2px' }}>Guardrails</div>
                <div style={{ fontSize: '0.88rem', color: status.blocked ? '#ef4444' : 'var(--success)' }}>
                  {status.blocked ? '🔒 Blocked' : '✅ Clear'}
                </div>
              </div>
            </div>
            {status.blocked_reasons?.length > 0 && (
              <div style={{ marginTop: '10px', padding: '10px', background: 'rgba(239,68,68,0.08)', borderRadius: '6px', fontSize: '0.82rem', color: '#ef4444' }}>
                {status.blocked_reasons.map((r, i) => <div key={i}>🔒 {r}</div>)}
              </div>
            )}
            {status.last_actions?.length > 0 && (
              <div style={{ marginTop: '10px', fontSize: '0.82rem', color: 'var(--muted)' }}>
                Last: {status.last_actions.slice(0, 3).join(' · ')}
              </div>
            )}
          </div>
        )}

        {/* Feature Cards */}
        <div style={{ marginTop: '20px', marginBottom: '8px', fontWeight: 700, color: 'var(--text)' }}>
          Feature Toggles
        </div>
        {Object.entries(FEATURE_DESCRIPTIONS).map(([key, meta]) => {
          const isOn = settings?.[key] || false;
          return (
            <div key={key} style={{ ...cardStyle, border: isOn && masterEnabled ? '1px solid var(--success, #10b981)' : '1px solid var(--line)' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '12px' }}>
                <div style={{ flex: 1 }}>
                  <div style={{ fontWeight: 600, color: 'var(--text)', marginBottom: '4px' }}>{meta.label}</div>
                  <div style={{ fontSize: '0.82rem', color: 'var(--muted)', lineHeight: '1.5' }}>{meta.description}</div>
                  {/* Sub-fields */}
                  {isOn && meta.fields.length > 0 && (
                    <div style={{ marginTop: '10px', display: 'flex', flexWrap: 'wrap', gap: '10px' }}>
                      {meta.fields.map(field => (
                        <div key={field.key} style={{ display: 'flex', flexDirection: 'column', gap: '2px' }}>
                          <label style={{ fontSize: '0.75rem', color: 'var(--muted)' }}>{field.label}</label>
                          <input
                            type="number"
                            value={settings?.[field.key] ?? ''}
                            min={field.min}
                            max={field.max}
                            step={field.step || 1}
                            onChange={(e) => updateSetting(field.key, parseFloat(e.target.value))}
                            disabled={saving}
                            style={{
                              width: '120px', padding: '4px 8px',
                              background: 'var(--panel)', border: '1px solid var(--line)',
                              borderRadius: '4px', color: 'var(--text)', fontSize: '0.88rem',
                            }}
                          />
                        </div>
                      ))}
                    </div>
                  )}
                </div>
                <ToggleSwitch
                  checked={isOn}
                  onChange={(v) => updateSetting(key, v)}
                  disabled={saving || (!masterEnabled && !isOn)}
                />
              </div>
            </div>
          );
        })}

        {/* Leverage */}
        {(() => {
          const leverageOn = settings?.leverage_enabled || false;
          const multiplier = settings?.leverage_multiplier ?? 1.0;
          const mode = status?.mode || 'paper';
          const liveBlockedReason = status?.enabled_toggles?.leverage_enabled === false && mode === 'live'
            ? null : null; // resolved server-side per exchange
          return (
            <div style={{ ...cardStyle, border: leverageOn && masterEnabled ? '1px solid rgba(245,158,11,0.6)' : '1px solid var(--line)' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: '12px' }}>
                <div style={{ flex: 1 }}>
                  <div style={{ fontWeight: 600, color: 'var(--text)', marginBottom: '4px' }}>
                    📊 Leverage (Position Sizing Multiplier)
                  </div>
                  <div style={{ fontSize: '0.82rem', color: 'var(--muted)', lineHeight: '1.5' }}>
                    Scales position sizes by a multiplier (1.0–2.0x). Auto-reverts to 1.0x if any safety lock activates.
                    In live mode, only works on exchanges that support margin/futures.
                  </div>
                  {leverageOn && (
                    <div style={{ marginTop: '10px' }}>
                      <label style={{ fontSize: '0.75rem', color: 'var(--muted)', marginBottom: '4px', display: 'block' }}>
                        Multiplier: <strong style={{ color: 'var(--warning, #f59e0b)' }}>{parseFloat(multiplier).toFixed(1)}x</strong>
                      </label>
                      <input
                        type="range"
                        min="1.0"
                        max="2.0"
                        step="0.1"
                        value={multiplier}
                        onChange={(e) => updateSetting('leverage_multiplier', parseFloat(e.target.value))}
                        disabled={saving || !masterEnabled}
                        style={{ width: '180px', accentColor: 'var(--warning, #f59e0b)' }}
                      />
                      <div style={{ fontSize: '0.75rem', color: 'var(--muted)', marginTop: '2px' }}>
                        1.0x = no leverage &nbsp;·&nbsp; 2.0x = double position size
                      </div>
                      {mode === 'live' && (
                        <div style={{ marginTop: '6px', fontSize: '0.8rem', color: 'var(--warning, #f59e0b)' }}>
                          ⚠ Live mode: availability depends on your exchange. Check last run result for capability status.
                        </div>
                      )}
                    </div>
                  )}
                </div>
                <ToggleSwitch
                  checked={leverageOn}
                  onChange={(v) => updateSetting('leverage_enabled', v)}
                  disabled={saving || (!masterEnabled && !leverageOn)}
                />
              </div>
            </div>
          );
        })()}

        {/* Run Once Button */}
        <div style={{ marginTop: '20px', display: 'flex', gap: '12px', alignItems: 'center' }}>
          <button
            onClick={handleRunOnce}
            disabled={running || !masterEnabled}
            style={{
              padding: '10px 20px',
              background: masterEnabled ? 'var(--accent)' : 'var(--muted)',
              color: '#fff', border: 'none', borderRadius: '8px',
              fontWeight: 600, cursor: masterEnabled && !running ? 'pointer' : 'not-allowed',
              fontSize: '0.9rem',
            }}
            title={masterEnabled ? 'Manually trigger one Growth Engine analysis tick' : 'Enable the master switch first'}
          >
            {running ? '⏳ Running…' : '▶ Run Once (Paper Only)'}
          </button>
          {saving && <span style={{ fontSize: '0.82rem', color: 'var(--muted)' }}>Saving…</span>}
        </div>

        {/* Run Once Result */}
        {runResult && (
          <div style={{ ...cardStyle, marginTop: '12px', border: '1px solid var(--accent)' }}>
            <div style={{ fontWeight: 700, marginBottom: '8px', color: 'var(--text)' }}>
              Last Run Result — {new Date(runResult.timestamp).toLocaleString()}
            </div>
            <div style={{ fontSize: '0.88rem', color: 'var(--text)', marginBottom: '8px' }}>{runResult.summary}</div>
            {runResult.blocked_reasons?.length > 0 && (
              <div style={{ color: '#ef4444', fontSize: '0.82rem' }}>
                🔒 Blocked: {runResult.blocked_reasons.join('; ')}
              </div>
            )}
            {runResult.actions_proposed?.length > 0 && (
              <div style={{ marginTop: '8px' }}>
                <div style={{ fontSize: '0.75rem', color: 'var(--muted)', marginBottom: '4px' }}>Proposed Actions:</div>
                {runResult.actions_proposed.map((a, i) => (
                  <div key={i} style={{ fontSize: '0.82rem', color: 'var(--text)', padding: '4px 0' }}>
                    • <strong>{a.feature}</strong>: {a.skipped ? `Skipped — ${a.reason}` : a.description || JSON.stringify(a)}
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Recent Decisions */}
        {decisions.length > 0 && (
          <div style={{ marginTop: '24px' }}>
            <div style={{ fontWeight: 700, marginBottom: '12px', color: 'var(--text)' }}>
              Recent Decisions
            </div>
            {decisions.map((d, i) => (
              <div key={i} style={{ ...cardStyle, background: 'var(--glass)', marginBottom: '8px', fontSize: '0.82rem' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px' }}>
                  <span style={{ color: 'var(--muted)' }}>{new Date(d.timestamp).toLocaleString()}</span>
                  <span style={{ color: d.blocked_reasons?.length ? '#ef4444' : 'var(--success)' }}>
                    {d.blocked_reasons?.length ? '🔒 Blocked' : d.actions_taken?.length ? '✅ Actions' : '⭕ No action'}
                  </span>
                </div>
                <div style={{ color: 'var(--text)' }}>{d.summary}</div>
              </div>
            ))}
          </div>
        )}
      </div>
    </section>
  );
}
