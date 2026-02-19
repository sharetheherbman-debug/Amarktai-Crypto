import React, { useState, useEffect } from 'react';
import { ChevronDown, ChevronRight, Play, Pause, Square, RefreshCw } from 'lucide-react';
import { getPlatformDisplayName, getPlatformIcon } from '../../../constants/platforms';

const NOT_AVAILABLE = 'Not available';

const formatZAR = (value, digits = 2) => {
  const num = Number(value);
  if (!Number.isFinite(num)) return NOT_AVAILABLE;
  const formatted = Math.abs(num).toLocaleString('en-US', { minimumFractionDigits: digits, maximumFractionDigits: digits });
  return `${num < 0 ? '-R' : 'R'}${formatted}`;
};

const formatDate = (value) => {
  if (!value) return NOT_AVAILABLE;
  try {
    const date = new Date(value);
    if (isNaN(date.getTime())) return NOT_AVAILABLE;
    return date.toLocaleString('en-US', { 
      month: 'short', day: 'numeric', 
      hour: '2-digit', minute: '2-digit' 
    });
  } catch {
    return NOT_AVAILABLE;
  }
};

const getBotStatusBadge = (bot) => {
  const status = bot.status || 'unknown';
  const isActive = status === 'active';
  const isPaused = status === 'paused' || bot.paused_at;
  const isTraining = bot.training_complete === false;
  
  if (isTraining) {
    return { text: 'Training', color: '#60a5fa', bg: 'rgba(96, 165, 250, 0.15)' };
  }
  if (isActive) {
    return { text: 'Active', color: '#22c55e', bg: 'rgba(34, 197, 94, 0.15)' };
  }
  if (isPaused) {
    return { text: 'Paused', color: '#f59e0b', bg: 'rgba(245, 158, 11, 0.15)' };
  }
  return { text: status, color: '#9ca3af', bg: 'rgba(156, 163, 175, 0.15)' };
};

const BotFleetItem = ({ bot, isExpanded, onToggle, onControl, controlLoading }) => {
  const statusBadge = getBotStatusBadge(bot);
  const mode = bot.trading_mode || bot.mode || 'paper';
  const isLive = mode === 'live';
  const isActive = bot.status === 'active';
  const isPaused = bot.status === 'paused';
  const profit = bot.profit ?? bot.profit_loss ?? bot.pnl ?? 0;
  const isProfitable = profit > 0;
  
  const handleControlClick = (action, e) => {
    e.stopPropagation();
    onControl(bot.id, action);
  };
  
  return (
    <div style={{
      background: 'var(--glass)',
      border: '1px solid var(--line)',
      borderRadius: '12px',
      marginBottom: '8px',
      overflow: 'hidden',
      transition: 'all 0.2s ease'
    }}>
      {/* Bot Row - Clickable */}
      <div
        onClick={onToggle}
        style={{
          padding: '16px',
          cursor: 'pointer',
          display: 'flex',
          alignItems: 'center',
          gap: '12px',
          transition: 'background 0.2s ease'
        }}
        onMouseEnter={(e) => e.currentTarget.style.background = 'rgba(96, 165, 250, 0.05)'}
        onMouseLeave={(e) => e.currentTarget.style.background = 'transparent'}
      >
        {/* Expand Icon */}
        <div style={{ flexShrink: 0, color: 'var(--muted)' }}>
          {isExpanded ? <ChevronDown size={20} /> : <ChevronRight size={20} />}
        </div>
        
        {/* Bot Name & Exchange */}
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ 
            fontWeight: 600, 
            color: 'var(--text)',
            marginBottom: '4px',
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap'
          }}>
            {bot.name || 'Unnamed Bot'}
          </div>
          <div style={{ fontSize: '0.85rem', color: 'var(--muted)', display: 'flex', gap: '8px', alignItems: 'center' }}>
            <span>{getPlatformDisplayName(bot.exchange)}</span>
            <span>•</span>
            <span>{bot.pair || bot.symbol || 'N/A'}</span>
          </div>
        </div>
        
        {/* Status Badge */}
        <div style={{
          padding: '4px 12px',
          borderRadius: '6px',
          fontSize: '0.85rem',
          fontWeight: 600,
          background: statusBadge.bg,
          color: statusBadge.color,
          whiteSpace: 'nowrap'
        }}>
          {statusBadge.text}
        </div>
        
        {/* Mode Badge */}
        <div style={{
          padding: '4px 8px',
          borderRadius: '6px',
          fontSize: '0.75rem',
          fontWeight: 600,
          background: isLive ? 'rgba(239, 68, 68, 0.15)' : 'rgba(59, 130, 246, 0.15)',
          color: isLive ? '#ef4444' : '#3b82f6',
          whiteSpace: 'nowrap'
        }}>
          {isLive ? 'Live' : 'Paper'}
        </div>
        
        {/* Profit */}
        <div style={{
          fontSize: '0.95rem',
          fontWeight: 600,
          color: isProfitable ? 'var(--success)' : (profit < 0 ? 'var(--error)' : 'var(--muted)'),
          minWidth: '100px',
          textAlign: 'right'
        }}>
          {formatZAR(profit)}
        </div>
      </div>
      
      {/* Expanded Panel */}
      {isExpanded && (
        <div style={{
          borderTop: '1px solid var(--line)',
          padding: '16px',
          background: 'rgba(0, 0, 0, 0.2)'
        }}>
          {/* Details Grid */}
          <div style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
            gap: '16px',
            marginBottom: '16px'
          }}>
            {/* Performance */}
            <div>
              <div style={{ fontSize: '0.75rem', color: 'var(--muted)', marginBottom: '8px', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                Performance
              </div>
              <div style={{ fontSize: '0.9rem', lineHeight: 1.6 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px' }}>
                  <span style={{ color: 'var(--muted)' }}>Capital:</span>
                  <span style={{ color: 'var(--text)', fontWeight: 500 }}>{formatZAR(bot.current_capital)}</span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px' }}>
                  <span style={{ color: 'var(--muted)' }}>Trades:</span>
                  <span style={{ color: 'var(--text)', fontWeight: 500 }}>{bot.trades_count || 0}</span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                  <span style={{ color: 'var(--muted)' }}>Win Rate:</span>
                  <span style={{ color: 'var(--text)', fontWeight: 500 }}>
                    {bot.win_rate ? `${bot.win_rate.toFixed(1)}%` : 'N/A'}
                  </span>
                </div>
              </div>
            </div>
            
            {/* Last Activity */}
            <div>
              <div style={{ fontSize: '0.75rem', color: 'var(--muted)', marginBottom: '8px', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                Last Activity
              </div>
              <div style={{ fontSize: '0.9rem', lineHeight: 1.6 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px' }}>
                  <span style={{ color: 'var(--muted)' }}>Last Trade:</span>
                  <span style={{ color: 'var(--text)', fontWeight: 500, fontSize: '0.85rem' }}>
                    {formatDate(bot.last_trade_time || bot.last_trade_at)}
                  </span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px' }}>
                  <span style={{ color: 'var(--muted)' }}>Created:</span>
                  <span style={{ color: 'var(--text)', fontWeight: 500, fontSize: '0.85rem' }}>
                    {formatDate(bot.created_at)}
                  </span>
                </div>
              </div>
            </div>
            
            {/* Status & Errors */}
            <div>
              <div style={{ fontSize: '0.75rem', color: 'var(--muted)', marginBottom: '8px', textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                Status Info
              </div>
              <div style={{ fontSize: '0.9rem', lineHeight: 1.6 }}>
                {bot.paused_reason && (
                  <div style={{ marginBottom: '4px' }}>
                    <span style={{ color: 'var(--muted)' }}>Pause Reason:</span>
                    <div style={{ color: '#f59e0b', fontSize: '0.85rem', marginTop: '2px' }}>
                      {bot.paused_reason}
                    </div>
                  </div>
                )}
                {bot.last_error && (
                  <div style={{ marginBottom: '4px' }}>
                    <span style={{ color: 'var(--muted)' }}>Last Error:</span>
                    <div style={{ color: 'var(--error)', fontSize: '0.85rem', marginTop: '2px' }}>
                      {bot.last_error}
                    </div>
                  </div>
                )}
                {!bot.paused_reason && !bot.last_error && (
                  <div style={{ color: 'var(--success)', fontSize: '0.85rem' }}>
                    ✓ No issues detected
                  </div>
                )}
              </div>
            </div>
          </div>
          
          {/* Controls */}
          <div style={{
            display: 'flex',
            gap: '8px',
            paddingTop: '12px',
            borderTop: '1px solid var(--line)'
          }}>
            {!isActive && (
              <button
                onClick={(e) => handleControlClick('start', e)}
                disabled={controlLoading === bot.id}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '6px',
                  padding: '8px 16px',
                  borderRadius: '8px',
                  background: 'linear-gradient(135deg, #22c55e, #16a34a)',
                  color: 'white',
                  border: 'none',
                  fontSize: '0.9rem',
                  fontWeight: 600,
                  cursor: controlLoading === bot.id ? 'wait' : 'pointer',
                  opacity: controlLoading === bot.id ? 0.6 : 1,
                  transition: 'all 0.2s ease'
                }}
                onMouseEnter={(e) => !controlLoading && (e.currentTarget.style.opacity = '0.9')}
                onMouseLeave={(e) => !controlLoading && (e.currentTarget.style.opacity = '1')}
              >
                <Play size={16} />
                Start
              </button>
            )}
            
            {isActive && (
              <button
                onClick={(e) => handleControlClick('pause', e)}
                disabled={controlLoading === bot.id}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '6px',
                  padding: '8px 16px',
                  borderRadius: '8px',
                  background: 'rgba(245, 158, 11, 0.2)',
                  color: '#f59e0b',
                  border: '1px solid #f59e0b',
                  fontSize: '0.9rem',
                  fontWeight: 600,
                  cursor: controlLoading === bot.id ? 'wait' : 'pointer',
                  opacity: controlLoading === bot.id ? 0.6 : 1,
                  transition: 'all 0.2s ease'
                }}
                onMouseEnter={(e) => !controlLoading && (e.currentTarget.style.opacity = '0.9')}
                onMouseLeave={(e) => !controlLoading && (e.currentTarget.style.opacity = '1')}
              >
                <Pause size={16} />
                Pause
              </button>
            )}
            
            {isPaused && (
              <button
                onClick={(e) => handleControlClick('resume', e)}
                disabled={controlLoading === bot.id}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '6px',
                  padding: '8px 16px',
                  borderRadius: '8px',
                  background: 'rgba(34, 197, 94, 0.2)',
                  color: '#22c55e',
                  border: '1px solid #22c55e',
                  fontSize: '0.9rem',
                  fontWeight: 600,
                  cursor: controlLoading === bot.id ? 'wait' : 'pointer',
                  opacity: controlLoading === bot.id ? 0.6 : 1,
                  transition: 'all 0.2s ease'
                }}
                onMouseEnter={(e) => !controlLoading && (e.currentTarget.style.opacity = '0.9')}
                onMouseLeave={(e) => !controlLoading && (e.currentTarget.style.opacity = '1')}
              >
                <Play size={16} />
                Resume
              </button>
            )}
            
            <div style={{ flex: 1 }} />
            
            <button
              onClick={(e) => handleControlClick('delete', e)}
              disabled={controlLoading === bot.id}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '6px',
                padding: '8px 16px',
                borderRadius: '8px',
                background: 'rgba(239, 68, 68, 0.1)',
                color: '#ef4444',
                border: '1px solid rgba(239, 68, 68, 0.3)',
                fontSize: '0.9rem',
                fontWeight: 600,
                cursor: controlLoading === bot.id ? 'wait' : 'pointer',
                opacity: controlLoading === bot.id ? 0.6 : 1,
                transition: 'all 0.2s ease'
              }}
              onMouseEnter={(e) => !controlLoading && (e.currentTarget.style.opacity = '0.9')}
              onMouseLeave={(e) => !controlLoading && (e.currentTarget.style.opacity = '1')}
            >
              <Square size={16} />
              Delete
            </button>
          </div>
        </div>
      )}
    </div>
  );
};

export default function BotFleet({ bots, onControl, controlLoading, autoRefresh = true }) {
  const [expandedBots, setExpandedBots] = useState(new Set());
  const [isAutoRefresh, setIsAutoRefresh] = useState(autoRefresh);
  const [lastUpdate, setLastUpdate] = useState(new Date());
  
  useEffect(() => {
    if (isAutoRefresh) {
      const interval = setInterval(() => {
        setLastUpdate(new Date());
      }, 2000);
      return () => clearInterval(interval);
    }
  }, [isAutoRefresh]);
  
  const toggleBot = (botId) => {
    setExpandedBots(prev => {
      const next = new Set(prev);
      if (next.has(botId)) {
        next.delete(botId);
      } else {
        next.add(botId);
      }
      return next;
    });
  };
  
  const expandAll = () => {
    setExpandedBots(new Set(bots.map(b => b.id)));
  };
  
  const collapseAll = () => {
    setExpandedBots(new Set());
  };
  
  return (
    <div style={{ position: 'relative' }}>
      {/* Header with Controls */}
      <div style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        marginBottom: '16px',
        padding: '12px 16px',
        background: 'var(--glass)',
        border: '1px solid var(--line)',
        borderRadius: '12px'
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <h3 style={{ margin: 0, fontSize: '1.1rem', color: 'var(--text)' }}>
            Bot Fleet ({bots.length})
          </h3>
          <div style={{ fontSize: '0.85rem', color: 'var(--muted)' }}>
            {expandedBots.size > 0 && `${expandedBots.size} expanded`}
          </div>
        </div>
        
        <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
          <button
            onClick={() => setIsAutoRefresh(!isAutoRefresh)}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              padding: '6px 12px',
              borderRadius: '6px',
              background: isAutoRefresh ? 'rgba(34, 197, 94, 0.2)' : 'transparent',
              color: isAutoRefresh ? '#22c55e' : 'var(--muted)',
              border: `1px solid ${isAutoRefresh ? '#22c55e' : 'var(--line)'}`,
              fontSize: '0.85rem',
              fontWeight: 500,
              cursor: 'pointer',
              transition: 'all 0.2s ease'
            }}
          >
            <RefreshCw size={14} style={{ animation: isAutoRefresh ? 'spin 2s linear infinite' : 'none' }} />
            Auto-refresh
          </button>
          
          {expandedBots.size === 0 ? (
            <button
              onClick={expandAll}
              style={{
                padding: '6px 12px',
                borderRadius: '6px',
                background: 'transparent',
                color: 'var(--accent2)',
                border: '1px solid var(--line)',
                fontSize: '0.85rem',
                fontWeight: 500,
                cursor: 'pointer',
                transition: 'all 0.2s ease'
              }}
            >
              Expand All
            </button>
          ) : (
            <button
              onClick={collapseAll}
              style={{
                padding: '6px 12px',
                borderRadius: '6px',
                background: 'transparent',
                color: 'var(--accent2)',
                border: '1px solid var(--line)',
                fontSize: '0.85rem',
                fontWeight: 500,
                cursor: 'pointer',
                transition: 'all 0.2s ease'
              }}
            >
              Collapse All
            </button>
          )}
        </div>
      </div>
      
      {/* Bot List */}
      <div style={{
        maxHeight: '600px',
        overflowY: 'auto',
        paddingRight: '4px'
      }}>
        {bots.length === 0 ? (
          <div style={{
            padding: '60px 20px',
            textAlign: 'center',
            color: 'var(--muted)',
            background: 'var(--glass)',
            border: '1px solid var(--line)',
            borderRadius: '12px'
          }}>
            <div style={{ fontSize: '3rem', marginBottom: '16px', opacity: 0.5 }}>🤖</div>
            <div style={{ fontSize: '1.1rem', marginBottom: '8px' }}>No bots yet</div>
            <div style={{ fontSize: '0.9rem', opacity: 0.8 }}>Create your first bot to get started</div>
          </div>
        ) : (
          bots.map(bot => (
            <BotFleetItem
              key={bot.id}
              bot={bot}
              isExpanded={expandedBots.has(bot.id)}
              onToggle={() => toggleBot(bot.id)}
              onControl={onControl}
              controlLoading={controlLoading}
            />
          ))
        )}
      </div>
      
      <style>{`
        @keyframes spin {
          from { transform: rotate(0deg); }
          to { transform: rotate(360deg); }
        }
      `}</style>
    </div>
  );
}
