import React, { useState, useEffect, useMemo } from 'react';
import './APIKeySettings.css';
import { ALL_PROVIDERS, PLATFORM_CONFIG } from '../constants/platforms';
import realtimeClient from '../lib/realtime';
import { get, post, del, notifyError } from '../lib/apiClient';
import {
  Drawer,
  DrawerContent,
  DrawerDescription,
  DrawerHeader,
  DrawerTitle
} from '@/ui/components/Drawer';

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
  const [activeProviderId, setActiveProviderId] = useState(null);
  const [unsupportedProviders, setUnsupportedProviders] = useState({});
  const [requestCounter, setRequestCounter] = useState(0); // Track request order
  
  const getProviderName = (providerId) =>
    PROVIDERS.find((provider) => provider.id === providerId)?.name;

  const isProviderAvailable = (providerId) => {
    if (PLATFORM_CONFIG[providerId]?.enabled === false) {
      return false;
    }
    return !unsupportedProviders[providerId];
  };

  const activeProvider = useMemo(
    () => PROVIDERS.find((provider) => provider.id === activeProviderId),
    [PROVIDERS, activeProviderId]
  );

  const activeProviderStatus = useMemo(
    () => providers.find((status) => status.provider === activeProviderId),
    [providers, activeProviderId]
  );

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
      const data = await get('/keys/status');
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
    } catch (error) {
      console.error('Error fetching providers:', error);
      notifyError(error);
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

  const markProviderUnsupported = (providerId, providerName) => {
    setUnsupportedProviders(prev => ({ ...prev, [providerId]: true }));
    showMessage('error', `${providerName || 'This provider'} is not available in this build.`);
  };
  
  const saveApiKey = async (providerId) => {
    const providerName = getProviderName(providerId);
    const data = formData[providerId];
    if (!data || !data.api_key || data.api_key.trim() === '') {
      showMessage('error', 'API key cannot be empty');
      return;
    }
    
    setLoading(true);
    try {
      const result = await post('/keys/save', {
        provider: providerId,
        api_key: data.api_key,
        api_secret: data.api_secret || null,
        passphrase: data.passphrase || null
      });

      showMessage('success', result.message || 'API key saved successfully');
      setFormData(prev => ({ ...prev, [providerId]: {} }));
      fetchAllProviders();
    } catch (error) {
      if (error.status === 404 || error.status === 501) {
        markProviderUnsupported(providerId, providerName);
        return;
      }
      showMessage('error', 'Error saving API key: ' + error.message);
      notifyError(error);
    } finally {
      setLoading(false);
    }
  };
  
  const testApiKey = async (providerId) => {
    const providerName = getProviderName(providerId);
    setLoading(true);
    
    // Optimistic update: immediately show testing state
    setProviders(prev => prev.map(p => 
      p.provider === providerId 
        ? { ...p, status: 'testing', status_display: 'Testing...' }
        : p
    ));
    
    try {
      const result = await post('/keys/test', { provider: providerId });
      
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
      if (error.status === 404 || error.status === 501) {
        markProviderUnsupported(providerId, providerName);
        return;
      }
      showMessage('error', 'Error testing API key: ' + error.message);
      notifyError(error);
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
      const result = await del(`/keys/${providerId}`);

      showMessage('success', result.message || 'API key deleted successfully');
      // Refresh to confirm
      setTimeout(() => fetchAllProviders(), 300);
    } catch (error) {
      if (error.status === 404 || error.status === 501) {
        markProviderUnsupported(providerId, providerName);
        return;
      }
      showMessage('error', 'Error deleting API key: ' + error.message);
      notifyError(error);
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

  const getStatusBadge = (status, available = true) => {
    if (!available) {
      return { label: 'Not available', tone: 'muted' };
    }
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

  const activeStatus = activeProviderStatus?.status || 'not_configured';
  
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
          const isAvailable = isProviderAvailable(provider.id);
          const statusBadge = getStatusBadge(status, isAvailable);
          const statusDetails = isAvailable
            ? providerStatus?.status_display || getStatusDisplay(status, providerStatus?.last_test_error)
            : 'Not available in this build';
          const isConfigured = status !== 'not_configured';

          return (
            <div
              key={provider.id}
              className={`api-key-card ${!isAvailable ? 'disabled' : ''}`}
              aria-disabled={!isAvailable}
              onClick={() => {
                if (isAvailable) {
                  setActiveProviderId(provider.id);
                }
              }}
            >
              <div className="api-key-card-header">
                <div className="api-key-card-title">
                  <span className="api-key-icon">
                    <span>{provider.icon}</span>
                  </span>
                  <div>
                    <h3>{provider.name}</h3>
                    <span className={`api-key-badge ${statusBadge.tone}`}>{statusBadge.label}</span>
                  </div>
                </div>
                <span className="api-key-card-cta">{isAvailable ? 'Add/Update' : 'Unavailable'}</span>
              </div>

              <div className="api-key-card-meta">
                <span>Status: {statusDetails}</span>
                <span>Last tested: {isAvailable ? formatTimestamp(providerStatus?.last_tested_at) : 'Not available in this build'}</span>
              </div>

                <div className="api-key-card-actions">
                  <button
                    type="button"
                    onClick={() => setActiveProviderId(provider.id)}
                    disabled={!isAvailable}
                    className="api-key-button primary"
                  >
                    {isConfigured ? 'Manage' : 'Add Key'}
                  </button>
                  {isAvailable && isConfigured && (
                    <button
                      type="button"
                      onClick={() => testApiKey(provider.id)}
                      disabled={loading}
                      className="api-key-button ghost"
                    >
                      Test
                    </button>
                  )}
                </div>

              {!isAvailable && (
                <div className="api-key-disabled">
                  Not available in this build
                </div>
              )}
            </div>
          );
        })}
      </div>

      <Drawer
        open={Boolean(activeProviderId)}
        onOpenChange={(open) => {
          if (!open) {
            setActiveProviderId(null);
          }
        }}
      >
        <DrawerContent className="api-key-modal">
          {activeProvider && (
            <>
              <DrawerHeader>
                <DrawerTitle>{activeProvider.name} API Keys</DrawerTitle>
                <DrawerDescription>
                  Store or test your {activeProvider.name} credentials securely.
                </DrawerDescription>
              </DrawerHeader>

              {!isProviderAvailable(activeProvider.id) ? (
                <div className="api-key-disabled">
                  Not available in this build.
                </div>
              ) : (
                <>
                  <div className="api-key-card-meta">
                    <span>Status: {activeProviderStatus?.status_display || getStatusDisplay(activeStatus, activeProviderStatus?.last_test_error)}</span>
                    <span>Last tested: {formatTimestamp(activeProviderStatus?.last_tested_at)}</span>
                  </div>

                  <div className="api-key-fields">
                    {activeProvider.fields.map(field => (
                      <div key={field} className="api-key-field">
                        <label>
                          {field === 'api_key' ? 'API Key' :
                           field === 'api_secret' ? 'API Secret' :
                           field === 'passphrase' ? 'Passphrase' : field}
                        </label>
                        <input
                          type="password"
                          value={formData[activeProvider.id]?.[field] || ''}
                          onChange={(e) => handleInputChange(activeProvider.id, field, e.target.value)}
                          placeholder={`Enter ${field.replace('_', ' ')}`}
                          disabled={loading}
                        />
                      </div>
                    ))}
                  </div>

                  <div className="api-key-actions">
                    <button
                      onClick={() => saveApiKey(activeProvider.id)}
                      disabled={loading}
                      className="api-key-button primary"
                    >
                      {loading ? 'Saving...' : 'Save Key'}
                    </button>
                    {activeStatus !== 'not_configured' && (
                      <>
                        <button
                          onClick={() => testApiKey(activeProvider.id)}
                          disabled={loading}
                          className="api-key-button ghost"
                        >
                          Test
                        </button>
                        <button
                          onClick={() => deleteApiKey(activeProvider.id, activeProvider.name)}
                          disabled={loading}
                          className="api-key-button danger"
                        >
                          Remove
                        </button>
                      </>
                    )}
                  </div>

                  {activeProviderStatus?.last_test_error && (
                    <div className="api-key-error">
                      Last error: {activeProviderStatus.last_test_error}
                    </div>
                  )}
                  <div className="api-key-meta-note">
                    Updated: {formatTimestamp(activeProviderStatus?.updated_at)}
                  </div>
                  <div className="api-key-required">
                    Required fields: {activeProvider.fields.join(', ')}
                  </div>
                </>
              )}
            </>
          )}
        </DrawerContent>
      </Drawer>

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
