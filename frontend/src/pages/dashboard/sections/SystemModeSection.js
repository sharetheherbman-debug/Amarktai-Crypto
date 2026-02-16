import SectionHeader from '@/ui/components/SectionHeader';

const NOT_AVAILABLE = 'Not available';

export default function SystemModeSection({
  bots,
  handleEmergencyStop,
  handlePaperReset,
  handleRiskProfileChange,
  paperResetChecking,
  paperResetError,
  paperResetLoading,
  paperResetPassword,
  paperResetValid,
  riskProfile,
  setPaperResetError,
  setPaperResetPassword,
  setPaperResetValid,
  setShowPaperResetModal,
  showPaperResetModal,
  systemModes,
  toggleSystemMode,
}) {
  const hasLiveBots = bots.some(b => b.trading_mode === 'live' && b.status === 'active');
  const showPaperReset = true;
  const isPaperResetReady = paperResetValid && !paperResetChecking;
  const isPaperResetMode = systemModes.paperTrading && !systemModes.liveTrading;

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
                setPaperResetPassword('');
                setPaperResetValid(false);
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
        <div style={{marginTop: '24px', padding: '16px', background: 'var(--panel)', border: '2px solid var(--error)', borderRadius: '8px'}}>
          <h3 style={{color: 'var(--error)', marginBottom: '8px'}}>🚨 Emergency Controls</h3>
          <p style={{fontSize: '0.85rem', color: 'var(--muted)', marginBottom: '12px'}}>
            Immediately stop ALL bots and trading activity system-wide
          </p>
          <button
            onClick={handleEmergencyStop}
            style={{
              padding: '12px 24px',
              background: 'var(--error)',
              color: 'white',
              border: 'none',
              borderRadius: '6px',
              fontWeight: 700,
              fontSize: '1rem',
              cursor: 'pointer',
              width: '100%',
              maxWidth: '300px'
            }}
          >
            🚨 EMERGENCY STOP
          </button>
        </div>
      </div>
      {showPaperResetModal && (
        <div className="modal-overlay" onClick={() => setShowPaperResetModal(false)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <h3 style={{marginTop: 0}}>Confirm Paper Reset</h3>
            <p style={{color: 'var(--muted)', fontSize: '0.9rem'}}>
              Enter the confirmation password to reset paper bots, trades, and training funds.
            </p>
            <div className="system-reset-input" style={{marginTop: '16px'}}>
              <label htmlFor="paper-reset-password-modal">Confirmation Password</label>
              <input
                id="paper-reset-password-modal"
                type="password"
                value={paperResetPassword}
                onChange={(e) => setPaperResetPassword(e.target.value)}
                placeholder="Enter confirmation password"
              />
              <span className="system-reset-hint">Reset remains unavailable in live trading.</span>
            </div>
            {paperResetError && (
              <div className="system-reset-error">
                {paperResetError}
              </div>
            )}
            <div style={{display: 'flex', gap: '12px', marginTop: '20px', flexWrap: 'wrap'}}>
              <button
                className="system-reset-button"
                onClick={handlePaperReset}
                disabled={!isPaperResetReady || paperResetLoading}
              >
                {paperResetLoading ? 'Resetting...' : paperResetChecking ? 'Checking...' : 'Confirm Reset'}
              </button>
              <button
                onClick={() => {
                  setShowPaperResetModal(false);
                  setPaperResetPassword('');
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
    </section>
  );
}
