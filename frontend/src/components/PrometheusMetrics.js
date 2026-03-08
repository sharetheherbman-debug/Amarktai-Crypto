import { useState, useEffect } from 'react';
import { useRealtimeEvent, useLastUpdate } from '../hooks/useRealtime';
import { get, notifyError } from '../lib/apiClient';
import { Card } from './ui/card';
import { Badge } from './ui/badge';
import { Line } from 'react-chartjs-2';
import './PrometheusMetrics.css';

/**
 * PrometheusMetrics Component
 * 
 * Displays Golden Signals from Prometheus metrics and system health
 * - Latency: Tick-to-trade execution time
 * - Traffic: Request rate and throughput
 * - Errors: Error rate and types
 * - Saturation: System resource usage
 * Integrates with unified real-time system for live updates
 */
export default function PrometheusMetrics() {
  const [metrics, setMetrics] = useState(null);
  const [parsedMetrics, setParsedMetrics] = useState(null);
  const [systemHealth, setSystemHealth] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [selectedMetric, setSelectedMetric] = useState('latency');
  const [autoRefresh, setAutoRefresh] = useState(true);
  const lastUpdate = useLastUpdate('system_health');

  // Parse Prometheus text format
  const parsePrometheusMetrics = (text) => {
    const lines = text.split('\n');
    const parsed = {
      latency: { avg: 0, p95: 0, p99: 0 },
      traffic: { requests_total: 0, requests_per_sec: 0 },
      errors: { error_rate: 0, errors_total: 0 },
      saturation: { cpu_usage: 0, memory_usage: 0 },
      trading: {
        trades_total: 0,
        trades_success: 0,
        trades_failed: 0,
        profit_total: 0
      },
      components: {}
    };

    lines.forEach(line => {
      if (line.startsWith('#') || !line.trim()) return;

      // Latency metrics
      if (line.includes('trade_execution_latency_seconds')) {
        if (line.includes('quantile="0.95"')) {
          const match = line.match(/(\d+\.?\d*)/);
          if (match) parsed.latency.p95 = parseFloat(match[1]) * 1000; // Convert to ms
        } else if (line.includes('quantile="0.99"')) {
          const match = line.match(/(\d+\.?\d*)/);
          if (match) parsed.latency.p99 = parseFloat(match[1]) * 1000;
        } else if (line.includes('_sum')) {
          const match = line.match(/(\d+\.?\d*)/);
          if (match) parsed.latency.sum = parseFloat(match[1]);
        } else if (line.includes('_count')) {
          const match = line.match(/(\d+\.?\d*)/);
          if (match) {
            parsed.latency.count = parseFloat(match[1]);
            if (parsed.latency.sum && parsed.latency.count > 0) {
              parsed.latency.avg = (parsed.latency.sum / parsed.latency.count) * 1000;
            }
          }
        }
      }

      // Traffic metrics
      if (line.includes('api_requests_total')) {
        const match = line.match(/(\d+\.?\d*)/);
        if (match) parsed.traffic.requests_total = parseFloat(match[1]);
      }

      // Error metrics
      if (line.includes('api_errors_total')) {
        const match = line.match(/(\d+\.?\d*)/);
        if (match) parsed.errors.errors_total = parseFloat(match[1]);
      }

      // Trading metrics
      if (line.includes('trades_total{') && line.includes('status="success"')) {
        const match = line.match(/(\d+\.?\d*)/);
        if (match) parsed.trading.trades_success = parseFloat(match[1]);
      }
      if (line.includes('trades_total{') && line.includes('status="failed"')) {
        const match = line.match(/(\d+\.?\d*)/);
        if (match) parsed.trading.trades_failed = parseFloat(match[1]);
      }
      if (line.includes('total_profit_usd')) {
        const match = line.match(/(\d+\.?\d*)/);
        if (match) parsed.trading.profit_total = parseFloat(match[1]);
      }

      // Component health
      if (line.includes('component_health{')) {
        const componentMatch = line.match(/component="([^"]+)"/);
        const valueMatch = line.match(/(\d+\.?\d*)$/);
        if (componentMatch && valueMatch) {
          const component = componentMatch[1];
          const health = parseFloat(valueMatch[1]);
          parsed.components[component] = health;
        }
      }
    });

    // Calculate derived metrics
    parsed.trading.trades_total = parsed.trading.trades_success + parsed.trading.trades_failed;
    if (parsed.trading.trades_total > 0) {
      parsed.trading.success_rate = (parsed.trading.trades_success / parsed.trading.trades_total) * 100;
    } else {
      parsed.trading.success_rate = 0;
    }

    if (parsed.traffic.requests_total > 0) {
      parsed.errors.error_rate = (parsed.errors.errors_total / parsed.traffic.requests_total) * 100;
    }

    return parsed;
  };

  // Fetch metrics from Prometheus endpoint and system health
  const fetchMetrics = async () => {
    try {
      const metricsText = await get('/metrics', {
        responseType: 'text',
        headers: { Accept: 'text/plain' }
      });

      setMetrics(metricsText);
      const parsed = parsePrometheusMetrics(metricsText);
      setParsedMetrics(parsed);
      
      // Fetch system health
      try {
        const healthData = await get('/system/health');
        setSystemHealth(healthData);
      } catch (healthErr) {
        console.error('Error fetching system health:', healthErr);
        notifyError(healthErr);
      }
      
      setError(null);
    } catch (err) {
      console.error('Error fetching metrics:', err);
      const errorMessage = err.message || 'Failed to fetch metrics';
      const statusCode = err.status || err.response?.status || 'Not available';
      setError(`Metrics not available yet (${statusCode}): ${errorMessage}`);
      notifyError(err);
    } finally {
      setLoading(false);
    }
  };

  // Initial fetch
  useEffect(() => {
    fetchMetrics();
  }, []);

  // Subscribe to real-time system health updates
  useRealtimeEvent('system_health', (data) => {
    setSystemHealth(data);
  }, []);

  // Polling fallback (every 10 seconds)
  useEffect(() => {
    const interval = setInterval(fetchMetrics, 10000);
    return () => clearInterval(interval);
  }, []);

  // Get status color based on value
  const getStatusColor = (value, type) => {
    if (type === 'latency') {
      if (value < 100) return 'text-green-600 bg-green-50';
      if (value < 500) return 'text-yellow-600 bg-yellow-50';
      return 'text-red-600 bg-red-50';
    }
    if (type === 'error_rate') {
      if (value < 1) return 'text-green-600 bg-green-50';
      if (value < 5) return 'text-yellow-600 bg-yellow-50';
      return 'text-red-600 bg-red-50';
    }
    if (type === 'health') {
      if (value >= 0.9) return 'text-green-600 bg-green-50';
      if (value >= 0.7) return 'text-yellow-600 bg-yellow-50';
      return 'text-red-600 bg-red-50';
    }
    return 'text-gray-600 bg-gray-50';
  };

  if (loading) {
    return (
      <Card className="p-6">
        <div className="text-center">
          <p className="text-gray-500">Loading metrics...</p>
        </div>
      </Card>
    );
  }

  if (error) {
    return (
      <Card className="p-6">
        <div className="text-center">
          <div style={{fontSize: '2rem', marginBottom: '16px', color: 'var(--error)'}}>⚠️</div>
          <p style={{color: 'var(--error)', fontWeight: '600', marginBottom: '12px'}}>Metrics Not Available Yet</p>
          <p style={{color: 'var(--muted)', fontSize: '0.9rem', marginBottom: '16px'}}>{error}</p>
          <div style={{
            padding: '12px',
            background: 'var(--glass)',
            borderRadius: '6px',
            marginBottom: '16px',
            textAlign: 'left',
            fontSize: '0.85rem',
            color: 'var(--muted)'
          }}>
            <p><strong>Possible reasons:</strong></p>
            <ul style={{paddingLeft: '20px', marginTop: '8px'}}>
              <li>Prometheus metrics endpoint not configured on backend</li>
              <li>Insufficient permissions to access metrics</li>
              <li>Backend service not running</li>
            </ul>
          </div>
          <button
            onClick={fetchMetrics}
            className="mt-2 px-4 py-2 bg-blue-500 text-white rounded hover:bg-blue-600"
            style={{
              padding: '10px 20px',
              background: 'linear-gradient(135deg, #4a90e2 0%, #357abd 100%)',
              color: 'white',
              border: 'none',
              borderRadius: '6px',
              fontWeight: '600',
              cursor: 'pointer'
            }}
          >
            🔄 Retry
          </button>
        </div>
      </Card>
    );
  }

  return (
    <div className="prometheus-metrics">
      <Card className="p-6">
        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <div>
            <h2 className="text-2xl font-bold">System Metrics</h2>
            <p className="text-sm text-gray-500">Golden Signals - Prometheus</p>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={fetchMetrics}
              className="px-3 py-1 text-sm border rounded hover:bg-gray-50"
              title="Refresh"
            >
              🔄 Refresh
            </button>
            <button
              onClick={() => setAutoRefresh(!autoRefresh)}
              className={`px-3 py-1 text-sm border rounded ${
                autoRefresh ? 'bg-green-50 border-green-500' : 'hover:bg-gray-50'
              }`}
            >
              {autoRefresh ? '🟢 Auto' : '⏸️ Manual'}
            </button>
          </div>
        </div>

        {parsedMetrics && (
          <>
            {/* Golden Signals Overview */}
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
              {/* Latency */}
              <div className={`metric-card ${getStatusColor(parsedMetrics.latency.avg, 'latency')}`}>
                <h3 className="text-sm font-semibold mb-2">⚡ Latency</h3>
                <div className="text-2xl font-bold mb-1">
                  {parsedMetrics.latency.avg.toFixed(1)}ms
                </div>
                <div className="text-xs space-y-1">
                  <div>P95: {parsedMetrics.latency.p95.toFixed(1)}ms</div>
                  <div>P99: {parsedMetrics.latency.p99.toFixed(1)}ms</div>
                </div>
              </div>

              {/* Traffic */}
              <div className="metric-card bg-blue-50 text-blue-600">
                <h3 className="text-sm font-semibold mb-2">📊 Traffic</h3>
                <div className="text-2xl font-bold mb-1">
                  {parsedMetrics.traffic.requests_total}
                </div>
                <div className="text-xs">
                  Total Requests
                </div>
              </div>

              {/* Errors */}
              <div className={`metric-card ${getStatusColor(parsedMetrics.errors.error_rate, 'error_rate')}`}>
                <h3 className="text-sm font-semibold mb-2">❌ Errors</h3>
                <div className="text-2xl font-bold mb-1">
                  {parsedMetrics.errors.error_rate.toFixed(2)}%
                </div>
                <div className="text-xs">
                  {parsedMetrics.errors.errors_total} errors
                </div>
              </div>

              {/* Trading Performance */}
              <div className="metric-card bg-purple-50 text-purple-600">
                <h3 className="text-sm font-semibold mb-2">💰 Trading</h3>
                <div className="text-2xl font-bold mb-1">
                  ${parsedMetrics.trading.profit_total.toFixed(2)}
                </div>
                <div className="text-xs">
                  {parsedMetrics.trading.success_rate.toFixed(1)}% success rate
                </div>
              </div>
            </div>

            {/* Trading Details */}
            <div className="mb-6">
              <h3 className="text-lg font-semibold mb-3">Trading Statistics</h3>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <div className="stat-item">
                  <p className="text-sm text-gray-500">Total Trades</p>
                  <p className="text-xl font-bold">{parsedMetrics.trading.trades_total}</p>
                </div>
                <div className="stat-item">
                  <p className="text-sm text-gray-500">Successful Trades</p>
                  <p className="text-xl font-bold text-green-600">{parsedMetrics.trading.trades_success}</p>
                </div>
                <div className="stat-item">
                  <p className="text-sm text-gray-500">Failed Trades</p>
                  <p className="text-xl font-bold text-red-600">{parsedMetrics.trading.trades_failed}</p>
                </div>
              </div>
            </div>

            {/* Component Health */}
            {Object.keys(parsedMetrics.components).length > 0 && (
              <div className="mb-6">
                <h3 className="text-lg font-semibold mb-3">Component Health</h3>
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                  {Object.entries(parsedMetrics.components).map(([component, health]) => (
                    <div key={component} className={`component-card ${getStatusColor(health, 'health')}`}>
                      <div className="flex items-center justify-between">
                        <span className="font-medium capitalize">
                          {component.replace(/_/g, ' ')}
                        </span>
                        <Badge variant={health >= 0.9 ? 'default' : health >= 0.7 ? 'outline' : 'destructive'}>
                          {(health * 100).toFixed(0)}%
                        </Badge>
                      </div>
                      <div className="mt-2">
                        <div className="w-full h-2 bg-gray-200 rounded">
                          <div
                            className={`h-full rounded ${
                              health >= 0.9 ? 'bg-green-500' : 
                              health >= 0.7 ? 'bg-yellow-500' : 
                              'bg-red-500'
                            }`}
                            style={{ width: `${health * 100}%` }}
                          />
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

          </>
        )}
      </Card>
    </div>
  );
}
