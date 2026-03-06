import { useNavigate } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import SiteFooter from '../components/SiteFooter';
import Brand from '../components/Brand';
import NeuralBackground from '../components/NeuralBackground';
import './Auth.css';
import './Landing.css';

export default function Landing() {
  const navigate = useNavigate();

  return (
    <div className="neural-page">
      <NeuralBackground />

      <div className="neural-center">
        <img
          src="/assets/logo.png"
          alt="Amarktai Crypto"
          className="landing-logo-hero logo-float"
        />
        <h1 className="landing-headline">
          <Brand size="lg" />
          {' '}Crypto
        </h1>
        <p className="landing-subheadline">Autonomous AI Trading Intelligence</p>
        <p className="landing-subheadline-2">Self-Learning. Self-Healing. Fully Autonomous.</p>
        <div className="landing-cta">
          <Button
            onClick={() => navigate('/login')}
            className="auth-submit-btn landing-cta-btn landing-primary-btn"
          >
            Login
          </Button>
          <Button
            onClick={() => navigate('/register')}
            className="auth-submit-btn landing-cta-btn landing-register-btn"
          >
            Create Account
          </Button>
        </div>
      </div>

      <SiteFooter />
    </div>
  );
}
