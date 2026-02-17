import React, { useState, useEffect } from 'react';
import { useRealtimeEvent, useLastUpdate } from '../hooks/useRealtime';
import { get, post } from '../lib/apiClient';

const WalletHub = ({ platformFilter = 'all', isPaperMode = true }) => {
  const [balances, setBalances] = useState(null);
  const [requirements, setRequirements] = useState(null);
  const [fundingPlans, setFundingPlans] = useState([]);
  const [paperWallet, setPaperWallet] = useState(null);
  const [paperDepositAmount, setPaperDepositAmount] = useState('');
  const [paperDepositCurrency, setPaperDepositCurrency] = useState('ZAR');
  const [paperActionLoading, setPaperActionLoading] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const lastUpdate = useLastUpdate('wallet');

  useEffect(() => {
    loadWalletData();
  }, [platformFilter]);

  const loadWalletData = async () => {
    try {
      setLoading(true);
      setError(null);
      
      // Load balances, requirements, and funding plans in parallel with safe defaults
      const [balancesData, requirementsData, plansData, paperWalletData] = await Promise.all([
        get('/wallet/balances').catch(err => {
          console.error('Balance fetch error:', err);
          return { master_wallet: {}, last_updated: null }; // Safe default
        }),
        get('/wallet/requirements').catch(err => {
          console.error('Requirements fetch error:', err);
          return { requirements: {} }; // Safe default
        }),
        get('/wallet/funding-plans?status=awaiting_deposit').catch(err => {
          console.error('Funding plans fetch error:', err);
          return { plans: [] }; // Safe default
        }),
        get('/wallet/paper').catch(err => {
          console.error('Paper wallet fetch error:', err);
          return { balances: {}, total: 0, available: {} };
        })
      ]);

      setBalances(balancesData || {});
      setRequirements(requirementsData || {});
      setFundingPlans(plansData.plans || []);
      setPaperWallet(paperWalletData || {});
      setLoading(false);
    } catch (err) {
      console.error('Wallet data load error:', err);
      const statusCode = err.status || err.response?.status || '';
      setError(`Failed to load wallet data${statusCode ? ` (${statusCode})` : ''}: ${err.message || 'Unknown error'}`);
      setLoading(false);
      
      // Initialize to safe defaults even on error
      setBalances({});
      setRequirements({});
      setFundingPlans([]);
      setPaperWallet({});
    }
  };

  // Subscribe to real-time wallet updates
  useRealtimeEvent('wallet', (data) => {
    if (data.event === 'balance_update') {
      loadWalletData();
    }
  }, []);

  // Subscribe to real-time balance updates
  useRealtimeEvent('balances', (data) => {
    setBalances(prevBalances => ({
      ...prevBalances,
      ...data
    }));
  }, []);

  const getHealthColor = (health) => {
    switch (health) {
      case 'healthy': return '#27ae60';
      case 'adequate': return '#3498db';
      case 'warning': return '#f39c12';
      case 'critical': return '#e74c3c';
      default: return '#95a5a6';
    }
  };

  const getHealthIcon = (health) => {
    switch (health) {
      case 'healthy': return '✅';
      case 'adequate': return '✔️';
      case 'warning': return '⚠️';
      case 'critical': return '🚨';
      default: return '❓';
    }
  };

  const cancelFundingPlan = async (planId) => {
    try {
      await post(`/wallet/funding-plans/${planId}/cancel`, {});
      loadWalletData();
    } catch (err) {
      alert('Failed to cancel funding plan: ' + (err.message || 'Unknown error'));
    }
  };

  const handlePaperDeposit = async () => {
    const amount = parseFloat(paperDepositAmount);
    if (!amount || amount <= 0) {
      alert('Enter a valid amount');
      return;
    }
    if (!window.confirm(`Add ${amount} ${paperDepositCurrency} to your training funds?`)) {
      return;
    }
    try {
      setPaperActionLoading(true);
      await post('/wallet/paper/deposit', { amount, currency: paperDepositCurrency });
      setPaperDepositAmount('');
      await loadWalletData();
    } catch (err) {
      alert('Failed to add training funds: ' + (err.message || 'Unknown error'));
    } finally {
      setPaperActionLoading(false);
    }
  };

  const handlePaperReset = async () => {
    if (!window.confirm('Reset training funds to 0? This cannot be undone.')) {
      return;
    }
    try {
      setPaperActionLoading(true);
      await post('/wallet/paper/reset', { confirm: true });
      await loadWalletData();
    } catch (err) {
      alert('Failed to reset training funds: ' + (err.message || 'Unknown error'));
    } finally {
      setPaperActionLoading(false);
    }
  };

  if (loading) {
    return (
      <div style={{ padding: '40px', textAlign: 'center' }}>
        <div style={{ fontSize: '2rem', marginBottom: '20px' }}>💰</div>
        <p>Loading wallet data...</p>
      </div>
    );
  }

  if (error) {
    return (
      <div style={{ padding: '40px', textAlign: 'center' }}>
        <div style={{ fontSize: '2rem', marginBottom: '20px', color: '#e74c3c' }}>⚠️</div>
        <p style={{ color: '#e74c3c', fontWeight: '600', marginBottom: '12px' }}>Backend Error Fetching Balances</p>
        <p style={{ color: 'var(--muted)', fontSize: '0.9rem', marginBottom: '16px' }}>{error}</p>
        <div style={{
          padding: '12px',
          background: 'var(--glass)',
          borderRadius: '6px',
          marginBottom: '16px',
          textAlign: 'left',
          fontSize: '0.85rem',
          color: 'var(--muted)',
          maxWidth: '500px',
          margin: '0 auto 16px'
        }}>
          <p><strong>Possible causes:</strong></p>
          <ul style={{paddingLeft: '20px', marginTop: '8px'}}>
            <li>No exchange API keys configured yet</li>
            <li>Backend wallet service not responding</li>
            <li>Database connection issue</li>
          </ul>
        </div>
        <button onClick={loadWalletData} style={{ 
          marginTop: '20px', 
          padding: '12px 24px',
          background: 'linear-gradient(135deg, #4a90e2 0%, #357abd 100%)',
          color: 'white',
          border: 'none',
          borderRadius: '6px',
          fontWeight: '600',
          cursor: 'pointer'
        }}>
          🔄 Retry
        </button>
      </div>
    );
  }

  // Check if user has any keys saved - check actual key status
  const [keysStatus, setKeysStatus] = React.useState({});
  
  React.useEffect(() => {
    const loadKeysStatus = async () => {
      try {
        const data = await get('/keys/status');
        const statusMap = data?.status_map || {};
        setKeysStatus(statusMap);
      } catch (err) {
        console.error('Keys status fetch error:', err);
      }
    };
    loadKeysStatus();
  }, []);
  
  const masterWallet = balances?.master_wallet || {};
  const exchanges = requirements?.requirements || {};
  
  // Check if Luno key is valid - only show prompt if no valid Luno key
  const lunoStatus = keysStatus?.luno?.status || keysStatus?.luno || 'not_configured';
  const hasValidLunoKey = lunoStatus === 'configured_valid' || lunoStatus === 'test_ok';
  const showKeysPrompt = !hasValidLunoKey && !loading;

  return (
    <div style={{ padding: '20px', maxWidth: '1400px', margin: '0 auto' }}>
      <h1 style={{ marginBottom: '30px', fontSize: '2rem', color: 'var(--text)' }}>
        💰 Wallet Hub
      </h1>

      {showKeysPrompt && (
        <div style={{ padding: '20px', textAlign: 'center', marginBottom: '24px', background: 'var(--glass)', borderRadius: '8px', border: '1px solid var(--line)' }}>
          <div style={{ fontSize: '2rem', marginBottom: '12px' }}>🔑</div>
          <h3 style={{ marginBottom: '8px', color: 'var(--text)' }}>Add Exchange Keys to See Live Wallet Balances</h3>
          <p style={{ color: 'var(--muted)', marginBottom: '16px', fontSize: '0.9rem' }}>
            Configure your exchange API keys to view live balances and enable live trading.
          </p>
          <button
            onClick={() => {
              const event = new CustomEvent('navigateToSection', { detail: { section: 'api' } });
              window.dispatchEvent(event);
              const apiLink = document.querySelector('a[href="#"][class*="api"]');
              if (apiLink) {
                apiLink.click();
              }
            }}
            style={{
              padding: '10px 20px',
              background: 'linear-gradient(135deg, #10b981 0%, #059669 100%)',
              color: 'white',
              border: 'none',
              borderRadius: '6px',
              fontWeight: '600',
              cursor: 'pointer',
              fontSize: '0.95rem'
            }}
          >
            ➕ Add Exchange Keys
          </button>
        </div>
      )}

      <div style={{
        background: 'var(--glass)',
        borderRadius: '16px',
        padding: '30px',
        marginBottom: '30px',
        color: 'var(--text)',
        border: '1px solid var(--line)',
        boxShadow: '0 14px 28px rgba(0,0,0,0.25)'
      }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px' }}>
          <h2 style={{ margin: 0, fontSize: '1.5rem' }}>🏦 Master Luno Wallet</h2>
          {hasValidLunoKey && (
            <div style={{ 
              padding: '6px 12px', 
              background: 'rgba(34, 197, 94, 0.15)', 
              border: '1px solid rgba(34, 197, 94, 0.4)',
              borderRadius: '6px',
              fontSize: '0.85rem',
              color: 'var(--success)'
            }}>
              ✅ Luno Key: Valid
              {keysStatus?.luno?.last_tested_at && (
                <span style={{ marginLeft: '8px', opacity: 0.8 }}>
                  • Last checked: {new Date(keysStatus.luno.last_tested_at).toLocaleString('en-US')}
                </span>
              )}
            </div>
          )}
        </div>
        <div style={{ display: 'flex', gap: '40px', flexWrap: 'wrap' }}>
          <div>
            <div style={{ fontSize: '0.9rem', opacity: 0.9 }}>Total Balance (ZAR)</div>
            <div style={{ fontSize: '2.5rem', fontWeight: 'bold' }}>
              R{(masterWallet.total_zar || 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
            </div>
          </div>
          <div>
            <div style={{ fontSize: '0.9rem', opacity: 0.9 }}>BTC Balance</div>
            <div style={{ fontSize: '1.5rem', fontWeight: 'bold' }}>
              {(masterWallet.btc_balance || 0).toFixed(8)} BTC
            </div>
          </div>
          <div>
            <div style={{ fontSize: '0.9rem', opacity: 0.9 }}>ETH Balance</div>
            <div style={{ fontSize: '1.5rem', fontWeight: 'bold' }}>
              {(masterWallet.eth_balance || 0).toFixed(6)} ETH
            </div>
          </div>
        </div>
        <div style={{ marginTop: '20px', fontSize: '0.85rem', opacity: 0.8 }}>
          Last updated: {balances?.last_updated || 'Just now'}
        </div>
      </div>

      {isPaperMode ? (
        <div style={{
          background: 'var(--glass)',
          borderRadius: '12px',
          padding: '24px',
          marginBottom: '30px',
          border: '1px solid var(--line)'
        }}>
          <h2 style={{ marginBottom: '16px', fontSize: '1.3rem', color: 'var(--text)' }}>🧪 Training Funds</h2>
          <p style={{ marginBottom: '16px', color: 'var(--muted)', fontSize: '0.9rem' }}>
            Simulation funds for paper trading and training only. These credits never touch live balances.
          </p>
          <div style={{ display: 'flex', gap: '24px', flexWrap: 'wrap', alignItems: 'center' }}>
            <div>
              <div style={{ fontSize: '0.85rem', color: 'var(--muted)' }}>Training Capital (Paper Mode)</div>
              <div style={{ fontSize: '2rem', fontWeight: 'bold', color: 'var(--text)' }}>
                {paperWallet?.total?.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 }) || '0.00'}
              </div>
            </div>
            <div style={{ fontSize: '0.85rem', color: 'var(--muted)' }}>
              <div style={{ fontWeight: 600, marginBottom: '4px' }}>Available</div>
              <div>
                {Object.entries(paperWallet?.available || {}).map(([currency, amount]) => (
                  <div key={currency}>{currency}: {Number(amount || 0).toFixed(2)}</div>
                ))}
              </div>
            </div>
            <div style={{ fontSize: '0.85rem', color: 'var(--muted)' }}>
              <div style={{ fontWeight: 600, marginBottom: '4px' }}>Allocated</div>
              <div>
                {Object.entries(paperWallet?.allocated || {}).map(([currency, amount]) => (
                  <div key={currency}>{currency}: {Number(amount || 0).toFixed(2)}</div>
                ))}
              </div>
            </div>
          </div>
          <div style={{ marginTop: '16px', display: 'flex', gap: '12px', flexWrap: 'wrap' }}>
            <input
              type="number"
              min="0"
              step="0.01"
              placeholder="Amount"
              value={paperDepositAmount}
              onChange={(e) => setPaperDepositAmount(e.target.value)}
              style={{
                padding: '8px 10px',
                borderRadius: '10px',
                border: '1px solid var(--line)',
                background: 'var(--panel)',
                color: 'var(--text)'
              }}
            />
            <select
              value={paperDepositCurrency}
              onChange={(e) => setPaperDepositCurrency(e.target.value)}
              style={{
                padding: '8px 10px',
                borderRadius: '10px',
                border: '1px solid var(--line)',
                background: 'var(--panel)',
                color: 'var(--text)'
              }}
            >
              <option value="ZAR">ZAR</option>
              <option value="USDT">USDT</option>
            </select>
            <button
              onClick={handlePaperDeposit}
              disabled={paperActionLoading}
              style={{
                padding: '8px 14px',
                background: 'linear-gradient(135deg, rgba(34, 197, 94, 0.9) 0%, rgba(34, 197, 94, 0.65) 100%)',
                color: '#0b0d14',
                border: 'none',
                borderRadius: '999px',
                fontWeight: 600,
                cursor: paperActionLoading ? 'wait' : 'pointer'
              }}
            >
              ➕ Add Training Funds
            </button>
            <button
              onClick={handlePaperReset}
              disabled={paperActionLoading}
              style={{
                padding: '8px 14px',
                background: 'rgba(239, 68, 68, 0.2)',
                color: 'var(--text)',
                border: '1px solid rgba(239, 68, 68, 0.45)',
                borderRadius: '999px',
                fontWeight: 600,
                cursor: paperActionLoading ? 'wait' : 'pointer'
              }}
            >
              ♻️ Reset Training Capital
            </button>
          </div>
        </div>
      ) : (
        <div style={{
          background: 'var(--glass)',
          borderRadius: '12px',
          padding: '18px',
          marginBottom: '30px',
          border: '1px solid var(--line)',
          color: 'var(--muted)'
        }}>
          Training tools are available in paper mode only.
        </div>
      )}

      {/* Funding Plans (if any) */}
      {fundingPlans.length > 0 && (
        <div style={{ marginBottom: '30px' }}>
          <h2 style={{ marginBottom: '15px', fontSize: '1.3rem', color: 'var(--text)' }}>
            📋 Active Funding Plans
          </h2>
          {fundingPlans.map(plan => (
            <div key={plan.plan_id} style={{
              background: '#fff3cd',
              border: '2px solid #ffc107',
              borderRadius: '8px',
              padding: '20px',
              marginBottom: '15px'
            }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'start' }}>
                <div style={{ flex: 1 }}>
                  <div style={{ fontWeight: 'bold', fontSize: '1.1rem', marginBottom: '10px' }}>
                    💰 {plan.to_exchange?.toUpperCase()} - R{plan.amount_required?.toFixed(2)} needed
                  </div>
                  <div style={{ whiteSpace: 'pre-wrap', color: '#856404', marginBottom: '10px' }}>
                    {plan.ai_message}
                  </div>
                  <div style={{ fontSize: '0.85rem', color: '#856404' }}>
                    Bot: {plan.bot_name || 'Not available'} | Created: {new Date(plan.created_at).toLocaleString()}
                  </div>
                </div>
                <button
                  onClick={() => cancelFundingPlan(plan.plan_id)}
                  style={{
                    background: '#dc3545',
                    color: 'white',
                    border: 'none',
                    padding: '8px 16px',
                    borderRadius: '4px',
                    cursor: 'pointer',
                    fontSize: '0.9rem'
                  }}
                >
                  Cancel
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Exchange Cards */}
      <h2 style={{ marginBottom: '15px', fontSize: '1.3rem', color: 'var(--text)' }}>
        🏢 Exchange Balances
      </h2>
      <div style={{ 
        display: 'grid', 
        gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))',
        gap: '20px'
      }}>
        {Object.entries(exchanges).map(([exchange, data]) => {
          const healthColor = getHealthColor(data.health);
          const healthIcon = getHealthIcon(data.health);
          const surplus = data.surplus_deficit || 0;

          return (
            <div key={exchange} style={{
              background: 'var(--panel)',
              border: `2px solid ${healthColor}`,
              borderRadius: '8px',
              padding: '20px',
              boxShadow: '0 2px 4px rgba(0,0,0,0.1)'
            }}>
              {/* Exchange Header */}
              <div style={{ 
                display: 'flex', 
                justifyContent: 'space-between', 
                alignItems: 'center',
                marginBottom: '15px'
              }}>
                <h3 style={{ fontSize: '1.2rem', color: 'var(--text)', margin: 0 }}>
                  {exchange.toUpperCase()}
                </h3>
                <div style={{ fontSize: '1.5rem' }}>{healthIcon}</div>
              </div>

              {/* Balances */}
              <div style={{ marginBottom: '15px' }}>
                <div style={{ fontSize: '0.85rem', color: 'var(--muted)', marginBottom: '5px' }}>
                  Required Capital
                </div>
                <div style={{ fontSize: '1.5rem', fontWeight: 'bold', color: 'var(--text)' }}>
                  R{(data.required || 0).toLocaleString()}
                </div>
              </div>

              <div style={{ marginBottom: '15px' }}>
                <div style={{ fontSize: '0.85rem', color: 'var(--muted)', marginBottom: '5px' }}>
                  Available Balance
                </div>
                <div style={{ fontSize: '1.3rem', fontWeight: 'bold', color: 'var(--text)' }}>
                  R{(data.available || 0).toLocaleString()}
                </div>
              </div>

              {/* Surplus/Deficit */}
              <div style={{
                padding: '10px',
                borderRadius: '6px',
                background: surplus >= 0 ? '#d4edda' : '#f8d7da',
                color: surplus >= 0 ? '#155724' : '#721c24',
                marginBottom: '15px'
              }}>
                <div style={{ fontSize: '0.85rem' }}>
                  {surplus >= 0 ? 'Surplus' : 'Deficit'}
                </div>
                <div style={{ fontSize: '1.2rem', fontWeight: 'bold' }}>
                  R{Math.abs(surplus).toLocaleString()}
                </div>
              </div>

              {/* Stats */}
              <div style={{ 
                display: 'flex', 
                justifyContent: 'space-between',
                padding: '10px 0',
                borderTop: '1px solid var(--border)',
                fontSize: '0.85rem',
                color: 'var(--muted)'
              }}>
                <div>Active Bots: {data.bots || 0}</div>
                <div>Health: {data.health || 'unknown'}</div>
              </div>

              {/* Action Buttons */}
              <div style={{ display: 'flex', gap: '10px', marginTop: '15px' }}>
                <button style={{
                  flex: 1,
                  padding: '10px',
                  background: '#28a745',
                  color: 'white',
                  border: 'none',
                  borderRadius: '6px',
                  cursor: 'pointer',
                  fontWeight: 'bold'
                }}>
                  Top Up
                </button>
                <button style={{
                  flex: 1,
                  padding: '10px',
                  background: '#6c757d',
                  color: 'white',
                  border: 'none',
                  borderRadius: '6px',
                  cursor: 'pointer',
                  fontWeight: 'bold'
                }}>
                  Withdraw
                </button>
              </div>
            </div>
          );
        })}
      </div>

      {/* No exchanges with bots */}
      {Object.keys(exchanges).length === 0 && (
        <div style={{
          textAlign: 'center',
          padding: '40px',
          color: 'var(--muted)',
          background: 'var(--panel)',
          borderRadius: '8px'
        }}>
          <div style={{ fontSize: '3rem', marginBottom: '10px' }}>🤖</div>
          <p>No active bots yet. Create your first bot to see exchange requirements.</p>
        </div>
      )}
    </div>
  );
};

export default WalletHub;
