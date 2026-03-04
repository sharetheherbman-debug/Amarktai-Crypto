import { useNavigate } from 'react-router-dom';
import { useState, useEffect, useRef } from 'react';
import { Button } from '@/components/ui/button';
import SiteFooter from '../components/SiteFooter';
import { Volume2, VolumeX } from 'lucide-react';
import './Auth.css';
import './Landing.css';

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
    <div className="auth-container landing-container landing-hero-layout">
      <audio
        ref={audioRef}
        src="/assets/thunderstruck.mp3"
        loop
        preload="auto"
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

      {/* LEFT — Brand + CTAs */}
      <div className="landing-hero-left">
        <div className="landing-hero-content">
          <img src="/assets/logo.png" alt="Amarktai Network" className="auth-logo landing-logo-lg" />
          <h1 className="landing-headline">Amarktai Network</h1>
          <p className="landing-subheadline">Real-Time AI Trading, Built for Control</p>
          <div className="landing-cta">
            <Button onClick={() => navigate('/login')} className="auth-submit-btn landing-cta-btn landing-primary-btn">
              Launch Dashboard
            </Button>
            <Button onClick={() => navigate('/register')} className="auth-submit-btn landing-cta-btn landing-register-btn">
              Create Account
            </Button>
          </div>
          <p className="landing-proof-bar">Connect to see live metrics</p>
        </div>
      </div>

      {/* RIGHT — Video */}
      <div className="landing-hero-right">
        <video
          autoPlay
          muted
          loop
          playsInline
          poster="/assets/poster.jpg"
          className="landing-hero-video"
        >
          <source src="/assets/background.mp4" type="video/mp4" />
        </video>
        <div className="landing-hero-overlay" />
        <div className="landing-scanlines" />
      </div>

      <SiteFooter />
    </div>
  );
}
