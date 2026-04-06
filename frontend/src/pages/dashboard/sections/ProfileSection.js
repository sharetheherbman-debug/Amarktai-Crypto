import SectionHeader from '@/ui/components/SectionHeader';
import DisplayCurrencySelector from '../../../components/DisplayCurrencySelector';

export default function ProfileSection({
  user,
  bots,
  formatDate,
  profileData,
  handleProfileChange,
  handleProfileSave,
  handleEmergencyStop,
  // Display currency preference (from useDisplayCurrency via useDashboardState)
  displayCurrency,
  setDisplayCurrency,
  displayCurrencyError,
}) {
  return (
    <section className="section active">
      <div className="card">
        <SectionHeader
          title="👤 Profile"
          subtitle="Account preferences and security controls."
        />
        <div className="profile-grid">
          <div className="field-group">
            <label>Full Name</label>
            <input 
              type="text" 
              value={profileData.first_name || ''} 
              onChange={(e) => handleProfileChange('first_name', e.target.value)}
            />
          </div>
          <div className="field-group">
            <label>Email Address</label>
            <input 
              type="email" 
              value={profileData.email || ''} 
              onChange={(e) => handleProfileChange('email', e.target.value)}
            />
          </div>
          <div className="field-group">
            <label>Display Currency</label>
            {setDisplayCurrency ? (
              /* Instant-save via useDisplayCurrency hook */
              <DisplayCurrencySelector
                displayCurrency={displayCurrency || 'ZAR'}
                setDisplayCurrency={setDisplayCurrency}
                error={displayCurrencyError}
              />
            ) : (
              /* Fallback: legacy form field (handled by handleProfileSave) */
              <select
                value={profileData.display_currency || profileData.currency || 'ZAR'}
                onChange={(e) => handleProfileChange('display_currency', e.target.value)}
              >
                <option value="ZAR">ZAR – South African Rand</option>
                <option value="USD">USD – US Dollar</option>
                <option value="EUR">EUR – Euro</option>
                <option value="GBP">GBP – British Pound</option>
              </select>
            )}
          </div>
          <div className="field-group">
            <label>New Password (optional)</label>
            <input 
              type="password" 
              placeholder="Leave blank to keep current" 
              value={profileData.new_password || ''}
              onChange={(e) => handleProfileChange('new_password', e.target.value)}
            />
          </div>
          <div className="field-group">
            <label>&nbsp;</label>
            <button onClick={handleProfileSave}>Save Profile</button>
          </div>
        </div>
        
        <div style={{marginTop: '24px', padding: '16px', background: 'var(--panel)', borderRadius: '6px', border: '1px solid var(--line)'}}>
          <h3 style={{marginBottom: '12px'}}>Account Information</h3>
          <div style={{display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '12px'}}>
            <div>
              <div style={{fontSize: '0.85rem', color: 'var(--muted)'}}>Account Status</div>
              <div style={{fontWeight: 600, marginTop: '4px', color: 'var(--success)'}}>Active</div>
            </div>
            <div>
              <div style={{fontSize: '0.85rem', color: 'var(--muted)'}}>Member Since</div>
              <div style={{fontWeight: 600, marginTop: '4px'}}>{formatDate(user?.created_at, { format: 'localeDateString' })}</div>
            </div>
            <div>
              <div style={{fontSize: '0.85rem', color: 'var(--muted)'}}>Total Bots</div>
              <div style={{fontWeight: 600, marginTop: '4px'}}>{bots.length}</div>
            </div>
            <div>
              <div style={{fontSize: '0.85rem', color: 'var(--muted)'}}>Active Bots</div>
              <div style={{fontWeight: 600, marginTop: '4px', color: 'var(--success)'}}>
                {(() => {
                  const activeBots = bots.filter(b => b.status === 'active');
                  const paperBots = activeBots.filter(b => b.trading_mode === 'paper').length;
                  const liveBots = activeBots.filter(b => b.trading_mode === 'live').length;
                  if (liveBots > 0) {
                    return `${activeBots.length} (${liveBots} live, ${paperBots} paper)`;
                  }
                  return `${activeBots.length} (paper)`;
                })()}
              </div>
            </div>
          </div>
        </div>

        {/* Emergency Stop - Compact Button */}
        <div style={{marginTop: '24px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '12px'}}>
          <div>
            <h4 style={{margin: 0, fontSize: '0.9rem', color: 'var(--muted)'}}>Emergency Controls</h4>
            <p style={{fontSize: '0.75rem', color: 'var(--muted)', margin: '4px 0 0 0'}}>
              Immediately halt all trading activity
            </p>
          </div>
          <button 
            className="emergency-btn" 
            onClick={handleEmergencyStop}
            style={{
              padding: '10px 20px',
              fontSize: '0.9rem',
              background: 'var(--error)',
              color: 'white',
              border: 'none',
              borderRadius: '6px',
              fontWeight: 600,
              cursor: 'pointer',
              whiteSpace: 'nowrap'
            }}
          >
            🛑 Emergency Stop
          </button>
        </div>
      </div>
    </section>
  );
}
