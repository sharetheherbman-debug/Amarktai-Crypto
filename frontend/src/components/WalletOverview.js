import React, { useState, useEffect } from 'react';
import { get, notifyError } from '../lib/apiClient';

const WalletOverview = () => {
  const [balances, setBalances] = useState(null);
  const [requirements, setRequirements] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadWalletData();
    const interval = setInterval(loadWalletData, 30000);
    return () => clearInterval(interval);
  }, []);

  const loadWalletData = async () => {
    try {
      const [balancesRes, requirementsRes] = await Promise.all([
        get('/wallet/balances'),
        get('/wallet/requirements')
      ]);

      setBalances(balancesRes);
      setRequirements(requirementsRes);
      setLoading(false);
    } catch (err) {
      console.error('Wallet data load error:', err);
      notifyError(err);
      setLoading(false);
    }
  };

  if (loading) {
    return (
      <div style={{ padding: '20px', textAlign: 'center', color: 'var(--muted)' }}>
        Loading wallet data...
      </div>
    );
  }

  const masterWallet = balances?.master_wallet || {};
  const exchanges = requirements?.requirements || {};
  const summary = requirements?.summary || {};
  const totalEquity = masterWallet.total_zar || 0;
  const requiredFunds = summary.required_funds_zar ?? Object.values(exchanges).reduce((sum, ex) => sum + (ex.required || 0), 0);
  const reservedFunds = summary.reserved_funds_zar ?? 0;
  const availableWallet = summary.available_wallet_zar ?? totalEquity;
  const shortfall = summary.shortfall_zar ?? Math.max(0, requiredFunds - availableWallet);
  const free = availableWallet - requiredFunds;

  return (
    <div style={{ display: 'grid', gap: '16px' }}>
      {/* Wallet Overview Card */}
      <div style={{ 
        background: 'var(--panel)', 
        border: '1px solid var(--line)', 
        borderRadius: '8px', 
        padding: '20px' 
      }}>
        <h3 style={{ marginBottom: '16px', color: 'var(--text)', fontSize: '1.1rem' }}>
          💰 Wallet Overview
        </h3>
        
        <div style={{ marginBottom: '20px' }}>
          <div style={{ fontSize: '0.85rem', color: 'var(--muted)', marginBottom: '4px' }}>
            Total Equity (All Exchanges)
          </div>
          <div style={{ fontSize: '2rem', fontWeight: 'bold', color: 'var(--text)' }}>
            R{totalEquity.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
          </div>
        </div>

        <div style={{ 
          display: 'grid', 
          gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', 
          gap: '12px',
          marginBottom: '16px'
        }}>
          <div style={{ padding: '12px', background: 'var(--glass)', borderRadius: '6px' }}>
            <div style={{ fontSize: '0.75rem', color: 'var(--muted)', marginBottom: '4px' }}>
              🏦 Master (Luno)
            </div>
            <div style={{ fontSize: '1.1rem', fontWeight: '600', color: 'var(--text)' }}>
              R{(masterWallet.total_zar || 0).toLocaleString()}
            </div>
          </div>

          {Object.entries(exchanges).length > 0 && Object.entries(exchanges).map(([exchange, data]) => (
            <div key={exchange} style={{ padding: '12px', background: 'var(--glass)', borderRadius: '6px' }}>
              <div style={{ fontSize: '0.75rem', color: 'var(--muted)', marginBottom: '4px' }}>
                {exchange === 'binance' && '🌍 Binance'}
                {exchange === 'kucoin' && '🌐 KuCoin'}
                {exchange === 'bybit' && '🟠 Bybit'}
                {exchange === 'kraken' && '🟣 Kraken'}
                {exchange === 'bitget' && '🔵 Bitget'}
                {exchange === 'gate' && '⚪ Gate.io'}
                {exchange === 'luno' && '🏦 Luno'}
              </div>
              <div style={{ fontSize: '1.1rem', fontWeight: '600', color: 'var(--text)' }}>
                R{(data.available || 0).toLocaleString()}
              </div>
              <div style={{ fontSize: '0.7rem', color: data.health === 'healthy' ? 'var(--success)' : data.health === 'critical' ? 'var(--error)' : 'var(--muted)' }}>
                {data.bots || 0} bots
              </div>
            </div>
          ))}
        </div>

        <div style={{ 
          display: 'grid', 
          gridTemplateColumns: 'repeat(2, 1fr)', 
          gap: '12px',
          padding: '16px',
          background: 'var(--glass)',
          borderRadius: '6px'
        }}>
            <div>
              <div style={{ fontSize: '0.75rem', color: 'var(--muted)' }}>Required Funds</div>
              <div style={{ fontSize: '1.3rem', fontWeight: 'bold', color: 'var(--accent)' }}>
                R{Number(requiredFunds || 0).toLocaleString()}
              </div>
              <div style={{ fontSize: '0.75rem', color: 'var(--muted)' }}>Reserved: R{Number(reservedFunds || 0).toLocaleString()}</div>
            </div>
            <div>
              <div style={{ fontSize: '0.75rem', color: 'var(--muted)' }}>Available / Shortfall</div>
              <div style={{ fontSize: '1.3rem', fontWeight: 'bold', color: 'var(--success)' }}>
                R{Math.max(0, free).toLocaleString()}
              </div>
              <div style={{ fontSize: '0.75rem', color: shortfall > 0 ? 'var(--error)' : 'var(--muted)' }}>
                Shortfall: R{Number(shortfall || 0).toLocaleString()}
              </div>
            </div>
        </div>

        {masterWallet.error && (
          <div style={{ 
            marginTop: '12px', 
            padding: '12px', 
            background: 'rgba(255, 193, 7, 0.1)', 
            border: '1px solid rgba(255, 193, 7, 0.3)',
            borderRadius: '6px',
            color: 'var(--text)',
            fontSize: '0.85rem'
          }}>
            ⚠️ {masterWallet.error}
          </div>
        )}
      </div>

      {/* Exchange Health Badges */}
      {Object.keys(exchanges).length > 0 && (
        <div style={{ 
          background: 'var(--panel)', 
          border: '1px solid var(--line)', 
          borderRadius: '8px', 
          padding: '16px' 
        }}>
          <h4 style={{ marginBottom: '12px', color: 'var(--text)', fontSize: '0.95rem' }}>
            Exchange Status
          </h4>
          <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
            {Object.entries(exchanges).map(([exchange, data]) => (
              <div key={exchange} style={{
                padding: '8px 12px',
                background: 'var(--glass)',
                border: `1px solid ${data.health === 'healthy' ? 'var(--success)' : data.health === 'critical' ? 'var(--error)' : 'var(--muted)'}`,
                borderRadius: '6px',
                fontSize: '0.8rem',
                display: 'flex',
                alignItems: 'center',
                gap: '6px'
              }}>
                <span>
                  {exchange === 'binance' && '🌍'}
                  {exchange === 'kucoin' && '🌐'}
                  {exchange === 'bybit' && '🟠'}
                  {exchange === 'kraken' && '🟣'}
                  {exchange === 'bitget' && '🔵'}
                  {exchange === 'gate' && '⚪'}
                  {exchange === 'luno' && '🏦'}
                </span>
                <span style={{ color: 'var(--text)', fontWeight: '600' }}>
                  {exchange.toUpperCase()}
                </span>
                <span style={{ color: data.health === 'healthy' ? 'var(--success)' : data.health === 'critical' ? 'var(--error)' : 'var(--muted)' }}>
                  {data.health === 'healthy' && '✅'}
                  {data.health === 'adequate' && '✔️'}
                  {data.health === 'warning' && '⚠️'}
                  {data.health === 'critical' && '🚨'}
                  {!data.health && '❓'}
                </span>
                <span style={{ color: 'var(--muted)' }}>
                  {data.bots || 0}/{10} bots
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};

export default WalletOverview;
