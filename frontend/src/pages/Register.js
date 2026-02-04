import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { toast } from 'sonner';
import { Eye, EyeOff, ArrowLeft } from 'lucide-react';
import { API_BASE } from '@/lib/api';

const API = API_BASE;

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
      const response = await axios.post(`${API}/auth/register`, {
        first_name: formData.first_name,
        email: formData.email,
        password: formData.password,
        invite_code: formData.invite_code
      });
      
      localStorage.setItem('token', response.data.token);
      localStorage.setItem('user', JSON.stringify(response.data.user));
      toast.success('Account created successfully!');
      navigate('/dashboard');
    } catch (error) {
      toast.error(error.response?.data?.detail || 'Registration failed');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="auth-container">
      {/* Left Column - Content */}
      <div className="left">
        <div className="content">
          <img
            src="/assets/logo.png"
            alt="Amarktai Logo"
            className="logo"
            onClick={() => navigate('/')}
          />
          
          <h1>Create Account</h1>
          <p className="step-indicator">Step {step} of 4</p>

          <form onSubmit={handleSubmit} className="form">
            {/* Step 1: Name */}
            {step === 1 && (
              <div className="form-step">
                <Input
                  type="text"
                  value={formData.first_name}
                  onChange={(e) => setFormData({ ...formData, first_name: e.target.value })}
                  placeholder="Full Name"
                  required
                  className="input"
                  data-testid="name-input"
                  autoFocus
                />
                <Button
                  type="button"
                  onClick={handleNext}
                  className="submit-btn"
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
                  className="input"
                  data-testid="email-input"
                  autoFocus
                />
                <div className="button-row">
                  <Button
                    type="button"
                    onClick={handleBack}
                    className="back-btn"
                  >
                    <ArrowLeft size={18} /> Back
                  </Button>
                  <Button
                    type="button"
                    onClick={handleNext}
                    className="submit-btn"
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
                    className="input"
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
                    className="input"
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
                    className="back-btn"
                  >
                    <ArrowLeft size={18} /> Back
                  </Button>
                  <Button
                    type="button"
                    onClick={handleNext}
                    className="submit-btn"
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
                  className="input"
                  data-testid="invite-code-input"
                  autoFocus
                />
                <p className="invite-hint">Only available to select members</p>

                <div className="button-row">
                  <Button
                    type="button"
                    onClick={handleBack}
                    className="back-btn"
                  >
                    <ArrowLeft size={18} /> Back
                  </Button>
                  <Button
                    type="submit"
                    disabled={loading}
                    className="submit-btn"
                    data-testid="submit-button"
                  >
                    {loading ? 'Creating...' : 'Create Account'}
                  </Button>
                </div>
              </div>
            )}
          </form>

          <p className="alt-link">
            Already have an account?{' '}
            <a onClick={() => navigate('/login')}>Login</a>
          </p>
        </div>
      </div>

      {/* Right Column - Video */}
      <div className="right">
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

      <style jsx>{`
        .auth-container {
          display: flex;
          height: 100vh;
          align-items: center;
          background: #000;
          color: #f0f8f5;
          font-family: system-ui, 'Segoe UI', Roboto, Arial, sans-serif;
          position: relative;
          overflow: hidden;
        }

        .left {
          flex: 1;
          position: relative;
          display: flex;
          align-items: center;
          justify-content: center;
          padding: 40px;
          z-index: 2;
        }

        .right {
          flex: 1;
          position: relative;
          display: flex;
          align-items: center;
          justify-content: center;
        }

        .right video {
          width: 100%;
          height: 100%;
          object-fit: cover;
        }

        .content {
          display: flex;
          flex-direction: column;
          align-items: center;
          text-align: center;
          max-width: 420px;
          width: 100%;
          gap: 20px;
          background: rgba(6, 12, 16, 0.75);
          border: 1px solid rgba(46, 223, 163, 0.25);
          border-radius: 16px;
          padding: 48px;
          backdrop-filter: blur(8px);
          box-shadow: 0 6px 24px rgba(0, 0, 0, 0.35);
        }

        .logo {
          width: 90px;
          height: 90px;
          cursor: pointer;
          transition: transform 0.3s ease;
        }

        .logo:hover {
          transform: scale(1.05);
        }

        h1 {
          font-size: 2rem;
          font-weight: 700;
          margin: 0;
        }

        .step-indicator {
          font-size: 0.9rem;
          color: #8a9bb0;
          margin: 0;
        }

        .form {
          width: 100%;
        }

        .form-step {
          display: flex;
          flex-direction: column;
          gap: 16px;
          width: 100%;
        }

        .password-wrapper {
          position: relative;
        }

        .input {
          width: 100%;
          padding: 12px 16px;
          border-radius: 8px;
          border: 1px solid rgba(46, 223, 163, 0.25);
          background: rgba(0, 0, 0, 0.3);
          color: #f0f8f5;
          font-size: 1rem;
        }

        .input::placeholder {
          color: #8a9bb0;
        }

        .input:focus {
          outline: none;
          border-color: #2edfa3;
        }

        .eye-btn {
          position: absolute;
          right: 12px;
          top: 50%;
          transform: translateY(-50%);
          background: none;
          border: none;
          color: #8a9bb0;
          cursor: pointer;
          padding: 4px;
          display: flex;
          align-items: center;
        }

        .eye-btn:hover {
          color: #2edfa3;
        }

        .invite-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          width: 100%;
        }

        .invite-label {
          font-size: 0.9rem;
          color: #8a9bb0;
        }

        .show-toggle {
          background: none;
          border: none;
          color: #2edfa3;
          cursor: pointer;
          font-size: 0.85rem;
          padding: 4px 8px;
        }

        .show-toggle:hover {
          text-decoration: underline;
        }

        .invite-hint {
          font-size: 0.8rem;
          color: #8a9bb0;
          margin: -8px 0 0 0;
        }

        .button-row {
          display: flex;
          gap: 12px;
        }

        .submit-btn {
          flex: 1;
          padding: 14px;
          border-radius: 8px;
          background: linear-gradient(135deg, #008a65, #2edfa3);
          color: #fff;
          font-weight: 600;
          font-size: 1rem;
          border: none;
          cursor: pointer;
          transition: all 0.3s ease;
          display: flex;
          align-items: center;
          justify-content: center;
          gap: 8px;
        }

        .submit-btn:hover:not(:disabled) {
          opacity: 0.85;
          transform: translateY(-2px);
        }

        .submit-btn:disabled {
          opacity: 0.5;
          cursor: not-allowed;
        }

        .back-btn {
          padding: 14px 20px;
          border-radius: 8px;
          background: rgba(255, 255, 255, 0.1);
          color: #f0f8f5;
          font-weight: 600;
          font-size: 1rem;
          border: 1px solid rgba(46, 223, 163, 0.25);
          cursor: pointer;
          transition: all 0.3s ease;
          display: flex;
          align-items: center;
          gap: 6px;
        }

        .back-btn:hover {
          background: rgba(255, 255, 255, 0.15);
        }

        .alt-link {
          font-size: 0.9rem;
          color: #8a9bb0;
        }

        .alt-link a {
          color: #2edfa3;
          cursor: pointer;
          text-decoration: none;
        }

        .alt-link a:hover {
          text-decoration: underline;
        }

        /* Mobile Responsive */
        @media (max-width: 900px) {
          .auth-container {
            flex-direction: column;
          }

          .left {
            position: absolute;
            inset: 0;
            z-index: 2;
            padding: 32px 20px;
          }

          .right {
            position: fixed;
            inset: 0;
            z-index: 1;
          }

          .content {
            background: rgba(6, 12, 16, 0.85);
            backdrop-filter: blur(12px);
            padding: 32px 24px;
          }
        }
      `}</style>

      {/* Footer */}
      <footer style={{
        position: 'fixed',
        bottom: 0,
        left: 0,
        right: 0,
        textAlign: 'center',
        padding: '12px',
        color: '#8a9bb0',
        fontSize: '0.85rem',
        zIndex: 10,
        background: 'rgba(0, 0, 0, 0.7)',
        backdropFilter: 'blur(8px)'
      }}>
        © 2026 Amarktai Crypto. All rights reserved. | Part of Amarktai Network
      </footer>
    </div>
  );
}
