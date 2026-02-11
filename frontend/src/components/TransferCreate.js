import React, { useState, useEffect } from 'react';
import { post, get } from '../lib/apiClient';

const TransferCreate = ({ onTransferCreated, onCancel }) => {
  const [formData, setFormData] = useState({
    from_exchange: 'luno',
    to_exchange: 'binance',
    currency: 'BTC',
    amount: '',
    totp_code: '',
    withdrawal_address: '',
    notes: ''
  });
  const [addresses, setAddresses] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState(null);
  const [require2FA, setRequire2FA] = useState(false);

  const exchanges = [
    { id: 'luno', name: 'Luno' },
    { id: 'binance', name: 'Binance' },
    { id: 'kucoin', name: 'KuCoin' },
    { id: 'bybit', name: 'Bybit' },
    { id: 'kraken', name: 'Kraken' },
    { id: 'bitget', name: 'Bitget' },
    { id: 'gate', name: 'Gate.io' }
  ];

  const currencies = ['BTC', 'ETH', 'USDT', 'USDC', 'XRP'];

  useEffect(() => {
    loadAddresses();
    checkSettings();
  }, [formData.to_exchange, formData.currency]);

  const loadAddresses = async () => {
    try {
      const response = await get(`/wallet/addresses/list?exchange=${formData.to_exchange}&currency=${formData.currency}`);
      const approved = response.addresses?.filter(a => a.status === 'approved') || [];
      setAddresses(approved);
    } catch (err) {
      console.error('Error loading addresses:', err);
    }
  };

  const checkSettings = async () => {
    try {
      const response = await get('/user/settings');
      setRequire2FA(response.require_2fa_for_withdrawals || false);
    } catch (err) {
      console.error('Error checking settings:', err);
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    setSuccess(null);

    try {
      // Generate idempotency key
      const idempotency_key = `transfer_${Date.now()}_${Math.random().toString(36).substring(7)}`;

      const transferData = {
        from_exchange: formData.from_exchange,
        to_exchange: formData.to_exchange,
        currency: formData.currency,
        amount: parseFloat(formData.amount),
        idempotency_key,
        notes: formData.notes
      };

      // Add optional fields
      if (formData.totp_code) {
        transferData.totp_code = formData.totp_code;
      }
      if (formData.withdrawal_address) {
        transferData.withdrawal_address = formData.withdrawal_address;
      }

      const response = await post('/wallet/transfers/create', transferData);

      setSuccess('Transfer created successfully!');
      
      // Clear form
      setFormData({
        ...formData,
        amount: '',
        totp_code: '',
        notes: ''
      });

      // Notify parent
      if (onTransferCreated) {
        onTransferCreated(response);
      }

    } catch (err) {
      console.error('Transfer error:', err);
      setError(err.response?.data?.detail || err.message || 'Failed to create transfer');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{
      background: 'var(--panel)',
      border: '1px solid var(--line)',
      borderRadius: '8px',
      padding: '24px',
      maxWidth: '600px',
      margin: '0 auto'
    }}>
      <h3 style={{ marginBottom: '20px', color: 'var(--text)' }}>
        💸 Create Transfer
      </h3>

      {error && (
        <div style={{
          background: 'rgba(231, 76, 60, 0.1)',
          border: '1px solid rgba(231, 76, 60, 0.3)',
          borderRadius: '6px',
          padding: '12px',
          marginBottom: '16px',
          color: '#e74c3c'
        }}>
          ⚠️ {error}
        </div>
      )}

      {success && (
        <div style={{
          background: 'rgba(39, 174, 96, 0.1)',
          border: '1px solid rgba(39, 174, 96, 0.3)',
          borderRadius: '6px',
          padding: '12px',
          marginBottom: '16px',
          color: '#27ae60'
        }}>
          ✅ {success}
        </div>
      )}

      <form onSubmit={handleSubmit}>
        <div style={{ display: 'grid', gap: '16px' }}>
          {/* From Exchange */}
          <div>
            <label style={{ display: 'block', marginBottom: '8px', color: 'var(--text)', fontSize: '0.9rem' }}>
              From Exchange
            </label>
            <select
              value={formData.from_exchange}
              onChange={(e) => setFormData({ ...formData, from_exchange: e.target.value })}
              style={{
                width: '100%',
                padding: '10px',
                background: 'var(--glass)',
                border: '1px solid var(--line)',
                borderRadius: '6px',
                color: 'var(--text)',
                fontSize: '1rem'
              }}
              required
            >
              {exchanges.map(ex => (
                <option key={ex.id} value={ex.id}>{ex.name}</option>
              ))}
            </select>
          </div>

          {/* To Exchange */}
          <div>
            <label style={{ display: 'block', marginBottom: '8px', color: 'var(--text)', fontSize: '0.9rem' }}>
              To Exchange
            </label>
            <select
              value={formData.to_exchange}
              onChange={(e) => setFormData({ ...formData, to_exchange: e.target.value })}
              style={{
                width: '100%',
                padding: '10px',
                background: 'var(--glass)',
                border: '1px solid var(--line)',
                borderRadius: '6px',
                color: 'var(--text)',
                fontSize: '1rem'
              }}
              required
            >
              {exchanges.map(ex => (
                <option key={ex.id} value={ex.id}>{ex.name}</option>
              ))}
            </select>
          </div>

          {/* Currency */}
          <div>
            <label style={{ display: 'block', marginBottom: '8px', color: 'var(--text)', fontSize: '0.9rem' }}>
              Currency
            </label>
            <select
              value={formData.currency}
              onChange={(e) => setFormData({ ...formData, currency: e.target.value })}
              style={{
                width: '100%',
                padding: '10px',
                background: 'var(--glass)',
                border: '1px solid var(--line)',
                borderRadius: '6px',
                color: 'var(--text)',
                fontSize: '1rem'
              }}
              required
            >
              {currencies.map(curr => (
                <option key={curr} value={curr}>{curr}</option>
              ))}
            </select>
          </div>

          {/* Amount */}
          <div>
            <label style={{ display: 'block', marginBottom: '8px', color: 'var(--text)', fontSize: '0.9rem' }}>
              Amount
            </label>
            <input
              type="number"
              step="0.00000001"
              value={formData.amount}
              onChange={(e) => setFormData({ ...formData, amount: e.target.value })}
              placeholder="0.00"
              style={{
                width: '100%',
                padding: '10px',
                background: 'var(--glass)',
                border: '1px solid var(--line)',
                borderRadius: '6px',
                color: 'var(--text)',
                fontSize: '1rem'
              }}
              required
            />
          </div>

          {/* Withdrawal Address (Optional) */}
          {addresses.length > 0 && (
            <div>
              <label style={{ display: 'block', marginBottom: '8px', color: 'var(--text)', fontSize: '0.9rem' }}>
                Withdrawal Address (Optional - uses deposit address if empty)
              </label>
              <select
                value={formData.withdrawal_address}
                onChange={(e) => setFormData({ ...formData, withdrawal_address: e.target.value })}
                style={{
                  width: '100%',
                  padding: '10px',
                  background: 'var(--glass)',
                  border: '1px solid var(--line)',
                  borderRadius: '6px',
                  color: 'var(--text)',
                  fontSize: '1rem'
                }}
              >
                <option value="">Auto (use deposit address)</option>
                {addresses.map(addr => (
                  <option key={addr.address_id} value={addr.address}>
                    {addr.label} - {addr.address.substring(0, 12)}...
                  </option>
                ))}
              </select>
            </div>
          )}

          {/* 2FA Code */}
          {require2FA && (
            <div>
              <label style={{ display: 'block', marginBottom: '8px', color: 'var(--text)', fontSize: '0.9rem' }}>
                2FA Code (Required) *
              </label>
              <input
                type="text"
                value={formData.totp_code}
                onChange={(e) => setFormData({ ...formData, totp_code: e.target.value })}
                placeholder="Enter 6-digit code"
                maxLength="6"
                style={{
                  width: '100%',
                  padding: '10px',
                  background: 'var(--glass)',
                  border: '1px solid var(--line)',
                  borderRadius: '6px',
                  color: 'var(--text)',
                  fontSize: '1rem',
                  fontFamily: 'monospace',
                  letterSpacing: '0.2em'
                }}
                required={require2FA}
              />
            </div>
          )}

          {/* Notes */}
          <div>
            <label style={{ display: 'block', marginBottom: '8px', color: 'var(--text)', fontSize: '0.9rem' }}>
              Notes (Optional)
            </label>
            <textarea
              value={formData.notes}
              onChange={(e) => setFormData({ ...formData, notes: e.target.value })}
              placeholder="Optional notes about this transfer"
              rows="2"
              style={{
                width: '100%',
                padding: '10px',
                background: 'var(--glass)',
                border: '1px solid var(--line)',
                borderRadius: '6px',
                color: 'var(--text)',
                fontSize: '1rem',
                resize: 'vertical'
              }}
            />
          </div>

          {/* Buttons */}
          <div style={{ display: 'flex', gap: '12px', marginTop: '8px' }}>
            <button
              type="submit"
              disabled={loading}
              style={{
                flex: 1,
                padding: '12px 24px',
                background: loading ? 'var(--muted)' : 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
                border: 'none',
                borderRadius: '6px',
                color: 'white',
                fontSize: '1rem',
                fontWeight: '600',
                cursor: loading ? 'not-allowed' : 'pointer',
                opacity: loading ? 0.6 : 1
              }}
            >
              {loading ? 'Creating...' : 'Create Transfer'}
            </button>
            
            {onCancel && (
              <button
                type="button"
                onClick={onCancel}
                disabled={loading}
                style={{
                  padding: '12px 24px',
                  background: 'transparent',
                  border: '1px solid var(--line)',
                  borderRadius: '6px',
                  color: 'var(--text)',
                  fontSize: '1rem',
                  cursor: loading ? 'not-allowed' : 'pointer'
                }}
              >
                Cancel
              </button>
            )}
          </div>
        </div>
      </form>
    </div>
  );
};

export default TransferCreate;
