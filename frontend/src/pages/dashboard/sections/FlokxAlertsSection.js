import React from 'react';

const NOT_AVAILABLE = 'Not available';

const FlokxAlertsSection = ({ flokxAlerts, flokxStatus, formatDate, getAlertColor, isFlokxActive, loadFlokxAlerts, showSection }) => {
  return (
      <section className="section active">
        <div className="card">
          <h2>Flokx Alerts</h2>
          
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
      </section>
  );
};

export default FlokxAlertsSection;
