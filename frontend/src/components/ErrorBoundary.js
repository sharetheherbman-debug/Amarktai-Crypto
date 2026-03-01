import React from 'react';

/**
 * ErrorBoundary Component
 * Catches JavaScript errors anywhere in the child component tree.
 * Shows a diagnostic panel with "Copy Diagnostics" so engineers can
 * quickly identify and report the exact crash without guessing.
 */
class ErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = {
      hasError: false,
      error: null,
      errorInfo: null,
      copied: false,
    };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true };
  }

  componentDidCatch(error, errorInfo) {
    // Always log – visible in browser console and server-side log aggregators
    console.error('[ErrorBoundary] Caught:', error, errorInfo);
    this.setState({ error, errorInfo });
  }

  handleRetry = () => {
    this.setState({ hasError: false, error: null, errorInfo: null, copied: false });
  };

  buildDiagnostics = () => {
    const { error, errorInfo } = this.state;
    const wsStatus = (() => {
      try {
        const rc = window.__realtimeClient;
        return rc ? (rc.connected ? 'connected' : 'disconnected') : 'unknown';
      } catch { return 'unknown'; }
    })();
    return JSON.stringify({
      timestamp: new Date().toISOString(),
      buildVersion: process.env.REACT_APP_VERSION || 'unknown',
      buildSha: process.env.REACT_APP_BUILD_SHA || 'unknown',
      component: this.props.title || 'unknown',
      error: error ? error.toString() : null,
      componentStack: errorInfo ? errorInfo.componentStack : null,
      wsStatus,
      url: window.location.href,
      userAgent: navigator.userAgent,
    }, null, 2);
  };

  handleCopyDiagnostics = () => {
    try {
      navigator.clipboard.writeText(this.buildDiagnostics()).then(() => {
        this.setState({ copied: true });
        setTimeout(() => this.setState({ copied: false }), 2500);
      });
    } catch {
      // Fallback for non-secure contexts
      const ta = document.createElement('textarea');
      ta.value = this.buildDiagnostics();
      document.body.appendChild(ta);
      ta.select();
      document.execCommand('copy');
      document.body.removeChild(ta);
      this.setState({ copied: true });
      setTimeout(() => this.setState({ copied: false }), 2500);
    }
  };

  render() {
    if (!this.state.hasError) {
      return this.props.children;
    }

    const { error, errorInfo, copied } = this.state;
    const showDetails = !!(error || errorInfo);

    return (
      <div style={{
        padding: '28px 24px',
        background: 'var(--panel, rgba(14,24,52,0.85))',
        border: '1px solid var(--error, #ef4444)',
        borderRadius: 'var(--radius-md, 14px)',
        maxWidth: '640px',
        margin: '32px auto',
        textAlign: 'center',
        fontFamily: 'Inter, sans-serif',
      }}>
        <div style={{ fontSize: '2rem', marginBottom: '12px' }}>⚠️</div>

        <h3 style={{ color: 'var(--error, #ef4444)', marginBottom: '8px', fontSize: '1.1rem', fontWeight: 700 }}>
          {this.props.title || 'Something went wrong'}
        </h3>

        <p style={{ color: 'var(--muted, #94a3b8)', marginBottom: '20px', fontSize: '0.9rem', lineHeight: 1.5 }}>
          {this.props.message || "This section encountered an error and couldn't load."}
        </p>

        {showDetails && (
          <details style={{
            marginBottom: '20px',
            padding: '12px 14px',
            background: 'rgba(0,0,0,0.35)',
            borderRadius: '8px',
            textAlign: 'left',
            fontSize: '0.8rem',
            color: 'var(--muted, #94a3b8)',
            border: '1px solid rgba(255,255,255,0.08)',
          }}>
            <summary style={{ cursor: 'pointer', fontWeight: 600, marginBottom: '8px', color: 'var(--text, #f8fbff)' }}>
              Error Details
            </summary>
            <pre style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-all', maxHeight: '200px', overflow: 'auto', margin: 0 }}>
              {error ? error.toString() : ''}
              {errorInfo ? errorInfo.componentStack : ''}
            </pre>
          </details>
        )}

        <div style={{ display: 'flex', gap: '10px', justifyContent: 'center', flexWrap: 'wrap' }}>
          <button
            onClick={this.handleRetry}
            style={{
              padding: '10px 20px',
              background: 'var(--accent, #22c55e)',
              color: '#fff',
              border: 'none',
              borderRadius: '8px',
              cursor: 'pointer',
              fontWeight: 600,
              fontSize: '0.875rem',
            }}
          >
            🔄 Try Again
          </button>

          {showDetails && (
            <button
              onClick={this.handleCopyDiagnostics}
              style={{
                padding: '10px 20px',
                background: copied ? 'var(--accent2, #60a5fa)' : 'rgba(255,255,255,0.08)',
                color: 'var(--text, #f8fbff)',
                border: '1px solid rgba(255,255,255,0.15)',
                borderRadius: '8px',
                cursor: 'pointer',
                fontWeight: 600,
                fontSize: '0.875rem',
                transition: 'background 0.2s',
              }}
            >
              {copied ? '✅ Copied!' : '📋 Copy Diagnostics'}
            </button>
          )}
        </div>
      </div>
    );
  }
}

export default ErrorBoundary;
