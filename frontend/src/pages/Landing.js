import { useNavigate } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import AuthLayout from '../components/AuthLayout';

export default function Landing() {
  const navigate = useNavigate();

  return (
    <AuthLayout>
      <div className="auth-content bright-glass-panel">
        <img
          src="/assets/ai/ai-orb.svg"
          alt="AmarktAI"
          className="auth-logo landing-logo-lg"
        />
        <div className="landing-header">
          <p className="landing-welcome">Welcome to</p>
          <h1 className="auth-title landing-brand">
            Amarkt<span className="brand-ai">AI</span> Crypto
          </h1>
        </div>
        <p className="landing-summary">
          Advanced AI-Powered Trading Platform<br />
          Real-Time Intelligence • Autonomous Decision-Making • 24/7 Market Analysis
        </p>
        <div className="landing-cta">
          <Button onClick={() => navigate('/login')} className="auth-submit-btn landing-cta-btn">Login</Button>
          <Button onClick={() => navigate('/register')} className="auth-submit-btn landing-cta-btn landing-register-btn">Register</Button>
        </div>
      </div>
    </AuthLayout>
  );
}
