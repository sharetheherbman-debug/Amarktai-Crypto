import React, { useState, useEffect, useCallback } from 'react';
import { get } from '../../../lib/apiClient';

/**
 * DashboardIntelligencePanels — modular intelligence panels for the dashboard.
 *
 * Panels included:
 *   1. MarketBrainPanel   — regime, risk level, preferred strategy, confidence
 *   2. WhaleFlowPanel     — large transfers, exchange inflow/outflow
 *   3. SentimentPanel     — social sentiment, headlines, regulatory alerts
 *   4. OrderbookPanel     — imbalance, spread, liquidity walls
 *   5. CapitalPanel       — per-bot efficiency, capital allocation
 *   6. GeneticsPanel      — parent→child lineage, mutation summary
 */

// ── Shared styles ───────────────────────────────────────────────────────────

const cardStyle = {
  background: 'rgba(15,23,42,0.7)',
  backdropFilter: 'blur(12px)',
  border: '1px solid rgba(99,102,241,0.25)',
  borderRadius: 12,
  padding: 16,
  marginBottom: 12,
};

const headerStyle = {
  margin: '0 0 8px',
  fontSize: 14,
  fontWeight: 700,
  color: '#a5b4fc',
};

const subTextStyle = {
  fontSize: 11,
  color: '#64748b',
  margin: '0 0 8px',
};

const metricStyle = {
  display: 'flex',
  justifyContent: 'space-between',
  padding: '4px 0',
  fontSize: 12,
  borderBottom: '1px solid rgba(51,65,85,0.3)',
};

// ── 1. Market Brain Panel ───────────────────────────────────────────────────

export const MarketBrainPanel = () => {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const result = await get('/diagnostics/regime-summary');
      setData(result);
    } catch {
      // Endpoint may not exist yet — show placeholder
      setData(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
    const iv = setInterval(fetchData, 30000);
    return () => clearInterval(iv);
  }, [fetchData]);

  const regimeColors = {
    trending: '#10b981',
    ranging: '#f59e0b',
    volatile: '#ef4444',
    low_volatility: '#6366f1',
    panic: '#dc2626',
    accumulation: '#22d3ee',
  };

  const symbols = data ? Object.keys(data) : [];
  const primary = symbols.length > 0 ? data[symbols[0]] : null;

  return (
    <div style={cardStyle}>
      <h4 style={headerStyle}>🧠 Market Brain</h4>
      <p style={subTextStyle}>Real-time market regime classification and strategy recommendation</p>
      {loading && !primary && <span style={{ fontSize: 11, color: '#94a3b8' }}>Loading…</span>}
      {primary ? (
        <div>
          <div style={metricStyle}>
            <span style={{ color: '#94a3b8' }}>Regime</span>
            <span style={{
              fontWeight: 700,
              color: regimeColors[primary.regime] || '#e2e8f0',
              textTransform: 'uppercase',
            }}>{primary.regime || 'unknown'}</span>
          </div>
          <div style={metricStyle}>
            <span style={{ color: '#94a3b8' }}>Confidence</span>
            <span style={{ color: '#e2e8f0' }}>{((primary.confidence || 0) * 100).toFixed(1)}%</span>
          </div>
          <div style={metricStyle}>
            <span style={{ color: '#94a3b8' }}>Volatility</span>
            <span style={{ color: '#e2e8f0' }}>{(primary.volatility || 0).toFixed(4)}</span>
          </div>
          <div style={metricStyle}>
            <span style={{ color: '#94a3b8' }}>Preferred Strategy</span>
            <span style={{ color: '#a5b4fc' }}>{primary.trading_params?.preferred_strategy || 'balanced'}</span>
          </div>
          <div style={metricStyle}>
            <span style={{ color: '#94a3b8' }}>Position Size Multiplier</span>
            <span style={{ color: '#e2e8f0' }}>{primary.trading_params?.position_size_multiplier || 1.0}×</span>
          </div>
        </div>
      ) : (
        <div style={{ fontSize: 12, color: '#64748b', padding: '8px 0' }}>
          No regime data available. Market data collection is initializing.
        </div>
      )}
    </div>
  );
};

// ── 2. Whale Flow Panel ─────────────────────────────────────────────────────

export const WhaleFlowPanel = () => {
  const [signals, setSignals] = useState([]);
  const [loading, setLoading] = useState(false);

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const result = await get('/diagnostics/whale-signals');
      setSignals(result?.signals || []);
    } catch {
      setSignals([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
    const iv = setInterval(fetchData, 60000);
    return () => clearInterval(iv);
  }, [fetchData]);

  return (
    <div style={cardStyle}>
      <h4 style={headerStyle}>🐋 Whale Flow</h4>
      <p style={subTextStyle}>Large crypto transfers and exchange inflow/outflow indicators</p>
      {loading && signals.length === 0 && <span style={{ fontSize: 11, color: '#94a3b8' }}>Loading…</span>}
      {signals.length > 0 ? (
        <div>
          {signals.slice(0, 5).map((s, i) => (
            <div key={i} style={{
              ...metricStyle,
              flexDirection: 'column',
              gap: 2,
            }}>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span style={{ color: '#e2e8f0', fontWeight: 600 }}>{s.symbol || 'BTC'}</span>
                <span style={{
                  fontSize: 10,
                  color: s.direction === 'inflow' ? '#10b981' : '#ef4444',
                  fontWeight: 700,
                }}>{s.direction?.toUpperCase()}</span>
              </div>
              <div style={{ fontSize: 10, color: '#64748b' }}>
                {s.value_usd ? `${Number(s.value_usd).toLocaleString()} USD` : 'Value unknown'} · Confidence: {((s.confidence || 0) * 100).toFixed(0)}%
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div style={{ fontSize: 12, color: '#64748b', padding: '8px 0' }}>
          No whale signals detected. Configure on-chain enrichers (Glassnode, Etherscan, Whale Alert) in API Setup.
        </div>
      )}
    </div>
  );
};

// ── 3. Sentiment & News Panel ───────────────────────────────────────────────

export const SentimentPanel = () => {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const result = await get('/diagnostics/sentiment-summary');
      setData(result);
    } catch {
      setData(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
    const iv = setInterval(fetchData, 120000);
    return () => clearInterval(iv);
  }, [fetchData]);

  const sentimentColor = (score) => {
    if (score > 0.6) return '#10b981';
    if (score > 0.4) return '#f59e0b';
    return '#ef4444';
  };

  return (
    <div style={cardStyle}>
      <h4 style={headerStyle}>💬 Sentiment & News Intelligence</h4>
      <p style={subTextStyle}>Social sentiment scores and crypto news headlines</p>
      {data ? (
        <div>
          <div style={metricStyle}>
            <span style={{ color: '#94a3b8' }}>Overall Sentiment</span>
            <span style={{
              fontWeight: 700,
              color: sentimentColor(data.score || 0.5),
            }}>{data.label || 'Neutral'} ({((data.score || 0.5) * 100).toFixed(0)}%)</span>
          </div>
          {data.headlines && data.headlines.slice(0, 3).map((h, i) => (
            <div key={i} style={{ fontSize: 11, color: '#94a3b8', padding: '4px 0', borderBottom: '1px solid rgba(51,65,85,0.2)' }}>
              📰 {h.title || h}
            </div>
          ))}
        </div>
      ) : (
        <div style={{ fontSize: 12, color: '#64748b', padding: '8px 0' }}>
          No sentiment data available. Configure LunarCrush or CryptoPanic in API Setup.
        </div>
      )}
    </div>
  );
};

// ── 4. Orderbook Intelligence Panel ─────────────────────────────────────────

export const OrderbookPanel = () => {
  const [data, setData] = useState(null);

  const fetchData = useCallback(async () => {
    try {
      const result = await get('/diagnostics/orderbook-summary');
      setData(result);
    } catch {
      setData(null);
    }
  }, []);

  useEffect(() => {
    fetchData();
    const iv = setInterval(fetchData, 15000);
    return () => clearInterval(iv);
  }, [fetchData]);

  return (
    <div style={cardStyle}>
      <h4 style={headerStyle}>📚 Orderbook Intelligence</h4>
      <p style={subTextStyle}>Bid/ask imbalance, spread, and liquidity wall detection</p>
      {data ? (
        <div>
          <div style={metricStyle}>
            <span style={{ color: '#94a3b8' }}>Imbalance</span>
            <span style={{
              fontWeight: 700,
              color: data.imbalance > 0 ? '#10b981' : '#ef4444',
            }}>{(data.imbalance || 0).toFixed(3)} ({data.imbalance > 0 ? 'Buy pressure' : 'Sell pressure'})</span>
          </div>
          <div style={metricStyle}>
            <span style={{ color: '#94a3b8' }}>Spread</span>
            <span style={{ color: '#e2e8f0' }}>{((data.spread_pct || 0) * 100).toFixed(3)}%</span>
          </div>
          {data.walls && data.walls.length > 0 && (
            <div style={{ marginTop: 6 }}>
              <div style={{ fontSize: 11, color: '#a5b4fc', fontWeight: 600, marginBottom: 4 }}>Liquidity Walls</div>
              {data.walls.slice(0, 3).map((w, i) => (
                <div key={i} style={{ fontSize: 11, color: '#94a3b8', padding: '2px 0' }}>
                  {w.side === 'bid' ? '🟢' : '🔴'} {w.side.toUpperCase()} @ {w.price} — {w.volume} units
                </div>
              ))}
            </div>
          )}
        </div>
      ) : (
        <div style={{ fontSize: 12, color: '#64748b', padding: '8px 0' }}>
          No orderbook data available. Orderbook analysis activates during live trading.
        </div>
      )}
    </div>
  );
};

// ── 5. Capital Intelligence Panel ───────────────────────────────────────────

export const CapitalPanel = () => {
  const [data, setData] = useState(null);

  const fetchData = useCallback(async () => {
    try {
      const result = await get('/diagnostics/capital-efficiency');
      setData(result);
    } catch {
      setData(null);
    }
  }, []);

  useEffect(() => {
    fetchData();
    const iv = setInterval(fetchData, 30000);
    return () => clearInterval(iv);
  }, [fetchData]);

  return (
    <div style={cardStyle}>
      <h4 style={headerStyle}>💰 Capital Intelligence</h4>
      <p style={subTextStyle}>Per-bot efficiency ranking and capital allocation recommendations</p>
      {data ? (
        <div>
          <div style={metricStyle}>
            <span style={{ color: '#94a3b8' }}>Avg Efficiency</span>
            <span style={{ color: '#e2e8f0', fontWeight: 700 }}>{(data.avg_efficiency || 0).toFixed(4)} %/hr</span>
          </div>
          <div style={metricStyle}>
            <span style={{ color: '#94a3b8' }}>Idle Bots</span>
            <span style={{ color: data.idle_count > 0 ? '#f59e0b' : '#10b981', fontWeight: 700 }}>{data.idle_count || 0}</span>
          </div>
          <div style={metricStyle}>
            <span style={{ color: '#94a3b8' }}>Total Evaluated</span>
            <span style={{ color: '#e2e8f0' }}>{data.total_evaluated || 0}</span>
          </div>
          {data.best_bot && (
            <div style={metricStyle}>
              <span style={{ color: '#94a3b8' }}>Best Performer</span>
              <span style={{ color: '#10b981' }}>{data.best_bot.bot_id} ({data.best_bot.score?.toFixed(4)})</span>
            </div>
          )}
          {data.reallocation?.increase_capital?.length > 0 && (
            <div style={{ marginTop: 6, fontSize: 11, color: '#a5b4fc' }}>
              ⬆ Increase capital: {data.reallocation.increase_capital.join(', ')}
            </div>
          )}
          {data.reallocation?.decrease_capital?.length > 0 && (
            <div style={{ fontSize: 11, color: '#f59e0b' }}>
              ⬇ Decrease capital: {data.reallocation.decrease_capital.join(', ')}
            </div>
          )}
        </div>
      ) : (
        <div style={{ fontSize: 12, color: '#64748b', padding: '8px 0' }}>
          Capital efficiency data initializes after bots open positions.
        </div>
      )}
    </div>
  );
};

// ── 6. Bot Genetics Panel ───────────────────────────────────────────────────

export const GeneticsPanel = () => {
  const [data, setData] = useState(null);

  const fetchData = useCallback(async () => {
    try {
      const result = await get('/diagnostics/genetics-summary');
      setData(result);
    } catch {
      setData(null);
    }
  }, []);

  useEffect(() => {
    fetchData();
    const iv = setInterval(fetchData, 60000);
    return () => clearInterval(iv);
  }, [fetchData]);

  return (
    <div style={cardStyle}>
      <h4 style={headerStyle}>🧬 Bot Genetics / Evolution</h4>
      <p style={subTextStyle}>Parent→child lineage, parameter mutation, and performance comparison</p>
      {data ? (
        <div>
          <div style={metricStyle}>
            <span style={{ color: '#94a3b8' }}>Total Children</span>
            <span style={{ color: '#e2e8f0' }}>{data.total_children || 0}</span>
          </div>
          <div style={metricStyle}>
            <span style={{ color: '#94a3b8' }}>Population Cap</span>
            <span style={{ color: '#e2e8f0' }}>{data.population_cap || 50}</span>
          </div>
          <div style={metricStyle}>
            <span style={{ color: '#94a3b8' }}>Avg Generation</span>
            <span style={{ color: '#e2e8f0' }}>{(data.avg_generation || 0).toFixed(1)}</span>
          </div>
          {data.recent_mutations && data.recent_mutations.length > 0 && (
            <div style={{ marginTop: 6 }}>
              <div style={{ fontSize: 11, color: '#a5b4fc', fontWeight: 600, marginBottom: 4 }}>Recent Mutations</div>
              {data.recent_mutations.slice(0, 3).map((m, i) => (
                <div key={i} style={{ fontSize: 11, color: '#94a3b8', padding: '2px 0' }}>
                  🧬 {m.child_id} ← {m.parent_id} (gen {m.generation})
                </div>
              ))}
            </div>
          )}
        </div>
      ) : (
        <div style={{ fontSize: 12, color: '#64748b', padding: '8px 0' }}>
          Bot genetics data populates after evolutionary spawning occurs.
        </div>
      )}
    </div>
  );
};

export default {
  MarketBrainPanel,
  WhaleFlowPanel,
  SentimentPanel,
  OrderbookPanel,
  CapitalPanel,
  GeneticsPanel,
};
