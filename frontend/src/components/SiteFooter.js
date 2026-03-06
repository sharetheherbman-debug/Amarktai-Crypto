export default function SiteFooter() {
  const year = new Date().getFullYear();
  return (
    <footer className="site-footer">
      <span>© {year} Amarkt<span style={{ color: '#3B82F6', fontWeight: 700 }}>AI</span> Crypto — Part of Amarkt<span style={{ color: '#3B82F6', fontWeight: 700 }}>AI</span> Network — Personal use only.</span>
    </footer>
  );
}
