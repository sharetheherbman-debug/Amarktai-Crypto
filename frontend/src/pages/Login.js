import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { toast } from 'sonner';
import { Eye, EyeOff } from 'lucide-react';
import { API_BASE } from '../lib/api';
import './Auth.css';

const API = API_BASE;

export default function Login() {
  const [showPassword, setShowPassword] = useState(false);
  const [formData, setFormData] = useState({
    email: '',
    password: ''
  });
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();

  const handleSubmit = async (e) => {
    e.preventDefault();
    
    console.log('Login attempt:', { email: formData.email });
    console.log('API endpoint:', API);
    
    if (!formData.email || !formData.password) {
      toast.error('Please fill in all fields');
      return;
    }

    setLoading(true);
    try {
      const response = await axios.post(`${API}/auth/login`, formData);
      console.log('Login response:', response.data);
      
      // Clear all previous session data including chat
      localStorage.clear();
      sessionStorage.clear();
      
      // TASK B - Use access_token from standardized auth response
      localStorage.setItem('token', response.data.access_token);
      localStorage.setItem('user', JSON.stringify(response.data.user));
      
      toast.success('Welcome back!');
      navigate('/dashboard');
    } catch (error) {
      console.error('Login error:', error);
      toast.error(error.response?.data?.detail || 'Login failed. Please check your credentials.');
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
            className="auth-logo"
            onClick={() => navigate('/')}
          />
          
          <h1 className="auth-title">Login</h1>

          <form onSubmit={handleSubmit} className="auth-form">
            <div className="form-group">
              <Input
                type="email"
                value={formData.email}
                onChange={(e) => setFormData({ ...formData, email: e.target.value })}
                placeholder="Email"
                required
                className="auth-input"
                data-testid="email-input"
              />
            </div>

            <div className="form-group">
              <div className="password-wrapper">
                <Input
                  type={showPassword ? 'text' : 'password'}
                  value={formData.password}
                  onChange={(e) => setFormData({ ...formData, password: e.target.value })}
                  placeholder="Password"
                  required
                  className="auth-input"
                  data-testid="password-input"
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

            <Button
              type="submit"
              disabled={loading}
              className="auth-submit-btn"
              data-testid="submit-button"
            >
              {loading ? 'Logging in...' : 'Login'}
            </Button>
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

    </div>
  );
}
