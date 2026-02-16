import React from 'react';
import { Line } from 'react-chartjs-2';
import SectionHeader from '@/ui/components/SectionHeader';
import StatCard from '@/ui/components/StatCard';
import ErrorBoundary from '../../../components/ErrorBoundary';

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

const ProfitsSection = ({
  drawdownData,
  drawdownRange,
  equityData,
  equityRange,
  flokxAlerts,
  flokxStatus,
  formatDate,
  graphPeriod,
  isFlokxActive,
  loadFlokxAlerts,
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
  const maxDrawdown = drawdownData?.max_drawdown_pct ?? drawdownData?.max_drawdown;
  const feesValue = profitData?.fees ?? profitData?.total_fees ?? null;

  const chartData = {
    labels: profitData?.labels || ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'],
    datasets: [{
      label: 'Profit (ZAR)',
      data: profitData?.values || [0, 0, 0, 0, 0, 0, 0],
      borderColor: '#22c55e',
      backgroundColor: 'rgba(34, 197, 94, 0.15)',
      fill: true,
      tension: 0.4,
      pointRadius: 4,
      pointHoverRadius: 8,
      pointBackgroundColor: '#22c55e',
      pointBorderColor: 'rgba(34, 197, 94, 0.6)',
      pointBorderWidth: 2,
      borderWidth: 2.5,
      segment: { borderColor: ctx => ctx.p0.parsed.y > ctx.p1.parsed.y ? '#ef4444' : '#22c55e' }
    }]
  };

  const chartOptions = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: {
        display: false
      },
      tooltip: {
        backgroundColor: 'rgba(10, 12, 20, 0.95)',
        titleColor: 'var(--success)',
        bodyColor: '#ffffff',
        borderColor: 'rgba(34, 197, 94, 0.6)',
        borderWidth: 1,
        padding: 12,
        titleFont: { size: 14, weight: 'bold' },
        bodyFont: { size: 13 }
      }
    },
    scales: {
      y: {
        beginAtZero: true,
        ticks: {
          color: 'var(--muted)',
          font: { size: 11 },
          callback: function(value) {
            return 'R' + value;
          }
        },
        grid: { 
          color: 'rgba(255, 255, 255, 0.05)',
          drawBorder: false
        },
        border: { display: false }
      },
      x: {
        ticks: {
          color: 'var(--muted)',
          font: { size: 11 }
        },
        grid: { 
          display: false
        },
        border: { display: false }
      }
    },
    interaction: {
      intersect: false,
      mode: 'index'
    }
  };

  return (
    <section className="section active">
      <div className="card">
        <SectionHeader
          title="💹 Profits & Performance"
          subtitle="Track equity, drawdown, and performance metrics across bots."
        />

        <div className="profit-kpi-grid">
          <StatCard label="Net P&L" value={formatZAR(overviewData?.totalProfit)} />
          <StatCard label="Win Rate" value={safePercent(overviewData?.winRate, 1)} />
          <StatCard label="Max Drawdown" value={maxDrawdown !== undefined && maxDrawdown !== null ? `${safeToFixed(maxDrawdown, 2)}%` : NOT_AVAILABLE} />
          <StatCard label="Trades/Day" value={safeNumber(overviewData?.todaysTrades, 0)} />
          <StatCard label="Fees" value={feesValue !== null ? formatZAR(feesValue) : NOT_AVAILABLE} />
        </div>
        
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
              <div>
                <h3 style={{marginBottom: '16px'}}>📊 System Metrics</h3>
                
                {/* Simplified - Keep only Flokx Alerts for traders */}
                <div style={{marginBottom: '20px'}}>
                  <h3 style={{fontSize: '1.1rem', fontWeight: 700, color: 'var(--text)', marginBottom: '12px', display: 'flex', alignItems: 'center', gap: '8px'}}>
                    📊 Market Alerts & Intelligence
                  </h3>
                </div>

                {/* Flokx Alerts Content */}
                <div style={{marginTop: '20px'}}>
                  <ErrorBoundary title="Flokx Alerts Error" message="Unable to load Flokx alerts. Please check your API configuration.">
                    <div>
                      {!isFlokxActive && (
                        <div style={{padding: '40px', textAlign: 'center', background: 'var(--panel)', borderRadius: '6px', border: '1px solid var(--line)'}}>
                            <p style={{color: 'var(--muted)', marginBottom: '12px'}}>
                              ⚠️ Flokx alerts are not active. Configure your Flokx API key in the API Setup section to enable real-time alerts.
                            </p>
                            {flokxStatus.last_error && (
                              <p style={{color: 'var(--error)', marginBottom: '12px', fontSize: '0.85rem'}}>
                                Status check: {flokxStatus.last_error}
                              </p>
                            )}
                            <button 
                              onClick={() => showSection('api')}
                              style={{
                                padding: '8px 16px',
                                background: 'var(--accent2)',
                                color: 'var(--text)',
                                border: 'none',
                                borderRadius: '6px',
                                fontWeight: 600,
                                cursor: 'pointer'
                              }}
                            >
                              Configure Flokx API
                            </button>
                          </div>
                        )}
                        
                        {isFlokxActive && (
                          <div style={{display: 'flex', flexDirection: 'column', gap: '12px'}}>
                            <div style={{display: 'flex', justifyContent: 'space-between', alignItems: 'center'}}>
                              <div style={{display: 'flex', alignItems: 'center', gap: '8px'}}>
                                <div style={{width: '8px', height: '8px', borderRadius: '50%', background: 'var(--success)'}}></div>
                                <span style={{fontSize: '0.85rem', color: 'var(--muted)'}}>
                                  Flokx Active {flokxStatus.last_tested_at ? `• Last tested ${formatDate(flokxStatus.last_tested_at)}` : ''}
                                </span>
                              </div>
                              <button 
                                onClick={loadFlokxAlerts} 
                                style={{
                                  padding: '6px 12px',
                                  borderRadius: '6px',
                                  background: 'var(--accent2)',
                                  color: 'var(--text)',
                                  border: 'none',
                                  fontWeight: 600,
                                  fontSize: '0.85rem',
                                  cursor: 'pointer'
                                }}
                              >
                                Refresh Alerts
                              </button>
                            </div>
                            
                            <div style={{background: 'var(--glass)', padding: '12px', borderRadius: '6px', border: '1px solid var(--line)'}}>
                              {!Array.isArray(flokxAlerts) || flokxAlerts.length === 0 ? (
                                <p style={{color: 'var(--muted)', padding: '20px', textAlign: 'center'}}>
                                  ✓ No alerts at this time - System running smoothly
                                </p>
                              ) : (
                                <div style={{display: 'flex', flexDirection: 'column', gap: '8px'}}>
                                  {Array.isArray(flokxAlerts) && flokxAlerts.map((alert, idx) => (
                                    <div 
                                      key={idx}
                                      style={{
                                        padding: '12px',
                                        background: 'var(--panel)',
                                        borderRadius: '6px',
                                        borderLeft: '4px solid ' + getAlertColor(alert.priority || alert.type || 'info'),
                                        display: 'flex',
                                        justifyContent: 'space-between',
                                        alignItems: 'center'
                                      }}
                                    >
                                      <div>
                                        <div style={{fontWeight: 600, marginBottom: '4px'}}>
                                          {alert.title || alert.pair || 'Alert'}
                                        </div>
                                        <div style={{fontSize: '0.85rem', color: 'var(--muted)'}}>
                                          {alert.message || 'No details available'}
                                        </div>
                                        <div style={{fontSize: '0.75rem', color: 'var(--muted)', marginTop: '4px'}}>
                                          {alert.timestamp ? new Date(alert.timestamp).toLocaleString() : 'No timestamp'}
                                        </div>
                                      </div>
                                      {(alert.priority || alert.type) && (
                                        <div style={{
                                          padding: '4px 8px',
                                          borderRadius: '4px',
                                          fontSize: '0.75rem',
                                          fontWeight: 600,
                                          background: getAlertColor(alert.priority || alert.type || 'info'),
                                          color: 'white'
                                        }}>
                                          {(alert.priority || alert.type || 'INFO').toUpperCase()}
                                        </div>
                                      )}
                                    </div>
                                  ))}
                                </div>
                              )}
                            </div>
                          </div>
                        )}
                      </div>
                    </ErrorBoundary>
                  </div>
                </div>
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
              background: 'linear-gradient(135deg, rgba(0, 0, 42, 0.4) 0%, rgba(0, 0, 20, 0.6) 100%)',
              borderRadius: '10px',
              border: '1px solid rgba(16, 185, 129, 0.2)',
              boxShadow: '0 4px 6px rgba(0, 0, 0, 0.1)',
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
                  background: 'linear-gradient(135deg, rgba(0, 0, 42, 0.4) 0%, rgba(0, 0, 20, 0.6) 100%)',
                  borderRadius: '10px',
                  border: '1px solid rgba(16, 185, 129, 0.2)',
                  boxShadow: '0 4px 6px rgba(0, 0, 0, 0.1)',
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
                          borderColor: 'var(--success)',
                          backgroundColor: 'rgba(16, 185, 129, 0.2)',
                          fill: true,
                          tension: 0.4,
                          pointRadius: 3,
                          pointHoverRadius: 6,
                          pointBackgroundColor: 'var(--success)',
                          pointBorderColor: '#ffffff',
                          pointBorderWidth: 2
                        }]
                      }}
                      options={{
                        responsive: true,
                        maintainAspectRatio: false,
                        plugins: {
                          legend: { display: false },
                          tooltip: {
                            backgroundColor: 'rgba(0, 0, 42, 0.95)',
                            titleColor: 'var(--success)',
                            bodyColor: '#ffffff',
                            borderColor: 'var(--success)',
                            borderWidth: 2,
                            padding: 12,
                            titleFont: { size: 14, weight: 'bold' },
                            bodyFont: { size: 13 },
                            callbacks: {
                              label: (context) => `Equity: R${safeToFixed(context.parsed.y, 2)}`
                            }
                          }
                        },
                        scales: {
                          y: {
                            beginAtZero: false,
                            ticks: { 
                              color: '#8b8b8b',
                              font: { size: 11 },
                              callback: (value) => 'R' + safeToFixed(value, 0, '0')
                            },
                            grid: { color: 'rgba(255, 255, 255, 0.05)', drawBorder: false }
                          },
                          x: {
                            ticks: { color: '#8b8b8b', font: { size: 10 }, maxRotation: 45, minRotation: 45 },
                            grid: { display: false }
                          }
                        }
                      }}
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
                  background: 'linear-gradient(135deg, rgba(0, 0, 42, 0.4) 0%, rgba(0, 0, 20, 0.6) 100%)',
                  borderRadius: '10px',
                  border: '1px solid rgba(239, 68, 68, 0.2)',
                  boxShadow: '0 4px 6px rgba(0, 0, 0, 0.1)',
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
                          backgroundColor: 'rgba(239, 68, 68, 0.2)',
                          fill: true,
                          tension: 0.4,
                          pointRadius: 3,
                          pointHoverRadius: 6,
                          pointBackgroundColor: '#ef4444',
                          pointBorderColor: '#ffffff',
                          pointBorderWidth: 2
                        }]
                      }}
                      options={{
                        responsive: true,
                        maintainAspectRatio: false,
                        plugins: {
                          legend: { display: false },
                          tooltip: {
                            backgroundColor: 'rgba(0, 0, 42, 0.95)',
                            titleColor: '#ef4444',
                            bodyColor: '#ffffff',
                            borderColor: '#ef4444',
                            borderWidth: 2,
                            padding: 12,
                            titleFont: { size: 14, weight: 'bold' },
                            bodyFont: { size: 13 },
                            callbacks: {
                              label: (context) => `Drawdown: ${safeToFixed(Math.abs(context.parsed.y), 2)}%`
                            }
                          }
                        },
                        scales: {
                          y: {
                            reverse: false,
                            max: 0,
                            ticks: { 
                              color: '#8b8b8b',
                              font: { size: 11 },
                              callback: (value) => safeToFixed(Math.abs(value), 1, '0.0') + '%'
                            },
                            grid: { color: 'rgba(255, 255, 255, 0.05)', drawBorder: false }
                          },
                          x: {
                            ticks: { color: '#8b8b8b', font: { size: 10 }, maxRotation: 45, minRotation: 45 },
                            grid: { display: false }
                          }
                        }
                      }}
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
                  background: 'linear-gradient(135deg, rgba(0, 0, 42, 0.4) 0%, rgba(0, 0, 20, 0.6) 100%)',
                  borderRadius: '10px',
                  border: '1px solid rgba(139, 92, 246, 0.2)',
                  boxShadow: '0 4px 6px rgba(0, 0, 0, 0.1)'
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
