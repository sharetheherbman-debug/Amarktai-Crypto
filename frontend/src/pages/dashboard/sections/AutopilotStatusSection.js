import React, { useState, useEffect } from 'react';
import SectionHeader from '@/ui/components/SectionHeader';
import { apiClient } from '@/lib/apiClient';
import { toast } from 'sonner';

/**
 * Autopilot Status Section
 * 
 * Displays per-exchange autopilot growth and reinvestment status:
 * - Realized profit since last milestone
 * - Next profit milestone and progress percentage
 * - Current bot count vs platform limit
 * - Whether autopilot is enabled and running
 * - Last reinvest date and amount
 */
export default function AutopilotStatusSection() {
  const [growthStatus, setGrowthStatus] = useState(null);
  const [reinvestStatus, setReinvestStatus] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [refreshing, setRefreshing] = useState(false);

  const fetchAutopilotStatus = async () => {
    try {
      setRefreshing(true);
      setError(null);
      
      // Fetch growth and reinvest status in parallel
      const [growthRes, reinvestRes] = await Promise.all([
        apiClient.get('/autopilot/growth/status'),
        apiClient.get('/autopilot/reinvest/status')
      ]);
      
      setGrowthStatus(growthRes.data);
      setReinvestStatus(reinvestRes.data);
    } catch (err) {
      console.error('Error fetching autopilot status:', err);
      setError(err.message || 'Failed to load autopilot status');
      toast.error('Failed to load autopilot status');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  useEffect(() => {
    fetchAutopilotStatus();
  }, []);

  const handleRefresh = () => {
    fetchAutopilotStatus();
    toast.info('Refreshing autopilot status...');
  };

  if (loading) {
    return (
      <section className="section active">
        <div className="card">
          <SectionHeader
            title="🤖 Autopilot Status"
            subtitle="Monitor autopilot growth and reinvestment across exchanges"
          />
          <div style={{ padding: '40px', textAlign: 'center', color: 'var(--muted)' }}>
            Loading autopilot status...
          </div>
        </div>
      </section>
    );
  }

  if (error) {
    return (
      <section className="section active">
        <div className="card">
          <SectionHeader
            title="🤖 Autopilot Status"
            subtitle="Monitor autopilot growth and reinvestment across exchanges"
          />
          <div style={{ padding: '40px', textAlign: 'center' }}>
            <div style={{ color: 'var(--error)', marginBottom: '16px' }}>
              ⚠️ {error}
            </div>
            <button
              onClick={handleRefresh}
              className="btn btn-primary"
              style={{ padding: '8px 16px' }}
            >
              Retry
            </button>
          </div>
        </div>
      </section>
    );
  }

  const platforms = growthStatus?.platforms ? Object.keys(growthStatus.platforms) : [];

  return (
    <section className="section active">
      <div className="card">
        <SectionHeader
          title="🤖 Autopilot Status"
          subtitle="Monitor autopilot growth and reinvestment across exchanges"
        />

        {/* Global Status */}
        <div style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
          gap: '12px',
          marginBottom: '20px'
        }}>
          <div style={{
            padding: '16px',
            background: 'var(--glass)',
            border: `2px solid ${growthStatus?.enabled ? 'var(--success)' : 'var(--line)'}`,
            borderRadius: '8px'
          }}>
            <div style={{ fontSize: '0.85rem', color: 'var(--muted)', marginBottom: '4px' }}>
              Growth Status
            </div>
            <div style={{
              fontSize: '1.2rem',
              fontWeight: '600',
              color: growthStatus?.enabled ? 'var(--success)' : 'var(--error)'
            }}>
              {growthStatus?.enabled ? '✓ On' : '✗ Off'}
            </div>
            {!growthStatus?.enabled && (
              <div style={{ fontSize: '0.75rem', color: 'var(--muted)', marginTop: '4px' }}>
                <div><strong>Why:</strong> Autopilot growth is not enabled.</div>
                <div><strong>How to enable:</strong> Go to System Mode section and enable Autopilot.</div>
              </div>
            )}
          </div>

          <div style={{
            padding: '16px',
            background: 'var(--glass)',
            border: `2px solid ${reinvestStatus?.enabled ? 'var(--success)' : 'var(--line)'}`,
            borderRadius: '8px'
          }}>
            <div style={{ fontSize: '0.85rem', color: 'var(--muted)', marginBottom: '4px' }}>
              Reinvest Status
            </div>
            <div style={{
              fontSize: '1.2rem',
              fontWeight: '600',
              color: reinvestStatus?.enabled ? 'var(--success)' : 'var(--error)'
            }}>
              {reinvestStatus?.enabled ? '✓ On' : '✗ Off'}
            </div>
            {!reinvestStatus?.enabled && (
              <div style={{ fontSize: '0.75rem', color: 'var(--muted)', marginTop: '4px' }}>
                <div><strong>Why:</strong> Auto-Reinvest is not enabled.</div>
                <div><strong>How to enable:</strong> Go to System Mode section and enable Autopilot, then enable Auto-Reinvest in your profile settings.</div>
              </div>
            )}
          </div>

          <div style={{
            padding: '16px',
            background: 'var(--glass)',
            border: '1px solid var(--line)',
            borderRadius: '8px'
          }}>
            <div style={{ fontSize: '0.85rem', color: 'var(--muted)', marginBottom: '4px' }}>
              Profit Milestone
            </div>
            <div style={{ fontSize: '1.2rem', fontWeight: '600', color: 'var(--text)' }}>
              R {growthStatus?.profit_threshold_zar?.toFixed(0) || '0'}
            </div>
          </div>

          <div style={{
            padding: '16px',
            background: 'var(--glass)',
            border: '1px solid var(--line)',
            borderRadius: '8px'
          }}>
            <div style={{ fontSize: '0.85rem', color: 'var(--muted)', marginBottom: '4px' }}>
              Min Reinvest
            </div>
            <div style={{ fontSize: '1.2rem', fontWeight: '600', color: 'var(--text)' }}>
              R {reinvestStatus?.min_reinvest_zar?.toFixed(0) || '0'}
            </div>
          </div>
        </div>

        {/* Refresh Button */}
        <div style={{ marginBottom: '20px' }}>
          <button
            onClick={handleRefresh}
            disabled={refreshing}
            className="btn btn-secondary"
            style={{ padding: '8px 16px' }}
          >
            {refreshing ? '🔄 Refreshing...' : '🔄 Refresh Status'}
          </button>
        </div>

        {/* Per-Platform Status */}
        <div style={{ marginTop: '24px' }}>
          <h3 style={{ marginBottom: '16px', color: 'var(--text)', fontSize: '1.1rem' }}>
            Platform Status
          </h3>
          
          <div style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))',
            gap: '16px'
          }}>
            {platforms.map(platform => {
              const growth = growthStatus.platforms[platform];
              const reinvest = reinvestStatus.platforms[platform];
              
              // Calculate progress percentage
              const progressPct = growth.next_threshold_zar > 0
                ? Math.min(100, (growth.realized_profit_zar / growth.next_threshold_zar) * 100)
                : 0;

              return (
                <div
                  key={platform}
                  style={{
                    padding: '16px',
                    background: 'var(--panel)',
                    border: '1px solid var(--line)',
                    borderRadius: '8px'
                  }}
                >
                  {/* Platform Header */}
                  <div style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    marginBottom: '12px'
                  }}>
                    <h4 style={{
                      fontSize: '1rem',
                      fontWeight: '600',
                      color: 'var(--text)',
                      textTransform: 'capitalize'
                    }}>
                      {platform}
                    </h4>
                    {growth.eligible && (
                      <span style={{
                        padding: '2px 8px',
                        background: 'var(--success)',
                        color: 'white',
                        borderRadius: '4px',
                        fontSize: '0.75rem',
                        fontWeight: '600'
                      }}>
                        Ready
                      </span>
                    )}
                  </div>

                  {/* Bot Count */}
                  <div style={{ marginBottom: '12px' }}>
                    <div style={{
                      display: 'flex',
                      justifyContent: 'space-between',
                      fontSize: '0.85rem',
                      marginBottom: '4px'
                    }}>
                      <span style={{ color: 'var(--muted)' }}>Bots</span>
                      <span style={{ color: 'var(--text)', fontWeight: '500' }}>
                        {growth.bots_current} / {growth.bots_max}
                      </span>
                    </div>
                    <div style={{
                      width: '100%',
                      height: '6px',
                      background: 'var(--glass)',
                      borderRadius: '3px',
                      overflow: 'hidden'
                    }}>
                      <div style={{
                        width: `${(growth.bots_current / growth.bots_max) * 100}%`,
                        height: '100%',
                        background: growth.bots_current >= growth.bots_max ? 'var(--warning)' : 'var(--accent)',
                        transition: 'width 0.3s ease'
                      }} />
                    </div>
                  </div>

                  {/* Profit Progress */}
                  <div style={{ marginBottom: '12px' }}>
                    <div style={{
                      display: 'flex',
                      justifyContent: 'space-between',
                      fontSize: '0.85rem',
                      marginBottom: '4px'
                    }}>
                      <span style={{ color: 'var(--muted)' }}>Profit to Next Spawn</span>
                      <span style={{ color: 'var(--text)', fontWeight: '500' }}>
                        R {growth.realized_profit_zar.toFixed(2)} / R {growth.next_threshold_zar.toFixed(0)}
                      </span>
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
                    <div style={{
                      fontSize: '0.75rem',
                      color: 'var(--muted)',
                      marginTop: '4px'
                    }}>
                      {progressPct.toFixed(1)}% complete
                    </div>
                  </div>

                  {/* Milestones Spawned */}
                  <div style={{
                    fontSize: '0.85rem',
                    color: 'var(--muted)',
                    marginBottom: '8px'
                  }}>
                    Milestones spawned: <span style={{ color: 'var(--text)', fontWeight: '500' }}>
                      {growth.milestones_spawned}
                    </span>
                  </div>

                  {/* Last Reinvest */}
                  {reinvest.last_reinvest_date && (
                    <div style={{
                      fontSize: '0.85rem',
                      color: 'var(--muted)',
                      marginBottom: '4px'
                    }}>
                      Last reinvest: <span style={{ color: 'var(--text)', fontWeight: '500' }}>
                        R {reinvest.last_reinvest_amount?.toFixed(2) || '0'} on {reinvest.last_reinvest_date}
                      </span>
                    </div>
                  )}

                  {/* Blocked Reasons */}
                  {growth.blocked_reasons && growth.blocked_reasons.length > 0 && (
                    <div style={{
                      marginTop: '12px',
                      padding: '8px',
                      background: 'var(--glass)',
                      border: '1px solid var(--warning)',
                      borderRadius: '6px'
                    }}>
                      <div style={{
                        fontSize: '0.75rem',
                        color: 'var(--warning)',
                        fontWeight: '600',
                        marginBottom: '4px'
                      }}>
                        ⚠️ Blocked
                      </div>
                      <ul style={{
                        margin: 0,
                        paddingLeft: '20px',
                        fontSize: '0.75rem',
                        color: 'var(--muted)'
                      }}>
                        {growth.blocked_reasons.map((reason, idx) => (
                          <li key={idx}>{reason.replace(/_/g, ' ')}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>

        {/* Help Text */}
        <div style={{
          marginTop: '24px',
          padding: '12px',
          background: 'var(--glass)',
          border: '1px solid var(--line)',
          borderRadius: '8px',
          fontSize: '0.85rem',
          color: 'var(--muted)'
        }}>
          <strong>💡 How it works:</strong> When realized profit on a platform reaches the milestone threshold,
          Autopilot automatically spawns a new bot. Once the bot limit is reached, excess profit is reinvested
          into top-performing bots. Use the global Autopilot toggle in System Mode to enable/disable this feature.
        </div>
      </div>
    </section>
  );
}
