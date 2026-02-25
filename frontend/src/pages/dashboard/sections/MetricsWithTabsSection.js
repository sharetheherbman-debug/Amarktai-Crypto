import React, { useState, useEffect } from 'react';
import ErrorBoundary from '../../../components/ErrorBoundary';
import DecisionTrace from '../../../components/DecisionTrace';
import WhaleFlowHeatmap from '../../../components/WhaleFlowHeatmap';
import PrometheusMetrics from '../../../components/PrometheusMetrics';
import apiClient from '@/lib/apiClient';

const NOT_AVAILABLE = 'Not available';

function MarketIntelligencePanel() {
  const [intel, setIntel] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    const fetch = async () => {
      try {
        const res = await apiClient.get('/events/market-intelligence');
        if (!cancelled) { setIntel(res.data); setLoading(false); }
      } catch { if (!cancelled) setLoading(false); }
    };
    fetch();
    const iv = setInterval(fetch, 900000); // refresh every 15 min
    return () => { cancelled = true; clearInterval(iv); };
  }, []);

  const moodColor = { positive: 'var(--success)', negative: 'var(--error)', neutral: 'var(--muted)' };
  const moodEmoji = { positive: '📈', negative: '📉', neutral: '➡️' };

  if (loading) return <p style={{ color: 'var(--muted)' }}>Loading market intelligence from CoinStats…</p>;
  if (!intel) return <p style={{ color: 'var(--muted)' }}>Market intelligence unavailable.</p>;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
      <div style={{ display: 'flex', gap: '12px', flexWrap: 'wrap' }}>
        <div style={{ padding: '8px 16px', borderRadius: '8px', background: `${moodColor[intel.mood] || 'var(--muted)'}22`, border: `1px solid ${moodColor[intel.mood] || 'var(--muted)'}55`, color: moodColor[intel.mood] || 'var(--muted)', fontWeight: '700' }}>
          {moodEmoji[intel.mood] || '📊'} Mood: {intel.mood?.charAt(0).toUpperCase() + intel.mood?.slice(1) || 'Unknown'}
        </div>
        {intel.top_risk && intel.top_risk !== 'none' && (
          <div style={{ padding: '8px 16px', borderRadius: '8px', background: 'var(--warning, #f59e0b)22', border: '1px solid var(--warning, #f59e0b)55', color: 'var(--warning, #f59e0b)', fontWeight: '600' }}>
            ⚠️ Risk: {intel.top_risk}
          </div>
        )}
      </div>

      {[
        { label: 'What happened', value: intel.what_happened },
        { label: 'Why it matters', value: intel.why_it_matters },
        { label: 'What Amarktai Network is doing', value: intel.what_amarktai_is_doing },
        { label: 'Confidence', value: intel.confidence },
      ].map(({ label, value }) => value && (
        <div key={label} style={{ padding: '12px 16px', background: 'var(--glass)', borderRadius: '8px', border: '1px solid var(--line)' }}>
          <div style={{ fontSize: '0.75rem', color: 'var(--muted)', marginBottom: '4px', textTransform: 'uppercase', letterSpacing: '0.05em' }}>{label}</div>
          <div style={{ lineHeight: '1.5' }}>{value}</div>
        </div>
      ))}

      <div style={{ fontSize: '0.75rem', color: 'var(--muted)', textAlign: 'right' }}>
        Source: {intel.source} · Updated: {intel.updated_at ? new Date(intel.updated_at).toLocaleString() : 'Pending first fetch'}
      </div>
    </div>
  );
}

const MetricsWithTabsSection = ({ formatDate, getAlertColor, metrics, metricsTab, setMetricsTab, showSection }) => {
  return (
      <section className="section active">
        <div className="card">
          <h2>📊 Metrics Dashboard</h2>
          
          {/* Horizontal Tabs */}
          <div style={{
            display: 'flex', 
            gap: '10px', 
            marginBottom: '24px', 
            marginTop: '16px',
            borderBottom: '2px solid var(--line)', 
            paddingBottom: '10px',
            flexWrap: 'wrap'
          }}>
            <button 
              onClick={() => setMetricsTab('decision-trace')}
              style={{
                padding: '10px 20px',
                background: metricsTab === 'decision-trace' ? 'linear-gradient(135deg, var(--accent2) 0%, var(--accent2) 100%)' : 'var(--glass)',
                border: '2px solid ' + (metricsTab === 'decision-trace' ? 'var(--accent2)' : 'var(--line)'),
                borderRadius: '8px',
                color: metricsTab === 'decision-trace' ? '#fff' : 'var(--text)',
                cursor: 'pointer',
                fontSize: '0.95rem',
                fontWeight: metricsTab === 'decision-trace' ? '700' : '600',
                transition: 'all 0.3s',
                boxShadow: metricsTab === 'decision-trace' ? '0 4px 12px rgba(74, 144, 226, 0.4)' : 'none'
              }}
            >
              🎬 Decision Trace
            </button>
            <button 
              onClick={() => setMetricsTab('whale-flow')}
              style={{
                padding: '10px 20px',
                background: metricsTab === 'whale-flow' ? 'linear-gradient(135deg, var(--accent2) 0%, var(--accent2) 100%)' : 'var(--glass)',
                border: '2px solid ' + (metricsTab === 'whale-flow' ? 'var(--accent2)' : 'var(--line)'),
                borderRadius: '8px',
                color: metricsTab === 'whale-flow' ? '#fff' : 'var(--text)',
                cursor: 'pointer',
                fontSize: '0.95rem',
                fontWeight: metricsTab === 'whale-flow' ? '700' : '600',
                transition: 'all 0.3s',
                boxShadow: metricsTab === 'whale-flow' ? '0 4px 12px rgba(74, 144, 226, 0.4)' : 'none'
              }}
            >
              🐋 Whale Flow
            </button>
            <button 
              onClick={() => setMetricsTab('system-metrics')}
              style={{
                padding: '10px 20px',
                background: metricsTab === 'system-metrics' ? 'linear-gradient(135deg, var(--accent2) 0%, var(--accent2) 100%)' : 'var(--glass)',
                border: '2px solid ' + (metricsTab === 'system-metrics' ? 'var(--accent2)' : 'var(--line)'),
                borderRadius: '8px',
                color: metricsTab === 'system-metrics' ? '#fff' : 'var(--text)',
                cursor: 'pointer',
                fontSize: '0.95rem',
                fontWeight: metricsTab === 'system-metrics' ? '700' : '600',
                transition: 'all 0.3s',
                boxShadow: metricsTab === 'system-metrics' ? '0 4px 12px rgba(74, 144, 226, 0.4)' : 'none'
              }}
            >
              📊 System Metrics
            </button>
            <button
              onClick={() => setMetricsTab('market-intelligence')}
              style={{
                padding: '10px 20px',
                background: metricsTab === 'market-intelligence' ? 'linear-gradient(135deg, var(--accent2) 0%, var(--accent2) 100%)' : 'var(--glass)',
                border: '2px solid ' + (metricsTab === 'market-intelligence' ? 'var(--accent2)' : 'var(--line)'),
                borderRadius: '8px',
                color: metricsTab === 'market-intelligence' ? '#fff' : 'var(--text)',
                cursor: 'pointer',
                fontSize: '0.95rem',
                fontWeight: metricsTab === 'market-intelligence' ? '700' : '600',
                transition: 'all 0.3s',
                boxShadow: metricsTab === 'market-intelligence' ? '0 4px 12px rgba(74, 144, 226, 0.4)' : 'none'
              }}
            >
              🧠 Market Intelligence
            </button>
          </div>

          {/* Tab Content */}
          <div style={{marginTop: '20px'}}>
            {metricsTab === 'decision-trace' && (
              <ErrorBoundary title="Decision Trace Error" message="Unable to load decision trace. The service may be unavailable.">
                <DecisionTrace />
              </ErrorBoundary>
            )}
            {metricsTab === 'whale-flow' && (
              <ErrorBoundary title="Whale Flow Error" message="Unable to load whale flow heatmap. Data may be unavailable.">
                <WhaleFlowHeatmap />
              </ErrorBoundary>
            )}
            {metricsTab === 'system-metrics' && (
              <ErrorBoundary title="System Metrics Error" message="Unable to load system metrics. Prometheus may not be configured.">
                <PrometheusMetrics />
              </ErrorBoundary>
            )}
            {metricsTab === 'market-intelligence' && (
              <ErrorBoundary title="Market Intelligence Error" message="Unable to load market intelligence. CoinStats data may be unavailable.">
                <MarketIntelligencePanel />
              </ErrorBoundary>
            )}
          </div>
        </div>
      </section>
  );
};

export default MetricsWithTabsSection;
