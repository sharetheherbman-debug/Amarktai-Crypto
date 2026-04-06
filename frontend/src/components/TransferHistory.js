import React, { useState, useEffect } from 'react';
import { get, post } from '../lib/apiClient';
import { useRealtimeEvent } from '../hooks/useRealtime';

const TransferHistory = () => {
  const [transfers, setTransfers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [filter, setFilter] = useState('all'); // all, pending, completed, failed

  useEffect(() => {
    loadTransfers();
  }, [filter]);

  const loadTransfers = async () => {
    try {
      setLoading(true);
      setError(null);
      
      let url = '/wallet/transfers';
      if (filter !== 'all') {
        const stateMap = {
          'pending': 'requested,needs_approval,approved,queued,broadcast',
          'completed': 'confirmed',
          'failed': 'failed,cancelled'
        };
        url += `?state=${stateMap[filter]}`;
      }
      
      const response = await get(url);
      setTransfers(response.transfers || []);
      setLoading(false);
    } catch (err) {
      console.error('Error loading transfers:', err);
      setError(err.message || 'Failed to load transfers');
      setLoading(false);
    }
  };

  // Real-time update on transfer events
  useRealtimeEvent('transfer_updated', (data) => {
    loadTransfers();
  }, []);

  const getStateColor = (state) => {
    const colors = {
      'requested': '#3498db',
      'needs_approval': '#f39c12',
      'approved': '#2ecc71',
      'queued': '#9b59b6',
      'broadcast': '#e67e22',
      'confirmed': '#27ae60',
      'failed': '#e74c3c',
      'cancelled': '#95a5a6'
    };
    return colors[state] || '#95a5a6';
  };

  const getStateIcon = (state) => {
    const icons = {
      'requested': '📝',
      'needs_approval': '⏳',
      'approved': '✅',
      'queued': '📋',
      'broadcast': '📡',
      'confirmed': '✔️',
      'failed': '❌',
      'cancelled': '🚫'
    };
    return icons[state] || '❓';
  };

  const cancelTransfer = async (transferId) => {
    if (!window.confirm('Are you sure you want to cancel this transfer?')) {
      return;
    }

    try {
      await post(`/wallet/transfers/${transferId}/cancel`, {});
      loadTransfers();
    } catch (err) {
      alert('Failed to cancel transfer: ' + (err.message || 'Unknown error'));
    }
  };

  if (loading && transfers.length === 0) {
    return (
      <div style={{ padding: '20px', textAlign: 'center', color: 'var(--muted)' }}>
        Loading transfers...
      </div>
    );
  }

  return (
    <div style={{ padding: '0' }}>
      {/* Filter Tabs */}
      <div style={{ 
        display: 'flex', 
        gap: '8px', 
        marginBottom: '20px',
        borderBottom: '1px solid var(--line)',
        paddingBottom: '12px'
      }}>
        {['all', 'pending', 'completed', 'failed'].map(f => (
          <button
            key={f}
            onClick={() => setFilter(f)}
            style={{
              padding: '8px 16px',
              background: filter === f ? 'var(--glass)' : 'transparent',
              border: filter === f ? '1px solid var(--line)' : '1px solid transparent',
              borderRadius: '6px',
              color: 'var(--text)',
              fontSize: '0.9rem',
              cursor: 'pointer',
              textTransform: 'capitalize'
            }}
          >
            {f}
          </button>
        ))}
      </div>

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

      {transfers.length === 0 ? (
        <div style={{
          padding: '40px',
          textAlign: 'center',
          color: 'var(--muted)',
          background: 'var(--glass)',
          borderRadius: '8px',
          border: '1px dashed var(--line)'
        }}>
          No transfers found
        </div>
      ) : (
        <div style={{ display: 'grid', gap: '12px' }}>
          {transfers.map(transfer => (
            <div
              key={transfer.transfer_id}
              style={{
                background: 'var(--glass)',
                border: '1px solid var(--line)',
                borderRadius: '8px',
                padding: '16px'
              }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'start', marginBottom: '12px' }}>
                <div>
                  <div style={{ 
                    display: 'inline-block',
                    padding: '4px 10px',
                    background: getStateColor(transfer.state) + '20',
                    border: `1px solid ${getStateColor(transfer.state)}`,
                    borderRadius: '4px',
                    color: getStateColor(transfer.state),
                    fontSize: '0.8rem',
                    fontWeight: '600',
                    marginBottom: '8px'
                  }}>
                    {getStateIcon(transfer.state)} {String(transfer.state ?? '').replace('_', ' ').toUpperCase()}
                  </div>
                  <div style={{ fontSize: '0.85rem', color: 'var(--muted)' }}>
                    {new Date(transfer.created_at).toLocaleString()}
                  </div>
                </div>
                <div style={{ textAlign: 'right' }}>
                  <div style={{ fontSize: '1.2rem', fontWeight: '600', color: 'var(--text)' }}>
                    {transfer.amount} {transfer.currency}
                  </div>
                  <div style={{ fontSize: '0.85rem', color: 'var(--muted)' }}>
                    {transfer.from_exchange} → {transfer.to_exchange}
                  </div>
                </div>
              </div>

              {transfer.notes && (
                <div style={{ 
                  padding: '8px 12px',
                  background: 'var(--panel)',
                  borderRadius: '4px',
                  fontSize: '0.85rem',
                  color: 'var(--muted)',
                  marginBottom: '12px'
                }}>
                  📝 {transfer.notes}
                </div>
              )}

              {transfer.error_message && (
                <div style={{
                  padding: '8px 12px',
                  background: 'rgba(231, 76, 60, 0.1)',
                  borderRadius: '4px',
                  fontSize: '0.85rem',
                  color: '#e74c3c',
                  marginBottom: '12px'
                }}>
                  ⚠️ {transfer.error_message}
                </div>
              )}

              {transfer.withdrawal_txid && (
                <div style={{
                  padding: '8px 12px',
                  background: 'var(--panel)',
                  borderRadius: '4px',
                  fontSize: '0.75rem',
                  color: 'var(--muted)',
                  fontFamily: 'monospace',
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                  marginBottom: '12px'
                }}>
                  TX: {transfer.withdrawal_txid}
                </div>
              )}

              <div style={{ display: 'flex', gap: '8px', marginTop: '12px' }}>
                {(transfer.state === 'requested' || transfer.state === 'needs_approval') && (
                  <button
                    onClick={() => cancelTransfer(transfer.transfer_id)}
                    style={{
                      padding: '6px 12px',
                      background: 'transparent',
                      border: '1px solid #e74c3c',
                      borderRadius: '4px',
                      color: '#e74c3c',
                      fontSize: '0.85rem',
                      cursor: 'pointer'
                    }}
                  >
                    Cancel
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};

export default TransferHistory;
