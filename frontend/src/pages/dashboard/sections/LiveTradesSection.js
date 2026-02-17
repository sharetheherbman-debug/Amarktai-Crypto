import React from 'react';
import SectionHeader from '@/ui/components/SectionHeader';
import { getPlatformDisplayName } from '../../../constants/platforms';

const NOT_AVAILABLE = 'Not available';
const formatZAR = (value, digits = 2, fallback = NOT_AVAILABLE) => {
  const num = Number(value);
  if (!Number.isFinite(num)) return fallback;
  const formatted = Math.abs(num).toLocaleString('en-US', { minimumFractionDigits: digits, maximumFractionDigits: digits });
  return `${num < 0 ? '-R' : 'R'}${formatted}`;
};
const safeToFixed = (value, digits = 2, fallback = '0.00') => {
  const num = Number(value);
  return Number.isFinite(num) ? num.toFixed(digits) : fallback;
};

export default function LiveTradesSection({
  recentTrades,
  selectedTradeId,
  setSelectedTradeId,
  setTradeBotFilter,
  setTradeExchangeFilter,
  setTradePairFilter,
  tradeBotFilter,
  tradeExchangeFilter,
  tradePairFilter,
  bots = [],
}) {
  // Load from localStorage or use defaults
  const [sideFilter, setSideFilter] = React.useState(() => 
    localStorage.getItem('liveTradesSideFilter') || 'all'
  );
  const [statusFilter, setStatusFilter] = React.useState(() =>
    localStorage.getItem('liveTradesStatusFilter') || 'all'
  );
  const [timeRange, setTimeRange] = React.useState(() =>
    localStorage.getItem('liveTradesTimeRange') || '24h'
  );
  const [compactMode, setCompactMode] = React.useState(false);
  const [currentPage, setCurrentPage] = React.useState(() =>
    parseInt(localStorage.getItem('liveTradesCurrentPage') || '1', 10)
  );
  const [itemsPerPage, setItemsPerPage] = React.useState(() =>
    parseInt(localStorage.getItem('liveTradesItemsPerPage') || '20', 10)
  );
  const [lastPollTime, setLastPollTime] = React.useState(new Date());
  const [searchQuery, setSearchQuery] = React.useState('');
  const [sortColumn, setSortColumn] = React.useState(() =>
    localStorage.getItem('liveTradesSortColumn') || 'timestamp'
  );
  const [sortDirection, setSortDirection] = React.useState(() =>
    localStorage.getItem('liveTradesSortDirection') || 'desc'
  );
  const [newTradeIds, setNewTradeIds] = React.useState(new Set());

  // Persist filter state to localStorage
  React.useEffect(() => {
    localStorage.setItem('liveTradesSideFilter', sideFilter);
  }, [sideFilter]);

  React.useEffect(() => {
    localStorage.setItem('liveTradesStatusFilter', statusFilter);
  }, [statusFilter]);

  React.useEffect(() => {
    localStorage.setItem('liveTradesTimeRange', timeRange);
  }, [timeRange]);

  React.useEffect(() => {
    localStorage.setItem('liveTradesCurrentPage', currentPage.toString());
  }, [currentPage]);

  React.useEffect(() => {
    localStorage.setItem('liveTradesItemsPerPage', itemsPerPage.toString());
  }, [itemsPerPage]);

  React.useEffect(() => {
    localStorage.setItem('liveTradesSortColumn', sortColumn);
  }, [sortColumn]);

  React.useEffect(() => {
    localStorage.setItem('liveTradesSortDirection', sortDirection);
  }, [sortDirection]);

  // Track new trades and highlight them
  const previousTradeIdsRef = React.useRef(new Set());
  React.useEffect(() => {
    if (recentTrades.length > 0) {
      setLastPollTime(new Date());
      
      // Detect new trades
      const currentIds = new Set(recentTrades.map(t => t.id));
      const previousIds = previousTradeIdsRef.current;
      const newIds = new Set([...currentIds].filter(id => !previousIds.has(id)));
      
      if (newIds.size > 0) {
        setNewTradeIds(newIds);
        // Clear highlight after 5 seconds
        setTimeout(() => {
          setNewTradeIds(prev => {
            const updated = new Set(prev);
            newIds.forEach(id => updated.delete(id));
            return updated;
          });
        }, 5000);
      }
      
      previousTradeIdsRef.current = currentIds;
    }
  }, [recentTrades]);

  // Extract unique values for filters
  const exchanges = Array.from(new Set(recentTrades.map(trade => trade.exchange?.toLowerCase()).filter(Boolean)));
  const botsList = Array.from(new Set(recentTrades.map(trade => trade.bot_name).filter(Boolean)));
  const pairsList = Array.from(new Set(recentTrades.map(trade => trade.symbol).filter(Boolean)));
  const sides = ['all', 'buy', 'sell'];
  const statuses = ['all', 'filled', 'partial', 'pending', 'cancelled'];

  // Time range filtering
  const getTimeRangeDate = () => {
    const now = new Date();
    switch(timeRange) {
      case '1h': return new Date(now.getTime() - 60 * 60 * 1000);
      case '24h': return new Date(now.getTime() - 24 * 60 * 60 * 1000);
      case '7d': return new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000);
      case '30d': return new Date(now.getTime() - 30 * 24 * 60 * 60 * 1000);
      default: return null;
    }
  };

  const filteredTrades = React.useMemo(() => {
    let filtered = recentTrades.filter((trade) => {
      const tradeExchange = trade.exchange?.toLowerCase();
      if (tradeExchangeFilter !== 'all' && tradeExchange !== tradeExchangeFilter) return false;
      if (tradeBotFilter !== 'all' && trade.bot_name !== tradeBotFilter) return false;
      if (tradePairFilter !== 'all' && trade.symbol !== tradePairFilter) return false;
      
      // Side filter
      const tradeSide = (trade.side || trade.action || '').toString().toLowerCase();
      if (sideFilter !== 'all' && tradeSide !== sideFilter) return false;
      
      // Status filter
      const tradeStatus = (trade.status || 'filled').toString().toLowerCase();
      if (statusFilter !== 'all' && !tradeStatus.includes(statusFilter)) return false;
      
      // Time range filter
      if (timeRange !== 'all' && trade.timestamp) {
        const cutoff = getTimeRangeDate();
        if (cutoff && new Date(trade.timestamp) < cutoff) return false;
      }
      
      // Search filter
      if (searchQuery.trim()) {
        const query = searchQuery.toLowerCase();
        const searchableText = [
          trade.id,
          trade.bot_name,
          trade.symbol,
          trade.exchange,
          trade.side,
          trade.status
        ].join(' ').toLowerCase();
        
        if (!searchableText.includes(query)) return false;
      }
      
      return true;
    });

    // Apply sorting
    if (sortColumn) {
      filtered.sort((a, b) => {
        let aVal = a[sortColumn];
        let bVal = b[sortColumn];
        
        // Handle timestamp sorting
        if (sortColumn === 'timestamp') {
          aVal = new Date(aVal).getTime();
          bVal = new Date(bVal).getTime();
        }
        
        // Handle numeric sorting
        if (sortColumn === 'amount' || sortColumn === 'price' || sortColumn === 'profit_loss' || sortColumn === 'fee') {
          aVal = parseFloat(aVal) || 0;
          bVal = parseFloat(bVal) || 0;
        }
        
        // Handle string sorting
        if (typeof aVal === 'string') {
          aVal = aVal.toLowerCase();
          bVal = (bVal || '').toLowerCase();
        }
        
        if (aVal < bVal) return sortDirection === 'asc' ? -1 : 1;
        if (aVal > bVal) return sortDirection === 'asc' ? 1 : -1;
        return 0;
      });
    }

    return filtered;
  }, [recentTrades, tradeExchangeFilter, tradeBotFilter, tradePairFilter, sideFilter, statusFilter, timeRange, searchQuery, sortColumn, sortDirection]);

  // Pagination
  const totalPages = Math.ceil(filteredTrades.length / itemsPerPage);
  const paginatedTrades = filteredTrades.slice(
    (currentPage - 1) * itemsPerPage,
    currentPage * itemsPerPage
  );

  // Reset to page 1 when filters change
  React.useEffect(() => {
    setCurrentPage(1);
  }, [tradeExchangeFilter, tradeBotFilter, tradePairFilter, sideFilter, statusFilter, timeRange, searchQuery]);

  const handleSort = (column) => {
    if (sortColumn === column) {
      // Toggle direction
      setSortDirection(sortDirection === 'asc' ? 'desc' : 'asc');
    } else {
      setSortColumn(column);
      setSortDirection('desc');
    }
  };

  const resolvedTradeId = paginatedTrades.some(trade => trade.id === selectedTradeId)
    ? selectedTradeId
    : paginatedTrades[0]?.id;
  const selectedTrade = paginatedTrades.find(trade => trade.id === resolvedTradeId) || null;

  // Export to CSV function
  const exportToCSV = () => {
    const headers = ['Timestamp', 'Bot', 'Exchange', 'Symbol', 'Side', 'Quantity', 'Price', 'Fee', 'PnL', 'Mode', 'Status', 'Order ID'];
    const rows = filteredTrades.map(trade => [
      trade.timestamp ? new Date(trade.timestamp).toLocaleString() : '',
      trade.bot_name || '',
      trade.exchange || '',
      trade.symbol || '',
      trade.side || trade.action || '',
      trade.size || trade.quantity || '',
      trade.price || trade.avg_price || '',
      trade.fees || trade.fee || '',
      trade.profit_loss || '',
      trade.trading_mode || trade.mode || '',
      trade.status || '',
      trade.order_id || trade.id || ''
    ]);
    
    const csvContent = [headers, ...rows]
      .map(row => row.map(cell => `"${cell}"`).join(','))
      .join('\n');
    
    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const link = document.createElement('a');
    const url = URL.createObjectURL(blob);
    link.setAttribute('href', url);
    link.setAttribute('download', `trades_${new Date().toISOString().split('T')[0]}.csv`);
    link.style.visibility = 'hidden';
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  const refreshTrades = () => {
    // Trigger a refresh by resetting filters or calling parent refresh function
    setCurrentPage(1);
  };

  return (
    <section className="section active">
      <div className="card">
        <SectionHeader
          title="📊 Live Trades"
          subtitle="Track live executions with advanced filtering and export capabilities"
        />

        {/* Controls Bar */}
        <div style={{
          display: 'flex',
          gap: '12px',
          marginBottom: '16px',
          flexWrap: 'wrap',
          alignItems: 'center',
          justifyContent: 'space-between'
        }}>
          <div style={{display: 'flex', gap: '8px', flexWrap: 'wrap', alignItems: 'center'}}>
            <button
              onClick={refreshTrades}
              style={{
                padding: '8px 16px',
                background: 'var(--accent2)',
                color: 'var(--text)',
                border: 'none',
                borderRadius: '6px',
                fontWeight: 600,
                cursor: 'pointer',
                fontSize: '0.9rem'
              }}
            >
              🔄 Refresh
            </button>
            <button
              onClick={exportToCSV}
              disabled={filteredTrades.length === 0}
              style={{
                padding: '8px 16px',
                background: 'var(--success)',
                color: 'white',
                border: 'none',
                borderRadius: '6px',
                fontWeight: 600,
                cursor: filteredTrades.length === 0 ? 'not-allowed' : 'pointer',
                fontSize: '0.9rem',
                opacity: filteredTrades.length === 0 ? 0.5 : 1
              }}
            >
              📥 Export CSV
            </button>
            <button
              onClick={() => setCompactMode(!compactMode)}
              style={{
                padding: '8px 16px',
                background: compactMode ? 'var(--accent)' : 'var(--panel)',
                color: 'var(--text)',
                border: '1px solid var(--line)',
                borderRadius: '6px',
                fontWeight: 600,
                cursor: 'pointer',
                fontSize: '0.9rem'
              }}
            >
              {compactMode ? '📋 Standard' : '📑 Compact'}
            </button>
            
            {/* Page Size Selector */}
            <div style={{display: 'flex', alignItems: 'center', gap: '8px'}}>
              <span style={{fontSize: '0.9rem', color: 'var(--muted)'}}>Show:</span>
              <select
                value={itemsPerPage}
                onChange={(e) => setItemsPerPage(parseInt(e.target.value, 10))}
                style={{
                  padding: '8px 12px',
                  background: 'var(--panel)',
                  color: 'var(--text)',
                  border: '1px solid var(--line)',
                  borderRadius: '6px',
                  fontWeight: 600,
                  cursor: 'pointer',
                  fontSize: '0.9rem'
                }}
              >
                <option value="20">20</option>
                <option value="50">50</option>
                <option value="100">100</option>
              </select>
            </div>
          </div>
          
          <div style={{display: 'flex', alignItems: 'center', gap: '12px'}}>
            {/* Search Box */}
            <input
              type="text"
              placeholder="Search trades..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              style={{
                padding: '8px 12px',
                background: 'var(--panel)',
                color: 'var(--text)',
                border: '1px solid var(--line)',
                borderRadius: '6px',
                fontSize: '0.9rem',
                minWidth: '200px'
              }}
            />
            <div style={{fontSize: '0.9rem', color: 'var(--muted)', fontWeight: 600}}>
              {filteredTrades.length} trade{filteredTrades.length !== 1 ? 's' : ''} found
            </div>
          </div>
        </div>

        {/* Filters */}
        <div style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))',
          gap: '12px',
          marginBottom: '20px',
          background: 'var(--glass)',
          padding: '16px',
          borderRadius: '8px',
          border: '1px solid var(--line)'
        }}>
          <div>
            <label style={{fontSize: '0.75rem', fontWeight: 600, color: 'var(--muted)', display: 'block', marginBottom: '6px'}}>
              Exchange
            </label>
            <select 
              value={tradeExchangeFilter} 
              onChange={(e) => setTradeExchangeFilter(e.target.value)}
              style={{
                width: '100%',
                padding: '8px',
                background: 'var(--panel)',
                border: '1px solid var(--line)',
                borderRadius: '6px',
                color: 'var(--text)',
                cursor: 'pointer',
                fontSize: '0.9rem'
              }}
            >
              <option value="all">All Exchanges</option>
              {exchanges.map(exchange => (
                <option key={exchange} value={exchange}>{getPlatformDisplayName(exchange)}</option>
              ))}
            </select>
          </div>
          
          <div>
            <label style={{fontSize: '0.75rem', fontWeight: 600, color: 'var(--muted)', display: 'block', marginBottom: '6px'}}>
              Bot
            </label>
            <select 
              value={tradeBotFilter} 
              onChange={(e) => setTradeBotFilter(e.target.value)}
              style={{
                width: '100%',
                padding: '8px',
                background: 'var(--panel)',
                border: '1px solid var(--line)',
                borderRadius: '6px',
                color: 'var(--text)',
                cursor: 'pointer',
                fontSize: '0.9rem'
              }}
            >
              <option value="all">All Bots</option>
              {botsList.map(bot => (
                <option key={bot} value={bot}>{bot}</option>
              ))}
            </select>
          </div>
          
          <div>
            <label style={{fontSize: '0.75rem', fontWeight: 600, color: 'var(--muted)', display: 'block', marginBottom: '6px'}}>
              Pair
            </label>
            <select 
              value={tradePairFilter} 
              onChange={(e) => setTradePairFilter(e.target.value)}
              style={{
                width: '100%',
                padding: '8px',
                background: 'var(--panel)',
                border: '1px solid var(--line)',
                borderRadius: '6px',
                color: 'var(--text)',
                cursor: 'pointer',
                fontSize: '0.9rem'
              }}
            >
              <option value="all">All Pairs</option>
              {pairsList.map(pair => (
                <option key={pair} value={pair}>{pair}</option>
              ))}
            </select>
          </div>

          <div>
            <label style={{fontSize: '0.75rem', fontWeight: 600, color: 'var(--muted)', display: 'block', marginBottom: '6px'}}>
              Side
            </label>
            <select 
              value={sideFilter} 
              onChange={(e) => setSideFilter(e.target.value)}
              style={{
                width: '100%',
                padding: '8px',
                background: 'var(--panel)',
                border: '1px solid var(--line)',
                borderRadius: '6px',
                color: 'var(--text)',
                cursor: 'pointer',
                fontSize: '0.9rem',
                textTransform: 'capitalize'
              }}
            >
              {sides.map(side => (
                <option key={side} value={side}>{side === 'all' ? 'All Sides' : side.toUpperCase()}</option>
              ))}
            </select>
          </div>

          <div>
            <label style={{fontSize: '0.75rem', fontWeight: 600, color: 'var(--muted)', display: 'block', marginBottom: '6px'}}>
              Status
            </label>
            <select 
              value={statusFilter} 
              onChange={(e) => setStatusFilter(e.target.value)}
              style={{
                width: '100%',
                padding: '8px',
                background: 'var(--panel)',
                border: '1px solid var(--line)',
                borderRadius: '6px',
                color: 'var(--text)',
                cursor: 'pointer',
                fontSize: '0.9rem',
                textTransform: 'capitalize'
              }}
            >
              {statuses.map(status => (
                <option key={status} value={status}>{status === 'all' ? 'All Statuses' : status}</option>
              ))}
            </select>
          </div>

          <div>
            <label style={{fontSize: '0.75rem', fontWeight: 600, color: 'var(--muted)', display: 'block', marginBottom: '6px'}}>
              Time Range
            </label>
            <select 
              value={timeRange} 
              onChange={(e) => setTimeRange(e.target.value)}
              style={{
                width: '100%',
                padding: '8px',
                background: 'var(--panel)',
                border: '1px solid var(--line)',
                borderRadius: '6px',
                color: 'var(--text)',
                cursor: 'pointer',
                fontSize: '0.9rem'
              }}
            >
              <option value="all">All Time</option>
              <option value="1h">Last Hour</option>
              <option value="24h">Last 24 Hours</option>
              <option value="7d">Last 7 Days</option>
              <option value="30d">Last 30 Days</option>
            </select>
          </div>
        </div>

        <div className="trade-feed-layout">
          <div className="trade-feed-list" style={{flex: compactMode ? '1' : '0 0 300px'}}>
            {paginatedTrades.length === 0 ? (
              <div className="live-trades-empty" style={{padding: '40px', textAlign: 'center', background: 'var(--panel)', borderRadius: '8px', border: '1px solid var(--line)'}}>
                <div style={{fontSize: '2rem', marginBottom: '12px'}}>📭</div>
                <p style={{color: 'var(--text)', fontWeight: '600', marginBottom: '8px'}}>No trades match this filter</p>
                <p style={{color: 'var(--muted)', fontSize: '0.85rem', marginBottom: '16px'}}>
                  {recentTrades.length === 0 ? 'No trades have been executed yet.' : 'Try adjusting your filters to see more trades.'}
                </p>
                <div style={{padding: '12px', background: 'var(--glass)', borderRadius: '6px', fontSize: '0.85rem', color: 'var(--muted)', marginTop: '16px'}}>
                  <div style={{marginBottom: '4px'}}>
                    <strong style={{color: 'var(--text)'}}>Active Bots:</strong> {bots.filter(b => b.status === 'active' || b.state === 'active').length} / {bots.length}
                  </div>
                  <div>
                    <strong style={{color: 'var(--text)'}}>Last Poll:</strong> {lastPollTime.toLocaleTimeString()}
                  </div>
                </div>
              </div>
            ) : (
              paginatedTrades.map((trade, idx) => {
                const isWin = trade.is_profitable || trade.profit_loss > 0;
                const side = (trade.side || trade.action || 'trade').toString().toLowerCase();
                const sideLabel = side === 'buy' || side === 'sell' ? side : 'trade';
                return (
                  <button
                    key={trade.id || trade.timestamp || `trade-${trade.symbol}-${idx}`}
                    type="button"
                    className={`trade-row ${resolvedTradeId === trade.id ? 'active' : ''}`}
                    onClick={() => setSelectedTradeId(trade.id)}
                    style={{
                      padding: compactMode ? '8px' : '12px',
                      marginBottom: '8px',
                      background: resolvedTradeId === trade.id ? 'var(--accent-bg)' : 'var(--panel)',
                      border: '1px solid var(--line)',
                      borderRadius: '6px',
                      cursor: 'pointer',
                      width: '100%',
                      textAlign: 'left',
                      transition: 'all 0.2s'
                    }}
                  >
                    <div style={{display: 'flex', justifyContent: 'space-between', alignItems: 'center'}}>
                      <div>
                        <strong style={{fontSize: compactMode ? '0.85rem' : '0.95rem'}}>
                          {trade.bot_name || 'Bot'}
                        </strong>
                        <div style={{fontSize: '0.75rem', color: 'var(--muted)', marginTop: '2px'}}>
                          {trade.symbol || NOT_AVAILABLE} • {getPlatformDisplayName(trade.exchange?.toLowerCase())}
                        </div>
                      </div>
                      <div className="trade-row-meta" style={{textAlign: 'right'}}>
                        <span 
                          className={`trade-side ${sideLabel}`}
                          style={{
                            display: 'inline-block',
                            padding: '3px 8px',
                            borderRadius: '4px',
                            fontSize: '0.7rem',
                            fontWeight: 600,
                            marginBottom: '4px',
                            textTransform: 'uppercase',
                            background: sideLabel === 'buy' ? 'var(--success)' : sideLabel === 'sell' ? 'var(--error)' : 'var(--muted)',
                            color: 'white'
                          }}
                        >
                          {sideLabel}
                        </span>
                        <div 
                          className={`trade-profit ${isWin ? 'win' : 'loss'}`}
                          style={{
                            fontSize: '0.85rem',
                            fontWeight: 600,
                            color: isWin ? 'var(--success)' : 'var(--error)'
                          }}
                        >
                          R{safeToFixed(trade.profit_loss, 2)}
                        </div>
                      </div>
                    </div>
                    {!compactMode && (
                      <div style={{fontSize: '0.7rem', color: 'var(--muted)', marginTop: '6px'}}>
                        {trade.timestamp ? new Date(trade.timestamp).toLocaleTimeString() : ''}
                      </div>
                    )}
                  </button>
                );
              })
            )}
          </div>

          {!compactMode && (
            <div className="trade-detail-panel" style={{flex: '1', minHeight: '400px'}}>
              {!selectedTrade ? (
                <div className="trade-empty-detail" style={{
                  padding: '40px',
                  textAlign: 'center',
                  color: 'var(--muted)',
                  background: 'var(--panel)',
                  borderRadius: '8px',
                  border: '1px solid var(--line)'
                }}>
                  Select a trade to see details.
                </div>
              ) : (
                <div className="trade-detail-card" style={{
                  background: 'var(--panel)',
                  borderRadius: '8px',
                  border: '1px solid var(--line)',
                  overflow: 'hidden'
                }}>
                  <div className="trade-detail-header" style={{
                    padding: '16px',
                    background: 'var(--glass)',
                    borderBottom: '1px solid var(--line)'
                  }}>
                    <div style={{marginBottom: '8px'}}>
                      <h3 style={{fontSize: '1.2rem', margin: '0 0 4px 0'}}>
                        {selectedTrade.symbol || NOT_AVAILABLE}
                      </h3>
                      <p style={{margin: 0, fontSize: '0.85rem', color: 'var(--muted)'}}>
                        {selectedTrade.bot_name || 'Bot'} • {getPlatformDisplayName(selectedTrade.exchange?.toLowerCase())}
                      </p>
                    </div>
                    <span style={{fontSize: '0.8rem', color: 'var(--muted)'}}>
                      {selectedTrade.timestamp ? new Date(selectedTrade.timestamp).toLocaleString() : NOT_AVAILABLE}
                    </span>
                  </div>
                  <div className="trade-detail-grid" style={{
                    display: 'grid',
                    gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))',
                    gap: '16px',
                    padding: '20px'
                  }}>
                    <div>
                      <span style={{fontSize: '0.75rem', fontWeight: 600, color: 'var(--muted)', display: 'block', marginBottom: '4px'}}>
                        Side
                      </span>
                      <strong style={{fontSize: '1rem'}}>
                        {(selectedTrade.side || selectedTrade.action || 'Trade').toUpperCase()}
                      </strong>
                    </div>
                    <div>
                      <span style={{fontSize: '0.75rem', fontWeight: 600, color: 'var(--muted)', display: 'block', marginBottom: '4px'}}>
                        Price
                      </span>
                      <strong style={{fontSize: '1rem'}}>
                        {formatZAR(selectedTrade.price || selectedTrade.avg_price)}
                      </strong>
                    </div>
                    <div>
                      <span style={{fontSize: '0.75rem', fontWeight: 600, color: 'var(--muted)', display: 'block', marginBottom: '4px'}}>
                        Quantity
                      </span>
                      <strong style={{fontSize: '1rem'}}>
                        {selectedTrade.size || selectedTrade.quantity || NOT_AVAILABLE}
                      </strong>
                    </div>
                    <div>
                      <span style={{fontSize: '0.75rem', fontWeight: 600, color: 'var(--muted)', display: 'block', marginBottom: '4px'}}>
                        Fees
                      </span>
                      <strong style={{fontSize: '1rem'}}>
                        {formatZAR(selectedTrade.fees || selectedTrade.fee)}
                      </strong>
                    </div>
                    <div>
                      <span style={{fontSize: '0.75rem', fontWeight: 600, color: 'var(--muted)', display: 'block', marginBottom: '4px'}}>
                        PnL
                      </span>
                      <strong style={{
                        fontSize: '1rem',
                        color: (selectedTrade.profit_loss || 0) >= 0 ? 'var(--success)' : 'var(--error)'
                      }}>
                        {formatZAR(selectedTrade.profit_loss || 0)}
                      </strong>
                    </div>
                    <div>
                      <span style={{fontSize: '0.75rem', fontWeight: 600, color: 'var(--muted)', display: 'block', marginBottom: '4px'}}>
                        Mode
                      </span>
                      <strong style={{fontSize: '1rem', textTransform: 'capitalize'}}>
                        {selectedTrade.trading_mode || selectedTrade.mode || 'Paper'}
                      </strong>
                    </div>
                    <div>
                      <span style={{fontSize: '0.75rem', fontWeight: 600, color: 'var(--muted)', display: 'block', marginBottom: '4px'}}>
                        Status
                      </span>
                      <strong style={{fontSize: '1rem', textTransform: 'capitalize'}}>
                        {selectedTrade.status || 'Filled'}
                      </strong>
                    </div>
                    <div>
                      <span style={{fontSize: '0.75rem', fontWeight: 600, color: 'var(--muted)', display: 'block', marginBottom: '4px'}}>
                        Order ID
                      </span>
                      <strong style={{fontSize: '0.85rem', fontFamily: 'monospace', wordBreak: 'break-all'}}>
                        {selectedTrade.order_id || selectedTrade.id || NOT_AVAILABLE}
                      </strong>
                    </div>
                    {selectedTrade.slippage && (
                      <div>
                        <span style={{fontSize: '0.75rem', fontWeight: 600, color: 'var(--muted)', display: 'block', marginBottom: '4px'}}>
                          Slippage
                        </span>
                        <strong style={{fontSize: '1rem'}}>
                          {selectedTrade.slippage}
                        </strong>
                      </div>
                    )}
                    {(selectedTrade.reason || selectedTrade.decision_trace) && (
                      <div style={{gridColumn: '1 / -1'}}>
                        <span style={{fontSize: '0.75rem', fontWeight: 600, color: 'var(--muted)', display: 'block', marginBottom: '6px'}}>
                          Decision Trace
                        </span>
                        <div style={{
                          padding: '12px',
                          background: 'var(--glass)',
                          borderRadius: '6px',
                          fontSize: '0.85rem',
                          fontFamily: 'monospace',
                          whiteSpace: 'pre-wrap',
                          wordBreak: 'break-word'
                        }}>
                          {selectedTrade.reason || selectedTrade.decision_trace}
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Pagination */}
        {totalPages > 1 && (
          <div style={{
            display: 'flex',
            justifyContent: 'center',
            alignItems: 'center',
            gap: '12px',
            marginTop: '20px',
            padding: '16px',
            background: 'var(--glass)',
            borderRadius: '8px',
            border: '1px solid var(--line)'
          }}>
            <button
              onClick={() => setCurrentPage(prev => Math.max(1, prev - 1))}
              disabled={currentPage === 1}
              style={{
                padding: '8px 16px',
                background: currentPage === 1 ? 'var(--panel)' : 'var(--accent2)',
                color: 'var(--text)',
                border: '1px solid var(--line)',
                borderRadius: '6px',
                fontWeight: 600,
                cursor: currentPage === 1 ? 'not-allowed' : 'pointer',
                opacity: currentPage === 1 ? 0.5 : 1
              }}
            >
              ← Previous
            </button>
            <span style={{fontSize: '0.9rem', fontWeight: 600}}>
              Page {currentPage} of {totalPages}
            </span>
            <button
              onClick={() => setCurrentPage(prev => Math.min(totalPages, prev + 1))}
              disabled={currentPage === totalPages}
              style={{
                padding: '8px 16px',
                background: currentPage === totalPages ? 'var(--panel)' : 'var(--accent2)',
                color: 'var(--text)',
                border: '1px solid var(--line)',
                borderRadius: '6px',
                fontWeight: 600,
                cursor: currentPage === totalPages ? 'not-allowed' : 'pointer',
                opacity: currentPage === totalPages ? 0.5 : 1
              }}
            >
              Next →
            </button>
          </div>
        )}
      </div>
    </section>
  );
}
