import SectionHeader from '@/ui/components/SectionHeader';

export default function ProfileSection({ user, bots, formatDate, profileData, handleProfileChange, handleProfileSave, handleEmergencyStop }) {
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
            <select 
              value={profileData.currency || 'ZAR'} 
              onChange={(e) => handleProfileChange('currency', e.target.value)}
            >
              <option value="ZAR">ZAR (South African Rand)</option>
              <option value="USD">USD (US Dollar)</option>
              <option value="EUR">EUR (Euro)</option>
              <option value="GBP">GBP (British Pound)</option>
            </select>
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

        {/* Emergency Stop - moved from top bar */}
        <div style={{marginTop: '24px', padding: '16px', background: 'rgba(239, 68, 68, 0.08)', borderRadius: '8px', border: '1px solid rgba(239, 68, 68, 0.3)'}}>
          <h3 style={{marginBottom: '12px', color: 'var(--error)'}}>⚠️ Emergency Controls</h3>
          <p style={{fontSize: '0.85rem', color: 'var(--muted)', marginBottom: '12px'}}>
            Immediately halts all bots and trading activity across the system.
          </p>
          <button className="emergency-btn" onClick={handleEmergencyStop} style={{padding: '10px 24px', fontSize: '0.95rem'}}>
            🛑 Emergency Stop
          </button>
        </div>
      </div>
    </section>
  );
}
