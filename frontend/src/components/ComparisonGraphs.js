/**
 * ComparisonGraphs Component
 * 
 * Displays profit/ROI/trades/win rate graphs with daily/weekly/monthly periods
 * Supports platform breakdown and real-time updates
 */

import { useState, useEffect } from 'react';
import { Line, Bar } from 'react-chartjs-2';
import { useRealtimeEvent } from '../hooks/useRealtime';
import { get } from '../lib/apiClient';
import { Card } from './ui/card';
import { Badge } from './ui/badge';
import './ComparisonGraphs.css';

export default function ComparisonGraphs({ platformFilter = 'all' }) {
  const [period, setPeriod] = useState('daily');
  const [metric, setMetric] = useState('profit');
  const [loading, setLoading] = useState(true);
  const [graphData, setGraphData] = useState(null);
  const [lastUpdate, setLastUpdate] = useState(null);

  // Load graph data
  useEffect(() => {
    loadGraphData();
  }, [period, metric, platformFilter]);

  const loadGraphData = async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({
        period,
        platform: platformFilter
      });
      const data = await get(`/analytics/profit-history?${params}`);
      processGraphData(data);
      setLastUpdate(new Date().toISOString());
      setLoading(false);
    } catch (error) {
      console.error('Failed to load graph data:', error);
      setLoading(false);
    }
  };

  const processGraphData = (data) => {
    if (!data || !data.history) {
      setGraphData(null);
      return;
    }

    const labels = data.history.map(item => formatLabel(item.timestamp, period));
    const values = data.history.map(item => {
      switch (metric) {
        case 'profit':
          return item.profit || 0;
        case 'roi':
          return item.roi || 0;
        case 'trades':
          return item.trade_count || 0;
        case 'win_rate':
          return (item.win_rate || 0) * 100;
        default:
          return 0;
      }
    });

    setGraphData({
      labels,
      datasets: [{
        label: getMetricLabel(),
        data: values,
        borderColor: getMetricColor(),
        backgroundColor: getMetricColor() + '33',
        fill: true,
        tension: 0.4
      }]
    });
  };

  // Subscribe to real-time updates
  useRealtimeEvent('trades', () => {
    // Debounce graph refresh on new trades
    const timer = setTimeout(() => {
      loadGraphData();
    }, 5000);
    return () => clearTimeout(timer);
  }, [period, metric, platformFilter]);

  const formatLabel = (timestamp, period) => {
    const date = new Date(timestamp);
    switch (period) {
      case 'daily':
        return date.toLocaleDateString('en-ZA', { month: 'short', day: 'numeric' });
      case 'weekly':
        return `Week ${getWeekNumber(date)}`;
      case 'monthly':
        return date.toLocaleDateString('en-ZA', { month: 'short', year: 'numeric' });
      default:
        return date.toLocaleDateString();
    }
  };

  const getWeekNumber = (date) => {
    const firstDayOfYear = new Date(date.getFullYear(), 0, 1);
    const pastDaysOfYear = (date - firstDayOfYear) / 86400000;
    return Math.ceil((pastDaysOfYear + firstDayOfYear.getDay() + 1) / 7);
  };

  const getMetricLabel = () => {
    const labels = {
      profit: 'Profit (ZAR)',
      roi: 'ROI (%)',
      trades: 'Number of Trades',
      win_rate: 'Win Rate (%)'
    };
    return labels[metric] || 'Value';
  };

  const getMetricColor = () => {
    const colors = {
      profit: 'rgb(34, 197, 94)',
      roi: 'rgb(59, 130, 246)',
      trades: 'rgb(168, 85, 247)',
      win_rate: 'rgb(251, 191, 36)'
    };
    return colors[metric] || 'rgb(156, 163, 175)';
  };

  const formatTime = (timestamp) => {
    if (!timestamp) return 'Not available';
    const date = new Date(timestamp);
    return date.toLocaleTimeString('en-ZA', { 
      hour: '2-digit', 
      minute: '2-digit'
    });
  };

  const chartOptions = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: {
        display: false
      },
      tooltip: {
        backgroundColor: 'rgba(17, 24, 39, 0.9)',
        titleColor: '#fff',
        bodyColor: '#fff',
        borderColor: 'rgba(255, 255, 255, 0.1)',
        borderWidth: 1,
        padding: 12,
        displayColors: false
      }
    },
    scales: {
      x: {
        grid: {
          color: 'rgba(255, 255, 255, 0.05)'
        },
        ticks: {
          color: 'rgba(255, 255, 255, 0.6)'
        }
      },
      y: {
        grid: {
          color: 'rgba(255, 255, 255, 0.05)'
        },
        ticks: {
          color: 'rgba(255, 255, 255, 0.6)'
        },
        beginAtZero: true
      }
    }
  };

  if (loading && !graphData) {
    return (
      <Card className="comparison-graphs p-6">
        <div className="flex items-center justify-center h-64">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary"></div>
        </div>
      </Card>
    );
  }

  return (
    <Card className="comparison-graphs">
      <div className="p-4 border-b border-border">
        <div className="flex items-center justify-between flex-wrap gap-4">
          <h3 className="text-lg font-semibold">Performance Metrics</h3>
          
          <div className="flex items-center gap-2 flex-wrap">
            {/* Period Selector */}
            <div className="flex items-center gap-1 bg-accent/30 rounded-lg p-1">
              {['daily', 'weekly', 'monthly'].map(p => (
                <button
                  key={p}
                  onClick={() => setPeriod(p)}
                  className={`px-3 py-1 rounded text-sm transition-colors ${
                    period === p 
                      ? 'bg-primary text-primary-foreground' 
                      : 'hover:bg-accent'
                  }`}
                >
                  {p.charAt(0).toUpperCase() + p.slice(1)}
                </button>
              ))}
            </div>

            {/* Metric Selector */}
            <div className="flex items-center gap-1 bg-accent/30 rounded-lg p-1">
              {[
                { value: 'profit', label: 'Profit' },
                { value: 'roi', label: 'ROI' },
                { value: 'trades', label: 'Trades' },
                { value: 'win_rate', label: 'Win Rate' }
              ].map(m => (
                <button
                  key={m.value}
                  onClick={() => setMetric(m.value)}
                  className={`px-3 py-1 rounded text-sm transition-colors ${
                    metric === m.value 
                      ? 'bg-primary text-primary-foreground' 
                      : 'hover:bg-accent'
                  }`}
                >
                  {m.label}
                </button>
              ))}
            </div>
          </div>
        </div>

        {lastUpdate && (
          <p className="text-xs text-muted-foreground mt-2">
            Last updated: {formatTime(lastUpdate)}
          </p>
        )}
      </div>

      <div className="p-4">
        {!graphData ? (
          <div className="flex items-center justify-center h-64 text-muted-foreground">
            <div className="text-center">
              <p>No data available</p>
              <p className="text-sm mt-2">Data will appear when trades are executed</p>
            </div>
          </div>
        ) : (
          <div className="h-64">
            <Line data={graphData} options={chartOptions} />
          </div>
        )}
      </div>
    </Card>
  );
}
