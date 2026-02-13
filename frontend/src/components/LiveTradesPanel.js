/**
 * LiveTradesPanel Component
 * 
 * Left panel (50%) showing live trades stream with real-time updates
 * Supports platform filtering and displays trade details
 */

import { useState, useEffect } from 'react';
import { useRealtimeEvent, useLastUpdate } from '../hooks/useRealtime';
import { filterByPlatform, getPlatformIcon, getPlatformName } from '../lib/platforms';
import { get } from '../lib/apiClient';
import { Card } from './ui/card';
import { Badge } from './ui/badge';
import './LiveTradesPanel.css';

export default function LiveTradesPanel({ platformFilter = 'all' }) {
  const [trades, setTrades] = useState([]);
  const [loading, setLoading] = useState(true);
  const lastUpdate = useLastUpdate('trades');

  // Load initial trades
  useEffect(() => {
    loadInitialTrades();
  }, []);

  const loadInitialTrades = async () => {
    try {
      const data = await get('/trades/recent?limit=50');
      setTrades(data.trades || []);
      setLoading(false);
    } catch (error) {
      console.error('Failed to load trades:', error);
      setLoading(false);
    }
  };

  // Subscribe to real-time trade updates
  useRealtimeEvent('trades', (newTrade) => {
    setTrades(prev => [newTrade, ...prev].slice(0, 50));
  }, []);

  // Filter trades by platform
  const filteredTrades = filterByPlatform(trades, platformFilter);

  const formatMoney = (amount, currency = 'ZAR') => {
    if (!amount) return 'Not available';
    return new Intl.NumberFormat('en-ZA', {
      style: 'currency',
      currency: currency,
      minimumFractionDigits: 2
    }).format(amount);
  };

  const formatTime = (timestamp) => {
    if (!timestamp) return 'Not available';
    const date = new Date(timestamp);
    return date.toLocaleTimeString('en-ZA', { 
      hour: '2-digit', 
      minute: '2-digit',
      second: '2-digit'
    });
  };

  const getSideColor = (side) => {
    return side === 'buy' ? 'text-green-400' : 'text-red-400';
  };

  const getStatusBadge = (status) => {
    const colors = {
      filled: 'bg-green-500/20 text-green-400',
      pending: 'bg-yellow-500/20 text-yellow-400',
      cancelled: 'bg-gray-500/20 text-gray-400',
      failed: 'bg-red-500/20 text-red-400'
    };
    return colors[status] || colors.pending;
  };

  if (loading) {
    return (
      <Card className="live-trades-panel h-full">
        <div className="p-6">
          <div className="flex items-center justify-center h-64">
            <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary"></div>
          </div>
        </div>
      </Card>
    );
  }

  return (
    <Card className="live-trades-panel h-full flex flex-col">
      <div className="p-4 border-b border-border">
        <div className="flex items-center justify-between">
          <h3 className="text-lg font-semibold">Live Trades</h3>
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <span className="flex items-center gap-1">
              <span className="w-2 h-2 bg-green-500 rounded-full animate-pulse"></span>
              Live
            </span>
            {lastUpdate && (
              <span>Updated: {formatTime(lastUpdate)}</span>
            )}
          </div>
        </div>
        <p className="text-sm text-muted-foreground mt-1">
          {filteredTrades.length} trades
          {platformFilter !== 'all' && ` on ${getPlatformName(platformFilter)}`}
        </p>
      </div>

      <div className="flex-1 overflow-y-auto">
        {filteredTrades.length === 0 ? (
          <div className="flex items-center justify-center h-64 text-muted-foreground">
            <div className="text-center">
              <p>No trades yet</p>
              <p className="text-sm mt-2">Trades will appear here when executed</p>
            </div>
          </div>
        ) : (
          <div className="divide-y divide-border">
            {filteredTrades.map((trade, index) => (
              <div key={trade.id || index} className="p-4 hover:bg-accent/50 transition-colors">
                <div className="flex items-start justify-between mb-2">
                  <div className="flex items-center gap-2">
                    <span className="text-lg">{getPlatformIcon(trade.platform)}</span>
                    <div>
                      <p className="font-medium">{trade.symbol}</p>
                      <p className="text-xs text-muted-foreground">
                        {getPlatformName(trade.platform)}
                      </p>
                    </div>
                  </div>
                  <Badge className={getStatusBadge(trade.status)}>
                    {trade.status}
                  </Badge>
                </div>

                <div className="grid grid-cols-2 gap-4 text-sm">
                  <div>
                    <p className="text-muted-foreground">Side</p>
                    <p className={`font-medium uppercase ${getSideColor(trade.side)}`}>
                      {trade.side}
                    </p>
                  </div>
                  <div>
                    <p className="text-muted-foreground">Quantity</p>
                    <p className="font-medium">{trade.quantity}</p>
                  </div>
                  <div>
                    <p className="text-muted-foreground">Price</p>
                    <p className="font-medium">{formatMoney(trade.price)}</p>
                  </div>
                  <div>
                    <p className="text-muted-foreground">Total</p>
                    <p className="font-medium">{formatMoney(trade.total)}</p>
                  </div>
                </div>

                {trade.pnl !== null && trade.pnl !== undefined && (
                  <div className="mt-2 pt-2 border-t border-border">
                    <p className="text-sm text-muted-foreground">P&L</p>
                    <p className={`font-semibold ${trade.pnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                      {trade.pnl >= 0 ? '+' : ''}{formatMoney(trade.pnl)}
                    </p>
                  </div>
                )}

                <p className="text-xs text-muted-foreground mt-2">
                  {formatTime(trade.timestamp)}
                </p>
              </div>
            ))}
          </div>
        )}
      </div>
    </Card>
  );
}
