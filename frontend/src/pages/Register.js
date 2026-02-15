import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { toast } from 'sonner';
import { Eye, EyeOff, ArrowLeft } from 'lucide-react';
import { post } from '@/lib/apiClient';
import './Auth.css';

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
    invite_code: ''
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
        invite_code: formData.invite_code
      });
      
      // TASK B - Use access_token from standardized auth response
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
    <div className="auth-container">
      {/* Left Column - Content */}
      <div className="auth-left">
        <div className="auth-content bright-glass-panel">
          <img
            src="/assets/logo.png"
            alt="Amarktai Crypto"
            className="auth-logo"
            onClick={() => navigate('/')}
          />
          
          <h1 className="auth-title">Create Account</h1>
          <p className="auth-step">Step {step} of 4</p>

          <form onSubmit={handleSubmit} className="auth-form">
            {/* Step 1: Name */}
            {step === 1 && (
              <div className="form-step">
                <Input
                  type="text"
                  value={formData.first_name}
                  onChange={(e) => setFormData({ ...formData, first_name: e.target.value })}
                  placeholder="Full Name"
                  required
                  className="auth-input"
                  data-testid="name-input"
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

            {/* Step 2: Email */}
            {step === 2 && (
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
                <div className="button-row">
                  <Button
                    type="button"
                    onClick={handleBack}
                    className="auth-back-btn"
                  >
                    <ArrowLeft size={18} /> Back
                  </Button>
                  <Button
                    type="button"
                    onClick={handleNext}
                    className="auth-submit-btn"
                  >
                    Next
                  </Button>
                </div>
              </div>
            )}

            {/* Step 3: Password */}
            {step === 3 && (
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

                <div className="password-wrapper">
                  <Input
                    type={showConfirm ? 'text' : 'password'}
                    value={formData.confirmPassword}
                    onChange={(e) => setFormData({ ...formData, confirmPassword: e.target.value })}
                    placeholder="Confirm Password"
                    required
                    className="auth-input"
                    data-testid="confirm-password-input"
                  />
                  <button
                    type="button"
                    onClick={() => setShowConfirm(!showConfirm)}
                    className="eye-btn"
                  >
                    {showConfirm ? <EyeOff size={18} /> : <Eye size={18} />}
                  </button>
                </div>

                <div className="button-row">
                  <Button
                    type="button"
                    onClick={handleBack}
                    className="auth-back-btn"
                  >
                    <ArrowLeft size={18} /> Back
                  </Button>
                  <Button
                    type="button"
                    onClick={handleNext}
                    className="auth-submit-btn"
                  >
                    Next
                  </Button>
                </div>
              </div>
            )}

            {/* Step 4: Invite Code */}
            {step === 4 && (
              <div className="form-step">
                <div className="invite-header">
                  <label className="invite-label">Exclusive Access Code</label>
                  <button
                    type="button"
                    onClick={() => setShowInvite(!showInvite)}
                    className="show-toggle"
                  >
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

                <div className="button-row">
                  <Button
                    type="button"
                    onClick={handleBack}
                    className="auth-back-btn"
                  >
                    <ArrowLeft size={18} /> Back
                  </Button>
                  <Button
                    type="submit"
                    disabled={loading}
                    className="auth-submit-btn"
                    data-testid="submit-button"
                  >
                    {loading ? 'Creating...' : 'Create Account'}
                  </Button>
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
        <div className="auth-overlay" />
      </div>
    </div>
  );
}
