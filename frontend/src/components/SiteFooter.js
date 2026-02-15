export default function SiteFooter() {
  const year = new Date().getFullYear();
  return (
    <footer className="site-footer">
      © {year} Part of Amarktai Network — For personal use only.
    </footer>
  );
}
