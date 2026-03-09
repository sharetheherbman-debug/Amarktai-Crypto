import React, { useState, useEffect, useCallback } from 'react';
import { MARKET_DATA_PROVIDERS, INTELLIGENCE_ENRICHERS, PLATFORM_CONFIG } from '../../../constants/platforms';
import { get } from '../../../lib/apiClient';

/**
 * MarketIntelligencePanel — canonical market intelligence & data provider dashboard.
 *
 * Shows:
 *  - Provider health, priority, and fallback order
 *  - Capabilities per provider (prices, metadata, whale flow, sentiment, news, on-chain)
 *  - Intelligence enricher status
 *  - Degraded-state warnings when enrichers are missing
 */

const CAPABILITY_LABELS = {
  prices: '💰 Prices',
  ohlcv: '📊 OHLCV',
  metadata: '📋 Metadata',
  market_cap: '📈 Market Cap',
  on_chain: '🔗 On-Chain',
  whale_flow: '🐋 Whale Flow',
  sentiment: '💬 Sentiment',
  news: '📰 News',
};

const STATUS_STYLES = {
  healthy: { label: '● Healthy', bg: 'rgba(16,185,129,0.15)', color: '#10b981', border: 'rgba(16,185,129,0.3)' },
  degraded: { label: '⚠ Degraded', bg: 'rgba(245,158,11,0.15)', color: '#f59e0b', border: 'rgba(245,158,11,0.3)' },
  down: { label: '✗ Down', bg: 'rgba(239,68,68,0.15)', color: '#ef4444', border: 'rgba(239,68,68,0.3)' },
  unconfigured: { label: '○ Not configured', bg: 'rgba(100,116,139,0.15)', color: '#94a3b8', border: 'rgba(100,116,139,0.3)' },
};

const cardStyle = {
  background: 'rgba(15,23,42,0.7)',
  backdropFilter: 'blur(12px)',
  border: '1px solid rgba(99,102,241,0.25)',
  borderRadius: 12,
  padding: 16,
  marginBottom: 12,
};

const StatusBadge = ({ status }) => {
  const s = STATUS_STYLES[status] || STATUS_STYLES.unconfigured;
  return (
    <span style={{
      padding: '2px 10px', borderRadius: 20, fontSize: 11, fontWeight: 600,
      background: s.bg, color: s.color, border: `1px solid ${s.border}`,
    }}>
      {s.label}
    </span>
  );
};

const ProviderRow = ({ config, providerHealth }) => {
  const health = providerHealth?.[config.id];
  const status = health?.status || 'unconfigured';
  const capabilities = config.capabilities || [];

  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 10, padding: '8px 0',
      borderBottom: '1px solid rgba(51,65,85,0.4)',
    }}>
      <span style={{ fontSize: 18, width: 28, textAlign: 'center' }}>{config.icon}</span>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{ fontWeight: 700, color: '#e2e8f0', fontSize: 13 }}>{config.displayName}</span>
          {config.priority && (
            <span style={{
              fontSize: 10, fontWeight: 700, color: '#a5b4fc',
              background: 'rgba(99,102,241,0.2)', padding: '1px 6px', borderRadius: 4,
            }}>
              P{config.priority}
            </span>
          )}
          <StatusBadge status={status} />
        </div>
        <div style={{ display: 'flex', gap: 6, marginTop: 4, flexWrap: 'wrap' }}>
          {capabilities.map(cap => (
            <span key={cap} style={{
              fontSize: 10, color: '#94a3b8', background: 'rgba(30,41,59,0.7)',
              padding: '1px 6px', borderRadius: 4,
            }}>
              {CAPABILITY_LABELS[cap] || cap}
            </span>
          ))}
        </div>
        {health?.last_tested && (
          <div style={{ fontSize: 10, color: '#64748b', marginTop: 2 }}>
            Last checked: {new Date(health.last_tested).toLocaleString()}
          </div>
        )}
      </div>
    </div>
  );
};

const MarketIntelligencePanel = () => {
  const [providerHealth, setProviderHealth] = useState({});
  const [loading, setLoading] = useState(false);

  const fetchHealth = useCallback(async () => {
    setLoading(true);
    try {
      const data = await get('/keys/status');
      const statusMap = data?.status_map || {};
      // Also try fetching market intelligence health
      let miHealth = {};
      try {
        miHealth = await get('/diagnostics/provider-health');
      } catch {
        // Provider health endpoint may not exist yet — that's fine
      }

      const merged = {};
      const allIds = [
        ...MARKET_DATA_PROVIDERS,
        ...INTELLIGENCE_ENRICHERS,
      ];
      for (const id of allIds) {
        const keyStatus = statusMap[id]?.status;
        const mi = miHealth?.[id];
        let status = 'unconfigured';
        if (keyStatus === 'configured_valid' || keyStatus === 'test_ok') status = 'healthy';
        else if (keyStatus === 'configured_invalid' || keyStatus === 'test_failed') status = 'down';
        else if (keyStatus === 'configured_untested' || keyStatus === 'saved_untested') status = 'degraded';
        else if (mi?.healthy) status = 'healthy';
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

  const healthyCount = Object.values(providerHealth).filter(h => h.status === 'healthy').length;
  const totalProviders = MARKET_DATA_PROVIDERS.length + INTELLIGENCE_ENRICHERS.length;
  const missingEnrichers = INTELLIGENCE_ENRICHERS.filter(id => {
    const h = providerHealth[id];
    return !h || h.status === 'unconfigured';
  });

  return (
    <div>
      {/* Summary header */}
      <div style={{ ...cardStyle, display: 'flex', alignItems: 'center', gap: 12 }}>
        <span style={{ fontSize: 26 }}>🧠</span>
        <div style={{ flex: 1 }}>
          <h3 style={{ margin: 0, fontSize: 16, fontWeight: 700, color: '#e2e8f0' }}>
            Market Intelligence
          </h3>
          <p style={{ margin: '2px 0 0', fontSize: 12, color: '#94a3b8' }}>
            Multi-provider data aggregation with automatic failover
          </p>
        </div>
        <div style={{ textAlign: 'right' }}>
          <div style={{ fontSize: 22, fontWeight: 700, color: healthyCount > 0 ? '#10b981' : '#ef4444' }}>
            {healthyCount}/{totalProviders}
          </div>
          <div style={{ fontSize: 10, color: '#64748b' }}>providers active</div>
        </div>
        {loading && <span style={{ fontSize: 12, color: '#94a3b8' }}>⟳</span>}
      </div>

      {/* Degraded warning */}
      {missingEnrichers.length > 0 && (
        <div style={{
          ...cardStyle,
          background: 'rgba(245,158,11,0.08)',
          border: '1px solid rgba(245,158,11,0.25)',
          padding: '10px 16px',
          fontSize: 12,
          color: '#f59e0b',
        }}>
          ⚠ Intelligence is operating in degraded mode. Missing enrichers:{' '}
          {missingEnrichers.map(id => PLATFORM_CONFIG[id]?.displayName || id).join(', ')}.
          Configure API keys in API Setup to unlock full capabilities.
        </div>
      )}

      {/* Market Data Providers */}
      <div style={cardStyle}>
        <h4 style={{ margin: '0 0 8px', fontSize: 13, fontWeight: 700, color: '#a5b4fc' }}>
          📈 Market Data Providers (Fallback Order)
        </h4>
        <p style={{ margin: '0 0 8px', fontSize: 11, color: '#64748b' }}>
          Primary → Secondary → Tertiary. System auto-rotates before quota exhaustion.
        </p>
        {MARKET_DATA_PROVIDERS.map(id => (
          <ProviderRow key={id} config={PLATFORM_CONFIG[id]} providerHealth={providerHealth} />
        ))}
      </div>

      {/* Intelligence Enrichers */}
      <div style={cardStyle}>
        <h4 style={{ margin: '0 0 8px', fontSize: 13, fontWeight: 700, color: '#a5b4fc' }}>
          🔍 Intelligence Enrichers
        </h4>
        <p style={{ margin: '0 0 8px', fontSize: 11, color: '#64748b' }}>
          Optional data sources for whale flow, sentiment, news, and on-chain analytics.
        </p>
        {INTELLIGENCE_ENRICHERS.map(id => (
          <ProviderRow key={id} config={PLATFORM_CONFIG[id]} providerHealth={providerHealth} />
        ))}
      </div>

      {/* Fallback architecture info */}
      <div style={{
        ...cardStyle,
        background: 'rgba(99,102,241,0.06)',
        border: '1px solid rgba(99,102,241,0.15)',
      }}>
        <h4 style={{ margin: '0 0 6px', fontSize: 13, fontWeight: 700, color: '#a5b4fc' }}>
          🔄 Fallback Architecture
        </h4>
        <div style={{ fontSize: 12, color: '#cbd5e1', lineHeight: 1.8 }}>
          <div>1️⃣ <strong>CryptoCompare</strong> — Primary (100k calls/month, 50 req/min)</div>
          <div>2️⃣ <strong>CoinGecko</strong> — Secondary (30 req/min, no daily cap)</div>
          <div>3️⃣ <strong>Coinranking</strong> — Tertiary (10k calls/month)</div>
          <div style={{ marginTop: 4, fontSize: 11, color: '#64748b' }}>
            Provider rotation triggers at 70% quota threshold. All data is normalized before use.
          </div>
        </div>
      </div>
    </div>
  );
};

export default MarketIntelligencePanel;
