import { useState, useEffect, useCallback } from 'react';

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
  }, [fetchTruth]);

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
                            <span key={i} className="truth-reason-badge">{r}</span>
                          ))
                        : Object.entries(info.reasons).map(([botId, reasons]) => (
                            <div key={botId} style={{ fontSize: '0.75rem', marginBottom: '2px' }}>
                              <b>{botId.slice(0, 8)}…</b>: {Array.isArray(reasons) ? reasons.join(', ') : String(reasons)}
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
