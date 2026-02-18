import React, { useState, useEffect } from 'react';
import { apiClient } from '@/lib/apiClient';
import { toast } from 'sonner';
import { getPlatformDisplayName, getPlatformIcon } from '../../../constants/platforms';

/**
 * Autopilot Insights Panel
 * User-configurable autopilot settings per exchange with real-time status
 */
export default function AutopilotInsightsPanel({ onRefresh }) {
  const [growthStatus, setGrowthStatus] = useState(null);
  const [reinvestStatus, setReinvestStatus] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [expanded, setExpanded] = useState({});
  
  // User-configurable settings per exchange
  const [settings, setSettings] = useState({});
  const [editMode, setEditMode] = useState({});

  useEffect(() => {
    fetchAutopilotStatus();
    loadUserSettings();
    
    // Auto-refresh every 30 seconds
    const interval = setInterval(fetchAutopilotStatus, 30000);
    return () => clearInterval(interval);
  }, []);

  const fetchAutopilotStatus = async () => {
    try {
      const [growthRes, reinvestRes] = await Promise.all([
        apiClient.get('/autopilot/growth/status'),
        apiClient.get('/autopilot/reinvest/status')
      ]);
      
      setGrowthStatus(growthRes.data);
      setReinvestStatus(reinvestRes.data);
    } catch (err) {
      console.error('Failed to fetch autopilot status:', err);
    } finally {
      setLoading(false);
    }
  };

  const loadUserSettings = async () => {
    try {
      const response = await apiClient.get('/autopilot/user-settings');
      setSettings(response.data.settings || {});
    } catch (err) {
      console.error('Failed to load user settings:', err);
      // Initialize with default settings
      setSettings({});
    }
  };

  const saveExchangeSettings = async (exchange) => {
    try {
      setSaving(true);
      const exchangeSettings = settings[exchange] || {};
      
      await apiClient.post('/autopilot/configure', {
        exchange,
        profit_threshold_zar: parseFloat(exchangeSettings.profit_threshold_zar || 1000),
        bot_cap: parseInt(exchangeSettings.bot_cap || 10),
        reinvest_min_zar: parseFloat(exchangeSettings.reinvest_min_zar || 500)
      });
      
      toast.success(`Settings saved for ${getPlatformDisplayName(exchange)}`);
      setEditMode(prev => ({ ...prev, [exchange]: false }));
      
      // Refresh status
      await fetchAutopilotStatus();
    } catch (err) {
      console.error('Failed to save settings:', err);
      toast.error(err.response?.data?.detail || 'Failed to save settings');
    } finally {
      setSaving(false);
    }
  };

  const updateExchangeSetting = (exchange, field, value) => {
    setSettings(prev => ({
      ...prev,
      [exchange]: {
        ...(prev[exchange] || {}),
        [field]: value
      }
    }));
  };

  const toggleExpanded = (exchange) => {
    setExpanded(prev => ({
      ...prev,
      [exchange]: !prev[exchange]
    }));
  };

  const toggleEditMode = (exchange) => {
    setEditMode(prev => ({
      ...prev,
      [exchange]: !prev[exchange]
    }));
  };

  const getProgressPercentage = (current, target) => {
    if (!target || target === 0) return 0;
    return Math.min(100, (current / target) * 100);
  };

  if (loading) {
    return (
      <div style={{
        padding: '20px',
        textAlign: 'center',
        color: 'var(--muted)'
      }}>
        Loading autopilot insights...
      </div>
    );
  }

  const exchanges = growthStatus?.platforms ? Object.keys(growthStatus.platforms) : [];

  return (
    <div style={{
      padding: '16px',
      background: 'var(--glass)',
      border: '1px solid var(--line)',
      borderRadius: '8px'
    }}>
      <div style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        marginBottom: '16px'
      }}>
        <div>
          <h3 style={{ margin: 0, color: 'var(--text)', fontSize: '1.1rem' }}>
            🤖 Autopilot Insights
          </h3>
          <p style={{ margin: '4px 0 0 0', fontSize: '0.85rem', color: 'var(--muted)' }}>
            Configure profit thresholds and bot caps per exchange
          </p>
        </div>
        <button
          onClick={fetchAutopilotStatus}
          style={{
            padding: '6px 12px',
            background: 'var(--panel)',
            color: 'var(--text)',
            border: '1px solid var(--line)',
            borderRadius: '6px',
            cursor: 'pointer',
            fontSize: '0.85rem',
            fontWeight: 600
          }}
        >
          🔄 Refresh
        </button>
      </div>

      {/* Global Status */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))',
        gap: '12px',
        marginBottom: '20px',
        padding: '12px',
        background: 'var(--panel)',
        borderRadius: '6px'
      }}>
        <div>
          <div style={{ fontSize: '0.8rem', color: 'var(--muted)', marginBottom: '4px' }}>
            Growth Status
          </div>
          <div style={{
            fontWeight: 600,
            color: growthStatus?.enabled ? 'var(--success)' : 'var(--error)'
          }}>
            {growthStatus?.enabled ? '✓ Enabled' : '✗ Disabled'}
          </div>
        </div>
        
        <div>
          <div style={{ fontSize: '0.8rem', color: 'var(--muted)', marginBottom: '4px' }}>
            Reinvest Status
          </div>
          <div style={{
            fontWeight: 600,
            color: reinvestStatus?.enabled ? 'var(--success)' : 'var(--error)'
          }}>
            {reinvestStatus?.enabled ? '✓ Enabled' : '✗ Disabled'}
          </div>
        </div>
        
        <div>
          <div style={{ fontSize: '0.8rem', color: 'var(--muted)', marginBottom: '4px' }}>
            Default Milestone
          </div>
          <div style={{ fontSize: '0.9rem', fontWeight: 600, color: 'var(--text)' }}>
            R {growthStatus?.profit_threshold_zar?.toFixed(0) || '1,000'}
          </div>
        </div>
      </div>

      {/* Per-Exchange Cards */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))',
        gap: '12px'
      }}>
        {exchanges.map(exchange => {
          const growth = growthStatus.platforms[exchange];
          const reinvest = reinvestStatus.platforms[exchange];
          const exchangeSettings = settings[exchange] || {
            profit_threshold_zar: growth?.next_threshold_zar || 1000,
            bot_cap: growth?.bots_max || 10,
            reinvest_min_zar: 500
          };
          const isEditing = editMode[exchange];
          const isExpanded = expanded[exchange];
          const progressPct = getProgressPercentage(
            growth?.realized_profit_zar || 0,
            growth?.next_threshold_zar || exchangeSettings.profit_threshold_zar
          );

          return (
            <div
              key={exchange}
              style={{
                padding: '12px',
                background: 'var(--panel)',
                border: '1px solid var(--line)',
                borderRadius: '6px'
              }}
            >
              {/* Exchange Header */}
              <div style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                marginBottom: '12px'
              }}>
                <div style={{
                  fontSize: '1rem',
                  fontWeight: 600,
                  color: 'var(--text)',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '8px'
                }}>
                  <span>{getPlatformIcon(exchange)}</span>
                  <span>{getPlatformDisplayName(exchange)}</span>
                </div>
                <div style={{ display: 'flex', gap: '8px' }}>
                  <button
                    onClick={() => toggleEditMode(exchange)}
                    style={{
                      padding: '4px 8px',
                      background: isEditing ? 'var(--accent)' : 'transparent',
                      color: isEditing ? 'white' : 'var(--text)',
                      border: '1px solid var(--line)',
                      borderRadius: '4px',
                      cursor: 'pointer',
                      fontSize: '0.8rem'
                    }}
                  >
                    {isEditing ? '✓' : '⚙️'}
                  </button>
                  <button
                    onClick={() => toggleExpanded(exchange)}
                    style={{
                      padding: '4px 8px',
                      background: 'transparent',
                      color: 'var(--text)',
                      border: '1px solid var(--line)',
                      borderRadius: '4px',
                      cursor: 'pointer',
                      fontSize: '0.8rem'
                    }}
                  >
                    {isExpanded ? '▼' : '▶'}
                  </button>
                </div>
              </div>

              {/* Quick Stats */}
              <div style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(2, 1fr)',
                gap: '8px',
                marginBottom: '12px'
              }}>
                <div>
                  <div style={{ fontSize: '0.75rem', color: 'var(--muted)' }}>Bots</div>
                  <div style={{ fontSize: '0.9rem', fontWeight: 600, color: 'var(--text)' }}>
                    {growth?.bots_current || 0} / {growth?.bots_max || exchangeSettings.bot_cap}
                  </div>
                </div>
                <div>
                  <div style={{ fontSize: '0.75rem', color: 'var(--muted)' }}>Profit</div>
                  <div style={{ fontSize: '0.9rem', fontWeight: 600, color: 'var(--text)' }}>
                    R {growth?.realized_profit_zar?.toFixed(0) || '0'}
                  </div>
                </div>
              </div>

              {/* Progress Bar */}
              <div style={{ marginBottom: '12px' }}>
                <div style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  fontSize: '0.75rem',
                  color: 'var(--muted)',
                  marginBottom: '4px'
                }}>
                  <span>Next Spawn</span>
                  <span>{progressPct.toFixed(0)}%</span>
                </div>
                <div style={{
                  width: '100%',
                  height: '6px',
                  background: 'var(--glass)',
                  borderRadius: '3px',
                  overflow: 'hidden'
                }}>
                  <div style={{
                    width: `${progressPct}%`,
                    height: '100%',
                    background: progressPct >= 100 ? 'var(--success)' : 'var(--accent2)',
                    transition: 'width 0.3s ease'
                  }} />
                </div>
              </div>

              {/* Expanded Details */}
              {isExpanded && (
                <div style={{
                  marginTop: '12px',
                  padding: '12px',
                  background: 'var(--glass)',
                  borderRadius: '6px'
                }}>
                  {isEditing ? (
                    // Edit Mode
                    <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
                      <div>
                        <label style={{
                          display: 'block',
                          fontSize: '0.8rem',
                          fontWeight: 600,
                          color: 'var(--text)',
                          marginBottom: '4px'
                        }}>
                          Profit Threshold (ZAR)
                        </label>
                        <input
                          type="number"
                          value={exchangeSettings.profit_threshold_zar}
                          onChange={(e) => updateExchangeSetting(exchange, 'profit_threshold_zar', e.target.value)}
                          style={{
                            width: '100%',
                            padding: '8px',
                            background: 'var(--panel)',
                            border: '1px solid var(--line)',
                            borderRadius: '4px',
                            color: 'var(--text)',
                            fontSize: '0.9rem'
                          }}
                        />
                        <div style={{ fontSize: '0.7rem', color: 'var(--muted)', marginTop: '2px' }}>
                          Spawn new bot when profit exceeds this amount
                        </div>
                      </div>

                      <div>
                        <label style={{
                          display: 'block',
                          fontSize: '0.8rem',
                          fontWeight: 600,
                          color: 'var(--text)',
                          marginBottom: '4px'
                        }}>
                          Bot Cap
                        </label>
                        <input
                          type="number"
                          value={exchangeSettings.bot_cap}
                          onChange={(e) => updateExchangeSetting(exchange, 'bot_cap', e.target.value)}
                          style={{
                            width: '100%',
                            padding: '8px',
                            background: 'var(--panel)',
                            border: '1px solid var(--line)',
                            borderRadius: '4px',
                            color: 'var(--text)',
                            fontSize: '0.9rem'
                          }}
                        />
                        <div style={{ fontSize: '0.7rem', color: 'var(--muted)', marginTop: '2px' }}>
                          Maximum number of bots on this exchange
                        </div>
                      </div>

                      <div>
                        <label style={{
                          display: 'block',
                          fontSize: '0.8rem',
                          fontWeight: 600,
                          color: 'var(--text)',
                          marginBottom: '4px'
                        }}>
                          Reinvest Minimum (ZAR)
                        </label>
                        <input
                          type="number"
                          value={exchangeSettings.reinvest_min_zar}
                          onChange={(e) => updateExchangeSetting(exchange, 'reinvest_min_zar', e.target.value)}
                          style={{
                            width: '100%',
                            padding: '8px',
                            background: 'var(--panel)',
                            border: '1px solid var(--line)',
                            borderRadius: '4px',
                            color: 'var(--text)',
                            fontSize: '0.9rem'
                          }}
                        />
                        <div style={{ fontSize: '0.7rem', color: 'var(--muted)', marginTop: '2px' }}>
                          Minimum profit for reinvestment when bot cap reached
                        </div>
                      </div>

                      <button
                        onClick={() => saveExchangeSettings(exchange)}
                        disabled={saving}
                        style={{
                          padding: '10px',
                          background: saving ? 'var(--muted)' : 'var(--success)',
                          color: 'white',
                          border: 'none',
                          borderRadius: '6px',
                          cursor: saving ? 'not-allowed' : 'pointer',
                          fontWeight: 600,
                          fontSize: '0.9rem'
                        }}
                      >
                        {saving ? '💾 Saving...' : '💾 Save Settings'}
                      </button>
                    </div>
                  ) : (
                    // View Mode
                    <div style={{ fontSize: '0.85rem' }}>
                      <div style={{ marginBottom: '8px' }}>
                        <span style={{ color: 'var(--muted)' }}>Next Spawn: </span>
                        <span style={{ color: 'var(--text)', fontWeight: 500 }}>
                          R {growth?.next_threshold_zar?.toFixed(0) || exchangeSettings.profit_threshold_zar}
                        </span>
                      </div>
                      <div style={{ marginBottom: '8px' }}>
                        <span style={{ color: 'var(--muted)' }}>Last Spawn: </span>
                        <span style={{ color: 'var(--text)', fontWeight: 500 }}>
                          {growth?.last_spawn_date || 'Never'}
                        </span>
                      </div>
                      <div style={{ marginBottom: '8px' }}>
                        <span style={{ color: 'var(--muted)' }}>Last Reinvest: </span>
                        <span style={{ color: 'var(--text)', fontWeight: 500 }}>
                          R {reinvest?.last_reinvest_amount?.toFixed(0) || '0'}
                        </span>
                      </div>
                      <div>
                        <span style={{ color: 'var(--muted)' }}>Reinvest Date: </span>
                        <span style={{ color: 'var(--text)', fontWeight: 500 }}>
                          {reinvest?.last_reinvest_date || 'Never'}
                        </span>
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>

      <div style={{
        marginTop: '16px',
        padding: '12px',
        background: 'var(--panel)',
        borderRadius: '6px',
        fontSize: '0.8rem',
        color: 'var(--muted)'
      }}>
        💡 <strong>Tip:</strong> Autopilot will spawn new bots when profit milestones are reached.
        When bot caps are hit, excess profit is reinvested into top performers.
      </div>
    </div>
  );
}
