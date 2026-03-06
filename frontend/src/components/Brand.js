/**
 * Brand component — renders "AmarktAI" with the "AI" in blue.
 * Usage: <Brand /> or <Brand size="lg" />
 */
export default function Brand({ size = 'md', className = '' }) {
  const fontSize = size === 'lg' ? '1.5rem' : size === 'sm' ? '0.875rem' : '1.125rem';
  return (
    <span className={className} style={{ fontWeight: 700, fontSize, letterSpacing: '-0.02em' }}>
      Amarkt<span style={{ color: '#3B82F6', fontWeight: 800 }}>AI</span>
    </span>
  );
}
