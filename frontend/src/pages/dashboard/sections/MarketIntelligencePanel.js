import React, { useState, useEffect } from 'react';
import apiClient from '@/lib/apiClient';

/**
 * Market Intelligence Panel
 *
 * Displays automatic CoinStats-based market intelligence.
 * No manual input required — intelligence updates on a background schedule.
 * Shows fetch_status and block_reason if data is unavailable.
 */
const MarketIntelligencePanel = () => {
  const [status, setStatus] = useState(null);
  const [latest, setLatest] = useState(null);
  const [loading, setLoading] = useState(true);

  const fetchIntelligence = async () => {
    try {
      const [statusRes, latestRes] = await Promise.all([
        apiClient.get('/intelligence/status'),
        apiClient.get('/intelligence/latest'),
      ]);
      setStatus(statusRes.data);
      setLatest(latestRes.data);
    } catch (err) {
      console.error('MarketIntelligencePanel: fetch error', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchIntelligence();
    const interval = setInterval(fetchIntelligence, 60000); // refresh every 60 s
    return () => clearInterval(interval);
  }, []);

  const moodColors = {
    positive: 'var(--success, #10b981)',
    negative: 'var(--error, #ef4444)',
    neutral: 'var(--warning, #f59e0b)',
  };

  const moodEmojis = { positive: '📈', negative: '📉', neutral: '➡️' };
  const mood = latest?.mood || 'neutral';
  const fetchStatus = latest?.fetch_status || status?.fetch_status || 'pending';
  const blockReason = latest?.block_reason || status?.block_reason;
  const hasRealData = fetchStatus === 'ok' && latest?.what_happened && !blockReason;

  const panelStyle = {
    padding: '16px',
    background: 'var(--glass, rgba(255,255,255,0.05))',
    border: '1px solid var(--line, rgba(255,255,255,0.1))',
    borderRadius: '10px',
    marginBottom: '12px',
  };

  const labelStyle = { fontSize: '0.78rem', color: 'var(--muted)', marginBottom: '4px' };
  const valueStyle = { fontSize: '0.95rem', color: 'var(--text)', lineHeight: '1.5' };

  if (loading) {
    return (
      <div style={panelStyle}>
        <div style={{ color: 'var(--muted)', fontSize: '0.9rem' }}>
          ⏳ Loading market intelligence…
        </div>
      </div>
    );
  }

  // Determine status label for footer
  const getStatusLabel = () => {
    if (fetchStatus === 'key_missing') return '⚠️ CoinStats API key not configured';
    if (fetchStatus === 'rate_limited') return '⚠️ CoinStats rate-limited';
    if (fetchStatus === 'invalid_key') return '⚠️ CoinStats API key rejected (401)';
    if (fetchStatus === 'error' && blockReason) return `⚠️ ${blockReason}`;
    if (fetchStatus === 'no_articles') return '⏳ Awaiting CoinStats data';
    if (fetchStatus === 'pending' || !status?.last_run_at) return '⏳ Fetching first update…';
    if (status?.last_run_at) return `Updated: ${new Date(status.last_run_at).toLocaleString()}`;
    return '⏳ Waiting for first fetch…';
  };

  return (
    <div style={panelStyle}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '12px' }}>
        <div style={{ fontWeight: 700, fontSize: '1rem', color: 'var(--text)' }}>
          🧠 Market Intelligence
        </div>
        <div style={{ fontSize: '0.78rem', color: hasRealData ? 'var(--success)' : 'var(--muted)' }}>
          {hasRealData ? '● Live' : '○ Pending'} · Source: {status?.source || 'CoinStats'}
        </div>
      </div>

      {/* What it does */}
      <div style={{ ...labelStyle, marginBottom: '10px', fontStyle: 'italic' }}>
        {status?.what_it_does || 'Automatically monitors CoinStats headlines and classifies market mood.'}
      </div>

      {/* Block reason banner — only show when data isn't fresh */}
      {!hasRealData && blockReason && (
        <div style={{
          padding: '8px 12px',
          background: 'rgba(239,68,68,0.08)',
          border: '1px solid rgba(239,68,68,0.2)',
          borderRadius: '6px',
          fontSize: '0.82rem',
          color: '#ef4444',
          marginBottom: '10px',
        }}>
          {fetchStatus === 'key_missing' ? '🔑' : '⚠️'} {blockReason}
        </div>
      )}

      {/* Fetching state */}
      {!hasRealData && !blockReason && (
        <div style={{ ...valueStyle, color: 'var(--muted)', marginBottom: '10px' }}>
          ⏳ Fetching market data from CoinStats…
        </div>
      )}

      {/* Mood — only show when we have real data */}
      {hasRealData && (
        <div style={{ marginBottom: '10px' }}>
          <div style={labelStyle}>Market Mood</div>
          <div style={{ ...valueStyle, color: moodColors[mood], fontWeight: 600 }}>
            {moodEmojis[mood]} {mood.charAt(0).toUpperCase() + mood.slice(1)}
          </div>
        </div>
      )}

      {/* Latest brief */}
      {hasRealData && latest?.what_happened && (
        <div style={{ marginBottom: '10px' }}>
          <div style={labelStyle}>Latest Headline</div>
          <div style={valueStyle}>{latest.what_happened}</div>
        </div>
      )}

      {/* Top risk */}
      {hasRealData && latest?.top_risk && latest.top_risk !== 'none' && (
        <div style={{ marginBottom: '10px' }}>
          <div style={labelStyle}>Risk Signal</div>
          <div style={{ ...valueStyle, color: 'var(--warning, #f59e0b)' }}>
            ⚠️ {latest.top_risk}
          </div>
        </div>
      )}

      {/* What AmarktAI Crypto is doing */}
      {hasRealData && latest?.what_amarktai_is_doing && (
        <div style={{ marginBottom: '10px' }}>
          <div style={labelStyle}>Platform Response</div>
          <div style={valueStyle}>{latest.what_amarktai_is_doing}</div>
        </div>
      )}

      {/* Footer: last updated */}
      <div style={{ marginTop: '12px', fontSize: '0.75rem', color: 'var(--muted)', display: 'flex', justifyContent: 'space-between' }}>
        <span>{getStatusLabel()}</span>
        {status?.next_run_in_seconds != null && hasRealData && (
          <span>Next run in ~{Math.ceil(status.next_run_in_seconds / 60)} min</span>
        )}
      </div>
    </div>
  );
};

export default MarketIntelligencePanel;
