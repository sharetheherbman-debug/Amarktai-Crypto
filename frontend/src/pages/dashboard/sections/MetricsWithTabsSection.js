import React from 'react';
import ErrorBoundary from '../../../components/ErrorBoundary';
import DecisionTrace from '../../../components/DecisionTrace';
import WhaleFlowHeatmap from '../../../components/WhaleFlowHeatmap';
import PrometheusMetrics from '../../../components/PrometheusMetrics';

const NOT_AVAILABLE = 'Not available';

const MetricsWithTabsSection = ({ metrics, metricsTab, setMetricsTab }) => {
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
          </div>
        </div>
      </section>
  );
};

export default MetricsWithTabsSection;
