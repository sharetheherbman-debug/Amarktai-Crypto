import { useEffect } from 'react';
import { BrowserRouter, Routes, Route, Navigate, useNavigate } from 'react-router-dom';
import { Toaster } from 'sonner';
import Landing from './pages/Landing';
import Login from './pages/Login';
import Register from './pages/Register';
import Dashboard from './pages/Dashboard';
import ErrorBoundary from './components/ErrorBoundary';
import '@/App.css';
import '@/styles/particles.css';

function PrivateRoute({ children }) {
  const token = localStorage.getItem('token');
  return token ? children : <Navigate to="/login" replace />;
}

/**
 * Global auth:unauthorized listener — redirects to /login on 401.
 * Prevents silent 401 polling loops by catching the event from apiClient.
 */
function AuthListener() {
  const navigate = useNavigate();
  useEffect(() => {
    const handler = () => {
      localStorage.removeItem('token');
      navigate('/login', { replace: true });
    };
    window.addEventListener('auth:unauthorized', handler);
    return () => window.removeEventListener('auth:unauthorized', handler);
  }, [navigate]);
  return null;
}

function App() {
  return (
    <div className="App">
      <Toaster position="top-right" richColors />
      <div className="particles-bg" aria-hidden="true">
        <span className="particles-dots" />
      </div>
      <BrowserRouter>
        <AuthListener />
        <div className="app-shell">
          <Routes>
            <Route path="/" element={<Landing />} />
            <Route path="/login" element={<Login />} />
            <Route path="/register" element={<Register />} />
            <Route
              path="/dashboard"
              element={
                <PrivateRoute>
                  <ErrorBoundary title="Dashboard Error" message="Unable to render dashboard view.">
                    <Dashboard />
                  </ErrorBoundary>
                </PrivateRoute>
              }
            />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </div>
      </BrowserRouter>
    </div>
  );
}

export default App;
