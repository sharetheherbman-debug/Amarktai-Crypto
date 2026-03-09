export default function SiteFooter() {
  const year = new Date().getFullYear();
  const buildSha = process.env.REACT_APP_BUILD_SHA || 'unknown';
  const buildTag = process.env.REACT_APP_VERSION_TAG || 'unknown';
  const buildTimestamp = process.env.REACT_APP_BUILD_TIMESTAMP || process.env.REACT_APP_BUILD_TIME || 'unknown';
  const buildLabel = buildSha === 'unknown' ? 'unknown' : buildSha.slice(0, 8);
  const tagLabel = buildTag === 'unknown' ? 'untagged' : buildTag;
  return (
    <footer className="site-footer">
      <span>© {year} Amarkt<span style={{ color: '#3B82F6', fontWeight: 700 }}>AI</span> Crypto — Part of Amarkt<span style={{ color: '#3B82F6', fontWeight: 700 }}>AI</span> Network — Personal use only.</span>
      <span style={{ marginLeft: '10px', opacity: 0.8 }}>
        Build {buildLabel} · Tag {tagLabel} · {buildTimestamp}
      </span>
    </footer>
  );
}
