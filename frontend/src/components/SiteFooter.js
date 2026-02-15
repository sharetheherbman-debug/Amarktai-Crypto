export default function SiteFooter() {
  const year = new Date().getFullYear();
  return (
    <footer className="site-footer">
      © {year} Amarktai Crypto — Part of Amarktai Network
    </footer>
  );
}
