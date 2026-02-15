export default function SiteFooter() {
  const year = new Date().getFullYear();
  return (
    <footer className="site-footer">
      © {year} Amarktai Crypto — part of Amarktai Network
    </footer>
  );
}
