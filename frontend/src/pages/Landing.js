import { useNavigate } from 'react-router-dom';
import { useState, useEffect, useRef } from 'react';
import { Button } from '@/components/ui/button';
import AuthLayout from '../components/AuthLayout';
import { Volume2, VolumeX } from 'lucide-react';

export default function Landing() {
  const navigate = useNavigate();
  const [isMuted, setIsMuted] = useState(true);
  const [hasInteracted, setHasInteracted] = useState(false);
  const audioRef = useRef(null);

  useEffect(() => {
    const userMuted = localStorage.getItem('amarktai_userMuted');
    if (userMuted === 'false') {
      setIsMuted(false);
    }

    const tryAutoplay = async () => {
      try {
        if (audioRef.current && !isMuted) {
          await audioRef.current.play();
          setHasInteracted(true);
        }
      } catch (err) {
        console.log('Autoplay blocked');
      }
    };

    tryAutoplay();

    const handleVisibilityChange = () => {
      if (document.hidden && audioRef.current) {
        audioRef.current.pause();
      } else if (!document.hidden && audioRef.current && !isMuted && hasInteracted) {
        audioRef.current.play();
      }
    };

    const handleBlur = () => {
      if (audioRef.current) audioRef.current.pause();
    };

    const handleFocus = () => {
      if (audioRef.current && !isMuted && hasInteracted) audioRef.current.play();
    };

    document.addEventListener('visibilitychange', handleVisibilityChange);
    window.addEventListener('blur', handleBlur);
    window.addEventListener('focus', handleFocus);

    return () => {
      document.removeEventListener('visibilitychange', handleVisibilityChange);
      window.removeEventListener('blur', handleBlur);
      window.removeEventListener('focus', handleFocus);
    };
  }, [isMuted, hasInteracted]);

  const toggleSound = async () => {
    setHasInteracted(true);
    const newMuted = !isMuted;
    setIsMuted(newMuted);
    localStorage.setItem('amarktai_userMuted', String(newMuted));

    if (audioRef.current) {
      if (newMuted) {
        audioRef.current.pause();
      } else {
        try {
          await audioRef.current.play();
        } catch (err) {
          console.error('Failed to play audio:', err);
        }
      }
    }
  };

  return (
    <AuthLayout>
      <audio
        ref={audioRef}
        src="/assets/thunderstruck.mp3"
        loop
        preload="none"
      />

      {/* Sound Control */}
      <button
        onClick={toggleSound}
        className={`landing-sound ${isMuted ? 'pulse' : ''}`}
        title={isMuted ? 'Play Sound' : 'Mute Sound'}
        data-testid="sound-toggle"
      >
        {isMuted ? <VolumeX size={20} /> : <Volume2 size={20} />}
      </button>

      <div className="auth-content bright-glass-panel">
        <img src="/assets/final-logo-v2.png" alt="Amarktai Crypto" className="auth-logo landing-logo-lg" style={{ width: '200px', height: '200px' }} />
        <div className="landing-header">
          <p className="landing-welcome">Welcome to</p>
          <h1 className="auth-title landing-brand">
            Amarkt<span className="brand-ai">AI</span>
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
