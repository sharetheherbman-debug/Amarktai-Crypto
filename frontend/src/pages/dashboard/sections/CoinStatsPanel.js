import React, { useState, useEffect } from 'react';

const API = process.env.REACT_APP_API_URL || '';

const CoinStatsPanel = ({ axiosConfig }) => {
  const [status, setStatus] = useState({ configured: false, reachable: false });
  const [news, setNews] = useState([]);
  const [tickers, setTickers] = useState([]);
  const [tab, setTab] = useState('news');
  const [loading, setLoading] = useState(false);

  const headers = axiosConfig?.headers || {};

  useEffect(() => {
    loadStatus();
    const interval = setInterval(loadStatus, 60000);
    return () => clearInterval(interval);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (status.configured) {
      if (tab === 'news') loadNews();
      if (tab === 'markets') loadMarkets();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [status.configured, tab]);

  const loadStatus = async () => {
    try {
      const res = await fetch(`${API}/api/coinstats/status`, { headers });
      if (res.ok) setStatus(await res.json());
    } catch { /* ignore */ }
  };

  const loadNews = async () => {
    setLoading(true);
    try {
      const res = await fetch(`${API}/api/coinstats/news`, { headers });
      if (res.ok) {
        const data = await res.json();
        setNews(data?.news || []);
      }
    } catch { setNews([]); }
    setLoading(false);
  };

  const loadMarkets = async () => {
    setLoading(true);
    try {
      const res = await fetch(`${API}/api/coinstats/markets`, { headers });
      if (res.ok) {
        const data = await res.json();
        setTickers(data?.tickers || []);
      }
    } catch { setTickers([]); }
    setLoading(false);
  };

  return (
    <div style={{
      background: 'rgba(15,23,42,0.7)',
      backdropFilter: 'blur(12px)',
      border: '1px solid rgba(99,102,241,0.25)',
      borderRadius: 12,
      padding: 20,
      marginBottom: 16
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 14 }}>
        <span style={{ fontSize: 22 }}>📊</span>
        <h3 style={{ margin: 0, fontSize: 16, fontWeight: 700, color: '#e2e8f0' }}>CoinStats Intelligence</h3>
        <span style={{
          marginLeft: 'auto',
          padding: '2px 10px',
          borderRadius: 20,
          fontSize: 11,
          fontWeight: 600,
          background: status.reachable ? 'rgba(16,185,129,0.15)' : 'rgba(239,68,68,0.15)',
          color: status.reachable ? '#10b981' : '#ef4444',
          border: `1px solid ${status.reachable ? 'rgba(16,185,129,0.3)' : 'rgba(239,68,68,0.3)'}`,
        }}>
          {status.reachable ? '● Connected' : status.configured ? '○ Unreachable' : '○ Not configured'}
        </span>
      </div>

      {!status.configured && (
        <p style={{ color: '#94a3b8', fontSize: 13 }}>
          Configure your CoinStats API key in API Setup to enable market intelligence.
        </p>
      )}

      {status.configured && (
        <>
          <div style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
            {['news', 'markets'].map(t => (
              <button key={t} onClick={() => setTab(t)} style={{
                padding: '5px 14px',
                borderRadius: 6,
                border: 'none',
                fontSize: 12,
                fontWeight: 600,
                cursor: 'pointer',
                background: tab === t ? 'rgba(99,102,241,0.3)' : 'rgba(30,41,59,0.5)',
                color: tab === t ? '#a5b4fc' : '#94a3b8',
              }}>
                {t === 'news' ? '📰 News' : '💹 Markets'}
              </button>
            ))}
          </div>

          {loading && <p style={{ color: '#94a3b8', fontSize: 12 }}>Loading…</p>}

          {!loading && tab === 'news' && (
            <div style={{ maxHeight: 300, overflowY: 'auto' }}>
              {news.length === 0 && <p style={{ color: '#64748b', fontSize: 12 }}>No news available</p>}
              {news.map((item, i) => (
                <div key={i} style={{
                  padding: '8px 0',
                  borderBottom: '1px solid rgba(51,65,85,0.4)',
                  fontSize: 12,
                  color: '#cbd5e1',
                }}>
                  <a href={item.url} target="_blank" rel="noopener noreferrer"
                    style={{ color: '#a5b4fc', textDecoration: 'none', fontWeight: 600 }}>
                    {item.title}
                  </a>
                  <div style={{ color: '#64748b', fontSize: 11, marginTop: 2 }}>
                    {item.source} · {item.published_at ? new Date(item.published_at).toLocaleString() : ''}
                  </div>
                </div>
              ))}
            </div>
          )}

          {!loading && tab === 'markets' && (
            <div style={{ maxHeight: 300, overflowY: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
                <thead>
                  <tr style={{ color: '#64748b', textAlign: 'left' }}>
                    <th style={{ padding: '4px 8px' }}>#</th>
                    <th style={{ padding: '4px 8px' }}>Symbol</th>
                    <th style={{ padding: '4px 8px' }}>Price</th>
                    <th style={{ padding: '4px 8px' }}>24h</th>
                  </tr>
                </thead>
                <tbody>
                  {tickers.map((t, i) => (
                    <tr key={i} style={{ borderBottom: '1px solid rgba(51,65,85,0.3)' }}>
                      <td style={{ padding: '4px 8px', color: '#94a3b8' }}>{t.rank}</td>
                      <td style={{ padding: '4px 8px', fontWeight: 600, color: '#e2e8f0' }}>{t.symbol}</td>
                      <td style={{ padding: '4px 8px', color: '#cbd5e1' }}>${Number(t.price).toLocaleString(undefined, { maximumFractionDigits: 2 })}</td>
                      <td style={{ padding: '4px 8px', color: t.price_change_24h >= 0 ? '#10b981' : '#ef4444' }}>
                        {t.price_change_24h >= 0 ? '+' : ''}{Number(t.price_change_24h).toFixed(2)}%
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </div>
  );
};

export default CoinStatsPanel;
