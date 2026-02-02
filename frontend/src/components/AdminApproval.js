import React, { useState, useEffect } from 'react';
import { get, post } from '../lib/apiClient';
import { useRealtimeEvent } from '../hooks/useRealtime';

const AdminApproval = () => {
  const [pendingTransfers, setPendingTransfers] = useState([]);
  const [pendingAddresses, setPendingAddresses] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [tab, setTab] = useState('transfers'); // transfers or addresses

  useEffect(() => {
    loadPending();
  }, [tab]);

  const loadPending = async () => {
    try {
      setLoading(true);
      setError(null);

      if (tab === 'transfers') {
        const response = await get('/wallet/admin/transfers/pending');
        setPendingTransfers(response.pending_transfers || []);
      } else {
        const response = await get('/wallet/admin/addresses/pending');
        setPendingAddresses(response.pending_addresses || []);
      }

      setLoading(false);
    } catch (err) {
      console.error('Error loading pending:', err);
      setError(err.message || 'Failed to load pending items');
      setLoading(false);
    }
  };

  // Real-time updates
  useRealtimeEvent('transfer_updated', () => {
    if (tab === 'transfers') loadPending();
  }, [tab]);

  const approveTransfer = async (transferId) => {
    try {
      await post(`/wallet/admin/transfers/${transferId}/approve`, {});
      loadPending();
    } catch (err) {
      alert('Failed to approve transfer: ' + (err.message || 'Unknown error'));
    }
  };

  const rejectTransfer = async (transferId) => {
    const reason = prompt('Enter rejection reason:');
    if (!reason) return;

    try {
      await post(`/wallet/admin/transfers/${transferId}/reject`, { rejection_reason: reason });
      loadPending();
    } catch (err) {
      alert('Failed to reject transfer: ' + (err.message || 'Unknown error'));
    }
  };

  const approveAddress = async (addressId) => {
    try {
      await post('/wallet/admin/addresses/approve', { address_id: addressId });
      loadPending();
    } catch (err) {
      alert('Failed to approve address: ' + (err.message || 'Unknown error'));
    }
  };

  const rejectAddress = async (addressId) => {
    const reason = prompt('Enter rejection reason:');
    if (!reason) return;

    try {
      await post('/wallet/admin/addresses/reject', { address_id: addressId, reason });
      loadPending();
    } catch (err) {
      alert('Failed to reject address: ' + (err.message || 'Unknown error'));
    }
  };

  return (
    <div style={{
      background: 'var(--panel)',
      border: '1px solid var(--line)',
      borderRadius: '8px',
      padding: '20px'
    }}>
      <h3 style={{ marginBottom: '20px', color: 'var(--text)' }}>
        🔐 Admin Approvals
      </h3>

      {/* Tabs */}
      <div style={{ 
        display: 'flex', 
        gap: '8px', 
        marginBottom: '20px',
        borderBottom: '1px solid var(--line)',
        paddingBottom: '12px'
      }}>
        <button
          onClick={() => setTab('transfers')}
          style={{
            padding: '8px 16px',
            background: tab === 'transfers' ? 'var(--glass)' : 'transparent',
            border: tab === 'transfers' ? '1px solid var(--line)' : '1px solid transparent',
            borderRadius: '6px',
            color: 'var(--text)',
            fontSize: '0.9rem',
            cursor: 'pointer'
          }}
        >
          Transfers ({pendingTransfers.length})
        </button>
        <button
          onClick={() => setTab('addresses')}
          style={{
            padding: '8px 16px',
            background: tab === 'addresses' ? 'var(--glass)' : 'transparent',
            border: tab === 'addresses' ? '1px solid var(--line)' : '1px solid transparent',
            borderRadius: '6px',
            color: 'var(--text)',
            fontSize: '0.9rem',
            cursor: 'pointer'
          }}
        >
          Addresses ({pendingAddresses.length})
        </button>
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

      {loading ? (
        <div style={{ padding: '20px', textAlign: 'center', color: 'var(--muted)' }}>
          Loading...
        </div>
      ) : (
        <>
          {/* Transfers Tab */}
          {tab === 'transfers' && (
            pendingTransfers.length === 0 ? (
              <div style={{
                padding: '40px',
                textAlign: 'center',
                color: 'var(--muted)',
                background: 'var(--glass)',
                borderRadius: '8px'
              }}>
                ✅ No pending transfers
              </div>
            ) : (
              <div style={{ display: 'grid', gap: '12px' }}>
                {pendingTransfers.map(transfer => (
                  <div
                    key={transfer.transfer_id}
                    style={{
                      background: 'var(--glass)',
                      border: '1px solid var(--line)',
                      borderRadius: '8px',
                      padding: '16px'
                    }}
                  >
                    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '12px' }}>
                      <div>
                        <div style={{ fontSize: '1.1rem', fontWeight: '600', color: 'var(--text)', marginBottom: '4px' }}>
                          {transfer.amount} {transfer.currency}
                        </div>
                        <div style={{ fontSize: '0.85rem', color: 'var(--muted)' }}>
                          {transfer.from_exchange} → {transfer.to_exchange}
                        </div>
                        <div style={{ fontSize: '0.75rem', color: 'var(--muted)', marginTop: '4px' }}>
                          User: {transfer.user_id.substring(0, 8)}...
                        </div>
                      </div>
                      <div style={{ textAlign: 'right' }}>
                        <div style={{ fontSize: '0.85rem', color: 'var(--muted)' }}>
                          {new Date(transfer.created_at).toLocaleString()}
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

                    <div style={{ display: 'flex', gap: '8px', marginTop: '12px' }}>
                      <button
                        onClick={() => approveTransfer(transfer.transfer_id)}
                        style={{
                          flex: 1,
                          padding: '10px',
                          background: 'linear-gradient(135deg, #27ae60, #2ecc71)',
                          border: 'none',
                          borderRadius: '6px',
                          color: 'white',
                          fontSize: '0.9rem',
                          fontWeight: '600',
                          cursor: 'pointer'
                        }}
                      >
                        ✅ Approve
                      </button>
                      <button
                        onClick={() => rejectTransfer(transfer.transfer_id)}
                        style={{
                          flex: 1,
                          padding: '10px',
                          background: 'transparent',
                          border: '1px solid #e74c3c',
                          borderRadius: '6px',
                          color: '#e74c3c',
                          fontSize: '0.9rem',
                          cursor: 'pointer'
                        }}
                      >
                        ❌ Reject
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )
          )}

          {/* Addresses Tab */}
          {tab === 'addresses' && (
            pendingAddresses.length === 0 ? (
              <div style={{
                padding: '40px',
                textAlign: 'center',
                color: 'var(--muted)',
                background: 'var(--glass)',
                borderRadius: '8px'
              }}>
                ✅ No pending addresses
              </div>
            ) : (
              <div style={{ display: 'grid', gap: '12px' }}>
                {pendingAddresses.map(addr => (
                  <div
                    key={addr.address_id}
                    style={{
                      background: 'var(--glass)',
                      border: '1px solid var(--line)',
                      borderRadius: '8px',
                      padding: '16px'
                    }}
                  >
                    <div style={{ marginBottom: '12px' }}>
                      <div style={{ fontSize: '1.1rem', fontWeight: '600', color: 'var(--text)', marginBottom: '4px' }}>
                        {addr.label || 'Unnamed Address'}
                      </div>
                      <div style={{ fontSize: '0.85rem', color: 'var(--muted)' }}>
                        {addr.exchange} - {addr.currency}
                      </div>
                      <div style={{ 
                        fontSize: '0.75rem', 
                        color: 'var(--muted)', 
                        marginTop: '8px',
                        fontFamily: 'monospace',
                        wordBreak: 'break-all',
                        background: 'var(--panel)',
                        padding: '8px',
                        borderRadius: '4px'
                      }}>
                        {addr.address}
                      </div>
                      {addr.tag && (
                        <div style={{ fontSize: '0.75rem', color: 'var(--muted)', marginTop: '4px' }}>
                          Tag: {addr.tag}
                        </div>
                      )}
                      {addr.network && (
                        <div style={{ fontSize: '0.75rem', color: 'var(--muted)', marginTop: '4px' }}>
                          Network: {addr.network}
                        </div>
                      )}
                      <div style={{ fontSize: '0.75rem', color: 'var(--muted)', marginTop: '8px' }}>
                        User: {addr.user_id.substring(0, 8)}... | {new Date(addr.created_at).toLocaleString()}
                      </div>
                    </div>

                    <div style={{ display: 'flex', gap: '8px' }}>
                      <button
                        onClick={() => approveAddress(addr.address_id)}
                        style={{
                          flex: 1,
                          padding: '10px',
                          background: 'linear-gradient(135deg, #27ae60, #2ecc71)',
                          border: 'none',
                          borderRadius: '6px',
                          color: 'white',
                          fontSize: '0.9rem',
                          fontWeight: '600',
                          cursor: 'pointer'
                        }}
                      >
                        ✅ Approve
                      </button>
                      <button
                        onClick={() => rejectAddress(addr.address_id)}
                        style={{
                          flex: 1,
                          padding: '10px',
                          background: 'transparent',
                          border: '1px solid #e74c3c',
                          borderRadius: '6px',
                          color: '#e74c3c',
                          fontSize: '0.9rem',
                          cursor: 'pointer'
                        }}
                      >
                        ❌ Reject
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )
          )}
        </>
      )}
    </div>
  );
};

export default AdminApproval;
