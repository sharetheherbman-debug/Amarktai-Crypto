import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { toast } from 'sonner';
import { Eye, EyeOff, ArrowLeft } from 'lucide-react';
import SiteFooter from '../components/SiteFooter';
import './Auth.css';
import './Landing.css';
import { post } from '../lib/apiClient';

export default function Login() {
  const [step, setStep] = useState(1);
  const [showPassword, setShowPassword] = useState(false);
  const [formData, setFormData] = useState({
    email: '',
    password: ''
  });
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
        password: formData.password
      });
      console.log('Login response:', response);
      
      // Clear all previous session data including chat
      localStorage.clear();
      sessionStorage.clear();
      
      // TASK B - Use access_token from standardized auth response
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
    <div className="auth-container">
      {/* Left Column - Content */}
      <div className="auth-left">
        <div className="auth-content">
          <img
            src="/assets/logo.png"
            alt="Amarktai Crypto"
            className="auth-logo landing-logo-lg"
            onClick={() => navigate('/')}
          />
          
          <h1 className="auth-title">Login</h1>
          <p className="auth-step" aria-label={`Step ${step} of 2: ${step === 1 ? 'Enter your email' : 'Enter your password'}`}>Step {step} of 2</p>

          <form onSubmit={handleSubmit} className="auth-form">
            {/* Step 1: Email */}
            {step === 1 && (
              <div className="form-step">
                <Input
                  type="email"
                  value={formData.email}
                  onChange={(e) => setFormData({ ...formData, email: e.target.value })}
                  placeholder="Email"
                  required
                  className="auth-input"
                  data-testid="email-input"
                  autoFocus
                />
                <Button
                  type="button"
                  onClick={handleNext}
                  className="auth-submit-btn"
                >
                  Next
                </Button>
              </div>
            )}

            {/* Step 2: Password */}
            {step === 2 && (
              <div className="form-step">
                <div className="password-wrapper">
                  <Input
                    type={showPassword ? 'text' : 'password'}
                    value={formData.password}
                    onChange={(e) => setFormData({ ...formData, password: e.target.value })}
                    placeholder="Password"
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

                <div className="button-row">
                  <Button
                    type="button"
                    onClick={handleBack}
                    className="auth-back-btn"
                    aria-label="Go back to email entry"
                  >
                    <ArrowLeft size={18} /> Back
                  </Button>
                  <Button
                    type="submit"
                    disabled={loading}
                    className="auth-submit-btn"
                    data-testid="submit-button"
                  >
                    {loading ? 'Logging in...' : 'Login'}
                  </Button>
                </div>
              </div>
            )}
          </form>

          <p className="auth-alt-link">
            Don't have an account?{' '}
            <span onClick={() => navigate('/register')} className="link">Register</span>
          </p>
        </div>
      </div>

      {/* Right Column - Video */}
      <div className="auth-right">
        <video
          autoPlay
          muted
          loop
          playsInline
          poster="/assets/poster.jpg"
        >
          <source src="/assets/background.mp4" type="video/mp4" />
        </video>
      </div>
      <SiteFooter />
    </div>
  );
}

