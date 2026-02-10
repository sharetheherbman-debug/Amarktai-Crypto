import React, { useState, useEffect } from 'react';
import './APIKeySettings.css';
import { ALL_PROVIDERS, PLATFORM_CONFIG } from '../constants/platforms';
import realtimeClient from '../lib/realtime';

const APIKeySettings = () => {
  // Build providers list from platform config (10 providers: 3 AI + 7 exchanges)
  const PROVIDERS = ALL_PROVIDERS.map(id => {
    const config = PLATFORM_CONFIG[id];
    return {
      id: config.id,
      name: config.displayName || config.name,
      icon: config.icon,
      fields: config.requiredKeyFields
    };
  });

  const [providers, setProviders] = useState([]);
  const [formData, setFormData] = useState({});
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState({ type: '', text: '' });
  const [showKeys, setShowKeys] = useState({});
  const [requestCounter, setRequestCounter] = useState(0); // Track request order
  
  const token = localStorage.getItem('token');
  
  useEffect(() => {
    fetchAllProviders();
    
    // Subscribe to realtime API key events
    const unsubscribeKeySaved = realtimeClient.on('key_saved', (data) => {
      console.log('🔑 Realtime: Key saved', data);
      fetchAllProviders(); // Refresh on key save
    });
    
    const unsubscribeKeyTested = realtimeClient.on('key_tested', (data) => {
      console.log('🔑 Realtime: Key tested', data);
      fetchAllProviders(); // Refresh on key test
    });
    
    const unsubscribeKeyDeleted = realtimeClient.on('key_deleted', (data) => {
      console.log('🔑 Realtime: Key deleted', data);
      fetchAllProviders(); // Refresh on key delete
    });
    
    // Cleanup subscriptions on unmount
    return () => {
      unsubscribeKeySaved();
      unsubscribeKeyTested();
      unsubscribeKeyDeleted();
    };
  }, []);
  
  const fetchAllProviders = async () => {
    try {
      const response = await fetch('/api/keys/status', {
        headers: { 'Authorization': `Bearer ${token}` }
      });
      
      if (response.status === 401 || response.status === 403) {
        showMessage('error', 'Session expired. Please login again.');
        setTimeout(() => {
          localStorage.removeItem('token');
          window.location.href = '/login';
        }, 2000);
        return;
      }
      
      if (response.ok) {
        const data = await response.json();
        const statusMap = data.status_map || {};
        const providerStatuses = PROVIDERS.map(provider => {
          const statusInfo = statusMap[provider.id] || {};
          const status = statusInfo.status || 'not_configured';
          return {
            provider: provider.id,
            status,
            status_display: getStatusDisplay(status, statusInfo.last_test_error),
            last_test_error: statusInfo.last_test_error,
            updated_at: statusInfo.updated_at,
            last_tested_at: statusInfo.last_tested_at
          };
        });
        setProviders(providerStatuses);
      } else {
        console.error('Failed to fetch providers');
      }
    } catch (error) {
      console.error('Error fetching providers:', error);
    }
  };
  
  const handleInputChange = (provider, field, value) => {
    setFormData(prev => ({
      ...prev,
      [provider]: {
        ...prev[provider],
        [field]: value
      }
    }));
  };
  
  const saveApiKey = async (providerId) => {
    const data = formData[providerId];
    if (!data || !data.api_key || data.api_key.trim() === '') {
      showMessage('error', 'API key cannot be empty');
      return;
    }
    
    setLoading(true);
    try {
      const response = await fetch('/api/keys/save', {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          provider: providerId,
          api_key: data.api_key,
          api_secret: data.api_secret || null,
          passphrase: data.passphrase || null
        })
      });
      
      if (response.status === 401 || response.status === 403) {
        showMessage('error', 'Session expired. Please login again.');
        setTimeout(() => {
          localStorage.removeItem('token');
          window.location.href = '/login';
        }, 2000);
        return;
      }
      
      const result = await response.json();
      
      if (response.ok) {
        showMessage('success', result.message || 'API key saved successfully');
        setFormData(prev => ({ ...prev, [providerId]: {} }));
        fetchAllProviders();
      } else {
        showMessage('error', result.detail || 'Failed to save API key');
      }
    } catch (error) {
      showMessage('error', 'Error saving API key: ' + error.message);
    } finally {
      setLoading(false);
    }
  };
  
  const testApiKey = async (providerId) => {
    setLoading(true);
    
    // Optimistic update: immediately show testing state
    setProviders(prev => prev.map(p => 
      p.provider === providerId 
        ? { ...p, status: 'testing', status_display: 'Testing...' }
        : p
    ));
    
    try {
      const response = await fetch('/api/keys/test', {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ provider: providerId })
      });
      
      if (response.status === 401 || response.status === 403) {
        showMessage('error', 'Session expired. Please login again.');
        setTimeout(() => {
          localStorage.removeItem('token');
          window.location.href = '/login';
        }, 2000);
        return;
      }
      
      const result = await response.json();
      
      if (result.success) {
        // Optimistic update: immediately set to configured_valid before refetch
        setProviders(prev => prev.map(p => 
          p.provider === providerId 
            ? { ...p, status: 'configured_valid', status_display: 'Valid ✅' }
            : p
        ));
        showMessage('success', result.message || 'API key test passed ✅');
      } else {
        // Immediately set to configured_invalid
        setProviders(prev => prev.map(p => 
          p.provider === providerId 
            ? { ...p, status: 'configured_invalid', status_display: 'Invalid ❌', last_test_error: result.message }
            : p
        ));
        showMessage('error', result.message || 'API key test failed ❌');
      }
      
      // Increment counter and fetch to verify
      const currentCounter = requestCounter + 1;
      setRequestCounter(currentCounter);
      
      // Delayed refetch to confirm persisted state (don't overwrite optimistic update immediately)
      setTimeout(() => fetchAllProviders(), 500);
    } catch (error) {
      showMessage('error', 'Error testing API key: ' + error.message);
      // Revert optimistic update on error
      fetchAllProviders();
    } finally {
      setLoading(false);
    }
  };
  
  const deleteApiKey = async (providerId, providerName) => {
    if (!window.confirm(`Delete your ${providerName} API key?`)) {
      return;
    }
    
    setLoading(true);
    
    // Optimistic update: immediately set to not_configured
    setProviders(prev => prev.map(p => 
      p.provider === providerId 
        ? { ...p, status: 'not_configured', status_display: 'Not configured' }
        : p
    ));
    
    try {
      const response = await fetch(`/api/keys/${providerId}`, {
        method: 'DELETE',
        headers: { 'Authorization': `Bearer ${token}` }
      });
      
      const result = await response.json();
      
      if (response.ok) {
        showMessage('success', result.message || 'API key deleted successfully');
        // Refresh to confirm
        setTimeout(() => fetchAllProviders(), 300);
      } else {
        showMessage('error', result.message || 'Failed to delete API key');
        // Revert on error
        fetchAllProviders();
      }
    } catch (error) {
      showMessage('error', 'Error deleting API key: ' + error.message);
      // Revert on error
      fetchAllProviders();
    } finally {
      setLoading(false);
    }
  };
  
  const showMessage = (type, text) => {
    setMessage({ type, text });
    setTimeout(() => setMessage({ type: '', text: '' }), 5000);
  };
  
  const getStatusColor = (status) => {
    // Normalize status: handle both old and new values
    const normalizedStatus = status?.toLowerCase();
    
    if (normalizedStatus === 'test_ok' || normalizedStatus === 'configured_valid') {
      return '#22c55e'; // Green
    } else if (normalizedStatus === 'test_failed' || normalizedStatus === 'configured_invalid') {
      return '#ef4444'; // Red
    } else if (normalizedStatus === 'saved_untested' || normalizedStatus === 'configured_untested') {
      return '#f59e0b'; // Amber/Warning
    } else {
      return '#6b7280'; // Gray for not_configured
    }
  };
  
  const getStatusIcon = (status) => {
    // Normalize status: handle both old and new values
    const normalizedStatus = status?.toLowerCase();
    
    if (normalizedStatus === 'test_ok' || normalizedStatus === 'configured_valid') {
      return '✅';
    } else if (normalizedStatus === 'test_failed' || normalizedStatus === 'configured_invalid') {
      return '❌';
    } else if (normalizedStatus === 'saved_untested' || normalizedStatus === 'configured_untested') {
      return '⚠️';
    } else {
      return '⚪';
    }
  };

  const getStatusDisplay = (status, lastTestError) => {
    const normalizedStatus = status?.toLowerCase();
    if (normalizedStatus === 'configured_valid') {
      return 'Valid ✅';
    }
    if (normalizedStatus === 'configured_invalid') {
      return lastTestError ? `Invalid ❌ - ${lastTestError}` : 'Invalid ❌';
    }
    if (normalizedStatus === 'configured_untested') {
      return 'Configured (untested)';
    }
    if (normalizedStatus === 'configured_rate_limited') {
      return 'Rate limited ⏱️';
    }
    if (normalizedStatus === 'testing') {
      return 'Testing...';
    }
    return 'Not configured';
  };

  const formatTimestamp = (timestamp) => {
    if (!timestamp) return '—';
    const date = new Date(timestamp);
    if (Number.isNaN(date.getTime())) return '—';
    return date.toLocaleString();
  };
  
  return (
    <div className="api-key-settings">
      <h2 style={{marginBottom: '20px', fontSize: '1.5rem', fontWeight: 'bold', color: '#ffffff'}}>
        🔑 API Key Management
      </h2>
      
      {message.text && (
        <div className={`message ${message.type}`} style={{
          padding: '12px 16px',
          marginBottom: '20px',
          borderRadius: '6px',
          backgroundColor: message.type === 'success' ? '#22c55e20' : '#ef444420',
          border: `1px solid ${message.type === 'success' ? '#22c55e' : '#ef4444'}`,
          color: message.type === 'success' ? '#22c55e' : '#ef4444'
        }}>
          {message.text}
        </div>
      )}
      
      <div style={{display: 'grid', gap: '20px'}}>
        {PROVIDERS.map(provider => {
          const providerStatus = providers.find(p => p.provider === provider.id);
          const status = providerStatus?.status || 'not_configured';
          
          return (
            <div key={provider.id} style={{
              padding: '20px',
              background: 'var(--panel)',
              borderRadius: '8px',
              border: '1px solid var(--line)'
            }}>
              <div style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                marginBottom: '16px'
              }}>
                <div style={{display: 'flex', alignItems: 'center', gap: '10px'}}>
                  <span style={{fontSize: '1.5rem'}}>{provider.icon}</span>
                  <div>
                    <h3 style={{margin: 0, fontSize: '1.1rem', fontWeight: 'bold'}}>
                      {provider.name}
                    </h3>
                    <div style={{
                      fontSize: '0.75rem',
                      color: getStatusColor(status),
                      marginTop: '4px'
                    }}>
                      {getStatusIcon(status)} {providerStatus?.status_display || 'Not configured'}
                    </div>
                    {providerStatus?.last_test_error && (
                      <div style={{fontSize: '0.7rem', color: '#ef4444', marginTop: '4px'}}>
                        Last error: {providerStatus.last_test_error}
                      </div>
                    )}
                    {providerStatus?.updated_at && (
                      <div style={{fontSize: '0.7rem', color: 'var(--muted)', marginTop: '4px'}}>
                        Updated: {formatTimestamp(providerStatus.updated_at)}
                      </div>
                    )}
                  </div>
                </div>
                
                {status !== 'not_configured' && (
                  <div style={{display: 'flex', gap: '8px'}}>
                    <button
                      onClick={() => testApiKey(provider.id)}
                      disabled={loading}
                      style={{
                        padding: '6px 12px',
                        fontSize: '0.85rem',
                        background: '#3b82f6',
                        color: 'white',
                        border: 'none',
                        borderRadius: '4px',
                        cursor: 'pointer'
                      }}
                    >
                      Test
                    </button>
                    <button
                      onClick={() => deleteApiKey(provider.id, provider.name)}
                      disabled={loading}
                      style={{
                        padding: '6px 12px',
                        fontSize: '0.85rem',
                        background: '#ef4444',
                        color: 'white',
                        border: 'none',
                        borderRadius: '4px',
                        cursor: 'pointer'
                      }}
                    >
                      Delete
                    </button>
                  </div>
                )}
              </div>
              
              <div style={{display: 'grid', gap: '12px'}}>
                {provider.fields.map(field => (
                  <div key={field}>
                    <label style={{
                      display: 'block',
                      fontSize: '0.85rem',
                      marginBottom: '6px',
                      color: 'var(--muted)'
                    }}>
                      {field === 'api_key' ? 'API Key' :
                       field === 'api_secret' ? 'API Secret' :
                       field === 'passphrase' ? 'Passphrase' : field}
                    </label>
                    <input
                      type={showKeys[`${provider.id}_${field}`] ? 'text' : 'password'}
                      value={formData[provider.id]?.[field] || ''}
                      onChange={(e) => handleInputChange(provider.id, field, e.target.value)}
                      placeholder={`Enter ${field.replace('_', ' ')}`}
                      disabled={loading}
                      style={{
                        width: '100%',
                        padding: '10px',
                        fontSize: '0.9rem',
                        background: 'var(--glass)',
                        border: '1px solid var(--line)',
                        borderRadius: '4px',
                        color: 'var(--text)'
                      }}
                    />
                  </div>
                ))}
                
                <button
                  onClick={() => saveApiKey(provider.id)}
                  disabled={loading}
                  style={{
                    padding: '10px 16px',
                    fontSize: '0.9rem',
                    background: '#22c55e',
                    color: 'white',
                    border: 'none',
                    borderRadius: '4px',
                    cursor: 'pointer',
                    fontWeight: 'bold'
                  }}
                >
                  {loading ? 'Saving...' : 'Save API Key'}
                </button>
              </div>
              
              <div style={{
                marginTop: '12px',
                padding: '8px',
                background: 'var(--glass)',
                borderRadius: '4px',
                fontSize: '0.75rem',
                color: 'var(--muted)'
              }}>
                Required fields: {provider.fields.join(', ')}
              </div>
            </div>
          );
        })}
      </div>
      
      <div style={{
        marginTop: '20px',
        padding: '16px',
        background: 'var(--panel)',
        borderRadius: '8px',
        border: '1px solid #3b82f6',
        fontSize: '0.85rem',
        color: 'var(--muted)'
      }}>
        <h4 style={{margin: '0 0 8px 0', color: '#3b82f6'}}>ℹ️ Security Note</h4>
        <p style={{margin: 0}}>
          All API keys are encrypted at rest using industry-standard encryption.
          Keys are never stored in plaintext and are only used for authenticated API calls.
        </p>
      </div>
    </div>
  );
};

export default APIKeySettings;
