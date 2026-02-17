import React from 'react';
import SectionHeader from '@/ui/components/SectionHeader';
import apiClient from '../../../lib/apiClient';

const NOT_AVAILABLE = 'Not available';

const FetchAISection = () => {
  const [agents, setAgents] = React.useState([]);
  const [signals, setSignals] = React.useState([]);
  const [isActive, setIsActive] = React.useState(false);
  const [loading, setLoading] = React.useState(false);
  const [lastUpdate, setLastUpdate] = React.useState(null);
  const [error, setError] = React.useState(null);

  const tradingPairs = ['BTC/USD', 'ETH/USD', 'BTC/ZAR', 'ETH/ZAR'];

  const loadFetchAIData = async () => {
    setLoading(true);
    setError(null);
    try {
      // Check Fetch.ai status
      const statusResponse = await apiClient.get('/api/fetchai/status');
      const statusData = statusResponse.data;
      
      setIsActive(statusData.configured && statusData.active);
      
      if (statusData.configured) {
        // Fetch signals for multiple pairs
        const signalPromises = tradingPairs.map(async (pair) => {
          try {
            const response = await apiClient.get(`/api/fetchai/signals/${pair}`);
            return response.data.signals;
          } catch (err) {
            console.error(`Failed to fetch signals for ${pair}:`, err);
            return null;
          }
        });
        
        const signalResults = await Promise.all(signalPromises);
        const validSignals = signalResults.filter(s => s !== null);
        setSignals(validSignals);
        setLastUpdate(new Date());
      } else {
        setSignals([]);
      }
      
      // Agents are not implemented yet - placeholder
      setAgents([]);
    } catch (error) {
      console.error('Failed to load Fetch.ai data:', error);
      setError(error.response?.data?.message || error.message || 'Failed to load Fetch.ai data');
      setIsActive(false);
    } finally {
      setLoading(false);
    }
  };

  React.useEffect(() => {
    loadFetchAIData();
    // Auto-refresh every 30 seconds when active
    const interval = setInterval(() => {
      if (isActive) {
        loadFetchAIData();
      }
    }, 30000);
    return () => clearInterval(interval);
  }, [isActive]);

  const getSignalColor = (signal) => {
    if (!signal) return 'var(--muted)';
    const sig = signal.toString().toUpperCase();
    if (sig === 'BUY' || sig === 'BULLISH') return 'var(--success)';
    if (sig === 'SELL' || sig === 'BEARISH') return 'var(--error)';
    return 'var(--warning)';
  };

  return (
    <section className="section active">
      <div className="card">
        <SectionHeader
          title="🤖 Fetch.ai Integration"
          subtitle="AI-powered market signals and autonomous trading agents"
        />

        {!isActive && (
          <div style={{
            padding: '40px',
            textAlign: 'center',
            background: 'var(--panel)',
            borderRadius: '8px',
            border: '1px solid var(--line)',
            marginBottom: '20px'
          }}>
            <div style={{fontSize: '3rem', marginBottom: '16px'}}>🤖</div>
            <h3 style={{marginBottom: '12px', color: 'var(--text)'}}>
              Fetch.ai Not Configured
            </h3>
            <p style={{color: 'var(--muted)', marginBottom: '20px', maxWidth: '600px', margin: '0 auto 20px'}}>
              Connect your Fetch.ai API key to access AI-powered market signals, autonomous agents, and predictive analytics for your trading strategy.
            </p>
            {error && (
              <div style={{
                padding: '12px',
                marginBottom: '20px',
                background: 'var(--error-bg)',
                color: 'var(--error)',
                borderRadius: '6px',
                fontSize: '0.9rem'
              }}>
                {error}
              </div>
            )}
            <button 
              onClick={() => window.location.hash = '#/dashboard?section=api'}
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
              Configure Fetch.ai API
            </button>
          </div>
        )}

        {isActive && (
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
                  <div style={{fontWeight: 600, fontSize: '1rem'}}>Fetch.ai Active</div>
                  <div style={{fontSize: '0.85rem', color: 'var(--muted)'}}>
                    {lastUpdate ? `Last updated: ${new Date(lastUpdate).toLocaleString()}` : 'Ready'}
                  </div>
                </div>
              </div>
              <button 
                onClick={loadFetchAIData}
                disabled={loading}
                style={{
                  padding: '8px 16px',
                  borderRadius: '6px',
                  background: 'var(--accent2)',
                  color: 'var(--text)',
                  border: 'none',
                  fontWeight: 600,
                  cursor: loading ? 'not-allowed' : 'pointer',
                  opacity: loading ? 0.6 : 1
                }}
              >
                {loading ? 'Refreshing...' : '🔄 Refresh'}
              </button>
            </div>

            {/* Market Signals */}
            <div>
              <h3 style={{marginBottom: '12px', fontSize: '1.1rem'}}>📊 Market Signals</h3>
              <div style={{
                background: 'var(--glass)',
                padding: '16px',
                borderRadius: '8px',
                border: '1px solid var(--line)'
              }}>
                {signals.length === 0 ? (
                  <p style={{color: 'var(--muted)', textAlign: 'center', padding: '20px'}}>
                    No signals available. Refresh to fetch latest data.
                  </p>
                ) : (
                  <div style={{display: 'grid', gap: '12px'}}>
                    {signals.map((signal, idx) => (
                      <div key={idx} style={{
                        padding: '12px',
                        background: 'var(--panel)',
                        borderRadius: '6px',
                        borderLeft: `4px solid ${getSignalColor(signal.signal)}`,
                        display: 'grid',
                        gridTemplateColumns: '1fr auto',
                        gap: '12px',
                        alignItems: 'center'
                      }}>
                        <div>
                          <div style={{fontWeight: 600, marginBottom: '4px'}}>
                            {signal.pair || 'BTC/USD'}
                          </div>
                          <div style={{fontSize: '0.85rem', color: 'var(--muted)'}}>
                            Signal: <strong style={{color: getSignalColor(signal.signal)}}>
                              {signal.signal || 'HOLD'}
                            </strong> • Confidence: {signal.confidence || 0}%
                          </div>
                        </div>
                        <div style={{
                          padding: '6px 12px',
                          borderRadius: '6px',
                          background: getSignalColor(signal.signal),
                          color: 'white',
                          fontWeight: 600,
                          fontSize: '0.85rem'
                        }}>
                          {signal.strength || 'MODERATE'}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>

            {/* Autonomous Agents */}
            <div>
              <h3 style={{marginBottom: '12px', fontSize: '1.1rem'}}>🤖 Autonomous Agents</h3>
              <div style={{
                background: 'var(--glass)',
                padding: '16px',
                borderRadius: '8px',
                border: '1px solid var(--line)'
              }}>
                {agents.length === 0 ? (
                  <div style={{textAlign: 'center', padding: '20px'}}>
                    <p style={{color: 'var(--muted)', marginBottom: '16px'}}>
                      No active Fetch.ai agents configured.
                    </p>
                    <button style={{
                      padding: '10px 20px',
                      background: 'var(--accent)',
                      color: 'white',
                      border: 'none',
                      borderRadius: '6px',
                      fontWeight: 600,
                      cursor: 'pointer'
                    }}>
                      Create Agent
                    </button>
                  </div>
                ) : (
                  <div style={{display: 'grid', gap: '12px'}}>
                    {agents.map((agent, idx) => (
                      <div key={idx} style={{
                        padding: '12px',
                        background: 'var(--panel)',
                        borderRadius: '6px',
                        display: 'flex',
                        justifyContent: 'space-between',
                        alignItems: 'center'
                      }}>
                        <div>
                          <div style={{fontWeight: 600}}>{agent.name || 'Agent'}</div>
                          <div style={{fontSize: '0.85rem', color: 'var(--muted)'}}>
                            Status: {agent.status || 'Unknown'}
                          </div>
                        </div>
                        <button style={{
                          padding: '6px 12px',
                          borderRadius: '6px',
                          background: 'var(--error)',
                          color: 'white',
                          border: 'none',
                          fontWeight: 600,
                          fontSize: '0.85rem',
                          cursor: 'pointer'
                        }}>
                          Stop
                        </button>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          </div>
        )}
      </div>
    </section>
  );
};

export default FetchAISection;
