import React from 'react';
import ErrorBoundary from '../../../components/ErrorBoundary';
import DecisionTrace from '../../../components/DecisionTrace';
import MarketIntelligencePanel from './MarketIntelligencePanel';
import HuggingFacePanel from './HuggingFacePanel';
import {
  MarketBrainPanel,
  CapitalPanel,
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
          <h2>📊 Analytics & Intelligence</h2>
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
              🎬 Trade Decisions
            </button>
            <button onClick={() => setMetricsTab('market-state')} style={tabStyle(metricsTab === 'market-state')}>
              🧠 Market State
            </button>
            <button onClick={() => setMetricsTab('capital')} style={tabStyle(metricsTab === 'capital')}>
              💰 Capital
            </button>
            <button onClick={() => setMetricsTab('huggingface')} style={tabStyle(metricsTab === 'huggingface')}>
              🤖 AI Analysis
            </button>
          </div>

          {/* Tab Content */}
          <div style={{marginTop: '20px'}}>
            {metricsTab === 'decision-trace' && (
              <ErrorBoundary title="Decision Trace Error" message="Unable to load decision trace. The service may be unavailable.">
                <DecisionTrace />
              </ErrorBoundary>
            )}
            {metricsTab === 'market-state' && (
              <ErrorBoundary title="Market State Error" message="Unable to load market state.">
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(340px, 1fr))', gap: 16 }}>
                  <MarketBrainPanel />
                  <MarketIntelligencePanel />
                </div>
              </ErrorBoundary>
            )}
            {metricsTab === 'capital' && (
              <ErrorBoundary title="Capital Intelligence Error" message="Unable to load capital data.">
                <CapitalPanel />
              </ErrorBoundary>
            )}
            {metricsTab === 'huggingface' && (
              <ErrorBoundary title="AI Analysis Error" message="Unable to load AI analysis.">
                <HuggingFacePanel axiosConfig={axiosConfig} />
              </ErrorBoundary>
            )}
          </div>
        </div>
      </section>
  );
};

export default MetricsWithTabsSection;
