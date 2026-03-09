import { useState, useEffect, useCallback } from 'react';
import { post, notifyError } from '../../../lib/apiClient';

const BOT_ID_DISPLAY_LENGTH = 8; // Characters of bot ID to show in reason display

// Human-readable labels for common reason codes
const REASON_LABELS = {
  bot_paused: 'Bot is paused — resume it from Bot Fleet controls',
  bot_stopped: 'Bot is stopped — start it from Bot Fleet controls',
  bot_deleted: 'Bot has been deleted',
  bot_quarantined: 'Bot is quarantined for retraining',
  daily_loss_lock: 'Daily loss limit reached — reset via Risk panel',
  circuit_breaker_active: 'Circuit breaker is active',
  no_trading_mode: 'Bot has no trading mode set',
  scheduler_stale: 'Scheduler has not ticked recently',
  balance_mismatch: 'Wallet balance does not reconcile',
  negative_balance: 'Wallet has negative balance',
  no_active_bots_not_configured: 'Exchange not configured',
};

/**
 * TruthConsoleSection — Admin-only Truth Console dashboard section
 *
 * Dropdown list of subsystems with PASS/FAIL and evidence details.
 * Reads from GET /api/admin/truth/summary (same Truth Kernel logic).
 * Not visible unless admin.
 */
export default function TruthConsoleSection({ axiosConfig }) {
  const [truthData, setTruthData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [expandedSubs, setExpandedSubs] = useState({});
  const [repairing, setRepairing] = useState(false);
  const [repairResult, setRepairResult] = useState(null);

  const fetchTruth = useCallback(async () => {
    try {
      const res = await fetch('/api/admin/truth/summary', {
        headers: axiosConfig?.headers || {},
      });
      if (res.status === 403) {
        setError('Admin access required');
        return;
      }
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setTruthData(data);
      setError(null);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [axiosConfig]);

  useEffect(() => {
    fetchTruth();
    const interval = setInterval(fetchTruth, 30000);
    return () => clearInterval(interval);
  }, [fetchTruth]);

  const handleRepairBots = async () => {
    setRepairing(true);
    setRepairResult(null);
    try {
      const result = await post('/admin/truth/repair-bots', {});
      setRepairResult(result);
      await fetchTruth();
    } catch (err) {
      notifyError(err, 'Repair failed');
    } finally {
      setRepairing(false);
    }
  };

  const toggleExpand = (key) => {
    setExpandedSubs((prev) => ({ ...prev, [key]: !prev[key] }));
  };

  const getStatusIcon = (status) => {
    switch (status) {
      case 'PASS': return '✅';
      case 'FAIL': return '❌';
      case 'WARN': return '⚠️';
      default: return '❓';
    }
  };

  const getStatusColor = (status) => {
    switch (status) {
      case 'PASS': return '#22c55e';
      case 'FAIL': return '#ef4444';
      case 'WARN': return '#f59e0b';
      default: return '#6b7280';
    }
  };

  // Derive what's blocking paper/live trading from subsystem statuses
  const getPaperBlockers = (subsystems) => {
    const blockers = [];
    const botElig = subsystems?.BOT_ELIGIBILITY;
    if (botElig?.status === 'FAIL') blockers.push(`BOT_ELIGIBILITY: ${botElig.detail}`);
    const paper = subsystems?.PAPER_ENGINE;
    if (paper?.status === 'FAIL') blockers.push(`PAPER_ENGINE: ${paper.detail}`);
    const wallet = subsystems?.WALLET_RECONCILIATION;
    if (wallet?.status === 'FAIL') blockers.push(`WALLET: ${wallet.detail}`);
    return blockers;
  };

  const getLiveBlockers = (subsystems) => {
    const blockers = [...getPaperBlockers(subsystems)];
    const exchange = subsystems?.EXCHANGE_HEALTH;
    if (exchange?.status === 'FAIL' || exchange?.status === 'WARN') {
      blockers.push(`EXCHANGE_HEALTH: ${exchange.detail}`);
    }
    return blockers;
  };

  if (loading) {
    return (
      <div className="truth-console">
        <h2>🔍 Truth Console</h2>
        <p style={{ color: '#9ca3af' }}>Loading truth data...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div className="truth-console">
        <h2>🔍 Truth Console</h2>
        <p style={{ color: '#ef4444' }}>{error}</p>
      </div>
    );
  }

  const subsystems = truthData?.subsystems || {};
  const contradictions = truthData?.contradictions || [];
  const overall = truthData?.overall_status || 'UNKNOWN';
  const paperBlockers = getPaperBlockers(subsystems);
  const liveBlockers = getLiveBlockers(subsystems);

  return (
    <div className="truth-console">
      <div className="truth-header">
        <h2>🔍 Truth Console</h2>
        <span
          className="truth-overall"
          style={{ color: getStatusColor(overall.includes('FAIL') ? 'FAIL' : overall.includes('WARN') ? 'WARN' : 'PASS') }}
        >
          {overall}
        </span>
        <button className="truth-refresh" onClick={fetchTruth} title="Refresh">↻</button>
      </div>

      {/* Paper / Live readiness summary */}
      <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap', margin: '12px 0' }}>
        <div style={{
          flex: 1, minWidth: 220, padding: '10px 14px',
          background: paperBlockers.length === 0 ? 'rgba(34,197,94,0.08)' : 'rgba(239,68,68,0.08)',
          border: `1px solid ${paperBlockers.length === 0 ? '#22c55e' : '#ef4444'}`,
          borderRadius: 8,
        }}>
          <div style={{ fontWeight: 700, fontSize: '0.85rem', marginBottom: 4, color: paperBlockers.length === 0 ? '#22c55e' : '#ef4444' }}>
            {paperBlockers.length === 0 ? '✅ Paper Trading: READY' : '❌ Paper Trading: BLOCKED'}
          </div>
          {paperBlockers.map((b, i) => (
            <div key={i} style={{ fontSize: '0.78rem', color: '#ef4444', marginTop: 2 }}>• {b}</div>
          ))}
        </div>
        <div style={{
          flex: 1, minWidth: 220, padding: '10px 14px',
          background: liveBlockers.length === 0 ? 'rgba(34,197,94,0.08)' : 'rgba(245,158,11,0.08)',
          border: `1px solid ${liveBlockers.length === 0 ? '#22c55e' : '#f59e0b'}`,
          borderRadius: 8,
        }}>
          <div style={{ fontWeight: 700, fontSize: '0.85rem', marginBottom: 4, color: liveBlockers.length === 0 ? '#22c55e' : '#f59e0b' }}>
            {liveBlockers.length === 0 ? '✅ Live Trading: READY' : '⚠ Live Trading: NOT READY'}
          </div>
          {liveBlockers.map((b, i) => (
            <div key={i} style={{ fontSize: '0.78rem', color: '#f59e0b', marginTop: 2 }}>• {b}</div>
          ))}
        </div>
      </div>

      {/* Repair button */}
      <div style={{ marginBottom: 12 }}>
        <button
          onClick={handleRepairBots}
          disabled={repairing}
          style={{
            padding: '6px 14px', borderRadius: 6, border: '1px solid var(--accent2, #60a5fa)',
            background: 'rgba(96,165,250,0.12)', color: 'var(--accent2, #60a5fa)',
            cursor: repairing ? 'not-allowed' : 'pointer', fontSize: '0.82rem', fontWeight: 600,
          }}
        >
          {repairing ? '⏳ Repairing...' : '🔧 Repair Stuck Bots'}
        </button>
        {repairResult && (
          <span style={{ marginLeft: 10, fontSize: '0.8rem', color: '#22c55e' }}>
            ✅ Reconciled {repairResult.reconciled_count} bot(s)
          </span>
        )}
      </div>

      {/* Contradictions Alert */}
      {contradictions.length > 0 && (
        <div className="truth-contradictions">
          <h3>⚡ Contradictions ({contradictions.length})</h3>
          {contradictions.map((c, i) => (
            <div key={i} className={`truth-contradiction truth-sev-${c.severity}`}>
              <strong>[{c.severity.toUpperCase()}] {c.id}</strong>
              <p>{c.description}</p>
              <div className="truth-expect">
                <span><b>Expected:</b> {c.expected}</span>
                <span><b>Actual:</b> {c.actual}</span>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Subsystem List */}
      <div className="truth-subsystems">
        {Object.entries(subsystems).map(([key, info]) => (
          <div key={key} className="truth-subsystem-item">
            <div
              className="truth-subsystem-header"
              onClick={() => toggleExpand(key)}
              onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); toggleExpand(key); } }}
              role="button"
              tabIndex={0}
              aria-expanded={!!expandedSubs[key]}
              style={{ cursor: 'pointer' }}
            >
              <span className="truth-status-icon">{getStatusIcon(info.status)}</span>
              <span className="truth-subsystem-name">{key}</span>
              <span className="truth-subsystem-detail">{info.detail}</span>
              <span className="truth-expand-arrow">{expandedSubs[key] ? '▼' : '▶'}</span>
            </div>

            {expandedSubs[key] && (
              <div className="truth-subsystem-body">
                <div className="truth-row">
                  <span className="truth-label">Status</span>
                  <span style={{ color: getStatusColor(info.status) }}>{info.status}</span>
                </div>
                <div className="truth-row">
                  <span className="truth-label">Last Run</span>
                  <span>{info.last_run || '—'}</span>
                </div>

                {/* Counters */}
                {info.counters && (
                  <div className="truth-counters">
                    <span className="truth-label">Counters</span>
                    <div className="truth-counter-grid">
                      {Object.entries(info.counters).map(([k, v]) => (
                        <div key={k} className="truth-counter">
                          <span className="truth-counter-key">{k}</span>
                          <span className="truth-counter-val">{String(v)}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Reasons */}
                {info.reasons && (Array.isArray(info.reasons) ? info.reasons.length > 0 : Object.keys(info.reasons).length > 0) && (
                  <div className="truth-reasons">
                    <span className="truth-label">Reason Codes</span>
                    <div>
                      {Array.isArray(info.reasons)
                        ? info.reasons.map((r, i) => (
                            <div key={i} style={{ marginBottom: 2 }}>
                              <span className="truth-reason-badge">{r}</span>
                              {REASON_LABELS[r] && (
                                <span style={{ fontSize: '0.75rem', color: '#9ca3af', marginLeft: 6 }}>
                                  — {REASON_LABELS[r]}
                                </span>
                              )}
                            </div>
                          ))
                        : Object.entries(info.reasons).map(([botId, reasons]) => (
                            <div key={botId} style={{ fontSize: '0.75rem', marginBottom: '4px' }}>
                              <b>{botId.slice(0, BOT_ID_DISPLAY_LENGTH)}…</b>:{' '}
                              {(Array.isArray(reasons) ? reasons : [String(reasons)]).map((r, i) => (
                                <span key={i}>
                                  <span className="truth-reason-badge">{r}</span>
                                  {REASON_LABELS[r] && (
                                    <span style={{ color: '#9ca3af', marginLeft: 4 }}>({REASON_LABELS[r]})</span>
                                  )}
                                </span>
                              ))}
                            </div>
                          ))}
                    </div>
                  </div>
                )}

                {/* Endpoint Link */}
                {info.endpoint && (
                  <div className="truth-row">
                    <span className="truth-label">Endpoint</span>
                    <code className="truth-endpoint">{info.endpoint}</code>
                  </div>
                )}
              </div>
            )}
          </div>
        ))}
      </div>

      {/* Rule Precedence */}
      {truthData?.rule_precedence && (
        <div className="truth-precedence">
          <h3>📋 Rule Precedence</h3>
          <ol className="truth-precedence-list">
            {truthData.rule_precedence.map((rule, i) => (
              <li key={i}>{rule.replace(/_/g, ' ')}</li>
            ))}
          </ol>
        </div>
      )}
    </div>
  );
}
