/**
 * PlatformPanel Component
 * 
 * Right panel (50%) showing platform-specific information:
 * - Bots running on the platform
 * - Wallet/balance snapshot
 * - Connection status and last update
 */

import { useState, useEffect } from 'react';
import { useRealtimeEvent, useLastUpdate } from '../hooks/useRealtime';
import { getPlatformIcon, getPlatformName, filterByPlatform } from '../lib/platforms';
import { get } from '../lib/apiClient';
import { Card } from './ui/card';
import { Badge } from './ui/badge';
import './PlatformPanel.css';

export default function PlatformPanel({ platformFilter = 'all', bots = [], balances = {} }) {
  const [platformBots, setPlatformBots] = useState([]);
  const [platformBalances, setPlatformBalances] = useState(null);
  const lastBotUpdate = useLastUpdate('bots');
  const lastBalanceUpdate = useLastUpdate('balances');

  // Filter bots by platform
  useEffect(() => {
    if (platformFilter === 'all') {
      setPlatformBots(bots);
    } else {
      const filtered = filterByPlatform(bots, platformFilter, 'platform');
      setPlatformBots(filtered);
    }
  }, [platformFilter, bots]);

  // Update balances for the platform
  useRealtimeEvent('balances', (data) => {
    if (platformFilter === 'all' || data.platform === platformFilter) {
      setPlatformBalances(data);
    }
  }, [platformFilter]);

  const formatMoney = (amount, currency = 'ZAR') => {
    if (!amount && amount !== 0) return 'Not available';
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
      minute: '2-digit'
    });
  };

  const getStatusColor = (status) => {
    const colors = {
      running: 'bg-green-500/20 text-green-400',
      stopped: 'bg-gray-500/20 text-gray-400',
      paused: 'bg-yellow-500/20 text-yellow-400',
      error: 'bg-red-500/20 text-red-400'
    };
    return colors[status] || colors.stopped;
  };

  const getModeColor = (mode) => {
    return mode === 'live' ? 'bg-red-500/20 text-red-400' : 'bg-blue-500/20 text-blue-400';
  };

  return (
    <Card className="platform-panel h-full flex flex-col">
      <div className="p-4 border-b border-border">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            {platformFilter !== 'all' && (
              <span className="text-2xl">{getPlatformIcon(platformFilter)}</span>
            )}
            <div>
              <h3 className="text-lg font-semibold">
                {platformFilter === 'all' ? 'All Platforms' : getPlatformName(platformFilter)}
              </h3>
              <p className="text-sm text-muted-foreground">
                {platformBots.length} bots running
              </p>
            </div>
          </div>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {/* Bots Section */}
        <div>
          <h4 className="text-sm font-semibold mb-3 flex items-center justify-between">
            <span>Active Bots</span>
            {lastBotUpdate && (
              <span className="text-xs text-muted-foreground font-normal">
                Updated: {formatTime(lastBotUpdate)}
              </span>
            )}
          </h4>
          {platformBots.length === 0 ? (
            <div className="text-center py-8 text-muted-foreground">
              <p>No bots running</p>
              <p className="text-sm mt-2">Create a bot to get started</p>
            </div>
          ) : (
            <div className="space-y-2">
              {platformBots.map(bot => (
                <div key={bot.id} className="p-3 rounded-lg bg-accent/30 hover:bg-accent/50 transition-colors">
                  <div className="flex items-start justify-between mb-2">
                    <div className="flex-1">
                      <p className="font-medium">{bot.name}</p>
                      <p className="text-xs text-muted-foreground">{bot.symbol}</p>
                    </div>
                    <div className="flex flex-col items-end gap-1">
                      <Badge className={getStatusColor(bot.status)}>
                        {bot.status}
                      </Badge>
                      <Badge className={getModeColor(bot.trading_mode)}>
                        {bot.trading_mode}
                      </Badge>
                    </div>
                  </div>
                  <div className="grid grid-cols-2 gap-2 text-sm">
                    <div>
                      <p className="text-muted-foreground text-xs">Capital</p>
                      <p className="font-medium">{formatMoney(bot.capital)}</p>
                    </div>
                    <div>
                      <p className="text-muted-foreground text-xs">P&L</p>
                      <p className={`font-medium ${bot.pnl >= 0 ? 'text-green-400' : 'text-red-400'}`}>
                        {bot.pnl >= 0 ? '+' : ''}{formatMoney(bot.pnl)}
                      </p>
                    </div>
                    <div>
                      <p className="text-muted-foreground text-xs">Trades</p>
                      <p className="font-medium">{bot.trades_count || 0}</p>
                    </div>
                    <div>
                      <p className="text-muted-foreground text-xs">Win Rate</p>
                      <p className="font-medium">
                        {bot.win_rate ? `${(bot.win_rate * 100).toFixed(1)}%` : 'Not available'}
                      </p>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Wallet/Balances Section */}
        {platformFilter !== 'all' && (
          <div>
            <h4 className="text-sm font-semibold mb-3 flex items-center justify-between">
              <span>Wallet Balances</span>
              {lastBalanceUpdate && (
                <span className="text-xs text-muted-foreground font-normal">
                  Updated: {formatTime(lastBalanceUpdate)}
                </span>
              )}
            </h4>
            {platformBalances && platformBalances.balances ? (
              <div className="space-y-2">
                {Object.entries(platformBalances.balances).map(([asset, balance]) => (
                  <div key={asset} className="p-3 rounded-lg bg-accent/30">
                    <div className="flex items-center justify-between">
                      <span className="font-medium">{asset}</span>
                      <span className="text-muted-foreground text-sm">
                        {balance.free || 0} {asset}
                      </span>
                    </div>
                    {balance.locked > 0 && (
                      <p className="text-xs text-muted-foreground mt-1">
                        Locked: {balance.locked} {asset}
                      </p>
                    )}
                  </div>
                ))}
                {platformBalances.total_value_zar && (
                  <div className="pt-2 border-t border-border">
                    <p className="text-sm text-muted-foreground">Total Value</p>
                    <p className="text-lg font-semibold">
                      {formatMoney(platformBalances.total_value_zar)}
                    </p>
                  </div>
                )}
              </div>
            ) : (
              <div className="text-center py-6 text-muted-foreground text-sm">
                <p>No balance data available</p>
              </div>
            )}
          </div>
        )}

        {/* Connection Status */}
        <div className="pt-4 border-t border-border">
          <div className="flex items-center justify-between text-sm">
            <span className="text-muted-foreground">Connection</span>
            <div className="flex items-center gap-2">
              <span className="w-2 h-2 bg-green-500 rounded-full animate-pulse"></span>
              <span className="text-green-400">Connected</span>
            </div>
          </div>
        </div>
      </div>
    </Card>
  );
}
