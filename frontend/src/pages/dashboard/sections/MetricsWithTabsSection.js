import React from 'react';
import ErrorBoundary from '../../../components/ErrorBoundary';
import DecisionTrace from '../../../components/DecisionTrace';
import WhaleFlowHeatmap from '../../../components/WhaleFlowHeatmap';
import PrometheusMetrics from '../../../components/PrometheusMetrics';

const NOT_AVAILABLE = 'Not available';

const MetricsWithTabsSection = ({ flokxAlerts, flokxStatus, formatDate, getAlertColor, isFlokxActive, loadFlokxAlerts, metrics, metricsTab, setMetricsTab, showSection, renderFlokxAlerts }) => {
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
              onClick={() => setMetricsTab('flokx')}
              style={{
                padding: '10px 20px',
                background: metricsTab === 'flokx' ? 'linear-gradient(135deg, var(--accent2) 0%, var(--accent2) 100%)' : 'var(--glass)',
                border: '2px solid ' + (metricsTab === 'flokx' ? 'var(--accent2)' : 'var(--line)'),
                borderRadius: '8px',
                color: metricsTab === 'flokx' ? '#fff' : 'var(--text)',
                cursor: 'pointer',
                fontSize: '0.95rem',
                fontWeight: metricsTab === 'flokx' ? '700' : '600',
                transition: 'all 0.3s',
                boxShadow: metricsTab === 'flokx' ? '0 4px 12px rgba(74, 144, 226, 0.4)' : 'none'
              }}
            >
              🔔 Flokx Alerts
            </button>
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
            {metricsTab === 'flokx' && (
              <ErrorBoundary title="Flokx Alerts Error" message="Unable to load Flokx alerts. Please check your API configuration.">
                <div>
                  {!isFlokxActive && (
                    <div style={{padding: '40px', textAlign: 'center', background: 'var(--panel)', borderRadius: '6px', border: '1px solid var(--line)'}}>
                      <p style={{color: 'var(--muted)', marginBottom: '12px'}}>
                        ⚠️ Flokx alerts are not active. Configure your Flokx API key in the API Setup section to enable real-time alerts.
                      </p>
                      {flokxStatus.last_error && (
                        <p style={{color: 'var(--error)', marginBottom: '12px', fontSize: '0.85rem'}}>
                          Status check: {flokxStatus.last_error}
                        </p>
                      )}
                      <button 
                        onClick={() => showSection('api')}
                        style={{
                          padding: '8px 16px',
                          background: 'var(--accent2)',
                          color: 'var(--text)',
                          border: 'none',
                          borderRadius: '6px',
                          fontWeight: 600,
                          cursor: 'pointer'
                        }}
                      >
                        Configure Flokx API
                      </button>
                    </div>
                  )}
                  
                  {isFlokxActive && (
                    <div style={{display: 'flex', flexDirection: 'column', gap: '12px'}}>
                      <div style={{display: 'flex', justifyContent: 'space-between', alignItems: 'center'}}>
                        <div style={{display: 'flex', alignItems: 'center', gap: '8px'}}>
                          <div style={{width: '8px', height: '8px', borderRadius: '50%', background: 'var(--success)'}}></div>
                          <span style={{fontSize: '0.85rem', color: 'var(--muted)'}}>
                            Flokx Active {flokxStatus.last_tested_at ? `• Last tested ${formatDate(flokxStatus.last_tested_at)}` : ''}
                          </span>
                        </div>
                        <button 
                          onClick={loadFlokxAlerts} 
                          style={{
                            padding: '6px 12px',
                            borderRadius: '6px',
                            background: 'var(--accent2)',
                            color: 'var(--text)',
                            border: 'none',
                            fontWeight: 600,
                            fontSize: '0.85rem',
                            cursor: 'pointer'
                          }}
                        >
                          Refresh Alerts
                        </button>
                      </div>
                      
                      <div style={{background: 'var(--glass)', padding: '12px', borderRadius: '6px', border: '1px solid var(--line)'}}>
                        {!Array.isArray(flokxAlerts) || flokxAlerts.length === 0 ? (
                          <p style={{color: 'var(--muted)', padding: '20px', textAlign: 'center'}}>
                            ✓ No alerts at this time - System running smoothly
                          </p>
                        ) : (
                          <div style={{display: 'flex', flexDirection: 'column', gap: '8px'}}>
                            {Array.isArray(flokxAlerts) && flokxAlerts.map((alert, idx) => (
                              <div 
                                key={idx}
                                style={{
                                  padding: '12px',
                                  background: 'var(--panel)',
                                  borderRadius: '6px',
                                  borderLeft: '4px solid ' + getAlertColor(alert.priority || alert.type || 'info'),
                                  display: 'flex',
                                  justifyContent: 'space-between',
                                  alignItems: 'center'
                                }}
                              >
                                <div>
                                  <div style={{fontWeight: 600, marginBottom: '4px'}}>
                                    {alert.title || alert.pair || 'Alert'}
                                  </div>
                                  <div style={{fontSize: '0.85rem', color: 'var(--muted)'}}>
                                    {alert.message || 'No details available'}
                                  </div>
                                  <div style={{fontSize: '0.75rem', color: 'var(--muted)', marginTop: '4px'}}>
                                    {alert.timestamp ? new Date(alert.timestamp).toLocaleString() : 'No timestamp'}
                                  </div>
                                </div>
                                {(alert.priority || alert.type) && (
                                  <div style={{
                                    padding: '4px 8px',
                                    borderRadius: '4px',
                                    fontSize: '0.75rem',
                                    fontWeight: 600,
                                    background: getAlertColor(alert.priority || alert.type || 'info'),
                                    color: 'white'
                                  }}>
                                    {(alert.priority || alert.type || 'INFO').toUpperCase()}
                                  </div>
                                )}
                              </div>
                            ))}
                          </div>
                        )}
                      </div>
                    </div>
                  )}
                </div>
              </ErrorBoundary>
            )}
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
