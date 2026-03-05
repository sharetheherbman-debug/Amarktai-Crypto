export default function SiteFooter() {
  const buildSha = process.env.REACT_APP_BUILD_SHA || 'dev';
  return (
    <footer className="site-footer">
      <span>Amarkt<span style={{ color: '#6366f1', fontWeight: 700 }}>AI</span> Crypto — Part of Amarkt<span style={{ color: '#6366f1', fontWeight: 700 }}>AI</span> Network — Personal use only.</span>
      <span style={{ fontSize: '0.7rem', opacity: 0.5, marginLeft: 12 }}>Build: {buildSha.slice(0, 8)}</span>
    </footer>
  );
}
