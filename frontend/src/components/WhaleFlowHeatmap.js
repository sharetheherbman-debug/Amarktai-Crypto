import { useState, useEffect } from 'react';
import { useRealtimeEvent, useLastUpdate } from '../hooks/useRealtime';
import { get } from '../lib/apiClient';
import { Card } from './ui/card';
import { Badge } from './ui/badge';
import { Bar } from 'react-chartjs-2';
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  BarElement,
  Title,
  Tooltip,
  Legend
} from 'chart.js';
import './WhaleFlowHeatmap.css';

ChartJS.register(
  CategoryScale,
  LinearScale,
  BarElement,
  Title,
  Tooltip,
  Legend
);

/**
 * WhaleFlowHeatmap Component
 * 
 * Visualizes on-chain whale activity across exchanges
 * Shows inflows (positive) and outflows (negative) for BTC, ETH, and stablecoins
 * Color-coded heatmap with real-time updates via WebSocket and polling fallback
 */
export default function WhaleFlowHeatmap() {
  const [whaleData, setWhaleData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [selectedCoin, setSelectedCoin] = useState('BTC');
  const [timeRange, setTimeRange] = useState('1h'); // 1h, 6h, 24h
  const lastUpdate = useLastUpdate('whale');

  // Format amount based on coin type
  const formatAmount = (amount, coin) => {
    if (!amount) return '0';
    if (coin === 'BTC') return amount.toFixed(2);
    if (coin === 'ETH') return amount.toFixed(0);
    return amount.toLocaleString();
  };

  // Fetch whale flow data
  const fetchWhaleData = async () => {
    try {
      const params = new URLSearchParams({ time_range: timeRange });
      const data = await get(`/advanced/whale/summary?${params}`);
      
      if (data.status === 'success') {
        setWhaleData(data.data);
        setError(null);
      } else if (data.message && data.message.includes('not configured')) {
        setError('Whale data not configured. Please configure whale tracking service.');
      } else {
        setError(data.message || 'Failed to fetch whale data');
      }
    } catch (err) {
      console.error('Error fetching whale data:', err);
      if (err.message && err.message.includes('not configured')) {
        setError('Whale data not configured. Please configure whale tracking service.');
      } else {
        setError(err.message || 'Failed to fetch whale data');
      }
    } finally {
      setLoading(false);
    }
  };

  // Initial fetch
  useEffect(() => {
    fetchWhaleData();
  }, [timeRange]);

  // Subscribe to real-time whale updates
  useRealtimeEvent('whale', (data) => {
    setWhaleData(prevData => ({
      ...prevData,
      ...data
    }));
  }, []);

  // Polling fallback (every 60s)
  useEffect(() => {
    const interval = setInterval(fetchWhaleData, 60000);
    return () => clearInterval(interval);
  }, [timeRange]);

  // Prepare chart data
  const getChartData = () => {
    if (!whaleData || !whaleData.exchanges) {
      return null;
    }

    const exchanges = Object.keys(whaleData.exchanges);
    const inflowData = exchanges.map(ex => whaleData.exchanges[ex][selectedCoin]?.inflow || 0);
    const outflowData = exchanges.map(ex => -(whaleData.exchanges[ex][selectedCoin]?.outflow || 0));

    return {
      labels: exchanges,
      datasets: [
        {
          label: 'Inflows',
          data: inflowData,
          backgroundColor: 'rgba(34, 197, 94, 0.7)',
          borderColor: 'rgba(34, 197, 94, 1)',
          borderWidth: 2
        },
        {
          label: 'Outflows',
          data: outflowData,
          backgroundColor: 'rgba(239, 68, 68, 0.7)',
          borderColor: 'rgba(239, 68, 68, 1)',
          borderWidth: 2
        }
      ]
    };
  };

  const chartOptions = {
    responsive: true,
    maintainAspectRatio: false,
    scales: {
      y: {
        beginAtZero: true,
        ticks: {
          callback: (value) => {
            if (selectedCoin === 'BTC') {
              return `${Math.abs(value).toFixed(2)} BTC`;
            } else if (selectedCoin === 'ETH') {
              return `${Math.abs(value).toFixed(0)} ETH`;
            } else {
              return `$${Math.abs(value).toLocaleString()}`;
            }
          }
        }
      }
    },
    plugins: {
      legend: {
        position: 'top'
      },
      tooltip: {
        callbacks: {
          label: (context) => {
            const value = Math.abs(context.raw);
            let label = context.dataset.label + ': ';
            
            if (selectedCoin === 'BTC') {
              label += `${value.toFixed(2)} BTC`;
            } else if (selectedCoin === 'ETH') {
              label += `${value.toFixed(0)} ETH`;
            } else {
              label += `$${value.toLocaleString()}`;
            }
            
            return label;
          }
        }
      }
    }
  };

  // Calculate net flow color
  const getNetFlowColor = (netFlow) => {
    if (!netFlow) return 'bg-gray-100 text-gray-600';
    if (netFlow > 1000) return 'bg-green-100 text-green-700';
    if (netFlow > 0) return 'bg-green-50 text-green-600';
    if (netFlow < -1000) return 'bg-red-100 text-red-700';
    if (netFlow < 0) return 'bg-red-50 text-red-600';
    return 'bg-gray-100 text-gray-600';
  };

  // Get signal strength badge
  const getSignalBadge = (signal) => {
    if (!signal) return null;
    
    const strength = signal.strength || 0;
    const recommendation = signal.recommendation || 'neutral';
    
    let variant = 'outline';
    let color = 'text-gray-600';
    
    if (recommendation === 'accumulation') {
      variant = 'default';
      color = 'text-green-600';
    } else if (recommendation === 'distribution') {
      variant = 'destructive';
      color = 'text-red-600';
    }
    
    return (
      <Badge variant={variant} className={color}>
        {String(recommendation ?? '').toUpperCase()} ({(strength * 100).toFixed(0)}%)
      </Badge>
    );
  };

  if (loading) {
    return (
      <Card className="p-6">
        <div className="text-center">
          <p className="text-gray-500">Loading whale flow data...</p>
        </div>
      </Card>
    );
  }

  if (error) {
    return (
      <Card className="p-6">
        <div className="text-center text-red-600">
          <p>Error: {error}</p>
          <button
            onClick={fetchWhaleData}
            className="mt-2 px-4 py-2 bg-blue-500 text-white rounded hover:bg-blue-600"
          >
            Retry
          </button>
        </div>
      </Card>
    );
  }

  const chartData = getChartData();

  return (
    <div className="whale-flow-heatmap">
      <Card className="p-6">
        {/* Header */}
        <div className="flex items-center justify-between mb-4">
          <div>
            <h2 className="text-2xl font-bold">Whale Flow Heatmap</h2>
            <p className="text-sm text-gray-500">On-Chain Exchange Flows</p>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={fetchWhaleData}
              className="px-3 py-1 text-sm border rounded hover:bg-gray-50"
              title="Refresh"
            >
              🔄 Refresh
            </button>
            <Badge variant={lastUpdate ? 'default' : 'outline'}>
              {lastUpdate ? '🟢 Live' : '⏸️ Waiting'}
            </Badge>
            {lastUpdate && (
              <span className="text-xs text-muted-foreground ml-2">
                Updated: {new Date(lastUpdate).toLocaleTimeString()}
              </span>
            )}
          </div>
        </div>

        {/* Controls */}
        <div className="flex items-center gap-4 mb-4">
          {/* Coin selector */}
          <div className="flex gap-2">
            <label className="text-sm font-medium">Asset:</label>
            {['BTC', 'ETH', 'USDT', 'USDC'].map(coin => (
              <button
                key={coin}
                onClick={() => setSelectedCoin(coin)}
                className={`px-3 py-1 text-sm rounded ${
                  selectedCoin === coin
                    ? 'bg-blue-500 text-white'
                    : 'bg-gray-100 hover:bg-gray-200'
                }`}
              >
                {coin}
              </button>
            ))}
          </div>

          {/* Time range selector */}
          <div className="flex gap-2">
            <label className="text-sm font-medium">Period:</label>
            {['1h', '6h', '24h'].map(range => (
              <button
                key={range}
                onClick={() => setTimeRange(range)}
                className={`px-3 py-1 text-sm rounded ${
                  timeRange === range
                    ? 'bg-blue-500 text-white'
                    : 'bg-gray-100 hover:bg-gray-200'
                }`}
              >
                {range}
              </button>
            ))}
          </div>
        </div>

        {/* Summary Stats */}
        {whaleData && whaleData.summary && (
          <div className="grid grid-cols-3 gap-4 mb-6">
            <div className="stat-card">
              <p className="text-sm text-gray-500">Total Inflow</p>
              <p className="text-xl font-bold text-green-600">
                {selectedCoin === 'BTC' && `${formatAmount(whaleData.summary[selectedCoin]?.total_inflow, 'BTC')} BTC`}
                {selectedCoin === 'ETH' && `${formatAmount(whaleData.summary[selectedCoin]?.total_inflow, 'ETH')} ETH`}
                {(selectedCoin === 'USDT' || selectedCoin === 'USDC') && 
                  `$${formatAmount(whaleData.summary[selectedCoin]?.total_inflow, 'USD')}`}
              </p>
            </div>
            <div className="stat-card">
              <p className="text-sm text-gray-500">Total Outflow</p>
              <p className="text-xl font-bold text-red-600">
                {selectedCoin === 'BTC' && `${formatAmount(whaleData.summary[selectedCoin]?.total_outflow, 'BTC')} BTC`}
                {selectedCoin === 'ETH' && `${formatAmount(whaleData.summary[selectedCoin]?.total_outflow, 'ETH')} ETH`}
                {(selectedCoin === 'USDT' || selectedCoin === 'USDC') && 
                  `$${formatAmount(whaleData.summary[selectedCoin]?.total_outflow, 'USD')}`}
              </p>
            </div>
            <div className={`stat-card ${getNetFlowColor(whaleData.summary[selectedCoin]?.net_flow)}`}>
              <p className="text-sm">Net Flow</p>
              <p className="text-xl font-bold">
                {selectedCoin === 'BTC' && `${formatAmount(whaleData.summary[selectedCoin]?.net_flow, 'BTC')} BTC`}
                {selectedCoin === 'ETH' && `${formatAmount(whaleData.summary[selectedCoin]?.net_flow, 'ETH')} ETH`}
                {(selectedCoin === 'USDT' || selectedCoin === 'USDC') && 
                  `$${formatAmount(whaleData.summary[selectedCoin]?.net_flow, 'USD')}`}
              </p>
              {whaleData.signals && whaleData.signals[selectedCoin] && (
                <div className="mt-2">
                  {getSignalBadge(whaleData.signals[selectedCoin])}
                </div>
              )}
            </div>
          </div>
        )}

        {/* Chart */}
        {chartData && (
          <div className="chart-container" style={{ height: '400px' }}>
            <Bar data={chartData} options={chartOptions} />
          </div>
        )}

        {/* Exchange Details */}
        {whaleData && whaleData.exchanges && (
          <div className="mt-6">
            <h3 className="text-lg font-semibold mb-3">Exchange Breakdown</h3>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
              {Object.entries(whaleData.exchanges).map(([exchange, data]) => {
                const coinData = data[selectedCoin] || {};
                const netFlow = coinData.net_flow || 0;
                
                return (
                  <div key={exchange} className="exchange-card">
                    <h4 className="font-semibold mb-2">{exchange}</h4>
                    <div className="text-sm space-y-1">
                      <div className="flex justify-between">
                        <span className="text-gray-500">Inflow:</span>
                        <span className="text-green-600 font-medium">
                          +{coinData.inflow?.toFixed(2) || 0}
                        </span>
                      </div>
                      <div className="flex justify-between">
                        <span className="text-gray-500">Outflow:</span>
                        <span className="text-red-600 font-medium">
                          -{coinData.outflow?.toFixed(2) || 0}
                        </span>
                      </div>
                      <div className="flex justify-between border-t pt-1">
                        <span className="font-medium">Net:</span>
                        <span className={netFlow > 0 ? 'text-green-600' : 'text-red-600'}>
                          {netFlow > 0 ? '+' : ''}{netFlow.toFixed(2)}
                        </span>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* Last Update */}
        {whaleData && whaleData.last_update && (
          <div className="mt-4 text-xs text-gray-500 text-center">
            Last updated: {new Date(whaleData.last_update).toLocaleString()}
          </div>
        )}
      </Card>
    </div>
  );
}
