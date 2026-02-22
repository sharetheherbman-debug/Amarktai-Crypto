import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { toast } from 'sonner';
import { Eye, EyeOff } from 'lucide-react';
import AuthLayout from '../components/AuthLayout';
import { post } from '../lib/apiClient';

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
    
    if (!formData.email || !formData.password) {
      toast.error('Please fill in all fields');
      return;
    }

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
      
      // Support both access_token (standard) and token (legacy) fields
      const accessToken = response.access_token || response.token;
      if (!accessToken) {
        toast.error('Login failed: no token received from server.');
        return;
      }
      localStorage.setItem('token', accessToken);
      localStorage.setItem('user', JSON.stringify(response.user || {}));
      
      // DEV: Log token metadata for debugging session issues
      if (process.env.NODE_ENV !== 'production') {
        try {
          const parts = accessToken.split('.');
          if (parts.length === 3) {
            const payload = JSON.parse(atob(parts[1]));
            const expTs = payload.exp;
            const nowTs = Math.floor(Date.now() / 1000);
            const remainSecs = expTs ? expTs - nowTs : null;
            console.debug(
              `[Auth] Token stored | length=${accessToken.length}` +
              ` | exp=${expTs ? new Date(expTs * 1000).toISOString() : 'N/A'}` +
              ` | remaining=${remainSecs != null ? remainSecs + 's' : 'N/A'}`
            );
          }
        } catch (_) {
          console.debug('[Auth] Token stored (could not decode for debug)');
        }
      }
      
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
    <AuthLayout>
      <div className="auth-content bright-glass-panel">
        <div className="auth-logo-placeholder" style={{ width: '120px', height: '60px', background: '#1e293b', borderRadius: '8px', display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer', color: '#3b82f6', fontWeight: '700', fontSize: '1.2rem' }} onClick={() => navigate('/')}>
          Amarkt<span style={{ color: '#60a5fa' }}>AI</span>
        </div>
        
        <h1 className="auth-title">
          Log in to Amarkt<span className="brand-ai">AI</span>
        </h1>

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
    </AuthLayout>
  );
}
