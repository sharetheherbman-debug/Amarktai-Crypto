import React, { useState, useEffect, useCallback } from 'react';
import { useRealtimeEvent } from '../hooks/useRealtime';
import { get, post } from '../lib/apiClient';

const EXCHANGE_NATIVE = {
  luno: 'ZAR',
  binance: 'USDT',
  kucoin: 'USDT',
  bybit: 'USDT',
  kraken: 'USDT',
  bitget: 'USDT',
  gate: 'USDT',
  coinbase: 'USDT',
};

const EXCHANGE_LABELS = {
  luno: 'Luno',
  binance: 'Binance',
  kucoin: 'KuCoin',
  bybit: 'Bybit',
  kraken: 'Kraken',
  bitget: 'Bitget',
  gate: 'Gate.io',
  coinbase: 'Coinbase',
};

const WalletHub = ({ platformFilter = 'all', isPaperMode = true }) => {
  const [walletStatus, setWalletStatus] = useState(null);
  const [platformSummary, setPlatformSummary] = useState(null);
  const [platformWallets, setPlatformWallets] = useState({});
  const [fundingPlans, setFundingPlans] = useState([]);
  const [paperWallet, setPaperWallet] = useState(null);
  const [fundInputs, setFundInputs] = useState({});
  const [fundCurrencies, setFundCurrencies] = useState({});
  const [actionLoading, setActionLoading] = useState({});
  const [globalDepositAmount, setGlobalDepositAmount] = useState('');
  const [globalDepositCurrency, setGlobalDepositCurrency] = useState('ZAR');
  const [paperActionLoading, setPaperActionLoading] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  const loadWalletData = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);

      const [statusData, platformData, summaryData, plansData, paperWalletData] = await Promise.all([
        get('/wallet/status').catch(() => null),
        get('/wallet/platform').catch(() => null),
        get('/wallet/platform/summary').catch(() => null),
        get('/wallet/funding-plans?status=awaiting_deposit').catch(() => ({ plans: [] })),
        get('/wallet/paper').catch(() => ({ balances: {}, total: 0, available: {} })),
      ]);

      setWalletStatus(statusData);
      setPlatformWallets((platformData && platformData.platform_wallets) || {});
      setPlatformSummary(summaryData);
      setFundingPlans((plansData && plansData.plans) || []);
      setPaperWallet(paperWalletData || {});
      setLoading(false);
    } catch (err) {
      setError('Failed to load wallet data: ' + (err.message || 'Unknown error'));
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadWalletData();
  }, [platformFilter, loadWalletData]);

  useRealtimeEvent('wallet', (data) => {
    if (data.event === 'balance_update') loadWalletData();
  }, []);

  const handleFundPlatform = async (exchange) => {
    const amount = parseFloat(fundInputs[exchange] || '');
    if (!amount || amount <= 0) { alert('Enter a valid positive amount'); return; }
    const nativeCur = EXCHANGE_NATIVE[exchange] || 'ZAR';
    const currency = fundCurrencies[exchange] || nativeCur;
    const label = EXCHANGE_LABELS[exchange] || exchange;
    if (!window.confirm('Add ' + amount + ' ' + currency + ' to ' + label + ' paper wallet?')) return;
    try {
      setActionLoading(prev => ({ ...prev, [exchange]: true }));
      await post('/wallet/platform/' + exchange + '/fund', { amount, currency, confirmed: true });
      setFundInputs(prev => ({ ...prev, [exchange]: '' }));
      await loadWalletData();
    } catch (err) {
      alert('Failed to fund ' + exchange + ' wallet: ' + (err.message || 'Unknown error'));
    } finally {
      setActionLoading(prev => ({ ...prev, [exchange]: false }));
    }
  };

  const handleResetPlatform = async (exchange) => {
    const label = EXCHANGE_LABELS[exchange] || exchange;
    if (!window.confirm('Reset ' + label + ' paper wallet to 0? This cannot be undone.')) return;
    try {
      setActionLoading(prev => ({ ...prev, [exchange]: true }));
      await post('/wallet/platform/' + exchange + '/reset', { confirm: true });
      await loadWalletData();
    } catch (err) {
      alert('Failed to reset ' + exchange + ' wallet: ' + (err.message || 'Unknown error'));
    } finally {
      setActionLoading(prev => ({ ...prev, [exchange]: false }));
    }
  };

  const handleGlobalDeposit = async () => {
    const amount = parseFloat(globalDepositAmount);
    if (!amount || amount <= 0) { alert('Enter a valid amount'); return; }
    if (!window.confirm('Add ' + amount + ' ' + globalDepositCurrency + ' to your global paper wallet?')) return;
    try {
      setPaperActionLoading(true);
      await post('/wallet/paper/deposit', { amount, currency: globalDepositCurrency });
      setGlobalDepositAmount('');
      await loadWalletData();
    } catch (err) {
      alert('Failed to add funds: ' + (err.message || 'Unknown error'));
    } finally {
      setPaperActionLoading(false);
    }
  };

  const handleGlobalReset = async () => {
    if (!window.confirm('Reset global paper wallet to 0? This cannot be undone.')) return;
    try {
      setPaperActionLoading(true);
      await post('/wallet/paper/reset', { confirm: true });
      await loadWalletData();
    } catch (err) {
      alert('Failed to reset: ' + (err.message || 'Unknown error'));
    } finally {
      setPaperActionLoading(false);
    }
  };

  const cancelFundingPlan = async (planId) => {
    try {
      await post('/wallet/funding-plans/' + planId + '/cancel', {});
      loadWalletData();
    } catch (err) {
      alert('Failed to cancel funding plan: ' + (err.message || 'Unknown error'));
    }
  };

  const fmtZAR = (v) =>
    'R' + Number(v || 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });

  const fmtNative = (v, currency) =>
    Number(v || 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 4 }) + ' ' + currency;

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
        <p style={{ color: '#e74c3c', fontWeight: '600', marginBottom: '12px' }}>Wallet Error</p>
        <p style={{ color: 'var(--muted)', fontSize: '0.9rem', marginBottom: '16px' }}>{error}</p>
        <button onClick={loadWalletData} style={{
          padding: '12px 24px', background: 'linear-gradient(135deg,#4a90e2,#357abd)',
          color: 'white', border: 'none', borderRadius: '6px', fontWeight: '600', cursor: 'pointer'
        }}>Retry</button>
      </div>
    );
  }

  const unlockedExchanges = (walletStatus && walletStatus.unlocked_exchanges) || [];
  const mode = (walletStatus && walletStatus.mode) || 'paper';
  const totalPortfolioZar = (platformSummary && (platformSummary.total_portfolio_zar != null
    ? platformSummary.total_portfolio_zar
    : platformSummary.global_wallet_zar)) || 0;
  const availableGlobalZar = (paperWallet && (paperWallet.available_wallet_zar != null
    ? paperWallet.available_wallet_zar
    : ((paperWallet.available && paperWallet.available.ZAR) || 0))) || 0;

  const displayExchanges = unlockedExchanges.length > 0
    ? unlockedExchanges
    : Object.keys(platformWallets);

  return (
    <div style={{ padding: '20px', maxWidth: '1400px', margin: '0 auto' }}>
      <h1 style={{ marginBottom: '30px', fontSize: '2rem', color: 'var(--text)' }}>
        Wallet Hub
      </h1>

      {/* Mode Banner */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: '12px',
        padding: '10px 16px', marginBottom: '24px',
        background: mode === 'paper' ? 'rgba(59,130,246,0.1)' : 'rgba(34,197,94,0.1)',
        border: '1px solid ' + (mode === 'paper' ? 'rgba(59,130,246,0.3)' : 'rgba(34,197,94,0.3)'),
        borderRadius: '8px', fontSize: '0.9rem',
      }}>
        <span style={{ fontWeight: 600, color: 'var(--text)' }}>
          {mode === 'paper' ? 'Paper Trading Mode' : 'Live Trading Mode'}
        </span>
        <span style={{ color: 'var(--muted)' }}>
          {mode === 'paper'
            ? '— Simulated funds only. No real money at risk.'
            : '— Real exchange balances. Handle with care.'}
        </span>
      </div>

      {/* Portfolio Summary */}
      <div style={{
        background: 'var(--glass)', borderRadius: '16px', padding: '24px',
        marginBottom: '24px', border: '1px solid var(--line)',
        boxShadow: '0 14px 28px rgba(0,0,0,0.25)',
      }}>
        <h2 style={{ margin: '0 0 20px', fontSize: '1.3rem', color: 'var(--text)' }}>
          Portfolio Summary
        </h2>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '20px' }}>
          <div>
            <div style={{ fontSize: '0.82rem', color: 'var(--muted)', marginBottom: '4px' }}>Total Equity (ZAR)</div>
            <div style={{ fontSize: '1.8rem', fontWeight: 'bold', color: 'var(--text)' }}>{fmtZAR(totalPortfolioZar)}</div>
          </div>
          <div>
            <div style={{ fontSize: '0.82rem', color: 'var(--muted)', marginBottom: '4px' }}>Global Paper Wallet</div>
            <div style={{ fontSize: '1.4rem', fontWeight: 600, color: 'var(--text)' }}>{fmtZAR(availableGlobalZar)}</div>
          </div>
          <div>
            <div style={{ fontSize: '0.82rem', color: 'var(--muted)', marginBottom: '4px' }}>Active Bots</div>
            <div style={{ fontSize: '1.4rem', fontWeight: 600, color: 'var(--text)' }}>
              {(walletStatus && walletStatus.active_bots) || 0}
            </div>
          </div>
          <div>
            <div style={{ fontSize: '0.82rem', color: 'var(--muted)', marginBottom: '4px' }}>Status</div>
            <div style={{
              display: 'inline-block', padding: '4px 10px', borderRadius: '6px', fontWeight: 600, fontSize: '0.88rem',
              background: (walletStatus && walletStatus.funding_status) === 'FUNDED' ? 'rgba(34,197,94,0.15)' : 'rgba(239,68,68,0.15)',
              border: '1px solid ' + ((walletStatus && walletStatus.funding_status) === 'FUNDED' ? 'rgba(34,197,94,0.4)' : 'rgba(239,68,68,0.4)'),
              color: (walletStatus && walletStatus.funding_status) === 'FUNDED' ? 'var(--success)' : 'var(--error)',
            }}>
              {(walletStatus && walletStatus.funding_status) === 'FUNDED' ? 'Funded' :
               (walletStatus && walletStatus.funding_status) === 'UNFUNDED' ? 'Unfunded' : 'Not Configured'}
            </div>
          </div>
        </div>
        {unlockedExchanges.length === 0 && (
          <div style={{ marginTop: '16px', padding: '12px', background: 'rgba(245,158,11,0.1)', border: '1px solid rgba(245,158,11,0.3)', borderRadius: '8px', fontSize: '0.85rem', color: 'var(--muted)' }}>
            No exchanges unlocked yet. Add and test API keys in API Setup to unlock per-platform wallets.
          </div>
        )}
      </div>

      {/* Platform Wallets (paper mode) */}
      {mode === 'paper' && (
        <div style={{ marginBottom: '30px' }}>
          <h2 style={{ marginBottom: '16px', fontSize: '1.3rem', color: 'var(--text)' }}>
            Platform Paper Wallets
          </h2>
          {displayExchanges.length === 0 ? (
            <div style={{ textAlign: 'center', padding: '32px', background: 'var(--glass)', borderRadius: '12px', border: '1px solid var(--line)', color: 'var(--muted)' }}>
              <p>No platforms unlocked. Add API keys to activate per-platform wallets.</p>
              <p style={{ fontSize: '0.85rem', marginTop: '8px' }}>Platform wallets appear here once exchange keys are tested successfully.</p>
            </div>
          ) : (
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: '16px' }}>
              {displayExchanges.map((exchange) => {
                const wallet = platformWallets[exchange] || {};
                const nativeCurrency = wallet.native_currency || EXCHANGE_NATIVE[exchange] || 'ZAR';
                const available = wallet.available || 0;
                const funded = wallet.funded || available > 0;
                const zarBreakdown = platformSummary && platformSummary.by_exchange && platformSummary.by_exchange[exchange];
                const zarValue = (zarBreakdown && zarBreakdown.zar) || 0;
                const isLoading = actionLoading[exchange];
                const currency = fundCurrencies[exchange] || nativeCurrency;

                return (
                  <div key={exchange} style={{
                    background: 'var(--panel)', borderRadius: '12px', padding: '20px',
                    border: '1px solid ' + (funded ? 'rgba(34,197,94,0.4)' : 'var(--line)'),
                    boxShadow: '0 4px 12px rgba(0,0,0,0.15)',
                  }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
                      <h3 style={{ margin: 0, fontSize: '1.1rem', color: 'var(--text)' }}>
                        {EXCHANGE_LABELS[exchange] || exchange.toUpperCase()}
                      </h3>
                      <span style={{
                        padding: '3px 8px', borderRadius: '4px', fontSize: '0.75rem', fontWeight: 600,
                        background: funded ? 'rgba(34,197,94,0.15)' : 'rgba(156,163,175,0.15)',
                        border: '1px solid ' + (funded ? 'rgba(34,197,94,0.4)' : 'rgba(156,163,175,0.4)'),
                        color: funded ? 'var(--success)' : 'var(--muted)',
                      }}>
                        {funded ? 'Funded' : 'Unfunded'}
                      </span>
                    </div>
                    <div style={{ marginBottom: '12px' }}>
                      <div style={{ fontSize: '0.8rem', color: 'var(--muted)', marginBottom: '4px' }}>
                        Available ({nativeCurrency})
                      </div>
                      <div style={{ fontSize: '1.5rem', fontWeight: 'bold', color: 'var(--text)' }}>
                        {fmtNative(available, nativeCurrency)}
                      </div>
                      {nativeCurrency !== 'ZAR' && zarValue > 0 && (
                        <div style={{ fontSize: '0.82rem', color: 'var(--muted)', marginTop: '2px' }}>
                          approx. {fmtZAR(zarValue)}
                        </div>
                      )}
                    </div>
                    <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap', marginTop: '12px' }}>
                      <input
                        type="number"
                        min="0"
                        step="0.01"
                        placeholder={'Amount (' + nativeCurrency + ')'}
                        aria-label={'Fund ' + (EXCHANGE_LABELS[exchange] || exchange) + ' paper wallet amount'}
                        id={'fund-amount-' + exchange}
                        name={'fund_amount_' + exchange}
                        value={fundInputs[exchange] || ''}
                        onChange={(e) => setFundInputs(prev => ({ ...prev, [exchange]: e.target.value }))}
                        style={{
                          flex: 1, minWidth: '90px', padding: '7px 10px',
                          borderRadius: '8px', border: '1px solid var(--line)',
                          background: 'var(--panel)', color: 'var(--text)', fontSize: '0.88rem',
                        }}
                      />
                      <select
                        aria-label={'Fund ' + (EXCHANGE_LABELS[exchange] || exchange) + ' currency'}
                        id={'fund-currency-' + exchange}
                        name={'fund_currency_' + exchange}
                        value={currency}
                        onChange={(e) => setFundCurrencies(prev => ({ ...prev, [exchange]: e.target.value }))}
                        style={{
                          padding: '7px 10px', borderRadius: '8px',
                          border: '1px solid var(--line)', background: 'var(--panel)', color: 'var(--text)', fontSize: '0.88rem',
                        }}
                      >
                        <option value={nativeCurrency}>{nativeCurrency}</option>
                        {nativeCurrency !== 'ZAR' && <option value="ZAR">ZAR</option>}
                      </select>
                      <button
                        onClick={() => handleFundPlatform(exchange)}
                        disabled={isLoading}
                        style={{
                          padding: '7px 14px',
                          background: 'linear-gradient(135deg,rgba(34,197,94,0.9),rgba(34,197,94,0.65))',
                          color: '#0b0d14', border: 'none', borderRadius: '999px',
                          fontWeight: 600, cursor: isLoading ? 'wait' : 'pointer', fontSize: '0.85rem',
                        }}
                      >
                        + Fund
                      </button>
                      {funded && (
                        <button
                          onClick={() => handleResetPlatform(exchange)}
                          disabled={isLoading}
                          style={{
                            padding: '7px 12px',
                            background: 'rgba(239,68,68,0.15)', color: 'var(--text)',
                            border: '1px solid rgba(239,68,68,0.35)', borderRadius: '999px',
                            fontWeight: 600, cursor: isLoading ? 'wait' : 'pointer', fontSize: '0.85rem',
                          }}
                        >
                          Reset
                        </button>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}

      {/* Global Paper Wallet */}
      {mode === 'paper' && (
        <div style={{
          background: 'var(--glass)', borderRadius: '12px', padding: '24px',
          marginBottom: '30px', border: '1px solid var(--line)',
        }}>
          <h2 style={{ marginBottom: '8px', fontSize: '1.2rem', color: 'var(--text)' }}>
            Global Paper Wallet
          </h2>
          <p style={{ marginBottom: '16px', color: 'var(--muted)', fontSize: '0.88rem' }}>
            Shared simulation pool. Platform wallets above take priority when funded.
          </p>
          <div style={{ display: 'flex', gap: '24px', flexWrap: 'wrap', alignItems: 'center', marginBottom: '16px' }}>
            <div>
              <div style={{ fontSize: '0.82rem', color: 'var(--muted)', marginBottom: '4px' }}>Available (ZAR)</div>
              <div style={{ fontSize: '1.8rem', fontWeight: 'bold', color: 'var(--text)' }}>{fmtZAR(availableGlobalZar)}</div>
            </div>
            {paperWallet && paperWallet.allocated_funds_zar != null && (
              <div>
                <div style={{ fontSize: '0.82rem', color: 'var(--muted)', marginBottom: '4px' }}>Allocated</div>
                <div style={{ fontSize: '1.2rem', fontWeight: 600, color: 'var(--text)' }}>{fmtZAR(paperWallet.allocated_funds_zar)}</div>
              </div>
            )}
          </div>
          <div style={{ display: 'flex', gap: '10px', flexWrap: 'wrap' }}>
            <input
              type="number"
              min="0"
              step="0.01"
              placeholder="Amount"
              aria-label="Global paper wallet deposit amount"
              id="global-deposit-amount"
              name="global_deposit_amount"
              value={globalDepositAmount}
              onChange={(e) => setGlobalDepositAmount(e.target.value)}
              style={{ padding: '8px 10px', borderRadius: '10px', border: '1px solid var(--line)', background: 'var(--panel)', color: 'var(--text)' }}
            />
            <select
              aria-label="Global paper wallet deposit currency"
              id="global-deposit-currency"
              name="global_deposit_currency"
              value={globalDepositCurrency}
              onChange={(e) => setGlobalDepositCurrency(e.target.value)}
              style={{ padding: '8px 10px', borderRadius: '10px', border: '1px solid var(--line)', background: 'var(--panel)', color: 'var(--text)' }}
            >
              <option value="ZAR">ZAR</option>
              <option value="USDT">USDT</option>
            </select>
            <button
              onClick={handleGlobalDeposit}
              disabled={paperActionLoading}
              style={{
                padding: '8px 14px',
                background: 'linear-gradient(135deg,rgba(34,197,94,0.9),rgba(34,197,94,0.65))',
                color: '#0b0d14', border: 'none', borderRadius: '999px',
                fontWeight: 600, cursor: paperActionLoading ? 'wait' : 'pointer',
              }}
            >
              + Add Funds
            </button>
            <button
              onClick={handleGlobalReset}
              disabled={paperActionLoading}
              style={{
                padding: '8px 14px', background: 'rgba(239,68,68,0.2)', color: 'var(--text)',
                border: '1px solid rgba(239,68,68,0.45)', borderRadius: '999px',
                fontWeight: 600, cursor: paperActionLoading ? 'wait' : 'pointer',
              }}
            >
              Reset
            </button>
          </div>
        </div>
      )}

      {/* Live Exchange Balances */}
      {mode !== 'paper' && walletStatus && walletStatus.live && walletStatus.live.balances && (
        <div style={{ marginBottom: '30px' }}>
          <h2 style={{ marginBottom: '16px', fontSize: '1.3rem', color: 'var(--text)' }}>Live Exchange Balances</h2>
          <div style={{ padding: '20px', background: 'var(--glass)', borderRadius: '12px', border: '1px solid var(--line)' }}>
            <pre style={{ color: 'var(--text)', fontSize: '0.85rem', margin: 0 }}>
              {JSON.stringify(walletStatus.live.balances, null, 2)}
            </pre>
          </div>
        </div>
      )}

      {/* Funding Plans */}
      {fundingPlans.length > 0 && (
        <div style={{ marginBottom: '30px' }}>
          <h2 style={{ marginBottom: '15px', fontSize: '1.3rem', color: 'var(--text)' }}>Active Funding Plans</h2>
          {fundingPlans.map(plan => (
            <div key={plan.plan_id} style={{ background: '#fff3cd', border: '2px solid #ffc107', borderRadius: '8px', padding: '20px', marginBottom: '15px' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'start' }}>
                <div style={{ flex: 1 }}>
                  <div style={{ fontWeight: 'bold', fontSize: '1.1rem', marginBottom: '10px' }}>
                    {plan.to_exchange && plan.to_exchange.toUpperCase()} - R{plan.amount_required && plan.amount_required.toFixed(2)} needed
                  </div>
                  <div style={{ whiteSpace: 'pre-wrap', color: '#856404', marginBottom: '10px' }}>{plan.ai_message}</div>
                  <div style={{ fontSize: '0.85rem', color: '#856404' }}>
                    Bot: {plan.bot_name || 'Not available'} | Created: {new Date(plan.created_at).toLocaleString()}
                  </div>
                </div>
                <button onClick={() => cancelFundingPlan(plan.plan_id)}
                  style={{ background: '#dc3545', color: 'white', border: 'none', padding: '8px 16px', borderRadius: '4px', cursor: 'pointer', fontSize: '0.9rem' }}>
                  Cancel
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Unlocked Exchanges Status */}
      {unlockedExchanges.length > 0 && (
        <div>
          <h2 style={{ marginBottom: '15px', fontSize: '1.3rem', color: 'var(--text)' }}>Unlocked Exchanges</h2>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '12px' }}>
            {unlockedExchanges.map(exchange => (
              <div key={exchange} style={{ background: 'var(--panel)', borderRadius: '10px', padding: '16px', border: '1px solid rgba(34,197,94,0.3)' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <span style={{ fontWeight: 600, fontSize: '0.95rem', color: 'var(--text)' }}>{EXCHANGE_LABELS[exchange] || exchange.toUpperCase()}</span>
                  <span style={{ fontSize: '0.75rem', color: 'var(--success)', fontWeight: 600 }}>Unlocked</span>
                </div>
                <div style={{ marginTop: '8px', fontSize: '0.8rem', color: 'var(--muted)' }}>
                  Native: {EXCHANGE_NATIVE[exchange] || 'USDT'}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};

export default WalletHub;
