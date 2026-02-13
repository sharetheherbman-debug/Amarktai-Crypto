import React, { useState, useEffect } from 'react';
import './APIKeySettings.css';
import { ALL_PROVIDERS, PLATFORM_CONFIG } from '../constants/platforms';
import realtimeClient from '../lib/realtime';

const APIKeySettings = () => {
  const NOT_AVAILABLE = 'Not available';
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
  const [expandedProvider, setExpandedProvider] = useState(null);
  const [requestCounter, setRequestCounter] = useState(0); // Track request order
  
  const token = localStorage.getItem('token');

  const normalizeStatusResponse = (data) => {
    if (data?.status_map && Object.keys(data.status_map).length > 0) {
      return data.status_map;
    }

    if (Array.isArray(data?.keys)) {
      return data.keys.reduce((acc, key) => {
        if (!key?.provider) return acc;
        acc[key.provider] = {
          status: key.status,
          last_tested_at: key.last_tested_at,
          last_test_error: key.last_test_error,
          updated_at: key.updated_at
        };
        return acc;
      }, {});
    }

    return {};
  };
  
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
        const statusMap = normalizeStatusResponse(data);
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

  const toggleProvider = (providerId) => {
    setExpandedProvider(prev => (prev === providerId ? null : providerId));
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
    if (!timestamp) return NOT_AVAILABLE;
    const date = new Date(timestamp);
    if (Number.isNaN(date.getTime())) return NOT_AVAILABLE;
    return date.toLocaleString();
  };

  const getStatusBadge = (status) => {
    const normalizedStatus = status?.toLowerCase();
    if (normalizedStatus === 'configured_valid' || normalizedStatus === 'test_ok') {
      return { label: 'Test OK', tone: 'success' };
    }
    if (normalizedStatus === 'configured_invalid' || normalizedStatus === 'test_failed') {
      return { label: 'Test failed', tone: 'error' };
    }
    if (normalizedStatus === 'configured_untested' || normalizedStatus === 'saved_untested') {
      return { label: 'Configured', tone: 'warning' };
    }
    if (normalizedStatus === 'testing') {
      return { label: 'Testing', tone: 'info' };
    }
    return { label: 'Not configured', tone: 'muted' };
  };
  
  return (
    <div className="api-key-settings">
      <div className="api-key-header">
        <div>
          <h2>🔑 API Key Management</h2>
          <p className="api-key-subtitle">
            Select a provider to add, update, or test your credentials. Keys are encrypted and scoped to your account.
          </p>
        </div>
      </div>

      {message.text && (
        <div className={`api-message ${message.type}`}>
          {message.text}
        </div>
      )}

      <div className="api-key-grid">
        {PROVIDERS.map(provider => {
          const providerStatus = providers.find(p => p.provider === provider.id);
          const status = providerStatus?.status || 'not_configured';
          const statusBadge = getStatusBadge(status);
          const isExpanded = expandedProvider === provider.id;
          const statusDetails = providerStatus?.status_display || getStatusDisplay(status, providerStatus?.last_test_error);

          return (
            <div key={provider.id} className={`api-key-card ${isExpanded ? 'expanded' : ''}`}>
              <button
                type="button"
                className="api-key-card-header"
                onClick={() => toggleProvider(provider.id)}
                aria-expanded={isExpanded}
              >
                <div className="api-key-card-title">
                  <span className="api-key-icon">{provider.icon}</span>
                  <div>
                    <h3>{provider.name}</h3>
                    <span className={`api-key-badge ${statusBadge.tone}`}>{statusBadge.label}</span>
                  </div>
                </div>
                <span className="api-key-card-cta">Click to manage</span>
              </button>

              <div className="api-key-card-meta">
                <span>Status: {statusDetails}</span>
                <span>Last tested: {formatTimestamp(providerStatus?.last_tested_at)}</span>
              </div>

              {isExpanded && (
                <div className="api-key-card-body">
                  <div className="api-key-fields">
                    {provider.fields.map(field => (
                      <div key={field} className="api-key-field">
                        <label>
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
                        />
                      </div>
                    ))}
                  </div>

                  <div className="api-key-actions">
                    <button
                      onClick={() => saveApiKey(provider.id)}
                      disabled={loading}
                      className="api-key-button primary"
                    >
                      {loading ? 'Saving...' : 'Save Key'}
                    </button>
                    {status !== 'not_configured' && (
                      <>
                        <button
                          onClick={() => testApiKey(provider.id)}
                          disabled={loading}
                          className="api-key-button ghost"
                        >
                          Test
                        </button>
                        <button
                          onClick={() => deleteApiKey(provider.id, provider.name)}
                          disabled={loading}
                          className="api-key-button danger"
                        >
                          Remove
                        </button>
                      </>
                    )}
                  </div>

                  {providerStatus?.last_test_error && (
                    <div className="api-key-error">
                      Last error: {providerStatus.last_test_error}
                    </div>
                  )}
                  <div className="api-key-meta-note">
                    Updated: {formatTimestamp(providerStatus?.updated_at)}
                  </div>
                  <div className="api-key-required">
                    Required fields: {provider.fields.join(', ')}
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>

      <div className="api-key-security">
        <h4>ℹ️ Security Note</h4>
        <p>
          All API keys are encrypted at rest using industry-standard encryption. Keys are never stored in plaintext and are only used for authenticated API calls.
        </p>
      </div>
    </div>
  );
};

export default APIKeySettings;
