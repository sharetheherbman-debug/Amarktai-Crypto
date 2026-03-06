import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Input } from '@/components/ui/input';
import { toast } from 'sonner';
import { Eye, EyeOff, ArrowLeft } from 'lucide-react';
import SiteFooter from '../components/SiteFooter';
import NeuralBackground from '../components/NeuralBackground';
import './Auth.css';
import './Landing.css';
import { post } from '../lib/apiClient';

function StepDots({ current, total }) {
  return (
    <div className="step-dots" aria-label={`Step ${current} of ${total}`}>
      {Array.from({ length: total }, (_, i) => (
        <span
          key={i}
          className={`step-dot${i + 1 < current ? ' done' : i + 1 === current ? ' active' : ''}`}
        />
      ))}
    </div>
  );
}

export default function Login() {
  const [step, setStep] = useState(1);
  const [showPassword, setShowPassword] = useState(false);
  const [formData, setFormData] = useState({ email: '', password: '' });
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();

  const validateStep = () => {
    if (step === 1 && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(formData.email)) {
      toast.error('Please enter a valid email');
      return false;
    }
    if (step === 2 && !formData.password) {
      toast.error('Please enter your password');
      return false;
    }
    return true;
  };

  const handleNext = () => {
    if (validateStep()) {
      setStep(2);
    }
  };

  const handleBack = () => {
    setStep(1);
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!validateStep()) return;
    setLoading(true);
    try {
      const response = await post('/auth/login', {
        email: formData.email,
        password: formData.password,
      });
      console.log('Login response:', response);
      localStorage.clear();
      sessionStorage.clear();
      localStorage.setItem('token', response.access_token);
      localStorage.setItem('user', JSON.stringify(response.user));
      toast.success('Welcome back!');
      navigate('/dashboard');
    } catch (error) {
      console.error('Login error:', error);
      toast.error(error.message || 'Login failed. Please check your credentials.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="neural-page">
      <NeuralBackground />
      <div className="neural-vignette" aria-hidden="true" />

      <div className="neural-center">
        <div className="neural-card">
          <img
            src="/assets/logo.png"
            alt="Amarktai Crypto"
            className="card-logo logo-float"
            onClick={() => navigate('/')}
          />

          <div className="card-brand" onClick={() => navigate('/')}>
            Amarkt<span className="wordmark-ai">AI</span> Crypto
          </div>

          <h1 className="auth-title">Welcome Back</h1>
          <StepDots current={step} total={2} />

          <form onSubmit={handleSubmit} className="auth-form">
            {step === 1 && (
              <div className="form-step">
                <div className="field-group">
                  <label className="field-label">Email address</label>
                  <Input
                    type="email"
                    value={formData.email}
                    onChange={(e) => setFormData({ ...formData, email: e.target.value })}
                    placeholder="you@example.com"
                    required
                    className="auth-input"
                    data-testid="email-input"
                    autoFocus
                  />
                </div>
                <button type="button" onClick={handleNext} className="lp-btn lp-btn-primary btn-full">
                  Continue
                </button>
              </div>
            )}

            {step === 2 && (
              <div className="form-step">
                <div className="field-group">
                  <label className="field-label">Password</label>
                  <div className="password-wrapper">
                    <Input
                      type={showPassword ? 'text' : 'password'}
                      value={formData.password}
                      onChange={(e) => setFormData({ ...formData, password: e.target.value })}
                      placeholder="••••••••"
                      required
                      className="auth-input"
                      data-testid="password-input"
                      autoFocus
                    />
                    <button
                      type="button"
                      onClick={() => setShowPassword(!showPassword)}
                      className="eye-btn"
                    >
                      {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
                    </button>
                  </div>
                </div>
                <div className="button-row">
                  <button
                    type="button"
                    onClick={handleBack}
                    className="lp-btn lp-btn-ghost"
                    aria-label="Go back to email entry"
                  >
                    <ArrowLeft size={16} /> Back
                  </button>
                  <button
                    type="submit"
                    disabled={loading}
                    className="lp-btn lp-btn-primary btn-flex"
                  data-testid="submit-button"
                  >
                    {loading ? 'Signing in…' : 'Login'}
                  </button>
                </div>
              </div>
            )}
          </form>

          <p className="auth-alt-link">
            No account?{' '}
            <span onClick={() => navigate('/register')} className="link">Create one</span>
          </p>
        </div>
      </div>

      <SiteFooter />
    </div>
  );
}

