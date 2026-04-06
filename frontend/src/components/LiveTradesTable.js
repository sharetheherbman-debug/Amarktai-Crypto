import React, { useState, useEffect, useCallback } from 'react';
import { RefreshCw, Filter } from 'lucide-react';
import { getPlatformDisplayName } from '../constants/platforms';
import { useRealtimeEvent } from '../hooks/useRealtime';

const NOT_AVAILABLE = 'N/A';

const formatZAR = (value, digits = 2) => {
  const num = Number(value);
  if (!Number.isFinite(num)) return NOT_AVAILABLE;
  const formatted = Math.abs(num).toLocaleString('en-US', { minimumFractionDigits: digits, maximumFractionDigits: digits });
  return `${num < 0 ? '-R' : 'R'}${formatted}`;
};

const formatTime = (value) => {
  if (!value) return NOT_AVAILABLE;
  try {
    const date = new Date(value);
    if (isNaN(date.getTime())) return NOT_AVAILABLE;
    const now = new Date();
    const diffMs = now - date;
    const diffMins = Math.floor(diffMs / 60000);
    
    if (diffMins < 1) return 'Just now';
    if (diffMins < 60) return `${diffMins}m ago`;
    
    const diffHours = Math.floor(diffMins / 60);
    if (diffHours < 24) return `${diffHours}h ago`;
    
    return date.toLocaleString('en-US', { 
      month: 'short', 
      day: 'numeric',
      hour: '2-digit', 
      minute: '2-digit' 
    });
  } catch {
    return NOT_AVAILABLE;
  }
};

const getStatusBadge = (status) => {
  const statusMap = {
    'completed': { text: 'Completed', color: '#22c55e', bg: 'rgba(34, 197, 94, 0.15)' },
    'filled': { text: 'Filled', color: '#22c55e', bg: 'rgba(34, 197, 94, 0.15)' },
    'success': { text: 'Success', color: '#22c55e', bg: 'rgba(34, 197, 94, 0.15)' },
    'pending': { text: 'Pending', color: '#f59e0b', bg: 'rgba(245, 158, 11, 0.15)' },
    'open': { text: 'Open', color: '#3b82f6', bg: 'rgba(59, 130, 246, 0.15)' },
    'error': { text: 'Error', color: '#ef4444', bg: 'rgba(239, 68, 68, 0.15)' },
    'failed': { text: 'Failed', color: '#ef4444', bg: 'rgba(239, 68, 68, 0.15)' },
    'cancelled': { text: 'Cancelled', color: '#9ca3af', bg: 'rgba(156, 163, 175, 0.15)' }
  };
  
  const normalized = (status || 'unknown').toLowerCase();
  return statusMap[normalized] || { text: status || 'Unknown', color: '#9ca3af', bg: 'rgba(156, 163, 175, 0.15)' };
};

export default function LiveTradesTable({ trades = [], bots = [], onRefresh, loadError, isLoading }) {
  const [filters, setFilters] = useState({
    exchange: 'all',
    bot: 'all',
    pair: 'all',
    side: 'all',
    status: 'all'
  });
  const [autoRefresh, setAutoRefresh] = useState(true);
  const [showFilters, setShowFilters] = useState(false);
  const [highlightedTrades, setHighlightedTrades] = useState(new Set());
  const [lastUpdate, setLastUpdate] = useState(new Date());
  
  // WebSocket subscription for real-time trade updates
  useRealtimeEvent('trade_executed', (data) => {
    console.log('Trade executed event received:', data);
    if (data && data.bot_id) {
      // Highlight new trade briefly
      setHighlightedTrades(prev => new Set([...prev, data.bot_id]));
      setTimeout(() => {
        setHighlightedTrades(prev => {
          const next = new Set(prev);
          next.delete(data.bot_id);
          return next;
        });
      }, 3000);
    }
    // Trigger parent refresh
    if (onRefresh) {
      onRefresh();
    }
  }, [onRefresh]);
  
  // Auto-refresh polling (fallback)
  useEffect(() => {
    if (autoRefresh && onRefresh) {
      const interval = setInterval(() => {
        onRefresh();
        setLastUpdate(new Date());
      }, 2000); // 2 second polling
      return () => clearInterval(interval);
    }
  }, [autoRefresh, onRefresh]);
  
  // Extract unique values for filters
  const uniqueExchanges = [...new Set(trades.map(t => t.exchange).filter(Boolean))];
  const uniqueBots = [...new Set(trades.map(t => t.bot_name || t.bot_id).filter(Boolean))];
  const uniquePairs = [...new Set(trades.map(t => t.pair || t.symbol).filter(Boolean))];
  
  // Apply filters
  const filteredTrades = trades.filter(trade => {
    if (filters.exchange !== 'all' && trade.exchange !== filters.exchange) return false;
    if (filters.bot !== 'all' && (trade.bot_name || trade.bot_id) !== filters.bot) return false;
    if (filters.pair !== 'all' && (trade.pair || trade.symbol) !== filters.pair) return false;
    if (filters.side !== 'all' && trade.side !== filters.side) return false;
    if (filters.status !== 'all' && trade.status !== filters.status) return false;
    return true;
  });
  
  const handleFilterChange = (key, value) => {
    setFilters(prev => ({ ...prev, [key]: value }));
  };
  
  const clearFilters = () => {
    setFilters({
      exchange: 'all',
      bot: 'all',
      pair: 'all',
      side: 'all',
      status: 'all'
    });
  };
  
  const hasActiveFilters = Object.values(filters).some(v => v !== 'all');
  
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
        borderRadius: '12px',
        flexWrap: 'wrap',
        gap: '12px'
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <h3 style={{ margin: 0, fontSize: '1.1rem', color: 'var(--text)' }}>
            Live Trades ({filteredTrades.length})
          </h3>
          {hasActiveFilters && (
            <div style={{ fontSize: '0.85rem', color: 'var(--accent2)' }}>
              Filtered
            </div>
          )}
        </div>
        
        <div style={{ display: 'flex', gap: '8px', alignItems: 'center', flexWrap: 'wrap' }}>
          <button
            onClick={() => setShowFilters(!showFilters)}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              padding: '6px 12px',
              borderRadius: '6px',
              background: showFilters ? 'rgba(96, 165, 250, 0.2)' : 'transparent',
              color: showFilters ? '#60a5fa' : 'var(--muted)',
              border: `1px solid ${showFilters ? '#60a5fa' : 'var(--line)'}`,
              fontSize: '0.85rem',
              fontWeight: 500,
              cursor: 'pointer',
              transition: 'all 0.2s ease'
            }}
          >
            <Filter size={14} />
            Filters
            {hasActiveFilters && ` (${Object.values(filters).filter(v => v !== 'all').length})`}
          </button>
          
          {hasActiveFilters && (
            <button
              onClick={clearFilters}
              style={{
                padding: '6px 12px',
                borderRadius: '6px',
                background: 'transparent',
                color: 'var(--error)',
                border: '1px solid var(--line)',
                fontSize: '0.85rem',
                fontWeight: 500,
                cursor: 'pointer',
                transition: 'all 0.2s ease'
              }}
            >
              Clear
            </button>
          )}
          
          <button
            onClick={() => setAutoRefresh(!autoRefresh)}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              padding: '6px 12px',
              borderRadius: '6px',
              background: autoRefresh ? 'rgba(34, 197, 94, 0.2)' : 'transparent',
              color: autoRefresh ? '#22c55e' : 'var(--muted)',
              border: `1px solid ${autoRefresh ? '#22c55e' : 'var(--line)'}`,
              fontSize: '0.85rem',
              fontWeight: 500,
              cursor: 'pointer',
              transition: 'all 0.2s ease'
            }}
          >
            <RefreshCw size={14} style={{ animation: autoRefresh ? 'spin 2s linear infinite' : 'none' }} />
            Auto-refresh
          </button>
        </div>
      </div>
      
      {/* Filters Panel */}
      {showFilters && (
        <div style={{
          padding: '16px',
          marginBottom: '16px',
          background: 'var(--glass)',
          border: '1px solid var(--line)',
          borderRadius: '12px',
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
          gap: '12px'
        }}>
          {/* Exchange Filter */}
          <div>
            <label style={{ fontSize: '0.85rem', color: 'var(--muted)', display: 'block', marginBottom: '6px' }}>
              Exchange
            </label>
            <select
              value={filters.exchange}
              onChange={(e) => handleFilterChange('exchange', e.target.value)}
              style={{
                width: '100%',
                padding: '8px',
                borderRadius: '6px',
                background: 'rgba(0, 0, 0, 0.3)',
                color: 'var(--text)',
                border: '1px solid var(--line)',
                fontSize: '0.9rem'
              }}
            >
              <option value="all">All Exchanges</option>
              {uniqueExchanges.map(ex => (
                <option key={ex} value={ex}>{getPlatformDisplayName(ex)}</option>
              ))}
            </select>
          </div>
          
          {/* Bot Filter */}
          <div>
            <label style={{ fontSize: '0.85rem', color: 'var(--muted)', display: 'block', marginBottom: '6px' }}>
              Bot
            </label>
            <select
              value={filters.bot}
              onChange={(e) => handleFilterChange('bot', e.target.value)}
              style={{
                width: '100%',
                padding: '8px',
                borderRadius: '6px',
                background: 'rgba(0, 0, 0, 0.3)',
                color: 'var(--text)',
                border: '1px solid var(--line)',
                fontSize: '0.9rem'
              }}
            >
              <option value="all">All Bots</option>
              {uniqueBots.map(bot => (
                <option key={bot} value={bot}>{bot}</option>
              ))}
            </select>
          </div>
          
          {/* Pair Filter */}
          <div>
            <label style={{ fontSize: '0.85rem', color: 'var(--muted)', display: 'block', marginBottom: '6px' }}>
              Pair
            </label>
            <select
              value={filters.pair}
              onChange={(e) => handleFilterChange('pair', e.target.value)}
              style={{
                width: '100%',
                padding: '8px',
                borderRadius: '6px',
                background: 'rgba(0, 0, 0, 0.3)',
                color: 'var(--text)',
                border: '1px solid var(--line)',
                fontSize: '0.9rem'
              }}
            >
              <option value="all">All Pairs</option>
              {uniquePairs.map(pair => (
                <option key={pair} value={pair}>{pair}</option>
              ))}
            </select>
          </div>
          
          {/* Side Filter */}
          <div>
            <label style={{ fontSize: '0.85rem', color: 'var(--muted)', display: 'block', marginBottom: '6px' }}>
              Side
            </label>
            <select
              value={filters.side}
              onChange={(e) => handleFilterChange('side', e.target.value)}
              style={{
                width: '100%',
                padding: '8px',
                borderRadius: '6px',
                background: 'rgba(0, 0, 0, 0.3)',
                color: 'var(--text)',
                border: '1px solid var(--line)',
                fontSize: '0.9rem'
              }}
            >
              <option value="all">All Sides</option>
              <option value="buy">Buy</option>
              <option value="sell">Sell</option>
            </select>
          </div>
          
          {/* Status Filter */}
          <div>
            <label style={{ fontSize: '0.85rem', color: 'var(--muted)', display: 'block', marginBottom: '6px' }}>
              Status
            </label>
            <select
              value={filters.status}
              onChange={(e) => handleFilterChange('status', e.target.value)}
              style={{
                width: '100%',
                padding: '8px',
                borderRadius: '6px',
                background: 'rgba(0, 0, 0, 0.3)',
                color: 'var(--text)',
                border: '1px solid var(--line)',
                fontSize: '0.9rem'
              }}
            >
              <option value="all">All Status</option>
              <option value="completed">Completed</option>
              <option value="pending">Pending</option>
              <option value="error">Error</option>
              <option value="cancelled">Cancelled</option>
            </select>
          </div>
        </div>
      )}
      
      {/* Error Banner */}
      {loadError && (
        <div style={{
          padding: '12px 16px',
          marginBottom: '12px',
          background: 'rgba(239, 68, 68, 0.1)',
          border: '1px solid rgba(239, 68, 68, 0.3)',
          borderRadius: '8px',
          color: '#ef4444',
          fontSize: '0.9rem',
          display: 'flex',
          alignItems: 'center',
          gap: '10px'
        }}>
          <span>⚠️ {loadError}</span>
          <button
            onClick={() => onRefresh && onRefresh()}
            style={{
              marginLeft: 'auto',
              padding: '4px 12px',
              borderRadius: '6px',
              background: 'rgba(239, 68, 68, 0.2)',
              color: '#ef4444',
              border: '1px solid rgba(239, 68, 68, 0.4)',
              fontSize: '0.85rem',
              cursor: 'pointer'
            }}
          >
            Retry
          </button>
        </div>
      )}

      {/* Trades Table */}
      <div style={{
        background: 'var(--glass)',
        border: '1px solid var(--line)',
        borderRadius: '12px',
        overflow: 'hidden',
        minWidth: 0,
      }}>
        <div style={{
          maxHeight: '600px',
          overflowY: 'auto',
          overflowX: 'auto',
          width: '100%',
        }}>
          <table style={{
            width: '100%',
            minWidth: '600px',
            borderCollapse: 'collapse',
            fontSize: '0.9rem',
            tableLayout: 'auto',
          }}>
            <thead style={{
              position: 'sticky',
              top: 0,
              background: 'rgba(0, 0, 0, 0.5)',
              backdropFilter: 'blur(10px)',
              zIndex: 1
            }}>
              <tr>
                <th style={{ padding: '12px', textAlign: 'left', color: 'var(--muted)', fontWeight: 600, fontSize: '0.85rem', borderBottom: '1px solid var(--line)' }}>Time</th>
                <th style={{ padding: '12px', textAlign: 'left', color: 'var(--muted)', fontWeight: 600, fontSize: '0.85rem', borderBottom: '1px solid var(--line)' }}>Bot</th>
                <th style={{ padding: '12px', textAlign: 'left', color: 'var(--muted)', fontWeight: 600, fontSize: '0.85rem', borderBottom: '1px solid var(--line)' }}>Exchange</th>
                <th style={{ padding: '12px', textAlign: 'left', color: 'var(--muted)', fontWeight: 600, fontSize: '0.85rem', borderBottom: '1px solid var(--line)' }}>Pair</th>
                <th style={{ padding: '12px', textAlign: 'left', color: 'var(--muted)', fontWeight: 600, fontSize: '0.85rem', borderBottom: '1px solid var(--line)' }}>Side</th>
                <th style={{ padding: '12px', textAlign: 'right', color: 'var(--muted)', fontWeight: 600, fontSize: '0.85rem', borderBottom: '1px solid var(--line)' }}>Qty</th>
                <th style={{ padding: '12px', textAlign: 'right', color: 'var(--muted)', fontWeight: 600, fontSize: '0.85rem', borderBottom: '1px solid var(--line)' }}>Price</th>
                <th style={{ padding: '12px', textAlign: 'center', color: 'var(--muted)', fontWeight: 600, fontSize: '0.85rem', borderBottom: '1px solid var(--line)' }}>Status</th>
                <th style={{ padding: '12px', textAlign: 'right', color: 'var(--muted)', fontWeight: 600, fontSize: '0.85rem', borderBottom: '1px solid var(--line)' }}>P/L</th>
              </tr>
            </thead>
            <tbody>
              {filteredTrades.length === 0 ? (
                <tr>
                  <td colSpan="9" style={{ padding: '40px', textAlign: 'center', color: 'var(--muted)' }}>
                    {isLoading
                      ? '⏳ Loading trades...'
                      : loadError
                        ? 'Could not load trades — see error above'
                        : hasActiveFilters
                          ? 'No trades match the selected filters'
                          : 'No trades yet'}
                  </td>
                </tr>
              ) : (
                filteredTrades.map((trade) => {
                  const statusBadge = getStatusBadge(trade.status);
                  const pnl = trade.profit_loss || trade.pnl || trade.profit || 0;
                  const isProfitable = pnl > 0;
                  const isHighlighted = highlightedTrades.has(trade.bot_id);
                  // Use trade.id or create stable key from trade properties
                  const tradeKey = trade.id || `${trade.timestamp}-${trade.bot_id}-${trade.pair}`;
                  
                  return (
                    <tr
                      key={tradeKey}
                      style={{
                        borderBottom: '1px solid var(--line)',
                        background: isHighlighted ? 'rgba(34, 197, 94, 0.1)' : 'transparent',
                        transition: 'background 0.3s ease'
                      }}
                    >
                      <td style={{ padding: '12px', color: 'var(--text)', whiteSpace: 'nowrap' }}>
                        {formatTime(trade.timestamp || trade.created_at)}
                      </td>
                      <td style={{ padding: '12px', color: 'var(--text)', maxWidth: '150px', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                        {trade.bot_name || trade.bot_id || NOT_AVAILABLE}
                      </td>
                      <td style={{ padding: '12px', color: 'var(--text)' }}>
                        {getPlatformDisplayName(trade.exchange)}
                      </td>
                      <td style={{ padding: '12px', color: 'var(--text)', fontWeight: 500 }}>
                        {trade.pair || trade.symbol || NOT_AVAILABLE}
                      </td>
                      <td style={{ padding: '12px' }}>
                        <span style={{
                          padding: '4px 8px',
                          borderRadius: '4px',
                          fontSize: '0.8rem',
                          fontWeight: 600,
                          background: trade.side === 'buy' ? 'rgba(34, 197, 94, 0.15)' : 'rgba(239, 68, 68, 0.15)',
                          color: trade.side === 'buy' ? '#22c55e' : '#ef4444',
                          textTransform: 'uppercase'
                        }}>
                          {trade.side || 'N/A'}
                        </span>
                      </td>
                      <td style={{ padding: '12px', textAlign: 'right', color: 'var(--text)', fontWeight: 500 }}>
                        {trade.amount || trade.quantity || '0'}
                      </td>
                      <td style={{ padding: '12px', textAlign: 'right', color: 'var(--text)', fontWeight: 500 }}>
                        {formatZAR(trade.price, 2)}
                      </td>
                      <td style={{ padding: '12px', textAlign: 'center' }}>
                        <span style={{
                          padding: '4px 10px',
                          borderRadius: '6px',
                          fontSize: '0.8rem',
                          fontWeight: 600,
                          background: statusBadge.bg,
                          color: statusBadge.color,
                          whiteSpace: 'nowrap'
                        }}>
                          {statusBadge.text}
                        </span>
                      </td>
                      <td style={{ 
                        padding: '12px', 
                        textAlign: 'right', 
                        fontWeight: 600,
                        color: isProfitable ? 'var(--success)' : (pnl < 0 ? 'var(--error)' : 'var(--muted)')
                      }}>
                        {formatZAR(pnl)}
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
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
