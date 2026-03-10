import React from 'react';
import apiClient from '../../../lib/apiClient';
import { SUPPORTED_PLATFORMS, getPlatformDisplayName, getPlatformIcon } from '../../../constants/platforms';

const API = '';
const axios = apiClient;

const NOT_AVAILABLE = 'Not available';

const safeNumber = (value, fallback = 0) => {
  const num = Number(value);
  return Number.isFinite(num) ? num : fallback;
};

const safeToFixed = (value, digits = 2, fallback = '0.00') => {
  const num = Number(value);
  return Number.isFinite(num) ? num.toFixed(digits) : fallback;
};

const formatZAR = (value, digits = 2, fallback = NOT_AVAILABLE) => {
  const num = Number(value);
  if (!Number.isFinite(num)) return fallback;
  const formatted = Math.abs(num).toLocaleString('en-US', { minimumFractionDigits: digits, maximumFractionDigits: digits });
  return `${num < 0 ? '-R' : 'R'}${formatted}`;
};

/* ── Collapsible API Key Monitor grouped by category ───────────────── */
const KEY_GROUPS = [
  { id: 'ai', label: '🤖 Core AI', match: (p) => ['openai', 'huggingface', 'fetchai', 'litellm', 'google_ai'].includes(p.provider) },
  { id: 'market', label: '📈 Market Data', match: (p) => ['coindesk', 'cryptocompare', 'coingecko', 'coinranking'].includes(p.provider) },
  { id: 'exchange', label: '🏦 Exchanges', match: (p) => ['luno', 'binance', 'kucoin', 'bybit', 'okx', 'valr'].includes(p.provider) },
  { id: 'enricher', label: '🔬 Enrichers', match: (p) => ['whale_alert', 'glassnode', 'santiment', 'lunarcrush'].includes(p.provider) },
];

function KeyMonitorGrouped({ providers, formatDate }) {
  const [openGroups, setOpenGroups] = React.useState({ ai: true, exchange: true });

  const grouped = {};
  const other = [];
  for (const p of providers) {
    let placed = false;
    for (const g of KEY_GROUPS) {
      if (g.match(p)) {
        (grouped[g.id] = grouped[g.id] || []).push(p);
        placed = true;
        break;
      }
    }
    if (!placed) other.push(p);
  }

  const toggle = (id) => setOpenGroups((prev) => ({ ...prev, [id]: !prev[id] }));

  const renderRow = (row) => {
    const statusColor = row.valid ? 'var(--success)' : row.configured ? 'var(--error)' : 'var(--muted)';
    const statusText = row.valid ? 'Valid' : row.configured ? 'Invalid' : 'Not set';
    return (
      <div key={row.provider} style={{
        display: 'grid',
        gridTemplateColumns: '1fr 80px 100px 100px',
        gap: '8px',
        padding: '8px 12px',
        borderBottom: '1px solid rgba(255,255,255,0.04)',
        fontSize: '0.82rem',
        alignItems: 'center',
      }}>
        <span style={{ color: 'var(--text)', fontWeight: 500 }}>{row.display_name || row.provider}</span>
        <span style={{ color: statusColor, fontWeight: 600 }}>{statusText}</span>
        <span style={{ color: 'var(--muted)', fontSize: '0.75rem' }}>
          {row.last_tested_at ? formatDate(row.last_tested_at) : '—'}
        </span>
        <span style={{ color: row.last_error ? 'var(--error)' : 'var(--muted)', fontSize: '0.75rem', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {row.last_error || 'OK'}
        </span>
      </div>
    );
  };

  const renderGroup = (groupDef) => {
    const items = grouped[groupDef.id] || [];
    if (items.length === 0) return null;
    const isOpen = openGroups[groupDef.id];
    const validCount = items.filter((p) => p.valid).length;
    return (
      <div key={groupDef.id} style={{ marginBottom: '8px', border: '1px solid var(--line)', borderRadius: '8px', overflow: 'hidden' }}>
        <button
          onClick={() => toggle(groupDef.id)}
          style={{
            width: '100%',
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            padding: '10px 14px',
            background: 'rgba(255,255,255,0.03)',
            border: 'none',
            cursor: 'pointer',
            color: 'var(--text)',
            fontSize: '0.88rem',
            fontWeight: 600,
          }}
        >
          <span>{groupDef.label} ({validCount}/{items.length} valid)</span>
          <span style={{ fontSize: '0.75rem', opacity: 0.6 }}>{isOpen ? '▼' : '▶'}</span>
        </button>
        {isOpen && (
          <div>
            <div style={{
              display: 'grid',
              gridTemplateColumns: '1fr 80px 100px 100px',
              gap: '8px',
              padding: '4px 12px',
              fontSize: '0.7rem',
              color: 'var(--muted)',
              borderBottom: '1px solid var(--line)',
            }}>
              <span>Provider</span><span>Status</span><span>Tested</span><span>Error</span>
            </div>
            {items.map(renderRow)}
          </div>
        )}
      </div>
    );
  };

  return (
    <div>
      {KEY_GROUPS.map(renderGroup)}
      {other.length > 0 && (() => { grouped['other'] = other; return renderGroup({ id: 'other', label: '📦 Other', match: () => true }); })()}
    </div>
  );
}

export default function AdminPanelSection({
  actionLoading,
  adminApiHealth,
  adminKeyMonitor,
  adminBots,
  adminUsers,
  aiTaskLoading,
  allUsers,
  axiosConfig,
  bodyguardStatus,
  bots,
  clearUserEmergencyOverride,
  emergencyOverrideStatus,
  filteredAdminBots,
  formatDate,
  handleBlockUser,
  handleChangeBotExchange,
  handleChangeBotMode,
  handleChangePassword,
  handleDeleteUser,
  handleDeleteUserAdmin,
  handleEmailAllUsers,
  handleForceLogout,
  handleMigrateApiKeys,
  handleResetPassword,
  handleToggleBlockUser,
  handleToggleBotPause,
  handleTriggerBodyguard,
  handleUserSelection,
  loadAdminBots,
  loadAdminUsers,
  loadingBots,
  loadingUsers,
  selectedBotId,
  selectedUserId,
  setActiveSection,
  setChatMessages,
  setSelectedBotId,
  setSelectedUserId,
  showNotification,
  showSection,
  storageData,
  storageError,
  storageTotals,
  systemStats,
  updateGlobalEmergencyOverride,
  updateUserEmergencyOverride,
  user,
}) {
  return (
      <section className="section active">
        <div className="card">
          <h2 style={{color: '#ffffff'}}>🔧 Admin Panel (God Mode)</h2>
          <div style={{display: 'flex', alignItems: 'center', gap: '12px', marginTop: '8px', marginBottom: '24px'}}>
            <div style={{
              padding: '6px 12px',
              borderRadius: '6px',
              background: adminApiHealth.status === 'Error'
                ? 'var(--error)'
                : adminApiHealth.status === 'Unknown'
                  ? 'var(--line)'
                  : 'var(--success)',
              color: 'white',
              fontSize: '0.8rem',
              fontWeight: 600
            }}>
              Admin API: {adminApiHealth.status}
            </div>
            <div style={{fontSize: '0.75rem', color: 'var(--muted)'}}>
              Last check: {adminApiHealth.lastCheck ? formatDate(adminApiHealth.lastCheck) : NOT_AVAILABLE}
            </div>
          {adminApiHealth.error && (
            <div style={{fontSize: '0.75rem', color: 'var(--error)'}}>
              {adminApiHealth.error}
            </div>
          )}
        </div>
        
        <div className="admin-stack">
          <div className="admin-card">
            <h3 style={{ marginBottom: '12px', color: 'var(--text)' }}>🔐 API Key Monitor (Admin)</h3>
            {adminKeyMonitor?.providers?.length > 0 ? (
              <KeyMonitorGrouped providers={adminKeyMonitor.providers} formatDate={formatDate} />
            ) : (
              <div style={{ color: 'var(--muted)', fontSize: '0.82rem' }}>
                No key telemetry available yet.
              </div>
            )}
          </div>

          {/* VPS Resource Summary */}
          {systemStats?.vps_resources && (
            <div className="admin-card">
              <h3 style={{marginBottom: '12px', color: '#ffffff'}}>🖥️ VPS Resources</h3>
              <div style={{display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '12px'}}>
                <div style={{padding: '16px', background: 'var(--panel)', borderRadius: '6px', border: '1px solid var(--line)'}}>
                  <div style={{fontSize: '0.75rem', color: '#ffffff', marginBottom: '4px'}}>CPU Usage</div>
                  <div style={{fontSize: '1.8rem', fontWeight: 700, color: safeNumber(systemStats.vps_resources.cpu.usage_percent, 0) > 80 ? 'var(--error)' : 'var(--success)'}}>
                    {safeNumber(systemStats.vps_resources.cpu.usage_percent, 0)}%
                  </div>
                  <div style={{fontSize: '0.7rem', color: '#cccccc', marginTop: '4px'}}>
                    {safeNumber(systemStats.vps_resources.cpu.count, 0)} cores
                    {systemStats.vps_resources.cpu.load_average && 
                      ` • Load: ${systemStats.vps_resources.cpu.load_average['1min']}`
                    }
                  </div>
                </div>
                <div style={{padding: '16px', background: 'var(--panel)', borderRadius: '6px', border: '1px solid var(--line)'}}>
                  <div style={{fontSize: '0.75rem', color: '#ffffff', marginBottom: '4px'}}>RAM Usage</div>
                  <div style={{fontSize: '1.8rem', fontWeight: 700, color: safeNumber(systemStats.vps_resources.memory.usage_percent, 0) > 85 ? 'var(--error)' : 'var(--success)'}}>
                    {safeNumber(systemStats.vps_resources.memory.usage_percent, 0)}%
                  </div>
                  <div style={{fontSize: '0.7rem', color: '#cccccc', marginTop: '4px'}}>
                    {safeNumber(systemStats.vps_resources.memory.used_gb, 0)} / {safeNumber(systemStats.vps_resources.memory.total_gb, 0)} GB used
                  </div>
                </div>
                <div style={{padding: '16px', background: 'var(--panel)', borderRadius: '6px', border: '1px solid var(--line)'}}>
                  <div style={{fontSize: '0.75rem', color: '#ffffff', marginBottom: '4px'}}>Disk Usage</div>
                  <div style={{fontSize: '1.8rem', fontWeight: 700, color: safeNumber(systemStats.vps_resources.disk.usage_percent, 0) > 85 ? 'var(--error)' : 'var(--success)'}}>
                    {safeNumber(systemStats.vps_resources.disk.usage_percent, 0)}%
                  </div>
                  <div style={{fontSize: '0.7rem', color: '#cccccc', marginTop: '4px'}}>
                    {safeNumber(systemStats.vps_resources.disk.free_gb, 0)} GB free
                  </div>
                </div>
              </div>
            </div>
          )}
          
          {/* System Stats */}
          {systemStats && (
            <div className="admin-card" style={{display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: '12px'}}>
              <div style={{padding: '16px', background: 'var(--panel)', borderRadius: '6px', border: '1px solid var(--line)', textAlign: 'center'}}>
                <div style={{fontSize: '2rem', fontWeight: 700, color: 'var(--success)'}}>{safeNumber(systemStats.users?.total, 0)}</div>
                <div style={{fontSize: '0.85rem', color: '#ffffff', marginTop: '4px'}}>Total Users</div>
              </div>
              <div style={{padding: '16px', background: 'var(--panel)', borderRadius: '6px', border: '1px solid var(--line)', textAlign: 'center'}}>
                <div style={{fontSize: '2rem', fontWeight: 700, color: 'var(--success)'}}>{safeNumber(systemStats.bots?.active, 0)}</div>
                <div style={{fontSize: '0.85rem', color: '#ffffff', marginTop: '4px'}}>Active Bots</div>
              </div>
              <div style={{padding: '16px', background: 'var(--panel)', borderRadius: '6px', border: '1px solid var(--line)', textAlign: 'center'}}>
                <div style={{fontSize: '2rem', fontWeight: 700, color: 'var(--success)'}}>{safeNumber(systemStats.trades?.total, 0)}</div>
                <div style={{fontSize: '0.85rem', color: '#ffffff', marginTop: '4px'}}>Total Trades</div>
              </div>
              <div style={{padding: '16px', background: 'var(--panel)', borderRadius: '6px', border: '1px solid var(--line)', textAlign: 'center'}}>
                <div style={{fontSize: '2rem', fontWeight: 700, color: 'var(--success)'}}>{formatZAR(systemStats.profit?.total)}</div>
                <div style={{fontSize: '0.85rem', color: '#ffffff', marginTop: '4px'}}>Total Profit</div>
              </div>
            </div>
          )}

          {systemStats && (
            <div className="admin-card" style={{display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '12px'}}>
              <div style={{padding: '16px', background: 'var(--panel)', borderRadius: '6px', border: '1px solid var(--line)'}}>
                <div style={{fontSize: '0.85rem', color: '#ffffff', marginBottom: '8px'}}>System Modes</div>
                <div style={{fontSize: '0.75rem', color: 'var(--muted)'}}>
                  Paper: {safeNumber(systemStats.system_modes?.paper_trading, 0)} • Live: {safeNumber(systemStats.system_modes?.live_trading, 0)} • Autopilot: {safeNumber(systemStats.system_modes?.autopilot, 0)}
                </div>
              </div>
              <div style={{padding: '16px', background: 'var(--panel)', borderRadius: '6px', border: '1px solid var(--line)'}}>
                <div style={{fontSize: '0.85rem', color: '#ffffff', marginBottom: '8px'}}>Scheduler Status</div>
                <div style={{fontSize: '0.75rem', color: systemStats.scheduler_status?.running ? 'var(--success)' : 'var(--error)'}}>
                  {systemStats.scheduler_status?.running ? 'Running' : 'Stopped'}
                </div>
              </div>
            </div>
          )}

          {systemStats?.exchange_breakdown && (
            <div className="admin-card">
              <h3 style={{margin: 0, color: '#ffffff'}}>📊 Exchange Breakdown</h3>
              <div style={{marginTop: '12px', display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '12px'}}>
                {SUPPORTED_PLATFORMS.map(exchange => {
                  const breakdown = systemStats.exchange_breakdown?.[exchange] || {};
                  return (
                    <div key={exchange} style={{padding: '12px', background: 'var(--glass)', borderRadius: '6px'}}>
                      <div style={{fontWeight: 600, marginBottom: '6px'}}>{getPlatformIcon(exchange)} {getPlatformDisplayName(exchange)}</div>
                      <div style={{fontSize: '0.75rem', color: 'var(--muted)'}}>Bots: {safeNumber(breakdown.bots, 0)}</div>
                      <div style={{fontSize: '0.75rem', color: 'var(--muted)'}}>Trades: {safeNumber(breakdown.trades, 0)}</div>
                      <div style={{fontSize: '0.75rem', color: 'var(--muted)'}}>Profit: {formatZAR(breakdown.profit)}</div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}
          
          {/* Per-User Storage Usage */}
          {storageError && (
            <div style={{marginBottom: '24px', padding: '12px 16px', borderRadius: '8px', border: '1px solid var(--error)', background: 'rgba(239, 68, 68, 0.1)', color: 'var(--error)'}}>
              ⚠️ Unable to load storage data: {storageError}
            </div>
          )}
          {storageData && (
            <div className="admin-card">
              <div style={{display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px'}}>
                <h3 style={{margin: 0, color: '#ffffff'}}>💾 User Storage Usage</h3>
                <div style={{fontSize: '0.9rem', color: '#cccccc'}}>
                  Total: {storageTotals ? safeToFixed(storageTotals.totalMb, 2) : '0.00'} MB ({storageTotals ? safeToFixed(storageTotals.totalGb, 2) : '0.00'} GB)
                </div>
              </div>
              <div style={{maxHeight: '200px', overflowY: 'auto'}}>
                {storageData.users && storageData.users.length > 0 ? (
                  storageData.users.map((userStorage) => {
                    const storageMb = userStorage.total_storage_mb ?? userStorage.storage_mb ?? 0;
                    return (
                      <div key={userStorage.user_id} style={{
                        padding: '8px 12px',
                        marginBottom: '6px',
                        background: 'var(--glass)',
                        borderRadius: '4px',
                        display: 'flex',
                        justifyContent: 'space-between',
                        alignItems: 'center'
                      }}>
                        <div style={{flex: 1}}>
                        <div style={{fontWeight: 600, fontSize: '0.9rem', color: '#ffffff'}}>{userStorage.name || 'Unknown'}</div>
                          <div style={{fontSize: '0.75rem', color: '#cccccc'}}>{userStorage.email}</div>
                        </div>
                        <div style={{fontWeight: 700, fontSize: '0.95rem', color: storageMb > 100 ? 'var(--error)' : 'var(--success)'}}>
                          {safeToFixed(storageMb, 2)} MB
                        </div>
                      </div>
                    );
                  })
                ) : (
                  <div style={{textAlign: 'center', padding: '20px', color: '#cccccc'}}>
                    No storage data available
                  </div>
                )}
              </div>
            </div>
          )}
          
          {/* Users Table */}
          <div className="admin-card" style={{overflowX: 'auto'}}>
            <h3 style={{margin: '0 0 12px 0', color: '#ffffff'}}>👥 User Management</h3>
            <table style={{width: '100%', borderCollapse: 'collapse', fontSize: '0.85rem'}}>
              <thead>
                <tr style={{borderBottom: '2px solid var(--line)'}}>
                  <th style={{padding: '12px', textAlign: 'left', color: '#ffffff', fontWeight: 600}}>User</th>
                  <th style={{padding: '12px', textAlign: 'left', color: '#ffffff', fontWeight: 600}}>Email</th>
                  <th style={{padding: '12px', textAlign: 'center', color: '#ffffff', fontWeight: 600}}>Bots</th>
                  <th style={{padding: '12px', textAlign: 'center', color: '#ffffff', fontWeight: 600}}>Status</th>
                  <th style={{padding: '12px', textAlign: 'center', color: '#ffffff', fontWeight: 600}}>Actions</th>
                </tr>
              </thead>
              <tbody>
                {allUsers.length === 0 ? (
                  <tr>
                    <td colSpan="5" style={{padding: '40px', textAlign: 'center', color: '#cccccc'}}>
                      No users found
                    </td>
                  </tr>
                ) : (
                  allUsers.map(usr => (
                    <tr key={usr.id} style={{borderBottom: '1px solid var(--line)'}}>
                      <td style={{padding: '12px', color: '#ffffff'}}>{usr.first_name || NOT_AVAILABLE}</td>
                      <td style={{padding: '12px', color: '#ffffff'}}>{usr.email}</td>
                      <td style={{padding: '12px', textAlign: 'center', color: '#ffffff'}}>
                        {safeNumber(usr.stats?.total_bots, 0)}
                      </td>
                      <td style={{padding: '12px', textAlign: 'center'}}>
                        <span style={{
                          padding: '4px 8px',
                          borderRadius: '4px',
                          fontSize: '0.75rem',
                          fontWeight: 600,
                          background: usr.status === 'blocked' ? 'var(--error)' : 'var(--success)',
                          color: 'white'
                        }}>
                          {usr.status === 'blocked' ? 'Blocked' : 'Active'}
                        </span>
                      </td>
                      <td style={{padding: '12px', textAlign: 'center'}}>
                        <div style={{display: 'flex', gap: '4px', justifyContent: 'center', flexWrap: 'wrap'}}>
                          <button 
                            onClick={() => handleChangePassword(usr.id)}
                            style={{
                              padding: '4px 8px',
                              fontSize: '0.75rem',
                              background: 'var(--accent2)',
                              color: 'var(--text)',
                              border: 'none',
                              borderRadius: '4px',
                              cursor: 'pointer',
                              fontWeight: 600
                            }}
                          >
                            Change PW
                          </button>
                          <button 
                            onClick={() => handleBlockUser(usr.id, usr.status === 'blocked')}
                            style={{
                              padding: '4px 8px',
                              fontSize: '0.75rem',
                              background: usr.status === 'blocked' ? 'var(--success)' : 'var(--accent2)',
                              color: 'white',
                              border: 'none',
                              borderRadius: '4px',
                              cursor: 'pointer',
                              fontWeight: 600
                            }}
                          >
                            {usr.status === 'blocked' ? 'Unblock' : 'Block'}
                          </button>
                          <button 
                            onClick={() => handleDeleteUser(usr.id)}
                            style={{
                              padding: '4px 8px',
                              fontSize: '0.75rem',
                              background: 'var(--error)',
                              color: 'white',
                              border: 'none',
                              borderRadius: '4px',
                              cursor: 'pointer',
                              fontWeight: 600
                            }}
                          >
                            Delete
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
          
          {/* AI Bodyguard Status */}
          {bodyguardStatus && (
            <div className="admin-card" style={{marginTop: '24px', border: '2px solid ' + (bodyguardStatus.health_score >= 80 ? 'var(--success)' : bodyguardStatus.health_score >= 60 ? 'var(--accent2)' : 'var(--error)')}}>
              <h3 style={{marginBottom: '16px', color: 'var(--accent)', display: 'flex', alignItems: 'center', gap: '8px'}}>
                🛡️ AI Bodyguard Status
                <span style={{
                  fontSize: '0.75rem', 
                  padding: '4px 8px', 
                  borderRadius: '4px', 
                  background: bodyguardStatus.health_score >= 80 ? 'var(--success)' : bodyguardStatus.health_score >= 60 ? 'var(--accent2)' : 'var(--error)',
                  color: 'white'
                }}>
                  {bodyguardStatus.health_status}
                </span>
              </h3>
              
              <div style={{display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: '12px', marginBottom: '16px'}}>
                <div style={{padding: '12px', background: 'var(--glass)', borderRadius: '6px', textAlign: 'center'}}>
                  <div style={{fontSize: '1.8rem', fontWeight: 700, color: bodyguardStatus.health_score >= 80 ? 'var(--success)' : 'var(--error)'}}>{bodyguardStatus.health_score}</div>
                  <div style={{fontSize: '0.8rem', color: 'var(--muted)'}}>Health Score</div>
                </div>
                <div style={{padding: '12px', background: 'var(--glass)', borderRadius: '6px', textAlign: 'center'}}>
                  <div style={{fontSize: '1.8rem', fontWeight: 700, color: 'var(--text)'}}>{bodyguardStatus.system_health?.cpu_usage}%</div>
                  <div style={{fontSize: '0.8rem', color: 'var(--muted)'}}>CPU</div>
                </div>
                <div style={{padding: '12px', background: 'var(--glass)', borderRadius: '6px', textAlign: 'center'}}>
                  <div style={{fontSize: '1.8rem', fontWeight: 700, color: 'var(--text)'}}>{bodyguardStatus.system_health?.memory_usage}%</div>
                  <div style={{fontSize: '0.8rem', color: 'var(--muted)'}}>Memory</div>
                </div>
                <div style={{padding: '12px', background: 'var(--glass)', borderRadius: '6px', textAlign: 'center'}}>
                  <div style={{fontSize: '1.8rem', fontWeight: 700, color: 'var(--accent)'}}>{bodyguardStatus.trading_health?.active_bots}</div>
                  <div style={{fontSize: '0.8rem', color: 'var(--muted)'}}>Active Bots</div>
                </div>
              </div>
              
              {(bodyguardStatus.issues?.length > 0 || bodyguardStatus.warnings?.length > 0) && (
                <div style={{marginTop: '16px'}}>
                  {bodyguardStatus.issues?.length > 0 && (
                    <div style={{marginBottom: '12px', padding: '12px', background: 'rgba(239, 68, 68, 0.1)', borderRadius: '6px', border: '1px solid var(--error)'}}>
                      <div style={{fontWeight: 600, color: 'var(--error)', marginBottom: '8px'}}>🚨 Critical Issues ({bodyguardStatus.issues.length})</div>
                      <ul style={{margin: 0, paddingLeft: '20px', fontSize: '0.85rem', color: 'var(--text)'}}>
                        {bodyguardStatus.issues.map((issue, idx) => (
                          <li key={idx} style={{marginBottom: '4px'}}>{issue}</li>
          ))}
                      </ul>
                    </div>
                  )}
                  
                  {bodyguardStatus.warnings?.length > 0 && (
                    <div style={{padding: '12px', background: 'rgba(245, 158, 11, 0.1)', borderRadius: '6px', border: '1px solid var(--accent2)'}}>
                      <div style={{fontWeight: 600, color: 'var(--accent2)', marginBottom: '8px'}}>⚠️ Warnings ({bodyguardStatus.warnings.length})</div>
                      <ul style={{margin: 0, paddingLeft: '20px', fontSize: '0.85rem', color: 'var(--text)'}}>
                        {bodyguardStatus.warnings.map((warning, idx) => (
                          <li key={idx} style={{marginBottom: '4px'}}>{warning}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              )}
              
              <div style={{marginTop: '12px', fontSize: '0.75rem', color: 'var(--muted)', textAlign: 'right'}}>
                Last check: {formatDate(bodyguardStatus.timestamp)}
              </div>
            </div>
          )}
          
          {/* User Storage Tracking */}
          {storageData && (
            <div style={{marginTop: '24px', padding: '20px', background: 'var(--panel)', borderRadius: '8px', border: '1px solid var(--line)'}}>
              <h3 style={{marginBottom: '16px', color: 'var(--accent)'}}>💾 User Storage Tracking</h3>
              
              <div style={{marginBottom: '16px', padding: '12px', background: 'var(--glass)', borderRadius: '6px', display: 'flex', justifyContent: 'space-between', alignItems: 'center'}}>
                <div>
                  <div style={{fontSize: '0.85rem', color: 'var(--muted)'}}>Total System Storage</div>
                  <div style={{fontSize: '1.5rem', fontWeight: 700, color: 'var(--text)'}}>{storageTotals ? safeToFixed(storageTotals.totalMb, 2) : '0.00'} MB</div>
                </div>
                <div>
                  <div style={{fontSize: '0.85rem', color: 'var(--muted)'}}>Total Users</div>
                  <div style={{fontSize: '1.5rem', fontWeight: 700, color: 'var(--accent)'}}>{storageTotals ? safeNumber(storageTotals.totalUsers, 0) : 0}</div>
                </div>
              </div>
              
              <div style={{maxHeight: '400px', overflowY: 'auto'}}>
                <table style={{width: '100%', borderCollapse: 'collapse', fontSize: '0.85rem'}}>
                  <thead style={{position: 'sticky', top: 0, background: 'var(--panel)'}}>
                    <tr style={{borderBottom: '2px solid var(--line)'}}>
                      <th style={{padding: '12px', textAlign: 'left', color: 'var(--muted)', fontWeight: 600}}>User</th>
                      <th style={{padding: '12px', textAlign: 'center', color: 'var(--muted)', fontWeight: 600}}>Chats</th>
                      <th style={{padding: '12px', textAlign: 'center', color: 'var(--muted)', fontWeight: 600}}>Trades</th>
                      <th style={{padding: '12px', textAlign: 'center', color: 'var(--muted)', fontWeight: 600}}>Bots</th>
                      <th style={{padding: '12px', textAlign: 'center', color: 'var(--muted)', fontWeight: 600}}>Total</th>
                    </tr>
                  </thead>
                  <tbody>
                    {storageData.users?.map((usr, idx) => (
                      <tr key={idx} style={{borderBottom: '1px solid var(--line)'}}>
                        <td style={{padding: '12px'}}>
                          <div>{usr.name || 'Unknown'}</div>
                          <div style={{fontSize: '0.75rem', color: 'var(--muted)'}}>{usr.email}</div>
                        </td>
                        <td style={{padding: '12px', textAlign: 'center'}}>
                          <div style={{fontWeight: 600}}>{safeToFixed(usr.storage_breakdown?.chat_messages?.size_mb, 2)} MB</div>
                          <div style={{fontSize: '0.75rem', color: 'var(--muted)'}}>{usr.storage_breakdown?.chat_messages?.count} msgs</div>
                        </td>
                        <td style={{padding: '12px', textAlign: 'center'}}>
                          <div style={{fontWeight: 600}}>{safeToFixed(usr.storage_breakdown?.trades?.size_mb, 2)} MB</div>
                          <div style={{fontSize: '0.75rem', color: 'var(--muted)'}}>{usr.storage_breakdown?.trades?.count} trades</div>
                        </td>
                        <td style={{padding: '12px', textAlign: 'center'}}>
                          <div style={{fontWeight: 600}}>{safeToFixed(usr.storage_breakdown?.bots?.size_mb, 2)} MB</div>
                          <div style={{fontSize: '0.75rem', color: 'var(--muted)'}}>{usr.storage_breakdown?.bots?.count} bots</div>
                        </td>
                        <td style={{padding: '12px', textAlign: 'center'}}>
                          <span style={{
                            padding: '6px 12px',
                            borderRadius: '4px',
                            fontWeight: 700,
                            background: usr.total_storage_mb > 10 ? 'rgba(245, 158, 11, 0.2)' : 'rgba(16, 185, 129, 0.2)',
                            color: usr.total_storage_mb > 10 ? 'var(--accent2)' : 'var(--success)'
                          }}>
                            {safeToFixed(usr.total_storage_mb, 2)} MB
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
          
          {/* User Management Table - Interactive */}
          <div className="admin-card">
            <div style={{display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px'}}>
              <h3 style={{margin: 0, color: 'var(--accent)', fontWeight: 'bold'}}>👥 User Management</h3>
              <button
                onClick={loadAdminUsers}
                disabled={loadingUsers}
                style={{
                  padding: '8px 16px',
                  fontSize: '0.85rem',
                  background: 'var(--accent2)',
                  color: 'white',
                  border: 'none',
                  borderRadius: '4px',
                  cursor: loadingUsers ? 'not-allowed' : 'pointer',
                  opacity: loadingUsers ? 0.6 : 1,
                  fontWeight: 600
                }}
              >
                {loadingUsers ? '⏳ Loading...' : '🔄 Refresh'}
              </button>
            </div>
            
            {loadingUsers ? (
              <div style={{textAlign: 'center', padding: '40px', color: 'var(--muted)'}}>
                Loading users...
              </div>
            ) : adminUsers.length === 0 ? (
              <div style={{textAlign: 'center', padding: '40px', color: 'var(--muted)'}}>
                No users found
              </div>
            ) : (
              <div style={{overflowX: 'auto'}}>
                <table style={{width: '100%', borderCollapse: 'collapse', fontSize: '0.85rem'}}>
                  <thead>
                    <tr style={{borderBottom: '2px solid var(--line)'}}>
                      <th style={{padding: '12px', textAlign: 'left', color: 'var(--muted)', fontWeight: 600}}>Username</th>
                      <th style={{padding: '12px', textAlign: 'left', color: 'var(--muted)', fontWeight: 600}}>Email</th>
                      <th style={{padding: '12px', textAlign: 'center', color: 'var(--muted)', fontWeight: 600}}>Role</th>
                      <th style={{padding: '12px', textAlign: 'center', color: 'var(--muted)', fontWeight: 600}}>Status</th>
                      <th style={{padding: '12px', textAlign: 'center', color: 'var(--muted)', fontWeight: 600}}>API Keys</th>
                      <th style={{padding: '12px', textAlign: 'center', color: 'var(--muted)', fontWeight: 600}}>Bots</th>
                      <th style={{padding: '12px', textAlign: 'center', color: 'var(--muted)', fontWeight: 600}}>Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {adminUsers.map(usr => (
                      <tr key={usr.id} style={{borderBottom: '1px solid var(--line)'}}>
                        <td style={{padding: '12px'}}>{usr.first_name || NOT_AVAILABLE}</td>
                        <td style={{padding: '12px'}}>{usr.email}</td>
                        <td style={{padding: '12px', textAlign: 'center'}}>
                          <span style={{
                            padding: '4px 8px',
                            borderRadius: '4px',
                            fontSize: '0.75rem',
                            fontWeight: 600,
                            background: usr.role === 'admin' ? 'var(--accent2)' : 'var(--glass)',
                            color: usr.role === 'admin' ? 'white' : 'var(--text)'
                          }}>
                            {usr.role || 'user'}
                          </span>
                        </td>
                        <td style={{padding: '12px', textAlign: 'center'}}>
                          <span style={{
                            padding: '4px 8px',
                            borderRadius: '4px',
                            fontSize: '0.75rem',
                            fontWeight: 600,
                            background: usr.status === 'blocked' ? 'var(--error)' : 'var(--success)',
                            color: 'white'
                          }}>
                            {usr.status === 'blocked' ? '🚫 Blocked' : '✓ Active'}
                          </span>
                        </td>
                        <td style={{padding: '12px', textAlign: 'center'}}>
                          {usr.api_keys_count > 0 ? `✓ ${usr.api_keys_count}` : NOT_AVAILABLE}
                        </td>
                        <td style={{padding: '12px', textAlign: 'center', fontWeight: 600}}>
                          {usr.bots_count || 0}
                        </td>
                        <td style={{padding: '12px', textAlign: 'center'}}>
                          <div style={{display: 'flex', gap: '4px', justifyContent: 'center', flexWrap: 'wrap'}}>
                            <button
                              onClick={() => handleResetPassword(usr.id)}
                              disabled={actionLoading[`reset-${usr.id}`]}
                              style={{
                                padding: '4px 8px',
                                fontSize: '0.75rem',
                                background: actionLoading[`reset-${usr.id}`] ? '#666' : 'var(--accent2)',
                                color: 'white',
                                border: 'none',
                                borderRadius: '4px',
                                cursor: actionLoading[`reset-${usr.id}`] ? 'not-allowed' : 'pointer',
                                opacity: actionLoading[`reset-${usr.id}`] ? 0.6 : 1,
                                fontWeight: 600
                              }}
                            >
                              {actionLoading[`reset-${usr.id}`] ? '...' : '🔑 Reset PW'}
                            </button>
                            <button
                              onClick={() => handleToggleBlockUser(usr.id, usr.status)}
                              disabled={actionLoading[`block-${usr.id}`]}
                              style={{
                                padding: '4px 8px',
                                fontSize: '0.75rem',
                                background: actionLoading[`block-${usr.id}`] ? '#666' : (usr.status === 'blocked' ? 'var(--success)' : 'var(--accent2)'),
                                color: 'white',
                                border: 'none',
                                borderRadius: '4px',
                                cursor: actionLoading[`block-${usr.id}`] ? 'not-allowed' : 'pointer',
                                opacity: actionLoading[`block-${usr.id}`] ? 0.6 : 1,
                                fontWeight: 600
                              }}
                            >
                              {actionLoading[`block-${usr.id}`] ? '...' : (usr.status === 'blocked' ? '✓ Unblock' : '🚫 Block')}
                            </button>
                            <button
                              onClick={() => handleDeleteUserAdmin(usr.id)}
                              disabled={actionLoading[`delete-${usr.id}`]}
                              style={{
                                padding: '4px 8px',
                                fontSize: '0.75rem',
                                background: actionLoading[`delete-${usr.id}`] ? '#666' : 'var(--error)',
                                color: 'white',
                                border: 'none',
                                borderRadius: '4px',
                                cursor: actionLoading[`delete-${usr.id}`] ? 'not-allowed' : 'pointer',
                                opacity: actionLoading[`delete-${usr.id}`] ? 0.6 : 1,
                                fontWeight: 600
                              }}
                            >
                              {actionLoading[`delete-${usr.id}`] ? '...' : '🗑️ Delete'}
                            </button>
                            <button
                              onClick={() => handleForceLogout(usr.id)}
                              disabled={actionLoading[`logout-${usr.id}`]}
                              style={{
                                padding: '4px 8px',
                                fontSize: '0.75rem',
                                background: actionLoading[`logout-${usr.id}`] ? '#666' : '#ef4444',
                                color: 'white',
                                border: 'none',
                                borderRadius: '4px',
                                cursor: actionLoading[`logout-${usr.id}`] ? 'not-allowed' : 'pointer',
                                opacity: actionLoading[`logout-${usr.id}`] ? 0.6 : 1,
                                fontWeight: 600
                              }}
                            >
                              {actionLoading[`logout-${usr.id}`] ? '...' : '🚪 Logout'}
                            </button>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
          
          {/* Bot Override Panel - Interactive */}
          <div className="admin-card">
            <div style={{display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px'}}>
              <h3 style={{margin: 0, color: 'var(--accent)', fontWeight: 'bold'}}>🤖 Bot Control Panel</h3>
              <button
                onClick={loadAdminBots}
                disabled={loadingBots}
                style={{
                  padding: '8px 16px',
                  fontSize: '0.85rem',
                  background: 'var(--accent2)',
                  color: 'white',
                  border: 'none',
                  borderRadius: '4px',
                  cursor: loadingBots ? 'not-allowed' : 'pointer',
                  opacity: loadingBots ? 0.6 : 1,
                  fontWeight: 600
                }}
              >
                {loadingBots ? '⏳ Loading...' : '🔄 Refresh'}
              </button>
            </div>
            
            {/* User and Bot Selection */}
            <div style={{marginBottom: '20px', padding: '16px', background: 'var(--glass)', borderRadius: '6px', border: '1px solid var(--accent)'}}>
              <h4 style={{margin: '0 0 12px 0', color: 'var(--accent)', fontSize: '0.9rem', fontWeight: 'bold'}}>🎯 Select Target</h4>
              {!loadingBots && adminBots.length === 0 && (
                <div className="admin-empty" style={{marginBottom: '12px'}}>
                  No bots are currently registered for any users.
                </div>
              )}
              <div style={{display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(250px, 1fr))', gap: '12px'}}>
                {/* User Selection */}
                <div>
                  <label style={{display: 'block', fontSize: '0.85rem', color: 'var(--text)', marginBottom: '6px', fontWeight: 600}}>
                    Select User
                  </label>
                  <select
                    value={selectedUserId}
                    onChange={(e) => handleUserSelection(e.target.value)}
                    style={{
                      width: '100%',
                      padding: '8px 12px',
                      fontSize: '0.85rem',
                      background: 'var(--panel)',
                      color: 'var(--text)',
                      border: '1px solid var(--line)',
                      borderRadius: '4px',
                      cursor: 'pointer',
                      fontWeight: 600
                    }}
                  >
                    <option value="">-- Select a User --</option>
                    {adminUsers.map(usr => (
                      <option key={usr.id} value={usr.id}>
                        {usr.name || usr.first_name || usr.email} ({usr.email})
                      </option>
                    ))}
                  </select>
                </div>
                
                {/* Bot Selection */}
                <div>
                  <label style={{display: 'block', fontSize: '0.85rem', color: 'var(--text)', marginBottom: '6px', fontWeight: 600}}>
                    Select Bot
                  </label>
                  <select
                    value={selectedBotId}
                    onChange={(e) => setSelectedBotId(e.target.value)}
                    disabled={!selectedUserId}
                    style={{
                      width: '100%',
                      padding: '8px 12px',
                      fontSize: '0.85rem',
                      background: selectedUserId ? 'var(--panel)' : '#e0e0e0',
                      color: selectedUserId ? 'var(--text)' : '#999',
                      border: '1px solid var(--line)',
                      borderRadius: '4px',
                      cursor: selectedUserId ? 'pointer' : 'not-allowed',
                      fontWeight: 600
                    }}
                  >
                    <option value="">-- Select a Bot --</option>
                    {filteredAdminBots.map(bot => (
                      <option key={bot.bot_id} value={bot.bot_id}>
                        {bot.name} ({bot.exchange?.toUpperCase()}) - {bot.mode === 'live' ? '💰 Live' : '📝 Paper'}
                      </option>
                    ))}
                  </select>
                </div>
              </div>
              
              {selectedUserId && filteredAdminBots.length === 0 && (
                <div style={{marginTop: '12px', padding: '8px 12px', background: 'rgba(245, 158, 11, 0.1)', borderRadius: '4px', fontSize: '0.8rem', color: 'var(--accent2)'}}>
                  ⚠️ Selected user has no bots
                </div>
              )}
            </div>
            
            {/* Bot Actions - Only visible when bot is selected */}
            {selectedBotId && (() => {
              const selectedBot = filteredAdminBots.find(b => b.bot_id === selectedBotId);
              if (!selectedBot) return null;
              
              return (
                <div style={{padding: '16px', background: 'var(--glass)', borderRadius: '6px', border: '1px solid var(--success)'}}>
                  <h4 style={{margin: '0 0 12px 0', color: 'var(--success)', fontSize: '0.9rem'}}>⚙️ Bot Actions</h4>
                  
                  {/* Bot Info */}
                  <div style={{marginBottom: '16px', padding: '12px', background: 'var(--panel)', borderRadius: '4px'}}>
                    <div style={{fontWeight: 700, fontSize: '1rem', marginBottom: '4px'}}>{selectedBot.name}</div>
                    <div style={{fontSize: '0.8rem', color: 'var(--muted)'}}>
                      User: {selectedBot.username} • Exchange: {selectedBot.exchange?.toUpperCase()} • 
                      Status: {selectedBot.status === 'active' ? '▶ Active' : selectedBot.status === 'paused' ? '⏸ Paused' : '⏹ Stopped'}
                    </div>
                    <div style={{fontSize: '0.8rem', color: 'var(--muted)', marginTop: '4px'}}>
                      Mode: {selectedBot.mode === 'live' ? '💰 Live Trading' : '📝 Paper Trading'} • 
                      Capital: {formatZAR(selectedBot.current_capital)} • 
                      P/L: {formatZAR(selectedBot.profit_loss)}
                    </div>
                  </div>
                  
                  {/* Action Buttons */}
                  <div style={{display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: '8px'}}>
                    {/* Pause/Resume */}
                    <button
                      onClick={() => handleToggleBotPause(selectedBot.bot_id, selectedBot.status)}
                      disabled={actionLoading[`pause-${selectedBot.bot_id}`]}
                      style={{
                        padding: '10px 16px',
                        fontSize: '0.85rem',
                        background: actionLoading[`pause-${selectedBot.bot_id}`] ? '#666' : (selectedBot.status === 'active' ? 'var(--accent2)' : 'var(--success)'),
                        color: 'white',
                        border: 'none',
                        borderRadius: '4px',
                        cursor: actionLoading[`pause-${selectedBot.bot_id}`] ? 'not-allowed' : 'pointer',
                        opacity: actionLoading[`pause-${selectedBot.bot_id}`] ? 0.6 : 1,
                        fontWeight: 600
                      }}
                    >
                      {actionLoading[`pause-${selectedBot.bot_id}`] ? '...' : (selectedBot.status === 'active' ? '⏸ Pause Bot' : '▶ Resume Bot')}
                    </button>
                    
                    {/* Change Mode: Paper */}
                    <button
                      onClick={() => handleChangeBotMode(selectedBot.bot_id, 'paper')}
                      disabled={actionLoading[`mode-${selectedBot.bot_id}`] || selectedBot.mode === 'paper'}
                      style={{
                        padding: '10px 16px',
                        fontSize: '0.85rem',
                        background: selectedBot.mode === 'paper' ? 'var(--success)' : (actionLoading[`mode-${selectedBot.bot_id}`] ? '#666' : 'var(--glass)'),
                        color: selectedBot.mode === 'paper' ? 'white' : 'var(--text)',
                        border: '1px solid var(--line)',
                        borderRadius: '4px',
                        cursor: (actionLoading[`mode-${selectedBot.bot_id}`] || selectedBot.mode === 'paper') ? 'not-allowed' : 'pointer',
                        opacity: (actionLoading[`mode-${selectedBot.bot_id}`] || selectedBot.mode === 'paper') ? 0.6 : 1,
                        fontWeight: 600
                      }}
                    >
                      {selectedBot.mode === 'paper' ? '✓ Paper Mode' : '📝 Set Paper'}
                    </button>
                    
                    {/* Change Mode: Live */}
                    <button
                      onClick={() => handleChangeBotMode(selectedBot.bot_id, 'live')}
                      disabled={actionLoading[`mode-${selectedBot.bot_id}`] || selectedBot.mode === 'live'}
                      style={{
                        padding: '10px 16px',
                        fontSize: '0.85rem',
                        background: selectedBot.mode === 'live' ? 'var(--accent2)' : (actionLoading[`mode-${selectedBot.bot_id}`] ? '#666' : 'var(--glass)'),
                        color: selectedBot.mode === 'live' ? 'white' : 'var(--text)',
                        border: '1px solid var(--line)',
                        borderRadius: '4px',
                        cursor: (actionLoading[`mode-${selectedBot.bot_id}`] || selectedBot.mode === 'live') ? 'not-allowed' : 'pointer',
                        opacity: (actionLoading[`mode-${selectedBot.bot_id}`] || selectedBot.mode === 'live') ? 0.6 : 1,
                        fontWeight: 600
                      }}
                    >
                      {selectedBot.mode === 'live' ? '✓ Live Mode' : '💰 Set Live'}
                    </button>
                    
                    {/* Change Exchange */}
                    <div>
                      <select
                        value={selectedBot.exchange}
                        onChange={(e) => handleChangeBotExchange(selectedBot.bot_id, e.target.value)}
                        disabled={actionLoading[`exchange-${selectedBot.bot_id}`]}
                        style={{
                          width: '100%',
                          padding: '10px 12px',
                          fontSize: '0.85rem',
                          background: 'var(--glass)',
                          color: 'var(--text)',
                          border: '1px solid var(--line)',
                          borderRadius: '4px',
                          cursor: actionLoading[`exchange-${selectedBot.bot_id}`] ? 'not-allowed' : 'pointer',
                          opacity: actionLoading[`exchange-${selectedBot.bot_id}`] ? 0.6 : 1,
                          fontWeight: 600
                        }}
                      >
                        <option value="binance">Binance</option>
                        <option value="luno">Luno</option>
                        <option value="kucoin">KuCoin</option>
                        <option value="bybit">Bybit</option>
                        <option value="kraken">Kraken</option>
                        <option value="bitget">Bitget</option>
                        <option value="gate">Gate.io</option>
                      </select>
                    </div>
                  </div>
                  
                  <div style={{marginTop: '12px', padding: '10px', background: 'rgba(59, 130, 246, 0.1)', borderRadius: '4px', fontSize: '0.75rem', color: 'var(--muted)'}}>
                    ℹ️ All admin actions are logged in the audit trail. Actions apply ONLY to the selected bot.
                  </div>
                </div>
              );
            })()}
            
            {!selectedBotId && (
              <div style={{textAlign: 'center', padding: '40px', color: 'var(--muted)', fontSize: '0.9rem'}}>
                👆 Select a user and bot above to perform admin actions
              </div>
            )}
          </div>

          <div className="admin-card">
            <h3 style={{marginBottom: '12px', color: 'var(--accent)'}}>🚨 Emergency Stop Overrides (Admin-only)</h3>
            <p style={{fontSize: '0.8rem', color: 'var(--muted)', marginBottom: '12px'}}>
              This panel is available only after admin unlock. Every change is recorded in the audit trail.
            </p>
            <div style={{display: 'flex', gap: '8px', flexWrap: 'wrap', marginBottom: '12px'}}>
              <button onClick={() => updateGlobalEmergencyOverride(true)} style={{padding: '8px 12px', borderRadius: '6px', border: '1px solid var(--line)', background: 'var(--error)', color: '#fff', fontWeight: 600, cursor: 'pointer'}}>
                Disable Emergency Stop (Global)
              </button>
              <button onClick={() => updateGlobalEmergencyOverride(false)} style={{padding: '8px 12px', borderRadius: '6px', border: '1px solid var(--line)', background: 'var(--success)', color: '#fff', fontWeight: 600, cursor: 'pointer'}}>
                Re-enable Emergency Stop (Global)
              </button>
            </div>
            <div style={{fontSize: '0.8rem', color: 'var(--muted)', marginBottom: '8px'}}>
              Global override: {emergencyOverrideStatus?.global?.disabled ? 'Disabled' : 'Enabled'} • Last change: {formatDate(emergencyOverrideStatus?.global?.updated_at)}
            </div>
            <div style={{display: 'flex', gap: '8px', alignItems: 'center', flexWrap: 'wrap'}}>
              <select value={selectedUserId} onChange={(e) => setSelectedUserId(e.target.value)} style={{padding: '8px', borderRadius: '6px', border: '1px solid var(--line)', background: 'var(--panel)', color: '#fff'}}>
                <option value="">Select user for override</option>
                {adminUsers.map((usr) => (
                  <option key={usr.id} value={usr.id}>{usr.email || usr.id}</option>
                ))}
              </select>
              <button onClick={() => updateUserEmergencyOverride(selectedUserId, true)} disabled={!selectedUserId} style={{padding: '8px 12px', borderRadius: '6px', border: '1px solid var(--line)', background: 'var(--accent2)', color: '#fff', cursor: selectedUserId ? 'pointer' : 'not-allowed'}}>
                Disable for User
              </button>
              <button onClick={() => updateUserEmergencyOverride(selectedUserId, false)} disabled={!selectedUserId} style={{padding: '8px 12px', borderRadius: '6px', border: '1px solid var(--line)', background: 'var(--success)', color: '#fff', cursor: selectedUserId ? 'pointer' : 'not-allowed'}}>
                Re-enable for User
              </button>
              <button onClick={() => clearUserEmergencyOverride(selectedUserId)} disabled={!selectedUserId} style={{padding: '8px 12px', borderRadius: '6px', border: '1px solid var(--line)', background: 'var(--panel)', color: '#fff', cursor: selectedUserId ? 'pointer' : 'not-allowed'}}>
                Clear User Override
              </button>
            </div>
          </div>
          
          {/* Admin Tools - All in One Section */}
          <div className="admin-card">
            <h3 style={{marginBottom: '16px', color: 'var(--accent)'}}>🛠️ System Administration</h3>
            
            <div style={{display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '12px'}}>
              <button 
                onClick={handleTriggerBodyguard}
                disabled={aiTaskLoading === 'bodyguard'}
                style={{
                  padding: '12px 16px',
                  background: aiTaskLoading === 'bodyguard' ? '#666' : 'linear-gradient(135deg, var(--accent2) 0%, var(--accent2) 100%)',
                  color: 'white',
                  border: 'none',
                  borderRadius: '6px',
                  cursor: aiTaskLoading === 'bodyguard' ? 'wait' : 'pointer',
                  fontWeight: 600,
                  fontSize: '0.9rem',
                  transition: 'transform 0.2s',
                  opacity: aiTaskLoading === 'bodyguard' ? 0.7 : 1
                }}
                onMouseEnter={(e) => e.currentTarget.style.transform = 'scale(1.02)'}
                onMouseLeave={(e) => e.currentTarget.style.transform = 'scale(1)'}
              >
                {aiTaskLoading === 'bodyguard' ? '⏳ Scanning...' : '🛡️ AI Bodyguard'}
              </button>
              
              <button 
                onClick={handleEmailAllUsers}
                style={{
                  padding: '12px 16px',
                  background: 'linear-gradient(135deg, var(--success) 0%, var(--success) 100%)',
                  color: 'white',
                  border: 'none',
                  borderRadius: '6px',
                  cursor: 'pointer',
                  fontWeight: 600,
                  fontSize: '0.9rem',
                  transition: 'transform 0.2s'
                }}
                onMouseEnter={(e) => e.currentTarget.style.transform = 'scale(1.02)'}
                onMouseLeave={(e) => e.currentTarget.style.transform = 'scale(1)'}
              >
                📧 Email All Users
              </button>
              
              <button 
                onClick={async () => {
                  try {
                    const res = await axios.get(`${API}/admin/health`, axiosConfig);
                    const services = {
                      database: res.data?.database?.status || 'unknown',
                      scheduler: res.data?.scheduler?.running ? 'healthy' : 'degraded'
                    };
                    const score = res.data?.status === 'ok' ? 100 : 60;
                    
                    let statusHTML = `Health Score: ${score}/100\n\n`;
                    statusHTML += 'Services Status:\n';
                    Object.entries(services).forEach(([name, status]) => {
                      const emoji = status === 'healthy' ? '✅' : '❌';
                      statusHTML += `${emoji} ${name}: ${status}\n`;
                    });
                    
                    // Add health report to chat
                    const reportMsg = `System Health Report (${score}/100)\n\n${statusHTML}`;
                    setChatMessages(prev => [...prev, 
                      { role: 'user', content: 'Check system health' },
                      { role: 'assistant', type: 'system', content: reportMsg }
                    ]);
                    
                    // Redirect to chat section
                    setActiveSection('welcome');
                    setTimeout(() => showSection('welcome'), 100);
                    
                    showNotification(`System Health: ${score}/100 - Check chat for details`, score >= 80 ? 'success' : 'warning');
                  } catch (err) {
                    showNotification('Health check failed', 'error');
                  }
                }}
                style={{
                  padding: '12px 16px',
                  background: 'linear-gradient(135deg, var(--accent2) 0%, var(--accent2) 100%)',
                  color: 'white',
                  border: 'none',
                  borderRadius: '6px',
                  cursor: 'pointer',
                  fontWeight: 600,
                  fontSize: '0.9rem',
                  transition: 'transform 0.2s'
                }}
                onMouseEnter={(e) => e.currentTarget.style.transform = 'scale(1.02)'}
                onMouseLeave={(e) => e.currentTarget.style.transform = 'scale(1)'}
              >
                🏥 System Health
              </button>
            </div>
            
            <p style={{fontSize: '0.75rem', color: 'var(--muted)', marginTop: '12px', lineHeight: '1.5'}}>
              Monitor system health, send notifications, and check backend services in real-time
            </p>
          </div>
          
          {/* Admin Utilities */}
          <div className="admin-card">
            <h3 style={{marginBottom: '16px', color: 'var(--text)', display: 'flex', alignItems: 'center', gap: '8px'}}>
              🔐 Encryption Utilities
              <span style={{fontSize: '0.75rem', fontWeight: 'normal', color: 'var(--muted)'}}>
                (Admin-only maintenance)
              </span>
            </h3>
            
            <div style={{display: 'grid', gap: '12px'}}>
              <div style={{
                padding: '16px',
                background: 'var(--panel)',
                borderRadius: '8px',
                border: '1px solid rgba(245, 158, 11, 0.4)'
              }}>
                <div style={{marginBottom: '12px'}}>
                  <h4 style={{margin: '0 0 8px 0', color: 'var(--text)', fontSize: '1rem'}}>
                    🔐 Migrate API Key Encryption
                  </h4>
                  <p style={{fontSize: '0.85rem', color: 'var(--muted)', margin: 0, lineHeight: '1.5'}}>
                    Re-encrypt stored API keys using the dedicated AMARKTAI_FERNET_KEY. Run once after rotating encryption keys.
                  </p>
                </div>
                <button
                  onClick={handleMigrateApiKeys}
                  style={{
                    padding: '10px 20px',
                    background: 'linear-gradient(135deg, var(--accent2) 0%, var(--accent2) 100%)',
                    color: 'white',
                    border: 'none',
                    borderRadius: '6px',
                    cursor: 'pointer',
                    fontWeight: 600,
                    fontSize: '0.9rem',
                    width: '100%'
                  }}
                  onMouseEnter={(e) => e.currentTarget.style.opacity = '0.9'}
                  onMouseLeave={(e) => e.currentTarget.style.opacity = '1'}
                >
                  🔐 Migrate API Keys
                </button>
              </div>
            </div>
          </div>
          
          <div className="admin-card" style={{borderColor: 'var(--error)'}}>
            <p style={{color: 'var(--error)', fontWeight: 600, marginBottom: '8px'}}>⚠️ Admin Warning</p>
            <p style={{color: 'var(--muted)'}}>
              You have full control over all users. Use these powers responsibly. All actions are logged.
            </p>
          </div>
        </div>
        </div>
      </section>
  );
}
