import PublicNav from './PublicNav';

export default function PublicPageLayout({ title, subtitle, children }) {
  return (
    <div className="public-page">
      <PublicNav />
      <div className="page-inner">
        <div className="section-header">
          <h1>{title}</h1>
          {subtitle && <p>{subtitle}</p>}
        </div>
        <div className="glass-panel" style={{ padding: '28px', display: 'grid', gap: '20px' }}>
          {children}
        </div>
      </div>
    </div>
  );
}
