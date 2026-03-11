import SectionHeader from '@/ui/components/SectionHeader';
import { formatZAR } from '../../../lib/moneyFormat';

const NOT_AVAILABLE = 'Not available';
const safeToFixed = (value, digits = 2, fallback = '0.00') => {
  const num = Number(value);
  return Number.isFinite(num) ? num.toFixed(digits) : fallback;
};
const safeNumber = (value, fallback = 0) => {
  const num = Number(value);
  return Number.isFinite(num) ? num : fallback;
};
// formatZAR imported from canonical moneyFormat.js — do not redefine here
const formatCurrencyValue = (value, digits = 2) => {
  const num = Number(value);
  if (!Number.isFinite(num)) return null;
  return num.toLocaleString('en-US', {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits
  });
};

export default function CountdownSection({
  countdown,
  customCountdowns,
  metrics,
  newCountdownAmount,
  newCountdownLabel,
  setNewCountdownAmount,
  setNewCountdownLabel,
  setShowAddCountdown,
  showAddCountdown,
  addCustomCountdown,
  deleteCustomCountdown
}) {
  const countdownData = countdown || {};
  const progressPct = safeNumber(countdownData.progress_pct, 0);
  const progressDeg = progressPct ? (progressPct / 100) * 360 : 0;
  const currentCapital = safeNumber(countdownData.current_capital, 0);
  const remainingCapital = Number.isFinite(Number(countdownData.remaining))
    ? safeNumber(countdownData.remaining, 0)
    : Math.max(0, 1000000 - currentCapital);
  const daysRemaining = safeNumber(countdownData.days_remaining, null);
  const requiredDaily = daysRemaining && daysRemaining < 9999
    ? remainingCapital / Math.max(daysRemaining, 1)
    : null;
  const milestoneTargets = [30000, 100000, 250000, 500000, 1000000];
  const nextMilestone = milestoneTargets.find((target) => currentCapital < target) || 1000000;

  return (
    <section className="section active">
      <div className="card">
        <SectionHeader
          title="⏱️ Road to R1,000,000"
          subtitle="Goal-driven automation to 1M ZAR. Every trade compounds the momentum."
          action={(
            <span className={`countdown-mode ${countdownData.mode === 'live' ? 'live' : 'paper'}`}>
              {countdownData.mode || 'Paper'} Mode
            </span>
          )}
        />
        <div className="countdown-progress">
          <div className="countdown-progress-track">
            <span style={{ width: `${Math.min(progressPct, 100)}%` }} />
          </div>
          <span className="countdown-progress-label">{safeToFixed(progressPct, 1, '0.0')}% toward R1,000,000</span>
        </div>

        <div className="countdown-summary-grid">
          <div>
            <span>Current Equity</span>
            <strong>{formatZAR(currentCapital)}</strong>
          </div>
          <div>
            <span>Goal</span>
            <strong>R1,000,000</strong>
          </div>
          <div>
            <span>Remaining</span>
            <strong>{formatZAR(remainingCapital)}</strong>
          </div>
          <div>
            <span>Required Daily Avg</span>
            <strong>{requiredDaily ? formatZAR(requiredDaily) : NOT_AVAILABLE}</strong>
          </div>
        </div>
        
        {countdownData.status === 'achieved' ? (
          <div style={{textAlign: 'center', padding: '60px 20px'}}>
            <div style={{fontSize: '5rem', marginBottom: '20px'}}>🎉</div>
            <div style={{fontSize: '2.5rem', fontWeight: 700, color: 'var(--success)', marginBottom: '15px'}}>
              TARGET ACHIEVED!
            </div>
            <div style={{fontSize: '1.3rem', color: 'var(--muted)'}}>
              You reached R1,000,000!
            </div>
          </div>
        ) : (
          <>
            {/* Main Stats Row */}
            <div style={{display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '20px', marginBottom: '24px'}}>
              {/* Days Remaining Card */}
              <div className="countdown-hero" style={{
                padding: '30px',
                border: '1px solid rgba(16, 185, 129, 0.35)',
                borderRadius: '16px',
                textAlign: 'center',
                background: 'rgba(16, 185, 129, 0.12)',
                boxShadow: '0 8px 18px rgba(0, 0, 0, 0.2)'
              }}>
                <div style={{fontSize: '4rem', fontWeight: 700, color: countdownData.days_remaining >= 9999 ? 'var(--error)' : 'var(--success)', margin: '12px 0'}}>
                  {countdownData.days_remaining < 9999 ? countdownData.days_remaining : '∞'}
                </div>
                <p style={{fontSize: '1rem', fontWeight: 600, color: 'var(--muted)', marginBottom: '4px'}}>
                  DAYS REMAINING
                </p>
                <p style={{fontSize: '1.5rem', fontWeight: 700, background: 'linear-gradient(45deg, var(--success), var(--success))', WebkitBackgroundClip: 'text', backgroundClip: 'text', color: 'transparent', margin: '8px 0'}}>
                  TO R1 MILLION
                </p>
              </div>
              
              {/* Progress Circle Card */}
              <div className="countdown-ring" style={{
                padding: '32px',
                border: '1px solid var(--line)',
                borderRadius: '16px',
                display: 'flex',
                flexDirection: 'column',
                justifyContent: 'center',
                alignItems: 'center',
                background: 'rgba(15, 17, 26, 0.7)'
              }}>
                <div style={{width: '180px', height: '180px', borderRadius: '50%', background: `conic-gradient(var(--success) 0deg ${progressDeg}deg, var(--accent-bright) ${progressDeg}deg 360deg)`, display: 'flex', alignItems: 'center', justifyContent: 'center', boxShadow: '0 6px 14px rgba(0, 0, 0, 0.3)'}}>
                  <div style={{width: '140px', height: '140px', borderRadius: '50%', background: 'rgba(11, 13, 20, 0.9)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '2rem', fontWeight: 700, color: 'var(--success)', flexDirection: 'column'}}>
                    <div>{safeToFixed(countdownData.progress_pct, 1, '0.0')}%</div>
                    <div style={{fontSize: '0.7rem', color: 'var(--muted)', marginTop: '4px'}}>Complete</div>
                  </div>
                </div>
              </div>
            </div>
            
            <div className="countdown-roadmap">
              <div className="countdown-roadmap-header">
                <div>
                  <h3>Roadmap Milestones</h3>
                  <p>Track the climb from today's balance to R1,000,000.</p>
                </div>
                <span className="countdown-roadmap-badge">{safeToFixed(progressPct, 1, '0.0')}% Complete</span>
              </div>
              <div className="countdown-roadmap-bar">
                <div
                  className="countdown-roadmap-fill"
                  style={{ width: `${Math.min(progressPct, 100)}%` }}
                />
              </div>
              <div className="countdown-roadmap-milestones">
                {milestoneTargets.map((target) => {
                  const isComplete = currentCapital >= target;
                  const labelValue = formatCurrencyValue(target, 0) || target.toLocaleString();
                  return (
                    <span
                      key={target}
                      className={`countdown-roadmap-chip ${isComplete ? 'active' : ''}`}
                    >
                      R{labelValue}
                    </span>
                  );
                })}
              </div>
              <div className="countdown-roadmap-next">
                Next milestone: <strong>{formatZAR(nextMilestone, 0)}</strong> - keep the momentum.
              </div>
            </div>

            {/* Key Metrics Grid */}
            <div style={{display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '16px', marginBottom: '24px'}}>
              <div style={{padding: '20px', background: 'rgba(16, 185, 129, 0.12)', borderRadius: '10px', border: '1px solid rgba(16, 185, 129, 0.35)'}}>
                <div style={{fontSize: '0.8rem', color: 'var(--muted)', marginBottom: '8px', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.5px'}}>Current Capital</div>
                <div style={{fontSize: '1.8rem', fontWeight: 700, color: 'var(--success)'}}>
                  R{Number.isFinite(Number(countdownData.current_capital))
                    ? safeToFixed(countdownData.current_capital, 2).replace(/\B(?=(\d{3})+(?!\d))/g, ',')
                    : '0.00'}
                </div>
              </div>
              
              <div style={{padding: '20px', background: 'rgba(56, 189, 248, 0.12)', borderRadius: '10px', border: '1px solid rgba(56, 189, 248, 0.35)'}}>
                <div style={{fontSize: '0.8rem', color: 'var(--muted)', marginBottom: '8px', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.5px'}}>Daily ROI</div>
                <div style={{fontSize: '1.8rem', fontWeight: 700, color: 'var(--accent-bright)'}}>
                  {safeToFixed(countdownData.metrics?.daily_roi_pct, 3, '0.000')}%
                </div>
              </div>
              
              <div style={{padding: '20px', background: 'rgba(16, 185, 129, 0.12)', borderRadius: '10px', border: '1px solid rgba(16, 185, 129, 0.25)'}}>
                <div style={{fontSize: '0.8rem', color: 'var(--muted)', marginBottom: '8px', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.5px'}}>Avg Daily Profit</div>
                <div style={{fontSize: '1.8rem', fontWeight: 700, color: 'var(--success)'}}>
                  R{safeToFixed(countdownData.metrics?.avg_daily_profit, 2)}
                </div>
              </div>
              
              <div style={{padding: '20px', background: 'rgba(56, 189, 248, 0.1)', borderRadius: '10px', border: '1px solid rgba(56, 189, 248, 0.25)'}}>
                <div style={{fontSize: '0.8rem', color: 'var(--muted)', marginBottom: '8px', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.5px'}}>Remaining</div>
                <div style={{fontSize: '1.8rem', fontWeight: 700, color: 'var(--accent-bright)'}}>
                  R{Number.isFinite(Number(countdownData.remaining))
                    ? safeToFixed(countdownData.remaining, 2).replace(/\B(?=(\d{3})+(?!\d))/g, ',')
                    : '1,000,000'}
                </div>
              </div>
            </div>
            
            {/* Details Grid */}
            <div style={{display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '16px', marginBottom: '20px'}}>
              <div style={{padding: '16px', background: 'var(--panel)', borderRadius: '8px', border: '1px solid var(--line)'}}>
                <div style={{fontSize: '0.85rem', color: 'var(--muted)', marginBottom: '6px'}}>Avg Daily Profit</div>
                <div style={{fontSize: '1.3rem', fontWeight: 700, color: 'var(--success)'}}>
                  R{safeToFixed(countdownData.metrics?.avg_daily_profit, 2)}
                </div>
              </div>
              <div style={{padding: '16px', background: 'var(--panel)', borderRadius: '8px', border: '1px solid var(--line)'}}>
                <div style={{fontSize: '0.85rem', color: 'var(--muted)', marginBottom: '6px'}}>Total Trades</div>
                <div style={{fontSize: '1.3rem', fontWeight: 700, color: 'var(--accent)'}}>
                  {countdownData.metrics?.total_trades || 0}
                </div>
              </div>
              <div style={{padding: '16px', background: 'var(--panel)', borderRadius: '8px', border: '1px solid var(--line)'}}>
                <div style={{fontSize: '0.85rem', color: 'var(--muted)', marginBottom: '6px'}}>Est. Completion</div>
                <div style={{fontSize: '1.1rem', fontWeight: 700, color: 'var(--text)'}}>
                  {countdownData.completion_date || NOT_AVAILABLE}
                </div>
              </div>
              <div style={{padding: '16px', background: 'var(--panel)', borderRadius: '8px', border: '1px solid var(--line)'}}>
                <div style={{fontSize: '0.85rem', color: 'var(--muted)', marginBottom: '6px'}}>Projection Type</div>
                <div style={{fontSize: '1.1rem', fontWeight: 700, color: 'var(--text)', textTransform: 'capitalize'}}>
                  {countdownData.projections?.using || NOT_AVAILABLE}
                </div>
              </div>
            </div>
            
            {/* 12-Month AI Projection */}
            {countdownData.projections?.twelve_month && (
              <div style={{marginTop: '20px', padding: '20px', background: 'linear-gradient(135deg, rgba(56, 189, 248, 0.12) 0%, rgba(14, 165, 233, 0.05) 100%)', borderRadius: '12px', border: '2px solid var(--accent-bright)'}}>
                <h3 style={{color: 'var(--accent-bright)', marginBottom: '16px', display: 'flex', alignItems: 'center', gap: '8px'}}>
                  🔮 AI 12-Month Projection
                </h3>
                <div style={{display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '16px'}}>
                  <div style={{textAlign: 'center', padding: '16px', background: 'var(--panel)', borderRadius: '8px'}}>
                    <div style={{fontSize: '0.85rem', color: 'var(--muted)', marginBottom: '8px'}}>Projected Value</div>
                    <div style={{fontSize: '1.6rem', fontWeight: 700, color: 'var(--accent-bright)'}}>
                      R{Number.isFinite(Number(countdownData.projections?.twelve_month))
                        ? safeToFixed(countdownData.projections.twelve_month, 2).replace(/\B(?=(\d{3})+(?!\d))/g, ',')
                        : '0.00'}
                    </div>
                  </div>
                  <div style={{textAlign: 'center', padding: '16px', background: 'var(--panel)', borderRadius: '8px'}}>
                    <div style={{fontSize: '0.85rem', color: 'var(--muted)', marginBottom: '8px'}}>Expected Gain</div>
                    <div style={{fontSize: '1.6rem', fontWeight: 700, color: 'var(--success)'}}>
                      +R{Number.isFinite(Number(countdownData.projections?.twelve_month_gain))
                        ? safeToFixed(countdownData.projections.twelve_month_gain, 2).replace(/\B(?=(\d{3})+(?!\d))/g, ',')
                        : '0.00'}
                    </div>
                  </div>
                  <div style={{textAlign: 'center', padding: '16px', background: 'var(--panel)', borderRadius: '8px'}}>
                    <div style={{fontSize: '0.85rem', color: 'var(--muted)', marginBottom: '8px'}}>12-Month ROI</div>
                    <div style={{fontSize: '1.6rem', fontWeight: 700, color: 'var(--accent-bright)'}}>
                      {safeToFixed(countdownData.projections?.twelve_month_roi, 1, '0.0')}%
                    </div>
                  </div>
                </div>
                <div style={{marginTop: '12px', padding: '12px', background: 'var(--glass)', borderRadius: '6px', fontSize: '0.85rem', color: 'var(--muted)', textAlign: 'center'}}>
                  💡 Based on current {safeToFixed(countdownData.metrics?.daily_roi_pct, 3, '0')}% daily ROI with compound interest over 365 days
                </div>
              </div>
            )}
            
            <div style={{marginTop: '16px', padding: '16px', background: 'rgba(16, 185, 129, 0.12)', borderRadius: '10px', border: '1px solid rgba(16, 185, 129, 0.35)', textAlign: 'center'}}>
              <p style={{margin: 0, fontSize: '1rem', color: 'var(--text)', fontWeight: 600}}>
                {countdownData.message || 'Keep trading to reach your goal!'}
              </p>
            </div>
            
            <div style={{marginTop: '12px', padding: '12px', background: 'var(--glass)', borderRadius: '6px', border: '1px solid var(--line)', fontSize: '0.85rem', color: 'var(--muted)'}}>
              <p><strong>How it works:</strong> Based on your current capital (R{Number.isFinite(Number(countdownData.current_capital))
                ? safeToFixed(countdownData.current_capital, 2).replace(/\B(?=(\d{3})+(?!\d))/g, ',')
                : '0.00'}) and daily ROI ({safeToFixed(countdownData.metrics?.daily_roi_pct, 3, '0')}%), the system uses compound interest calculations to project your path to R1,000,000. Updates in real-time as you trade!</p>
            </div>
          </>
        )}
        
        {/* Custom User Countdowns */}
        <div style={{marginTop: '40px', paddingTop: '30px', borderTop: '2px solid var(--line)'}}>
          <div style={{display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px'}}>
            <h3 style={{fontSize: '1.3rem', fontWeight: 600, color: 'var(--text)'}}>
              🎯 Your Custom Goals
            </h3>
            {customCountdowns.length < 2 && (
              <button
                onClick={() => setShowAddCountdown(!showAddCountdown)}
                style={{
                  padding: '8px 16px',
                  background: showAddCountdown ? 'var(--error)' : 'linear-gradient(135deg, var(--accent2) 0%, var(--accent2) 100%)',
                  color: 'white',
                  border: 'none',
                  borderRadius: '6px',
                  cursor: 'pointer',
                  fontWeight: 600,
                  fontSize: '0.9rem'
                }}
              >
                {showAddCountdown ? '✖ Cancel' : '➕ Add Goal'}
              </button>
            )}
          </div>
          
          {/* Add Countdown Form */}
          {showAddCountdown && (
            <div style={{
              marginBottom: '20px',
              padding: '20px',
              background: 'linear-gradient(135deg, rgba(139, 92, 246, 0.1) 0%, rgba(124, 58, 237, 0.05) 100%)',
              borderRadius: '12px',
              border: '2px solid var(--accent2)'
            }}>
              <h4 style={{marginBottom: '16px', color: 'var(--accent2)'}}>Add New Goal</h4>
              <div style={{display: 'grid', gridTemplateColumns: '1fr 1fr auto', gap: '12px', alignItems: 'end'}}>
                <div>
                  <label style={{display: 'block', fontSize: '0.85rem', color: 'var(--muted)', marginBottom: '6px'}}>
                    Goal Label
                  </label>
                  <input
                    type="text"
                    value={newCountdownLabel}
                    onChange={(e) => setNewCountdownLabel(e.target.value)}
                    placeholder="e.g., BMW M3"
                    maxLength={50}
                    style={{
                      width: '100%',
                      padding: '10px',
                      borderRadius: '6px',
                      border: '1px solid var(--line)',
                      background: 'var(--panel)',
                      color: 'var(--text)',
                      fontSize: '0.95rem'
                    }}
                  />
                </div>
                <div>
                  <label style={{display: 'block', fontSize: '0.85rem', color: 'var(--muted)', marginBottom: '6px'}}>
                    Target Amount (ZAR)
                  </label>
                  <input
                    type="number"
                    value={newCountdownAmount}
                    onChange={(e) => setNewCountdownAmount(e.target.value)}
                    placeholder="e.g., 1340000"
                    min="1"
                    style={{
                      width: '100%',
                      padding: '10px',
                      borderRadius: '6px',
                      border: '1px solid var(--line)',
                      background: 'var(--panel)',
                      color: 'var(--text)',
                      fontSize: '0.95rem'
                    }}
                  />
                </div>
                <button
                  onClick={addCustomCountdown}
                  style={{
                    padding: '10px 20px',
                    background: 'linear-gradient(135deg, var(--success) 0%, var(--success) 100%)',
                    color: 'white',
                    border: 'none',
                    borderRadius: '6px',
                    cursor: 'pointer',
                    fontWeight: 600,
                    fontSize: '0.9rem',
                    height: '42px'
                  }}
                >
                  ✓ Add
                </button>
              </div>
            </div>
          )}
          
          {/* Display Custom Countdowns */}
          {customCountdowns.length === 0 ? (
            <div style={{
              padding: '40px 20px',
              textAlign: 'center',
              background: 'var(--panel)',
              borderRadius: '12px',
              border: '1px solid var(--line)'
            }}>
              <div style={{fontSize: '3rem', marginBottom: '12px'}}>🎯</div>
              <p style={{color: 'var(--muted)', fontSize: '1rem'}}>
                No custom goals yet. Add up to 2 personal financial targets!
              </p>
              <p style={{color: 'var(--muted)', fontSize: '0.85rem', marginTop: '8px'}}>
                Track your progress towards that dream car, house, or any goal.
              </p>
            </div>
          ) : (
            <div style={{display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: '20px'}}>
              {customCountdowns.map((cd) => {
                const progressDeg = (cd.progress_pct / 100) * 360;
                return (
                  <div key={cd.id} style={{
                    padding: '24px',
                    background: 'var(--panel)',
                    borderRadius: '12px',
                    border: '2px solid var(--accent)',
                    position: 'relative'
                  }}>
                    <button
                      onClick={() => deleteCustomCountdown(cd.id)}
                      style={{
                        position: 'absolute',
                        top: '12px',
                        right: '12px',
                        padding: '4px 8px',
                        background: 'var(--error)',
                        color: 'white',
                        border: 'none',
                        borderRadius: '4px',
                        cursor: 'pointer',
                        fontSize: '0.75rem',
                        fontWeight: 600
                      }}
                    >
                      ✖
                    </button>
                    
                    <h4 style={{fontSize: '1.2rem', fontWeight: 700, color: 'var(--text)', marginBottom: '16px'}}>
                      {cd.label}
                    </h4>
                    
                    <div style={{textAlign: 'center', marginBottom: '16px'}}>
                      <div style={{fontSize: '3rem', fontWeight: 700, color: cd.days_remaining >= 9999 ? 'var(--error)' : 'var(--accent)'}}>
                        {cd.days_remaining < 9999 ? cd.days_remaining : '∞'}
                      </div>
                      <div style={{fontSize: '0.85rem', color: 'var(--muted)', fontWeight: 600}}>
                        DAYS REMAINING
                      </div>
                    </div>
                    
                    {/* Progress Bar */}
                    <div style={{marginBottom: '16px'}}>
                      <div style={{display: 'flex', justifyContent: 'space-between', marginBottom: '8px', fontSize: '0.85rem'}}>
                        <span>R{safeToFixed(cd.current_progress, 2).replace(/\B(?=(\d{3})+(?!\d))/g, ',')}</span>
                        <span style={{color: 'var(--accent)', fontWeight: 600}}>
                          {safeToFixed(cd.progress_pct, 1, '0.0')}%
                        </span>
                        <span>R{safeToFixed(cd.target_amount, 0, '0').replace(/\B(?=(\d{3})+(?!\d))/g, ',')}</span>
                      </div>
                      <div style={{
                        height: '12px',
                        background: 'var(--glass)',
                        borderRadius: '6px',
                        overflow: 'hidden',
                        border: '1px solid var(--line)'
                      }}>
                        <div style={{
                          height: '100%',
                          width: `${Math.min(cd.progress_pct, 100)}%`,
                          background: 'linear-gradient(90deg, var(--accent) 0%, var(--accent2) 100%)',
                          transition: 'width 1s ease-in-out'
                        }}></div>
                      </div>
                    </div>
                    
                    <div style={{
                      padding: '12px',
                      background: 'var(--glass)',
                      borderRadius: '6px',
                      border: '1px solid var(--line)',
                      fontSize: '0.85rem',
                      color: 'var(--muted)',
                      textAlign: 'center'
                    }}>
                      R{safeToFixed(cd.remaining, 2).replace(/\B(?=(\d{3})+(?!\d))/g, ',')} remaining
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>
    </section>
  );
}
