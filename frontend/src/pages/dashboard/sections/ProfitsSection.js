import React, { useState, useEffect } from 'react';
import { Line } from 'react-chartjs-2';
import {
  Chart as ChartJS,
  CategoryScale, LinearScale, PointElement, LineElement,
  Title, Tooltip, Legend, Filler
} from 'chart.js';
import SectionHeader from '@/ui/components/SectionHeader';
import StatCard from '@/ui/components/StatCard';
import ErrorBoundary from '../../../components/ErrorBoundary';
import apiClient from '@/lib/apiClient';

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, Title, Tooltip, Legend, Filler);

const NOT_AVAILABLE = 'Not available';
const safeToFixed = (value, digits = 2, fallback = '0.00') => {
  const num = Number(value);
  return Number.isFinite(num) ? num.toFixed(digits) : fallback;
};
const safeNumber = (value, fallback = 0) => {
  const num = Number(value);
  return Number.isFinite(num) ? num : fallback;
};
const safePercent = (value, digits = 1, fallback = '0.0') => `${safeToFixed(value, digits, fallback)}%`;
const formatZAR = (value, digits = 2, fallback = NOT_AVAILABLE) => {
  const num = Number(value);
  if (!Number.isFinite(num)) return fallback;
  const formatted = Math.abs(num).toLocaleString('en-US', { minimumFractionDigits: digits, maximumFractionDigits: digits });
  return `${num < 0 ? '-R' : 'R'}${formatted}`;
};

// ─── Premium chart helpers ────────────────────────────────────────────────────
/**
 * Build a Chart.js gradient fill using the canvas context.
 * Returns a CanvasGradient when ctx is available, falls back to a static rgba string.
 */
function buildGradient(ctx, colorStopTop, colorStopBottom) {
  if (!ctx) return colorStopBottom;
  try {
    const gradient = ctx.createLinearGradient(0, 0, 0, ctx.canvas.height);
    gradient.addColorStop(0, colorStopTop);
    gradient.addColorStop(1, colorStopBottom);
    return gradient;
  } catch {
    return colorStopBottom;
  }
}

/** Shared premium Chart.js options factory — dark-mode, no flicker, polished */
function premiumChartOptions({
  accentColor = '#22c55e',
  tooltipLabel = null,
  yTickCallback = null,
  yMin = undefined,
  yMax = undefined,
  beginAtZero = true,
} = {}) {
  return {
    responsive: true,
    maintainAspectRatio: false,
    animation: { duration: 700, easing: 'easeInOutQuart' },
    interaction: { intersect: false, mode: 'index' },
    plugins: {
      legend: { display: false },
      tooltip: {
        enabled: true,
        backgroundColor: 'rgba(8, 10, 22, 0.97)',
        titleColor: accentColor,
        bodyColor: '#e2e8f0',
        borderColor: accentColor,
        borderWidth: 1,
        padding: { x: 14, y: 10 },
        cornerRadius: 10,
        titleFont: { size: 13, weight: '700', family: 'inherit' },
        bodyFont: { size: 12, family: 'inherit' },
        displayColors: false,
        callbacks: tooltipLabel ? { label: tooltipLabel } : undefined,
      },
    },
    scales: {
      y: {
        beginAtZero,
        min: yMin,
        max: yMax,
        ticks: {
          color: '#64748b',
          font: { size: 11, family: 'inherit' },
          padding: 10,
          maxTicksLimit: 6,
          callback: yTickCallback || ((v) => 'R' + safeToFixed(v, 0, '0')),
        },
        grid: {
          color: 'rgba(148, 163, 184, 0.07)',
          lineWidth: 1,
          drawBorder: false,
        },
        border: { display: false, dash: [3, 3] },
      },
      x: {
        ticks: {
          color: '#64748b',
          font: { size: 10, family: 'inherit' },
          padding: 4,
          maxRotation: 30,
          minRotation: 0,
        },
        grid: { display: false },
        border: { display: false },
      },
    },
  };
}
// ─────────────────────────────────────────────────────────────────────────────

const ProfitsSection = ({
  drawdownData,
  drawdownRange,
  equityData,
  equityRange,
  formatDate,
  graphPeriod,
  overviewData,
  profitData,
  profitsTab,
  setDrawdownRange,
  setEquityRange,
  setGraphPeriod,
  setProfitsTab,
  setWinRatePeriod,
  showSection,
  winRateData,
  winRatePeriod,
  getAlertColor,
}) => {
  const [systemMetrics, setSystemMetrics] = useState(null);
  const [systemMetricsLoading, setSystemMetricsLoading] = useState(false);

  // Fetch system metrics when the metrics tab is active
  useEffect(() => {
    if (profitsTab !== 'metrics') return;
    let cancelled = false;
    const fetchMetrics = async () => {
      setSystemMetricsLoading(true);
      try {
        const res = await apiClient.get('/metrics/system');
        if (!cancelled) setSystemMetrics(res.data);
      } catch (e) {
        console.error('System metrics fetch error:', e);
      } finally {
        if (!cancelled) setSystemMetricsLoading(false);
      }
    };
    fetchMetrics();
    const interval = setInterval(fetchMetrics, 60000); // refresh every 60 s
    return () => { cancelled = true; clearInterval(interval); };
  }, [profitsTab]);

  const maxDrawdown = drawdownData?.max_drawdown_pct ?? drawdownData?.max_drawdown;
  const feesValue = profitData?.fees ?? profitData?.total_fees ?? null;

  // Profit history chart — segment coloring (green up / red down)
  const chartData = {
    labels: profitData?.labels || ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'],
    datasets: [{
      label: 'Profit (ZAR)',
      data: profitData?.values || [0, 0, 0, 0, 0, 0, 0],
      borderColor: '#22c55e',
      backgroundColor: (ctx) => {
        const c = ctx.chart.ctx;
        return buildGradient(c, 'rgba(34, 197, 94, 0.22)', 'rgba(34, 197, 94, 0.01)');
      },
      fill: true,
      tension: 0.45,
      pointRadius: 3,
      pointHoverRadius: 7,
      pointBackgroundColor: '#22c55e',
      pointBorderColor: '#0a0c16',
      pointBorderWidth: 2,
      borderWidth: 2,
      segment: {
        borderColor: ctx => ctx.p0.parsed.y > ctx.p1.parsed.y ? '#ef4444' : '#22c55e',
      },
    }],
  };

  const chartOptions = premiumChartOptions({
    accentColor: '#22c55e',
    tooltipLabel: ctx => `Profit: R${safeToFixed(ctx.parsed.y, 2)}`,
  });

  return (
    <section className="section active">
      <div className="card">
        <SectionHeader
          title="💹 Profits & Performance"
          subtitle="Track equity, drawdown, and performance metrics across bots."
        />
        
        {/* Horizontal Sub-tabs */}
        <div className="profit-tabs">
          <button
            onClick={() => setProfitsTab('metrics')}
            className={`profit-tab ${profitsTab === 'metrics' ? 'active' : ''}`}
          >
            📊 Metrics
          </button>
          <button
            onClick={() => setProfitsTab('profit-history')}
            className={`profit-tab ${profitsTab === 'profit-history' ? 'active' : ''}`}
          >
            💰 Profit History
          </button>
          <button
            onClick={() => setProfitsTab('equity')}
            className={`profit-tab ${profitsTab === 'equity' ? 'active' : ''}`}
          >
            📈 Equity/PnL
          </button>
          <button
            onClick={() => setProfitsTab('drawdown')}
            className={`profit-tab ${profitsTab === 'drawdown' ? 'active' : ''}`}
          >
            📉 Drawdown
          </button>
          <button
            onClick={() => setProfitsTab('win-rate')}
            className={`profit-tab ${profitsTab === 'win-rate' ? 'active' : ''}`}
          >
            🎯 Win Rate
          </button>
        </div>
        
        {/* Tab Content */}
        {profitsTab === 'metrics' && (
          <div style={{marginTop: '20px'}}>
            <ErrorBoundary title="Metrics Error" message="Unable to load metrics data.">
              {systemMetricsLoading && !systemMetrics ? (
                <div style={{color: 'var(--muted)', padding: '20px 0'}}>Loading system metrics…</div>
              ) : (
                <div>
                  {/* Trading Performance */}
                  <h3 style={{fontSize: '1.1rem', fontWeight: 700, color: 'var(--text)', marginBottom: '12px'}}>
                    📊 Trading Performance
                  </h3>
                  <div style={{display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: '12px', marginBottom: '24px'}}>
                    {[
                      {
                        label: 'Net Profit / Loss',
                        help: 'Total realised profit after fees (ZAR)',
                        value: systemMetrics?.trading?.net_pnl != null
                          ? formatZAR(systemMetrics.trading.net_pnl)
                          : NOT_AVAILABLE,
                        color: systemMetrics?.trading?.net_pnl >= 0 ? 'var(--success)' : 'var(--error)',
                      },
                      {
                        label: 'Win Rate',
                        help: 'Percentage of closed trades that were profitable',
                        value: systemMetrics?.trading?.win_rate != null
                          ? `${systemMetrics.trading.win_rate}%`
                          : NOT_AVAILABLE,
                        color: 'var(--accent2)',
                      },
                      {
                        label: 'Total Trades',
                        help: 'Number of completed closed trades',
                        value: systemMetrics?.trading?.trade_count != null
                          ? String(systemMetrics.trading.trade_count)
                          : NOT_AVAILABLE,
                        color: 'var(--text)',
                      },
                      {
                        label: 'Max Drawdown',
                        help: 'Worst peak-to-trough loss — lower is better',
                        value: systemMetrics?.trading?.max_drawdown_pct != null
                          ? `${systemMetrics.trading.max_drawdown_pct}%`
                          : NOT_AVAILABLE,
                        color: 'var(--warning)',
                      },
                    ].map(({label, help, value, color}) => (
                      <div key={label} style={{
                        padding: '14px',
                        background: 'var(--panel)',
                        borderRadius: '8px',
                        border: '1px solid var(--line)',
                      }}>
                        <div style={{fontSize: '0.75rem', color: 'var(--muted)', marginBottom: '4px'}}>{label}</div>
                        <div style={{fontSize: '1.25rem', fontWeight: 700, color}}>{value}</div>
                        <div style={{fontSize: '0.72rem', color: 'var(--muted)', marginTop: '4px'}}>{help}</div>
                      </div>
                    ))}
                  </div>
                  {systemMetrics?.trading?.last_trade_at && (
                    <div style={{fontSize: '0.8rem', color: 'var(--muted)', marginBottom: '20px'}}>
                      Last trade: {new Date(systemMetrics.trading.last_trade_at).toLocaleString()}
                    </div>
                  )}

                  {/* Market Intelligence */}
                  <h3 style={{fontSize: '1.1rem', fontWeight: 700, color: 'var(--text)', marginBottom: '12px', display: 'flex', alignItems: 'center', gap: '8px'}}>
                    🌐 Market Intelligence
                    <span style={{fontSize: '0.75rem', fontWeight: 400, color: 'var(--muted)'}}>
                      Source: {systemMetrics?.market_intelligence?.source || 'CoinStats'}
                    </span>
                  </h3>
                  {systemMetrics?.market_intelligence ? (
                    <div style={{
                      padding: '16px',
                      background: 'var(--panel)',
                      borderRadius: '8px',
                      border: '1px solid var(--line)',
                    }}>
                      <div style={{display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '12px'}}>
                        <span style={{
                          fontSize: '1rem',
                          fontWeight: 700,
                          color: systemMetrics.market_intelligence.mood === 'positive' ? 'var(--success)' :
                                 systemMetrics.market_intelligence.mood === 'negative' ? 'var(--error)' : 'var(--warning)',
                        }}>
                          {systemMetrics.market_intelligence.mood === 'positive' ? '📈' :
                           systemMetrics.market_intelligence.mood === 'negative' ? '📉' : '➡️'}{' '}
                          Mood: {systemMetrics.market_intelligence.mood}
                        </span>
                        {systemMetrics.market_intelligence.top_risk !== 'none' && (
                          <span style={{fontSize: '0.82rem', color: 'var(--warning)'}}>
                            ⚠️ {systemMetrics.market_intelligence.top_risk}
                          </span>
                        )}
                      </div>
                      <div style={{fontSize: '0.9rem', color: 'var(--text)', marginBottom: '8px'}}>
                        {systemMetrics.market_intelligence.brief}
                      </div>
                      {systemMetrics.market_intelligence.last_updated && (
                        <div style={{fontSize: '0.75rem', color: 'var(--muted)'}}>
                          Updated: {new Date(systemMetrics.market_intelligence.last_updated).toLocaleString()} · Source: CoinStats
                        </div>
                      )}
                    </div>
                  ) : (
                    <div style={{color: 'var(--muted)', fontSize: '0.9rem'}}>
                      News and market signals are served by CoinStats. Waiting for first fetch…
                    </div>
                  )}
                </div>
              )}
            </ErrorBoundary>
          </div>
        )}
        
        {profitsTab === 'profit-history' && (
          <div style={{marginTop: '20px'}}>
            {/* Header with period selector */}
            <div style={{display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px', flexWrap: 'wrap', gap: '12px'}}>
              <h3 style={{margin: 0, fontSize: '1.2rem', display: 'flex', alignItems: 'center', gap: '8px'}}>
                📊 Performance Analytics
              </h3>
              <div style={{display: 'flex', gap: '6px'}}>
                {['daily', 'weekly', 'monthly'].map(period => (
                  <button 
                    key={period}
                    onClick={() => setGraphPeriod(period)}
                    style={{
                      padding: '6px 14px',
                      background: graphPeriod === period ? 'linear-gradient(135deg, var(--success) 0%, var(--success) 100%)' : 'var(--glass)',
                      color: graphPeriod === period ? '#ffffff' : 'var(--muted)',
                      border: graphPeriod === period ? 'none' : '1px solid var(--line)',
                      borderRadius: '6px',
                      cursor: 'pointer',
                      fontWeight: 600,
                      fontSize: '0.85rem',
                      textTransform: 'capitalize',
                      transition: 'all 0.3s'
                    }}
                  >
                    {period}
                  </button>
                ))}
              </div>
            </div>
            
            {/* Stats Cards Row */}
            <div style={{display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: '12px', marginBottom: '16px'}}>
              <div style={{
                padding: '16px',
                background: 'linear-gradient(135deg, rgba(16, 185, 129, 0.1) 0%, rgba(5, 150, 105, 0.05) 100%)',
                borderRadius: '10px',
                border: '1px solid rgba(16, 185, 129, 0.3)',
                textAlign: 'center'
              }}>
                <div style={{fontSize: '0.75rem', color: 'var(--success)', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.5px'}}>Total Profit</div>
                <div style={{fontSize: '1.75rem', fontWeight: 700, color: 'var(--success)', marginTop: '6px', display: 'flex', alignItems: 'baseline', justifyContent: 'center', gap: '4px'}}>
                  R{safeToFixed(profitData?.total, 2)}
                  <span style={{fontSize: '0.75rem', color: 'var(--muted)'}}>ZAR</span>
                </div>
              </div>
              
              <div style={{
                padding: '16px',
                background: 'linear-gradient(135deg, rgba(59, 130, 246, 0.1) 0%, rgba(37, 99, 235, 0.05) 100%)',
                borderRadius: '10px',
                border: '1px solid rgba(59, 130, 246, 0.3)',
                textAlign: 'center'
              }}>
                <div style={{fontSize: '0.75rem', color: 'var(--accent2)', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.5px'}}>Avg Daily</div>
                <div style={{fontSize: '1.75rem', fontWeight: 700, color: 'var(--accent2)', marginTop: '6px', display: 'flex', alignItems: 'baseline', justifyContent: 'center', gap: '4px'}}>
                  R{safeToFixed(profitData?.avg_daily, 2)}
                  <span style={{fontSize: '0.75rem', color: 'var(--muted)'}}>{profitData?.avg_daily ? '+12%' : ''}</span>
                </div>
              </div>
              
              <div style={{
                padding: '16px',
                background: 'linear-gradient(135deg, rgba(245, 158, 11, 0.1) 0%, rgba(217, 119, 6, 0.05) 100%)',
                borderRadius: '10px',
                border: '1px solid rgba(245, 158, 11, 0.3)',
                textAlign: 'center'
              }}>
                <div style={{fontSize: '0.75rem', color: 'var(--accent2)', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.5px'}}>Best Day</div>
                <div style={{fontSize: '1.75rem', fontWeight: 700, color: 'var(--accent2)', marginTop: '6px', display: 'flex', alignItems: 'baseline', justifyContent: 'center', gap: '4px'}}>
                  R{Number.isFinite(Number(profitData?.best_day))
                    ? safeToFixed(profitData.best_day, 2).replace(/\B(?=(\d{3})+(?!\d))/g, ',')
                    : '0.00'}
                </div>
              </div>
              
              <div style={{
                padding: '16px',
                background: 'linear-gradient(135deg, rgba(168, 85, 247, 0.1) 0%, rgba(147, 51, 234, 0.05) 100%)',
                borderRadius: '10px',
                border: '1px solid rgba(168, 85, 247, 0.3)',
                textAlign: 'center'
              }}>
                <div style={{fontSize: '0.75rem', color: 'var(--accent2)', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.5px'}}>Growth Rate</div>
                <div style={{fontSize: '1.75rem', fontWeight: 700, color: 'var(--accent2)', marginTop: '6px', display: 'flex', alignItems: 'baseline', justifyContent: 'center', gap: '4px'}}>
                  {safeToFixed(profitData?.growth_rate, 2)}%
                  <span style={{fontSize: '0.75rem', color: 'var(--muted)'}}>{profitData?.growth_rate > 0 ? '↑' : ''}</span>
                </div>
              </div>
            </div>
            
            {/* Chart */}
            <div style={{
              minHeight: '350px', 
              height: '350px',
              padding: '20px',
              background: 'linear-gradient(160deg, rgba(5, 12, 30, 0.7) 0%, rgba(2, 6, 18, 0.85) 100%)',
              borderRadius: '12px',
              border: '1px solid rgba(34, 197, 94, 0.15)',
              boxShadow: '0 8px 24px rgba(0,0,0,0.25)',
              display: 'flex',
              flexDirection: 'column'
            }}>
              {typeof window !== 'undefined' && (
                <ErrorBoundary title="Chart Error" message="Unable to render chart.">
                  <Line data={chartData} options={chartOptions} />
                </ErrorBoundary>
              )}
            </div>
          </div>
        )}
        
        {profitsTab === 'equity' && (
          <div style={{marginTop: '20px'}}>
            {/* Header with range selector */}
            <div style={{display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px', flexWrap: 'wrap', gap: '12px'}}>
              <h3 style={{margin: 0, fontSize: '1.2rem', display: 'flex', alignItems: 'center', gap: '8px'}}>
                📈 Equity & P/L Tracking
              </h3>
              <div style={{display: 'flex', gap: '6px'}}>
                {['1d', '7d', '30d', '90d'].map(range => (
                  <button 
                    key={range}
                    onClick={() => setEquityRange(range)}
                    style={{
                      padding: '6px 14px',
                      background: equityRange === range ? 'linear-gradient(135deg, var(--success) 0%, var(--success) 100%)' : 'var(--glass)',
                      color: equityRange === range ? '#ffffff' : 'var(--muted)',
                      border: equityRange === range ? 'none' : '1px solid var(--line)',
                      borderRadius: '6px',
                      cursor: 'pointer',
                      fontWeight: 600,
                      fontSize: '0.85rem',
                      textTransform: 'uppercase',
                      transition: 'all 0.3s'
                    }}
                  >
                    {range}
                  </button>
                ))}
              </div>
            </div>
            
            {equityData ? (
              <>
                {/* Stats Cards Row */}
                <div style={{display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: '12px', marginBottom: '16px'}}>
                  <div style={{
                    padding: '16px',
                    background: 'linear-gradient(135deg, rgba(16, 185, 129, 0.1) 0%, rgba(5, 150, 105, 0.05) 100%)',
                    borderRadius: '10px',
                    border: '1px solid rgba(16, 185, 129, 0.3)',
                    textAlign: 'center'
                  }}>
                    <div style={{fontSize: '0.75rem', color: 'var(--success)', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.5px'}}>Current Equity</div>
                    <div style={{fontSize: '1.75rem', fontWeight: 700, color: 'var(--success)', marginTop: '6px', display: 'flex', alignItems: 'baseline', justifyContent: 'center', gap: '4px'}}>
                      R{safeToFixed(equityData.current_equity, 2)}
                      <span style={{fontSize: '0.75rem', color: 'var(--muted)'}}>ZAR</span>
                    </div>
                  </div>
                  
                  <div style={{
                    padding: '16px',
                    background: 'linear-gradient(135deg, rgba(59, 130, 246, 0.1) 0%, rgba(37, 99, 235, 0.05) 100%)',
                    borderRadius: '10px',
                    border: '1px solid rgba(59, 130, 246, 0.3)',
                    textAlign: 'center'
                  }}>
                    <div style={{fontSize: '0.75rem', color: 'var(--accent2)', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.5px'}}>Total P&L</div>
                    <div style={{fontSize: '1.75rem', fontWeight: 700, color: safeNumber(equityData.total_pnl, 0) >= 0 ? 'var(--success)' : '#ef4444', marginTop: '6px', display: 'flex', alignItems: 'baseline', justifyContent: 'center', gap: '4px'}}>
                      R{safeToFixed(equityData.total_pnl, 2)}
                    </div>
                  </div>
                  
                  <div style={{
                    padding: '16px',
                    background: 'linear-gradient(135deg, rgba(245, 158, 11, 0.1) 0%, rgba(217, 119, 6, 0.05) 100%)',
                    borderRadius: '10px',
                    border: '1px solid rgba(245, 158, 11, 0.3)',
                    textAlign: 'center'
                  }}>
                    <div style={{fontSize: '0.75rem', color: 'var(--accent2)', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.5px'}}>Realized P&L</div>
                    <div style={{fontSize: '1.75rem', fontWeight: 700, color: 'var(--accent2)', marginTop: '6px', display: 'flex', alignItems: 'baseline', justifyContent: 'center', gap: '4px'}}>
                      R{safeToFixed(equityData.total_pnl, 2)}
                    </div>
                  </div>
                  
                  <div style={{
                    padding: '16px',
                    background: 'linear-gradient(135deg, rgba(239, 68, 68, 0.1) 0%, rgba(220, 38, 38, 0.05) 100%)',
                    borderRadius: '10px',
                    border: '1px solid rgba(239, 68, 68, 0.3)',
                    textAlign: 'center'
                  }}>
                    <div style={{fontSize: '0.75rem', color: '#ef4444', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.5px'}}>Total Fees</div>
                    <div style={{fontSize: '1.75rem', fontWeight: 700, color: '#ef4444', marginTop: '6px', display: 'flex', alignItems: 'baseline', justifyContent: 'center', gap: '4px'}}>
                      R{safeToFixed(equityData.total_fees, 2)}
                    </div>
                  </div>
                </div>
                
                {/* Equity Curve Chart */}
                <div style={{
                  minHeight: '350px', 
                  height: '350px',
                  padding: '20px',
                  background: 'linear-gradient(160deg, rgba(5, 12, 30, 0.7) 0%, rgba(2, 6, 18, 0.85) 100%)',
                  borderRadius: '12px',
                  border: '1px solid rgba(16, 185, 129, 0.18)',
                  boxShadow: '0 8px 24px rgba(0,0,0,0.25)',
                  display: 'flex',
                  flexDirection: 'column'
                }}>
                  {typeof window !== 'undefined' && equityData.equity_curve && equityData.equity_curve.length > 0 && (
                    <Line 
                      data={{
                        labels: equityData.equity_curve.map(p => new Date(p.timestamp).toLocaleDateString('en-ZA', {month: 'short', day: 'numeric'})),
                        datasets: [{
                          label: 'Equity (ZAR)',
                          data: equityData.equity_curve.map(p => p.equity),
                          borderColor: '#10b981',
                          backgroundColor: (ctx) => buildGradient(ctx.chart.ctx, 'rgba(16,185,129,0.25)', 'rgba(16,185,129,0.02)'),
                          fill: true,
                          tension: 0.45,
                          pointRadius: 2,
                          pointHoverRadius: 6,
                          pointBackgroundColor: '#10b981',
                          pointBorderColor: '#0a0c16',
                          pointBorderWidth: 2,
                          borderWidth: 2,
                        }]
                      }}
                      options={premiumChartOptions({
                        accentColor: '#10b981',
                        beginAtZero: false,
                        tooltipLabel: ctx => `Equity: R${safeToFixed(ctx.parsed.y, 2)}`,
                      })}
                    />
                  )}
                </div>
              </>
            ) : (
              <div style={{padding: '40px', textAlign: 'center', background: 'var(--panel)', borderRadius: '6px', border: '1px solid var(--line)'}}>
                <p style={{color: 'var(--muted)', fontSize: '1.1rem'}}>
                  📊 No trade data available yet
                </p>
                <p style={{color: 'var(--muted)', fontSize: '0.9rem', marginTop: '10px'}}>
                  Start trading to see your equity curve
                </p>
              </div>
            )}
          </div>
        )}
        
        {profitsTab === 'drawdown' && (
          <div style={{marginTop: '20px'}}>
            {/* Header with range selector */}
            <div style={{display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px', flexWrap: 'wrap', gap: '12px'}}>
              <h3 style={{margin: 0, fontSize: '1.2rem', display: 'flex', alignItems: 'center', gap: '8px'}}>
                📉 Drawdown Analysis
              </h3>
              <div style={{display: 'flex', gap: '6px'}}>
                {['1d', '7d', '30d', '90d'].map(range => (
                  <button 
                    key={range}
                    onClick={() => setDrawdownRange(range)}
                    style={{
                      padding: '6px 14px',
                      background: drawdownRange === range ? 'linear-gradient(135deg, #ef4444 0%, #dc2626 100%)' : 'var(--glass)',
                      color: drawdownRange === range ? '#ffffff' : 'var(--muted)',
                      border: drawdownRange === range ? 'none' : '1px solid var(--line)',
                      borderRadius: '6px',
                      cursor: 'pointer',
                      fontWeight: 600,
                      fontSize: '0.85rem',
                      textTransform: 'uppercase',
                      transition: 'all 0.3s'
                    }}
                  >
                    {range}
                  </button>
                ))}
              </div>
            </div>
            
            {drawdownData ? (
              <>
                {/* Stats Cards Row */}
                <div style={{display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: '12px', marginBottom: '16px'}}>
                  <div style={{
                    padding: '16px',
                    background: 'linear-gradient(135deg, rgba(239, 68, 68, 0.1) 0%, rgba(220, 38, 38, 0.05) 100%)',
                    borderRadius: '10px',
                    border: '1px solid rgba(239, 68, 68, 0.3)',
                    textAlign: 'center'
                  }}>
                    <div style={{fontSize: '0.75rem', color: '#ef4444', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.5px'}}>Max Drawdown</div>
                    <div style={{fontSize: '1.75rem', fontWeight: 700, color: '#ef4444', marginTop: '6px', display: 'flex', alignItems: 'baseline', justifyContent: 'center', gap: '4px'}}>
                      {safeToFixed(drawdownData.max_drawdown_pct, 2)}%
                      <span style={{fontSize: '0.75rem', color: 'var(--muted)'}}>↓</span>
                    </div>
                  </div>
                  
                  <div style={{
                    padding: '16px',
                    background: 'linear-gradient(135deg, rgba(245, 158, 11, 0.1) 0%, rgba(217, 119, 6, 0.05) 100%)',
                    borderRadius: '10px',
                    border: '1px solid rgba(245, 158, 11, 0.3)',
                    textAlign: 'center'
                  }}>
                    <div style={{fontSize: '0.75rem', color: 'var(--accent2)', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.5px'}}>Current Drawdown</div>
                    <div style={{fontSize: '1.75rem', fontWeight: 700, color: 'var(--accent2)', marginTop: '6px', display: 'flex', alignItems: 'baseline', justifyContent: 'center', gap: '4px'}}>
                      {safeToFixed(drawdownData.current_drawdown_pct, 2)}%
                    </div>
                  </div>
                  
                  <div style={{
                    padding: '16px',
                    background: 'linear-gradient(135deg, rgba(16, 185, 129, 0.1) 0%, rgba(5, 150, 105, 0.05) 100%)',
                    borderRadius: '10px',
                    border: '1px solid rgba(16, 185, 129, 0.3)',
                    textAlign: 'center'
                  }}>
                    <div style={{fontSize: '0.75rem', color: 'var(--success)', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.5px'}}>Peak Equity</div>
                    <div style={{fontSize: '1.75rem', fontWeight: 700, color: 'var(--success)', marginTop: '6px', display: 'flex', alignItems: 'baseline', justifyContent: 'center', gap: '4px'}}>
                      R{safeToFixed(drawdownData.peak_equity, 2)}
                    </div>
                  </div>
                  
                  <div style={{
                    padding: '16px',
                    background: 'linear-gradient(135deg, rgba(59, 130, 246, 0.1) 0%, rgba(37, 99, 235, 0.05) 100%)',
                    borderRadius: '10px',
                    border: '1px solid rgba(59, 130, 246, 0.3)',
                    textAlign: 'center'
                  }}>
                    <div style={{fontSize: '0.75rem', color: 'var(--accent2)', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.5px'}}>Underwater Periods</div>
                    <div style={{fontSize: '1.75rem', fontWeight: 700, color: 'var(--accent2)', marginTop: '6px', display: 'flex', alignItems: 'baseline', justifyContent: 'center', gap: '4px'}}>
                      {drawdownData.underwater_periods || 0}
                    </div>
                  </div>
                </div>
                
                {/* Drawdown Curve Chart */}
                <div style={{
                  minHeight: '350px', 
                  height: '350px',
                  padding: '20px',
                  background: 'linear-gradient(160deg, rgba(30, 5, 8, 0.7) 0%, rgba(18, 2, 4, 0.85) 100%)',
                  borderRadius: '12px',
                  border: '1px solid rgba(239, 68, 68, 0.18)',
                  boxShadow: '0 8px 24px rgba(0,0,0,0.25)',
                  display: 'flex',
                  flexDirection: 'column'
                }}>
                  {typeof window !== 'undefined' && drawdownData.drawdown_curve && drawdownData.drawdown_curve.length > 0 ? (
                    <Line 
                      data={{
                        labels: drawdownData.drawdown_curve.map(p => new Date(p.timestamp).toLocaleDateString('en-ZA', {month: 'short', day: 'numeric'})),
                        datasets: [{
                          label: 'Drawdown %',
                          data: drawdownData.drawdown_curve.map(p => -p.drawdown_pct),
                          borderColor: '#ef4444',
                          backgroundColor: (ctx) => buildGradient(ctx.chart.ctx, 'rgba(239,68,68,0.22)', 'rgba(239,68,68,0.02)'),
                          fill: true,
                          tension: 0.45,
                          pointRadius: 2,
                          pointHoverRadius: 6,
                          pointBackgroundColor: '#ef4444',
                          pointBorderColor: '#0a0c16',
                          pointBorderWidth: 2,
                          borderWidth: 2,
                        }]
                      }}
                      options={premiumChartOptions({
                        accentColor: '#ef4444',
                        beginAtZero: false,
                        yMax: 0,
                        yTickCallback: v => safeToFixed(Math.abs(v), 1, '0.0') + '%',
                        tooltipLabel: ctx => `Drawdown: ${safeToFixed(Math.abs(ctx.parsed.y), 2)}%`,
                      })}
                    />
                  ) : (
                    <div style={{display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', color: 'var(--muted)'}}>
                      No drawdown data available
                    </div>
                  )}
                </div>
              </>
            ) : (
              <div style={{padding: '40px', textAlign: 'center', background: 'var(--panel)', borderRadius: '6px', border: '1px solid var(--line)'}}>
                <p style={{color: 'var(--muted)', fontSize: '1.1rem'}}>
                  📊 No trade data available yet
                </p>
                <p style={{color: 'var(--muted)', fontSize: '0.9rem', marginTop: '10px'}}>
                  Start trading to see drawdown analysis
                </p>
              </div>
            )}
          </div>
        )}
        
        {profitsTab === 'win-rate' && (
          <div style={{marginTop: '20px'}}>
            {/* Header with period selector */}
            <div style={{display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '20px', flexWrap: 'wrap', gap: '12px'}}>
              <h3 style={{margin: 0, fontSize: '1.2rem', display: 'flex', alignItems: 'center', gap: '8px'}}>
                🎯 Win Rate & Trade Statistics
              </h3>
              <div style={{display: 'flex', gap: '6px'}}>
                {['today', '7d', '30d', 'all'].map(period => (
                  <button 
                    key={period}
                    onClick={() => setWinRatePeriod(period)}
                    style={{
                      padding: '6px 14px',
                      background: winRatePeriod === period ? 'linear-gradient(135deg, var(--accent2) 0%, var(--accent2) 100%)' : 'var(--glass)',
                      color: winRatePeriod === period ? '#ffffff' : 'var(--muted)',
                      border: winRatePeriod === period ? 'none' : '1px solid var(--line)',
                      borderRadius: '6px',
                      cursor: 'pointer',
                      fontWeight: 600,
                      fontSize: '0.85rem',
                      textTransform: 'capitalize',
                      transition: 'all 0.3s'
                    }}
                  >
                    {period}
                  </button>
                ))}
              </div>
            </div>
            
            {winRateData && winRateData.total_trades > 0 ? (
              <>
                {/* Stats Cards Grid */}
                <div style={{display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: '12px', marginBottom: '16px'}}>
                  <div style={{
                    padding: '16px',
                    background: 'linear-gradient(135deg, rgba(139, 92, 246, 0.1) 0%, rgba(124, 58, 237, 0.05) 100%)',
                    borderRadius: '10px',
                    border: '1px solid rgba(139, 92, 246, 0.3)',
                    textAlign: 'center'
                  }}>
                    <div style={{fontSize: '0.75rem', color: 'var(--accent2)', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.5px'}}>Win Rate</div>
                    <div style={{fontSize: '1.75rem', fontWeight: 700, color: 'var(--accent2)', marginTop: '6px', display: 'flex', alignItems: 'baseline', justifyContent: 'center', gap: '4px'}}>
                      {safeToFixed(winRateData.win_rate_pct, 1, '0.0')}%
                      <span style={{fontSize: '0.75rem', color: 'var(--muted)'}}>({winRateData.winning_trades}/{winRateData.total_trades})</span>
                    </div>
                  </div>
                  
                  <div style={{
                    padding: '16px',
                    background: 'linear-gradient(135deg, rgba(16, 185, 129, 0.1) 0%, rgba(5, 150, 105, 0.05) 100%)',
                    borderRadius: '10px',
                    border: '1px solid rgba(16, 185, 129, 0.3)',
                    textAlign: 'center'
                  }}>
                    <div style={{fontSize: '0.75rem', color: 'var(--success)', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.5px'}}>Avg Win</div>
                    <div style={{fontSize: '1.75rem', fontWeight: 700, color: 'var(--success)', marginTop: '6px', display: 'flex', alignItems: 'baseline', justifyContent: 'center', gap: '4px'}}>
                      R{safeToFixed(winRateData.avg_win, 2)}
                    </div>
                  </div>
                  
                  <div style={{
                    padding: '16px',
                    background: 'linear-gradient(135deg, rgba(239, 68, 68, 0.1) 0%, rgba(220, 38, 38, 0.05) 100%)',
                    borderRadius: '10px',
                    border: '1px solid rgba(239, 68, 68, 0.3)',
                    textAlign: 'center'
                  }}>
                    <div style={{fontSize: '0.75rem', color: '#ef4444', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.5px'}}>Avg Loss</div>
                    <div style={{fontSize: '1.75rem', fontWeight: 700, color: '#ef4444', marginTop: '6px', display: 'flex', alignItems: 'baseline', justifyContent: 'center', gap: '4px'}}>
                      R{safeToFixed(winRateData.avg_loss, 2)}
                    </div>
                  </div>
                  
                  <div style={{
                    padding: '16px',
                    background: 'linear-gradient(135deg, rgba(245, 158, 11, 0.1) 0%, rgba(217, 119, 6, 0.05) 100%)',
                    borderRadius: '10px',
                    border: '1px solid rgba(245, 158, 11, 0.3)',
                    textAlign: 'center'
                  }}>
                    <div style={{fontSize: '0.75rem', color: 'var(--accent2)', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.5px'}}>Profit Factor</div>
                    <div style={{fontSize: '1.75rem', fontWeight: 700, color: 'var(--accent2)', marginTop: '6px', display: 'flex', alignItems: 'baseline', justifyContent: 'center', gap: '4px'}}>
                      {safeToFixed(winRateData.profit_factor, 2)}
                    </div>
                  </div>
                </div>
                
                {/* Second Row */}
                <div style={{display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: '12px', marginBottom: '16px'}}>
                  <div style={{
                    padding: '16px',
                    background: 'linear-gradient(135deg, rgba(59, 130, 246, 0.1) 0%, rgba(37, 99, 235, 0.05) 100%)',
                    borderRadius: '10px',
                    border: '1px solid rgba(59, 130, 246, 0.3)',
                    textAlign: 'center'
                  }}>
                    <div style={{fontSize: '0.75rem', color: 'var(--accent2)', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.5px'}}>Total Trades</div>
                    <div style={{fontSize: '1.75rem', fontWeight: 700, color: 'var(--accent2)', marginTop: '6px', display: 'flex', alignItems: 'baseline', justifyContent: 'center', gap: '4px'}}>
                      {winRateData.total_trades || 0}
                    </div>
                  </div>
                  
                  <div style={{
                    padding: '16px',
                    background: 'linear-gradient(135deg, rgba(34, 197, 94, 0.1) 0%, rgba(22, 163, 74, 0.05) 100%)',
                    borderRadius: '10px',
                    border: '1px solid rgba(34, 197, 94, 0.3)',
                    textAlign: 'center'
                  }}>
                    <div style={{fontSize: '0.75rem', color: 'var(--success)', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.5px'}}>Best Trade</div>
                    <div style={{fontSize: '1.75rem', fontWeight: 700, color: 'var(--success)', marginTop: '6px', display: 'flex', alignItems: 'baseline', justifyContent: 'center', gap: '4px'}}>
                      R{safeToFixed(winRateData.best_trade, 2)}
                    </div>
                  </div>
                  
                  <div style={{
                    padding: '16px',
                    background: 'linear-gradient(135deg, rgba(220, 38, 38, 0.1) 0%, rgba(185, 28, 28, 0.05) 100%)',
                    borderRadius: '10px',
                    border: '1px solid rgba(220, 38, 38, 0.3)',
                    textAlign: 'center'
                  }}>
                    <div style={{fontSize: '0.75rem', color: '#dc2626', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.5px'}}>Worst Trade</div>
                    <div style={{fontSize: '1.75rem', fontWeight: 700, color: '#dc2626', marginTop: '6px', display: 'flex', alignItems: 'baseline', justifyContent: 'center', gap: '4px'}}>
                      R{safeToFixed(winRateData.worst_trade, 2)}
                    </div>
                  </div>
                  
                  <div style={{
                    padding: '16px',
                    background: 'linear-gradient(135deg, rgba(168, 85, 247, 0.1) 0%, rgba(147, 51, 234, 0.05) 100%)',
                    borderRadius: '10px',
                    border: '1px solid rgba(168, 85, 247, 0.3)',
                    textAlign: 'center'
                  }}>
                    <div style={{fontSize: '0.75rem', color: 'var(--accent2)', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.5px'}}>Total P&L</div>
                    <div style={{fontSize: '1.75rem', fontWeight: 700, color: winRateData.total_pnl >= 0 ? 'var(--success)' : '#ef4444', marginTop: '6px', display: 'flex', alignItems: 'baseline', justifyContent: 'center', gap: '4px'}}>
                      R{safeToFixed(winRateData.total_pnl, 2)}
                    </div>
                  </div>
                </div>
                
                {/* Win/Loss Breakdown */}
                <div style={{
                  padding: '20px',
                  background: 'linear-gradient(160deg, rgba(10, 5, 30, 0.7) 0%, rgba(5, 2, 18, 0.85) 100%)',
                  borderRadius: '12px',
                  border: '1px solid rgba(139, 92, 246, 0.18)',
                  boxShadow: '0 8px 24px rgba(0,0,0,0.25)',
                }}>
                  <h4 style={{margin: '0 0 16px 0', fontSize: '1rem', color: 'var(--text)'}}>Trade Distribution</h4>
                  <div style={{display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '20px'}}>
                    <div>
                      <div style={{fontSize: '0.9rem', color: 'var(--muted)', marginBottom: '8px'}}>Winning Trades</div>
                      <div style={{fontSize: '1.5rem', fontWeight: 700, color: 'var(--success)'}}>
                        {safeNumber(winRateData.winning_trades, 0)} ({safeToFixed((safeNumber(winRateData.winning_trades, 0) / Math.max(safeNumber(winRateData.total_trades, 0), 1)) * 100, 1, '0.0')}%)
                      </div>
                      <div style={{fontSize: '0.85rem', color: 'var(--muted)', marginTop: '4px'}}>
                        Gross Profit: R{safeToFixed(winRateData.gross_profit, 2)}
                      </div>
                    </div>
                    <div>
                      <div style={{fontSize: '0.9rem', color: 'var(--muted)', marginBottom: '8px'}}>Losing Trades</div>
                      <div style={{fontSize: '1.5rem', fontWeight: 700, color: '#ef4444'}}>
                        {safeNumber(winRateData.losing_trades, 0)} ({safeToFixed((safeNumber(winRateData.losing_trades, 0) / Math.max(safeNumber(winRateData.total_trades, 0), 1)) * 100, 1, '0.0')}%)
                      </div>
                      <div style={{fontSize: '0.85rem', color: 'var(--muted)', marginTop: '4px'}}>
                        Gross Loss: R{safeToFixed(winRateData.gross_loss, 2)}
                      </div>
                    </div>
                  </div>
                </div>
              </>
            ) : (
              <div style={{padding: '40px', textAlign: 'center', background: 'var(--panel)', borderRadius: '6px', border: '1px solid var(--line)'}}>
                <p style={{color: 'var(--muted)', fontSize: '1.1rem'}}>
                  📊 No trade data available yet
                </p>
                <p style={{color: 'var(--muted)', fontSize: '0.9rem', marginTop: '10px'}}>
                  Start trading to see win rate statistics
                </p>
              </div>
            )}
          </div>
        )}
      </div>
    </section>
  );
};

export default ProfitsSection;
