import React, { useState, useEffect } from 'react';

/** Use empty base — all fetch URLs already include /api prefix */
const API = '';

const HuggingFacePanel = ({ axiosConfig }) => {
  const [status, setStatus] = useState({ configured: false, reachable: false });
  const [testResult, setTestResult] = useState(null);
  const [sentimentText, setSentimentText] = useState('');
  const [sentimentResult, setSentimentResult] = useState(null);
  const [loading, setLoading] = useState(false);

  const headers = axiosConfig?.headers || {};

  useEffect(() => {
    loadStatus();
    const interval = setInterval(loadStatus, 60000);
    return () => clearInterval(interval);
  }, []); // eslint-disable-line

  const loadStatus = async () => {
    try {
      const res = await fetch(`${API}/api/huggingface/status`, { headers });
      if (res.ok) setStatus(await res.json());
    } catch { /* ignore */ }
  };

  const handleTestConnection = async () => {
    setLoading(true);
    try {
      const res = await fetch(`${API}/api/huggingface/test-connection`, {
        method: 'POST',
        headers: { ...headers, 'Content-Type': 'application/json' },
        body: JSON.stringify({}),
      });
      if (res.ok) setTestResult(await res.json());
      else setTestResult({ connected: false, message: `HTTP ${res.status}` });
    } catch (err) {
      setTestResult({ connected: false, message: err.message });
    }
    setLoading(false);
  };

  const handleSentiment = async () => {
    if (!sentimentText.trim()) return;
    setLoading(true);
    try {
      const res = await fetch(`${API}/api/sentiment/analyze`, {
        method: 'POST',
        headers: { ...headers, 'Content-Type': 'application/json' },
        body: JSON.stringify({ texts: [sentimentText.trim()] }),
      });
      if (res.ok) {
        const data = await res.json();
        setSentimentResult(data?.results?.[0] || null);
      } else {
        setSentimentResult({ error: `HTTP ${res.status}` });
      }
    } catch (err) {
      setSentimentResult({ error: err.message });
    }
    setLoading(false);
  };

  const renderLabel = (label) => {
    const name = (label.label || '').toLowerCase();
    const score = (label.score * 100).toFixed(1);
    const color = name.includes('positive') ? '#10b981' : name.includes('negative') ? '#ef4444' : '#f59e0b';
    return (
      <span key={label.label} style={{
        display: 'inline-block',
        padding: '2px 8px',
        borderRadius: 4,
        fontSize: 11,
        fontWeight: 600,
        marginRight: 6,
        background: `${color}20`,
        color,
        border: `1px solid ${color}40`,
      }}>
        {label.label}: {score}%
      </span>
    );
  };

  return (
    <div style={{
      background: 'rgba(15,23,42,0.7)',
      backdropFilter: 'blur(12px)',
      border: '1px solid rgba(251,191,36,0.25)',
      borderRadius: 12,
      padding: 20,
      marginBottom: 16
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 14 }}>
        <span style={{ fontSize: 22 }}>🤗</span>
        <h3 style={{ margin: 0, fontSize: 16, fontWeight: 700, color: '#e2e8f0' }}>Hugging Face Sentiment</h3>
        <span style={{
          marginLeft: 'auto',
          padding: '2px 10px',
          borderRadius: 20,
          fontSize: 11,
          fontWeight: 600,
          background: status.reachable ? 'rgba(16,185,129,0.15)' : 'rgba(239,68,68,0.15)',
          color: status.reachable ? '#10b981' : '#ef4444',
          border: `1px solid ${status.reachable ? 'rgba(16,185,129,0.3)' : 'rgba(239,68,68,0.3)'}`,
        }}>
          {status.reachable ? '● Connected' : status.configured ? '○ Unreachable' : '○ Not configured'}
        </span>
      </div>

      {!status.configured && (
        <p style={{ color: '#94a3b8', fontSize: 13 }}>
          Configure your Hugging Face API token in API Setup to enable AI sentiment analysis.
        </p>
      )}

      {status.configured && (
        <>
          <div style={{ marginBottom: 14 }}>
            <button onClick={handleTestConnection} disabled={loading} style={{
              padding: '6px 14px',
              borderRadius: 6,
              border: 'none',
              fontSize: 12,
              fontWeight: 600,
              cursor: loading ? 'not-allowed' : 'pointer',
              background: 'rgba(251,191,36,0.2)',
              color: '#fbbf24',
            }}>
              {loading ? 'Testing…' : '🔌 Test Connection'}
            </button>
            {testResult && (
              <span style={{
                marginLeft: 10,
                fontSize: 12,
                color: testResult.connected ? '#10b981' : '#ef4444',
              }}>
                {testResult.message}
              </span>
            )}
          </div>

          <div style={{ marginBottom: 12 }}>
            <label style={{ display: 'block', fontSize: 12, color: '#94a3b8', marginBottom: 4 }}>
              Analyze sentiment:
            </label>
            <div style={{ display: 'flex', gap: 8 }}>
              <input
                type="text"
                value={sentimentText}
                onChange={(e) => setSentimentText(e.target.value)}
                placeholder="e.g. Bitcoin breaks all-time high..."
                style={{
                  flex: 1,
                  padding: '6px 10px',
                  borderRadius: 6,
                  border: '1px solid rgba(51,65,85,0.6)',
                  background: 'rgba(15,23,42,0.6)',
                  color: '#e2e8f0',
                  fontSize: 12,
                  outline: 'none',
                }}
                onKeyDown={(e) => e.key === 'Enter' && handleSentiment()}
              />
              <button onClick={handleSentiment} disabled={loading || !sentimentText.trim()} style={{
                padding: '6px 14px',
                borderRadius: 6,
                border: 'none',
                fontSize: 12,
                fontWeight: 600,
                cursor: 'pointer',
                background: 'rgba(99,102,241,0.3)',
                color: '#a5b4fc',
              }}>
                Analyze
              </button>
            </div>
          </div>

          {sentimentResult && !sentimentResult.error && (
            <div style={{
              padding: 10,
              borderRadius: 8,
              background: 'rgba(30,41,59,0.5)',
              fontSize: 12,
            }}>
              <div style={{ color: '#94a3b8', marginBottom: 6 }}>Result:</div>
              {Array.isArray(sentimentResult.labels) && sentimentResult.labels.map(renderLabel)}
            </div>
          )}

          {sentimentResult?.error && (
            <div style={{ fontSize: 12, color: '#ef4444' }}>Error: {sentimentResult.error}</div>
          )}
        </>
      )}
    </div>
  );
};

export default HuggingFacePanel;
