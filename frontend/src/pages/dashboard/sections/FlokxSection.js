import React from 'react';
import SectionHeader from '@/ui/components/SectionHeader';

const NOT_AVAILABLE = 'Not available';

const FlokxSection = ({ 
  flokxAlerts, 
  flokxStatus, 
  formatDate, 
  getAlertColor, 
  isFlokxActive, 
  loadFlokxAlerts,
  showSection 
}) => {
  const [selectedAlert, setSelectedAlert] = React.useState(null);
  const [filterPriority, setFilterPriority] = React.useState('all');

  const filteredAlerts = React.useMemo(() => {
    if (!Array.isArray(flokxAlerts)) return [];
    if (filterPriority === 'all') return flokxAlerts;
    return flokxAlerts.filter(alert => 
      (alert.priority || alert.type || 'info').toLowerCase() === filterPriority.toLowerCase()
    );
  }, [flokxAlerts, filterPriority]);

  const alertCounts = React.useMemo(() => {
    if (!Array.isArray(flokxAlerts)) return { critical: 0, high: 0, medium: 0, low: 0, info: 0 };
    return flokxAlerts.reduce((acc, alert) => {
      const priority = (alert.priority || alert.type || 'info').toLowerCase();
      acc[priority] = (acc[priority] || 0) + 1;
      return acc;
    }, { critical: 0, high: 0, medium: 0, low: 0, info: 0 });
  }, [flokxAlerts]);

  return (
    <section className="section active">
      <div className="card">
        <SectionHeader
          title="🦊 Flokx Monitoring"
          subtitle="Real-time alerts and market intelligence from Flokx"
        />

        {!isFlokxActive && (
          <div style={{
            padding: '40px',
            textAlign: 'center',
            background: 'var(--panel)',
            borderRadius: '8px',
            border: '1px solid var(--line)',
            marginBottom: '20px'
          }}>
            <div style={{fontSize: '3rem', marginBottom: '16px'}}>🦊</div>
            <h3 style={{marginBottom: '12px', color: 'var(--text)'}}>
              Flokx Not Configured
            </h3>
            <p style={{color: 'var(--muted)', marginBottom: '12px', maxWidth: '600px', margin: '0 auto 12px'}}>
              Connect your Flokx API key to receive real-time trading alerts, market analysis, and risk notifications.
            </p>
            {flokxStatus?.last_error && (
              <p style={{
                color: 'var(--error)',
                marginBottom: '20px',
                fontSize: '0.85rem',
                padding: '8px 12px',
                background: 'rgba(239, 68, 68, 0.1)',
                borderRadius: '6px',
                display: 'inline-block'
              }}>
                Status: {flokxStatus.last_error}
              </p>
            )}
            <div style={{marginTop: '20px'}}>
              <button 
                onClick={() => showSection('api')}
                style={{
                  padding: '12px 24px',
                  background: 'var(--accent2)',
                  color: 'var(--text)',
                  border: 'none',
                  borderRadius: '8px',
                  fontWeight: 600,
                  cursor: 'pointer',
                  fontSize: '1rem'
                }}
              >
                Configure Flokx API
              </button>
            </div>
          </div>
        )}

        {isFlokxActive && (
          <div style={{display: 'flex', flexDirection: 'column', gap: '20px'}}>
            {/* Status Header */}
            <div style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              padding: '16px',
              background: 'var(--glass)',
              borderRadius: '8px',
              border: '1px solid var(--line)'
            }}>
              <div style={{display: 'flex', alignItems: 'center', gap: '12px'}}>
                <div style={{
                  width: '12px',
                  height: '12px',
                  borderRadius: '50%',
                  background: 'var(--success)',
                  boxShadow: '0 0 8px var(--success)'
                }}></div>
                <div>
                  <div style={{fontWeight: 600, fontSize: '1rem'}}>Flokx Active</div>
                  <div style={{fontSize: '0.85rem', color: 'var(--muted)'}}>
                    {flokxStatus?.last_tested_at 
                      ? `Last tested: ${formatDate(flokxStatus.last_tested_at)}`
                      : 'Connected'}
                  </div>
                </div>
              </div>
              <button 
                onClick={loadFlokxAlerts}
                style={{
                  padding: '8px 16px',
                  borderRadius: '6px',
                  background: 'var(--accent2)',
                  color: 'var(--text)',
                  border: 'none',
                  fontWeight: 600,
                  cursor: 'pointer'
                }}
              >
                🔄 Refresh
              </button>
            </div>

            {/* Alert Statistics */}
            <div style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))',
              gap: '12px'
            }}>
              {[
                { label: 'Critical', count: alertCounts.critical, color: '#dc2626' },
                { label: 'High', count: alertCounts.high, color: '#ea580c' },
                { label: 'Medium', count: alertCounts.medium, color: '#ca8a04' },
                { label: 'Low', count: alertCounts.low, color: '#16a34a' },
                { label: 'Info', count: alertCounts.info, color: '#0284c7' }
              ].map(stat => (
                <div key={stat.label} style={{
                  padding: '16px',
                  background: 'var(--glass)',
                  borderRadius: '8px',
                  border: '1px solid var(--line)',
                  textAlign: 'center',
                  cursor: 'pointer',
                  transition: 'all 0.2s',
                  borderLeft: `4px solid ${stat.color}`
                }}
                onClick={() => setFilterPriority(stat.label.toLowerCase())}
                >
                  <div style={{fontSize: '1.5rem', fontWeight: 700, marginBottom: '4px'}}>
                    {stat.count}
                  </div>
                  <div style={{fontSize: '0.85rem', color: 'var(--muted)'}}>
                    {stat.label}
                  </div>
                </div>
              ))}
            </div>

            {/* Filters */}
            <div style={{display: 'flex', gap: '8px', flexWrap: 'wrap', alignItems: 'center'}}>
              <span style={{fontSize: '0.85rem', fontWeight: 600, color: 'var(--muted)'}}>
                Filter:
              </span>
              {['all', 'critical', 'high', 'medium', 'low', 'info'].map(priority => (
                <button
                  key={priority}
                  onClick={() => setFilterPriority(priority)}
                  style={{
                    padding: '6px 12px',
                    borderRadius: '6px',
                    border: '1px solid var(--line)',
                    background: filterPriority === priority ? 'var(--accent2)' : 'var(--panel)',
                    color: 'var(--text)',
                    fontWeight: 600,
                    fontSize: '0.85rem',
                    cursor: 'pointer',
                    textTransform: 'capitalize'
                  }}
                >
                  {priority}
                </button>
              ))}
            </div>

            {/* Alerts List */}
            <div style={{
              background: 'var(--glass)',
              padding: '16px',
              borderRadius: '8px',
              border: '1px solid var(--line)'
            }}>
              {filteredAlerts.length === 0 ? (
                <p style={{color: 'var(--muted)', padding: '20px', textAlign: 'center'}}>
                  {filterPriority === 'all'
                    ? '✓ No alerts at this time - System running smoothly'
                    : `No ${filterPriority} priority alerts`}
                </p>
              ) : (
                <div style={{display: 'flex', flexDirection: 'column', gap: '12px'}}>
                  {filteredAlerts.map((alert, idx) => {
                    const isSelected = selectedAlert?.timestamp === alert.timestamp;
                    return (
                      <div 
                        key={idx}
                        onClick={() => setSelectedAlert(isSelected ? null : alert)}
                        style={{
                          padding: '14px',
                          background: isSelected ? 'var(--accent-bg)' : 'var(--panel)',
                          borderRadius: '8px',
                          borderLeft: '4px solid ' + getAlertColor(alert.priority || alert.type || 'info'),
                          cursor: 'pointer',
                          transition: 'all 0.2s',
                          border: isSelected ? '1px solid var(--accent2)' : '1px solid transparent'
                        }}
                      >
                        <div style={{
                          display: 'flex',
                          justifyContent: 'space-between',
                          alignItems: 'flex-start',
                          gap: '12px'
                        }}>
                          <div style={{flex: 1}}>
                            <div style={{
                              display: 'flex',
                              alignItems: 'center',
                              gap: '8px',
                              marginBottom: '6px'
                            }}>
                              <div style={{fontWeight: 600, fontSize: '1rem'}}>
                                {alert.title || alert.pair || 'Alert'}
                              </div>
                              {(alert.priority || alert.type) && (
                                <div style={{
                                  padding: '3px 8px',
                                  borderRadius: '4px',
                                  fontSize: '0.7rem',
                                  fontWeight: 600,
                                  background: getAlertColor(alert.priority || alert.type || 'info'),
                                  color: 'white',
                                  textTransform: 'uppercase'
                                }}>
                                  {alert.priority || alert.type}
                                </div>
                              )}
                            </div>
                            <div style={{
                              fontSize: '0.9rem',
                              color: 'var(--muted)',
                              marginBottom: '6px',
                              lineHeight: '1.5'
                            }}>
                              {alert.message || alert.detail || 'No details available'}
                            </div>
                            {isSelected && alert.details && (
                              <div style={{
                                marginTop: '12px',
                                padding: '12px',
                                background: 'var(--glass)',
                                borderRadius: '6px',
                                fontSize: '0.85rem',
                                color: 'var(--text)'
                              }}>
                                {alert.details}
                              </div>
                            )}
                            <div style={{
                              fontSize: '0.75rem',
                              color: 'var(--muted)',
                              marginTop: '6px',
                              display: 'flex',
                              alignItems: 'center',
                              gap: '8px'
                            }}>
                              <span>🕐</span>
                              <span>
                                {alert.timestamp 
                                  ? new Date(alert.timestamp).toLocaleString()
                                  : 'No timestamp'}
                              </span>
                            </div>
                          </div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </section>
  );
};

export default FlokxSection;
