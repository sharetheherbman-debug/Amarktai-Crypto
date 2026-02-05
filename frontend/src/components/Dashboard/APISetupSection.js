import React, { useState } from 'react';
import axios from 'axios';
import { toast } from 'sonner';
import { API_BASE } from '../../lib/api.js';
import { SUPPORTED_PLATFORMS, PLATFORM_CONFIG } from '../../constants/platforms.js';

const API = API_BASE;

export const APISetupSection = ({ apiKeys, token, onKeysUpdate }) => {
  const [showForm, setShowForm] = useState(null);
  const [formData, setFormData] = useState({});
  const axiosConfig = { headers: { Authorization: `Bearer ${token}` } };

  const providers = [
    { id: 'openai', name: 'OpenAI', fields: ['api_key'] },
    ...SUPPORTED_PLATFORMS.map(platformId => {
      const config = PLATFORM_CONFIG[platformId];
      const fields = ['api_key', 'api_secret'];
      if (config.requiresPassphrase) {
        fields.push('passphrase');
      }
      return {
        id: platformId,
        name: config.displayName,
        fields
      };
    }),
    { id: 'fetchai', name: 'Fetch.ai', fields: ['api_key'] },
    { id: 'flokx', name: 'Flokx', fields: ['api_key'] }
  ];

  const handleSaveKey = async (provider) => {
    try {
      const response = await axios.post(`${API}/keys/save`, {
        provider: provider.id,
        ...formData
      }, axiosConfig);
      
      toast.success(response.data?.message || `${provider.name} API key saved!`);
      setShowForm(null);
      setFormData({});
      onKeysUpdate();
    } catch (err) {
      const errorMsg = err.response?.data?.detail || err.message || 'Failed to save API key';
      console.error(`Failed to save ${provider.name} key:`, err);
      toast.error(`Failed to save ${provider.name} key: ${errorMsg}`);
    }
  };

  const handleTestConnection = async (providerId) => {
    try {
      const res = await axios.post(`${API}/keys/test`, {
        provider: providerId
      }, axiosConfig);
      if (res.data.success) {
        toast.success(res.data.message || `${providerId} connection successful!`);
      } else {
        toast.error(res.data.message || `${providerId} connection failed`);
      }
    } catch (err) {
      const errorMsg = err.response?.data?.detail || err.response?.data?.message || err.message || 'Connection test failed';
      console.error('Connection test error:', err);
      toast.error(`Connection test failed: ${errorMsg}`);
    }
  };

  return (
    <div className="api-setup-section">
      <h2 className="section-title">🔑 API Keys Setup</h2>
      
      <div className="api-providers-grid">
        {providers.map(provider => {
          const keyData = apiKeys[provider.id];
          // Handle new API response format: status can be "test_ok", "test_failed", "saved_untested", "not_configured"
          const isConnected = keyData?.status === 'connected' || keyData?.status === 'test_ok';
          
          return (
            <div key={provider.id} className="api-provider-card">
              <div className="provider-header">
                <h3>{provider.name}</h3>
                <span className={`status-badge ${isConnected ? 'connected' : 'not-connected'}`}>
                  {isConnected ? '✅ Connected' : keyData?.status === 'test_failed' ? '❌ Test Failed' : keyData?.status === 'saved_untested' ? '⚠️ Untested' : '⚠️ Not Connected'}
                </span>
              </div>
              
              {showForm === provider.id ? (
                <div className="api-form">
                  {provider.fields.map(field => (
                    <input
                      key={field}
                      type="password"
                      autoComplete="new-password"
                      placeholder={field.replace('_', ' ').toUpperCase()}
                      value={formData[field] || ''}
                      onChange={(e) => setFormData({...formData, [field]: e.target.value})}
                    />
                  ))}
                  <div className="form-actions">
                    <button className="btn-primary" onClick={() => handleSaveKey(provider)}>
                      Save
                    </button>
                    <button className="btn-secondary" onClick={() => setShowForm(null)}>
                      Cancel
                    </button>
                  </div>
                </div>
              ) : (
                <div className="provider-actions">
                  <button 
                    className="btn-secondary"
                    onClick={() => setShowForm(provider.id)}
                  >
                    {isConnected ? 'Update' : 'Add'} Key
                  </button>
                  {isConnected && (
                    <button 
                      className="btn-outline"
                      onClick={() => handleTestConnection(provider.id)}
                    >
                      Test
                    </button>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
};
