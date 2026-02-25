import React from 'react';
import SectionHeader from '@/ui/components/SectionHeader';
import { apiClient } from '@/lib/apiClient';

const SENTIMENT_COLORS = {
  POSITIVE: 'var(--success)',
  NEGATIVE: 'var(--error)',
  NEUTRAL: 'var(--muted)',
};

const SentimentBadge = ({ label, score }) => {
  if (!label) return null;
  const color = SENTIMENT_COLORS[label?.toUpperCase()] || 'var(--muted)';
  return (
    <span style={{
      display: 'inline-block',
      padding: '2px 8px',
      borderRadius: '999px',
      fontSize: '0.75rem',
      fontWeight: 700,
      background: `${color}22`,
      color,
      border: `1px solid ${color}55`,
      marginLeft: '8px',
    }}>
      {label}{score != null ? ` ${(score * 100).toFixed(0)}%` : ''}
    </span>
  );
};

const FlokxSection = ({ showSection }) => {
  const [status, setStatus] = React.useState(null);
  const [articles, setArticles] = React.useState([]);
  const [loading, setLoading] = React.useState(false);
  const [error, setError] = React.useState(null);
  const [withSentiment, setWithSentiment] = React.useState(false);

  const load = React.useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [diagRes, feedRes] = await Promise.all([
        apiClient.get('/diagnostics/sentiment-news').catch(e => ({ data: { last_error: e.message } })),
        apiClient.get(`/news/feed?limit=20&with_sentiment=${withSentiment}`).catch(e => ({ data: { articles: [], error: e.message } })),
      ]);
      setStatus(diagRes.data);
      setArticles(feedRes.data?.articles || []);
    } catch (e) {
      setError(e.message || 'Failed to load news');
    } finally {
      setLoading(false);
    }
  }, [withSentiment]);

  React.useEffect(() => { load(); }, [load]);

  const configured = status?.configured !== false;
  const statusColor = configured && !status?.last_error ? 'var(--success)' : status?.last_error ? 'var(--warning)' : 'var(--muted)';

  return (
    <section className="section active">
      <div className="card">
        <SectionHeader
          title="📰 News &amp; Sentiment (CoinStats)"
          subtitle="Real-time crypto news with optional HuggingFace sentiment scoring"
        />

        {/* Status bar */}
        <div style={{
          display: 'flex', alignItems: 'center', gap: '12px', padding: '12px 16px',
          background: 'var(--glass)', borderRadius: '8px', marginBottom: '16px',
          fontSize: '0.85rem', flexWrap: 'wrap',
        }}>
          <span style={{ width: 10, height: 10, borderRadius: '50%', background: statusColor, flexShrink: 0 }} />
          <span style={{ color: 'var(--text)', fontWeight: 600 }}>
            CoinStats: {configured ? (status?.last_error ? 'Error' : 'Active') : 'Not configured (free tier)'}
          </span>
          {status?.articles_count > 0 && (
            <span style={{ color: 'var(--muted)' }}>{status.articles_count} articles cached</span>
          )}
          {status?.hf_configured && (
            <span style={{ color: 'var(--success)', fontSize: '0.8rem' }}>🤗 HF sentiment ready</span>
          )}
          {status?.last_error && (
            <span style={{ color: 'var(--warning)', fontSize: '0.8rem' }}>⚠ {status.last_error}</span>
          )}
          <div style={{ marginLeft: 'auto', display: 'flex', gap: '8px', alignItems: 'center' }}>
            <label style={{ fontSize: '0.8rem', color: 'var(--muted)', cursor: 'pointer', display: 'flex', gap: '6px', alignItems: 'center' }}>
              <input
                type="checkbox"
                checked={withSentiment}
                onChange={e => setWithSentiment(e.target.checked)}
                style={{ cursor: 'pointer' }}
              />
              HF Sentiment
            </label>
            <button
              onClick={load}
              disabled={loading}
              style={{
                padding: '4px 12px', borderRadius: '6px', border: '1px solid var(--line)',
                background: 'transparent', color: 'var(--text)', cursor: 'pointer', fontSize: '0.8rem',
              }}
            >
              {loading ? 'Loading…' : '↺ Refresh'}
            </button>
          </div>
        </div>

        {/* Key not configured hint */}
        {!status?.key_source || status?.key_source === 'none' ? (
          <div style={{
            padding: '12px 16px', background: 'rgba(59,130,246,0.08)',
            borderRadius: '8px', border: '1px solid rgba(59,130,246,0.3)',
            marginBottom: '16px', fontSize: '0.85rem', color: 'var(--muted)',
          }}>
            💡 Add a CoinStats API key in <strong style={{ color: 'var(--text)', cursor: 'pointer' }} onClick={() => showSection && showSection('api')}>API Setup</strong> to unlock higher rate limits and more articles.
          </div>
        ) : null}

        {/* Error */}
        {error && (
          <div style={{
            padding: '12px', background: 'var(--error-bg)', border: '1px solid var(--error)',
            borderRadius: '8px', color: 'var(--error)', fontSize: '0.9rem', marginBottom: '16px',
          }}>
            {error}
          </div>
        )}

        {/* Article list */}
        {articles.length > 0 ? (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
            {articles.map((art, i) => (
              <a
                key={art.id || i}
                href={art.url}
                target="_blank"
                rel="noopener noreferrer"
                style={{
                  padding: '10px 14px', background: 'var(--panel)', borderRadius: '6px',
                  border: '1px solid var(--line)', color: 'var(--text)', textDecoration: 'none',
                  display: 'flex', flexDirection: 'column', gap: '4px',
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', flexWrap: 'wrap' }}>
                  <span style={{ fontWeight: 500, flex: 1 }}>{art.title}</span>
                  <SentimentBadge label={art.sentiment_label} score={art.sentiment_score} />
                </div>
                <div style={{ fontSize: '0.78rem', color: 'var(--muted)', display: 'flex', gap: '12px' }}>
                  {art.source && <span>{art.source}</span>}
                  {art.published_at && <span>{new Date(art.published_at).toLocaleString()}</span>}
                  {art.hf_error && <span style={{ color: 'var(--warning)' }}>⚠ HF: {art.hf_error}</span>}
                </div>
              </a>
            ))}
          </div>
        ) : !loading && (
          <div style={{ padding: '32px', textAlign: 'center', color: 'var(--muted)' }}>
            {status?.last_error ? `News unavailable: ${status.last_error}` : 'No articles loaded yet. Click Refresh.'}
          </div>
        )}
      </div>
    </section>
  );
};

export default FlokxSection;
