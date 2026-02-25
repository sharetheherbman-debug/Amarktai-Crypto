import PublicPageLayout from '../components/PublicPageLayout';

export default function About() {
  return (
    <PublicPageLayout
      title="About Amarktai Crypto"
      subtitle="Amarktai Crypto is the personal automation layer for disciplined, AI-assisted trading."
    >
      <p style={{ margin: 0, color: 'var(--muted)', lineHeight: 1.6 }}>
        Amarktai Crypto combines live exchange connectivity, smart automation, and transparent system status
        in a single glassmorphic workspace. Every action is backed by real APIs and real-time telemetry, so
        you always know what the system is doing.
      </p>
      <div className="glass-panel" style={{ padding: '16px', display: 'grid', gap: '8px' }}>
        <strong style={{ color: 'var(--text)' }}>Core principles</strong>
        <span style={{ color: 'var(--muted)' }}>• Clarity over hype</span>
        <span style={{ color: 'var(--muted)' }}>• Strict separation of paper vs live modes</span>
        <span style={{ color: 'var(--muted)' }}>• Premium UX without altering backend logic</span>
      </div>
    </PublicPageLayout>
  );
}
