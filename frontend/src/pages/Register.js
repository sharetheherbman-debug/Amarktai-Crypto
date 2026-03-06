import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Input } from '@/components/ui/input';
import { toast } from 'sonner';
import { Eye, EyeOff, ArrowLeft } from 'lucide-react';
import SiteFooter from '../components/SiteFooter';
import NeuralBackground from '../components/NeuralBackground';
import { post } from '@/lib/apiClient';
import './Auth.css';
import './Landing.css';

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

const STEP_LABELS = ['Your Name', 'Email', 'Password', 'Access Code'];

export default function Register() {
  const [step, setStep] = useState(1);
  const [showPassword, setShowPassword] = useState(false);
  const [showConfirm, setShowConfirm] = useState(false);
  const [showInvite, setShowInvite] = useState(false);
  const [formData, setFormData] = useState({
    first_name: '',
    email: '',
    password: '',
    confirmPassword: '',
    invite_code: '',
  });
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();

  const validateStep = () => {
    if (step === 1 && formData.first_name.length < 2) {
      toast.error('Name must be at least 2 characters');
      return false;
    }
    if (step === 2 && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(formData.email)) {
      toast.error('Please enter a valid email');
      return false;
    }
    if (step === 3 && formData.password.length < 6) {
      toast.error('Password must be at least 6 characters');
      return false;
    }
    if (step === 3 && formData.password !== formData.confirmPassword) {
      toast.error('Passwords do not match');
      return false;
    }
    if (step === 4 && !formData.invite_code) {
      toast.error('Access code is required');
      return false;
    }
    return true;
  };

  const handleNext = () => {
    if (validateStep()) {
      setStep(step + 1);
    }
  };

  const handleBack = () => {
    setStep(step - 1);
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!validateStep()) return;
    setLoading(true);
    try {
      const response = await post('/auth/register', {
        first_name: formData.first_name,
        email: formData.email,
        password: formData.password,
        invite_code: formData.invite_code,
      });
      localStorage.setItem('token', response.access_token);
      localStorage.setItem('user', JSON.stringify(response.user));
      toast.success('Account created successfully!');
      navigate('/dashboard');
    } catch (error) {
      toast.error(error.message || 'Registration failed');
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

          <h1 className="auth-title">Create Account</h1>
          <StepDots current={step} total={4} />
          <p className="step-hint">{STEP_LABELS[step - 1]}</p>

          <form onSubmit={handleSubmit} className="auth-form">
            {step === 1 && (
              <div className="form-step">
                <div className="field-group">
                  <label className="field-label">Full Name</label>
                  <Input
                    type="text"
                    value={formData.first_name}
                    onChange={(e) => setFormData({ ...formData, first_name: e.target.value })}
                    placeholder="Your full name"
                    required
                    className="auth-input"
                    data-testid="name-input"
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
                <div className="button-row">
                  <button type="button" onClick={handleBack} className="lp-btn lp-btn-ghost">
                    <ArrowLeft size={16} /> Back
                  </button>
                  <button type="button" onClick={handleNext} className="lp-btn lp-btn-primary btn-flex">
                    Continue
                  </button>
                </div>
              </div>
            )}

            {step === 3 && (
              <div className="form-step">
                <div className="field-group">
                  <label className="field-label">Password</label>
                  <div className="password-wrapper">
                    <Input
                      type={showPassword ? 'text' : 'password'}
                      value={formData.password}
                      onChange={(e) => setFormData({ ...formData, password: e.target.value })}
                      placeholder="Min. 6 characters"
                      required
                      className="auth-input"
                      data-testid="password-input"
                      autoFocus
                    />
                    <button type="button" onClick={() => setShowPassword(!showPassword)} className="eye-btn">
                      {showPassword ? <EyeOff size={18} /> : <Eye size={18} />}
                    </button>
                  </div>
                </div>
                <div className="field-group">
                  <label className="field-label">Confirm Password</label>
                  <div className="password-wrapper">
                    <Input
                      type={showConfirm ? 'text' : 'password'}
                      value={formData.confirmPassword}
                      onChange={(e) => setFormData({ ...formData, confirmPassword: e.target.value })}
                      placeholder="Repeat password"
                      required
                      className="auth-input"
                      data-testid="confirm-password-input"
                    />
                    <button type="button" onClick={() => setShowConfirm(!showConfirm)} className="eye-btn">
                      {showConfirm ? <EyeOff size={18} /> : <Eye size={18} />}
                    </button>
                  </div>
                </div>
                <div className="button-row">
                  <button type="button" onClick={handleBack} className="lp-btn lp-btn-ghost">
                    <ArrowLeft size={16} /> Back
                  </button>
                  <button type="button" onClick={handleNext} className="lp-btn lp-btn-primary btn-flex">
                    Continue
                  </button>
                </div>
              </div>
            )}

            {step === 4 && (
              <div className="form-step">
                <div className="field-group">
                  <div className="invite-header">
                    <label className="field-label">Exclusive Access Code</label>
                    <button type="button" onClick={() => setShowInvite(!showInvite)} className="show-toggle">
                      {showInvite ? 'Hide' : 'Show'}
                    </button>
                  </div>
                  <Input
                    type={showInvite ? 'text' : 'password'}
                    value={formData.invite_code}
                    onChange={(e) => setFormData({ ...formData, invite_code: e.target.value })}
                    placeholder="Enter access code"
                    required
                    className="auth-input"
                    data-testid="invite-code-input"
                    autoFocus
                  />
                  <p className="invite-hint">Only available to select members</p>
                </div>
                <div className="button-row">
                  <button type="button" onClick={handleBack} className="lp-btn lp-btn-ghost">
                    <ArrowLeft size={16} /> Back
                  </button>
                  <button
                    type="submit"
                    disabled={loading}
                    className="lp-btn lp-btn-primary btn-flex"
                    data-testid="submit-button"
                  >
                    {loading ? 'Creating…' : 'Create Account'}
                  </button>
                </div>
              </div>
            )}
          </form>

          <p className="auth-alt-link">
            Already have an account?{' '}
            <span onClick={() => navigate('/login')} className="link">Login</span>
          </p>
        </div>
      </div>

      <SiteFooter />
    </div>
  );
}

