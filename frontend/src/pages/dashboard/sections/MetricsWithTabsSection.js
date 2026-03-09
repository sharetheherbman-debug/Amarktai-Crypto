import React from 'react';
import ErrorBoundary from '../../../components/ErrorBoundary';
import DecisionTrace from '../../../components/DecisionTrace';
import WhaleFlowHeatmap from '../../../components/WhaleFlowHeatmap';
import PrometheusMetrics from '../../../components/PrometheusMetrics';
import MarketIntelligencePanel from './MarketIntelligencePanel';
import HuggingFacePanel from './HuggingFacePanel';
import {
  MarketBrainPanel,
  WhaleFlowPanel,
  SentimentPanel,
  OrderbookPanel,
  CapitalPanel,
  GeneticsPanel,
} from './DashboardIntelligencePanels';

const MetricsWithTabsSection = ({ metrics, metricsTab, setMetricsTab, axiosConfig }) => {
  const tabStyle = (active) => ({
    padding: '10px 20px',
    background: active ? 'linear-gradient(135deg, var(--accent2) 0%, var(--accent2) 100%)' : 'var(--glass)',
    border: '2px solid ' + (active ? 'var(--accent2)' : 'var(--line)'),
    borderRadius: '8px',
    color: active ? '#fff' : 'var(--text)',
    cursor: 'pointer',
    fontSize: '0.95rem',
    fontWeight: active ? '700' : '600',
    transition: 'all 0.3s',
    boxShadow: active ? '0 4px 12px rgba(74, 144, 226, 0.4)' : 'none',
  });

  return (
      <section className="section active">
        <div className="card">
          <h2>📊 Analytics & Metrics</h2>
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
            <button onClick={() => setMetricsTab('decision-trace')} style={tabStyle(metricsTab === 'decision-trace')}>
              🎬 Decision Trace
            </button>
            <button onClick={() => setMetricsTab('whale-flow')} style={tabStyle(metricsTab === 'whale-flow')}>
              🐋 Whale Flow
            </button>
            <button onClick={() => setMetricsTab('system-metrics')} style={tabStyle(metricsTab === 'system-metrics')}>
              📊 System Metrics
            </button>
            <button onClick={() => setMetricsTab('market-intelligence')} style={tabStyle(metricsTab === 'market-intelligence')}>
              🧠 Market Intelligence
            </button>
            <button onClick={() => setMetricsTab('intelligence-panels')} style={tabStyle(metricsTab === 'intelligence-panels')}>
              🔬 Intelligence Panels
            </button>
            <button onClick={() => setMetricsTab('huggingface')} style={tabStyle(metricsTab === 'huggingface')}>
              🤗 AI Analysis
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
              <ErrorBoundary title="Market Intelligence Error" message="Unable to load market intelligence data.">
                <MarketIntelligencePanel />
              </ErrorBoundary>
            )}
            {metricsTab === 'intelligence-panels' && (
              <ErrorBoundary title="Intelligence Panels Error" message="Unable to load intelligence panels.">
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: 12 }}>
                  <MarketBrainPanel />
                  <WhaleFlowPanel />
                  <SentimentPanel />
                  <OrderbookPanel />
                  <CapitalPanel />
                  <GeneticsPanel />
                </div>
              </ErrorBoundary>
            )}
            {metricsTab === 'huggingface' && (
              <ErrorBoundary title="AI Analysis Error" message="Unable to load HuggingFace AI analysis.">
                <HuggingFacePanel axiosConfig={axiosConfig} />
              </ErrorBoundary>
            )}
          </div>
        </div>
      </section>
  );
};

export default MetricsWithTabsSection;
