import { useNavigate } from 'react-router-dom';
import { Brain, Network, Zap } from 'lucide-react';
import SiteFooter from '../components/SiteFooter';
import NeuralBackground from '../components/NeuralBackground';
import './Auth.css';
import './Landing.css';

const FEATURES = [
  {
    Icon: Brain,
    title: 'Neural AI Core',
    desc: 'Self-learning models analyse thousands of market signals per second, adapting to every shift in real time.',
  },
  {
    Icon: Network,
    title: 'Multi-Exchange Engine',
    desc: 'Simultaneously active across 7 major exchanges — Binance, Bybit, Kraken, KuCoin, Gate, Bitget & Luno.',
  },
  {
    Icon: Zap,
    title: 'Fully Autonomous',
    desc: '24/7 self-healing system that opens, manages and closes positions without any manual input. Ever.',
  },
];

const STATS = [
  { value: '7',    label: 'Exchanges' },
  { value: '4',    label: 'AI Providers' },
  { value: '24/7', label: 'Autonomous' },
  { value: '∞',    label: 'Scalable' },
];

export default function Landing() {
  const navigate = useNavigate();

  return (
    <div className="neural-page landing-page">
      <NeuralBackground />
      <div className="neural-vignette" aria-hidden="true" />

      {/* ── Hero ─────────────────────────────────── */}
      <section className="landing-hero">
        <div className="landing-badge">
          <span className="badge-dot" aria-hidden="true" />
          LIVE AI TRADING SYSTEM
        </div>

        <img
          src="/assets/logo.png"
          alt="Amarktai"
          className="landing-logo-hero logo-float"
        />

        <div className="landing-wordmark">
          <div className="wordmark-line1">
            Amarkt<span className="wordmark-ai">AI</span>
          </div>
          <div className="wordmark-line2">Crypto</div>
        </div>

        <p className="landing-tagline">Autonomous AI Trading Intelligence</p>
        <p className="landing-tagline-sub">
          Self‑Learning &nbsp;·&nbsp; Self‑Healing &nbsp;·&nbsp; Fully Autonomous
        </p>

        <div className="landing-cta">
          <button onClick={() => navigate('/login')} className="lp-btn lp-btn-primary">
            Enter Platform
          </button>
          <button onClick={() => navigate('/register')} className="lp-btn lp-btn-outline">
            Create Account
          </button>
        </div>
      </section>

      {/* ── Stats Bar ────────────────────────────── */}
      <section className="landing-stats" aria-label="Platform statistics">
        {STATS.map((s) => (
          <div key={s.label} className="stat-item">
            <span className="stat-value">{s.value}</span>
            <span className="stat-label">{s.label}</span>
          </div>
        ))}
      </section>

      {/* ── Feature Cards ────────────────────────── */}
      <section className="landing-features" aria-label="Platform features">
        {FEATURES.map(({ Icon, title, desc }) => (
          <div key={title} className="feature-card">
            <div className="feature-icon-wrap" aria-hidden="true">
              <Icon size={26} strokeWidth={1.5} />
            </div>
            <h3 className="feature-title">{title}</h3>
            <p className="feature-desc">{desc}</p>
          </div>
        ))}
      </section>

      <SiteFooter />
    </div>
  );
}

