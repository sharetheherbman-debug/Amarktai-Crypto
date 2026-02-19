import React from 'react';
import SectionHeader from '@/ui/components/SectionHeader';
import { apiClient } from '@/lib/apiClient';
import { toast } from 'sonner';
import AutopilotInsightsPanel from './AutopilotInsightsPanel';

const NOT_AVAILABLE = 'Not available';

export default function SystemModeSection({
  bots,
  handleEmergencyStop,
  handlePaperReset,
  handleRiskProfileChange,
  paperResetLoading,
  paperResetError,
  riskProfile,
  setPaperResetError,
  setShowPaperResetModal,
  showPaperResetModal,
  systemModes,
  toggleSystemMode,
}) {
  const hasLiveBots = bots.some(b => b.trading_mode === 'live' && b.status === 'active');
  const showPaperReset = systemModes.paperTrading && !systemModes.liveTrading;
  const isPaperResetMode = systemModes.paperTrading && !systemModes.liveTrading;
  const [confirmPhrase, setConfirmPhrase] = React.useState('');
  
  // Runtime reset state
  const [showRuntimeResetModal, setShowRuntimeResetModal] = React.useState(false);
  const [runtimeResetPhrase, setRuntimeResetPhrase] = React.useState('');
  const [runtimeResetLoading, setRuntimeResetLoading] = React.useState(false);
  const [runtimeResetResult, setRuntimeResetResult] = React.useState(null);
  
  // Self-healing state
  const [selfHealingStatus, setSelfHealingStatus] = React.useState(null);
  const [loadingSelfHealing, setLoadingSelfHealing] = React.useState(false);
  const [confirmSelfHealing, setConfirmSelfHealing] = React.useState('');
  const [showSelfHealingModal, setShowSelfHealingModal] = React.useState(false);
  const [selfHealingAction, setSelfHealingAction] = React.useState(null); // 'pause' or 'resume'

  // Autopilot status state
  const [autopilotGrowth, setAutopilotGrowth] = React.useState(null);
  const [autopilotReinvest, setAutopilotReinvest] = React.useState(null);
  const [showAutopilotDetails, setShowAutopilotDetails] = React.useState(false);

  // Fetch self-healing status
  const fetchSelfHealingStatus = async () => {
    try {
      const response = await apiClient.get('/autonomy/status');
      const selfHealData = response.data?.subsystems?.self_heal;
      setSelfHealingStatus(selfHealData);
    } catch (err) {
      console.error('Failed to fetch self-healing status:', err);
    }
  };

  // Fetch autopilot status
  const fetchAutopilotStatus = async () => {
    try {
      const [growthRes, reinvestRes] = await Promise.all([
        apiClient.get('/autopilot/growth/status'),
        apiClient.get('/autopilot/reinvest/status')
      ]);
      setAutopilotGrowth(growthRes.data);
      setAutopilotReinvest(reinvestRes.data);
    } catch (err) {
      console.error('Failed to fetch autopilot status:', err);
    }
  };

  React.useEffect(() => {
    fetchSelfHealingStatus();
    fetchAutopilotStatus();
    // Poll every 30 seconds
    const interval = setInterval(() => {
      fetchSelfHealingStatus();
      fetchAutopilotStatus();
    }, 30000);
    return () => clearInterval(interval);
  }, []);

  const handleSelfHealingControl = async (action) => {
    setLoadingSelfHealing(true);
    try {
      const endpoint = action === 'pause' ? '/autonomy/pause' : '/autonomy/resume';
      const confirmPhrase = action === 'pause' ? 'CONFIRM AUTONOMY PAUSE' : 'CONFIRM AUTONOMY RESUME';
      
      await apiClient.post(endpoint, {
        subsystem: 'self_heal',
        confirmation_phrase: confirmPhrase
      });
      
      toast.success(`Self-healing ${action === 'pause' ? 'paused' : 'resumed'} successfully`);
      setShowSelfHealingModal(false);
      setConfirmSelfHealing('');
      fetchSelfHealingStatus();
    } catch (err) {
      console.error(`Failed to ${action} self-healing:`, err);
      toast.error(err.response?.data?.detail || `Failed to ${action} self-healing`);
    } finally {
      setLoadingSelfHealing(false);
    }
  };

  const openSelfHealingModal = (action) => {
    setSelfHealingAction(action);
    setConfirmSelfHealing('');
    setShowSelfHealingModal(true);
  };

  const handleRuntimeReset = async () => {
    if (runtimeResetPhrase !== 'CONFIRM RUNTIME RESET') {
      toast.error('Please enter the exact confirmation phrase');
      return;
    }
    
    setRuntimeResetLoading(true);
    setRuntimeResetResult(null);
    
    try {
      const response = await apiClient.post('/admin/runtime/reset', {
        confirmation_phrase: runtimeResetPhrase,
        mode: 'paper'
      });
      
      setRuntimeResetResult(response.data);
      toast.success('Runtime reset completed successfully');
      setRuntimeResetPhrase('');
      
      // Close modal after showing result for a moment
      setTimeout(() => {
        setShowRuntimeResetModal(false);
        setRuntimeResetResult(null);
      }, 3000);
      
    } catch (err) {
      console.error('Runtime reset failed:', err);
      toast.error(err.response?.data?.detail || 'Failed to reset runtime');
    } finally {
      setRuntimeResetLoading(false);
    }
  };

  return (
    <section className="section active">
      <div className="card">
        <SectionHeader
          title="🎮 System Mode"
          subtitle="Control paper/live trading, autopilot, and reset runtime safely."
        />
        <div style={{display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '12px', marginBottom: '16px'}}>
          <div className="system-card" onClick={() => toggleSystemMode('paperTrading')} style={{padding: '16px', background: 'var(--glass)', border: '2px solid ' + (systemModes.paperTrading ? 'var(--success)' : 'var(--line)'), borderRadius: '8px', cursor: 'pointer', textAlign: 'center'}}>
            <h3>🧪 Paper Trading</h3>
            <p style={{fontSize: '0.85rem', color: 'var(--muted)', margin: '8px 0'}}>Practice with simulated funds</p>
            <div style={{fontWeight: 600, fontSize: '1.2rem', color: systemModes.paperTrading ? 'var(--success)' : 'var(--error)'}}>
              {systemModes.paperTrading ? '✓ ON' : '✗ OFF'}
            </div>
          </div>
          <div className="system-card" onClick={() => toggleSystemMode('liveTrading')} style={{padding: '16px', background: 'var(--glass)', border: '2px solid ' + (systemModes.liveTrading ? 'var(--accent2)' : 'var(--line)'), borderRadius: '8px', cursor: 'pointer', textAlign: 'center'}}>
            <h3>💰 Live Trading</h3>
            <p style={{fontSize: '0.85rem', color: 'var(--muted)', margin: '8px 0'}}>⚠️ Execute REAL trades</p>
            <div style={{fontWeight: 600, fontSize: '1.2rem', color: systemModes.liveTrading ? 'var(--accent2)' : 'var(--error)'}}>
              {systemModes.liveTrading ? '⚡ ON' : '✗ OFF'}
            </div>
          </div>
          <div className="system-card" onClick={() => toggleSystemMode('autopilot')} style={{padding: '16px', background: 'var(--glass)', border: '2px solid ' + (systemModes.autopilot ? 'var(--success)' : 'var(--line)'), borderRadius: '8px', cursor: 'pointer', textAlign: 'center'}}>
            <h3>🤖 Autopilot</h3>
            <p style={{fontSize: '0.85rem', color: 'var(--muted)', margin: '8px 0'}}>Autonomous 24/7 trading</p>
            <div style={{fontWeight: 600, fontSize: '1.2rem', color: systemModes.autopilot ? 'var(--success)' : 'var(--error)'}}>
              {systemModes.autopilot ? '✓ ON' : '✗ OFF'}
            </div>
          </div>
        </div>
        <div style={{marginTop: '12px', padding: '16px', background: 'var(--glass)', border: '1px solid var(--line)', borderRadius: '8px'}}>
          <div style={{fontWeight: 700, marginBottom: '8px', color: 'var(--text)'}}>🛡️ Risk Profile</div>
          <select
            value={riskProfile}
            onChange={(e) => handleRiskProfileChange(e.target.value)}
            style={{
              width: '100%',
              padding: '10px',
              background: 'var(--panel)',
              border: '1px solid var(--line)',
              borderRadius: '6px',
              color: 'var(--text)',
              cursor: 'pointer',
              maxWidth: '320px'
            }}
          >
            <option value="safe">Safe (15% daily loss/drawdown)</option>
            <option value="balanced">Balanced (20% daily loss/drawdown)</option>
            <option value="risky">Risky (25% daily loss/drawdown)</option>
          </select>
          <div style={{fontSize: '0.8rem', color: 'var(--muted)', marginTop: '8px'}}>
            Bodyguard uses this tier to pause bots when drawdown exceeds your selected threshold.
          </div>
        </div>

        {/* Self-Healing Control */}
        <div style={{marginTop: '20px', padding: '16px', background: 'var(--glass)', border: '1px solid var(--line)', borderRadius: '8px'}}>
          <div style={{fontWeight: 700, marginBottom: '12px', color: 'var(--text)', display: 'flex', alignItems: 'center', gap: '8px'}}>
            🏥 Self-Healing System
          </div>
          
          {selfHealingStatus ? (
            <div>
              <div style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))',
                gap: '12px',
                marginBottom: '12px'
              }}>
                <div>
                  <div style={{fontSize: '0.8rem', color: 'var(--muted)', marginBottom: '4px'}}>Status</div>
                  <div style={{
                    fontWeight: 600,
                    color: selfHealingStatus.status === 'running' ? 'var(--success)' :
                          selfHealingStatus.status === 'paused' ? 'var(--warning)' :
                          'var(--error)'
                  }}>
                    {selfHealingStatus.status === 'running' ? '✓ Running' :
                     selfHealingStatus.status === 'paused' ? '⏸ Paused' :
                     '✗ Stopped'}
                  </div>
                </div>
                
                {selfHealingStatus.last_ok_at && (
                  <div>
                    <div style={{fontSize: '0.8rem', color: 'var(--muted)', marginBottom: '4px'}}>Last Check</div>
                    <div style={{fontSize: '0.85rem', color: 'var(--text)'}}>
                      {new Date(selfHealingStatus.last_ok_at).toLocaleTimeString()}
                    </div>
                  </div>
                )}
                
                {selfHealingStatus.last_error_message && (
                  <div>
                    <div style={{fontSize: '0.8rem', color: 'var(--muted)', marginBottom: '4px'}}>Last Error</div>
                    <div style={{fontSize: '0.85rem', color: 'var(--error)'}}>
                      {selfHealingStatus.last_error_message.substring(0, 50)}...
                    </div>
                  </div>
                )}
              </div>
              
              <div style={{display: 'flex', gap: '8px', marginTop: '12px'}}>
                {selfHealingStatus.status === 'running' ? (
                  <button
                    onClick={() => openSelfHealingModal('pause')}
                    style={{
                      padding: '8px 16px',
                      background: 'var(--warning)',
                      color: 'white',
                      border: 'none',
                      borderRadius: '6px',
                      fontWeight: 600,
                      cursor: 'pointer',
                      fontSize: '0.9rem'
                    }}
                  >
                    ⏸ Pause Self-Healing
                  </button>
                ) : (
                  <button
                    onClick={() => openSelfHealingModal('resume')}
                    style={{
                      padding: '8px 16px',
                      background: 'var(--success)',
                      color: 'white',
                      border: 'none',
                      borderRadius: '6px',
                      fontWeight: 600,
                      cursor: 'pointer',
                      fontSize: '0.9rem'
                    }}
                  >
                    ▶ Resume Self-Healing
                  </button>
                )}
                
                <button
                  onClick={fetchSelfHealingStatus}
                  style={{
                    padding: '8px 16px',
                    background: 'var(--panel)',
                    color: 'var(--text)',
                    border: '1px solid var(--line)',
                    borderRadius: '6px',
                    fontWeight: 600,
                    cursor: 'pointer',
                    fontSize: '0.9rem'
                  }}
                >
                  🔄 Refresh
                </button>
              </div>
              
              <div style={{fontSize: '0.75rem', color: 'var(--muted)', marginTop: '12px'}}>
                Self-healing monitors database connectivity, memory usage, and disk space, automatically recovering from common issues.
              </div>
            </div>
          ) : (
            <div style={{color: 'var(--muted)', fontSize: '0.9rem'}}>
              Loading self-healing status...
            </div>
          )}
        </div>

        {/* Autopilot Insights Panel - Replaces inline status display */}
        <div style={{marginTop: '20px'}}>
          <AutopilotInsightsPanel onRefresh={() => {
            fetchSelfHealingStatus();
            fetchAutopilotStatus();
          }} />
        </div>

        {/* Runtime Reset (Admin) */}
        <div style={{marginTop: '20px', padding: '16px', background: 'var(--glass)', border: '1px solid rgba(239, 68, 68, 0.3)', borderRadius: '8px'}}>
          <div style={{fontWeight: 700, marginBottom: '12px', color: 'var(--text)', display: 'flex', alignItems: 'center', gap: '8px'}}>
            🔄 Runtime Reset (Admin)
          </div>
          <div style={{fontSize: '0.9rem', color: 'var(--muted)', marginBottom: '12px'}}>
            Safely reset paper trading runtime (bots, trades, queues) while preserving users and API keys.
          </div>
          <button
            onClick={() => setShowRuntimeResetModal(true)}
            style={{
              padding: '10px 20px',
              borderRadius: '6px',
              background: 'rgba(239, 68, 68, 0.2)',
              color: '#ef4444',
              border: '1px solid #ef4444',
              fontSize: '0.9rem',
              fontWeight: 600,
              cursor: 'pointer',
              transition: 'all 0.2s ease'
            }}
          >
            Reset Runtime
          </button>
        </div>

        {showPaperReset && (
          <div className="system-reset-card">
            <div className="system-reset-header">
              <div>
                <h3>♻️ Start Fresh / Reset Runtime</h3>
                <p>
                  Clears bots, trades, and analytics snapshots, and resets the paper wallet. Live trading must be off to proceed.
                </p>
              </div>
              <span className="system-reset-badge">{isPaperResetMode ? 'Paper-only' : 'Unavailable in Live'}</span>
            </div>
            <button
              onClick={() => {
                setPaperResetError('');
                setConfirmPhrase('');
                setShowPaperResetModal(true);
              }}
              disabled={!isPaperResetMode || paperResetLoading}
              className="system-reset-button"
            >
              {paperResetLoading ? 'Resetting...' : 'Reset Runtime'}
            </button>
            {!isPaperResetMode && (
              <div className="system-reset-hint">Disable live trading to enable reset.</div>
            )}
          </div>
        )}
      </div>
      {showPaperResetModal && (
        <div className="modal-overlay" onClick={() => setShowPaperResetModal(false)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <h3 style={{marginTop: 0}}>⚠️ Confirm Reset Runtime</h3>
            <p style={{color: 'var(--muted)', fontSize: '0.9rem', marginBottom: '16px'}}>
              This will permanently delete all paper trading bots, trades, and analytics data. This action cannot be undone.
            </p>
            <div style={{
              padding: '12px',
              background: 'rgba(239, 68, 68, 0.1)',
              border: '1px solid rgba(239, 68, 68, 0.3)',
              borderRadius: '6px',
              marginBottom: '16px',
              fontSize: '0.85rem',
              color: 'var(--error)'
            }}>
              <strong>⚠️ Warning:</strong> All paper bots, trade history, and performance data will be permanently deleted.
            </div>
            <div className="system-reset-input" style={{marginTop: '16px'}}>
              <label htmlFor="confirm-phrase-modal" style={{display: 'block', marginBottom: '8px', fontWeight: 600}}>
                Type <strong style={{color: 'var(--accent)'}}>START FRESH</strong> to confirm:
              </label>
              <input
                id="confirm-phrase-modal"
                type="text"
                value={confirmPhrase}
                onChange={(e) => setConfirmPhrase(e.target.value)}
                placeholder="START FRESH"
                autoComplete="off"
                style={{
                  width: '100%',
                  padding: '10px',
                  background: 'var(--panel)',
                  border: '1px solid var(--line)',
                  borderRadius: '6px',
                  color: 'var(--text)',
                  fontSize: '1rem'
                }}
              />
            </div>
            {paperResetError && (
              <div className="system-reset-error" style={{marginTop: '12px'}}>
                {paperResetError}
              </div>
            )}
            <div style={{display: 'flex', gap: '12px', marginTop: '20px', flexWrap: 'wrap'}}>
              <button
                className="system-reset-button"
                onClick={() => handlePaperReset(confirmPhrase)}
                disabled={confirmPhrase !== 'START FRESH' || paperResetLoading}
                style={{
                  opacity: confirmPhrase !== 'START FRESH' ? 0.5 : 1,
                  cursor: confirmPhrase !== 'START FRESH' ? 'not-allowed' : 'pointer'
                }}
              >
                {paperResetLoading ? 'Resetting...' : 'Confirm Reset'}
              </button>
              <button
                onClick={() => {
                  setShowPaperResetModal(false);
                  setConfirmPhrase('');
                  setPaperResetError('');
                }}
                style={{
                  padding: '10px 16px',
                  borderRadius: '999px',
                  border: '1px solid var(--line)',
                  background: 'transparent',
                  color: 'var(--text)',
                  fontWeight: 600,
                  cursor: 'pointer'
                }}
              >
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Self-Healing Control Modal */}
      {showSelfHealingModal && (
        <div className="modal-overlay" onClick={() => setShowSelfHealingModal(false)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <h3 style={{marginTop: 0}}>
              ⚠️ Confirm Self-Healing {selfHealingAction === 'pause' ? 'Pause' : 'Resume'}
            </h3>
            <p style={{color: 'var(--muted)', fontSize: '0.9rem', marginBottom: '16px'}}>
              {selfHealingAction === 'pause' ? 
                'Pausing self-healing will disable automatic recovery from system issues. Only pause if you need to perform maintenance.' :
                'Resuming self-healing will re-enable automatic recovery from database, memory, and disk issues.'}
            </p>
            <div style={{marginTop: '16px'}}>
              <label htmlFor="confirm-phrase-selfhealing" style={{display: 'block', marginBottom: '8px', fontWeight: 600}}>
                Type <strong style={{color: 'var(--accent)'}}>
                  {selfHealingAction === 'pause' ? 'CONFIRM AUTONOMY PAUSE' : 'CONFIRM AUTONOMY RESUME'}
                </strong> to confirm:
              </label>
              <input
                id="confirm-phrase-selfhealing"
                type="text"
                value={confirmSelfHealing}
                onChange={(e) => setConfirmSelfHealing(e.target.value)}
                placeholder={selfHealingAction === 'pause' ? 'CONFIRM AUTONOMY PAUSE' : 'CONFIRM AUTONOMY RESUME'}
                autoComplete="off"
                style={{
                  width: '100%',
                  padding: '10px',
                  background: 'var(--panel)',
                  border: '1px solid var(--line)',
                  borderRadius: '6px',
                  color: 'var(--text)',
                  fontSize: '1rem'
                }}
              />
            </div>
            <div style={{display: 'flex', gap: '12px', marginTop: '20px', flexWrap: 'wrap'}}>
              <button
                onClick={() => handleSelfHealingControl(selfHealingAction)}
                disabled={
                  loadingSelfHealing ||
                  (selfHealingAction === 'pause' && confirmSelfHealing !== 'CONFIRM AUTONOMY PAUSE') ||
                  (selfHealingAction === 'resume' && confirmSelfHealing !== 'CONFIRM AUTONOMY RESUME')
                }
                style={{
                  padding: '10px 16px',
                  borderRadius: '999px',
                  border: 'none',
                  background: selfHealingAction === 'pause' ? 'var(--warning)' : 'var(--success)',
                  color: 'white',
                  fontWeight: 600,
                  cursor: (loadingSelfHealing ||
                    (selfHealingAction === 'pause' && confirmSelfHealing !== 'CONFIRM AUTONOMY PAUSE') ||
                    (selfHealingAction === 'resume' && confirmSelfHealing !== 'CONFIRM AUTONOMY RESUME'))
                    ? 'not-allowed' : 'pointer',
                  opacity: (loadingSelfHealing ||
                    (selfHealingAction === 'pause' && confirmSelfHealing !== 'CONFIRM AUTONOMY PAUSE') ||
                    (selfHealingAction === 'resume' && confirmSelfHealing !== 'CONFIRM AUTONOMY RESUME'))
                    ? 0.5 : 1
                }}
              >
                {loadingSelfHealing ? 'Processing...' : `Confirm ${selfHealingAction === 'pause' ? 'Pause' : 'Resume'}`}
              </button>
              <button
                onClick={() => {
                  setShowSelfHealingModal(false);
                  setConfirmSelfHealing('');
                }}
                style={{
                  padding: '10px 16px',
                  borderRadius: '999px',
                  border: '1px solid var(--line)',
                  background: 'transparent',
                  color: 'var(--text)',
                  fontWeight: 600,
                  cursor: 'pointer'
                }}
              >
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}
      
      {/* Runtime Reset Modal */}
      {showRuntimeResetModal && (
        <div className="modal-overlay" onClick={() => setShowRuntimeResetModal(false)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()} style={{maxWidth: '500px'}}>
            <h3 style={{marginTop: 0, display: 'flex', alignItems: 'center', gap: '8px'}}>
              ⚠️ Runtime Reset
            </h3>
            
            {!runtimeResetResult ? (
              <>
                <p style={{color: 'var(--muted)', fontSize: '0.9rem', marginBottom: '16px'}}>
                  This will safely reset the paper trading runtime by clearing:
                </p>
                <ul style={{color: 'var(--muted)', fontSize: '0.9rem', marginBottom: '16px', paddingLeft: '20px'}}>
                  <li>All bots (configurations)</li>
                  <li>Trade history and queues</li>
                  <li>Runtime state and locks</li>
                  <li>Paper balances</li>
                </ul>
                <p style={{color: 'var(--success)', fontSize: '0.9rem', marginBottom: '16px', fontWeight: 600}}>
                  ✓ User accounts and API keys will be preserved
                </p>
                <p style={{color: 'var(--error)', fontSize: '0.9rem', marginBottom: '16px', fontWeight: 600}}>
                  ⚠️ This action cannot be undone
                </p>
                
                <div style={{marginBottom: '16px'}}>
                  <label style={{display: 'block', marginBottom: '8px', fontSize: '0.9rem', fontWeight: 600, color: 'var(--text)'}}>
                    Type "CONFIRM RUNTIME RESET" to proceed:
                  </label>
                  <input
                    type="text"
                    value={runtimeResetPhrase}
                    onChange={(e) => setRuntimeResetPhrase(e.target.value)}
                    placeholder="CONFIRM RUNTIME RESET"
                    style={{
                      width: '100%',
                      padding: '10px',
                      borderRadius: '6px',
                      border: '1px solid var(--line)',
                      background: 'var(--panel)',
                      color: 'var(--text)',
                      fontSize: '0.9rem'
                    }}
                    autoFocus
                  />
                </div>
                
                <div style={{display: 'flex', gap: '12px', justifyContent: 'flex-end'}}>
                  <button
                    onClick={() => {
                      setShowRuntimeResetModal(false);
                      setRuntimeResetPhrase('');
                      setRuntimeResetResult(null);
                    }}
                    style={{
                      padding: '10px 20px',
                      borderRadius: '6px',
                      border: '1px solid var(--line)',
                      background: 'transparent',
                      color: 'var(--text)',
                      fontSize: '0.9rem',
                      fontWeight: 600,
                      cursor: 'pointer'
                    }}
                  >
                    Cancel
                  </button>
                  <button
                    onClick={handleRuntimeReset}
                    disabled={runtimeResetLoading || runtimeResetPhrase !== 'CONFIRM RUNTIME RESET'}
                    style={{
                      padding: '10px 20px',
                      borderRadius: '6px',
                      border: 'none',
                      background: runtimeResetPhrase === 'CONFIRM RUNTIME RESET' ? '#ef4444' : 'rgba(239, 68, 68, 0.3)',
                      color: 'white',
                      fontSize: '0.9rem',
                      fontWeight: 600,
                      cursor: (runtimeResetLoading || runtimeResetPhrase !== 'CONFIRM RUNTIME RESET') ? 'not-allowed' : 'pointer',
                      opacity: (runtimeResetLoading || runtimeResetPhrase !== 'CONFIRM RUNTIME RESET') ? 0.5 : 1
                    }}
                  >
                    {runtimeResetLoading ? 'Resetting...' : 'Reset Runtime'}
                  </button>
                </div>
              </>
            ) : (
              <>
                <div style={{
                  padding: '16px',
                  borderRadius: '8px',
                  background: 'rgba(34, 197, 94, 0.1)',
                  border: '1px solid rgba(34, 197, 94, 0.3)',
                  marginBottom: '16px'
                }}>
                  <div style={{color: 'var(--success)', fontWeight: 600, marginBottom: '8px'}}>
                    ✓ Reset Completed Successfully
                  </div>
                  {runtimeResetResult.cleared_collections && (
                    <div style={{fontSize: '0.85rem', color: 'var(--muted)'}}>
                      Cleared {runtimeResetResult.cleared_collections.length} collections:
                      <ul style={{marginTop: '8px', paddingLeft: '20px'}}>
                        {runtimeResetResult.cleared_collections.slice(0, 5).map((item, idx) => (
                          <li key={idx}>
                            {item.collection.replace('_collection', '')}: {item.deleted_count} documents
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
                <div style={{textAlign: 'center'}}>
                  <p style={{fontSize: '0.85rem', color: 'var(--muted)', marginBottom: '12px'}}>
                    This dialog will close automatically...
                  </p>
                </div>
              </>
            )}
          </div>
        </div>
      )}
    </section>
  );
}
