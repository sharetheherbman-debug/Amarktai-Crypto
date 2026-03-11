import React, { useState, useEffect, useCallback } from 'react';
import { MARKET_DATA_PROVIDERS, INTELLIGENCE_ENRICHERS, PLATFORM_CONFIG } from '../../../constants/platforms';
import { get } from '../../../lib/apiClient';

/**
 * MarketIntelligencePanel — compact market intelligence status card.
 *
 * Main dashboard view: single status summary card with key metrics.
 * Provider detail rows are collapsed behind a "View details" toggle to
 * reduce visual noise and eliminate the old repetitive provider grids.
 */

const STATUS_STYLES = {
  healthy: { label: '● Healthy', dot: '#10b981', bg: 'rgba(16,185,129,0.15)', color: '#10b981', border: 'rgba(16,185,129,0.3)' },
  degraded: { label: '⚠ Degraded', dot: '#f59e0b', bg: 'rgba(245,158,11,0.15)', color: '#f59e0b', border: 'rgba(245,158,11,0.3)' },
  down: { label: '✗ Down', dot: '#ef4444', bg: 'rgba(239,68,68,0.15)', color: '#ef4444', border: 'rgba(239,68,68,0.3)' },
  unconfigured: { label: '○ Not configured', dot: '#475569', bg: 'rgba(100,116,139,0.12)', color: '#94a3b8', border: 'rgba(100,116,139,0.25)' },
};

const glass = (extra = {}) => ({
  background: 'rgba(15,23,42,0.75)',
  backdropFilter: 'blur(14px)',
  border: '1px solid rgba(99,102,241,0.22)',
  borderRadius: 14,
  ...extra,
});

const StatusChip = ({ status }) => {
  const s = STATUS_STYLES[status] || STATUS_STYLES.unconfigured;
  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: 5,
      padding: '3px 12px', borderRadius: 20, fontSize: 12, fontWeight: 600,
      background: s.bg, color: s.color, border: `1px solid ${s.border}`,
    }}>
      {s.label}
    </span>
  );
};

const ProviderDetailRow = ({ config, providerHealth }) => {
  const health = providerHealth?.[config?.id] || {};
  const status = health.status || 'unconfigured';
  const s = STATUS_STYLES[status] || STATUS_STYLES.unconfigured;
  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 10,
      padding: '10px 14px', borderRadius: 8,
      background: 'rgba(15,23,42,0.55)',
      border: '1px solid rgba(51,65,85,0.4)',
    }}>
      <span style={{ fontSize: 20, width: 26, textAlign: 'center' }}>{config?.icon || '📦'}</span>
      <div style={{ flex: 1 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
          <span style={{ fontWeight: 700, color: '#e2e8f0', fontSize: 14 }}>{config?.displayName || config?.id}</span>
          {config?.priority && (
            <span style={{ fontSize: 11, color: '#a5b4fc', background: 'rgba(99,102,241,0.18)', padding: '1px 7px', borderRadius: 5, fontWeight: 700 }}>
              P{config.priority}
            </span>
          )}
          <StatusChip status={status} />
        </div>
        {health.last_tested && (
          <div style={{ fontSize: 11, color: '#64748b', marginTop: 3 }}>
            Checked: {new Date(health.last_tested).toLocaleString()}
          </div>
        )}
      </div>
    </div>
  );
};

const CollapsibleGroup = ({ title, icon, children, defaultOpen = false }) => {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div style={{ marginBottom: 10 }}>
      <button
        onClick={() => setOpen(o => !o)}
        style={{
          width: '100%', display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          background: 'rgba(99,102,241,0.1)', border: '1px solid rgba(99,102,241,0.2)',
          borderRadius: 9, padding: '10px 14px', cursor: 'pointer', color: '#a5b4fc',
          fontSize: 14, fontWeight: 700,
        }}
      >
        <span>{icon} {title}</span>
        <span style={{ fontSize: 12, opacity: 0.7 }}>{open ? '▲ collapse' : '▼ expand'}</span>
      </button>
      {open && <div style={{ marginTop: 8, display: 'flex', flexDirection: 'column', gap: 6 }}>{children}</div>}
    </div>
  );
};

const MarketIntelligencePanel = () => {
  const [providerHealth, setProviderHealth] = useState({});
  const [intelligence, setIntelligence] = useState({});
  const [loading, setLoading] = useState(false);
  const [showDetail, setShowDetail] = useState(false);

  const fetchHealth = useCallback(async () => {
    setLoading(true);
    try {
      const statusRes = await get('/keys/status');
      const statusMap = statusRes?.status_map || {};
      let diagnostics = {};
      try { diagnostics = await get('/diagnostics/provider-health'); } catch { /* no-op */ }
      const healthMap = diagnostics?.provider_health || {};
      let intelligencePayload = diagnostics?.intelligence || {};
      if (!Object.keys(intelligencePayload?.prices || {}).length) {
        try {
          const marketPrices = await get('/market/prices');
          const norm = {};
          Object.entries(marketPrices?.prices || {}).forEach(([sym, p]) => {
            norm[sym] = { price: p?.price, provider: p?.source || p?.provider || 'market_api' };
          });
          intelligencePayload = { ...intelligencePayload, prices: norm };
        } catch { /* fallback unavailable */ }
      }
      setIntelligence(intelligencePayload);

      const allIds = [...MARKET_DATA_PROVIDERS, ...INTELLIGENCE_ENRICHERS];
      const merged = {};
      for (const id of allIds) {
        const keyStatus = statusMap[id]?.status;
        const mi = healthMap?.[id];
        let status = 'unconfigured';
        if (keyStatus === 'configured_valid' || keyStatus === 'test_ok') status = 'healthy';
        else if (keyStatus === 'configured_invalid' || keyStatus === 'test_failed') status = 'down';
        else if (keyStatus === 'configured_untested' || keyStatus === 'saved_untested') status = 'degraded';
        else if (mi?.healthy || mi?.status === 'healthy') status = 'healthy';
        else if (mi?.status === 'degraded') status = 'degraded';
        merged[id] = { status, last_tested: statusMap[id]?.last_tested_at || mi?.last_tested };
      }
      setProviderHealth(merged);
    } catch (err) {
      console.error('Failed to fetch provider health', err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchHealth();
    const interval = setInterval(fetchHealth, 60000);
    return () => clearInterval(interval);
  }, [fetchHealth]);

  const healthyMarketCount = MARKET_DATA_PROVIDERS.filter(id => providerHealth[id]?.status === 'healthy').length;
  const healthyEnricherCount = INTELLIGENCE_ENRICHERS.filter(id => providerHealth[id]?.status === 'healthy').length;
  const overallStatus = healthyMarketCount > 0 ? 'healthy' : 'degraded';
  const priceRows = Object.entries(intelligence?.prices || {});
  const whaleSignals = intelligence?.whale_signals || [];
  const dominantRegime = intelligence?.regime || intelligence?.market_regime;
  const lastRefresh = intelligence?.timestamp || intelligence?.fetched_at;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>

      {/* ── Compact Summary Card ─────────────────────────────────────── */}
      <div style={glass({ padding: '20px 22px' })}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 14, marginBottom: 16 }}>
          <span style={{ fontSize: 30 }}>🧠</span>
          <div style={{ flex: 1 }}>
            <h3 style={{ margin: 0, fontSize: 18, fontWeight: 800, color: '#e2e8f0', letterSpacing: '-0.3px' }}>
              Market Intelligence
            </h3>
            <p style={{ margin: '3px 0 0', fontSize: 13, color: '#94a3b8' }}>
              Live normalized output from configured providers
            </p>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            {loading && <span style={{ fontSize: 13, color: '#94a3b8' }}>⟳</span>}
            <StatusChip status={overallStatus} />
          </div>
        </div>

        {/* Key metrics row */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(130px, 1fr))', gap: 10, marginBottom: 16 }}>
          {[
            { label: 'Market Sources', value: `${healthyMarketCount} / ${MARKET_DATA_PROVIDERS.length}`, color: healthyMarketCount > 0 ? '#10b981' : '#ef4444' },
            { label: 'Intelligence Enrichers', value: `${healthyEnricherCount} / ${INTELLIGENCE_ENRICHERS.length}`, color: '#a5b4fc' },
            { label: 'Price Symbols', value: priceRows.length || '—', color: '#e2e8f0' },
            { label: 'Whale Signals', value: whaleSignals.length || '—', color: '#e2e8f0' },
          ].map(({ label, value, color }) => (
            <div key={label} style={{ background: 'rgba(30,41,59,0.55)', borderRadius: 10, padding: '12px 14px' }}>
              <div style={{ fontSize: 22, fontWeight: 800, color }}>{value}</div>
              <div style={{ fontSize: 12, color: '#64748b', marginTop: 2 }}>{label}</div>
            </div>
          ))}
        </div>

        {/* Additional context row */}
        <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap', fontSize: 13, color: '#94a3b8' }}>
          {dominantRegime && (
            <span>🌡 Regime: <strong style={{ color: '#e2e8f0' }}>{dominantRegime}</strong></span>
          )}
          {lastRefresh && (
            <span>🕐 Last refresh: <strong style={{ color: '#e2e8f0' }}>{new Date(lastRefresh).toLocaleTimeString()}</strong></span>
          )}
          {healthyMarketCount === 0 && (
            <span style={{ color: '#f59e0b' }}>⚠ No market sources healthy — configure CoinDesk / CryptoCompare</span>
          )}
        </div>
      </div>

      {/* ── Live Price Output (condensed) ────────────────────────────── */}
      {priceRows.length > 0 && (
        <div style={glass({ padding: '16px 18px' })}>
          <h4 style={{ margin: '0 0 12px', fontSize: 15, fontWeight: 700, color: '#a5b4fc' }}>🗞️ Live Prices</h4>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: 8 }}>
            {priceRows.slice(0, 9).map(([symbol, payload]) => (
              <div key={symbol} style={{ background: 'rgba(30,41,59,0.6)', borderRadius: 10, padding: '10px 12px' }}>
                <div style={{ fontSize: 12, color: '#94a3b8' }}>{symbol}</div>
                <div style={{ fontSize: 18, color: '#e2e8f0', fontWeight: 800, marginTop: 2 }}>
                  {payload?.price != null ? Number(payload.price).toLocaleString(undefined, { maximumFractionDigits: 2 }) : '—'}
                </div>
                <div style={{ fontSize: 11, color: '#64748b', marginTop: 2 }}>via {payload?.provider || 'unknown'}</div>
              </div>
            ))}
          </div>
          {whaleSignals.length > 0 && (
            <div style={{ marginTop: 12, fontSize: 13, color: '#94a3b8' }}>
              🐋 Whale activity: {whaleSignals.slice(0, 3).map(s => `${s.coin || s.symbol}: ${s.signal || s.direction || 'detected'}`).join(' • ')}
            </div>
          )}
        </div>
      )}

      {/* ── Collapsible Provider Detail (admin-style) ─────────────────── */}
      <div style={glass({ padding: '14px 18px' })}>
        <button
          onClick={() => setShowDetail(o => !o)}
          style={{
            width: '100%', display: 'flex', alignItems: 'center', justifyContent: 'space-between',
            background: 'transparent', border: 'none', cursor: 'pointer', padding: 0,
            color: '#94a3b8', fontSize: 14, fontWeight: 600,
          }}
        >
          <span>⚙ Provider details</span>
          <span style={{ fontSize: 12 }}>{showDetail ? '▲ hide' : '▼ show'}</span>
        </button>

        {showDetail && (
          <div style={{ marginTop: 14, display: 'flex', flexDirection: 'column', gap: 12 }}>
            <CollapsibleGroup title="Core Market Data" icon="📈" defaultOpen>
              {MARKET_DATA_PROVIDERS.map(id => (
                <ProviderDetailRow key={id} config={PLATFORM_CONFIG[id]} providerHealth={providerHealth} />
              ))}
            </CollapsibleGroup>
            <CollapsibleGroup title="Intelligence Enrichers" icon="🔍">
              {INTELLIGENCE_ENRICHERS.map(id => (
                <ProviderDetailRow key={id} config={PLATFORM_CONFIG[id]} providerHealth={providerHealth} />
              ))}
            </CollapsibleGroup>
          </div>
        )}
      </div>

    </div>
  );
};

export default MarketIntelligencePanel;

