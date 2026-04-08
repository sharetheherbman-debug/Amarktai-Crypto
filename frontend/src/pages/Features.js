import PublicPageLayout from '../components/PublicPageLayout';

export default function Features() {
  const items = [
    {
      title: 'Autonomous Strategy Engine',
      body: 'Adaptive bots monitor risk, rebalance capital, and keep your portfolio aligned with your profile.'
    },
    {
      title: 'Real-time Market Intelligence',
      body: 'Streaming trade data, market intelligence, and AI summaries surface high-impact signals fast.'
    },
    {
      title: 'Secure API Orchestration',
      body: 'Encrypted key vaults with testing tools and audit trails keep every provider connection safe.'
    }
  ];

  return (
    <PublicPageLayout
      title="Platform Features"
      subtitle="Premium glass tooling built for disciplined, automated trading."
    >
      <div style={{ display: 'grid', gap: '16px' }}>
        {items.map((item) => (
          <div key={item.title} className="glass-panel" style={{ padding: '18px' }}>
            <h3 style={{ margin: 0, color: 'var(--text)' }}>{item.title}</h3>
            <p style={{ margin: '8px 0 0', color: 'var(--muted)' }}>{item.body}</p>
          </div>
        ))}
      </div>
      <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
        <img src="/assets/logo.png" alt="" style={{ width: 160, opacity: 0.7 }} />
      </div>
    </PublicPageLayout>
  );
}
