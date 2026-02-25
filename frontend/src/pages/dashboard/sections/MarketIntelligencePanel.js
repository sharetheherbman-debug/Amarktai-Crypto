import React, { useState, useEffect } from 'react';
import apiClient from '@/lib/apiClient';

/**
 * Market Intelligence Panel
 *
 * Displays automatic CoinStats-based market intelligence.
 * No manual input required — intelligence updates on a background schedule.
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
          Loading market intelligence…
        </div>
      </div>
    );
  }

  return (
    <div style={panelStyle}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '12px' }}>
        <div style={{ fontWeight: 700, fontSize: '1rem', color: 'var(--text)' }}>
          🧠 Market Intelligence
        </div>
        <div style={{ fontSize: '0.78rem', color: status?.running ? 'var(--success)' : 'var(--muted)' }}>
          {status?.running ? '● Live' : '○ Offline'} · Source: {status?.source || 'CoinStats'}
        </div>
      </div>

      {/* What it does */}
      <div style={{ ...labelStyle, marginBottom: '10px', fontStyle: 'italic' }}>
        {status?.what_it_does || 'Automatically monitors CoinStats headlines and classifies market mood.'}
      </div>

      {/* Mood */}
      <div style={{ marginBottom: '10px' }}>
        <div style={labelStyle}>Market Mood</div>
        <div style={{ ...valueStyle, color: moodColors[mood], fontWeight: 600 }}>
          {moodEmojis[mood]} {mood.charAt(0).toUpperCase() + mood.slice(1)}
        </div>
      </div>

      {/* Latest brief */}
      {latest?.what_happened && (
        <div style={{ marginBottom: '10px' }}>
          <div style={labelStyle}>Latest Headline</div>
          <div style={valueStyle}>{latest.what_happened}</div>
        </div>
      )}

      {/* Top risk */}
      {latest?.top_risk && latest.top_risk !== 'none' && (
        <div style={{ marginBottom: '10px' }}>
          <div style={labelStyle}>Risk Signal</div>
          <div style={{ ...valueStyle, color: 'var(--warning, #f59e0b)' }}>
            ⚠️ {latest.top_risk}
          </div>
        </div>
      )}

      {/* What Amarktai is doing */}
      {latest?.what_amarktai_is_doing && (
        <div style={{ marginBottom: '10px' }}>
          <div style={labelStyle}>Platform Response</div>
          <div style={valueStyle}>{latest.what_amarktai_is_doing}</div>
        </div>
      )}

      {/* Footer: last updated */}
      <div style={{ marginTop: '12px', fontSize: '0.75rem', color: 'var(--muted)', display: 'flex', justifyContent: 'space-between' }}>
        <span>
          {status?.last_run_at
            ? `Updated: ${new Date(status.last_run_at).toLocaleString()}`
            : 'Not yet updated — runs every 15 minutes'}
        </span>
        {status?.next_run_in_seconds != null && (
          <span>Next run in ~{Math.ceil(status.next_run_in_seconds / 60)} min</span>
        )}
      </div>
    </div>
  );
};

export default MarketIntelligencePanel;
